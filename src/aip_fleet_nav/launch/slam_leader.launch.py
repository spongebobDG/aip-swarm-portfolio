"""slam_leader.launch.py — start slam_toolbox for the leader vehicle.

The leader (default: peer_1) builds the shared /map.  Follower vehicles
use amcl on this map via nav_follower.launch.py.

Usage:
  ros2 launch aip_fleet_nav slam_leader.launch.py vehicle_id:=peer_1
"""
from __future__ import annotations

import os
import string
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _launch_slam(context, *args, **kwargs):
    vid = LaunchConfiguration('vehicle_id').perform(context)
    rtf = float(LaunchConfiguration('rtf').perform(context))

    nav_share  = get_package_share_directory('aip_fleet_nav')
    tmpl_path  = os.path.join(nav_share, 'params', 'slam_toolbox_online.yaml')

    with open(tmpl_path) as f:
        tmpl = string.Template(f.read())
    rendered = tmpl.substitute(vehicle_id=vid)

    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', delete=False,
        prefix=f'slam_{vid}_',
    )
    tmp.write(rendered)
    tmp.close()

    # transform_timeout = odom_time에 더해 TF stamp을 찍는 sim_time 오프셋.
    # rtf로 스케일하면 안 됨: 12.0이면 TF가 현재 시각보다 10+s 미래로 찍혀
    # costmap이 "현재" TF를 못 찾아 extrapolation into the past 반복 발생.
    # 3.0s(sim) 고정: odom_time + 3.0 = current_sim - 1.7 + 3.0 = current_sim + 1.3
    # → 이전 TF(current_sim - 0.4)와 현재 TF(current_sim + 1.3) 사이로 보간 성공.
    _ = rtf  # rtf is received but not used for transform_timeout
    transform_timeout = 3.0

    return [
        Node(
            package='slam_toolbox',
            executable='async_slam_toolbox_node',
            name='slam_toolbox',
            namespace=vid,
            output='screen',
            parameters=[tmp.name, {'use_sim_time': True,
                                   'transform_timeout': transform_timeout}],
            remappings=[
                # slam_toolbox subscribes to /scan by default; remap to namespaced
                ('scan', f'/{vid}/scan'),
                # Publish map to global /map so AMCL followers can subscribe.
                # Without this remap the topic lands at /peer_1/map (namespaced)
                # and follower AMCL nodes (which remap 'map' → '/map') never receive it.
                ('map',          '/map'),
                ('map_metadata', '/map_metadata'),
                # map_updates 도 절대경로로 remapping — RViz(/map_updates) 및
                # explore_lite 가 증분 업데이트를 받으려면 네임스페이스 밖으로 노출 필요.
                ('map_updates',  '/map_updates'),
            ],
        )
    ]


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        DeclareLaunchArgument('vehicle_id', default_value='peer_1',
                              description='Namespace of the SLAM leader vehicle.'),
        DeclareLaunchArgument('rtf', default_value='1.0',
                              description='시뮬 배속. transform_timeout을 rtf에 비례하여 자동 조정.'),
        OpaqueFunction(function=_launch_slam),
    ])
