#!/usr/bin/env python3
"""메인 AGV (aip1) 통합 launch — RPi4B 온보드 실행.

이 launch 가 제공하는 것:
  /aip1/scan        ← YDLidar TG15  (10 Hz LaserScan)
  /aip1/odom        ← serial_bridge Odometry  (20 Hz)
  /aip1/cmd_vel     ← twist_mux 출력 (ESP32 모터 입력)
  /aip1/heartbeat   ← FleetHeartbeat  (2 Hz)
  /map              ← slam_toolbox(localization:=slam) 또는 map_server(:=amcl)
  /aip1/autonomy_cmd_vel ← Nav2 경로 추종 출력  [with_nav2=true]
  TF: map → odom → base_footprint → base_link → laser_link

twist_mux 우선순위:
  central(80) > fleet_coord(50) > stuck_escape(15) > autonomy(10)
  estop_lock(90) — supervisor 발행 시 twist_mux.yaml 주석 해제

USB 장치 (udev 심링크):
  /dev/ydlidar    → ttyUSB0 / CP210x
  /dev/aip_esp32  → ttyUSB1 / CP210x / 115200 baud

위치추정 모드 (localization):
  slam  — slam_toolbox 온보드 매핑. /map 생성. 맵 제작 단계용(부하 높음).
  amcl  — map_server(저장맵) + amcl. /map 로드 + map→odom 추정. 운영(미션)용(저부하).
  none  — 위치추정 미실행(외부/오프보드 compute 사용 시).

실행 (RPi4B):
  # 운영 기본: 저장맵 + AMCL + Nav2 (저부하, 미션 좌표계 고정) — 권장:
  ros2 launch aip_fleet_real fleet_main.launch.py localization:=amcl \
      map_yaml:=/home/jh/aip_maps/latest_fleet_map.yaml

  # 맵 제작: SLAM + Nav2:
  ros2 launch aip_fleet_real fleet_main.launch.py localization:=slam

  # 드라이버만 (위치추정/Nav2 없이, 수동 teleop/외부 compute):
  ros2 launch aip_fleet_real fleet_main.launch.py localization:=none with_nav2:=false

  # ESP32 없이 YDLidar만:
  ros2 launch aip_fleet_real fleet_main.launch.py with_base:=false

  # 순찰 자동 시작:
  ros2 launch aip_fleet_real fleet_main.launch.py with_patrol:=true
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, GroupAction,
                            IncludeLaunchDescription, TimerAction)
from launch.conditions import IfCondition, LaunchConfigurationEquals
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, PushRosNamespace, SetRemap
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_real = get_package_share_directory('aip_fleet_real')
    cfg_dir = os.path.join(pkg_real, 'config', 'main_agv')

    namespace = 'aip1'
    with_base    = LaunchConfiguration('with_base')
    with_nav2    = LaunchConfiguration('with_nav2')
    with_patrol  = LaunchConfiguration('with_patrol')
    localization = LaunchConfiguration('localization')
    map_yaml     = LaunchConfiguration('map_yaml')
    use_sim_time = LaunchConfiguration('use_sim_time')

    BASE_H  = 0.120
    LIDAR_H = 0.060
    WHEEL_R = 0.060
    laser_z = BASE_H + LIDAR_H / 2.0 + 0.010

    declares = [
        DeclareLaunchArgument('with_base',    default_value='true',
            description='ESP32 serial_bridge 포함 여부'),
        DeclareLaunchArgument('localization', default_value='slam',
            description="위치추정 모드: 'slam'(매핑) | 'amcl'(저장맵 운영·저부하) | 'none'(외부)"),
        DeclareLaunchArgument('map_yaml',
            default_value='/home/jh/aip_maps/latest_fleet_map.yaml',
            description='amcl 모드에서 map_server 가 로드할 저장 맵 yaml 경로'),
        DeclareLaunchArgument('with_nav2',    default_value='true',
            description='Nav2 네비게이션 온보드 실행'),
        DeclareLaunchArgument('with_patrol',  default_value='false',
            description='순찰 미션 자동 시작'),
        DeclareLaunchArgument('use_sim_time', default_value='false',
            description='실차에서는 반드시 false'),
    ]

    # ── 1. YDLidar TG15 ──────────────────────────────────────────────────────
    ydlidar = Node(
        package='ydlidar_ros2_driver',
        executable='ydlidar_ros2_driver_node',
        name='ydlidar_ros2_driver_node',
        namespace=namespace,
        output='screen',
        parameters=[os.path.join(cfg_dir, 'ydlidar.yaml')],
        remappings=[('scan', f'/{namespace}/scan')],
    )

    # ── 2. Static TF ─────────────────────────────────────────────────────────
    tf_base = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='tf_base_footprint_to_base_link',
        namespace=namespace,
        arguments=[
            '--x', '0', '--y', '0', '--z', str(WHEEL_R),
            '--roll', '0', '--pitch', '0', '--yaw', '0',
            '--frame-id', 'base_footprint', '--child-frame-id', 'base_link',
        ],
    )
    tf_laser = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='tf_base_link_to_laser_link',
        namespace=namespace,
        arguments=[
            '--x', '0', '--y', '0', '--z', str(laser_z),
            '--roll', '0', '--pitch', '0', '--yaw', '0',
            '--frame-id', 'base_link', '--child-frame-id', 'laser_link',
        ],
    )

    # ── 3. serial_bridge (ESP32 ↔ RPi) ───────────────────────────────────────
    serial_bridge = Node(
        condition=IfCondition(with_base),
        package='aip_fleet_real',
        executable='serial_bridge',
        name='aip_serial_bridge',
        namespace=namespace,
        output='screen',
        parameters=[{
            'port': '/dev/aip_esp32',
            'baud': 115200,
            'vehicle_id': namespace,
            'wheel_base': 0.290,
            'wheel_radius': WHEEL_R,
            'ticks_per_rev': 700,
            'odom_frame': 'odom',
            'base_frame': 'base_footprint',
        }],
    )

    # ── 4. twist_mux ─────────────────────────────────────────────────────────
    twist_mux = Node(
        package='twist_mux',
        executable='twist_mux',
        name='twist_mux',
        namespace=namespace,
        output='screen',
        parameters=[os.path.join(cfg_dir, 'twist_mux.yaml')],
        remappings=[('cmd_vel_out', f'/{namespace}/cmd_vel')],
    )

    # ── 5. heartbeat_pub ─────────────────────────────────────────────────────
    heartbeat = Node(
        package='aip_fleet_real',
        executable='heartbeat_pub',
        name='heartbeat_pub',
        namespace=namespace,
        output='screen',
        parameters=[{'vehicle_id': namespace}],
    )

    # ── 6a. slam_toolbox (localization:=slam — 매핑 모드) ─────────────────────
    # slam_toolbox.yaml: scan_topic=/aip1/scan, odom_frame=odom, base_frame=base_footprint
    # /map 생성 + map→odom TF. CPU 부하 높음 → 맵 제작 단계에서만 사용.
    slam = GroupAction(
        condition=LaunchConfigurationEquals('localization', 'slam'),
        actions=[
            PushRosNamespace(namespace),
            SetRemap('/tf', '/tf'),
            SetRemap('/tf_static', '/tf_static'),
            Node(
                package='slam_toolbox',
                executable='async_slam_toolbox_node',
                name='slam_toolbox',
                output='screen',
                parameters=[
                    os.path.join(cfg_dir, 'slam_toolbox.yaml'),
                    {'use_sim_time': use_sim_time},
                ],
            ),
        ],
    )

    # ── 6b. map_server + amcl (localization:=amcl — 운영 모드) ─────────────────
    # 저장 맵을 /map(절대, latched)으로 발행 + AMCL 이 LiDAR/odom 으로 map→odom TF 추정.
    # SLAM 대비 CPU 부하가 낮고, 맵 좌표계가 고정되어 미션(웨이포인트/금지구역) 좌표가
    # 재기동 후에도 유효하다. amcl.yaml 노드키=/aip1/amcl.
    # ⚠️ 실차 검증 필요(이 PC 에 ROS2 부재) — 프레임/토픽 배선은 slam 그룹과 동일 규약.
    amcl = GroupAction(
        condition=LaunchConfigurationEquals('localization', 'amcl'),
        actions=[
            PushRosNamespace(namespace),
            SetRemap('/tf', '/tf'),
            SetRemap('/tf_static', '/tf_static'),
            Node(
                package='nav2_map_server',
                executable='map_server',
                name='map_server',
                output='screen',
                parameters=[{
                    'use_sim_time': use_sim_time,
                    'yaml_filename': map_yaml,
                    'topic_name': 'map',
                    'frame_id': 'map',
                }],
                remappings=[('map', '/map')],   # nav2 static_layer·대시보드와 동일 절대 토픽
            ),
            Node(
                package='nav2_amcl',
                executable='amcl',
                name='amcl',
                output='screen',
                parameters=[
                    os.path.join(cfg_dir, 'amcl.yaml'),
                    {'use_sim_time': use_sim_time},
                ],
                remappings=[('map', '/map')],
            ),
            Node(
                package='nav2_lifecycle_manager',
                executable='lifecycle_manager',
                name='lifecycle_manager_localization',
                output='screen',
                parameters=[{
                    'use_sim_time': use_sim_time,
                    'autostart': True,
                    'node_names': ['map_server', 'amcl'],
                }],
            ),
        ],
    )

    # ── 7. Nav2 (온보드) ──────────────────────────────────────────────────────
    # cmd_vel → autonomy_cmd_vel 리맵 → twist_mux autonomy(10) 슬롯
    nav2 = GroupAction(
        condition=IfCondition(with_nav2),
        actions=[
            PushRosNamespace(namespace),
            SetRemap('/tf', '/tf'),
            SetRemap('/tf_static', '/tf_static'),
            SetRemap('cmd_vel', 'autonomy_cmd_vel'),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(PathJoinSubstitution([
                    FindPackageShare('nav2_bringup'),
                    'launch', 'navigation_launch.py',
                ])),
                launch_arguments={
                    'namespace':    namespace,
                    'use_sim_time': use_sim_time,
                    'autostart':    'true',
                    'params_file':  os.path.join(cfg_dir, 'nav2.yaml'),
                }.items(),
            ),
        ],
    )

    # ── 8. patrol_node (선택) ─────────────────────────────────────────────────
    patrol = Node(
        condition=IfCondition(with_patrol),
        package='aip_fleet_autonomous',
        executable='patrol_node',
        name='patrol_node',
        namespace=namespace,
        output='screen',
        parameters=[
            os.path.join(cfg_dir, 'patrol.yaml'),
            {'use_sim_time': use_sim_time},
        ],
        remappings=[('/map_static', '/map')],
    )

    return LaunchDescription(declares + [
        ydlidar,
        tf_base,
        tf_laser,
        serial_bridge,
        twist_mux,
        TimerAction(period=1.0,  actions=[heartbeat]),
        # slam/amcl 는 localization 인자로 상호배타 — 둘 다 등록해도 하나만 기동.
        TimerAction(period=2.0,  actions=[slam]),    # localization:=slam
        TimerAction(period=2.0,  actions=[amcl]),    # localization:=amcl
        TimerAction(period=7.0,  actions=[nav2]),    # 위치추정 초기화 후 Nav2 기동(스파이크 분산)
        TimerAction(period=8.0,  actions=[patrol]),  # Nav2 활성화 후 patrol 기동
    ])
