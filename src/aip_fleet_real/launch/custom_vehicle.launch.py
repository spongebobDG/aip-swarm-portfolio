#!/usr/bin/env python3
"""자작 SLAM 차량 (aip3) — PLACEHOLDER.

⚠️ 구동계 드라이버 미구현:
    - 모터: Feetech STS3215 서보 (UART half-duplex 직렬 버스)
    - LiDAR: 미확정
    STS3215 ros2_control hardware_interface 는 별도 세션에서 구현 예정.

현재 동작:
    - 시작 시 경고 로그 출력.
    - LiDAR/모터 드라이버가 없으므로 /aip3/scan, /aip3/odom 발행자 없음
      → 이 상태로는 slam_toolbox/Nav2 가 정상 동작하지 않는다.
    - 따라서 drivers_ready:=true 인 경우에만 slam_toolbox/Nav2 를 기동한다.
      (드라이버 구현 완료 후 launch_arguments 로 활성화)

TODO(별도 세션):
    1. STS3215 ros2_control SystemInterface 구현 → /aip3/cmd_vel 수신, /aip3/odom 발행
    2. LiDAR 드라이버 추가 → /aip3/scan 발행
    3. config/custom_vehicle/{slam_toolbox,nav2}.yaml 실측값으로 갱신
    4. drivers_ready 기본값을 true 로 변경
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, GroupAction,
                            IncludeLaunchDescription, LogInfo, TimerAction)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, PushRosNamespace, SetRemap
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_real = get_package_share_directory('aip_fleet_real')
    cfg_dir = os.path.join(pkg_real, 'config', 'custom_vehicle')
    slam_yaml = os.path.join(cfg_dir, 'slam_toolbox.yaml')
    nav2_yaml = os.path.join(cfg_dir, 'nav2.yaml')

    namespace = LaunchConfiguration('namespace')
    use_sim_time = LaunchConfiguration('use_sim_time')
    drivers_ready = LaunchConfiguration('drivers_ready')

    declare_ns = DeclareLaunchArgument('namespace', default_value='aip3')
    declare_sim = DeclareLaunchArgument('use_sim_time', default_value='false')
    declare_drivers = DeclareLaunchArgument(
        'drivers_ready', default_value='false',
        description='STS3215 모터 + LiDAR 드라이버 구현 완료 시 true')

    warn = LogInfo(msg=(
        '\n========================================================\n'
        '[custom_vehicle / aip3] PLACEHOLDER LAUNCH\n'
        '  STS3215 모터/LiDAR 드라이버 미구현 — 실제 모터 제어 없음.\n'
        '  drivers_ready:=true 로 실행해야 slam_toolbox/Nav2 가 기동됩니다.\n'
        '========================================================'))

    slam = GroupAction(
        condition=IfCondition(drivers_ready),
        actions=[
            PushRosNamespace(namespace),
            Node(
                package='slam_toolbox',
                executable='async_slam_toolbox_node',
                name='slam_toolbox',
                output='screen',
                parameters=[slam_yaml, {'use_sim_time': use_sim_time}],
            ),
        ])

    nav2 = GroupAction(
        condition=IfCondition(drivers_ready),
        actions=[
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

    # 기동 staggering: SLAM 과 Nav2 라이프사이클 동시 활성화로 인한 부하
    # 스파이크를 분산(드라이버 구현 완료 후 drivers_ready:=true 시 적용).
    # aip1/aip2 와 동일한 패턴 — period 는 보드 성능에 맞춰 조정.
    return LaunchDescription([
        declare_ns,
        declare_sim,
        declare_drivers,
        warn,
        TimerAction(period=4.0,  actions=[slam]),   # t=4   스캔 안정화 후 SLAM
        TimerAction(period=10.0, actions=[nav2]),   # t=10  SLAM 맵 초기화 후 Nav2
    ])
