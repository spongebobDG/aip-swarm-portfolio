"""scan_deskew_node — 회전/주행 중 스캔 모션 왜곡(skew) 보정 (중앙 PC 실행).

ydlidar 1회전(10Hz=100ms) 동안 로봇이 이동/선회하면 스캔이 왜곡된다(특히 선회 시 각도
스미어). slam_toolbox 는 단일 stamp 로 처리 → 왜곡 스캔을 맵에 맞추려다 포즈가 비틀려
TF 가 뒤로/밖으로 발산. 본 노드가 각 포인트를 **측정 시각의 로봇 모션만큼 역보정**해
sweep-시작(=slam 이 쓰는 stamp) 프레임으로 정렬한 깨끗한 스캔을 발행한다.

모션원: /{ns}/odom twist (vx, wz) 를 sweep 내 등속 가정으로 사용.
입출력: /aip1/scan(+/aip1/odom) → /aip1/scan_deskewed. slam scan_topic 이 이 토픽 구독.
부수효과: 무효점(0.0)·근거리도 inf 로 정리(slam min_laser_range 와 이중 안전).
"""
from __future__ import annotations

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry


class ScanDeskewNode(Node):
    def __init__(self) -> None:
        super().__init__('scan_deskew')
        self.declare_parameter('scan_in',   '/aip1/scan')
        self.declare_parameter('scan_out',  '/aip1/scan_deskewed')
        self.declare_parameter('odom_topic', '/aip1/odom')
        self.declare_parameter('time_reverse', False)   # reversion 등으로 시간순서가 인덱스 역순이면 True
        self.declare_parameter('motion_eps', 0.02)      # 이 미만 vx/wz 면 보정 생략(그대로 통과)

        self._trev = bool(self.get_parameter('time_reverse').value)
        self._eps  = float(self.get_parameter('motion_eps').value)
        sin  = self.get_parameter('scan_in').value
        sout = self.get_parameter('scan_out').value
        odt  = self.get_parameter('odom_topic').value

        self._vx = 0.0
        self._wz = 0.0
        self._pub = self.create_publisher(LaserScan, sout, qos_profile_sensor_data)
        self.create_subscription(LaserScan, sin, self._cb_scan, qos_profile_sensor_data)
        self.create_subscription(Odometry, odt, self._cb_odom, 20)
        self.get_logger().info(f'scan_deskew  {sin}(+{odt}) → {sout}  (time_reverse={self._trev})')

    def _cb_odom(self, msg: Odometry) -> None:
        self._vx = float(msg.twist.twist.linear.x)
        self._wz = float(msg.twist.twist.angular.z)

    def _cb_scan(self, msg: LaserScan) -> None:
        vx, wz = self._vx, self._wz
        n = len(msg.ranges)
        # 정지·미세모션이면 왜곡 무시할 수준 → 그대로 통과(CPU 절감)
        if n == 0 or (abs(wz) < self._eps and abs(vx) < self._eps):
            self._pub.publish(msg)
            return

        r = np.asarray(msg.ranges, dtype=np.float64)
        idx = np.arange(n)
        amin, ainc = msg.angle_min, msg.angle_increment
        ti = msg.time_increment
        valid = np.isfinite(r) & (r >= msg.range_min) & (r <= msg.range_max)

        # 각 포인트 측정 시각(sweep 시작 기준 오프셋)
        dt = (n - 1 - idx) * ti if self._trev else idx * ti
        th = amin + idx * ainc
        x = r * np.cos(th)
        y = r * np.sin(th)
        # sweep 동안 로봇이 (dx, dth) 만큼 이동 → 포인트를 sweep-시작 프레임으로 변환
        dth = wz * dt
        dx = vx * dt
        c, s = np.cos(dth), np.sin(dth)
        xs = c * x - s * y + dx
        ys = s * x + c * y
        rc = np.hypot(xs, ys)
        ac = np.arctan2(ys, xs)
        k = np.round((ac - amin) / ainc).astype(np.int64)

        out = np.full(n, np.inf)
        m = valid & (k >= 0) & (k < n)
        ks, rcs = k[m], rc[m]
        # 같은 bin 충돌 시 더 가까운(작은) range 유지: 큰 것 먼저 써서 작은 것이 덮어쓰게
        order = np.argsort(-rcs)
        out[ks[order]] = rcs[order]

        msg.ranges = out.astype(np.float32).tolist()
        msg.intensities = []   # 재배치로 무의미
        self._pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ScanDeskewNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
