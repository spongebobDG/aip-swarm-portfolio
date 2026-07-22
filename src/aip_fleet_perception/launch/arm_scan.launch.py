"""arm_scan.launch.py — 서보암 스캔 노드 런치.

Usage:
  ros2 launch aip_fleet_perception arm_scan.launch.py vehicle_id:=peer_1

  # 단순 서보 드라이버 사용 시 (arm_config.yaml controller_type: position 변경 후)
  ros2 launch aip_fleet_perception arm_scan.launch.py vehicle_id:=peer_1

  # 커스텀 arm_config 사용
  ros2 launch aip_fleet_perception arm_scan.launch.py \\
      vehicle_id:=peer_1 arm_config:=/path/to/my_arm_config.yaml

스캔 트리거:
  ros2 topic pub --once /peer_1/arm/scan_request std_msgs/Bool '{data: true}'

비상 정지:
  ros2 topic pub --once /peer_1/arm/estop std_msgs/Bool '{data: true}'
"""
from __future__ import annotations

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    share      = get_package_share_directory('aip_fleet_perception')
    default_cfg = os.path.join(share, 'config', 'arm_config.yaml')

    return LaunchDescription([
        DeclareLaunchArgument('vehicle_id',  default_value='peer_1',
                              description='차량 네임스페이스'),
        DeclareLaunchArgument('arm_config',  default_value=default_cfg,
                              description='arm_config.yaml 경로 (설계 변경 시 교체)'),

        Node(
            package='aip_fleet_perception',
            executable='arm_scan_node',
            name='arm_scan',
            output='screen',
            parameters=[{
                'vehicle_id':  LaunchConfiguration('vehicle_id'),
                'config_file': LaunchConfiguration('arm_config'),
            }],
        ),
    ])
