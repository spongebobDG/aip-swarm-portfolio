#!/usr/bin/env python3
"""coverage_tracker_node.py — 플릿 순찰 커버리지 그리드 추적.

각 차량의 오도메트리 위치를 /map 격자에 마킹하여
탐색 가능 영역(free cell) 대비 방문 비율(커버리지 %)을 계산.

구독:
  /map                           nav_msgs/OccupancyGrid  (SLAM 제공 맵)
  /{vid}/odometry/filtered       nav_msgs/Odometry       (각 차량, 설정된 모든 vid)

발행:
  /fleet/coverage_grid           nav_msgs/OccupancyGrid  (방문 시각화, 0=미방문/50=방문/100=장애물)
  /fleet/coverage_pct            std_msgs/Float32        (전체 커버리지 %)
  /fleet/vehicle_coverage_pct    std_msgs/String         (차량별 JSON 상세)

Usage:
  ros2 run aip_fleet_gazebo coverage_tracker_node.py \\
      --ros-args -p vehicle_ids:=peer_2,peer_3 -p visit_radius_m:=0.3

  # Foxglove 에서 /fleet/coverage_grid 를 Map 패널로 시각화 가능
  ros2 topic echo /fleet/coverage_pct
  ros2 topic echo /fleet/vehicle_coverage_pct
"""
from __future__ import annotations

import json
from typing import Optional

import numpy as np
import rclpy
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.node import Node
from std_msgs.msg import Float32, String


class CoverageTrackerNode(Node):
    def __init__(self) -> None:
        super().__init__('coverage_tracker_node')

        self.declare_parameter('vehicle_ids',    'peer_2,peer_3')
        self.declare_parameter('visit_radius_m',  0.30)  # 방문 판정 반경 (m)
        self.declare_parameter('publish_hz',       1.0)

        ids_str = self.get_parameter('vehicle_ids').value
        self._vids   = [v.strip() for v in ids_str.split(',')]
        self._radius = float(self.get_parameter('visit_radius_m').value)

        # 맵 메타데이터
        self._res:    float = 0.05
        self._ox:     float = 0.0
        self._oy:     float = 0.0
        self._width:  int   = 0
        self._height: int   = 0
        self._coverage: Optional[np.ndarray] = None  # shape=(H,W), int8
        self._r_cells:  int = 1

        # 차량별 기여 셀 수
        self._veh_cells: dict[str, int] = {v: 0 for v in self._vids}

        # 발행자
        self._pub_pct    = self.create_publisher(Float32,       '/fleet/coverage_pct',         10)
        self._pub_grid   = self.create_publisher(OccupancyGrid, '/fleet/coverage_grid',         10)
        self._pub_detail = self.create_publisher(String,        '/fleet/vehicle_coverage_pct',  10)

        # 구독자
        self.create_subscription(OccupancyGrid, '/map', self._cb_map, 10)
        for vid in self._vids:
            self.create_subscription(
                Odometry, f'/{vid}/odometry/filtered',
                lambda msg, v=vid: self._cb_odom(msg, v), 10)

        hz = float(self.get_parameter('publish_hz').value)
        self.create_timer(1.0 / hz, self._publish)

        self.get_logger().info(
            f'coverage_tracker: vehicles={self._vids}  '
            f'visit_radius={self._radius}m  {hz:.0f}Hz')

    # ── 맵 수신 ─────────────────────────────────────────────────────────────

    def _cb_map(self, msg: OccupancyGrid) -> None:
        self._res    = msg.info.resolution
        self._width  = msg.info.width
        self._height = msg.info.height
        self._ox     = msg.info.origin.position.x
        self._oy     = msg.info.origin.position.y

        raw = np.array(msg.data, dtype=np.int8).reshape(self._height, self._width)

        if self._coverage is None:
            # 초기화: -1=미탐색, 0=미방문 free, 50=방문, 100=장애물
            self._coverage = np.where(raw < 0,   np.int8(-1),
                             np.where(raw >= 65,  np.int8(100),
                                                  np.int8(0))).astype(np.int8)
            self.get_logger().info(
                f'coverage_tracker: 맵 초기화  {self._width}×{self._height}  '
                f'res={self._res:.3f}m')
        else:
            # 새 장애물 업데이트 (기존 방문 정보 유지)
            new_obs = (raw >= 65)
            self._coverage[new_obs] = np.int8(100)

        self._r_cells = max(1, int(self._radius / self._res))

    # ── 오도메트리 수신 → 격자 마킹 ─────────────────────────────────────────

    def _cb_odom(self, msg: Odometry, vid: str) -> None:
        if self._coverage is None:
            return

        wx = msg.pose.pose.position.x
        wy = msg.pose.pose.position.y
        cx = int((wx - self._ox) / self._res)
        cy = int((wy - self._oy) / self._res)

        r  = self._r_cells
        y0 = max(0, cy - r)
        y1 = min(self._height - 1, cy + r)
        x0 = max(0, cx - r)
        x1 = min(self._width  - 1, cx + r)

        before = int(np.sum(self._coverage == 50))
        for row in range(y0, y1 + 1):
            for col in range(x0, x1 + 1):
                if self._coverage[row, col] == 0:
                    if (col - cx) ** 2 + (row - cy) ** 2 <= r * r:
                        self._coverage[row, col] = np.int8(50)
        after = int(np.sum(self._coverage == 50))
        self._veh_cells[vid] += after - before

    # ── 발행 ─────────────────────────────────────────────────────────────────

    def _publish(self) -> None:
        if self._coverage is None:
            return

        total_free    = int(np.sum(self._coverage >= 0) - np.sum(self._coverage == 100))
        total_visited = int(np.sum(self._coverage == 50))
        pct = 100.0 * total_visited / total_free if total_free > 0 else 0.0

        self._pub_pct.publish(Float32(data=float(pct)))

        pct_each = {
            v: round(100.0 * n / max(total_free, 1), 1)
            for v, n in self._veh_cells.items()
        }
        self._pub_detail.publish(String(data=json.dumps({
            'fleet_coverage_pct': round(pct, 1),
            'total_free_cells':   total_free,
            'visited_cells':      total_visited,
            'per_vehicle':        pct_each,
        })))

        # OccupancyGrid 시각화
        grid = OccupancyGrid()
        grid.header.stamp          = self.get_clock().now().to_msg()
        grid.header.frame_id       = 'map'
        grid.info.resolution       = self._res
        grid.info.width            = self._width
        grid.info.height           = self._height
        grid.info.origin.position.x = self._ox
        grid.info.origin.position.y = self._oy
        grid.data = self._coverage.flatten().tolist()
        self._pub_grid.publish(grid)

        self.get_logger().info(
            f'coverage: {pct:.1f}%  ({total_visited}/{total_free} cells)  ' +
            '  '.join(f'{v}:{pct_each[v]}%' for v in self._vids),
            throttle_duration_sec=10.0)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CoverageTrackerNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
