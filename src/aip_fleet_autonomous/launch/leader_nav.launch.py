"""leader_nav.launch.py — Nav2 planner/controller/BT for the SLAM leader (peer_1).

autonomous_nav.launch.py 와 달리 AMCL 을 시작하지 않는다.
slam_toolbox 가 이미 map → peer_1/odom TF 를 발행하고 있으므로
planner/controller/bt_navigator 만 추가로 올리면 NavigateToPose 가 동작한다.

Nodes started (all under PushRosNamespace(vehicle_id)):
  planner_server    — global path planning (SmacHybrid-A*)
  bt_navigator      — NavigateToPose action
  controller_server — local DWB  →  autonomy_cmd_vel
  lifecycle_manager — manages above three
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


def _render_yaml(template_path: str, vehicle_id: str,
                 prefix: str = 'leadernav') -> str:
    """Template yaml을 vehicle_id 등으로 치환 후 임시 파일에 기록하고 경로 반환."""
    with open(template_path) as f:
        rendered = string.Template(f.read()).substitute(
            vehicle_id=vehicle_id,
            # peer_1(leader)은 AMCL 미사용 — slam_toolbox가 TF 담당.
            # nav2_full.yaml의 ${initial_pose_*} 변수 치환용 더미값.
            initial_pose_x=0.0,
            initial_pose_y=0.0,
            initial_pose_a=0.0,
            # leader는 slam_toolbox 실시간 맵을 global costmap에 사용.
            map_topic='/map',
        )
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', delete=False,
        prefix=f'{prefix}_{vehicle_id}_',
    )
    tmp.write(rendered)
    tmp.close()
    return tmp.name


def _launch_leader_nav(context, *args, **kwargs):
    vid        = LaunchConfiguration('vehicle_id').perform(context)
    rtf        = float(LaunchConfiguration('rtf').perform(context))
    auto_share = get_package_share_directory('aip_fleet_autonomous')

    # rtf=4.0에서 slam 처리 지연 ~1.7~2.0s sim → tolerance ≥ 2.0 필요.
    # max(2.0, rtf × 1.0): rtf=1→2.0, rtf=2→2.0, rtf=3→3.0, rtf=4→4.0
    tf_tol = max(2.0, rtf * 1.0)

    # nav2_full.yaml(TB3 Burger 기준 base) + nav2_override_peer1.yaml(FIT0186 오버라이드) 병합.
    # ROS2 Node.parameters 리스트: 뒤에 오는 파일/딕트가 앞선 값을 덮어씀.
    nav2_yaml = _render_yaml(
        os.path.join(auto_share, 'params', 'nav2_full.yaml'), vid,
        prefix='leadernav_base',
    )
    nav2_override = _render_yaml(
        os.path.join(auto_share, 'params', 'nav2_override_peer1.yaml'), vid,
        prefix='leadernav_override',
    )

    # 커스텀 충돌 회복 BT: BackUp(0.50m) → Spin(180°) → ClearCostmap → Wait(3s)
    # 기본 BT 대비 변경: 후진을 Spin보다 먼저 → 벽에서 탈출 후 방향 전환
    _bt_simple = os.path.join(
        auto_share, 'behavior_trees',
        'navigate_w_collision_recovery.xml',
    )

    return [
        GroupAction([
            PushRosNamespace(vid),

            # ── Global Planner ────────────────────────────────────────────────
            Node(
                package='nav2_planner',
                executable='planner_server',
                name='planner_server',
                output='screen',
                parameters=[nav2_yaml, nav2_override, {'use_sim_time': True,
                                                        'transform_tolerance': tf_tol}],
                remappings=[('map', '/map')],
            ),

            # ── BT Navigator ──────────────────────────────────────────────────
            Node(
                package='nav2_bt_navigator',
                executable='bt_navigator',
                name='bt_navigator',
                output='screen',
                parameters=[nav2_yaml, nav2_override, {
                    'use_sim_time': True,
                    'transform_tolerance':              tf_tol,
                    'default_nav_to_pose_bt_xml':       _bt_simple,
                    'default_nav_through_poses_bt_xml': _bt_simple,
                }],
                remappings=[
                    ('odom', f'/{vid}/odometry/filtered'),
                    ('map',  '/map'),
                ],
            ),

            # ── Controller (MPPI) ─────────────────────────────────────────────
            Node(
                package='nav2_controller',
                executable='controller_server',
                name='controller_server',
                output='screen',
                arguments=['--ros-args', '--log-level', 'WARN'],
                parameters=[nav2_yaml, nav2_override, {'use_sim_time': True,
                                                        'transform_tolerance': tf_tol}],
                remappings=[
                    ('cmd_vel', f'/{vid}/autonomy_cmd_vel'),
                    ('scan',    f'/{vid}/scan'),
                    # Nav2 Humble MPPI가 절대 경로 /trajectories 로 발행 (네임스페이스 무시)
                    ('/trajectories', f'/{vid}/trajectories'),
                ],
            ),

            # ── Behavior Server (BackUp / Spin / Wait) ────────────────────────
            # recovery BT가 ClearCostmap + Spin + BackUp 호출 시 필요.
            Node(
                package='nav2_behaviors',
                executable='behavior_server',
                name='behavior_server',
                output='screen',
                parameters=[nav2_yaml, nav2_override, {'use_sim_time': True,
                                                        'transform_tolerance': tf_tol}],
                remappings=[
                    ('cmd_vel', f'/{vid}/autonomy_cmd_vel'),
                ],
            ),

            # ── Lifecycle Manager (AMCL 없음 — slam_toolbox가 map→odom TF 담당) ──
            # Ubuntu 환경에서는 behavior_server를 lifecycle에 포함한다.
            # (navigate_w_collision_recovery.xml의 BackUp 노드가 behavior_server
            #  action을 필요로 하므로 lifecycle 관리 대상에 포함해야 bt_navigator 로드 성공)
            # bond_timeout=0: 플러그인 로딩 지연 시 본드 타임아웃 비활성화.
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
                        'controller_server',
                        'planner_server',
                        'behavior_server',
                        'bt_navigator',
                    ],
                }],
            ),
        ])
    ]


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        DeclareLaunchArgument(
            'vehicle_id', default_value='peer_1',
            description='SLAM 리더 차량 네임스페이스 (slam_toolbox 가 TF 담당).'),
        DeclareLaunchArgument(
            'rtf', default_value='1.0',
            description='시뮬 배속. transform_tolerance를 rtf에 비례하여 자동 조정.'),
        OpaqueFunction(function=_launch_leader_nav),
    ])
