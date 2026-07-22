"""End-to-end fleet simulation.

Spawns:
  - sim_world_node           (publishes /map + static map→<ns>/odom TFs)
  - sim_vehicle_node × 3     (one per vehicle, from config/vehicles.yaml)
  - sim_lidar_node           (only for vehicles with has_lidar: true)
  - twist_mux × 3            (one per vehicle; enforces estop_lock priority chain)
  - central.launch.py        (supervisor + watchdog + foxglove_bridge +
                               scout twist_mux — reused here for main too)

No hardware, no turtlesim dependency — numpy + rclpy + tf2 only.

Run:
  ros2 launch aip_fleet_sim fleet_sim.launch.py
Then open Foxglove Studio → ws://localhost:18765 →
import config/foxglove_layouts/fleet_overview.json.

Drive a vehicle (via autonomy slot — routed through twist_mux):
  ros2 topic pub /aip1/autonomy_cmd_vel geometry_msgs/Twist \\
      '{linear: {x: 0.3}, angular: {z: 0.2}}'
"""
from __future__ import annotations

import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node, PushRosNamespace
from launch.substitutions import LaunchConfiguration


def generate_launch_description() -> LaunchDescription:
    sim_share = get_package_share_directory('aip_fleet_sim')
    bringup_share = get_package_share_directory('aip_fleet_bringup')

    world_yaml = os.path.join(sim_share, 'config', 'world.yaml')
    vehicles_yaml = os.path.join(sim_share, 'config', 'vehicles.yaml')
    twist_mux_params = os.path.join(bringup_share, 'config', 'twist_mux_vehicle.yaml')

    with open(vehicles_yaml) as f:
        vehicles = yaml.safe_load(f)['vehicles']

    actions = [
        DeclareLaunchArgument(
            'with_demo_motion',
            default_value='true',
            description='Publish simulated leader autonomy commands for dashboard demos.',
        )
    ]

    # Shared world + /map + static TFs.
    actions.append(Node(
        package='aip_fleet_sim',
        executable='sim_world_node',
        name='sim_world',
        output='screen',
        parameters=[{'world_yaml': world_yaml, 'vehicles_yaml': vehicles_yaml}],
    ))

    for vid, cfg in vehicles.items():
        vparams = {
            'vehicle_id': vid,
            'initial_x': float(cfg.get('initial_x', 0.0)),
            'initial_y': float(cfg.get('initial_y', 0.0)),
            'initial_theta': float(cfg.get('initial_theta', 0.0)),
            'max_linear_vel': float(cfg.get('max_linear_vel', 0.5)),
            'max_angular_vel': float(cfg.get('max_angular_vel', 1.5)),
            'battery_drain_per_sec': float(cfg.get('battery_drain_per_sec', 0.02)),
        }
        group = [
            PushRosNamespace(vid),
            Node(
                package='aip_fleet_sim',
                executable='sim_vehicle_node',
                name=f'{vid}_sim',
                output='screen',
                parameters=[vparams],
            ),
            # twist_mux enforces estop_lock(90) > central(80) > fleet_coord(50) > autonomy(10).
            # Output cmd_vel_out remapped → cmd_vel consumed by sim_vehicle_node.
            Node(
                package='twist_mux',
                executable='twist_mux',
                name='twist_mux',
                output='screen',
                parameters=[twist_mux_params],
                remappings=[('cmd_vel_out', 'cmd_vel')],
            ),
        ]
        if cfg.get('has_lidar', False):
            group.append(Node(
                package='aip_fleet_sim',
                executable='sim_lidar_node',
                name=f'{vid}_lidar',
                output='screen',
                parameters=[{
                    'vehicle_id': vid,
                    'world_yaml': world_yaml,
                    'range_max': float(cfg.get('lidar_range_max', 8.0)),
                    'num_rays': int(cfg.get('lidar_num_rays', 360)),
                }],
            ))
        actions.append(GroupAction(group))

    actions.append(Node(
        package='aip_fleet_sim',
        executable='demo_patrol_node',
        name='demo_patrol_aip1',
        output='screen',
        parameters=[{'leader_ns': 'aip1'}],
        condition=IfCondition(LaunchConfiguration('with_demo_motion')),
    ))

    # Reuse the real central launch so supervisor/watchdog/foxglove come up
    # with the exact same parameters that ship to prod.
    # with_twist_mux:=false because the sim already spawned twist_mux for
    # every vehicle above; letting central add them again would duplicate nodes.
    actions.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(bringup_share, 'launch', 'central.launch.py')
        ),
        launch_arguments={
            'with_twist_mux': 'false',
            'with_foxglove': 'true',
        }.items(),
    ))

    return LaunchDescription(actions)
