"""perception_central.launch.py — 메인 PC 퍼셉션 융합 노드 런치.

메인 PC에서 실행:
  central_fusion_node — RGB+열화상 YOLOv8 융합 → /fleet/alerts

Usage:
  ros2 launch aip_fleet_perception perception_central.launch.py
  ros2 launch aip_fleet_perception perception_central.launch.py model_path:=/path/to/fire.pt
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
    thr_yaml   = os.path.join(share, 'config', 'thresholds.yaml')
    model_path = LaunchConfiguration('model_path')

    return LaunchDescription([
        DeclareLaunchArgument(
            'model_path',
            default_value='yolov8n.pt',
            description='YOLOv8 모델 경로 (fire/smoke 사전학습 모델 권장)'),

        Node(
            package='aip_fleet_perception',
            executable='central_fusion_node',
            name='central_fusion',
            output='screen',
            parameters=[
                thr_yaml,
                {
                    'vehicle_ids': ['aip1', 'aip2', 'aip3'],
                    'model_path':  model_path,
                },
            ],
        ),
    ])
