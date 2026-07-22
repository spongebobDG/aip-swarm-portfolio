"""Central-PC services for the real fleet, combined into one process."""
from __future__ import annotations

from launch import LaunchDescription
from launch.actions import ExecuteProcess


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        ExecuteProcess(
            cmd=['ros2', 'run', 'aip_fleet_bringup', 'central_real_combined.py'],
            name='aip_fleet_central_combined',
            output='screen',
        ),
    ])
