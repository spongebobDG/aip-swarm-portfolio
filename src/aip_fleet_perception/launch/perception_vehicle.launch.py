"""perception_vehicle.launch.py — Pi 4 탑재 퍼셉션 노드 런치.

각 차량 Pi 4에서 실행:
  camera_driver (camera_driver.launch.py 포함)
  thermal_driver_node  — MLX90640 드라이버
  patrol_monitor_node  — 1차 온도 임계값 필터 + 경보 발행

카메라 전환:
  CSI(현재): camera_type:=csi_v4l2  (기본값)
  USB(교체): camera_type:=usb  video_device:=/dev/video1

Usage:
  # CSI (기본)
  ros2 launch aip_fleet_perception perception_vehicle.launch.py vehicle_id:=peer_1

  # USB 교체 후
  ros2 launch aip_fleet_perception perception_vehicle.launch.py \\
      vehicle_id:=peer_1 camera_type:=usb video_device:=/dev/video1

  # 시뮬 (센서 없이)
  ros2 launch aip_fleet_perception perception_vehicle.launch.py \\
      vehicle_id:=peer_1 sim:=true
"""
from __future__ import annotations

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _thermal_node(context, *args, **kwargs):
    """thermal_iface 에 따라 UART(GY-MCU90640 핀8/10) / I2C(MLX90640 직결) 선택."""
    vid   = LaunchConfiguration('vehicle_id').perform(context)
    iface = LaunchConfiguration('thermal_iface').perform(context).lower()
    sim   = LaunchConfiguration('sim').perform(context).lower() == 'true'
    port  = LaunchConfiguration('thermal_port').perform(context)
    if iface == 'uart':
        return [Node(
            package='aip_fleet_perception',
            executable='thermal_uart_driver_node',
            name='thermal_driver',
            output='screen',
            parameters=[{'vehicle_id': vid, 'port': port, 'baud': 460800, 'sim': sim}],
        )]
    return [Node(
        package='aip_fleet_perception',
        executable='thermal_driver_node',
        name='thermal_driver',
        output='screen',
        parameters=[{'vehicle_id': vid, 'publish_hz': 8.0, 'sim': sim}],
    )]


def generate_launch_description() -> LaunchDescription:
    share    = get_package_share_directory('aip_fleet_perception')
    cal_yaml = os.path.join(share, 'config', 'calibration.yaml')
    thr_yaml = os.path.join(share, 'config', 'thresholds.yaml')
    cam_launch = os.path.join(share, 'launch', 'camera_driver.launch.py')

    vid          = LaunchConfiguration('vehicle_id')
    sim          = LaunchConfiguration('sim')
    camera_type  = LaunchConfiguration('camera_type')
    video_device = LaunchConfiguration('video_device')

    return LaunchDescription([
        DeclareLaunchArgument('vehicle_id',    default_value='peer_1',
                              description='차량 네임스페이스'),
        DeclareLaunchArgument('sim',           default_value='false',
                              description='true: 실제 센서 없이 시뮬 데이터 사용'),
        DeclareLaunchArgument('camera_type',   default_value='csi_v4l2',
                              description='csi_v4l2 | csi_libcamera | usb'),
        DeclareLaunchArgument('video_device',  default_value='/dev/video0',
                              description='V4L2 디바이스 경로'),
        DeclareLaunchArgument('thermal_iface', default_value='uart',
                              description='uart(GY-MCU90640, 핀8/10 /dev/serial0) | i2c(MLX90640 직결 0x33)'),
        DeclareLaunchArgument('thermal_port',  default_value='/dev/serial0',
                              description='UART 열상 포트 (핀8/10 = /dev/serial0)'),

        # ── 카메라 드라이버 (CSI ↔ USB 투명 전환) ────────────────────────
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(cam_launch),
            launch_arguments={
                'vehicle_id':   vid,
                'camera_type':  camera_type,
                'video_device': video_device,
            }.items(),
        ),

        # ── 열상 드라이버 (thermal_iface: uart=GY-MCU90640 / i2c=MLX90640) ──
        OpaqueFunction(function=_thermal_node),

        # ── 1차 온도 임계값 필터 ──────────────────────────────────────────
        Node(
            package='aip_fleet_perception',
            executable='patrol_monitor_node',
            name='patrol_monitor',
            output='screen',
            parameters=[
                thr_yaml,
                {
                    'vehicle_id':       vid,
                    'calibration_file': cal_yaml,
                },
            ],
        ),
    ])
