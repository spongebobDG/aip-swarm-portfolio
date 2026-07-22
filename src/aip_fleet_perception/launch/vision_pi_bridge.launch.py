"""Launch the standalone Vision Pi HTTP-to-ROS bridge.

Usage:
  ros2 launch aip_fleet_perception vision_pi_bridge.launch.py \
      vehicle_id:=aip2 base_url:=http://192.168.0.108:8081
"""
from __future__ import annotations

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    vehicle_id = LaunchConfiguration('vehicle_id')
    base_url = LaunchConfiguration('base_url')

    return LaunchDescription([
        DeclareLaunchArgument(
            'vehicle_id',
            default_value='aip2',
            description='AIP vehicle id to publish under. Use a lab id/domain to avoid collisions.'),
        DeclareLaunchArgument(
            'base_url',
            default_value='http://192.168.0.108:8081',
            description='Vision Pi HTTP preview base URL.'),

        Node(
            package='aip_fleet_perception',
            executable='vision_pi_bridge_node',
            name='vision_pi_bridge',
            output='screen',
            parameters=[{
                'vehicle_id': vehicle_id,
                'base_url': base_url,
            }],
        ),
    ])
