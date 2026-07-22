#!/usr/bin/env python3
"""peer_obstacle_node.py — 동료 차량 위치를 Nav2 로컬 코스트맵에 가상 장애물로 주입.

각 차량 vid 에 대해 다른 모든 차량의 TF 위치를 읽어
/{vid}/peer_obstacles (PointCloud2) 로 발행한다.
nav2_full.yaml 의 local_costmap → obstacle_layer 에서 이를 구독하여
다른 차량을 동적 장애물로 처리, DWB 컨트롤러가 실시간 회피한다.

알고리즘:
  1. TF 브로드캐스트에서 모든 차량의 map 기준 위치 조회
  2. 각 vid 에 대해 자신을 제외한 차량 위치 주변에 원형 점군 생성
     (반경 = robot_radius = 0.30m, 12점 = 30° 간격 + 중심점)
  3. /{vid}/peer_obstacles (PointCloud2, map frame) 발행
  4. 로컬 코스트맵 rolling window 가 이동하면서 구 위치 자동 소거

발행:
  /{vid}/peer_obstacles   sensor_msgs/PointCloud2  (map frame)

구독:
  /tf, /tf_static  (TF2 브로드캐스터)

Usage:
  ros2 run aip_fleet_gazebo peer_obstacle_node.py \\
      --ros-args -p vehicle_ids:=peer_1,peer_2,peer_3
"""
from __future__ import annotations

import math
import struct

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import PointCloud2, PointField
from tf2_ros import (
    Buffer, TransformListener,
    LookupException, ConnectivityException, ExtrapolationException,
)

_FIELDS = [
    PointField(name='x', offset=0,  datatype=PointField.FLOAT32, count=1),
    PointField(name='y', offset=4,  datatype=PointField.FLOAT32, count=1),
    PointField(name='z', offset=8,  datatype=PointField.FLOAT32, count=1),
]
_STEP = 12  # 3 × float32


class PeerObstacleNode(Node):
    def __init__(self) -> None:
        super().__init__('peer_obstacle_node')

        self.declare_parameter('vehicle_ids',   'peer_1,peer_2,peer_3')
        self.declare_parameter('map_frame',     'map')
        self.declare_parameter('publish_hz',     5.0)
        self.declare_parameter('robot_radius',   0.30)  # circumscribed(0.20) + 10cm 마진
        self.declare_parameter('ring_points',    12)    # 30° 간격

        ids_str = self.get_parameter('vehicle_ids').value
        self._vids   = [v.strip() for v in ids_str.split(',')]
        self._frame  = self.get_parameter('map_frame').value
        self._radius = float(self.get_parameter('robot_radius').value)
        self._n_pts  = int(self.get_parameter('ring_points').value)

        self._tf_buf = Buffer()
        self._tf_lis = TransformListener(self._tf_buf, self)

        self._pubs = {
            vid: self.create_publisher(PointCloud2, f'/{vid}/peer_obstacles', 10)
            for vid in self._vids
        }

        hz = float(self.get_parameter('publish_hz').value)
        self.create_timer(1.0 / hz, self._publish_all)

        self.get_logger().info(
            f'peer_obstacle_node: vehicles={self._vids}  '
            f'radius={self._radius:.2f}m  {hz:.0f}Hz  ring_pts={self._n_pts}')

    # ── TF 조회 ─────────────────────────────────────────────────────────────

    def _get_xy(self, vid: str) -> tuple[float, float] | None:
        try:
            t = self._tf_buf.lookup_transform(
                self._frame, f'{vid}/base_link', rclpy.time.Time())
            return (t.transform.translation.x, t.transform.translation.y)
        except (LookupException, ConnectivityException, ExtrapolationException):
            return None

    # ── 원형 점군 생성 ───────────────────────────────────────────────────────

    def _ring_cloud(self, positions: list[tuple[float, float]]) -> PointCloud2:
        pts: list[tuple[float, float, float]] = []
        for cx, cy in positions:
            # 원형 경계 + 중심점 → Nav2 가 해당 반경을 장애물로 마킹
            for i in range(self._n_pts):
                angle = 2.0 * math.pi * i / self._n_pts
                pts.append((cx + self._radius * math.cos(angle),
                             cy + self._radius * math.sin(angle), 0.0))
            pts.append((cx, cy, 0.0))

        data = bytearray()
        for x, y, z in pts:
            data += struct.pack('<fff', x, y, z)

        msg = PointCloud2()
        msg.header.frame_id = self._frame
        msg.header.stamp    = self.get_clock().now().to_msg()
        msg.height          = 1
        msg.width           = len(pts)
        msg.fields          = _FIELDS
        msg.is_bigendian    = False
        msg.point_step      = _STEP
        msg.row_step        = _STEP * len(pts)
        msg.data            = bytes(data)
        msg.is_dense        = True
        return msg

    # ── 메인 루프 ────────────────────────────────────────────────────────────

    def _publish_all(self) -> None:
        pos: dict[str, tuple[float, float] | None] = {
            vid: self._get_xy(vid) for vid in self._vids
        }
        for vid in self._vids:
            others = [p for v, p in pos.items() if v != vid and p is not None]
            if not others:
                continue
            self._pubs[vid].publish(self._ring_cloud(others))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PeerObstacleNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
