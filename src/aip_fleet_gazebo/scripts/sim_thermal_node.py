#!/usr/bin/env python3
"""sim_thermal_node.py — MLX90640 열화상 카메라 시뮬레이터.

시뮬 세계의 열원 위치 + 차량 TF 를 이용하여
실제 MLX90640 센서와 동일한 토픽을 발행한다.
thermal_driver_node.py 를 대체 (실차에서는 실제 드라이버 사용).

알고리즘:
  1. /sim/heat_sources 에서 활성 열원 목록 수신
  2. TF: map → peer_N/base_link 로 카메라 pose 획득
  3. 각 열원에 대해:
     a. 카메라 좌표계로 변환 (차량 전방이 +x)
     b. 수평/수직 각도 계산 → 110°/75° FOV 내부 여부 확인
     c. 해당 열상 픽셀 범위에 가우시안 분포로 온도 기여
     d. 거리 기반 감쇠 (inverse square)
  4. 배경 온도 + 노이즈 합산 후 발행

구독:
  /sim/heat_sources   std_msgs/Float32MultiArray
  /sim/active_scenario  std_msgs/String  (NORMAL 시 열원 없음)

발행: (thermal_driver_node.py 와 동일 인터페이스)
  /{vehicle_id}/thermal_raw   sensor_msgs/Image  (32FC1, °C)
  /{vehicle_id}/thermal_temp  std_msgs/Float32   (최고온도)
"""
from __future__ import annotations

import math
import os

import numpy as np
import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Float32, Float32MultiArray, String
from tf2_ros import Buffer, TransformListener

FIELDS      = 5          # x, y, z, temp_c, radius_m per source
COLS        = 32
ROWS        = 24
FOV_H_RAD   = math.radians(110.0)
FOV_V_RAD   = math.radians(75.0)
HALF_H      = FOV_H_RAD / 2.0
HALF_V      = FOV_V_RAD / 2.0
# 픽셀 중심 각도 (수평: 왼쪽 -55° ~ 오른쪽 +55°)
_COL_ANGLES = np.linspace(-HALF_H, HALF_H, COLS)
_ROW_ANGLES = np.linspace(-HALF_V, HALF_V, ROWS)


class SimThermalNode(Node):
    def __init__(self) -> None:
        super().__init__('sim_thermal')

        self.declare_parameter('vehicle_ids',   ['peer_1', 'peer_2', 'peer_3'])
        self.declare_parameter('publish_hz',    8.0)
        self.declare_parameter('config_file',   '')

        self._vids = self.get_parameter('vehicle_ids').value
        hz         = self.get_parameter('publish_hz').value

        cfg_file = self.get_parameter('config_file').value
        if not cfg_file:
            share = get_package_share_directory('aip_fleet_gazebo')
            cfg_file = os.path.join(share, 'config', 'heat_sources.yaml')
        with open(cfg_file) as f:
            cfg = yaml.safe_load(f)
        self._physics  = cfg['physics']
        self._ambient  = self._physics.get('ambient_temp_c',   25.0)
        self._amb_sd   = self._physics.get('ambient_noise_sd',  0.5)
        self._sens_sd  = self._physics.get('sensor_noise_sd',   0.3)

        self._tf_buf = Buffer()
        self._tf_lis = TransformListener(self._tf_buf, self)

        # 활성 열원 목록 [x, y, z, temp_c, radius_m, ...]
        self._sources: list[float] = []
        self._scenario = 'NORMAL'

        self.create_subscription(
            Float32MultiArray, '/sim/heat_sources', self._cb_sources, 10)
        self.create_subscription(
            String, '/sim/active_scenario', self._cb_scenario, 10)

        self._pubs_raw:  dict[str, object] = {}
        self._pubs_temp: dict[str, object] = {}
        for vid in self._vids:
            self._pubs_raw[vid]  = self.create_publisher(
                Image,   f'/{vid}/thermal_raw',  10)
            self._pubs_temp[vid] = self.create_publisher(
                Float32, f'/{vid}/thermal_temp', 10)

        self.create_timer(1.0 / hz, self._tick)
        self.get_logger().info(f'sim_thermal ready  vehicles={self._vids}')

    def _cb_sources(self, msg: Float32MultiArray) -> None:
        self._sources = list(msg.data)

    def _cb_scenario(self, msg: String) -> None:
        self._scenario = msg.data

    # ── 메인 루프 ──────────────────────────────────────────────────────────
    def _tick(self) -> None:
        for vid in self._vids:
            try:
                # thermal_frame (서보암 끝단) 우선, 없으면 base_link 폴백
                try:
                    tf: TransformStamped = self._tf_buf.lookup_transform(
                        'map', f'{vid}/thermal_frame', rclpy.time.Time())
                    cz_offset = 0.0
                except Exception:
                    tf = self._tf_buf.lookup_transform(
                        'map', f'{vid}/base_link', rclpy.time.Time())
                    cz_offset = 0.15   # 암 미사용 시 기존 오프셋
            except Exception:
                continue

            cx = tf.transform.translation.x
            cy = tf.transform.translation.y
            cz = tf.transform.translation.z + cz_offset

            # 센서 yaw 추출 (서보암 포함 시 arm_pan 반영됨)
            q  = tf.transform.rotation
            yaw = math.atan2(
                2.0 * (q.w * q.z + q.x * q.y),
                1.0 - 2.0 * (q.y * q.y + q.z * q.z))

            frame = self._render(cx, cy, cz, yaw)
            self._publish(vid, frame)

    # ── 열화상 렌더링 ──────────────────────────────────────────────────────
    def _render(self, cx: float, cy: float, cz: float,
                yaw: float) -> np.ndarray:
        arr = np.full((ROWS, COLS),
                      self._ambient, dtype=np.float32)
        arr += np.random.normal(0.0, self._amb_sd,
                                (ROWS, COLS)).astype(np.float32)

        n = len(self._sources) // FIELDS
        for i in range(n):
            base = i * FIELDS
            sx, sy, sz = (self._sources[base],
                          self._sources[base + 1],
                          self._sources[base + 2])
            temp   = self._sources[base + 3]
            radius = self._sources[base + 4]

            # 맵 프레임 → 카메라 프레임 (차량 전방 +x, 좌 +y, 상 +z)
            dx = sx - cx
            dy = sy - cy
            dz = sz - cz
            # yaw 회전
            fwd  =  dx * math.cos(yaw) + dy * math.sin(yaw)
            left = -dx * math.sin(yaw) + dy * math.cos(yaw)
            up   = dz

            if fwd <= 0.05:      # 후방 또는 너무 가까움
                continue

            dist   = math.sqrt(fwd * fwd + left * left + up * up)
            ang_h  = math.atan2(left, fwd)   # 수평 각도 (좌+ = CCW)
            ang_v  = math.atan2(up,   fwd)   # 수직 각도 (위+)

            if abs(ang_h) > HALF_H or abs(ang_v) > HALF_V:
                continue

            # 열원의 픽셀 좌표 (중심)
            col_f = (ang_h + HALF_H) / FOV_H_RAD * (COLS - 1)
            row_f = (ang_v + HALF_V) / FOV_V_RAD * (ROWS - 1)

            # 픽셀 당 각도
            px_ang_h = FOV_H_RAD / COLS
            px_ang_v = FOV_V_RAD / ROWS

            # 열원 시야각 반경 → 픽셀 수
            ang_radius = math.atan(radius / max(dist, 0.01))
            spread_h   = ang_radius / px_ang_h
            spread_v   = ang_radius / px_ang_v

            # 거리 감쇠 (1/d² 기반, 최대온도 제한)
            peak_temp = min(temp, self._ambient + temp /
                            max(1.0, dist * dist * 0.3))

            # 가우시안 분포로 픽셀 기여
            col_min = max(0, int(col_f - spread_h * 2))
            col_max = min(COLS - 1, int(col_f + spread_h * 2))
            row_min = max(0, int(row_f - spread_v * 2))
            row_max = min(ROWS - 1, int(row_f + spread_v * 2))

            for r in range(row_min, row_max + 1):
                for c in range(col_min, col_max + 1):
                    d_h = (c - col_f) / max(spread_h, 0.5)
                    d_v = (r - row_f) / max(spread_v, 0.5)
                    w   = math.exp(-0.5 * (d_h * d_h + d_v * d_v))
                    contribution = (peak_temp - self._ambient) * w
                    if arr[r, c] < self._ambient + contribution:
                        arr[r, c] = self._ambient + contribution

        arr += np.random.normal(0.0, self._sens_sd,
                                (ROWS, COLS)).astype(np.float32)
        return arr

    # ── 발행 ───────────────────────────────────────────────────────────────
    def _publish(self, vid: str, arr: np.ndarray) -> None:
        now = self.get_clock().now().to_msg()

        img = Image()
        img.header.stamp    = now
        img.header.frame_id = f'{vid}/thermal_frame'
        img.height   = ROWS
        img.width    = COLS
        img.encoding = '32FC1'
        img.step     = COLS * 4
        img.data     = arr.tobytes()
        self._pubs_raw[vid].publish(img)

        self._pubs_temp[vid].publish(Float32(data=float(arr.max())))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SimThermalNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
