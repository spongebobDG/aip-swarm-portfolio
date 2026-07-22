#!/usr/bin/env python3
"""aip1 URDF 미리보기 — RViz + joint_state_publisher_gui.

실행:
  ros2 launch aip_fleet_real urdf_preview.launch.py

기능:
  - robot_state_publisher: URDF → TF 발행
  - joint_state_publisher_gui: 조인트 슬라이더 (arm 4축 + 볼캐스터 2축)
  - RViz2: RobotModel 시각화
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory('aip_fleet_real')
    urdf_path = os.path.join(pkg, 'urdf', 'aip1.urdf')

    with open(urdf_path, 'r') as f:
        robot_description = f.read()

    return LaunchDescription([
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{
                'robot_description': robot_description,
                'use_sim_time': False,
            }],
        ),
        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            name='joint_state_publisher_gui',
            output='screen',
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen',
            arguments=['-d', os.path.join(pkg, 'rviz', 'urdf_preview.rviz')],
        ),
    ])
