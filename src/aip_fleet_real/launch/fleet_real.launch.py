#!/usr/bin/env python3
"""실차 플릿 통합 launch — main / aip2(TB3) / aip3(자작) 선택 기동.

사용 예:
    # TB3 한 대만
    ros2 launch aip_fleet_real fleet_real.launch.py with_tb3:=true with_main:=false with_custom:=false

    # TB3 + 순찰 미션 자동 시작
    ros2 launch aip_fleet_real fleet_real.launch.py with_tb3:=true with_patrol:=true

    # 메인 AGV 인터페이스 확인 + TB3
    ros2 launch aip_fleet_real fleet_real.launch.py with_main:=true with_tb3:=true

각 차량 launch 는 자체 노드를 자신의 머신(RPi4B)에서 실행하는 것이 원칙이다.
이 통합 launch 는 개발 PC 에서 한 번에 여러 차량을 띄우거나, 한 대씩 선택 기동할 때 사용.
모든 차량은 ROS_DOMAIN_ID=42 + FastDDS Discovery Server 로 동일 도메인에서 통신.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    launch_dir = os.path.join(
        get_package_share_directory('aip_fleet_real'), 'launch')

    with_main = LaunchConfiguration('with_main')
    with_tb3 = LaunchConfiguration('with_tb3')
    with_custom = LaunchConfiguration('with_custom')
    with_patrol = LaunchConfiguration('with_patrol')
    use_sim_time = LaunchConfiguration('use_sim_time')

    declares = [
        DeclareLaunchArgument('with_main', default_value='false',
                              description='메인 AGV 인터페이스 확인 launch 포함'),
        DeclareLaunchArgument('with_tb3', default_value='true',
                              description='TurtleBot3 Burger(aip2) 포함'),
        DeclareLaunchArgument('with_custom', default_value='false',
                              description='자작 차량(aip3) placeholder 포함'),
        DeclareLaunchArgument('with_patrol', default_value='false',
                              description='aip2(TB3) 순찰 미션 자동 시작'),
        DeclareLaunchArgument('use_sim_time', default_value='false',
                              description='실차 — 반드시 false'),
    ]

    def include(name, cond, extra=None):
        args = {'use_sim_time': use_sim_time}
        if extra:
            args.update(extra)
        return IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(launch_dir, name)),
            condition=IfCondition(cond),
            launch_arguments=args.items(),
        )

    return LaunchDescription(declares + [
        include('main_agv.launch.py', with_main),
        include('turtlebot3.launch.py', with_tb3, {'with_patrol': with_patrol}),
        include('custom_vehicle.launch.py', with_custom),
    ])
