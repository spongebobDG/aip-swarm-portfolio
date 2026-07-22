"""rviz_phase2.launch.py — Phase-2 전용 RViz2 시각화.

사용법:
  ros2 launch aip_fleet_nav rviz_phase2.launch.py

표시 항목:
  - /map          : SLAM 점유 격자 지도
  - /peer_1/scan  : LiDAR 스캔 (빨강)
  - /peer_2/scan  : LiDAR 스캔 (파랑)
  - /peer_3/scan  : LiDAR 스캔 (초록)
  - /peer_*/particlecloud : AMCL 파티클 분포
  - /peer_*/amcl_pose    : AMCL 위치 추정
  - TF            : map/odom/base_link 체인 전체

GPU: PRIME on-demand 환경에서 NVIDIA RTX를 강제 사용.
     AMD 내장 GPU로 실행 시 ~3fps → NVIDIA 전환 후 30+fps.
"""
from __future__ import annotations

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

# PRIME on-demand: NVIDIA GPU를 RViz2 프로세스에 강제 적용
_NVIDIA_ENV = {
    '__NV_PRIME_RENDER_OFFLOAD':      '1',
    '__NV_PRIME_RENDER_OFFLOAD_PROVIDER': 'NVIDIA-G0',
    '__GLX_VENDOR_LIBRARY_NAME':      'nvidia',
    '__EGL_VENDOR_LIBRARY_FILENAMES': '/usr/share/glvnd/egl_vendor.d/10_nvidia.json',
}


def generate_launch_description() -> LaunchDescription:
    rviz_cfg = os.path.join(
        get_package_share_directory('aip_fleet_nav'),
        'rviz', 'phase2.rviz',
    )

    return LaunchDescription([
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', rviz_cfg],
            additional_env=_NVIDIA_ENV,
            output='screen',
        ),
    ])
