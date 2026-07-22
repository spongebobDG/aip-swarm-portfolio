"""nav_follower.launch.py — AMCL + Nav2 local planner for a follower vehicle.

Each follower (peer_2 … peer_5) runs its own AMCL instance to localise on
the /map published by the leader's slam_toolbox.  The DWB local planner
handles obstacle avoidance; high-level following targets come from
coordinator_node via /<vehicle_id>/coord_cmd_vel → twist_mux.

Usage:
  ros2 launch aip_fleet_nav nav_follower.launch.py vehicle_id:=peer_2
  ros2 launch aip_fleet_nav nav_follower.launch.py vehicle_id:=peer_3
  ...
"""
from __future__ import annotations

import os
import string
import tempfile

# Initial poses must match the spawn positions in ign_fleet.launch.py.
# AMCL initialises all particles around initial_pose; without this, particles
# cluster at (0,0) while the robot is at the spawn offset → AMCL stalls,
# coordinator gets no TF → V-formation never starts.
_INITIAL_POSES: dict[str, tuple[float, float, float]] = {
    'peer_2': (-1.5,  1.0, 0.0),
    'peer_3': (-1.5, -1.0, 0.0),
}

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace


def _render_yaml(template_path: str, vehicle_id: str) -> str:
    """Substitute ${vehicle_id} tokens and write to a temp file."""
    with open(template_path) as f:
        rendered = string.Template(f.read()).substitute(vehicle_id=vehicle_id)
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', delete=False,
        prefix=f'nav_{vehicle_id}_',
    )
    tmp.write(rendered)
    tmp.close()
    return tmp.name


def _launch_follower(context, *args, **kwargs):
    vid       = LaunchConfiguration('vehicle_id').perform(context)
    nav_share = get_package_share_directory('aip_fleet_nav')

    amcl_yaml = _render_yaml(
        os.path.join(nav_share, 'params', 'amcl.yaml'), vid
    )
    nav_yaml = _render_yaml(
        os.path.join(nav_share, 'params', 'nav2_params.yaml'), vid
    )

    ix, iy, ia = _INITIAL_POSES.get(vid, (0.0, 0.0, 0.0))

    return [
        GroupAction([
            PushRosNamespace(vid),

            # AMCL: publishes map → peer_N/odom TF
            # 'map' must be remapped to '/map' (absolute) because PushRosNamespace
            # would otherwise make AMCL subscribe to /peer_N/map, not /map.
            Node(
                package='nav2_amcl',
                executable='amcl',
                name='amcl',
                output='screen',
                parameters=[amcl_yaml, {
                    'use_sim_time': True,
                    'set_initial_pose': True,  # use initial_pose_* params, not /initialpose topic
                    'initial_pose_x': ix,
                    'initial_pose_y': iy,
                    'initial_pose_a': ia,
                    # Tight initial particle cloud: spawn position is known exactly.
                    # Default Nav2 covariance (0.25 m²) spreads particles ±0.5 m,
                    # into areas where SLAM has recorded peer body ghost obstacles.
                    'initial_cov_xx': 0.05,   # σ ≈ 0.22 m
                    'initial_cov_yy': 0.05,
                    'initial_cov_aa': 0.025,  # σ ≈ 9°
                }],
                remappings=[
                    ('scan', f'/{vid}/scan'),
                    ('map',  '/map'),
                ],
            ),

            # Lifecycle manager: brings up AMCL automatically
            Node(
                package='nav2_lifecycle_manager',
                executable='lifecycle_manager',
                name='lifecycle_manager_localization',
                output='screen',
                parameters=[{
                    'use_sim_time': True,
                    'autostart': True,
                    'bond_timeout': 0.0,
                    'node_names': ['amcl'],
                }],
            ),

            # DWB controller server: local obstacle avoidance
            Node(
                package='nav2_controller',
                executable='controller_server',
                name='controller_server',
                output='screen',
                arguments=['--ros-args', '--log-level', 'WARN'],
                parameters=[nav_yaml, {'use_sim_time': True}],
                remappings=[
                    ('cmd_vel', f'/{vid}/autonomy_cmd_vel'),  # → twist_mux autonomy slot
                    ('scan',    f'/{vid}/scan'),
                ],
            ),

            # Lifecycle manager for controller
            Node(
                package='nav2_lifecycle_manager',
                executable='lifecycle_manager',
                name='lifecycle_manager_controller',
                output='screen',
                parameters=[{
                    'use_sim_time': True,
                    'autostart': True,
                    'bond_timeout': 0.0,
                    'node_names': ['controller_server'],
                }],
            ),
        ])
    ]


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        DeclareLaunchArgument('vehicle_id', default_value='peer_2',
                              description='Namespace of the follower vehicle.'),
        OpaqueFunction(function=_launch_follower),
    ])
