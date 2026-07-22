"""autonomous_nav.launch.py — full Nav2 stack for one autonomous vehicle.

Starts all Nav2 nodes for a follower peer operating on the shared /map
produced by peer_1's slam_toolbox.  Unlike nav_follower.launch.py (which
only runs AMCL + local DWB for V-formation following), this launch file
adds a global planner and BT navigator so the vehicle can accept and execute
independent NavigateToPose goals.

Nodes started (all under PushRosNamespace(vehicle_id)):
  amcl              — localisation on shared /map
  planner_server    — global path planner (NavFn)
  bt_navigator      — NavigateToPose action executive
  controller_server — local obstacle avoidance (DWB) → autonomy_cmd_vel
  lifecycle_manager — manages the four nodes above together

Goal input after launch:
  RViz2   : 2D Goal Pose widget → /peer_N/navigate_to_pose
  CLI     : ros2 action send_goal /peer_N/navigate_to_pose \\
                nav2_msgs/action/NavigateToPose \\
                '{pose: {header: {frame_id: map}, pose: {position: {x: 1.0}}}}'
  patrol  : ros2 run aip_fleet_autonomous patrol_node \\
                --ros-args -p vehicle_id:=peer_2 -p waypoints:="[…]"

Usage:
  ros2 launch aip_fleet_autonomous autonomous_nav.launch.py vehicle_id:=peer_2
"""
from __future__ import annotations

import os
import string
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace

# 시뮬 기본 초기 포즈 (Gazebo 스폰 좌표와 동일해야 AMCL 수렴 성공).
# 실차 사용 시에는 launch argument initial_pose_x/y/a 로 오버라이드.
_INITIAL_POSES: dict[str, tuple[float, float, float]] = {
    'peer_2': (-1.5,  1.0, 0.0),
    'peer_3': (-1.5, -1.0, 0.0),
}


def _render_yaml(template_path: str, vehicle_id: str,
                 ix: float = 0.0, iy: float = 0.0, ia: float = 0.0,
                 map_topic: str = '/map_static') -> str:
    with open(template_path) as f:
        rendered = string.Template(f.read()).substitute(
            vehicle_id=vehicle_id,
            initial_pose_x=ix,
            initial_pose_y=iy,
            initial_pose_a=ia,
            map_topic=map_topic,
        )
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', delete=False,
        prefix=f'autonav_{vehicle_id}_',
    )
    tmp.write(rendered)
    tmp.close()
    return tmp.name


def _launch_autonomous(context, *args, **kwargs):
    vid        = LaunchConfiguration('vehicle_id').perform(context)
    auto_share = get_package_share_directory('aip_fleet_autonomous')

    # BackUp/Spin/Wait 충돌 복구 BT — leader와 동일 BT 사용.
    # behavior_server가 함께 기동되어 recovery action 서버를 제공한다.
    _bt_recovery = os.path.join(
        auto_share, 'behavior_trees',
        'navigate_w_collision_recovery.xml',
    )
    bt_xml           = _bt_recovery   # NavigateToPose 용
    bt_xml_through   = _bt_recovery   # NavigateThroughPoses 용

    # 초기 포즈: launch arg 우선 → 시뮬 기본값 → 원점
    _ix_str = LaunchConfiguration('initial_pose_x').perform(context)
    _iy_str = LaunchConfiguration('initial_pose_y').perform(context)
    _ia_str = LaunchConfiguration('initial_pose_a').perform(context)
    if _ix_str != '' and _iy_str != '':
        ix, iy, ia = float(_ix_str), float(_iy_str), float(_ia_str or '0.0')
    else:
        ix, iy, ia = _INITIAL_POSES.get(vid, (0.0, 0.0, 0.0))

    nav2_yaml = _render_yaml(
        os.path.join(auto_share, 'params', 'nav2_full.yaml'), vid,
        ix=ix, iy=iy, ia=ia,
    )

    return [
        GroupAction([
            PushRosNamespace(vid),

            # ── AMCL ─────────────────────────────────────────────────────────
            # Localises on /map from peer_1 slam_toolbox.
            # Per-vehicle initial_pose is baked into nav2_yaml via Template
            # substitution — no dict override needed (avoids yaml/dict precedence
            # ambiguity that caused all vehicles to converge at map origin).
            Node(
                package='nav2_amcl',
                executable='amcl',
                name='amcl',
                output='screen',
                parameters=[nav2_yaml, {'use_sim_time': True}],
                remappings=[
                    ('scan', f'/{vid}/scan'),
                    # /map_static: follower_trigger_node가 peer 스폰 전에 저장한 정적 맵.
                    # peer 스폰 후 SLAM /map은 차체 phantom wall로 오염될 수 있으므로
                    # 오염 이전 시점의 깨끗한 맵을 AMCL에 제공.
                    ('map',  '/map_static'),
                ],
            ),

            # ── Global Planner (NavFn) ────────────────────────────────────────
            Node(
                package='nav2_planner',
                executable='planner_server',
                name='planner_server',
                output='screen',
                parameters=[nav2_yaml, {'use_sim_time': True}],
                remappings=[('map', '/map_static')],
            ),

            # ── BT Navigator ──────────────────────────────────────────────────
            # Exposes /peer_N/navigate_to_pose action server.
            # RViz2's 2D Goal Pose and patrol_node both target this action.
            Node(
                package='nav2_bt_navigator',
                executable='bt_navigator',
                name='bt_navigator',
                output='screen',
                parameters=[nav2_yaml, {
                    'use_sim_time': True,
                    'default_nav_to_pose_bt_xml':      bt_xml,
                    'default_nav_through_poses_bt_xml': bt_xml_through,
                }],
                remappings=[
                    ('odom', f'/{vid}/odometry/filtered'),
                    ('map',  '/map_static'),
                ],
            ),

            # ── Controller Server (MPPI local planner) ────────────────────────
            # Publishes to autonomy_cmd_vel (twist_mux priority 10).
            # In autonomous mode coordinator is NOT running, so autonomy slot
            # is always active (coord_cmd_vel times out after 0.5 s).
            Node(
                package='nav2_controller',
                executable='controller_server',
                name='controller_server',
                output='screen',
                arguments=['--ros-args', '--log-level', 'WARN'],
                parameters=[nav2_yaml, {'use_sim_time': True}],
                remappings=[
                    ('cmd_vel', f'/{vid}/autonomy_cmd_vel'),
                    ('scan',    f'/{vid}/scan'),
                    # Nav2 Humble MPPI가 절대 경로 /trajectories 로 발행 (네임스페이스 무시)
                    ('/trajectories', f'/{vid}/trajectories'),
                ],
            ),

            # ── Behavior Server (BackUp / Spin / Wait) ────────────────────────
            # navigate_w_collision_recovery.xml BT의 회복 동작(BackUp/Spin/Wait) 제공.
            # peer_1(leader_nav)과 동일한 구성 — 고착·오버슛 상황에서 물리적 복구 가능.
            Node(
                package='nav2_behaviors',
                executable='behavior_server',
                name='behavior_server',
                output='screen',
                parameters=[nav2_yaml, {'use_sim_time': True}],
                remappings=[
                    ('cmd_vel', f'/{vid}/autonomy_cmd_vel'),
                ],
            ),

            # ── Lifecycle Manager ─────────────────────────────────────────────
            # Manages all five Nav2 nodes in a single lifecycle group.
            # bond_timeout=0: 플러그인 로딩 지연(Ubuntu 환경) 시 본드 타임아웃 비활성화.
            Node(
                package='nav2_lifecycle_manager',
                executable='lifecycle_manager',
                name='lifecycle_manager_nav',
                output='screen',
                parameters=[{
                    'use_sim_time': True,
                    'autostart':    True,
                    'bond_timeout': 0.0,
                    'node_names': [
                        'amcl',
                        'planner_server',
                        'bt_navigator',
                        'controller_server',
                        'behavior_server',
                    ],
                }],
            ),
        ])
    ]


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        DeclareLaunchArgument(
            'vehicle_id', default_value='peer_2',
            description='팔로워 차량 네임스페이스. 시뮬: peer_2 / 실차: aip2'),
        # 초기 포즈 — 지정 시 _INITIAL_POSES 시뮬 기본값보다 우선.
        # 실차: 실제 시작 위치(맵 좌표)로 설정. 미지정 시 빈 문자열 → 시뮬 기본값 사용.
        DeclareLaunchArgument('initial_pose_x', default_value='',
            description='AMCL 초기 X 좌표 (m, 맵 프레임). 미지정 시 시뮬 기본값 사용.'),
        DeclareLaunchArgument('initial_pose_y', default_value='',
            description='AMCL 초기 Y 좌표 (m, 맵 프레임). 미지정 시 시뮬 기본값 사용.'),
        DeclareLaunchArgument('initial_pose_a', default_value='0.0',
            description='AMCL 초기 yaw 각 (rad). 미지정 시 0.0.'),
        OpaqueFunction(function=_launch_autonomous),
    ])
