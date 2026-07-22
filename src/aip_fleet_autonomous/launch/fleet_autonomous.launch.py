"""fleet_autonomous.launch.py — 독립 자율 주행 모드 플릿 런치.

fleet_phase2.launch.py (V 포메이션 추종)와 달리, 각 팔로워 차량이
coordinator 없이 독립적으로 목표를 수신하고 주행한다.

아키텍처:
  peer_1  — Ignition + EKF + slam_toolbox → /map 생성
  peer_2  — Ignition + EKF + AMCL + SmacHybrid-A* + BT Navigator + DWB
  peer_3  — Ignition + EKF + AMCL + SmacHybrid-A* + BT Navigator + DWB

coordinator_node 없음 → V 포메이션 없음.
autonomy_cmd_vel (priority 10) 이 twist_mux 에서 유일 활성 슬롯.

목표 입력 방법 3가지 (동시 지원):
  1. RViz2  — 2D Goal Pose → /peer_N/navigate_to_pose action
  2. CLI    — ros2 action send_goal /peer_N/navigate_to_pose …
  3. 자동   — with_patrol:=true 로 순찰 노드 자동 시작

추가 기능:
  with_peer_obstacles:=true  — peer_obstacle_node 실행 (다중 로봇 충돌 방지)
  with_coverage:=true        — coverage_tracker_node 실행 (커버리지 추적)
  with_thermal:=true         — 열화상 시뮬 파이프라인 (scenario_manager + sim_thermal + patrol_monitor)

브링업 타임라인:
  t=  0 s  Ignition 기동
  t=  3.5s peer_1 스폰
  t= 14 s  twist_mux × 3
  t= 16 s  sim_peer_sensing_node + map_readiness_node [+ scenario_manager + sim_thermal]
  t= 18 s  peer_obstacle_node (선택)
  t= 21 s  slam_toolbox (peer_1) — EKF(t=20.5s) 이후 시작으로 TF 경쟁 조건 제거
  t= 22 s  patrol_monitor × 3 (선택)
  t= 40 s  peer_1 Nav2 (AMCL 없음, leader_nav)
  t= 50 s  follower_trigger_node (맵 준비 감시, map_ready 구독 선행)
  t= 60 s  explore_lite (자율 프론티어 탐색)
  t= 70 s  coverage_tracker_node (선택, Nav2 맵 수신 후)
  t=243.5s peer_2 스폰 (follower_spawn_delay=240 + 60 s 스태거)
  t=303.5s peer_3 스폰 (peer_2 완료 후 60 s 뒤 → CPU 충돌 방지)
  t=~맵완성 /fleet/map_ready → follower_trigger_node → peer_2/3 Nav2 자동 기동
            (explore_lite 프론티어 소진 확인 후)

순찰 구역 (3-zone 겹침 없음, 구석 커버리지 확장):
  peer_1 — 북부 전담  y≥1.0  (doorway 통과, 북동/북서 구석 x=±4.5 + 열원 구역)
  peer_2 — 동남 전담  y<1.5, x>0  (동쪽 x=4.5 벽 근접 + 남부 y=-7.5 심층)
  peer_3 — 서남 전담  y<1.5, x<0  (서쪽 x=-4.5 벽 근접 + 남부 y=-7.5 심층)

Hybrid-A* doorway:
  fleet_world.sdf 에 y=4.0 위치 0.70m 너비 문 추가.
  peer_1 만 이 문을 통과하여 열원(heat_source_fire 등)에 접근.

Usage:
  ros2 launch aip_fleet_autonomous fleet_autonomous.launch.py
  ros2 launch aip_fleet_autonomous fleet_autonomous.launch.py with_patrol:=true
  ros2 launch aip_fleet_autonomous fleet_autonomous.launch.py \\
      with_patrol:=true with_peer_obstacles:=true with_coverage:=true with_thermal:=true
  ros2 launch aip_fleet_autonomous fleet_autonomous.launch.py gui:=false

열화상 시나리오 전환 (with_thermal:=true 실행 중):
  ros2 topic pub --once /sim/set_scenario std_msgs/String '{data: FIRE}'
  ros2 topic pub --once /sim/set_scenario std_msgs/String '{data: NORMAL}'
  ros2 topic pub --once /sim/set_scenario std_msgs/String '{data: OVERHEATING}'
  ros2 topic pub --once /sim/set_scenario std_msgs/String '{data: PROGRESSIVE}'
"""
from __future__ import annotations

import math
import os
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    GroupAction,
    IncludeLaunchDescription,
    OpaqueFunction,
    TimerAction,
)
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace

# 시뮬 기본값 — launch argument로 오버라이드 가능
# 실차 예시: leader:=aip1 followers:=aip2,aip3
_LEADER    = 'peer_1'
_FOLLOWERS = ['peer_2', 'peer_3']
_ALL_PEERS = [_LEADER] + _FOLLOWERS

_SPAWN_POS: dict[str, tuple[float, float, float]] = {
    'peer_1': ( 0.0,   0.0,  0.0),
    'peer_2': (-1.5,  +1.0,  0.0),
    'peer_3': (-1.5,  -1.0,  0.0),
}

# 순찰 웨이포인트 [x, y, yaw_deg, …] — 맵 프레임.
#
# ── 3-zone 구역 분할 (겹침 없음, 구석 커버리지 확장) ──────────────────────
#   peer_1 : 북부 전담  — 북동(4.5,7.5)/북서(-4.5,7.5) 구석까지 확장
#   peer_2 : 동남 전담  — x=4.5 동쪽 벽 + 남부 y=-7.5 심층까지 확장
#   peer_3 : 서남 전담  — x=-4.5 서쪽 벽 + 남부 y=-7.5 심층까지 확장
#
#   doorway: x=2.5, y=4.0 (너비 0.7m) — peer_1 만 통과, peer_2/3 는 불진입
#   shelf_center: y=6.0, x=[−3,3] — Nav2 가 자동 우회
#   shelf_N_east(6.5,7.5)/shelf_N_west(-6.5,7.5): 북부 측벽 선반
#   열원: heat_source_fire(2.0,7.5), heat_source_shelf(-2.0,6.0)
#   적재구역: col_loading_E(4.5,-4.0)/W(-4.5,-4.0) inflation 회피 (x=4.5 시 y=-5.5 이남)
#   남부 크레이트: crate_S_center(0,-8.5) → y=-7.5 이북 유지
#   모든 좌표: inflation_radius=0.35m 기준 안전 검증 완료
_PATROL_WP: dict[str, list[float]] = {
    # ── peer_1: 북부 전담 + 북동/북서 구석 확장 ─────────────────────────────
    # 경로: 중앙 → doorway 동측 → 북동구석(4.5,7.5) → 열원 → 북서구석(-4.5,7.5) → 복귀
    # shelf_center 우회: x=4.5 (동) 또는 x=-4.5 (서) — shelf 동/서 끝에서 1.8m 이격
    # shelf_N_east/west: x=±4.5 에서 각각 1.8m 이격 — 북동/북서 측면 구석 도달 가능
    'peer_1': [
         0.0,  1.5,  90.0,   # 중앙 시작
         2.5,  3.5,  90.0,   # doorway 직전
         3.5,  4.6,  45.0,   # doorway 통과 동측 (doorway_wall_east 에서 0.50m)
         4.5,  5.5,  90.0,   # 북동 하단 — shelf_center 동쪽 끝에서 1.8m
         4.5,  7.5, 135.0,   # 북동 구석 — shelf_N_east 서쪽 에서 1.8m
         2.0,  7.5, 135.0,   # heat_source_fire (2.0, 7.5) 인근
        -1.5,  7.5, 180.0,   # 북부 중앙 횡단 — heat_source_shelf 탐지 거리
        -4.5,  7.5,-135.0,   # 북서 구석 — shelf_N_west 동쪽에서 1.8m
        -4.5,  5.5,-135.0,   # 북서 하단 — shelf_center 서쪽 끝에서 1.8m
         2.5,  4.5, -90.0,   # doorway 복귀
         0.0,  1.5, 180.0,   # 귀환
    ],
    # ── peer_2: 동남 전담 + 동쪽 벽 근접 + 남부 심층 ───────────────────────
    # 경로: 동쪽(x=4.5) 상단 → 남행 → col_loading_E(4.5,-4.0) 우회(y=-5.5) →
    #       남부 심층(y=-7.5) → 서행 복귀
    # x=4.5: pillar_2(4.0,3.0)/pillar_4(4.0,-3.0) 에서 최소 0.73m 이격
    # y=-5.5: col_loading_E 남쪽 inflation 경계(y=-4.55)에서 1.3m 이격
    # y=-7.5: crate_S_center(0,-8.5) 북쪽 inflation 경계(y=-7.75)에서 0.6m 이격
    'peer_2': [
         4.5,  0.5,   0.0,   # 동쪽 상단 — pillar_2/4 사이 동쪽 벽 근접
         4.5, -2.0, -90.0,   # 동쪽 중앙 — pillar_4 에서 0.73m
         4.5, -5.5, -90.0,   # 동쪽 남부 — col_loading_E 남쪽 1.3m
         3.0, -7.5, 180.0,   # 남동 심층 구석 — 적재/rack 구역
         1.5, -7.5, 180.0,   # 남부 동측 심층 — crate 이북 0.6m
         0.5, -5.0, 180.0,   # 남부 중앙 복귀
         0.5, -2.0,  90.0,   # 북행 복귀
         2.0,  0.5,  90.0,   # 동측 복귀
    ],
    # ── peer_3: 서남 전담 + 서쪽 벽 근접 + 남부 심층 ───────────────────────
    # peer_2 와 대칭 (x 부호 반전, yaw 대칭)
    # x=-4.5: pillar_1(-4.0,3.0)/pillar_3(-4.0,-3.0) 에서 최소 0.73m 이격
    'peer_3': [
        -4.5,  0.5, 180.0,   # 서쪽 상단 — pillar_1/3 사이 서쪽 벽 근접
        -4.5, -2.0, -90.0,   # 서쪽 중앙 — pillar_3 에서 0.73m
        -4.5, -5.5, -90.0,   # 서쪽 남부 — col_loading_W 남쪽 1.3m
        -3.0, -7.5,   0.0,   # 남서 심층 구석 — 적재/rack 구역
        -1.5, -7.5,   0.0,   # 남부 서측 심층 — crate 이북 0.6m
        -0.5, -5.0,   0.0,   # 남부 중앙 복귀
        -0.5, -2.0,  90.0,   # 북행 복귀
        -2.0,  0.5, 180.0,   # 서측 복귀
    ],
}

def _make_t16_map_readiness(context, *_args, **_kwargs) -> list:
    """leader launch arg 를 읽어 map_readiness_node explore_status_topic 을 설정."""
    skip_explore = LaunchConfiguration('skip_explore').perform(context).lower() == 'true'
    if skip_explore:
        return []
    leader_id = LaunchConfiguration('leader').perform(context)
    return [
        Node(
            package='aip_fleet_autonomous',
            executable='map_readiness_node',
            name='map_readiness',
            output='screen',
            parameters=[{
                'min_known_cells':                 135000,
                'explore_status_topic':            f'/{leader_id}/explore/status',
                'explore_done_fallback_sec':       300.0,
                'explore_done_stabilization_sec':  90.0,
                'stall_timeout_sec':               350.0,
                'stall_min_delta':                 200,
            }],
        ),
    ]


def _load_patrol_plan(path: str) -> dict[str, list[float]]:
    """외부 patrol_plan YAML → 차량별 flat 웨이포인트 dict 변환.

    YAML 형식: vehicle_id → [[x, y, yaw_deg], ...]
    반환 형식: vehicle_id → [x, y, yaw_deg, x, y, yaw_deg, ...]  (patrol_node 입력)
    경로가 빈 문자열이면 빈 dict 반환 (기본 _PATROL_WP 사용).
    """
    if not path:
        return {}
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        import logging
        logging.getLogger('fleet_autonomous').warning(
            f'patrol_plan 파일 없음: {expanded} — 기본 경로 사용')
        return {}
    with open(expanded) as f:
        data = yaml.safe_load(f) or {}
    result: dict[str, list[float]] = {}
    for vid, wps in data.items():
        if not isinstance(wps, list):
            continue
        flat: list[float] = []
        for wp in wps:
            if len(wp) < 3:
                continue
            flat.extend([float(wp[0]), float(wp[1]), float(wp[2])])
        if flat:
            result[vid] = flat
    return result


# peer_N 자율 Nav2 시작 시각 (s).
# peer_3에 8 s 스태거 — AMCL 파티클 스톰 충돌 방지 및 초기화 안정성 확보.
# GUI 모드에서 slam_toolbox가 map TF를 발행하려면 EKF가 충분히 안정화돼야 한다.
# 16s(SLAM 시작) + 24s 여유 = 40s: GUI 물리 초기화 + EKF 시작 시 sim_time 점프 흡수.
_NAV_START_LEADER = 40.0   # peer_1: SLAM 안정화(16s) + 24s 여유 (headless: 22s도 충분)
# peer_2/3 는 follower_trigger_node 가 /fleet/map_ready 수신 시 이벤트 기반 기동


def generate_launch_description() -> LaunchDescription:
    gz_share      = get_package_share_directory('aip_fleet_gazebo')
    nav_share     = get_package_share_directory('aip_fleet_nav')
    auto_share    = get_package_share_directory('aip_fleet_autonomous')
    bringup_share = get_package_share_directory('aip_fleet_bringup')

    ign_fleet_py    = os.path.join(gz_share,   'launch', 'ign_fleet.launch.py')
    slam_leader_py  = os.path.join(nav_share,  'launch', 'slam_leader.launch.py')
    leader_nav_py   = os.path.join(auto_share, 'launch', 'leader_nav.launch.py')
    auto_nav_py     = os.path.join(auto_share, 'launch', 'autonomous_nav.launch.py')
    twist_mux_yaml  = os.path.join(bringup_share, 'config', 'twist_mux_vehicle.yaml')

    gui                  = LaunchConfiguration('gui')
    solo_mapping         = LaunchConfiguration('solo_mapping')
    skip_explore         = LaunchConfiguration('skip_explore')
    with_patrol          = LaunchConfiguration('with_patrol')
    with_peer_obstacles  = LaunchConfiguration('with_peer_obstacles')
    with_coverage        = LaunchConfiguration('with_coverage')
    with_thermal         = LaunchConfiguration('with_thermal')

    actions: list = [
        DeclareLaunchArgument(
            'leader', default_value=_LEADER,
            description='리더 차량 네임스페이스. 시뮬: peer_1 / 실차: aip1'),
        DeclareLaunchArgument(
            'followers', default_value=','.join(_FOLLOWERS),
            description='팔로워 네임스페이스 쉼표 구분. 시뮬: peer_2,peer_3 / 실차: aip2,aip3'),
        DeclareLaunchArgument(
            'gui', default_value='true',
            description='Ignition GUI 표시 여부. headless/CI: false'),
        DeclareLaunchArgument(
            'solo_mapping', default_value='false',
            description=(
                'true: peer_1 단독 매핑 모드. '
                'follower_trigger_node 비활성화 → peer_2/3 스폰 안 함. '
                '매핑 완성도 단독 검증용.'
            )),
        DeclareLaunchArgument(
            'skip_explore', default_value='false',
            description=(
                'true: ~/aip_maps/latest_fleet_map 을 사용해 탐색(explore_lite) 없이 '
                '바로 peer_2/3 를 스폰. 저장된 맵이 있을 때 빠른 재기동에 사용.'
            )),
        DeclareLaunchArgument(
            'rtf', default_value='1.0',
            description='시뮬 배속. 1.0=실시간 / 1.5=1.5배속(권장) / 2.0=2배속(CPU 한계 주의)'),
        DeclareLaunchArgument(
            'with_patrol', default_value='false',
            description=(
                'true: 각 팔로워에 patrol_node 자동 시작 → 웨이포인트 순찰. '
                'false: 수동 목표 입력 대기 (RViz2 / CLI).'
            )),
        DeclareLaunchArgument(
            'with_peer_obstacles', default_value='false',
            description=(
                'true: peer_obstacle_node 실행 → 동료 차량을 가상 장애물로 '
                'Nav2 로컬 코스트맵에 주입하여 다중 로봇 충돌 방지.'
            )),
        DeclareLaunchArgument(
            'with_coverage', default_value='false',
            description=(
                'true: coverage_tracker_node 실행 → 격자 기반 순찰 커버리지 추적. '
                '/fleet/coverage_pct, /fleet/coverage_grid 발행.'
            )),
        DeclareLaunchArgument(
            'with_thermal', default_value='false',
            description=(
                'true: 열화상 시뮬 파이프라인 실행. '
                'scenario_manager_node + sim_thermal_node + patrol_monitor_node × 3. '
                '/sim/set_scenario 토픽으로 시나리오 전환 가능 (NORMAL/FIRE/OVERHEATING 등).'
            )),
        DeclareLaunchArgument(
            'patrol_plan', default_value='',
            description=(
                '순찰 경로 계획 YAML 파일 경로. '
                '지정 시 기본 _PATROL_WP를 덮어씀. '
                'patrol_planner_node로 생성하거나 직접 편집. '
                '형식: vehicle_id → [[x, y, yaw_deg], ...] '
                '예: patrol_plan:=$HOME/aip_maps/patrol_plan.yaml'
            )),

        # ── t=0 s: Ignition 기동, peer_1 스폰 ────────────────────────────────
        # follower_spawn_delay=99999: 타이머 기반 팔로워 스폰 완전 비활성화.
        # 실제 스폰은 follower_trigger_node 가 /fleet/map_ready 수신 후 처리
        # → 매핑 완료 전 차체가 SLAM 맵에 벽으로 기록되는 문제 근본 해결.
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(ign_fleet_py),
            launch_arguments={
                'gui':                  gui,
                'with_static_tf':       'false',
                'follower_spawn_delay': '99999',
                'rtf':                  LaunchConfiguration('rtf'),
            }.items(),
        ),
    ]

    # ── t=14 s: twist_mux × 3 ────────────────────────────────────────────────
    twist_mux_nodes = []
    for vid in _ALL_PEERS:
        twist_mux_nodes.append(
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
    actions.append(TimerAction(period=14.0, actions=twist_mux_nodes))

    # ── t=16 s: sim peer sensing + map_readiness_node + 열화상 시뮬 ──────────────
    # SLAM leader는 t=21s로 분리 — EKF(t=3.5+17=20.5s) 이후에 시작해야
    # peer_1/odom→base_link TF 누락 없이 첫 스캔부터 처리 가능.
    # (SLAM이 EKF보다 먼저 시작하면 transform_timeout=3.0s 재시도가 4.5s 지속
    #  → 최초 스캔 처리가 늦어져 Nav2 시작(t=40s)까지 유효 매핑 시간 감소.)
    actions.append(
        TimerAction(
            period=16.0,
            actions=[
                # 맵 커버리지 모니터 — /fleet/map_ready 발행 (follower_trigger_node 가 구독)
                # skip_explore:=true 시 비활성화 — map_ready 는 별도 타이머로 발행.
                # explore_status_topic 은 leader launch arg 에서 읽어야 하므로 OpaqueFunction.
                OpaqueFunction(function=_make_t16_map_readiness),
                Node(
                    package='aip_fleet_gazebo',
                    executable='sim_peer_sensing_node.py',
                    name='sim_peer_sensing',
                    output='screen',
                    parameters=[{
                        'use_sim_time':         True,
                        'vehicle_ids':          _ALL_PEERS,
                        'range_noise_stddev_m': 0.05,
                        'max_range_m':          10.0,
                        'publish_hz':           10.0,
                    }],
                ),
                # ── 시뮬 heartbeat 더미 퍼블리셔 ─────────────────────────────
                # 실제 차량은 자체 SW가 heartbeat를 발행하지만 시뮬에는 없음.
                # 이 노드가 대신 발행하여 supervisor/대시보드에서 ONLINE 표시.
                Node(
                    package='aip_fleet_gazebo',
                    executable='sim_heartbeat_node.py',
                    name='sim_heartbeat',
                    output='screen',
                    parameters=[{
                        'use_sim_time': False,
                        'vehicle_ids':  _ALL_PEERS,
                        'publish_hz':   2.0,
                    }],
                ),
                # ── 시뮬 차량 위치 릴레이 ────────────────────────────────────
                # /tf (VOLATILE) 는 DDS 세션 경계를 넘지 않으므로 중앙 대시보드가
                # 직접 TF 조회 불가. 이 노드가 시뮬 세션 내에서 TF를 읽어
                # TRANSIENT_LOCAL /fleet/peer_poses 로 재발행 → 대시보드 수신.
                Node(
                    package='aip_fleet_gazebo',
                    executable='sim_pose_relay_node.py',
                    name='sim_pose_relay',
                    output='screen',
                    parameters=[{
                        'use_sim_time': True,
                        'vehicle_ids':  _ALL_PEERS,
                        'publish_hz':   2.0,
                    }],
                ),
                # ── 순찰 경로 계획 도구 (항상 실행) ──────────────────────────
                # Foxglove 패널·Web 대시보드에서 /patrol_planner/cmd 수신
                # /patrol_planner/plan_state 발행으로 UI 양방향 동기화
                Node(
                    package='aip_fleet_autonomous',
                    executable='patrol_planner_node',
                    name='patrol_planner',
                    output='screen',
                    parameters=[{
                        'output_path':    os.path.expanduser('~/aip_maps/patrol_plan.yaml'),
                        'active_vehicle': 'peer_1',
                        'vehicle_ids':    ','.join(_ALL_PEERS),
                        'row_spacing_m':  2.0,
                        'sweep_heading':  0.0,
                    }],
                ),
                # ── 열화상 시뮬 (with_thermal:=true) ─────────────────────────
                # scenario_manager: /sim/set_scenario → 활성 열원 목록 발행
                # sim_thermal:      TF + 열원 목록 → 각 차량 thermal_raw 발행
                Node(
                    package='aip_fleet_gazebo',
                    executable='scenario_manager_node.py',
                    name='scenario_manager',
                    output='screen',
                    condition=IfCondition(with_thermal),
                    parameters=[{'use_sim_time': True}],
                ),
                Node(
                    package='aip_fleet_gazebo',
                    executable='sim_thermal_node.py',
                    name='sim_thermal',
                    output='screen',
                    condition=IfCondition(with_thermal),
                    parameters=[{
                        'use_sim_time': True,
                        'vehicle_ids':  _ALL_PEERS,
                        'publish_hz':   8.0,
                    }],
                ),
                # 금지구역 → costmap obstacle 주입 노드 (단일 글로벌)
                Node(
                    package='aip_fleet_autonomous',
                    executable='keepout_zone_node',
                    name='keepout_zone_node',
                    output='screen',
                    parameters=[{'use_sim_time': True}],
                ),
            ],
        )
    )

    # ── t=21 s: SLAM leader ─────────────────────────────────────────────────────
    # EKF(t=20.5s) 시작 후 0.5s에 slam_toolbox 시작 → peer_1/odom→base_link TF 즉시 조회 가능.
    # Nav2(t=40s)까지 19s 유효 매핑 시간 확보 (기존 4.5s TF 대기로 실질 19.5s와 동등).
    actions.append(
        TimerAction(
            period=21.0,
            actions=[
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(slam_leader_py),
                    launch_arguments={
                        'vehicle_id': _LEADER,
                        'rtf':        LaunchConfiguration('rtf'),
                    }.items(),
                ),
            ],
        )
    )

    # ── t=22 s: patrol_monitor × 3 (with_thermal:=true) ─────────────────────
    # peer_1 TF 가 slam_toolbox 에서 발행되는 시각 이후 시작.
    # peer_2/3 는 AMCL 시작 전이라 map→peer_N/base_link TF 없음 →
    # _estimate_map_position 에서 TF miss → map_position=(0,0,0) 로 graceful 처리.
    # AMCL 이 활성화(t≈155/163s)되면 자동으로 올바른 위치 추정 시작.
    thermal_monitor_nodes = []
    for vid in _ALL_PEERS:
        thermal_monitor_nodes.append(
            Node(
                package='aip_fleet_perception',
                executable='patrol_monitor_node',
                name=f'patrol_monitor_{vid}',
                output='screen',
                condition=IfCondition(with_thermal),
                parameters=[{
                    'use_sim_time':                   True,
                    'vehicle_id':                     vid,
                    'estimated_hotspot_distance_m':   3.0,
                }],
            )
        )
    # alert_visualizer: /fleet/alerts → /fleet/alert_markers (RViz MarkerArray)
    thermal_monitor_nodes.append(
        Node(
            package='aip_fleet_perception',
            executable='alert_visualizer_node',
            name='alert_visualizer',
            output='screen',
            condition=IfCondition(with_thermal),
            parameters=[{
                'use_sim_time': True,
                'vehicle_ids':  _ALL_PEERS,
            }],
        )
    )
    actions.append(TimerAction(period=22.0, actions=thermal_monitor_nodes))

    # ── t=18 s: peer_obstacle_node (선택 — with_peer_obstacles:=true) ─────────
    # TF 가 안정화된 직후 시작. Nav2 로컬 코스트맵의 peer_obstacles 소스 구독.
    actions.append(
        TimerAction(
            period=18.0,
            actions=[
                Node(
                    package='aip_fleet_gazebo',
                    executable='peer_obstacle_node.py',
                    name='peer_obstacle_node',
                    output='screen',
                    condition=IfCondition(with_peer_obstacles),
                    parameters=[{
                        'vehicle_ids':  ','.join(_ALL_PEERS),
                        'map_frame':    'map',
                        'publish_hz':    5.0,
                        'robot_radius':  0.30,
                        'ring_points':  12,
                    }],
                ),
            ],
        )
    )

    # ── t=70 s: coverage_tracker_node (선택 — with_coverage:=true) ───────────
    # Nav2 맵(/map) 수신 후 시작. peer_2, peer_3 오도메트리 구독.
    actions.append(
        TimerAction(
            period=70.0,
            actions=[
                Node(
                    package='aip_fleet_gazebo',
                    executable='coverage_tracker_node.py',
                    name='coverage_tracker',
                    output='screen',
                    condition=IfCondition(with_coverage),
                    parameters=[{
                        'vehicle_ids':    ','.join(_FOLLOWERS),
                        'visit_radius_m':  0.30,
                        'publish_hz':      1.0,
                    }],
                ),
            ],
        )
    )

    # ── t=40 s: peer_1 Nav2 (leader_nav) ──────────────────────────────────────────
    # slam_toolbox(t=21s) 시작 후 19s 후 → map→peer_1/odom TF 안정화 후 Nav2 기동.
    # AMCL 없음 — slam_toolbox가 map→odom TF 직접 담당.
    # t=50s: follower_trigger_node (map_ready 5s 선행 구독)
    # t=60s: explore_lite (lifecycle 활성화 20s 여유)
    # 의존성: sudo apt install ros-humble-explore-lite
    actions.append(
        TimerAction(
            period=_NAV_START_LEADER,
            actions=[
                # peer_1 Nav2 플래너/컨트롤러/BT (slam_toolbox가 map→odom TF 담당)
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(leader_nav_py),
                    launch_arguments={
                        'vehicle_id': _LEADER,
                        'rtf':        LaunchConfiguration('rtf'),
                    }.items(),
                ),
            ],
        )
    )
    # ── t=50s: follower_trigger_node — map_ready 구독 대기 ──────────────────────
    # skip_explore=true:  map_ready가 t=55s에 1회 발행 후 즉시 종료되므로
    #                     구독자가 먼저 준비돼 있어야 메시지를 받을 수 있음.
    # skip_explore=false: map_readiness_node가 TRANSIENT_LOCAL 지속 발행자이므로
    #                     늦게 구독해도 받을 수 있지만, t=50s 선행 시작도 무해함.
    # patrol_plan이 제공되면 런치 시점에 YAML을 읽어 _PATROL_WP를 덮어씀.
    def _make_follower_trigger(context, *args, **kwargs):
        leader_id   = LaunchConfiguration('leader').perform(context)
        follower_str = LaunchConfiguration('followers').perform(context)
        follower_ids = [v.strip() for v in follower_str.split(',') if v.strip()]
        all_ids      = [leader_id] + follower_ids

        patrol_plan_path = LaunchConfiguration('patrol_plan').perform(context)
        wps = _PATROL_WP.copy()
        loaded = _load_patrol_plan(patrol_plan_path)
        wps.update(loaded)   # 외부 YAML이 기본값을 덮어씀 (없는 차량은 기본값 유지)

        params: dict = {
            'use_sim_time':       True,
            'leader':             leader_id,
            'follower_ids':       follower_str,
            'spawn_in_gazebo':    True,
            'with_patrol':        LaunchConfiguration('with_patrol').perform(context) == 'true',
            'skip_explore':       LaunchConfiguration('skip_explore').perform(context) == 'true',
            'patrol_start_delay': 60.0,
        }
        # aip_N → peer_N 폴백 매핑: 실차 ID에 _PATROL_WP가 없으면 인덱스 대응 시뮬 경로 사용.
        # 예) aip1→peer_1, aip2→peer_2, aip3→peer_3. patrol_plan YAML 지정이 우선.
        _aip_to_peer = {
            f'aip{i}': f'peer_{i}' for i in range(1, 10)
        }

        # 차량별 웨이포인트: vehicle_id 독립적 파라미터명
        for vid in all_ids:
            wp = wps.get(vid)
            if wp is None:
                peer_equiv = _aip_to_peer.get(vid)
                wp = _PATROL_WP.get(vid) or (
                    _PATROL_WP.get(peer_equiv) if peer_equiv else None
                )
            if wp is None:
                import logging
                logging.getLogger('fleet_autonomous').warning(
                    f'웨이포인트 없음: {vid} (patrol_plan YAML 로 제공하거나 '
                    f'waypoints_{vid} launch arg 를 지정하세요)'
                )
                wp = [0.0, 0.0, 0.0]
            params[f'waypoints_{vid}'] = wp
        # Gazebo 스폰 좌표: 알려진 위치 우선, 없으면 원점
        for vid in follower_ids:
            sx, sy, syaw = _SPAWN_POS.get(vid, (0.0, 0.0, 0.0))
            params[f'spawn_x_{vid}']   = sx
            params[f'spawn_y_{vid}']   = sy
            params[f'spawn_yaw_{vid}'] = syaw
        if loaded:
            import logging
            logging.getLogger('fleet_autonomous').info(
                f'외부 순찰 계획 로드: {patrol_plan_path} '
                f'(차량: {list(loaded.keys())})')
        return [
            Node(
                package='aip_fleet_autonomous',
                executable='follower_trigger_node',
                name='follower_trigger',
                output='screen',
                condition=UnlessCondition(LaunchConfiguration('solo_mapping')),
                parameters=[params],
            ),
        ]

    actions.append(
        TimerAction(
            period=_NAV_START_LEADER + 10.0,   # t=50s — map_ready 발행(t=55s) 보다 5s 앞서 구독
            actions=[OpaqueFunction(function=_make_follower_trigger)],
        )
    )

    # ── t=60s: explore_lite (자율 프론티어 탐색) ─────────────────────────────────
    # leader_nav와 동시 시작 시 bt_navigator INACTIVE → goal REJECTED →
    # 모든 frontier 즉시 "tried" 처리 → 탐색 종료 버그.
    # lifecycle_manager 활성화(~15s) 후 시작하려면 t=40+20=60s 필요.
    actions.append(
        TimerAction(
            period=_NAV_START_LEADER + 20.0,   # lifecycle 활성화 여유 20s 추가
            actions=[
                Node(
                    package='explore_lite',
                    executable='explore',
                    name='explore',
                    namespace=_LEADER,
                    output='screen',
                    condition=UnlessCondition(skip_explore),
                    parameters=[{
                        'use_sim_time':           True,
                        'robot_base_frame':        f'{_LEADER}/base_link',
                        'costmap_topic':           '/map',
                        'costmap_updates_topic':   '/map_updates',
                        'visualize':               True,
                        'return_to_init':           False,
                        'planner_frequency':        0.33,
                        'progress_timeout':        30.0,   # 60→30s: 고착 frontier 빠른 포기
                        'potential_scale':          0.003,
                        'orientation_scale':        0.0,
                        'gain_scale':               1.0,
                        'transform_tolerance':      4.0,
                        'min_frontier_size':        0.75,  # 0.5→0.75m: 코너 소형 frontier 제외
                        'blacklist_ttl':            120.0,
                        'blacklist_abort_ttl':      300.0,
                        'max_blacklist_retries':    2,
                        'goal_continuity_scale':    0.0,
                    }],
                ),
            ],
        )
    )

    # ── skip_explore:=true: t=55s에 /fleet/map_ready 발행 ────────────────────────
    # follower_trigger_node가 t=50s에 이미 구독 중이므로 메시지를 수신할 수 있음.
    # ros2 topic pub --once는 발행 후 즉시 종료 → follower_trigger가 먼저 구독해야 함.
    actions.append(
        TimerAction(
            period=_NAV_START_LEADER + 15.0,
            actions=[
                ExecuteProcess(
                    cmd=[
                        'ros2', 'topic', 'pub', '--once',
                        '--qos-durability', 'transient_local',
                        '--qos-reliability', 'reliable',
                        '/fleet/map_ready',
                        'std_msgs/msg/Bool',
                        '{data: true}',
                    ],
                    condition=IfCondition(skip_explore),
                    output='screen',
                ),
            ],
        )
    )

    # 팔로워 Nav2 기동은 follower_trigger_node 가 /fleet/map_ready 수신 시 처리.
    # (이 파일에서 타이머 기반 TimerAction 불필요)

    return LaunchDescription(actions)
