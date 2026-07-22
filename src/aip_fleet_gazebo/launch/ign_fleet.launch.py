"""ign_fleet.launch.py — launch Ignition Fortress with 5 peer vehicles.

Fleet layout (V-formation, peer_1 at origin heading +X):

    peer_4   peer_2              peer_2   peer_4
        \\      \\                    left-rear
         peer_1  →  (heading +X)
        /      /
    peer_5   peer_3

Spawn positions:
  peer_1: ( 0.0,  0.0)  ← leader
  peer_2: (-1.5, +1.0)
  peer_3: (-1.5, -1.0)
  peer_4: (-3.0, +2.0)
  peer_5: (-3.0, -2.0)

Phase-1 launch (basic spawn + static TF, no SLAM):
  ros2 launch aip_fleet_gazebo ign_fleet.launch.py

Phase-2 (add SLAM + Nav2 in separate terminals after Phase-1 is stable):
  ros2 launch aip_fleet_nav slam_leader.launch.py   vehicle_id:=peer_1
  ros2 launch aip_fleet_nav nav_follower.launch.py  vehicle_id:=peer_2
  # repeat for peer_3 .. peer_5

Central stack (supervisor + coordinator):
  ros2 launch aip_fleet_bringup central.launch.py \\
      supervisor_params:=<path>/supervisor_peers.yaml \\
      leader_ns:=peer_1
"""
from __future__ import annotations

import os
import re
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    GroupAction,
    IncludeLaunchDescription,
    OpaqueFunction,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace


def _patch_world_sdf(context, *args, **kwargs):
    """real_time_factor를 런치 인자 rtf 값으로 패치한 임시 SDF 경로를 반환."""
    gz_share  = get_package_share_directory('aip_fleet_gazebo')
    rg_share  = get_package_share_directory('ros_gz_sim')
    gz_launch = os.path.join(rg_share, 'launch', 'gz_sim.launch.py')
    src_sdf   = os.path.join(gz_share, 'worlds', 'fleet_world.sdf')

    rtf = context.launch_configurations.get('rtf', '1.0')
    gui = context.launch_configurations.get('gui', 'true')

    with open(src_sdf) as f:
        sdf_text = f.read()

    patched = re.sub(
        r'<real_time_factor>[\d.]+</real_time_factor>',
        f'<real_time_factor>{rtf}</real_time_factor>',
        sdf_text,
    )

    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='_fleet_world.sdf', delete=False)
    tmp.write(patched)
    tmp.flush()
    world_sdf = tmp.name

    headless = (gui != 'true')
    # -s: 서버 전용 (GUI 클라이언트 비활성화)
    # --headless-rendering: gpu_lidar 등 렌더 기반 센서가 디스플레이 없이도 동작
    gz_arg = f'-r -s --headless-rendering {world_sdf}' if headless else f'-r {world_sdf}'

    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(gz_launch),
            launch_arguments={
                'gz_args': gz_arg,
                'gz_version': '6',
                'on_exit_shutdown': 'true',
            }.items(),
        ),
    ]


# ── Fleet definition: (vehicle_id, spawn_x, spawn_y, spawn_yaw_rad) ──────────
# 3-vehicle fleet matching the real hardware (main + 2 budget peers).
# V-formation: peer_1 leads, peer_2/3 in symmetric left/right rear positions.
_FLEET: list[tuple[str, float, float, float]] = [
    ('peer_1',  0.0,  0.0,  0.0),
    ('peer_2', -1.5,  1.0,  0.0),   # left rear
    ('peer_3', -1.5, -1.0,  0.0),   # right rear
]


def generate_launch_description() -> LaunchDescription:
    gz_share   = get_package_share_directory('aip_fleet_gazebo')
    desc_share = get_package_share_directory('aip_main_description')
    rg_share   = get_package_share_directory('ros_gz_sim')
    world_sdf  = os.path.join(gz_share, 'worlds', 'fleet_world.sdf')
    spawn_py   = os.path.join(gz_share, 'launch', 'spawn_vehicle.launch.py')
    gz_launch  = os.path.join(rg_share, 'launch', 'gz_sim.launch.py')
    ctrl_yaml  = os.path.join(desc_share, 'config', 'ros2_controllers_base.yaml')

    gui            = LaunchConfiguration('gui')
    with_static_tf = LaunchConfiguration('with_static_tf')

    actions: list = [
        DeclareLaunchArgument(
            'gui', default_value='true',
            description='Start Ignition GUI. Set false for headless/CI.'),
        DeclareLaunchArgument(
            'with_static_tf', default_value='true',
            description='Publish static map→<ns>/odom TF per vehicle. '
                        'Set false for Phase-2 (slam_toolbox provides the TF dynamically).'),
        DeclareLaunchArgument(
            'rtf', default_value='1.0',
            description='Gazebo real_time_factor. 1.0=실시간, 2.0=2배속. '
                        'CPU 한계(8코어) 상 1.5 이상은 SLAM/MPPI 지연 위험.'),

        # ── Ignition Gazebo (rtf 패치 SDF로 실행) ───────────────────────────
        # OpaqueFunction이 rtf·gui 인자를 읽어 임시 SDF를 생성 후 Gazebo 기동.
        OpaqueFunction(function=_patch_world_sdf),
    ]

    # ── gz_ros2_control warmup (first-entity namespace bug workaround) ──────────
    # gz_ros2_control-system 0.7.19: the FIRST entity spawned in an Ignition
    # session fails to apply <ros><namespace> to its CM ROS node.  Spawning a
    # minimal dummy robot BEFORE peer_1 absorbs the first-entity slot so that
    # peer_1 becomes the second entity where the namespace IS applied correctly.
    # The warmup CM will not start (expected); peer_1/2/3 CMs will succeed.
    #
    # Why robot_state_publisher with no namespace?
    #   The bugged CM node for the warmup is created at /controller_manager
    #   (no namespace).  It reads robot_description from /robot_state_publisher
    #   (the default robot_param_node), so the warmup RSP must live at that path
    #   so the plugin can proceed past RSP discovery and fully consume the
    #   first-entity initialization slot.
    _warmup_urdf_tmpl = (
        '<?xml version="1.0"?>'
        '<robot name="gz_ctrl_warmup">'
        '  <link name="warmup_base">'
        '    <inertial><mass value="1.0"/>'
        '      <inertia ixx="0.1" ixy="0" ixz="0" iyy="0.1" iyz="0" izz="0.1"/>'
        '    </inertial>'
        '    <visual><geometry><box size="0.05 0.05 0.05"/></geometry></visual>'
        '    <collision><geometry><box size="0.05 0.05 0.05"/></geometry></collision>'
        '  </link>'
        '  <link name="warmup_wheel">'
        '    <inertial><mass value="0.01"/>'
        '      <inertia ixx="1e-5" ixy="0" ixz="0" iyy="1e-5" iyz="0" izz="1e-5"/>'
        '    </inertial>'
        '  </link>'
        '  <joint name="warmup_joint" type="continuous">'
        '    <parent link="warmup_base"/>'
        '    <child link="warmup_wheel"/>'
        '    <axis xyz="0 0 1"/>'
        '  </joint>'
        '  <ros2_control name="warmup_system" type="system">'
        '    <hardware>'
        '      <plugin>gz_ros2_control/GazeboSimSystem</plugin>'
        '    </hardware>'
        '    <joint name="warmup_joint">'
        '      <command_interface name="velocity"/>'
        '      <state_interface name="velocity"/>'
        '      <state_interface name="position"/>'
        '    </joint>'
        '  </ros2_control>'
        '  <gazebo>'
        '    <plugin filename="gz_ros2_control-system"'
        '            name="gz_ros2_control::GazeboSimROS2ControlPlugin">'
        '      <parameters>{ctrl_yaml}</parameters>'
        '      <ros><namespace>/gz_warmup</namespace></ros>'
        '    </plugin>'
        '  </gazebo>'
        '</robot>'
    )
    warmup_urdf = _warmup_urdf_tmpl.format(ctrl_yaml=ctrl_yaml)

    warmup_rsp = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        namespace='gz_warmup',              # → /gz_warmup/robot_state_publisher
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': warmup_urdf,
            'use_sim_time': True,
        }],
    )
    warmup_spawn = Node(
        package='ros_gz_sim',
        executable='create',
        name='spawn_gz_ctrl_warmup',
        output='screen',
        arguments=[
            '-world', 'fleet_world',
            '-name',  'gz_ctrl_warmup',
            '-topic', '/gz_warmup/robot_description',   # matches warmup RSP namespace
            '-x', '-45', '-y', '-45', '-z', '0.05',
        ],
    )
    # ── Single /clock bridge ────────────────────────────────────────────────────
    # 차량별 bridge_peer_N에서 /clock을 각자 발행하면 타임스탬프 순서 역전으로
    # "Detected jump back in time" → TF 버퍼 초기화 → Extrapolation Error 발생.
    # ign_fleet에서 단 하나만 발행하여 문제 방지.
    clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='clock_bridge',
        output='screen',
        arguments=['/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock'],
    )
    actions.append(TimerAction(period=1.0, actions=[warmup_rsp, warmup_spawn, clock_bridge]))

    # ── Spawn each vehicle ───────────────────────────────────────────────────────
    # peer_1 at 3.5 s → SECOND gz_ros2_control entity (namespace OK after warmup).
    # Followers (peer_2/3) get an optional extra delay via follower_spawn_delay arg.
    # fleet_autonomous sets this to ~136 s so followers spawn just before their
    # Nav2 starts (t=155/163 s), preventing SLAM from mapping their static bodies
    # as permanent obstacles for 150 s before AMCL even starts.
    def _spawn_vehicles(context, *args, **kwargs):
        gz_sh = get_package_share_directory('aip_fleet_gazebo')
        sp_py = os.path.join(gz_sh, 'launch', 'spawn_vehicle.launch.py')
        extra = float(LaunchConfiguration('follower_spawn_delay').perform(context))
        acts = []
        for idx, (vid, sx, sy, syaw) in enumerate(_FLEET):
            if idx == 0:
                delay = 3.5
            else:
                # 60 s 간격으로 팔로워를 순차 스폰.
                # 기존 0.8 s 간격은 peer_2/3 컨트롤러·EKF 가 동시에 기동되어
                # CPU 스파이크 → peer_1 EKF 속도 저하 → TF 지연 → explore_lite 실패.
                delay = 3.5 + extra + (idx - 1) * 60.0
            acts.append(
                TimerAction(
                    period=delay,
                    actions=[
                        IncludeLaunchDescription(
                            PythonLaunchDescriptionSource(sp_py),
                            launch_arguments={
                                'vehicle_id': vid,
                                'spawn_x':    str(sx),
                                'spawn_y':    str(sy),
                                'spawn_z':    '0.05',
                                'spawn_yaw':  str(syaw),
                                'world_name': 'fleet_world',
                            }.items(),
                        )
                    ],
                )
            )
        return acts

    actions.append(
        DeclareLaunchArgument(
            'follower_spawn_delay', default_value='0.0',
            description=(
                'Extra delay (s) before spawning follower vehicles (peer_2/3). '
                'Default 0 keeps Phase-1 behaviour. '
                'Set ~136 in fleet_autonomous to avoid SLAM map contamination.'
            ),
        )
    )
    actions.append(OpaqueFunction(function=_spawn_vehicles))

    # ── Phase-1: static map→odom TF per vehicle ──────────────────────────────
    # Lets coordinator_node TF lookups succeed before SLAM is running.
    # Disabled in Phase-2 (with_static_tf:=false) — slam_toolbox provides
    # the map→peer_1/odom TF dynamically; AMCL provides it for followers.
    static_tf_nodes = []
    for vid, sx, sy, _ in _FLEET:
        static_tf_nodes.append(
            Node(
                package='tf2_ros',
                executable='static_transform_publisher',
                name=f'static_map_odom_{vid}',
                output='screen',
                arguments=[
                    str(sx), str(sy), '0',
                    '0', '0', '0',
                    'map',
                    f'{vid}/odom',
                ],
                parameters=[{'use_sim_time': True}],
            )
        )
    actions.append(
        GroupAction(static_tf_nodes, condition=IfCondition(with_static_tf))
    )

    return LaunchDescription(actions)
