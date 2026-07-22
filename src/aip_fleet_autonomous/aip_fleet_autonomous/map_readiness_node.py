#!/usr/bin/env python3
"""map_readiness_node — explore_lite 완료 신호 + 최소 셀 수로 /fleet/map_ready 발행.

트리거 조건 (AND):
  1. explore_lite 가 exploration_complete 를 발행 (frontier 소진)
  2. known 셀 수 >= min_known_cells (너무 이른 완료 방지 안전장치)
  3. explore_done_stabilization_sec 동안 맵 성장 안정화 확인

폴백:
  explore_lite 완료 후에도 min_known_cells 미달인 경우
  (로봇이 일부 구역에 접근 불가 등), explore_done_fallback_sec 경과 후 강제 트리거.

stall 감지:
  셀 증가가 stall_timeout_sec(wall clock 기준) 동안 없으면 강제 트리거.
  rtf와 무관하게 실제 경과 시간 기준으로 동작.

explore_lite 없이 단독 운용 시: explore_status_topic 을 빈 문자열로 설정하면
기존 min_known_cells 도달 시 즉시 트리거(폴백 동작).
"""
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from nav_msgs.msg import OccupancyGrid
from std_msgs.msg import Bool

try:
    from explore_lite_msgs.msg import ExploreStatus
    _HAVE_EXPLORE_MSGS = True
except ImportError:
    _HAVE_EXPLORE_MSGS = False

_LATCHED_QOS = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)


class MapReadinessNode(Node):
    def __init__(self):
        super().__init__('map_readiness_node')

        # fleet_world 20×20m, 0.05m/cell → 160,000 셀 총량.
        # 80,000 ≈ 50% (200 m²) — 임시 기준값. 실측 후 조정 권장.
        self.declare_parameter('min_known_cells',              80000)
        self.declare_parameter('explore_status_topic',        '/peer_1/explore/status')
        self.declare_parameter('explore_done_fallback_sec',   60.0)
        self.declare_parameter('explore_done_stabilization_sec', 0.0)

        self.declare_parameter('stall_timeout_sec',   90.0)
        self.declare_parameter('stall_min_delta',     200)

        self._min_cells      = self.get_parameter('min_known_cells').value
        self._status_topic   = self.get_parameter('explore_status_topic').value
        self._fallback_sec   = self.get_parameter('explore_done_fallback_sec').value
        self._stabilize_sec  = self.get_parameter('explore_done_stabilization_sec').value
        self._stall_sec      = self.get_parameter('stall_timeout_sec').value
        self._stall_delta    = self.get_parameter('stall_min_delta').value
        self._ready          = False
        self._explore_done   = False
        self._known_cells    = 0
        # wall clock 기반 타임스탬프 (rtf 영향 없음)
        self._explore_done_wall: float | None  = None   # explore_complete 수신 시각
        self._last_growth_cells: int           = 0
        self._last_growth_wall: float | None   = None   # 마지막 셀 증가 wall clock

        self._pub = self.create_publisher(Bool, '/fleet/map_ready', _LATCHED_QOS)

        self._map_sub = self.create_subscription(
            OccupancyGrid, '/map', self._on_map, 10)

        if self._status_topic and _HAVE_EXPLORE_MSGS:
            self._explore_sub = self.create_subscription(
                ExploreStatus, self._status_topic,
                self._on_explore_status, 10)
            self.get_logger().info(
                f'map_readiness_node 시작: explore_status={self._status_topic}, '
                f'min_cells={self._min_cells}, '
                f'stabilize={self._stabilize_sec}s(wall), '
                f'fallback={self._fallback_sec}s(wall), stall={self._stall_sec}s(wall)'
            )
        else:
            self._explore_sub = None
            self.get_logger().warn(
                f'explore_lite_msgs 미설치 또는 status_topic 미설정 — '
                f'min_known_cells({self._min_cells}) 도달 시 즉시 트리거(폴백)'
            )

    def _on_map(self, msg: OccupancyGrid):
        if self._ready:
            self._pub.publish(Bool(data=True))
            return

        total = len(msg.data)
        if total == 0:
            return

        self._known_cells = sum(1 for c in msg.data if c >= 0)

        # stall 감지: 셀 증가량이 stall_min_delta 이상이면 타이머 리셋
        if self._known_cells - self._last_growth_cells >= self._stall_delta:
            self._last_growth_cells = self._known_cells
            self._last_growth_wall  = time.monotonic()   # wall clock 기준

        self.get_logger().info(
            f'맵 커버리지: known={self._known_cells}셀 '
            f'({self._known_cells * msg.info.resolution ** 2:.1f}㎡) '
            f'| explore_done={self._explore_done}',
            throttle_duration_sec=15.0,
        )

        self._check_ready()

    def _on_explore_status(self, msg):
        if msg.status == 'exploration_complete':
            self.get_logger().info(
                f'explore_lite: exploration_complete 수신 '
                f'(known={self._known_cells}셀) '
                f'— stabilization {self._stabilize_sec:.0f}s 대기 후 트리거 판정')
            self._explore_done      = True
            self._explore_done_wall = time.monotonic()   # wall clock
            self._check_ready()

    def _check_ready(self):
        if self._ready:
            return

        now_wall     = time.monotonic()
        enough_cells = self._known_cells >= self._min_cells

        if self._explore_sub is not None:
            trigger = False

            if self._explore_done and self._explore_done_wall is not None:
                done_elapsed = now_wall - self._explore_done_wall

                if enough_cells:
                    # 안정화 대기: explore_complete 후 stabilize_sec 경과해야 트리거
                    if done_elapsed >= self._stabilize_sec:
                        self.get_logger().info(
                            f'explore_lite 완료 + 셀 수 충족 + '
                            f'안정화 {done_elapsed:.0f}s 경과 → 트리거'
                        )
                        trigger = True
                    else:
                        self.get_logger().info(
                            f'explore_lite 완료, 안정화 대기 중 '
                            f'({done_elapsed:.0f}/{self._stabilize_sec:.0f}s) '
                            f'known={self._known_cells}셀',
                            throttle_duration_sec=15.0,
                        )
                else:
                    # 폴백: 셀 수 미달인데 fallback_sec 경과 → 접근 불가 구역 판단
                    if done_elapsed >= self._fallback_sec:
                        self.get_logger().warn(
                            f'explore_lite 완료 후 {done_elapsed:.0f}s 경과. '
                            f'known={self._known_cells}셀 < min={self._min_cells}셀. '
                            f'접근 불가 구역 존재 — 폴백 트리거.'
                        )
                        trigger = True

            # stall 트리거: 맵 성장이 wall clock stall_sec 동안 없고 셀 수 충분
            if not trigger and enough_cells and self._last_growth_wall is not None:
                stall_elapsed = now_wall - self._last_growth_wall
                if stall_elapsed >= self._stall_sec:
                    self.get_logger().warn(
                        f'맵 성장 stall {stall_elapsed:.0f}s 경과 (wall clock) '
                        f'(known={self._known_cells}셀 >= min={self._min_cells}셀). '
                        f'탐색 불가 구역 잔존 — stall 트리거.'
                    )
                    trigger = True
        else:
            trigger = enough_cells

        if trigger:
            area_m2 = self._known_cells * 0.05 ** 2
            self.get_logger().info(
                f'맵 준비 완료 (known={self._known_cells}셀, ~{area_m2:.0f}㎡) '
                f'→ /fleet/map_ready 발행'
            )
            self._ready = True
            self._pub.publish(Bool(data=True))


def main(args=None):
    rclpy.init(args=args)
    node = MapReadinessNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
