"""spawn_vehicle.launch.py — single vehicle spawner for Ignition Fortress.

Starts: robot_state_publisher → Ignition spawn → sensor bridge → controllers → EKF.

Sensor fusion pipeline (added for drift reduction):
  diff_drive_controller/odom + /<vid>/imu → ekf_node → /<vid>/odometry/filtered
  ekf_node publishes odom→base_link TF (diff_drive TF disabled to avoid conflict).
  slam_toolbox uses the EKF-fused odom for better scan-to-scan alignment.

Real-vehicle migration:
  - robot_state_publisher: same (use_sim:=false)
  - spawn / bridge: remove (hardware publishes sensors directly to ROS2)
  - controllers: same YAML, same spawner commands
  - cmd_relay: remove (diff_drive_controller subscribes directly on real robot)
  - ekf_node: keep, just set use_sim_time:=false
"""
from __future__ import annotations

import os
import string
import subprocess
import tempfile

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    OpaqueFunction,
    TimerAction,
)
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

# FIT0186 12V 43.8:1 / 바퀴 지름 120mm / 바퀴 간격 290mm  확정 (2026-05-19)
_WHEEL_SEP = 0.290   # 290mm 바퀴 간격
_WHEEL_R   = 0.060   # 60mm = 120mm 지름 ÷ 2
_V_MAX     = 0.2     # 0.3→0.2: 충돌 예방 강화 — 맵 오염 누적 방지
_W_MAX     = 2.0


def _make_arm_yaml(vehicle_id: str) -> str:
    """forward_command_controller params for the 4-DOF arm.

    velocity interface: gz_ros2_control 0.7.x GazeboSimSystem position interface is no-op.
    velocity interface works (same path as wheels).
    arm_scan_node uses dead-reckoning (velocity integration) as position estimate
    so P control + soft limit work correctly without depending on JSB publish rate.
    """
    config = {
        '/**': {
            'ros__parameters': {
                'joints': ['arm_pan_joint'],
                'interface_name': 'velocity',
            }
        }
    }
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', delete=False,
        prefix=f'arm_{vehicle_id}_',
    )
    yaml.dump(config, tmp, default_flow_style=False)
    tmp.close()
    return tmp.name


def _make_controller_yaml(vehicle_id: str) -> str:
    """Write per-vehicle diff_drive_controller params to a temp file, return path.

    This file is embedded in master_yaml (via _make_master_yaml) as the
    diff_drive_controller.params_file reference.  gz_ros2_control reads it
    via the URDF <parameters ns_ctrl_yaml> tag at CM startup so the controller
    node receives per-vehicle params when auto-loaded, without any spawner
    set_parameters call.

    Frame IDs MUST be explicitly namespaced (e.g. peer_1/odom) so that:
      - slam_toolbox / AMCL / EKF find the correct <ns>/odom → <ns>/base_link
      - ros2_control publishes frame_id='peer_N/odom', not the plain 'odom'
        that would cause TF conflicts across vehicles.
    """
    config = {
        '/**': {
            'ros__parameters': {
                'left_wheel_names':  ['left_wheel_joint'],
                'right_wheel_names': ['right_wheel_joint'],
                'wheel_separation': _WHEEL_SEP,
                'wheel_radius':     _WHEEL_R,
                'odom_frame_id':  f'{vehicle_id}/odom',
                'base_frame_id':  f'{vehicle_id}/base_link',
                'enable_odom_tf': False,
                'publish_rate':   50.0,
                'cmd_vel_timeout': 0.5,
                'use_stamped_vel': False,
                'linear.x.max_velocity':   _V_MAX,
                'linear.x.min_velocity':  -_V_MAX,
                'angular.z.max_velocity':  _W_MAX,
                'angular.z.min_velocity': -_W_MAX,
                'pose_covariance_diagonal':
                    [0.001, 0.001, 1e6, 1e6, 1e6, 0.010],
                'twist_covariance_diagonal':
                    [0.001, 0.001, 1e6, 1e6, 1e6, 0.010],
            }
        }
    }
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', delete=False,
        prefix=f'ddc_{vehicle_id}_',
    )
    yaml.dump(config, tmp, default_flow_style=False)
    tmp.close()
    return tmp.name


def _render_ekf_yaml(vehicle_id: str) -> str:
    """Substitute ${vehicle_id} in ekf_vehicle.yaml and write to a temp file."""
    nav_share = get_package_share_directory('aip_fleet_nav')
    tmpl_path = os.path.join(nav_share, 'params', 'ekf_vehicle.yaml')
    with open(tmpl_path) as f:
        rendered = string.Template(f.read()).substitute(vehicle_id=vehicle_id)
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', delete=False,
        prefix=f'ekf_{vehicle_id}_',
    )
    tmp.write(rendered)
    tmp.close()
    return tmp.name


def _spawn_one(context, *_args, **_kwargs) -> list:
    vid    = LaunchConfiguration('vehicle_id').perform(context)
    sx     = LaunchConfiguration('spawn_x').perform(context)
    sy     = LaunchConfiguration('spawn_y').perform(context)
    sz     = LaunchConfiguration('spawn_z').perform(context)
    syaw   = LaunchConfiguration('spawn_yaw').perform(context)
    world  = LaunchConfiguration('world_name').perform(context)

    desc_share = get_package_share_directory('aip_main_description')
    gz_share   = get_package_share_directory('aip_fleet_gazebo')
    urdf_file  = os.path.join(desc_share, 'urdf', 'main_agv.urdf.xacro')
    ctrl_yaml  = _make_controller_yaml(vid)
    arm_yaml   = _make_arm_yaml(vid)
    ekf_yaml   = _render_ekf_yaml(vid)
    relay_py   = os.path.join(gz_share, 'scripts', 'cmd_relay.py')
    fixer_py   = os.path.join(gz_share, 'scripts', 'odom_frame_fixer.py')

    # ── 1. URDF string from xacro ──────────────────────────────────────────
    # ctrl_yaml을 명시적으로 전달: xacro 내부 $(find ...) 는 stale ament 캐시로
    # Windows 경로(/mnt/c/...)를 반환할 수 있어 gz_ros2_control 초기화 실패 유발.
    # Python 런타임에서 해석한 절대 경로를 직접 주입해 경로 오염을 차단.
    robot_desc = subprocess.check_output(
        ['xacro', urdf_file, f'namespace:={vid}', 'use_sim:=true',
         f'ctrl_yaml:={ctrl_yaml}']
    ).decode()

    # ── 2. robot_state_publisher ───────────────────────────────────────────
    # joint_states_rsp 로 리매핑: joint_states_relay가 RELIABLE로 중계해 10Hz 안정 수신.
    # RSP 기본 구독은 BEST_EFFORT+VOLATILE — JSB(RELIABLE+TRANSIENT_LOCAL) 와 불일치로
    # 30Hz 발행 중 1.25Hz 만 수신 → 바퀴/암 TF 지연.  릴레이 경유 시 10Hz 보장.
    rsp = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        namespace=vid,
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_desc,
            'use_sim_time': True,
        }],
        remappings=[('joint_states', 'joint_states_rsp')],
    )

    # ── 2b. joint_states_relay ────────────────────────────────────────────
    # JSB(RELIABLE+TRANSIENT_LOCAL) → RELIABLE 구독 → 10Hz RELIABLE+VOLATILE 재발행.
    # RSP가 BEST_EFFORT로 구독해도 10Hz 저속에서는 드롭율 극히 낮아 TF 10Hz 달성.
    js_relay = Node(
        package='aip_fleet_gazebo',
        executable='joint_states_relay.py',
        name=f'joint_states_relay_{vid}',
        namespace=vid,
        output='screen',
        parameters=[{'use_sim_time': True}],
    )

    # ── 3. Spawn entity in Ignition (reads robot_description topic) ────────
    spawn = Node(
        package='ros_gz_sim',
        executable='create',
        name=f'spawn_{vid}',
        output='screen',
        arguments=[
            '-world', world,
            '-name',  vid,
            '-topic', f'/{vid}/robot_description',
            '-x', sx, '-y', sy, '-z', sz, '-Y', syaw,
        ],
    )

    # ── 4. Sensor bridge: Ignition topics → ROS2 topics ───────────────────
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name=f'bridge_{vid}',
        output='screen',
        arguments=[
            # LiDAR: IGN → ROS2
            f'/{vid}/scan_gz'
            f'@sensor_msgs/msg/LaserScan'
            f'[ignition.msgs.LaserScan',
            # IMU: IGN → ROS2
            f'/{vid}/imu_gz'
            f'@sensor_msgs/msg/Imu'
            f'[ignition.msgs.IMU',
            # /clock은 ign_fleet.launch.py의 단일 브리지에서만 발행.
            # 차량 수만큼 브리지가 생기면 타임스탬프 순서 역전 → TF 시간 역행 발생.
        ],
        remappings=[
            (f'/{vid}/scan_gz', f'/{vid}/scan'),
            (f'/{vid}/imu_gz',  f'/{vid}/imu'),
        ],
    )

    # ── 5. ros2_control: spawners ─────────────────────────────────────────────
    # 스포너 순차 실행 + 충분한 간격:
    #   - JSB: t=15s (SLAM 시작 전 — DDS 조용한 시간대)
    #   - DDC: t=25s (SLAM+EKF+rf2o 초기화 완료 후 — t=16~21s DDS 혼잡 구간 회피)
    #   - ARM: t=35s (DDC 완료 후 충분한 여유)
    #
    # t=18s 에 DDC 를 실행하면 t=16s SLAM + t=17s EKF/rf2o 초기화가 겹쳐
    # DDS 참여자 목록이 활발히 갱신되는 시점에 set_parameters 서비스 호출이 발생.
    # 이 구간에 CM의 set_parameters 콜백이 지연되면
    # set_parameters 성공(INFO 출력) 후 load_controller 시점에
    # "type param not defined" 오류가 발생함.
    # t=25s 로 이동하면 DDS 가 안정된 상태에서 서비스 호출 가능.
    jsb = Node(
        package='controller_manager',
        executable='spawner',
        namespace=vid,
        name=f'jsb_spawner_{vid}',
        output='screen',
        arguments=[
            'joint_state_broadcaster',
            '--controller-manager', f'/{vid}/controller_manager',
            '--controller-manager-timeout', '600',  # 180→600: peer_2/3 CM 초기화 지연(최대 541s 실측) 대응
            '--controller-type', 'joint_state_broadcaster/JointStateBroadcaster',
        ],
        parameters=[{'use_sim_time': True}],
    )
    ddc = Node(
        package='controller_manager',
        executable='spawner',
        namespace=vid,
        name=f'ddc_spawner_{vid}',
        output='screen',
        arguments=[
            'diff_drive_controller',
            '--controller-manager', f'/{vid}/controller_manager',
            '--controller-manager-timeout', '600',  # 180→600: JSB와 동일, CM 지연 대응
            '--controller-type', 'diff_drive_controller/DiffDriveController',
            '--param-file', ctrl_yaml,
        ],
        parameters=[{'use_sim_time': True}],
    )

    # ── 5b. arm_position_controller 스포너 ────────────────────────────────────
    arm_ctrl = Node(
        package='controller_manager',
        executable='spawner',
        namespace=vid,
        name=f'arm_spawner_{vid}',
        output='screen',
        arguments=[
            'arm_position_controller',
            '--controller-manager', f'/{vid}/controller_manager',
            '--controller-manager-timeout', '600',  # 180→600: 극단적 CPU 부하 시 CM 초기화 541s 실측
            '--controller-type', 'forward_command_controller/ForwardCommandController',
            '--param-file', arm_yaml,
        ],
        parameters=[{'use_sim_time': True}],
    )

    # ── 5c. arm_scan_node: 4-DOF 암 스캔/추적 제어 ──────────────────────────
    arm_scan = Node(
        package='aip_fleet_gazebo',
        executable='arm_scan_node.py',
        name=f'arm_scan_{vid}',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'vehicle_id':   vid,
        }],
    )

    # ── 5d. stuck_escape_node: 고착 감지 + costmap 우회 강제 탈출 ────────────
    # MPPI가 주변 모든 방향 충돌 판정 시 twist_mux priority=15 슬롯으로 직접 후진 주입
    stuck_escape = Node(
        package='aip_fleet_gazebo',
        executable='stuck_escape_node.py',
        name=f'stuck_escape_{vid}',
        output='screen',
        parameters=[{
            'use_sim_time':       False,   # wall time 기반 감지 (sim time 왜곡 방지)
            'vehicle_id':         vid,
            'stuck_timeout_sec':  5.0,   # 8.0→5.0: 더 빠른 고착 감지
            'escape_speed':       0.08,  # 0.06→0.08: 후진 탈출 거리 확보
            'escape_duration':    3.0,   # 2.0→3.0: 후진 거리 0.12m→0.24m
            'cooldown_sec':       4.0,   # 6.0→4.0: 반복 고착 시 회복 루프 단축
        }],
    )

    # ── 6. cmd_vel relay: /<vid>/cmd_vel → diff_drive_controller input ──────
    relay = ExecuteProcess(
        cmd=['python3', relay_py, '--ros-args', '-p', f'vehicle_id:={vid}'],
        name=f'cmd_relay_{vid}',
        output='screen',
    )

    # ── 7a. odom_frame_fixer: corrects frame_id/child_frame_id on diff_drive odom ──
    # diff_drive_controller publishes frame_id='odom' (plain); SLAM/AMCL/EKF need
    # 'peer_N/odom'. This relay rewrites the header before EKF sees it.
    fixer = ExecuteProcess(
        cmd=['python3', fixer_py, '--ros-args', '-p', f'vehicle_id:={vid}'],
        name=f'odom_frame_fixer_{vid}',
        output='screen',
    )

    # ── 7b. odom relay: diff_drive_controller/odom → /<vid>/odom ──────────────
    # Fleet standard (coordinator, Nav2) expects /<vid>/odom (unfiltered).
    odom_relay = Node(
        package='topic_tools',
        executable='relay',
        name=f'odom_relay_{vid}',
        namespace=vid,
        output='screen',
        arguments=[
            f'/{vid}/diff_drive_controller/odom',
            f'/{vid}/odom',
        ],
        parameters=[{'use_sim_time': True}],
    )

    # ── 8. rf2o LiDAR 오도메트리: 연속 스캔 ICP → 슬립 무관 속도 추정 ──────────
    # 선회 시 바퀴 슬립으로 인한 엔코더 오차를 LiDAR 기반 속도(vx·vyaw)로 보정.
    # publish_tf: false → EKF가 TF 담당 (충돌 방지).
    # freq: 10Hz → LiDAR 업데이트 주기와 일치.
    # odom_rf2o의 절대 위치는 EKF에서 미사용(드리프트) — 속도(vx·vyaw)만 융합.
    rf2o = Node(
        package='rf2o_laser_odometry',
        executable='rf2o_laser_odometry_node',
        name='rf2o_laser_odometry',
        namespace=vid,
        output='log',
        arguments=['--ros-args', '--log-level', 'ERROR'],
        parameters=[{
            'use_sim_time':        True,
            'laser_scan_topic':    f'/{vid}/scan',
            'odom_topic':          f'/{vid}/odom_rf2o',
            'base_frame_id':       f'{vid}/base_link',
            'odom_frame_id':       f'{vid}/odom',
            'publish_tf':          False,   # EKF가 TF 발행 — 충돌 방지
            'init_pose_from_topic': '',     # 초기 위치: 원점에서 시작
            'freq':                10.0,    # LiDAR 10Hz와 일치
        }],
    )

    # ── 9. EKF fusion: wheel odom + IMU gyro + rf2o LiDAR odom ─────────────
    # Starts at t=8 s (after fixer is up at t=7 s).
    # publish_tf: true → EKF publishes peer_N/odom → peer_N/base_link TF.
    # diff_drive enable_odom_tf: false → no TF conflict.
    ekf = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf',
        namespace=vid,
        output='screen',
        parameters=[ekf_yaml, {'use_sim_time': True}],
    )

    # base_footprint TF: URDF의 base_joint (parent=base_footprint, child=base_link)를
    # robot_state_publisher가 이미 발행함. static_transform_publisher를 추가하면
    # base_link ↔ base_footprint 루프가 형성되므로 별도 노드 불필요.

    # RSP must be fully registered on DDS before the Gazebo entity spawns.
    # gz_ros2_control immediately calls /{ns}/robot_state_publisher/get_parameters
    # when the entity loads. If RSP and spawn start simultaneously (heavy DDS load
    # with peer_1 already running), the response is dropped and gz_ros2_control
    # spins forever waiting → controller_manager never created → diff_drive never
    # runs → EKF has no odom → no odom→base_link TF → AMCL can't converge.
    # 3 s delay gives RSP time to complete DDS announcement before gz_ros2_control
    # makes the service call.
    return [
        rsp,
        bridge,
        # RSP 예열 5s: gz_ros2_control이 스폰 즉시 /{ns}/robot_state_publisher/get_parameters
        # 를 호출하므로, peer_2/3 스폰 시점(시스템 고부하)에서도 DDS 응답 준비 완료 필요.
        # (peer_1은 저부하라 3s면 충분하나, 공통 5s가 더 안전)
        TimerAction(period=5.0,  actions=[spawn]),
        # 스포너 순차 실행: jsb → ddc → arm_ctrl 을 3 s 간격으로 띄워
        # controller_manager 서비스 요청 충돌(DDS 응답 타임아웃 → "already loaded")
        # 방지. 동시 실행 시 set_parameters/load_controller 응답이 드롭되어
        # 스포너가 재시도하면 "already loaded" FATAL 이 발생했음.
        TimerAction(period=15.0, actions=[jsb, js_relay]),
        # DDC: t=40s — RTF=1.0에서 SLAM(t=16s)+EKF(t=17s) 초기화 + DDS 안정화까지
        # 최소 35~40s 소요 실측. 기존 t=25s에서 peer_1 FATAL 실패 재현됨.
        # peer_2가 t=78s에 동일 ddc 성공 → DDS 안정화 기준선 확인.
        TimerAction(period=40.0, actions=[ddc]),
        # ARM: t=50s — DDC(t=40s) 완료 후 10s 여유.
        TimerAction(period=50.0, actions=[arm_ctrl]),
        TimerAction(period=16.0, actions=[relay, odom_relay, fixer]),
        TimerAction(period=17.0, actions=[rf2o, ekf]),
        TimerAction(period=50.0, actions=[arm_scan, stuck_escape]),
    ]


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        DeclareLaunchArgument('vehicle_id',  default_value='peer_1'),
        DeclareLaunchArgument('spawn_x',     default_value='0.0'),
        DeclareLaunchArgument('spawn_y',     default_value='0.0'),
        DeclareLaunchArgument('spawn_z',     default_value='0.05'),
        DeclareLaunchArgument('spawn_yaw',   default_value='0.0'),
        DeclareLaunchArgument('world_name',  default_value='fleet_world'),
        OpaqueFunction(function=_spawn_one),
    ])
