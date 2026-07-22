#!/usr/bin/env python3
"""TurtleBot3 Burger 실차 bringup — AIP 플릿 네임스페이스(aip2)로 통합.

기동 구성:
  1. turtlebot3_bringup robot.launch.py  (OpenCR + LDS-03 LiDAR 드라이버)
  2. slam_toolbox (online async, mapping)  → map → aip2/odom TF 발행
  3. Nav2 navigation (nav2_bringup navigation_launch.py) — AMCL 없음(SLAM이 localize)
  4. twist_mux                             → AIP 우선순위 체인 적용
  5. (옵션) patrol_node                    → 순찰 미션 자동 시작 (with_patrol:=true)

토픽 라우팅 (cmd_vel 체인):
  Nav2 controller/behavior  --(cmd_vel→autonomy_cmd_vel remap)-->  /aip2/autonomy_cmd_vel
  twist_mux (autonomy:10)   --(cmd_vel_out→cmd_vel)------------->  /aip2/cmd_vel
  turtlebot3_node           --(subscribe cmd_vel)--------------->  /aip2/cmd_vel
  → 최종 모터 명령은 항상 twist_mux 우선순위 체인을 통과한다.
  ※ Nav2 velocity_smoother 는 위 remap 으로 입력이 끊겨 no-op 가 된다(twist_mux 가
    스무딩/우선순위를 담당). 추후 필요 시 별도 배선.

순찰 미션 (with_patrol:=true):
  patrol_node(aip_fleet_autonomous)가 config/turtlebot3/patrol.yaml 의 웨이포인트를
  /aip2/navigate_to_pose 액션으로 순환 전송한다. Nav2 bt_navigator 가 이를 실행.
  웨이포인트는 SLAM map 프레임 좌표 — 운용 환경에 맞게 patrol.yaml 을 수정할 것.

표준 차량 인터페이스 (HANDOFF_REAL_WS.md §4) 노출:
  /aip2/cmd_vel  /aip2/odom  /aip2/scan
  TF: aip2/odom→aip2/base_link, map→aip2/odom

⚠️ use_sim_time 은 반드시 false (실차).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ CAVEAT — TF frame_prefix (Phase 2 하드웨어 브링업 시 반드시 처리):
  PushRosNamespace 는 토픽/노드 이름만 네임스페이스화할 뿐, 메시지 내부 frame_id 는
  바꾸지 않는다. TurtleBot3 기본 bringup 은 TF 프레임을 prefix 없이
  (odom / base_link / base_footprint / base_scan) 발행한다.
  반면 본 패키지의 slam/nav2 config 는 aip2/odom, aip2/base_link 를 기대한다.
  → 이대로면 SLAM 이 map↔base 변환을 못 찾는다.

  해결(택1, Phase 2 에서 적용):
   (A) TB3 프레임에 prefix 부여:
       - robot_state_publisher 에 frame_prefix:='aip2/' 전달
       - turtlebot3_node 의 odom frame_id/child_frame_id 를 aip2/odom,
         aip2/base_footprint 로 설정 (turtlebot3_node 파라미터/URDF 수정 필요)
       - LDS 드라이버 frame_id 를 aip2/base_scan 으로 설정
   (B) 단일 TB3 운용이면 config 의 frame 값을 prefix 없는 기본값
       (odom/base_link/base_scan)으로 맞춰 단순화.
  본 scaffold 는 §4 규약(prefix 사용)을 기준으로 config 를 작성해 두었다.
  실제 하드웨어에서 위 (A) 배선을 완료한 뒤 단독 주행 테스트할 것.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, GroupAction,
                            IncludeLaunchDescription, SetEnvironmentVariable,
                            TimerAction)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, PushRosNamespace, SetRemap
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_real = get_package_share_directory('aip_fleet_real')
    cfg_dir = os.path.join(pkg_real, 'config', 'turtlebot3')
    slam_yaml = os.path.join(cfg_dir, 'slam_toolbox.yaml')
    nav2_yaml = os.path.join(cfg_dir, 'nav2.yaml')
    twist_mux_yaml = os.path.join(cfg_dir, 'twist_mux.yaml')
    patrol_yaml = os.path.join(cfg_dir, 'patrol.yaml')

    # ── 인자 ────────────────────────────────────────────────────────────────
    # namespace 변경 시 config/*.yaml 의 frame 값(aip2/odom 등)도 함께 수정 필요.
    namespace = LaunchConfiguration('namespace')
    use_sim_time = LaunchConfiguration('use_sim_time')
    with_patrol = LaunchConfiguration('with_patrol')

    declare_ns = DeclareLaunchArgument('namespace', default_value='aip2')
    declare_sim = DeclareLaunchArgument(
        'use_sim_time', default_value='false',
        description='실차에서는 반드시 false 유지')
    declare_patrol = DeclareLaunchArgument(
        'with_patrol', default_value='false',
        description='순찰 미션 자동 시작(patrol_node). 웨이포인트는 config/turtlebot3/patrol.yaml')

    # TB3 모델 환경변수 — turtlebot3_bringup 가 참조.
    set_tb3_model = SetEnvironmentVariable('TURTLEBOT3_MODEL', 'burger')

    # ── 1. TurtleBot3 하드웨어 bringup ──────────────────────────────────────
    # robot.launch.py 는 use_sim_time 인자를 선언하지 않을 수 있어 전달하지 않는다
    # (실차 드라이버는 시스템 시간 사용이 기본·올바름).
    # ⚠️ TF frame_prefix 는 위 CAVEAT 참고 — Phase 2 에서 처리.
    tb3_bringup = GroupAction([
        PushRosNamespace(namespace),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([
                FindPackageShare('turtlebot3_bringup'),
                'launch', 'robot.launch.py'])),
        ),
    ])

    # ── 2. slam_toolbox (online async, mapping) ─────────────────────────────
    # 노드 FQN = /aip2/slam_toolbox → slam yaml 키와 일치해야 함.
    slam = GroupAction([
        PushRosNamespace(namespace),
        Node(
            package='slam_toolbox',
            executable='async_slam_toolbox_node',
            name='slam_toolbox',
            output='screen',
            parameters=[slam_yaml, {'use_sim_time': use_sim_time}],
        ),
    ])

    # ── 3. Nav2 navigation (localization 없이, SLAM이 map 제공) ──────────────
    # navigation_launch.py 는 namespace 를 RewriteYaml root_key 로만 쓰고 노드에
    # 직접 적용하지 않는다 → PushRosNamespace 로 노드를 /aip2/* 에 배치해야
    # yaml 파라미터 매칭(MPPI 등)이 성공한다.
    # SetRemap('/tf','/tf'): navigation_launch 의 ('/tf','tf') remap 이 PushRosNamespace
    # 와 결합해 /aip2/tf 구독으로 바뀌는 것을 막는다(TF 는 글로벌 /tf).
    # SetRemap(cmd_vel→autonomy_cmd_vel): controller/behavior 출력 → twist_mux 입력.
    nav2 = GroupAction([
        PushRosNamespace(namespace),
        SetRemap('/tf', '/tf'),
        SetRemap('/tf_static', '/tf_static'),
        SetRemap('cmd_vel', 'autonomy_cmd_vel'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([
                FindPackageShare('nav2_bringup'),
                'launch', 'navigation_launch.py'])),
            launch_arguments={
                'namespace': namespace,
                'use_sim_time': use_sim_time,
                'autostart': 'true',
                'params_file': nav2_yaml,
            }.items(),
        ),
    ])

    # ── 4. twist_mux (AIP 우선순위 체인) ────────────────────────────────────
    twist_mux = GroupAction([
        PushRosNamespace(namespace),
        Node(
            package='twist_mux',
            executable='twist_mux',
            name='twist_mux',
            output='screen',
            parameters=[twist_mux_yaml, {'use_sim_time': use_sim_time}],
            remappings=[('cmd_vel_out', 'cmd_vel')],
        ),
    ])

    # ── 5. (옵션) 순찰 미션 ──────────────────────────────────────────────────
    # patrol_node 는 vehicle_id 파라미터로 /aip2/navigate_to_pose 액션을 직접 지정한다
    # (절대 토픽 사용 → namespace push 와 무관하게 동작하지만, 파라미터 FQN 매칭과
    # 시각화 토픽 위치를 위해 namespace 를 함께 적용).
    # /map_static(미매핑 웨이포인트 skip 판정용)을 실차 SLAM 맵 /aip2/map 으로 remap.
    patrol = GroupAction(
        condition=IfCondition(with_patrol),
        actions=[
            Node(
                package='aip_fleet_autonomous',
                executable='patrol_node',
                name='patrol_node',
                namespace=namespace,
                output='screen',
                parameters=[patrol_yaml],
                remappings=[('/map_static', '/aip2/map')],
            ),
        ])

    # ── 기동 순서 staggering (RPi/TB3 부하 스파이크 완화) ───────────────────
    # Nav2 라이프사이클(8+ 노드)과 SLAM 을 동시에 활성화하면 RPi 급 보드에서
    # 수 초간 CPU/IO 포화 → SSH·heartbeat 끊김(2026-06-27 aip2/aip3 동일 증상).
    # 드라이버·twist_mux 를 먼저 띄우고 SLAM, Nav2, patrol 을 시차 기동해
    # 스파이크를 분산한다. aip1 fleet_main.launch.py 와 동일한 패턴.
    # period 값은 보드 성능에 맞춰 조정 가능(느린 보드일수록 간격 ↑).
    return LaunchDescription([
        declare_ns,
        declare_sim,
        declare_patrol,
        set_tb3_model,
        tb3_bringup,                                  # t=0   하드웨어 드라이버(OpenCR+LDS)
        twist_mux,                                    # t=0   우선순위 믹서(경량)
        TimerAction(period=4.0,  actions=[slam]),     # t=4   스캔 안정화 후 SLAM
        TimerAction(period=10.0, actions=[nav2]),     # t=10  SLAM 맵 초기화 후 Nav2
        TimerAction(period=12.0, actions=[patrol]),   # t=12  Nav2 활성화 후 순찰
    ])
