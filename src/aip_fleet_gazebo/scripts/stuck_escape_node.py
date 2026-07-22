#!/usr/bin/env python3
"""stuck_escape_node.py — 고착 감지 + costmap 무시 강제 탈출 노드.

Nav2 MPPI는 주변 모든 방향이 inflation zone이면 어떤 경우에도 경로를 찾지 못함
(CostCritic 지수 가중치 특성). 이 노드는 MPPI/Nav2 스택을 완전히 우회하여
twist_mux의 stuck_escape 슬롯(priority=15)으로 직접 후진 명령을 주입한다.

고착 감지 조건 (모두 충족 시):
  1. 위치 변화 < position_threshold (0.05m) — N초 동안
  2. Nav2가 이동 명령을 내리는 중 (cmd_vel.linear.x 또는 angular.z != 0)
     → 명령이 없는 의도적 정차(도착, 경로 계산 중 대기)는 고착으로 판정하지 않음
  3. 고착 감지 쿨다운 경과 (탈출 직후 재진입 방지)

탈출 동작:
  - stuck_escape_cmd_vel 에 vx=-escape_speed 발행 (escape_duration 초간)
  - 이후 쿨다운 (cooldown_sec)
  - twist_mux timeout=0.3s: 발행 중단 시 자동 비활성

발행: /{vid}/stuck_escape_cmd_vel  geometry_msgs/Twist
구독: /{vid}/odometry/filtered      nav_msgs/Odometry
       /{vid}/autonomy_cmd_vel       geometry_msgs/Twist  (이동 의도 감지)
"""
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node


class StuckEscapeNode(Node):
    def __init__(self):
        super().__init__('stuck_escape_node')
        self.declare_parameter('vehicle_id',        'peer_1')
        self.declare_parameter('stuck_timeout_sec',  5.0)    # 고착 판정까지 대기
        self.declare_parameter('position_threshold', 0.05)   # m — 이 이하면 정지로 판정
        self.declare_parameter('escape_speed',       0.08)   # m/s — 탈출 후진 속도
        self.declare_parameter('escape_duration',    3.0)    # s — 탈출 지속 시간
        self.declare_parameter('cooldown_sec',       4.0)    # s — 탈출 후 재진입 방지
        self.declare_parameter('escape_angular',     0.15)   # rad/s — 탈출 중 미세 회전 (코너 탈출용)

        vid      = self.get_parameter('vehicle_id').value
        self._stuck_timeout  = self.get_parameter('stuck_timeout_sec').value
        self._pos_thresh     = self.get_parameter('position_threshold').value
        self._escape_speed   = self.get_parameter('escape_speed').value
        self._escape_dur     = self.get_parameter('escape_duration').value
        self._cooldown       = self.get_parameter('cooldown_sec').value
        self._escape_angular = self.get_parameter('escape_angular').value
        self._escape_dir     = 1   # 다음 탈출 회전 방향 (좌우 번갈아 — 동일 방향 재고착 방지)

        self._pub = self.create_publisher(
            Twist, f'/{vid}/stuck_escape_cmd_vel', 10)

        self.create_subscription(
            Odometry, f'/{vid}/odometry/filtered', self._on_odom, 10)
        self.create_subscription(
            Twist, f'/{vid}/autonomy_cmd_vel', self._on_cmd_vel, 10)

        self._last_x     = None
        self._last_y     = None
        self._still_since: float | None = None   # 정지 시작 시각 (wall time)
        self._last_escape: float        = 0.0    # 마지막 탈출 시각
        self._cmd_vel_active: bool      = False  # Nav2가 이동 명령 중인지
        self._last_cmd_time: float      = 0.0    # 마지막 cmd_vel 수신 시각

        # cmd_vel이 끊긴 후 이 시간 이상 지나면 의도적 정차로 간주
        self._cmd_active_window = 0.5   # s

        self.get_logger().info(
            f'{vid}: stuck_escape_node 시작 '
            f'(timeout={self._stuck_timeout}s, speed={self._escape_speed}m/s)')

    def _on_cmd_vel(self, msg: Twist) -> None:
        now = time.monotonic()
        moving = abs(msg.linear.x) > 0.001 or abs(msg.angular.z) > 0.001
        if moving:
            self._last_cmd_time = now
        self._cmd_vel_active = moving

    def _is_nav_commanding(self) -> bool:
        """Nav2가 이동 명령을 내리고 있는지 — 최근 0.5s 내 비제로 cmd_vel 수신."""
        return (time.monotonic() - self._last_cmd_time) < self._cmd_active_window

    def _on_odom(self, msg: Odometry) -> None:
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        now = time.monotonic()

        if self._last_x is None:
            self._last_x, self._last_y = x, y
            self._still_since = now
            return

        dist = math.hypot(x - self._last_x, y - self._last_y)

        if dist >= self._pos_thresh:
            # 이동 중 — 타이머 리셋
            self._last_x, self._last_y = x, y
            self._still_since = now
            return

        # 이동 없음
        if self._still_since is None:
            self._still_since = now

        still_elapsed = now - self._still_since
        cooldown_ok   = (now - self._last_escape) >= self._cooldown

        # 의도적 정차 (Nav2 명령 없음) → 고착 판정 보류
        if not self._is_nav_commanding():
            self._still_since = now   # 타이머 리셋 (명령 재개 시 새로 카운트)
            return

        if still_elapsed >= self._stuck_timeout and cooldown_ok:
            self.get_logger().warn(
                f'고착 감지 ({still_elapsed:.1f}s 정지, pos=({x:.2f},{y:.2f})) '
                f'— 탈출 후진 {self._escape_dur}s 시작')
            self._execute_escape()
            self._last_escape = now
            self._still_since = now   # 쿨다운 후 재감지

    def _execute_escape(self) -> None:
        """costmap 무시 강제 후진+회전 — twist_mux stuck_escape 슬롯(priority=15)으로 주입.

        직선 후진만으로는 코너에 낀 경우 탈출이 안 되므로 미세 회전을 함께 가해
        후진 궤적을 휘게 만든다. 매 탈출마다 회전 방향을 번갈아 동일 방향
        재고착(같은 코너로 다시 들어가는 것)을 방지.
        """
        rate_hz = 20.0
        steps   = int(self._escape_dur * rate_hz)
        twist   = Twist()
        twist.linear.x  = -self._escape_speed
        twist.angular.z = self._escape_dir * self._escape_angular

        for _ in range(steps):
            self._pub.publish(twist)
            time.sleep(1.0 / rate_hz)

        # 명시적 정지 후 슬롯 타임아웃 대기 (twist_mux timeout=0.3s)
        stop = Twist()
        for _ in range(3):
            self._pub.publish(stop)
            time.sleep(0.1)

        self._escape_dir *= -1
        self.get_logger().info('탈출 후진 완료 — Nav2 재시도 대기')


def main(args=None):
    rclpy.init(args=args)
    node = StuckEscapeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
