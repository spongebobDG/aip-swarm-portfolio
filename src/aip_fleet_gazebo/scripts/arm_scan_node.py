#!/usr/bin/env python3
"""arm_scan_node.py — 4-DOF 서보암 제어 + 열화상 FOV 시각화 노드.

모드
----
SCAN   (기본): pan 관절 ±45° 왕복 — 열화상 커버리지 확대
TRACK  (자동): 열원 감지 온도 초과 시 열원 방향으로 pan 지향
MANUAL (외부): /{vid}/arm_pan_target (Float32, rad) 수신 시 해당 각도 추적.
               마지막 명령 수신 후 MANUAL_TIMEOUT 초 경과 시 SCAN 복귀.

명령 방식
----------
gz_ros2_control 0.7.x GazeboSimSystem: position interface no-op(물리엔진 미반영).
velocity interface + dead-reckoning P 제어기 사용:

  est_pos  : 발행한 velocity 를 적분한 추정 위치 — JSB 피드백 없이도 정확
  vcmd     : ff + Kp × (target − est_pos)
  소프트리밋: est_pos 기준 → JSB 1 Hz 스테일 문제와 무관하게 한계 보호

JSB(joint_states) 가 도착하면 est_pos 를 실제 값으로 보정(드리프트 제거).
피드백이 1 Hz 로 느려도 dead-reckoning 이 10 Hz 간격으로 소프트리밋을 지킨다.

발행
----
  /{vid}/arm_position_controller/commands  Float64MultiArray  [pan_vel (rad/s)]
  /{vid}/arm_fov_marker                    MarkerArray        열화상 FOV 콘 시각화

구독
----
  /{vid}/joint_states    JointState         est_pos 보정용 (느려도 무방)
  /{vid}/thermal_temp    Float32            현재 감지 온도
  /sim/heat_sources      Float32MultiArray  [x,y,z,temp,…] 활성 열원
  /{vid}/arm_pan_target  Float32            외부 목표 각도 (rad, MANUAL 모드)
"""
import math

import rclpy
import rclpy.time
import tf2_ros
from geometry_msgs.msg import Point
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float32, Float32MultiArray, Float64MultiArray
from visualization_msgs.msg import Marker, MarkerArray

# ── 스캔 파라미터 ─────────────────────────────────────────────────────────────
_SCAN_AMP    = 0.7854   # ±45° 왕복 진폭 (rad)
_SCAN_FREQ   = 0.08     # Hz — 주기 12.5 s
_SCAN_RAMP   = 10.0     # s — 시작 시 진폭 0→full 점진 증가
_PAN_OFFSET  = 0.0      # 정면 정렬 오프셋 (rad)
_TRACK_THRESH = 35.0    # °C 이상이면 TRACK 모드

# ── 제어기 파라미터 ─────────────────────────────────────────────────────────
# SCAN : ff(목표 궤적 미분) + 소형 P 보정
# MANUAL/TRACK : 정적 목표, P 만 사용
_KP_SCAN   = 1.5    # SCAN 모드 P gain
_KP_STATIC = 2.5    # MANUAL/TRACK 모드 P gain
_VEL_LIMIT = 1.0    # rad/s (URDF velocity limit)
_CTRL_DT   = 0.1    # 제어 주기 s (10 Hz)

# ── 안전 파라미터 ─────────────────────────────────────────────────────────────
_PAN_LIMIT   = 1.5708  # ±90° URDF 한계 (rad)
_SOFT_LIMIT  = 1.0     # ±57° 소프트 펜스 (rad) — dead-reckoning 기준 적용
_MANUAL_TIMEOUT = 10.0 # s — 마지막 arm_pan_target 수신 후 SCAN 복귀

# ── FOV 파라미터 ──────────────────────────────────────────────────────────────
_THERMAL_FOV_H = math.radians(110.0)
_THERMAL_RANGE = 5.0
_CAM_FOV_H     = math.radians(110.0)
_CAM_RANGE     = 10.0
_N_ARC         = 32


class ArmScanNode(Node):
    def __init__(self):
        super().__init__('arm_scan_node')
        self.declare_parameter('vehicle_id', 'peer_1')
        vid = self.get_parameter('vehicle_id').value
        self._vid = vid

        self._cmd_pub = self.create_publisher(
            Float64MultiArray,
            f'/{vid}/arm_position_controller/commands', 10)
        self._fov_pub = self.create_publisher(
            MarkerArray, f'/{vid}/arm_fov_marker', 10)

        self.create_subscription(
            JointState, f'/{vid}/joint_states', self._on_joint_states, 10)
        self.create_subscription(
            Float32, f'/{vid}/thermal_temp', self._on_temp, 10)
        self.create_subscription(
            Float32MultiArray, '/sim/heat_sources', self._on_heat, 10)
        self.create_subscription(
            Float32, f'/{vid}/arm_pan_target', self._on_pan_target, 10)

        self._tf_buf      = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buf, self)

        self._mode          = 'SCAN'
        self._heat_sources: list[tuple[float, float, float]] = []
        self._t             = 0.0
        self._tracked_pan   = 0.0
        self._manual_target = 0.0
        self._manual_ts     = 0.0

        # dead-reckoning 위치 추정 (발행 velocity 적분)
        self._est_pos   = 0.0   # 추정 pan 위치 (rad)
        self._prev_vcmd = 0.0   # 직전 tick 에서 발행한 velocity

        # JSB 피드백 (보정용, 느려도 무방)
        self._jsb_pos       = 0.0
        self._js_received   = False
        self._js_count      = 0
        self._tick_ns       = 0   # _tick 마지막 실행 시각 (보간용)

        self.create_timer(_CTRL_DT, self._tick)
        self.create_timer(0.04, self._publish_fov)   # 25 Hz
        self.create_timer(5.0,  self._diag_log)      # 5 s
        self.get_logger().info(
            f'{vid}: arm_scan_node 시작 '
            f'(dead-reckoning, SCAN ±{math.degrees(_SCAN_AMP):.0f}°, '
            f'soft_limit=±{math.degrees(_SOFT_LIMIT):.0f}°)')

    # ── 콜백 ────────────────────────────────────────────────────────────────

    def _on_joint_states(self, msg: JointState) -> None:
        self._js_count += 1
        for name, pos in zip(msg.name, msg.position):
            if name == 'arm_pan_joint':
                if not self._js_received:
                    self._js_received = True
                    self._est_pos = pos   # 첫 수신 시 추정값 초기화
                    self.get_logger().info(
                        f'{self._vid}: [진단] joint_states 첫 수신 '
                        f'arm_pan={math.degrees(pos):.1f}°, est_pos 보정 완료')
                else:
                    # dead-reckoning 드리프트 보정 (JSB 는 느려도 됨)
                    self._est_pos = pos
                self._jsb_pos = pos

    def _diag_log(self) -> None:
        if not self._js_received:
            self.get_logger().warn(
                f'{self._vid}: [진단] joint_states 미수신 — '
                f'est_pos={math.degrees(self._est_pos):.1f}° (dead-reckoning)')
        else:
            self.get_logger().info(
                f'{self._vid}: [진단] '
                f'jsb={math.degrees(self._jsb_pos):.1f}° '
                f'est={math.degrees(self._est_pos):.1f}° '
                f'js_count={self._js_count} mode={self._mode}')

    def _on_temp(self, msg: Float32) -> None:
        if self._mode == 'MANUAL':
            return
        prev = self._mode
        self._mode = 'TRACK' if msg.data > _TRACK_THRESH else 'SCAN'
        if self._mode != prev:
            self.get_logger().info(
                f'{self._vid}: 모드 → {self._mode} (temp={msg.data:.1f}°C)')

    def _on_heat(self, msg: Float32MultiArray) -> None:
        data = msg.data
        self._heat_sources = [
            (data[i], data[i + 1], data[i + 2])
            for i in range(0, len(data) - 3, 4)
        ]

    def _on_pan_target(self, msg: Float32) -> None:
        """외부 각도 명령 (rad, ±90° 클램프). MANUAL 모드로 진입."""
        angle = max(-_PAN_LIMIT, min(_PAN_LIMIT, float(msg.data)))
        self._manual_target = angle
        self._manual_ts     = self.get_clock().now().nanoseconds * 1e-9
        if self._mode != 'MANUAL':
            self._mode = 'MANUAL'
            self.get_logger().info(
                f'{self._vid}: 모드 → MANUAL '
                f'(target={math.degrees(angle):.1f}°, timeout={_MANUAL_TIMEOUT}s)')

    # ── 제어 루프 ────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        self._t += _CTRL_DT
        now = self.get_clock().now().nanoseconds * 1e-9

        # MANUAL timeout → SCAN 복귀
        if self._mode == 'MANUAL' and now - self._manual_ts > _MANUAL_TIMEOUT:
            self._mode = 'SCAN'
            self.get_logger().info(f'{self._vid}: MANUAL timeout → SCAN 복귀')

        # ── dead-reckoning 위치 갱신 (직전 명령 적분) ──────────────────────
        self._est_pos += self._prev_vcmd * _CTRL_DT
        self._est_pos  = max(-_PAN_LIMIT, min(_PAN_LIMIT, self._est_pos))

        # ── 목표·피드포워드 계산 ────────────────────────────────────────────
        if self._mode == 'MANUAL':
            target = self._manual_target
            ff     = 0.0
            kp     = _KP_STATIC
        elif self._mode == 'SCAN' or not self._heat_sources:
            ramp   = min(1.0, self._t / _SCAN_RAMP)
            phase  = 2.0 * math.pi * _SCAN_FREQ * self._t
            amp    = ramp * _SCAN_AMP
            target = amp * math.sin(phase) + _PAN_OFFSET
            ff     = amp * 2.0 * math.pi * _SCAN_FREQ * math.cos(phase)
            kp     = _KP_SCAN
        else:
            target = self._compute_track_pan()
            ff     = 0.0
            kp     = _KP_STATIC

        # ── 속도 명령 (ff + P, dead-reckoning 기준) ────────────────────────
        vcmd = max(-_VEL_LIMIT, min(_VEL_LIMIT, ff + kp * (target - self._est_pos)))

        # ── 소프트 리밋 펜스 (dead-reckoning 기준 — JSB 의존 없음) ──────────
        if self._est_pos >= _SOFT_LIMIT and vcmd > 0:
            vcmd = -_VEL_LIMIT
        elif self._est_pos <= -_SOFT_LIMIT and vcmd < 0:
            vcmd = _VEL_LIMIT

        self._prev_vcmd = vcmd
        self._tick_ns   = self.get_clock().now().nanoseconds

        cmd      = Float64MultiArray()
        cmd.data = [vcmd]
        self._cmd_pub.publish(cmd)

    # ── FOV 시각화 ──────────────────────────────────────────────────────────

    def _publish_fov(self) -> None:
        # 로봇 위치: base_link TF (EKF 기반, 안정적 갱신)
        try:
            tf_robot = self._tf_buf.lookup_transform(
                'map', f'{self._vid}/base_link', rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=0.0))
        except Exception:
            return

        now_ns = self.get_clock().now().nanoseconds

        # arm_pan 각도: dead-reckoning(10Hz) + tick 이후 경과 시간으로 보간
        # → JSB→RSP→TF 체인(1Hz)에 의존하지 않아 25Hz 부드러운 갱신
        dt = min((now_ns - self._tick_ns) * 1e-9, _CTRL_DT) if self._tick_ns else 0.0
        arm_pan = self._est_pos + self._prev_vcmd * dt

        rx = tf_robot.transform.translation.x
        ry = tf_robot.transform.translation.y
        q  = tf_robot.transform.rotation
        siny  = 2.0 * (q.w * q.z + q.x * q.y)
        cosy  = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        robot_yaw = math.atan2(siny, cosy)

        # FOV 중심 방향 = 로봇 헤딩 + arm_pan
        fov_dir = robot_yaw + arm_pan
        now = self.get_clock().now().to_msg()

        def fov_marker(mid: int, fov_h: float, r_range: float,
                       cr: float, cg: float, cb: float) -> Marker:
            half   = fov_h / 2.0
            origin = Point(x=rx, y=ry, z=0.3)
            arc    = [
                Point(
                    x=rx + r_range * math.cos(fov_dir + half * t),
                    y=ry + r_range * math.sin(fov_dir + half * t),
                    z=0.3,
                )
                for t in (-1.0 + 2.0 * i / _N_ARC for i in range(_N_ARC + 1))
            ]
            pts: list[Point] = []
            for i in range(_N_ARC):
                pts += [arc[i], arc[i + 1]]
            pts += [origin, arc[0], origin, arc[-1]]

            m = Marker()
            m.header.stamp    = now
            m.header.frame_id = 'map'
            m.ns              = f'{self._vid}_fov'
            m.id              = mid
            m.type            = Marker.LINE_LIST
            m.action          = Marker.ADD
            m.scale.x         = 0.025
            m.color.r, m.color.g, m.color.b, m.color.a = cr, cg, cb, 1.0
            m.points          = pts
            m.lifetime.nanosec = 80_000_000   # 80ms — 25Hz 주기(40ms)의 2배 여유
            return m

        t_r, t_g, t_b = (1.0, 0.1, 0.0) if self._mode == 'TRACK' else (1.0, 0.5, 0.0)
        ma = MarkerArray()
        ma.markers.append(fov_marker(0, _THERMAL_FOV_H, _THERMAL_RANGE, t_r, t_g, t_b))
        ma.markers.append(fov_marker(1, _CAM_FOV_H,     _CAM_RANGE,     0.2, 0.6, 1.0))
        self._fov_pub.publish(ma)

    # ── 추적 계산 ────────────────────────────────────────────────────────────

    def _compute_track_pan(self) -> float:
        try:
            tf = self._tf_buf.lookup_transform(
                'map', f'{self._vid}/base_link', rclpy.time.Time())
        except Exception:
            return self._tracked_pan

        rx = tf.transform.translation.x
        ry = tf.transform.translation.y
        q  = tf.transform.rotation

        siny = 2.0 * (q.w * q.z + q.x * q.y)
        cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        yaw  = math.atan2(siny, cosy)

        best_pan  = self._tracked_pan
        best_dist = float('inf')
        for (hx, hy, _) in self._heat_sources:
            dist = math.hypot(hx - rx, hy - ry)
            if dist < best_dist:
                best_dist = dist
                angle     = math.atan2(hy - ry, hx - rx) - yaw
                angle     = (angle + math.pi) % (2.0 * math.pi) - math.pi
                best_pan  = max(-_PAN_LIMIT, min(_PAN_LIMIT, angle))

        self._tracked_pan = best_pan
        return best_pan


def main(args=None):
    rclpy.init(args=args)
    node = ArmScanNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
