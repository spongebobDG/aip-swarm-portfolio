#!/usr/bin/env python3
"""patrol_planner_node.py — 실배치용 순찰 경로 계획 도구.

두 가지 설계 방식:
  1. 웨이포인트 모드: RViz "2D Goal Pose" 클릭 → 순서대로 웨이포인트 기록
  2. 커버리지 모드:  RViz "Publish Point" 클릭 → 폴리곤 꼭짓점 정의
                     → generate_coverage 명령으로 잔디깎기(boustrophedon) 경로 자동 생성

워크플로:
  1. 맵 서버 기동 (맵 파일이 있을 경우):
       ros2 run nav2_map_server map_server --ros-args \\
           -p yaml_filename:=$HOME/aip_maps/latest_fleet_map/map.yaml \\
           -p use_sim_time:=false
     또는 시뮬 실행 중이라면 /map_static 이 이미 발행 중.
  2. 계획 노드 기동:
       ros2 run aip_fleet_autonomous patrol_planner_node --ros-args \\
           -p output_path:=$HOME/aip_maps/patrol_plan.yaml \\
           -p active_vehicle:=peer_1
  3. RViz2 실행 후 /patrol_planner/preview 표시 추가.

명령 (ros2 topic pub --once /patrol_planner/cmd std_msgs/String '{data: "..."}'):
  switch:<vehicle>        편집 대상 차량 변경  ex) switch:peer_2
  mode:waypoints          웨이포인트 직접 입력 모드 (기본)
  mode:coverage           커버리지 폴리곤 입력 모드
  generate_coverage [sp]  폴리곤 → 잔디깎기 경로 변환 (sp=행 간격 m, 기본 2.0)
  heading:<deg>           커버리지 스윕 방향 변경 (0=동쪽, 90=북쪽)
  undo                    마지막 포인트 제거
  clear                   현재 차량 전체 초기화
  clear_all               모든 차량 초기화
  save                    output_path 에 YAML 저장
  load:<path>             기존 YAML 로드

파라미터:
  active_vehicle   str    편집 대상 차량 ID (기본: peer_1)
  output_path      str    저장 YAML 경로 (기본: ~/aip_maps/patrol_plan.yaml)
  row_spacing_m    float  커버리지 행 간격 m (기본: 2.0)
  sweep_heading    float  커버리지 스윕 방향 도 (기본: 0.0 = 동쪽)
  vehicle_ids      str    쉼표 구분 차량 목록 (기본: peer_1,peer_2,peer_3)
"""
import json
import math
import os
import yaml

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from geometry_msgs.msg import PointStamped, PoseStamped, Point, Vector3
from nav_msgs.msg import OccupancyGrid
from std_msgs.msg import ColorRGBA, String
from visualization_msgs.msg import Marker, MarkerArray

# 차량별 색상 (patrol_node 와 통일)
_VIZ_COLORS = {
    'peer_1': (0.2, 0.85, 0.2),
    'peer_2': (0.2, 0.6,  1.0),
    'peer_3': (1.0, 0.55, 0.1),
}
_DEFAULT_COLOR = (0.8, 0.8, 0.8)

_TRANSIENT_QOS = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)


# ── 커버리지 알고리즘 (외부 의존성 없음) ─────────────────────────────────────

def _boustrophedon(polygon_pts: list[tuple[float, float]],
                   row_spacing_m: float,
                   sweep_heading_deg: float = 0.0
                   ) -> list[tuple[float, float, float]]:
    """폴리곤 내부를 잔디깎기(boustrophedon) 패턴으로 커버하는 웨이포인트 생성.

    Args:
        polygon_pts:      폴리곤 꼭짓점 리스트 [(x, y), …]
        row_spacing_m:    행 간격 (m)
        sweep_heading_deg: 주행 방향 (0=동쪽, 90=북쪽)

    Returns:
        [(x, y, yaw_rad), …]  — map 프레임 웨이포인트
    """
    if len(polygon_pts) < 3:
        return []

    a = math.radians(sweep_heading_deg)

    def rot(x, y, angle):
        c, s = math.cos(angle), math.sin(angle)
        return c * x - s * y, s * x + c * y

    # 폴리곤을 스윕 방향이 +x 축이 되도록 회전
    rotated = [rot(x, y, -a) for x, y in polygon_pts]
    n = len(rotated)

    miny = min(p[1] for p in rotated)
    maxy = max(p[1] for p in rotated)

    row_pts: list[tuple[float, float]] = []
    row_idx = 0
    scan_y = miny + row_spacing_m / 2.0

    while scan_y <= maxy:
        xs = []
        for i in range(n):
            x1, y1 = rotated[i]
            x2, y2 = rotated[(i + 1) % n]
            if (y1 < scan_y <= y2) or (y2 < scan_y <= y1):
                t = (scan_y - y1) / (y2 - y1)
                xs.append(x1 + t * (x2 - x1))

        if len(xs) >= 2:
            xs.sort()
            seg = [(xs[0], scan_y), (xs[-1], scan_y)]
            if row_idx % 2 == 1:
                seg = seg[::-1]
            row_pts.extend(seg)

        scan_y += row_spacing_m
        row_idx += 1

    if not row_pts:
        return []

    # 회전 복원 + yaw 계산
    result: list[tuple[float, float, float]] = []
    for i, (rx, ry) in enumerate(row_pts):
        x, y = rot(rx, ry, a)
        if i + 1 < len(row_pts):
            nrx, nry = row_pts[i + 1]
            nx, ny = rot(nrx, nry, a)
            yaw = math.atan2(ny - y, nx - x)
        else:
            yaw = result[-1][2] if result else math.radians(sweep_heading_deg)
        result.append((x, y, yaw))

    return result


# ── 노드 ────────────────────────────────────────────────────────────────────

class PatrolPlannerNode(Node):
    def __init__(self):
        super().__init__('patrol_planner')

        self.declare_parameter('active_vehicle', 'peer_1')
        self.declare_parameter('output_path',
                               os.path.expanduser('~/aip_maps/patrol_plan.yaml'))
        self.declare_parameter('row_spacing_m',  2.0)
        self.declare_parameter('sweep_heading',  0.0)
        self.declare_parameter('vehicle_ids',    'peer_1,peer_2,peer_3')

        self._active  = self.get_parameter('active_vehicle').value
        self._out     = os.path.expanduser(
            self.get_parameter('output_path').value)
        self._spacing = float(self.get_parameter('row_spacing_m').value)
        self._heading = float(self.get_parameter('sweep_heading').value)
        vids_str      = self.get_parameter('vehicle_ids').value
        self._vids    = [v.strip() for v in vids_str.split(',')]

        # vehicle_id → [(x,y,yaw_rad), …] (내부 저장 단위: 라디안)
        self._waypoints: dict[str, list[tuple[float, float, float]]] = {
            v: [] for v in self._vids
        }
        # coverage 모드: 폴리곤 꼭짓점
        self._polygon: list[tuple[float, float]] = []
        self._mode = 'waypoints'  # 'waypoints' | 'coverage'

        # 퍼블리셔
        self._prev_pub = self.create_publisher(
            MarkerArray, '/patrol_planner/preview', _TRANSIENT_QOS)
        self._state_pub = self.create_publisher(
            String, '/patrol_planner/plan_state', _TRANSIENT_QOS)

        # OccupancyGrid 캐시 (장애물 필터링용)
        self._occ_grid: OccupancyGrid | None = None

        # 구독
        self.create_subscription(PoseStamped, '/goal_pose',
                                 self._on_goal_pose, 10)
        self.create_subscription(PointStamped, '/clicked_point',
                                 self._on_clicked_point, 10)
        self.create_subscription(String, '/patrol_planner/cmd',
                                 self._on_cmd, 10)
        # /map 구독 (SLAM2D가 발행하는 지도 — TRANSIENT_LOCAL latched)
        self.create_subscription(OccupancyGrid, '/map',
                                 self._cb_occ_grid, _TRANSIENT_QOS)
        for _ns in self._vids:
            self.create_subscription(OccupancyGrid, f'/{_ns}/map',
                                     self._cb_occ_grid, _TRANSIENT_QOS)

        self.get_logger().info(
            f'patrol_planner 시작: 차량={self._active}, 모드={self._mode}\n'
            f'  저장 경로: {self._out}\n'
            f'  명령 토픽: /patrol_planner/cmd\n'
            f'  웨이포인트: RViz "2D Goal Pose" 클릭\n'
            f'  커버리지 폴리곤: mode:coverage 후 "Publish Point" 클릭'
        )
        self._publish_preview()
        self._publish_plan_state()

    # ── 입력 핸들러 ──────────────────────────────────────────────────────────

    def _on_goal_pose(self, msg: PoseStamped):
        """RViz "2D Goal Pose" → 웨이포인트 추가 (waypoints 모드에서만)."""
        if self._mode != 'waypoints':
            self.get_logger().warn(
                'goal_pose 수신 무시 — 현재 모드: coverage. '
                '"mode:waypoints" 명령으로 전환하세요.')
            return
        x = msg.pose.position.x
        y = msg.pose.position.y
        q = msg.pose.orientation
        yaw = math.atan2(2*(q.w*q.z + q.x*q.y),
                         1 - 2*(q.y*q.y + q.z*q.z))
        self._waypoints[self._active].append((x, y, yaw))
        n = len(self._waypoints[self._active])
        self.get_logger().info(
            f'[{self._active}] 웨이포인트 {n} 추가: '
            f'({x:.2f}, {y:.2f}, {math.degrees(yaw):.0f}°)')
        self._publish_preview()
        self._publish_plan_state()

    def _on_clicked_point(self, msg: PointStamped):
        """RViz "Publish Point" → 폴리곤 꼭짓점 추가 (coverage 모드에서만)."""
        if self._mode != 'coverage':
            self.get_logger().warn(
                'clicked_point 수신 무시 — 현재 모드: waypoints. '
                '"mode:coverage" 명령으로 전환하세요.')
            return
        x, y = msg.point.x, msg.point.y
        self._polygon.append((x, y))
        self.get_logger().info(
            f'[{self._active}] 폴리곤 꼭짓점 {len(self._polygon)} 추가: '
            f'({x:.2f}, {y:.2f})')
        self._publish_preview()
        self._publish_plan_state()

    def _on_cmd(self, msg: String):
        cmd = msg.data.strip()
        self.get_logger().info(f'명령 수신: {cmd}')

        if cmd.startswith('switch:'):
            vid = cmd[7:]
            if vid in self._vids:
                self._active = vid
                self._polygon.clear()
                self.get_logger().info(f'활성 차량 → {vid}')
            else:
                self.get_logger().error(f'알 수 없는 차량: {vid}')

        elif cmd.startswith('mode:'):
            m = cmd[5:]
            if m in ('waypoints', 'coverage'):
                self._mode = m
                self._polygon.clear()
                self.get_logger().info(f'모드 → {m}')
            else:
                self.get_logger().error(f'알 수 없는 모드: {m}')

        elif cmd.startswith('heading:'):
            try:
                self._heading = float(cmd[8:])
                self.get_logger().info(f'스윕 방향 → {self._heading}°')
            except ValueError:
                self.get_logger().error('heading 값이 올바르지 않음')

        elif cmd.startswith('generate_coverage'):
            parts = cmd.split()
            spacing = float(parts[1]) if len(parts) > 1 else self._spacing
            self._generate_coverage(spacing)

        elif cmd == 'undo':
            if self._mode == 'waypoints' and self._waypoints[self._active]:
                removed = self._waypoints[self._active].pop()
                self.get_logger().info(
                    f'[{self._active}] 마지막 웨이포인트 제거: '
                    f'({removed[0]:.2f}, {removed[1]:.2f})')
            elif self._mode == 'coverage' and self._polygon:
                removed = self._polygon.pop()
                self.get_logger().info(f'폴리곤 꼭짓점 제거: {removed}')

        elif cmd == 'clear':
            self._waypoints[self._active].clear()
            self._polygon.clear()
            self.get_logger().info(f'[{self._active}] 초기화')

        elif cmd == 'clear_all':
            for v in self._vids:
                self._waypoints[v].clear()
            self._polygon.clear()
            self.get_logger().info('모든 차량 초기화')

        elif cmd == 'save':
            self._save()

        elif cmd.startswith('load:'):
            path = os.path.expanduser(cmd[5:])
            self._load(path)

        elif cmd.startswith('set_wp_list:'):
            # 형식: set_wp_list:<vid>:<x1,y1,yaw1_deg>;<x2,y2,yaw2_deg>;...
            rest = cmd[12:]
            colon = rest.find(':')
            if colon >= 0:
                vid = rest[:colon]
                wps_str = rest[colon + 1:].strip()
                if vid in self._vids:
                    if wps_str:
                        wps = []
                        for seg in wps_str.split(';'):
                            vals = [v.strip() for v in seg.split(',')]
                            if len(vals) >= 3:
                                wps.append((float(vals[0]), float(vals[1]),
                                            math.radians(float(vals[2]))))
                        self._waypoints[vid] = wps
                    else:
                        self._waypoints[vid] = []
                    self.get_logger().info(
                        f'[{vid}] 웨이포인트 일괄 설정: {len(self._waypoints[vid])}개')

        elif cmd.startswith('set_coverage_polygon:'):
            # 형식: set_coverage_polygon:<vid>:<spacing_m>:<heading_deg>:<x1,y1>;<x2,y2>;...
            rest = cmd[len('set_coverage_polygon:'):]
            parts = rest.split(':', 3)
            if len(parts) >= 4:
                try:
                    vid, spacing_s, heading_s, pts_str = parts
                    spacing = float(spacing_s)
                    heading = float(heading_s)
                    polygon = []
                    for seg in pts_str.split(';'):
                        vals = [v.strip() for v in seg.split(',')]
                        if len(vals) >= 2:
                            polygon.append((float(vals[0]), float(vals[1])))
                    if vid in self._vids and len(polygon) >= 3:
                        wps = _boustrophedon(polygon, spacing, heading)
                        before = len(wps)
                        wps = [wp for wp in wps if self._is_free(wp[0], wp[1])]
                        if wps:
                            self._waypoints[vid] = list(wps)
                            self._mode = 'waypoints'
                            self.get_logger().info(
                                f'[{vid}] 커버리지 폴리곤 → {len(wps)}개 웨이포인트 '
                                f'(간격={spacing}m, 방향={heading}°, 꼭짓점={len(polygon)}개'
                                + (f', 장애물 제거={before-len(wps)}개' if self._occ_grid else '') + ')')
                        else:
                            self.get_logger().error(f'[{vid}] 커버리지 생성 실패 — 폴리곤 확인 필요')
                    else:
                        self.get_logger().error(
                            f'set_coverage_polygon 오류: vid={vid!r} 미등록 또는 꼭짓점 부족 ({len(polygon)}개)')
                except (ValueError, IndexError) as e:
                    self.get_logger().error(f'set_coverage_polygon 파싱 오류: {e}')

        elif cmd.startswith('coverage_box:'):
            # 형식: coverage_box:<vid>:<x1,y1>:<x2,y2>:<spacing>:<heading_deg>
            parts = cmd[13:].split(':')
            if len(parts) >= 5:
                vid = parts[0]
                xy1 = [float(v) for v in parts[1].split(',')]
                xy2 = [float(v) for v in parts[2].split(',')]
                spacing = float(parts[3])
                heading = float(parts[4])
                x1, y1, x2, y2 = xy1[0], xy1[1], xy2[0], xy2[1]
                poly = [
                    (min(x1, x2), min(y1, y2)),
                    (max(x1, x2), min(y1, y2)),
                    (max(x1, x2), max(y1, y2)),
                    (min(x1, x2), max(y1, y2)),
                ]
                wps = _boustrophedon(poly, spacing, heading)
                before = len(wps)
                wps = [wp for wp in wps if self._is_free(wp[0], wp[1])]
                if vid in self._vids and wps:
                    self._waypoints[vid] = list(wps)
                    self._mode = 'waypoints'
                    self.get_logger().info(
                        f'[{vid}] 커버리지 박스 생성: {len(wps)}개 웨이포인트 '
                        f'(간격={spacing}m, 방향={heading}°'
                        + (f', 장애물 제거={before-len(wps)}개' if self._occ_grid else '') + ')')

        else:
            self.get_logger().warn(f'알 수 없는 명령: {cmd}')

        self._publish_preview()
        self._publish_plan_state()

    # ── OccupancyGrid 장애물 필터링 ─────────────────────────────────────────

    def _cb_occ_grid(self, msg: OccupancyGrid):
        self._occ_grid = msg
        self.get_logger().debug(
            f'OccupancyGrid 수신: {msg.info.width}×{msg.info.height} '
            f'(해상도={msg.info.resolution:.3f}m/cell, 프레임={msg.header.frame_id})')

    def _is_free(self, wx: float, wy: float, inflation_cells: int = 1) -> bool:
        """월드 좌표 (wx, wy) 가 OccupancyGrid 상에서 자유 공간인지 검사.

        셀값 ≥ 65 를 장애물로 판정. inflation_cells 반경 내 임의 셀이 장애물이면 False.
        맵이 없으면 True (필터 비활성).
        """
        g = self._occ_grid
        if g is None:
            return True
        info = g.info
        res  = info.resolution
        if res <= 0:
            return True
        ox = info.origin.position.x
        oy = info.origin.position.y
        cx = int((wx - ox) / res)
        cy = int((wy - oy) / res)
        for dy in range(-inflation_cells, inflation_cells + 1):
            for dx in range(-inflation_cells, inflation_cells + 1):
                ix, iy = cx + dx, cy + dy
                if ix < 0 or iy < 0 or ix >= info.width or iy >= info.height:
                    continue
                val = g.data[iy * info.width + ix]
                if val >= 65:
                    return False
        return True

    # ── 커버리지 생성 ────────────────────────────────────────────────────────

    def _generate_coverage(self, spacing: float):
        if len(self._polygon) < 3:
            self.get_logger().error(
                f'폴리곤 꼭짓점이 {len(self._polygon)}개뿐 — 최소 3개 필요')
            return
        wps = _boustrophedon(self._polygon, spacing, self._heading)
        if not wps:
            self.get_logger().error('커버리지 생성 실패 — 폴리곤을 확인하세요')
            return
        before = len(wps)
        wps = [wp for wp in wps if self._is_free(wp[0], wp[1])]
        if not wps:
            self.get_logger().error('커버리지 생성 실패 — 장애물 필터 후 웨이포인트 없음')
            return
        self._waypoints[self._active] = list(wps)
        self._mode = 'waypoints'   # 생성 후 웨이포인트 모드로 전환
        self.get_logger().info(
            f'[{self._active}] 커버리지 생성 완료: {len(wps)}개 웨이포인트 '
            f'(간격={spacing}m, 방향={self._heading}°'
            + (f', 장애물 제거={before-len(wps)}개' if self._occ_grid else '') + ')')

    # ── 저장 / 로드 ──────────────────────────────────────────────────────────

    def _save(self):
        os.makedirs(os.path.dirname(self._out) if os.path.dirname(self._out)
                    else '.', exist_ok=True)
        plan = {}
        for vid in self._vids:
            wps = self._waypoints[vid]
            if wps:
                plan[vid] = [
                    [round(x, 4), round(y, 4), round(math.degrees(yaw), 2)]
                    for x, y, yaw in wps
                ]
        with open(self._out, 'w') as f:
            f.write(
                '# AIP Fleet 순찰 경로 계획\n'
                '# patrol_planner_node으로 생성. 직접 편집 가능.\n'
                '# 형식: vehicle_id → [[x, y, yaw_deg], ...]\n'
                '# fleet_autonomous.launch.py에서 patrol_plan:=<이 파일 경로> 로 사용.\n\n'
            )
            yaml.dump(plan, f, default_flow_style=None, allow_unicode=True)
        total = sum(len(v) for v in plan.values())
        self.get_logger().info(
            f'저장 완료: {self._out} '
            f'(차량 {len(plan)}대, 총 {total}개 웨이포인트)')

    def _load(self, path: str):
        if not os.path.exists(path):
            self.get_logger().error(f'파일 없음: {path}')
            return
        with open(path) as f:
            data = yaml.safe_load(f)
        for vid, wps in (data or {}).items():
            if vid not in self._vids:
                continue
            self._waypoints[vid] = [
                (float(wp[0]), float(wp[1]), math.radians(float(wp[2])))
                for wp in wps
            ]
        self.get_logger().info(
            f'로드 완료: {path} '
            f'(차량: {list(data.keys() if data else [])})')

    # ── 상태 발행 (UI 동기화) ────────────────────────────────────────────────

    def _publish_plan_state(self):
        """현재 순찰 계획 상태를 JSON으로 발행 — Foxglove 패널·대시보드 동기화."""
        vehicles = {}
        for vid in self._vids:
            vehicles[vid] = [
                [round(x, 3), round(y, 3), round(math.degrees(yaw), 1)]
                for x, y, yaw in self._waypoints[vid]
            ]
        payload = {
            'vehicles': vehicles,
            'active': self._active,
            'mode': self._mode,
            'polygon': [[round(x, 3), round(y, 3)] for x, y in self._polygon],
        }
        self._state_pub.publish(String(data=json.dumps(payload)))

    # ── 시각화 ───────────────────────────────────────────────────────────────

    def _publish_preview(self):
        ma = MarkerArray()
        now = self.get_clock().now().to_msg()

        # 모든 차량 순찰 경로
        for vid in self._vids:
            r, g, b = _VIZ_COLORS.get(vid, _DEFAULT_COLOR)
            wps = self._waypoints[vid]
            active = (vid == self._active)

            # 경로 선
            if len(wps) >= 2:
                line = Marker()
                line.header.frame_id = 'map'
                line.header.stamp = now
                line.ns = f'{vid}_route'
                line.id = 0
                line.type = Marker.LINE_STRIP
                line.action = Marker.ADD
                line.scale = Vector3(x=0.08 if active else 0.05, y=0.0, z=0.0)
                line.color = ColorRGBA(r=r, g=g, b=b,
                                       a=0.9 if active else 0.5)
                line.lifetime.sec = 0
                for x, y, _ in wps:
                    line.points.append(Point(x=x, y=y, z=0.05))
                # 루프 닫힘
                x0, y0, _ = wps[0]
                line.points.append(Point(x=x0, y=y0, z=0.05))
                ma.markers.append(line)

            # 웨이포인트 구체 + 번호
            for i, (x, y, _) in enumerate(wps):
                sph = Marker()
                sph.header.frame_id = 'map'
                sph.header.stamp = now
                sph.ns = f'{vid}_pts'
                sph.id = i
                sph.type = Marker.SPHERE
                sph.action = Marker.ADD
                sph.pose.position = Point(x=x, y=y, z=0.10)
                sph.pose.orientation.w = 1.0
                sph.scale = Vector3(x=0.20, y=0.20, z=0.20)
                sph.color = ColorRGBA(r=r, g=g, b=b,
                                      a=0.8 if active else 0.4)
                sph.lifetime.sec = 0
                ma.markers.append(sph)

                txt = Marker()
                txt.header.frame_id = 'map'
                txt.header.stamp = now
                txt.ns = f'{vid}_nums'
                txt.id = i
                txt.type = Marker.TEXT_VIEW_FACING
                txt.action = Marker.ADD
                txt.pose.position = Point(x=x, y=y, z=0.45)
                txt.pose.orientation.w = 1.0
                txt.scale.z = 0.25
                txt.color = ColorRGBA(r=1.0, g=1.0, b=1.0,
                                      a=0.9 if active else 0.5)
                txt.text = f'{vid[-1]}-{i+1}'  # 예: 1-3, 2-1
                txt.lifetime.sec = 0
                ma.markers.append(txt)

        # 현재 폴리곤 꼭짓점 (coverage 모드)
        if self._mode == 'coverage':
            for i, (x, y) in enumerate(self._polygon):
                m = Marker()
                m.header.frame_id = 'map'
                m.header.stamp = now
                m.ns = 'polygon'
                m.id = i
                m.type = Marker.CYLINDER
                m.action = Marker.ADD
                m.pose.position = Point(x=x, y=y, z=0.05)
                m.pose.orientation.w = 1.0
                m.scale = Vector3(x=0.25, y=0.25, z=0.15)
                m.color = ColorRGBA(r=1.0, g=1.0, b=0.0, a=0.8)
                m.lifetime.sec = 0
                ma.markers.append(m)

            # 폴리곤 윤곽선
            if len(self._polygon) >= 2:
                poly_line = Marker()
                poly_line.header.frame_id = 'map'
                poly_line.header.stamp = now
                poly_line.ns = 'polygon_outline'
                poly_line.id = 0
                poly_line.type = Marker.LINE_STRIP
                poly_line.action = Marker.ADD
                poly_line.scale = Vector3(x=0.04, y=0.0, z=0.0)
                poly_line.color = ColorRGBA(r=1.0, g=1.0, b=0.0, a=0.6)
                poly_line.lifetime.sec = 0
                for x, y in self._polygon:
                    poly_line.points.append(Point(x=x, y=y, z=0.05))
                if len(self._polygon) >= 3:
                    x0, y0 = self._polygon[0]
                    poly_line.points.append(Point(x=x0, y=y0, z=0.05))
                ma.markers.append(poly_line)

        self._prev_pub.publish(ma)


def main(args=None):
    rclpy.init(args=args)
    node = PatrolPlannerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
