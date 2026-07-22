"""camera_driver.launch.py — 카메라 타입 추상화 런치.

camera_type 파라미터 하나로 CSI ↔ USB 전환.
출력 토픽은 타입과 무관하게 동일:
  /{vehicle_id}/arm/image_raw
  /{vehicle_id}/arm/image_raw/compressed
  /{vehicle_id}/arm/camera_info

지원 camera_type:
  csi_v4l2     — OV5647 CSI (레거시 V4L2 스택, 기본값)
  csi_libcamera — OV5647 CSI (libcamera 스택, 신형 RPi OS)
  usb           — USB UVC 카메라 (ELP / Arducam / 범용)

CSI ↔ USB 전환 시 변경 항목:
  1. camera_type 인수 변경
  2. video_device 경로 확인 (ls /dev/video*)
  3. camera_calibration 재실행 → camera_info_usb.yaml 갱신

Usage:
  # CSI (현재, 기본값)
  ros2 launch aip_fleet_perception camera_driver.launch.py vehicle_id:=peer_1

  # USB 교체 후
  ros2 launch aip_fleet_perception camera_driver.launch.py \\
      vehicle_id:=peer_1 camera_type:=usb video_device:=/dev/video1
"""
from __future__ import annotations

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _launch_camera(context, *args, **kwargs):
    vid          = LaunchConfiguration('vehicle_id').perform(context)
    cam_type     = LaunchConfiguration('camera_type').perform(context)
    video_device = LaunchConfiguration('video_device').perform(context)
    share        = get_package_share_directory('aip_fleet_perception')

    # camera_type 별 camera_info yaml 선택
    if cam_type.startswith('csi'):
        info_yaml = os.path.join(share, 'config', 'camera_info_csi.yaml')
    else:
        info_yaml = os.path.join(share, 'config', 'camera_info_usb.yaml')

    info_url = f'file://{info_yaml}'

    # ── csi_libcamera: camera_ros 패키지 사용 (신형 RPi OS) ──────────────
    if cam_type == 'csi_libcamera':
        return [Node(
            package='camera_ros',
            executable='camera_node',
            name='arm_camera',
            output='screen',
            parameters=[{
                'camera':           0,
                'width':            1280,
                'height':           960,
                'camera_info_url':  info_url,
            }],
            remappings=[
                ('~/image_raw',   f'/{vid}/arm/image_raw'),
                ('~/camera_info', f'/{vid}/arm/camera_info'),
            ],
        )]

    # ── csi_v4l2 / usb: v4l2_camera 패키지 사용 ─────────────────────────
    # CSI 카메라도 V4L2 디바이스로 노출됨 (/dev/video0)
    # USB 카메라는 /dev/video1 등 — lsusb / ls /dev/video* 로 확인
    pixel_format = 'MJPG' if cam_type == 'usb' else 'YUYV'

    return [Node(
        package='v4l2_camera',
        executable='v4l2_camera_node',
        name='arm_camera',
        output='screen',
        parameters=[{
            'video_device':    video_device,
            'camera_info_url': info_url,
            'image_size':      [1280, 960] if cam_type.startswith('csi') else [1280, 720],
            'pixel_format':    pixel_format,
            'camera_frame_id': f'{vid}/arm/camera_optical_frame',
        }],
        remappings=[
            ('image_raw',   f'/{vid}/arm/image_raw'),
            ('camera_info', f'/{vid}/arm/camera_info'),
        ],
    )]


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        DeclareLaunchArgument(
            'vehicle_id',    default_value='peer_1',
            description='차량 네임스페이스'),
        DeclareLaunchArgument(
            'camera_type',   default_value='csi_v4l2',
            description='csi_v4l2 | csi_libcamera | usb'),
        DeclareLaunchArgument(
            'video_device',  default_value='/dev/video0',
            description='V4L2 디바이스 경로 (CSI: /dev/video0, USB: /dev/video1 등)'),
        OpaqueFunction(function=_launch_camera),
    ])
