"""fleet_phase2.launch.py — Phase-2: SLAM (peer_1) + Nav2 (peer_2~3) + coordination.

Single-command Phase-2 bring-up for the Ignition Fortress simulation:
  ros2 launch aip_fleet_gazebo fleet_phase2.launch.py

Bring-up timeline (TimerAction keeps nodes from racing):
  t= 0 s  Ignition Fortress + 3 vehicles spawn (peer_1/2/3; last at ~4 s)
  t=14 s  twist_mux × 3  (spawners now at t_spawn+6 s; peer_3 active by ~t=10 s)
  t=16 s  slam_toolbox (peer_1) + sim_peer_sensing_node
  t=19 s  coordinator × 2  (safe: publishes zero-vel until TF is available)
  t=55 s  AMCL + controller_server for peer_2~3  (SLAM ~39 s from t=16)
  t+1.5 s stagger between each follower to reduce init load

Sensing topics (sim_peer_sensing_node):
  /fleet/peer_poses   PeerPoseArray  — SLAM-derived absolute positions
  /fleet/peer_ranges  PeerRangeArray — pairwise ranges with Gaussian noise

For supervisor / Foxglove monitoring, run separately in another terminal:
  ros2 launch aip_fleet_bringup central.launch.py \\
      supervisor_params:=$(ros2 pkg prefix aip_fleet_bringup)/share/aip_fleet_bringup/config/supervisor_peers.yaml \\
      leader_ns:=peer_1  with_twist_mux:=false  with_coordinator:=false

Teleop in Phase-2 (peer_1 must be driven through twist_mux override slot):
  ros2 run teleop_twist_keyboard teleop_twist_keyboard \\
      --ros-args --remap cmd_vel:=/peer_1/override_cmd_vel
"""
from __future__ import annotations

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    TimerAction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace


_LEADER    = 'peer_1'
_FOLLOWERS = ['peer_2', 'peer_3']
_ALL_PEERS = [_LEADER] + _FOLLOWERS

# V-formation coordinator offsets (behind / lateral of leader body frame).
# Symmetric chevron: left-rear / right-rear. Matches central.launch.py formula.
_OFFSETS: dict[str, tuple[float, float]] = {
    'peer_2': (-1.5, +1.0),   # left rear
    'peer_3': (-1.5, -1.0),   # right rear
}

# Spawn positions (must match ign_fleet.launch.py).
_SPAWN_POS: dict[str, tuple[float, float, float]] = {
    'peer_1': (0.0,   0.0,  0.0),
    'peer_2': (-1.5, +1.0,  0.0),
    'peer_3': (-1.5, -1.0,  0.0),
}


def generate_launch_description() -> LaunchDescription:
    gz_share      = get_package_share_directory('aip_fleet_gazebo')
    nav_share     = get_package_share_directory('aip_fleet_nav')
    bringup_share = get_package_share_directory('aip_fleet_bringup')

    ign_fleet_py      = os.path.join(gz_share,      'launch', 'ign_fleet.launch.py')
    slam_leader_py    = os.path.join(nav_share,     'launch', 'slam_leader.launch.py')
    nav_follow_py     = os.path.join(nav_share,     'launch', 'nav_follower.launch.py')
    twist_mux_yaml    = os.path.join(bringup_share, 'config', 'twist_mux_vehicle.yaml')
    sensing_script_py = os.path.join(gz_share,      'scripts', 'sim_peer_sensing_node.py')

    gui = LaunchConfiguration('gui')

    actions: list = [
        DeclareLaunchArgument(
            'gui', default_value='true',
            description='Start Ignition GUI. Set false for headless/CI.'),

        # ── Phase-1 base: Ignition + 3 vehicle spawns ─────────────────────────
        # with_static_tf:=false because slam_toolbox/AMCL will publish the
        # dynamic map→<ns>/odom TF; static publishers would conflict.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(ign_fleet_py),
            launch_arguments={
                'gui':            gui,
                'with_static_tf': 'false',
            }.items(),
        ),
    ]

    # ── t=14 s: twist_mux × 3 ────────────────────────────────────────────────
    # spawn_vehicle fires spawners at t_spawn+6 s; peer_3 active by ~t=10 s.
    # Routes: override_cmd_vel(80) > coord_cmd_vel(50) > autonomy_cmd_vel(10).
    twist_mux_group = []
    for vid in _ALL_PEERS:
        twist_mux_group.append(
            GroupAction([
                PushRosNamespace(vid),
                Node(
                    package='twist_mux',
                    executable='twist_mux',
                    name='twist_mux',
                    output='screen',
                    parameters=[twist_mux_yaml, {'use_sim_time': False}],
                    remappings=[('cmd_vel_out', 'cmd_vel')],
                ),
            ])
        )
    actions.append(TimerAction(period=14.0, actions=twist_mux_group))

    # ── t=16 s: SLAM leader + sim peer sensing ────────────────────────────────
    # sim_peer_sensing_node uses TF lookups → safe to start anytime after TF
    # is publishing. Starts here alongside SLAM so pose data is available from
    # the moment the first map→<ns>/base_link chain becomes valid.
    actions.append(
        TimerAction(
            period=16.0,
            actions=[
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(slam_leader_py),
                    launch_arguments={'vehicle_id': _LEADER}.items(),
                ),
                Node(
                    package='aip_fleet_gazebo',
                    executable='sim_peer_sensing_node.py',
                    name='sim_peer_sensing',
                    output='screen',
                    parameters=[{
                        'use_sim_time':          True,
                        'vehicle_ids':           _ALL_PEERS,
                        'range_noise_stddev_m':  0.05,
                        'max_range_m':           10.0,
                        'publish_hz':            10.0,
                    }],
                ),
            ],
        )
    )

    # ── t=19 s: coordinator × 2 ───────────────────────────────────────────────
    # Publishes zero-vel safely until both leader and follower TF are available.
    coordinator_nodes = []
    for vid in _FOLLOWERS:
        ox, oy = _OFFSETS[vid]
        coordinator_nodes.append(
            Node(
                package='aip_fleet_coordinator',
                executable='coordinator_node',
                name=f'coordinator_{vid}',
                output='screen',
                parameters=[{
                    'use_sim_time': True,
                    'leader_ns':   _LEADER,
                    'follower_ns': vid,
                    'offset_x':    ox,
                    'offset_y':    oy,
                }],
            )
        )
    actions.append(TimerAction(period=19.0, actions=coordinator_nodes))

    # ── t=55 s (+8.0 s stagger): AMCL + Nav2 per follower ────────────────────
    # SLAM needs ~35–40 s from t=16 to build a reliable map in a new environment.
    # t=55 s gives 39 s of SLAM build time (ready by ~t=50–54 s with margin).
    # Stagger 8.0 s between followers:
    #   peer_2 AMCL at t=55 s, peer_3 at t=63 s.
    #   Wider gap reduces resource contention (parallel particle storms) and
    #   gives peer_2's EKF/AMCL time to fully stabilise before peer_3 init.
    for i, vid in enumerate(_FOLLOWERS):
        delay = 55.0 + i * 8.0
        actions.append(
            TimerAction(
                period=delay,
                actions=[
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(nav_follow_py),
                        launch_arguments={'vehicle_id': vid}.items(),
                    )
                ],
            )
        )

    return LaunchDescription(actions)
