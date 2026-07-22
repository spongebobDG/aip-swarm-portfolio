#!/usr/bin/env python3
"""keepout_zone_node.py — 금지구역 폴리곤을 Nav2 costmap obstacle로 주입.

/fleet/keepout_zones (String, JSON) 구독 → 폴리곤 내부를 0.05m 격자로 채워
/fleet/keepout_cloud (PointCloud2, TRANSIENT_LOCAL) 로 1Hz 재발행.

Nav2 global/local costmap의 observation_sources에 keepout_cloud를 추가하면
모든 차량이 동일한 금지구역을 costmap에 반영한다.

금지구역 감소(해제) 시:
  1. 빈 PointCloud2 발행 (clearing=False이므로 직접 소거는 불가)
  2. 전 차량 global/local costmap ClearEntireCostmap 서비스 호출
  → 1Hz 타이머로 현재 유효 구역 재마킹, LiDAR가 실제 장애물 복원
"""
import json
import struct

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from std_msgs.msg import String
from sensor_msgs.msg import PointCloud2, PointField
from nav2_msgs.srv import ClearEntireCostmap


_LATCHED = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)
_DEFAULT_VEHICLES = ['aip1', 'aip2', 'aip3']
_GRID_RES  = 0.05   # costmap resolution (m) — nav2_full.yaml resolution과 일치


class KeeputZoneNode(Node):
    def __init__(self) -> None:
        super().__init__('keepout_zone_node')
        self._zones: list[list[dict]] = []

        self.declare_parameter('vehicle_ids', _DEFAULT_VEHICLES)
        vehicles = list(self.get_parameter('vehicle_ids').get_parameter_value().string_array_value) \
                   or _DEFAULT_VEHICLES

        self._sub = self.create_subscription(
            String, '/fleet/keepout_zones', self._cb_zones, 10,
        )
        self._pub = self.create_publisher(PointCloud2, '/fleet/keepout_cloud', _LATCHED)

        self._clear_clients = []
        for vid in vehicles:
            for cmap in ['global_costmap', 'local_costmap']:
                svc = f'/{vid}/{cmap}/clear_entirely_{cmap}'
                self._clear_clients.append(self.create_client(ClearEntireCostmap, svc))

        self._timer = self.create_timer(1.0, self._publish_cloud)
        self.get_logger().info('keepout_zone_node 시작')

    # ── 콜백 ──────────────────────────────────────────────────────────────────

    def _cb_zones(self, msg: String) -> None:
        data = json.loads(msg.data)
        new_zones: list[list[dict]] = data.get('zones', [])
        shrunk = len(new_zones) < len(self._zones)
        self._zones = new_zones
        if shrunk:
            self._clear_costmaps()
        self._publish_cloud()
        self.get_logger().info(
            f'금지구역 업데이트: {len(self._zones)}개'
            + (' (costmap 초기화 요청)' if shrunk else '')
        )

    # ── 발행 ──────────────────────────────────────────────────────────────────

    def _publish_cloud(self) -> None:
        pts: list[tuple[float, float]] = []
        for zone in self._zones:
            pts.extend(self._fill_polygon(zone))

        cloud = PointCloud2()
        cloud.header.frame_id = 'map'
        cloud.header.stamp    = self.get_clock().now().to_msg()
        cloud.height          = 1
        cloud.width           = len(pts)
        cloud.fields = [
            PointField(name='x', offset=0,  datatype=PointField.FLOAT32, count=1),
            PointField(name='y', offset=4,  datatype=PointField.FLOAT32, count=1),
            PointField(name='z', offset=8,  datatype=PointField.FLOAT32, count=1),
        ]
        cloud.is_bigendian = False
        cloud.point_step   = 12
        cloud.row_step     = 12 * len(pts)
        cloud.is_dense     = True
        cloud.data         = b''.join(struct.pack('fff', x, y, 0.5) for x, y in pts)
        self._pub.publish(cloud)

    # ── 폴리곤 내부 격자 채우기 ───────────────────────────────────────────────

    def _fill_polygon(self, pts: list[dict]) -> list[tuple[float, float]]:
        if len(pts) < 3:
            return []
        xs = [p['x'] for p in pts]
        ys = [p['y'] for p in pts]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        half = _GRID_RES * 0.5
        result: list[tuple[float, float]] = []
        x = x0
        while x <= x1 + half:
            y = y0
            while y <= y1 + half:
                if self._inside(x, y, pts):
                    result.append((x, y))
                y += _GRID_RES
            x += _GRID_RES
        return result

    @staticmethod
    def _inside(px: float, py: float, polygon: list[dict]) -> bool:
        """Ray-casting 알고리즘으로 점이 폴리곤 안에 있는지 판별."""
        n = len(polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]['x'], polygon[i]['y']
            xj, yj = polygon[j]['x'], polygon[j]['y']
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    # ── costmap 초기화 ────────────────────────────────────────────────────────

    def _clear_costmaps(self) -> None:
        for client in self._clear_clients:
            if client.service_is_ready():
                client.call_async(ClearEntireCostmap.Request())


def main() -> None:
    rclpy.init()
    node = KeeputZoneNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
