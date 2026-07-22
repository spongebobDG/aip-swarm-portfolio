"""열상 전용 런치 — thermal_uart_driver + patrol_monitor (카메라 제외).

aip1 카메라(v4l2_camera) 미설치/분리 상태라 perception_vehicle.launch.py 가 실패하므로,
열화상 모니터링만 띄우는 경량 런치. systemd user 서비스(aip-thermal)에서 사용.

GY-MCU90640: /dev/serial0 @ 460800 (보드 8Hz 설정, ZZ-02-06 프로토콜).
발행: /aip1/thermal_raw(32FC1), /aip1/thermal_temp(Float32), /aip1/thermal_viz(rgb8, INFERNO).
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    vid = LaunchConfiguration('vehicle_id')
    return LaunchDescription([
        DeclareLaunchArgument('vehicle_id', default_value='aip1'),

        Node(
            package='aip_fleet_perception',
            executable='thermal_uart_driver_node',
            name='thermal_driver',
            output='screen',
            parameters=[{
                'vehicle_id': vid,
                'port': '/dev/serial0',
                'baud': 460800,          # GY-MCU90640 보드 460800 (8Hz)
            }],
        ),
        Node(
            package='aip_fleet_perception',
            executable='patrol_monitor_node',
            name='patrol_monitor',
            output='screen',
            parameters=[{
                'vehicle_id': vid,
                'warn_temp_c': 50.0,
            }],
        ),
    ])
