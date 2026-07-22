#!/usr/bin/env python3
"""patrol_node.py — autonomous waypoint patrol for a single vehicle.

Sends NavigateToPose goals to Nav2's bt_navigator action server and cycles
through a list of waypoints.  Designed for swarm patrol missions.

Goal input hierarchy (all share the same Nav2 action server):
  1. patrol_node    — this node; autonomous waypoint cycling
  2. RViz2          — 2D Goal Pose widget → /peer_N/navigate_to_pose action
  3. CLI            — ros2 action send_goal /peer_N/navigate_to_pose …

Why no Foxglove panel for goal input:
  A custom TypeScript panel would duplicate what RViz2's 2D Goal Pose already
  provides for simulation.  The panel build chain (npm + .foxe) adds overhead
  without functional benefit at this stage.  It remains an option for real
  deployment where RViz2 may not be available on the operator machine.

Parameters
----------
vehicle_id       : str    peer namespace, e.g. 'peer_2'
waypoints        : float[] flat [x1, y1, yaw1_deg, x2, y2, yaw2_deg, …]
                           waypoints in the map frame; yaw in degrees
loop_patrol      : bool   loop waypoints indefinitely (default: true)
start_delay_sec  : float  seconds to wait before sending the first goal
                           (default: 5.0 — allows Nav2 lifecycle to activate)

Usage
-----
  ros2 run aip_fleet_autonomous patrol_node \\
      --ros-args -p vehicle_id:=peer_2 \\
                 -p waypoints:="[2.0, 1.0, 0.0,  -1.0, 2.0, 90.0]" \\
                 -p loop_patrol:=true
"""
import json
import math

import rclpy
from rclpy.action import ActionClient
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import Point, PoseStamped, Quaternion, Vector3
from nav_msgs.msg import OccupancyGrid
from nav2_msgs.action import NavigateToPose
from std_msgs.msg import ColorRGBA, String
from visualization_msgs.msg import Marker, MarkerArray

# 차량별 순찰 경로 색상 (RViz Nav Plan 색상과 통일)
_VIZ_COLORS: dict[str, tuple[float, float, float]] = {
    'peer_1': (0.2,  0.85, 0.2),   # green
    'peer_2': (0.2,  0.6,  1.0),   # blue
    'peer_3': (1.0,  0.55, 0.1),   # orange
}


def _yaw_to_quat(yaw_rad: float) -> Quaternion:
    q = Quaternion()
    q.z = math.sin(yaw_rad / 2.0)
    q.w = math.cos(yaw_rad / 2.0)
    return q


class PatrolNode(Node):
    def __init__(self):
        super().__init__('patrol_node')

        self.declare_parameter('vehicle_id',      'peer_2')
        self.declare_parameter('waypoints',        [0.0, 0.0, 0.0])
        self.declare_parameter('loop_patrol',      True)
        self.declare_parameter('start_delay_sec',  5.0)

        vid       = self.get_parameter('vehicle_id').value
        flat_wps  = list(self.get_parameter('waypoints').value)
        self._loop  = bool(self.get_parameter('loop_patrol').value)
        delay       = float(self.get_parameter('start_delay_sec').value)

        if len(flat_wps) > 0 and len(flat_wps) % 3 != 0:
            raise ValueError(
                'waypoints must be a flat list of [x, y, yaw_deg] triplets, '
                f'got {len(flat_wps)} values'
            )

        self._waypoints = [
            (float(flat_wps[i]),
             float(flat_wps[i + 1]),
             math.radians(float(flat_wps[i + 2])))
            for i in range(0, len(flat_wps), 3)
        ]
        self._idx          = 0
        self._vid          = vid
        self._active       = False   # True while a Nav2 goal is in-flight
        self._paused       = False   # True when stopped by 'stop' cmd
        self._cmd_target   = vid     # 마지막 switch 명령 대상 (기본: 자신)
        self._goal_handle  = None    # 현재 진행 중인 goal handle (취소용)
        self._retry_count  = 0
        self._MAX_RETRY    = 5       # goal 거부 시 최대 재시도 횟수
        self._retry_timer  = None
        self._consec_fail  = 0       # 동일 웨이포인트 연속 실패 횟수
        self._MAX_FAIL     = 3       # 이 이상 실패 시 웨이포인트 건너뜀
        self._fail_timer   = None
        self._latest_map: OccupancyGrid | None = None

        # skip_explore 모드에서는 slam_toolbox가 빈 맵으로 시작하므로
        # /map 대신 follower_trigger가 발행하는 저장 맵 /map_static 을 사용.
        # explore 모드에서도 /map_static 은 탐색 완료 시점 맵이므로 동일하게 사용 가능.
        _latched_qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.create_subscription(OccupancyGrid, '/map_static', self._on_map, _latched_qos)
        # patrol_planner_node 에서 경로 실시간 업데이트 수신
        self.create_subscription(
            String, '/patrol_planner/plan_state',
            self._on_plan_state, _latched_qos,
        )
        # 대시보드 start/stop/mode 명령 수신
        self.create_subscription(String, '/patrol_planner/cmd', self._on_patrol_cmd, 10)

        # 순찰 상태 발행 — dashboard_server 가 WS로 브릿지
        self._status_pub = self.create_publisher(
            String, f'/{vid}/patrol_status', _latched_qos,
        )

        # 전체 순찰 경로 시각화 — TRANSIENT_LOCAL: RViz가 늦게 접속해도 수신 가능.
        self._viz_pub = self.create_publisher(
            MarkerArray, f'/{vid}/patrol_path_viz', _latched_qos
        )

        action_name = f'/{vid}/navigate_to_pose'
        self._client = ActionClient(self, NavigateToPose, action_name)

        if self._waypoints:
            self.get_logger().info(
                f'patrol_node [{vid}]: {len(self._waypoints)} waypoints | '
                f'loop={self._loop} | start in {delay:.0f}s'
            )
            # STEADY_TIME(벽시계) 사용: use_sim_time=True 환경에서 sim_time이
            # 노드 시작 시점에 이미 크게 앞서 있으면 타이머가 즉시 발화하는 문제 방지.
            self.create_timer(
                delay, self._start_once,
                clock=Clock(clock_type=ClockType.STEADY_TIME),
            )
            self._timer_fired = False
        else:
            self.get_logger().info(
                f'patrol_node [{vid}]: 웨이포인트 없음 — '
                '/patrol_planner/plan_state 수신 대기'
            )
            self._timer_fired = True  # Nav2 서버 대기 없이 plan_state 즉시 처리 가능

        # 초기 전체 경로 발행 (노드 시작 즉시)
        self._publish_viz()

    # ------------------------------------------------------------------

    def _publish_viz(self):
        """전체 순찰 경로 + 현재 목표를 MarkerArray로 발행.

        - {vid}_route   : LINE_STRIP — 모든 웨이포인트를 잇는 루프 선
        - {vid}_waypoints: CYLINDER  — 각 웨이포인트 위치 (소형)
        - {vid}_labels  : TEXT       — 웨이포인트 번호 (1-based)
        - {vid}_target  : SPHERE     — 현재 목표 강조 (노란색)
        """
        vid = self._vid
        r, g, b = _VIZ_COLORS.get(vid, (0.8, 0.8, 0.8))
        now = self.get_clock().now().to_msg()
        ma  = MarkerArray()

        # ── 1. 순찰 경로 선 (LINE_STRIP, 루프 닫힘) ──────────────────
        line = Marker()
        line.header.frame_id = 'map'
        line.header.stamp    = now
        line.ns              = f'{vid}_route'
        line.id              = 0
        line.type            = Marker.LINE_STRIP
        line.action          = Marker.ADD
        line.scale           = Vector3(x=0.06, y=0.0, z=0.0)
        line.color           = ColorRGBA(r=r, g=g, b=b, a=0.7)
        line.lifetime.sec    = 0
        for x, y, _ in self._waypoints:
            line.points.append(Point(x=x, y=y, z=0.05))
        if self._waypoints:
            x0, y0, _ = self._waypoints[0]
            line.points.append(Point(x=x0, y=y0, z=0.05))
        ma.markers.append(line)

        # ── 2. 웨이포인트 원기둥 + 번호 텍스트 ───────────────────────
        for i, (x, y, _) in enumerate(self._waypoints):
            cyl = Marker()
            cyl.header.frame_id = 'map'
            cyl.header.stamp    = now
            cyl.ns              = f'{vid}_waypoints'
            cyl.id              = i
            cyl.type            = Marker.CYLINDER
            cyl.action          = Marker.ADD
            cyl.pose.position   = Point(x=x, y=y, z=0.05)
            cyl.pose.orientation.w = 1.0
            cyl.scale           = Vector3(x=0.18, y=0.18, z=0.10)
            cyl.color           = ColorRGBA(r=r, g=g, b=b, a=0.6)
            cyl.lifetime.sec    = 0
            ma.markers.append(cyl)

            txt = Marker()
            txt.header.frame_id = 'map'
            txt.header.stamp    = now
            txt.ns              = f'{vid}_labels'
            txt.id              = i
            txt.type            = Marker.TEXT_VIEW_FACING
            txt.action          = Marker.ADD
            txt.pose.position   = Point(x=x, y=y, z=0.40)
            txt.pose.orientation.w = 1.0
            txt.scale.z         = 0.22
            txt.color           = ColorRGBA(r=1.0, g=1.0, b=1.0, a=0.9)
            txt.text            = str(i + 1)
            txt.lifetime.sec    = 0
            ma.markers.append(txt)

        # ── 3. 현재 목표 강조 (노란 구체) ────────────────────────────
        tgt = Marker()
        tgt.header.frame_id = 'map'
        tgt.header.stamp    = now
        tgt.ns              = f'{vid}_target'
        tgt.id              = 0
        tgt.action          = Marker.ADD
        if 0 <= self._idx < len(self._waypoints):
            tx, ty, _ = self._waypoints[self._idx]
            tgt.type            = Marker.SPHERE
            tgt.pose.position   = Point(x=tx, y=ty, z=0.20)
            tgt.pose.orientation.w = 1.0
            tgt.scale           = Vector3(x=0.35, y=0.35, z=0.35)
            tgt.color           = ColorRGBA(r=1.0, g=1.0, b=0.0, a=0.9)
        else:
            tgt.type  = Marker.SPHERE
            tgt.action = Marker.DELETE
        tgt.lifetime.sec = 0
        ma.markers.append(tgt)

        self._viz_pub.publish(ma)

    def _on_map(self, msg: OccupancyGrid):
        self._latest_map = msg

    def _on_plan_state(self, msg: String):
        """patrol_planner_node 경로 업데이트 수신 — 비어있지 않을 때만 반영."""
        try:
            state = json.loads(msg.data)
        except Exception:
            return

        raw = state.get('vehicles', {}).get(self._vid)
        if not raw:
            return  # 빈 경로는 무시 (플래너 초기 상태에서 기존 경로 보호)

        new_wps = [
            (float(wp[0]), float(wp[1]), math.radians(float(wp[2])))
            for wp in raw if len(wp) >= 3
        ]
        if not new_wps:
            return

        # 동일 경로면 무시 (불필요한 재시작 방지)
        if (len(new_wps) == len(self._waypoints) and all(
            abs(a[0] - b[0]) < 0.001 and
            abs(a[1] - b[1]) < 0.001 and
            abs(a[2] - b[2]) < 0.01
            for a, b in zip(new_wps, self._waypoints)
        )):
            return

        old_count = len(self._waypoints)
        self._apply_new_waypoints(new_wps)
        self.get_logger().info(
            f'[{self._vid}] 순찰 경로 업데이트: '
            f'{old_count}개 → {len(new_wps)}개 웨이포인트'
        )

    def _on_patrol_cmd(self, msg: String):
        """대시보드 start/stop/mode 명령 처리.

        UI는 항상 switch:<vid> 를 먼저 보내므로, 마지막 switch 대상이
        자신이 아닌 경우 start/stop/mode 명령을 무시한다.
        """
        cmd = msg.data.strip()

        if cmd.startswith('switch:'):
            self._cmd_target = cmd[7:]
            return

        # set_wp_list / save / load / undo / clear 등은 patrol_planner_node 처리
        if cmd not in ('start', 'stop', 'mode:loop', 'mode:waypoints'):
            return

        if self._cmd_target != self._vid:
            return  # 다른 차량 대상 명령

        if cmd == 'start':
            if self._paused:
                self._paused = False
                self.get_logger().info(f'[{self._vid}] 순찰 시작')
                if not self._active and self._waypoints and self._timer_fired:
                    if self._client.wait_for_server(timeout_sec=2.0):
                        self._send_next()
                    else:
                        self.get_logger().warn(
                            f'[{self._vid}] navigate_to_pose 서버 미응답 — 시작 지연')
            self._publish_patrol_status()

        elif cmd == 'stop':
            self._paused = True
            if self._active and self._goal_handle is not None:
                self._goal_handle.cancel_goal_async()
            self._goal_handle = None
            self._active = False
            for attr in ('_retry_timer', '_fail_timer'):
                t = getattr(self, attr, None)
                if t is not None:
                    self.destroy_timer(t)
                    setattr(self, attr, None)
            self.get_logger().info(f'[{self._vid}] 순찰 정지')
            self._publish_patrol_status()

        elif cmd == 'mode:loop':
            self._loop = True
            self.get_logger().info(f'[{self._vid}] 루프 모드 ON')
            self._publish_patrol_status()

        elif cmd == 'mode:waypoints':
            self._loop = False
            self.get_logger().info(f'[{self._vid}] 루프 모드 OFF')
            self._publish_patrol_status()

    def _publish_patrol_status(self):
        import json as _json
        self._status_pub.publish(String(data=_json.dumps({
            'vehicle_id': self._vid,
            'running':    not self._paused,
            'loop':       self._loop,
            'wp_index':   self._idx,
            'wp_total':   len(self._waypoints),
        })))

    def _apply_new_waypoints(self, wps: list[tuple[float, float, float]]):
        """새 경로 즉시 적용 — 진행 중인 목표 취소 후 첫 웨이포인트부터 재시작."""
        # 진행 중 goal 취소
        if self._active and self._goal_handle is not None:
            self._goal_handle.cancel_goal_async()
        self._goal_handle = None

        # 대기 타이머 정리
        for attr in ('_retry_timer', '_fail_timer'):
            t = getattr(self, attr, None)
            if t is not None:
                self.destroy_timer(t)
                setattr(self, attr, None)

        self._waypoints   = wps
        self._idx         = 0
        self._active      = False
        self._consec_fail = 0
        self._retry_count = 0

        self._publish_viz()

        # Nav2 서버 준비 완료 상태면 즉시 순찰 재시작
        if self._timer_fired:
            if not self._client.wait_for_server(timeout_sec=3.0):
                self.get_logger().warn(
                    'navigate_to_pose 서버 미응답 — 경로 업데이트 후 시작 지연'
                )
                return
            self._send_next()

    def _is_waypoint_known(self, x: float, y: float) -> bool:
        """웨이포인트 0.5m 반경 내에 known 셀이 하나라도 있으면 True.

        단일 셀 체크는 맵 경계 근처 웨이포인트를 과도하게 skip한다.
        Nav2 planner에 allow_unknown: true가 설정돼 있으므로 인근이 알려진
        구역이면 시도를 위임하는 것이 더 견고하다.
        """
        m = self._latest_map
        if m is None:
            return True
        res = m.info.resolution
        ox  = m.info.origin.position.x
        oy  = m.info.origin.position.y
        cx  = int((x - ox) / res)
        cy  = int((y - oy) / res)
        r   = max(1, int(0.5 / res))   # 0.5 m 반경 (최소 1 셀)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < m.info.width and 0 <= ny < m.info.height:
                    if m.data[ny * m.info.width + nx] >= 0:
                        return True
        return False

    def _start_once(self):
        if self._timer_fired:
            return
        self._timer_fired = True

        self.get_logger().info('patrol_node: waiting for navigate_to_pose server …')
        if not self._client.wait_for_server(timeout_sec=60.0):
            self.get_logger().error('navigate_to_pose action server not available after 60 s')
            return
        self.get_logger().info('patrol_node: server ready, starting patrol')
        self._send_next()

    def _send_next(self):
        if self._paused:
            return
        if self._idx >= len(self._waypoints):
            if self._loop:
                self._idx = 0
                self.get_logger().info('patrol_node: looping to waypoint 0')
            else:
                self.get_logger().info('patrol_node: all waypoints visited — idle')
                return

        x, y, yaw = self._waypoints[self._idx]

        if not self._is_waypoint_known(x, y):
            self.get_logger().warn(
                f'patrol_node: [{self._idx + 1}/{len(self._waypoints)}] '
                f'({x:.1f},{y:.1f}) — 미매핑 구역, 건너뜀'
            )
            self._idx += 1
            self._send_next()
            return

        self.get_logger().info(
            f'patrol_node: [{self._idx + 1}/{len(self._waypoints)}] '
            f'→ ({x:.2f}, {y:.2f}, {math.degrees(yaw):.0f}°)'
        )
        self._publish_viz()   # 현재 목표 강조 갱신

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id    = 'map'
        goal.pose.header.stamp       = self.get_clock().now().to_msg()
        goal.pose.pose.position.x    = x
        goal.pose.pose.position.y    = y
        goal.pose.pose.orientation   = _yaw_to_quat(yaw)

        self._active = True
        future = self._client.send_goal_async(
            goal, feedback_callback=self._on_feedback
        )
        future.add_done_callback(self._on_goal_response)

    def _on_goal_response(self, future):
        goal_handle = future.result()
        self._goal_handle = goal_handle
        if not goal_handle.accepted:
            self._active = False
            if self._retry_count < self._MAX_RETRY:
                self._retry_count += 1
                self.get_logger().warn(
                    f'patrol_node: waypoint {self._idx + 1} rejected — '
                    f'retry {self._retry_count}/{self._MAX_RETRY} in 2s '
                    f'(Nav2 아직 활성화 중일 수 있음)'
                )
                # 2초 후 동일 웨이포인트 재시도 (STEADY_TIME으로 sim_time 무관)
                self._retry_timer = self.create_timer(
                    2.0, self._retry_goal,
                    clock=Clock(clock_type=ClockType.STEADY_TIME),
                )
            else:
                self.get_logger().warn(
                    f'patrol_node: waypoint {self._idx + 1} 최대 재시도 초과 — skipping'
                )
                self._retry_count = 0
                self._idx += 1
                self._send_next()
            return
        self._retry_count = 0
        goal_handle.get_result_async().add_done_callback(self._on_result)

    def _retry_goal(self):
        # 1회성 타이머이므로 자기 자신을 취소
        if hasattr(self, '_retry_timer') and self._retry_timer is not None:
            self.destroy_timer(self._retry_timer)
            self._retry_timer = None
        self._send_next()

    def _on_result(self, future):
        status = future.result().status
        self._active = False
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info(
                f'patrol_node: waypoint {self._idx + 1} reached'
            )
            self._consec_fail = 0
            self._idx += 1
            self._send_next()
        else:
            self._consec_fail += 1
            if self._consec_fail >= self._MAX_FAIL:
                # 동일 웨이포인트를 MAX_FAIL번 시도해도 실패 → 건너뜀
                self.get_logger().warn(
                    f'patrol_node: waypoint {self._idx + 1} — '
                    f'{self._MAX_FAIL}회 연속 실패, 건너뜀 (status={status})'
                )
                self._consec_fail = 0
                self._idx += 1
                self._send_next()
            else:
                # TF 외삽 오류 등 일시적 장애: 5s 대기 후 동일 웨이포인트 재시도.
                # Foxglove bridge 연결 초기 CPU 포화로 TF 버퍼가 비었을 때 복구용.
                self.get_logger().warn(
                    f'patrol_node: waypoint {self._idx + 1} 실패 '
                    f'(status={status}) — 5s 후 재시도 '
                    f'({self._consec_fail}/{self._MAX_FAIL})'
                )
                self._fail_timer = self.create_timer(
                    5.0, self._on_fail_timeout,
                    clock=Clock(clock_type=ClockType.STEADY_TIME),
                )

    def _on_fail_timeout(self):
        if self._fail_timer is not None:
            self.destroy_timer(self._fail_timer)
            self._fail_timer = None
        self._send_next()

    def _on_feedback(self, feedback_msg):
        dist = feedback_msg.feedback.distance_remaining
        self.get_logger().info(
            f'patrol_node: remaining = {dist:.2f} m',
            throttle_duration_sec=5.0,
        )


def main(args=None):
    rclpy.init(args=args)
    node = PatrolNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
