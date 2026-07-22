"""Launch the central-PC-side fleet services.

This starts everything that lives on the Ubuntu 22.04 central PC *outside*
of docker-compose — intended for local dev or when you prefer host
installation over the containerized stack. In production the same
services run via docker/central/docker-compose.yml.

Started:
  - aip_fleet_supervisor/supervisor_node
  - aip_fleet_supervisor/watchdog_node
  - foxglove_bridge (WebSocket :8765)
  - twist_mux × N  (one per non-main vehicle; skipped when with_twist_mux:=false)

The FastDDS Discovery Server and micro-ROS Agent are *not* started here —
they are always containerized (see docker/central/docker-compose.yml)
because they need to survive ROS2 daemon restarts.

The set of vehicles the supervisor watches is controlled via a YAML
params file (default: the package's `config/supervisor.yaml`). Override
with the `supervisor_params` launch arg if you need a non-standard roster.

Note on main AGV: the main AGV runs its own twist_mux inside its ROS2
workspace (separate team). Central only manages scouts.

Note on with_twist_mux: fleet_sim.launch.py spawns twist_mux for all
vehicles itself and passes with_twist_mux:=false to avoid duplicates.
"""
from __future__ import annotations

import os
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument, GroupAction, OpaqueFunction, SetEnvironmentVariable,
)
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace
from launch_ros.parameter_descriptions import ParameterValue


def _make_foxglove_node(context, *_args, **_kwargs):
    """foxglove_bridge 노드를 조건부로 생성.

    패키지 미설치 환경에서 Node() 생성 자체가 PackageNotFoundError를 내는 것을 방지.
    with_foxglove:=true 일 때만 Node 객체를 생성한다.
    설치: sudo apt install ros-humble-foxglove-bridge
    """
    if LaunchConfiguration('with_foxglove').perform(context).lower() != 'true':
        return []
    return [
        Node(
            package='foxglove_bridge',
            executable='foxglove_bridge',
            name='foxglove_bridge',
            output='screen',
            parameters=[{
                'port': 8765,
                'address': LaunchConfiguration('foxglove_address').perform(context),
                'tls': False,
                'send_buffer_limit': 10000000,
                'use_sim_time': False,
                'topic_whitelist': [
                    '^/tf$', '^/tf_static$', '^/clock$', '^/map_static$',
                    '^/fleet/',
                    '^/peer_[123]/scan$', '^/peer_[123]/amcl_pose$',
                    '^/peer_[123]/plan$', '^/peer_[123]/patrol_path_viz$',
                    '^/peer_[123]/arm_fov_marker$',
                    '^/peer_[123]/odometry/filtered$', '^/peer_[123]/particlecloud$',
                    '^/peer_1/explore/goal_marker$',
                ],
                'num_threads': 4,
            }],
        ),
    ]


def _make_scout_twist_mux_nodes(context, *args, **kwargs):
    """Return twist_mux GroupActions for each non-main vehicle."""
    if LaunchConfiguration('with_twist_mux').perform(context).lower() != 'true':
        return []

    bringup_share = get_package_share_directory('aip_fleet_bringup')
    twist_mux_params = os.path.join(bringup_share, 'config', 'twist_mux_vehicle.yaml')

    supervisor_params_path = LaunchConfiguration('supervisor_params').perform(context)
    with open(supervisor_params_path) as f:
        config = yaml.safe_load(f)
    vehicle_ids = config['aip_fleet_supervisor']['ros__parameters']['vehicle_ids']

    nodes = []
    for vid in vehicle_ids:
        if vid == 'aip1':
            # aip1(메인 AGV)의 twist_mux는 RPi4B fleet_main.launch.py에서 담당.
            continue
        nodes.append(GroupAction([
            PushRosNamespace(vid),
            Node(
                package='twist_mux',
                executable='twist_mux',
                name='twist_mux',
                output='screen',
                parameters=[twist_mux_params],
                remappings=[('cmd_vel_out', 'cmd_vel')],
            ),
        ]))
    return nodes


def _make_coordinator_nodes(context, *args, **kwargs):
    """Return one coordinator_node per follower vehicle.

    The leader is determined by the `leader_ns` launch argument (default: 'aip1').
    All other vehicles in vehicle_ids become followers.  Offsets produce a
    V-formation: index-0 follower directly behind, then alternating left/right.

    For the 5-peer Gazebo fleet use leader_ns:=peer_1 with supervisor_peers.yaml.
    For the real 3-vehicle fleet use the default leader_ns:=aip1 with supervisor.yaml.
    """
    if LaunchConfiguration('with_coordinator').perform(context).lower() != 'true':
        return []

    leader = LaunchConfiguration('leader_ns').perform(context)

    supervisor_params_path = LaunchConfiguration('supervisor_params').perform(context)
    with open(supervisor_params_path) as f:
        config = yaml.safe_load(f)
    vehicle_ids = config['aip_fleet_supervisor']['ros__parameters']['vehicle_ids']

    followers = [v for v in vehicle_ids if v != leader]
    nodes = []
    for i, vid in enumerate(followers):
        # Symmetric V-formation (chevron) offsets.
        # Pairs fill rows outward: row-1 left+right, row-2 left+right, ...
        #   i=0 → row-1 left   (-1.5, +1.0)
        #   i=1 → row-1 right  (-1.5, -1.0)
        #   i=2 → row-2 left   (-3.0, +2.0)
        #   i=3 → row-2 right  (-3.0, -2.0)
        row      = i // 2 + 1             # 1, 1, 2, 2, 3, 3, …
        side     = 1 if i % 2 == 0 else -1  # +1=left, -1=right
        offset_x = -row * 1.5
        offset_y  = side * row * 1.0
        nodes.append(Node(
            package='aip_fleet_coordinator',
            executable='coordinator_node',
            name=f'coordinator_{vid}',
            output='screen',
            parameters=[{
                'leader_ns': leader,
                'follower_ns': vid,
                'offset_x': offset_x,
                'offset_y': offset_y,
            }],
        ))
    return nodes


def _make_localizer_nodes(context, *args, **kwargs):
    """Launch scout_localizer_node when with_localizer:=true.

    MODE A (기본, camera_mode:=fixed):
      static_transform_publisher로 aip1/base_link → aip1/camera_link 발행.
      카메라가 차체에 고정 장착된 경우.

    MODE B (확장 예정, camera_mode:=servo_arm):
      static_transform_publisher를 생략. 암 제어기가 발행하는 TF를 그대로 사용.
      camera_frame 파라미터를 암 end-effector 프레임명으로 변경해야 함.
      재개 조건: scout_localizer_node.py 상단 주석의 MODE B 체크리스트 참조.
    """
    if LaunchConfiguration('with_localizer').perform(context).lower() != 'true':
        return []

    camera_mode = LaunchConfiguration('camera_mode').perform(context)

    supervisor_params_path = LaunchConfiguration('supervisor_params').perform(context)
    with open(supervisor_params_path) as f:
        config = yaml.safe_load(f)
    vehicle_ids = config['aip_fleet_supervisor']['ros__parameters']['vehicle_ids']

    scouts = [v for v in vehicle_ids if v != 'aip1']
    marker_ids = list(range(1, len(scouts) + 1))  # IDs 1, 2, …

    nodes = []

    if camera_mode == 'fixed':
        # MODE A: 고정 카메라 — static TF 발행.
        cx = LaunchConfiguration('camera_offset_x').perform(context)
        cy = LaunchConfiguration('camera_offset_y').perform(context)
        cz = LaunchConfiguration('camera_offset_z').perform(context)
        camera_frame = 'aip1/camera_link'
        nodes.append(Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='camera_tf_pub',
            output='screen',
            arguments=[cx, cy, cz, '0', '0', '0',
                       'aip1/base_link', 'aip1/camera_link'],
        ))
    else:
        # MODE B: 서보 암 카메라 — 암 드라이버가 TF를 발행하므로 static TF 없음.
        # camera_frame은 암 end-effector 프레임명으로 설정 필요.
        camera_frame = LaunchConfiguration('camera_frame').perform(context)

    nodes.append(Node(
        package='aip_fleet_coordinator',
        executable='scout_localizer_node',
        name='scout_localizer',
        output='screen',
        parameters=[{
            'camera_ns': 'aip1',
            'camera_frame': camera_frame,
            'marker_size': 0.15,
            'marker_ids': marker_ids,
            'marker_namespaces': scouts,
        }],
    ))
    return nodes




def _make_telemetry_node(context, *args, **kwargs):
    """Launch telemetry_node when with_telemetry:=true."""
    if LaunchConfiguration('with_telemetry').perform(context).lower() != 'true':
        return []
    return [Node(
        package='aip_fleet_telemetry',
        executable='telemetry_node',
        name='aip_fleet_telemetry',
        output='screen',
    )]


def _make_security_env(context, *args, **kwargs):
    """Inject SROS2 environment variables when with_security:=true.

    Requires the keystore to be pre-generated via scripts/sros2_init.sh.
    Strategy=Enforce means nodes that lack a certificate will fail to start —
    use Permissive during initial roll-out and switch to Enforce once all
    nodes have been provisioned.
    """
    if LaunchConfiguration('with_security').perform(context).lower() != 'true':
        return []

    ws_root = os.path.join(
        get_package_share_directory('aip_fleet_bringup'),
        '..', '..', '..', '..', '..', 'config', 'security', 'keystore',
    )
    keystore = os.path.normpath(ws_root)

    if not os.path.isdir(keystore):
        raise RuntimeError(
            f'SROS2 keystore not found at {keystore}. '
            'Run scripts/sros2_init.sh first.'
        )

    return [
        SetEnvironmentVariable('ROS_SECURITY_ENABLE', 'true'),
        SetEnvironmentVariable('ROS_SECURITY_STRATEGY', 'Enforce'),
        SetEnvironmentVariable('ROS_SECURITY_KEYSTORE', keystore),
    ]


def generate_launch_description() -> LaunchDescription:
    bringup_share = get_package_share_directory('aip_fleet_bringup')
    default_params = os.path.join(bringup_share, 'config', 'supervisor.yaml')

    supervisor_params = LaunchConfiguration('supervisor_params')

    return LaunchDescription([
        DeclareLaunchArgument(
            'supervisor_params',
            default_value=default_params,
            description='Path to YAML params file for aip_fleet_supervisor.',
        ),
        DeclareLaunchArgument(
            'leader_ns',
            default_value='aip1',
            description='Namespace of the leader vehicle. '
                        'Use aip1 for real fleet; peer_1 for Ignition Fortress sim.',
        ),
        DeclareLaunchArgument(
            'with_twist_mux',
            default_value='true',
            description='Set false when included from fleet_sim (sim spawns its own).',
        ),
        DeclareLaunchArgument(
            'with_coordinator',
            default_value='true',
            description='Launch one coordinator_node per scout. '
                        'Set false to disable fleet coordination.',
        ),
        DeclareLaunchArgument(
            'with_security',
            default_value='false',
            description='Enable SROS2 (requires keystore from scripts/sros2_init.sh).',
        ),
        DeclareLaunchArgument(
            'with_localizer',
            default_value='false',
            description='Launch scout_localizer_node (ArUco camera-based Scout localisation). '
                        'Set true when a calibrated camera is connected to the main AGV.',
        ),
        # Camera position on the main AGV body (x forward, y left, z up).
        # Adjust these to match the physical camera mount.
        DeclareLaunchArgument(
            'camera_mode',
            default_value='fixed',
            description='fixed = 차체 고정 카메라 (static TF 발행). '
                        'servo_arm = 서보 암 카메라 (암 드라이버 TF 사용, 개발 중단).',
        ),
        DeclareLaunchArgument(
            'camera_frame',
            default_value='aip1/camera_link',
            description='[servo_arm 모드 전용] 암 드라이버가 발행하는 end-effector TF 프레임명.',
        ),
        DeclareLaunchArgument('camera_offset_x', default_value='0.20',
                              description='[fixed 모드] 카메라 mount X 오프셋 from aip1/base_link (m).'),
        DeclareLaunchArgument('camera_offset_y', default_value='0.00',
                              description='[fixed 모드] 카메라 mount Y 오프셋 (m).'),
        DeclareLaunchArgument('camera_offset_z', default_value='0.15',
                              description='[fixed 모드] 카메라 mount Z 오프셋 (m).'),

        # SROS2: inject env vars before nodes start (no-op when with_security:=false).
        OpaqueFunction(function=_make_security_env),

        Node(
            package='aip_fleet_supervisor',
            executable='supervisor_node',
            name='aip_fleet_supervisor',
            output='screen',
            parameters=[supervisor_params],
        ),
        Node(
            package='aip_fleet_supervisor',
            executable='watchdog_node',
            name='aip_fleet_watchdog',
            output='screen',
        ),
        # 금지구역(위험구역) → costmap 주입: 대시보드 /fleet/keepout_zones →
        # /fleet/keepout_cloud(PointCloud2, map프레임). 각 차량 nav2 obstacle_layer 가
        # 이를 구독해 자율주행(자율 매핑/탐사 포함) 경로가 금지구역을 회피·차단한다.
        # 구역이 비어 있으면 빈 클라우드라 부하 없음.
        DeclareLaunchArgument(
            'with_keepout',
            default_value='true',
            description='금지구역 → costmap 주입 노드(keepout_zone_node) 실행 여부.',
        ),
        Node(
            package='aip_fleet_autonomous',
            executable='keepout_zone_node',
            name='keepout_zone_node',
            output='screen',
            parameters=[{'use_sim_time': False}],
            condition=IfCondition(LaunchConfiguration('with_keepout')),
        ),
        # T10/T11: foxglove_bridge는 apt 설치(ros-humble-foxglove-bridge)로 구동.
        # 미설치 환경(웹 대시보드만 쓰는 경우)에서는 with_foxglove:=false 로 건너뜀.
        DeclareLaunchArgument(
            'with_foxglove',
            default_value='false',
            description='foxglove_bridge 실행 여부. '
                        'ros-humble-foxglove-bridge apt 설치 시 true 로 설정.',
        ),
        DeclareLaunchArgument(
            'foxglove_address',
            default_value='0.0.0.0',
            description='foxglove_bridge 바인드 주소. '
                        '시뮬: 0.0.0.0 (기본). 실차: 192.168.0.9 (fleet Wi-Fi).',
        ),
        OpaqueFunction(function=_make_foxglove_node),

        # Fleet Dashboard (FastAPI + WebSocket) → http://localhost:8080
        DeclareLaunchArgument(
            'with_dashboard',
            default_value='true',
            description='Launch standalone fleet dashboard at http://localhost:8080.',
        ),
        Node(
            package='aip_fleet_dashboard',
            executable='dashboard_server',
            name='aip_fleet_dashboard',
            output='screen',
            parameters=[{'use_sim_time': False}],
            condition=IfCondition(LaunchConfiguration('with_dashboard')),
        ),

        # Per-scout twist_mux (main AGV excluded — other team's responsibility).
        OpaqueFunction(function=_make_scout_twist_mux_nodes),

        # Per-scout coordinator: publishes /<ns>/coord_cmd_vel for follower tracking.
        OpaqueFunction(function=_make_coordinator_nodes),

        # Scout ArUco localizer + camera TF (enabled only with_localizer:=true).
        OpaqueFunction(function=_make_localizer_nodes),

        # Optional: fleet telemetry bridge → InfluxDB (enabled by with_telemetry:=true).
        # Requires influxdb-client: pip3 install influxdb-client
        # Credentials via environment: INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET.
        DeclareLaunchArgument(
            'with_telemetry',
            default_value='false',
            description='Launch telemetry_node to bridge /fleet/status → InfluxDB.',
        ),
        OpaqueFunction(function=_make_telemetry_node),

        # ── aip1 퓨전센서(열상+RGB) 퍼셉션 — Vision Pi HTTP→ROS 브리지 ──────────
        # 별도 Vision Pi(servo arm 장착, RGB+열상 HTTP 스트림)를 폴링 →
        #   /aip1/heartbeat, /aip1/image_raw/compressed, /aip1/thermal_viz,
        #   /fleet/alerts(WARN, 열상 핫스팟 > warn_temp). 기본 off.
        # ★ Vision Pi 전원 ON + 실제 IP 확인 후: with_perception:=true vision_pi_url:=http://<IP>:8081
        # central_fusion(YOLOv8/map_position)은 fire 학습모델 + ultralytics 준비 후 별도 추가.
        DeclareLaunchArgument(
            'with_perception',
            default_value='false',
            description='aip1 Vision Pi HTTP→ROS 브리지(열상 WARN·RGB·thermal_viz) 실행.',
        ),
        DeclareLaunchArgument(
            'vision_pi_url',
            default_value='http://192.168.0.7:8081',
            description='aip1 Vision Pi HTTP base URL (실제 IP 확인 필요 — 문서상 .7 vs .108 불일치).',
        ),
        Node(
            package='aip_fleet_perception',
            executable='vision_pi_bridge_node',
            name='vision_pi_bridge_aip1',
            output='screen',
            parameters=[{
                'vehicle_id':  'aip1',
                'base_url':    LaunchConfiguration('vision_pi_url'),
                'warn_temp_c': 60.0,   # config/thresholds.yaml WARN(60°C) 과 정합
            }],
            condition=IfCondition(LaunchConfiguration('with_perception')),
        ),

    ])
