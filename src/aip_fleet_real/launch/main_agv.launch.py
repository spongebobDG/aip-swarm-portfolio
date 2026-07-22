#!/usr/bin/env python3
"""메인 AGV (aip1) — SLAM + Nav2 + patrol 통합 launch.

⚠️ 전제: fleet_main.launch.py (aip_fleet_real, RPi4B) 가 먼저 실행 중이어야 함.
   fleet_main 이 제공하는 것 (RPi4B 에서 ros2 launch aip_fleet_real fleet_main.launch.py):
     /aip1/scan        ← YDLidar TG15 (10Hz LaserScan, frame_id='laser_link')
     /aip1/odom        ← serial_bridge 계산 Odometry (20Hz)
     /aip1/cmd_vel     ← twist_mux 출력 (ESP32 모터 입력)
     twist_mux         ← autonomy(10) / fleet_coord(50) / central(80) / estop_lock(90)
     TF static         ← base_footprint→base_link→laser_link (frame_prefix 없음)

이 launch 가 추가하는 것:
  1. slam_toolbox (DWB)  — /aip1/scan → /map 생성 + map→odom TF 발행
  2. Nav2               — /map + /aip1/scan → /aip1/autonomy_cmd_vel → twist_mux
  3. (옵션) patrol_node  — /aip1/navigate_to_pose → 순찰 웨이포인트 순환 전송

⚠️ TF 구조 (fleet_main RSP/serial_bridge 는 frame_prefix 없음):
   map → odom → base_footprint → base_link → laser_link
         ↑ slam  ↑ serial_bridge  ↑ RSP (static, fleet_main)

⚠️ Nav2 네임스페이스:
   navigation_launch.py 는 namespace 인자를 RewriteYaml root_key 로 사용.
   PushRosNamespace('aip1') 으로 노드를 /aip1/* 에 배치 + RewriteYaml(root_key=aip1)이
   nav2.yaml 의 bare 키(controller_server: 등)를 /aip1/* 노드에 매칭한다.
   SetRemap('/tf','/tf'): navigation_launch 내부 ('/tf','tf') remap +
   PushRosNamespace 조합으로 /aip1/tf 구독이 되는 것을 막는다.

실행:
  # 1) RPi4B 에서 fleet_main 기동 (터미널 1):
  #    ros2 launch aip_fleet_real fleet_main.launch.py
  # 2) dev PC 에서 SLAM+Nav2 기동 (터미널 2):
  source ~/aip_swarm_ws/install/setup.bash
  ros2 launch aip_fleet_real main_agv.launch.py with_patrol:=true

  # 맵 저장 (SLAM 실행 중, 순찰 전):
  ros2 service call /slam_toolbox/save_map slam_toolbox/srv/SaveMap "{name: {data: '/home/jh/maps/main_map'}}"

⚠️ use_sim_time 은 반드시 false (실차).
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, GroupAction,
                            IncludeLaunchDescription, TimerAction)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, PushRosNamespace, SetRemap
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_real = get_package_share_directory('aip_fleet_real')
    cfg_dir = os.path.join(pkg_real, 'config', 'main_agv')
    slam_yaml = os.path.join(cfg_dir, 'slam_toolbox.yaml')
    nav2_yaml = os.path.join(cfg_dir, 'nav2.yaml')
    patrol_yaml = os.path.join(cfg_dir, 'patrol.yaml')

    namespace = 'aip1'
    with_patrol = LaunchConfiguration('with_patrol')
    use_sim_time = LaunchConfiguration('use_sim_time')

    declares = [
        DeclareLaunchArgument(
            'with_patrol', default_value='false',
            description='순찰 미션 자동 시작(patrol_node). 좌표: config/main_agv/patrol.yaml'),
        DeclareLaunchArgument(
            'use_sim_time', default_value='false',
            description='실차에서는 반드시 false'),
        DeclareLaunchArgument('namespace', default_value='aip1'),
    ]

    # ── 0. Static TF 재발행 (dev PC 측) ─────────────────────────────────
    # FastDDS TRANSIENT_LOCAL 메시지가 다중 호스트 환경에서 미전달되는 알려진 이슈.
    # RPi fleet_main 이 이미 발행하는 static TF 를 dev PC 에서도 동일하게 발행.
    static_tf_footprint_to_base = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='tf_base_footprint_to_base_link_devpc',
        arguments=['0', '0', '0.06', '0', '0', '0', 'aip1/base_footprint', 'aip1/base_link'],
    )
    static_tf_base_to_laser = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='tf_base_link_to_laser_link_devpc',
        arguments=['0', '0', '0.16', '0', '0', '0', 'aip1/base_link', 'aip1/laser_link'],
    )

    # ── 0.5 scan_deskew — 회전/주행 중 스캔 모션 왜곡 보정 (+무효점 정리).
    scan_deskew = Node(
        package='aip_fleet_real',
        executable='scan_deskew_node',
        name='scan_deskew',
        output='screen',
        parameters=[{'scan_in': '/aip1/scan', 'scan_out': '/aip1/scan_deskewed',
                     'odom_topic': '/aip1/odom'}],
    )

    # ── 1. slam_toolbox (online async mapping) ────────────────────────────
    # /aip1/scan 구독 → /map 발행 + map→aip1/odom TF 발행.
    # slam_toolbox.yaml 에 scan_topic: /aip1/scan (절대 경로) 지정.
    slam = GroupAction([
        PushRosNamespace(namespace),
        SetRemap('/tf', '/tf'),
        SetRemap('/tf_static', '/tf_static'),
        Node(
            package='slam_toolbox',
            executable='async_slam_toolbox_node',
            name='slam_toolbox',
            output='screen',
            parameters=[slam_yaml, {'use_sim_time': use_sim_time}],
        ),
    ])

    # ── 2. Nav2 navigation (MPPI + SmacHybrid planner) ────────────────────
    # PushRosNamespace → 노드가 /aip1/* 에 배치되어 YAML root_key='aip1' 와 일치.
    # SetRemap('/tf','/tf') → navigation_launch 의 ('/tf','tf') remap 무효화.
    # SetRemap('cmd_vel','autonomy_cmd_vel') → twist_mux autonomy 슬롯(priority 10) 입력.
    nav2 = GroupAction([
        PushRosNamespace(namespace),
        # ⚠️ 미해결: navigation_launch 내부 remap('/tf','tf')+namespace 조합으로 Nav2 costmap이
        # 글로벌 /tf 의 aip1/odom→base_footprint 를 못 받아 "unconnected trees" → 활성화 실패.
        # SetRemap('/tf','/tf')·('tf','/tf') 둘 다 효과 없음. 자율 Nav2 블로커(별도 정리 필요).
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

    # ── 3. (옵션) 순찰 미션 ──────────────────────────────────────────────
    # patrol_node 는 /aip1/navigate_to_pose 액션으로 Nav2 에 목표를 전송한다.
    # /map_static: 금지구역(keepout) 판단용 → 실차에서는 /map 으로 remap.
    patrol = Node(
        condition=IfCondition(with_patrol),
        package='aip_fleet_autonomous',
        executable='patrol_node',
        name='patrol_node',
        namespace=namespace,
        output='screen',
        parameters=[patrol_yaml, {'use_sim_time': use_sim_time}],
        remappings=[('/map_static', '/map')],
    )

    return LaunchDescription(declares + [
        static_tf_footprint_to_base,
        static_tf_base_to_laser,
        scan_deskew,
        slam,
        TimerAction(period=5.0, actions=[nav2]),    # SLAM 맵 초기화 후 Nav2 기동
        TimerAction(period=6.0, actions=[patrol]),  # Nav2 활성화 후 patrol 기동
    ])
