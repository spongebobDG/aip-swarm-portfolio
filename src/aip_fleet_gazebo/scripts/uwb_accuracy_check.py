#!/usr/bin/env python3
"""uwb_accuracy_check.py — compare AMCL vs UWB estimated positions.

.. deprecated::
    DEPRECATED (2026-06-15): 전 차량 LiDAR+SLAM 채택으로 UWB 측위 불필요.
    실차에서 이 스크립트를 실행하지 않는다. 코드는 참고용으로 보존.

Prints a live table of position error between:
  AMCL (ground truth in sim): map → peer_N/base_link
  UWB estimate (shadow mode): map → peer_N/base_link_uwb_est

Usage:
  python3 uwb_accuracy_check.py --ros-args -p vehicle_ids:=[peer_2,peer_3]
  (or via the aip_uwb_compare alias)

Output (10 Hz):
  peer_2  AMCL(x,y)=(-1.50, 1.00)  UWB(x,y)=(-1.52, 1.03)  err=0.036 m
  peer_3  AMCL(x,y)=(-1.50,-1.00)  UWB(x,y)=(-1.49,-0.98)  err=0.022 m
"""
from __future__ import annotations

import math

import rclpy
import rclpy.duration
import rclpy.time
from rclpy.node import Node
import tf2_ros


class UwbAccuracyCheck(Node):

    def __init__(self) -> None:
        super().__init__('uwb_accuracy_check')
        self.declare_parameter('vehicle_ids', ['peer_2', 'peer_3'])
        self._ids = list(self.get_parameter('vehicle_ids').value)

        self._tf_buf = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buf, self)
        self.create_timer(0.1, self._tick)

        self.get_logger().info(
            f'uwb_accuracy_check: watching {self._ids}'
        )

    def _lookup_xy(self, child: str) -> tuple[float, float] | None:
        try:
            tf = self._tf_buf.lookup_transform(
                'map', child,
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=0.05),
            )
            t = tf.transform.translation
            return t.x, t.y
        except Exception:
            return None

    def _tick(self) -> None:
        lines = []
        for vid in self._ids:
            amcl = self._lookup_xy(f'{vid}/base_link')
            uwb  = self._lookup_xy(f'{vid}/base_link_uwb_est')

            if amcl is None and uwb is None:
                lines.append(f'  {vid}: TF not available yet')
                continue
            if amcl is None:
                lines.append(f'  {vid}: AMCL TF missing (uwb_est at {uwb})')
                continue
            if uwb is None:
                lines.append(f'  {vid}: UWB TF missing (AMCL at {amcl})')
                continue

            err = math.hypot(amcl[0] - uwb[0], amcl[1] - uwb[1])
            lines.append(
                f'  {vid}  '
                f'AMCL({amcl[0]:+.3f},{amcl[1]:+.3f})  '
                f'UWB({uwb[0]:+.3f},{uwb[1]:+.3f})  '
                f'err={err:.3f} m'
            )

        if lines:
            self.get_logger().info('\n' + '\n'.join(lines))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = UwbAccuracyCheck()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
