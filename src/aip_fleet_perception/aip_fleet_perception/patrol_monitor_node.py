"""patrol_monitor_node.py — Pi 4 측 1차 이상징후 필터 노드.

역할:
  - 열화상 최고온도 임계값 초과 시 즉시 WARN/HIGH 경보 발행
  - 연속 n 프레임 초과 필터로 오경보 억제
  - 열화상 → RGB 좌표 변환 (호모그래피 적용)
  - TF lookup으로 열원 map_position 추정 (estimated_hotspot_distance_m 파라미터)

구독:  /{vehicle_id}/thermal_raw   (sensor_msgs/Image 32FC1)
발행:  /fleet/alerts               (aip_fleet_msgs/PerceptionAlert)
       /{vehicle_id}/thermal_viz   (sensor_msgs/Image RGB8, 시각화용)
"""
from __future__ import annotations

import math
import os

import numpy as np
import rclpy
import rclpy.duration
import rclpy.time
import tf2_ros
import yaml
from ament_index_python.packages import get_package_share_directory
from aip_fleet_msgs.msg import PerceptionAlert
from geometry_msgs.msg import Point
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import ColorRGBA

THERMAL_COLS = 32
THERMAL_ROWS = 24
FOV_H_RAD    = math.radians(110.0)
FOV_V_RAD    = math.radians(75.0)
HALF_H       = FOV_H_RAD / 2.0
HALF_V       = FOV_V_RAD / 2.0
_TF_TIMEOUT  = 0.05   # s

ALERT_NONE = 0
ALERT_WARN = 1
ALERT_HIGH = 2


class PatrolMonitorNode(Node):
    def __init__(self) -> None:
        super().__init__('patrol_monitor')

        self.declare_parameter('vehicle_id',                  'peer_1')
        self.declare_parameter('warn_temp_c',                 60.0)
        self.declare_parameter('high_temp_c',                 80.0)
        self.declare_parameter('fire_temp_c',                150.0)
        self.declare_parameter('consecutive_frames',           3)
        self.declare_parameter('calibration_file',            '')
        self.declare_parameter('estimated_hotspot_distance_m', 3.0)

        vid              = self.get_parameter('vehicle_id').value
        self._warn_t     = self.get_parameter('warn_temp_c').value
        self._high_t     = self.get_parameter('high_temp_c').value
        self._fire_t     = self.get_parameter('fire_temp_c').value
        self._consec_req = self.get_parameter('consecutive_frames').value
        self._est_dist   = self.get_parameter('estimated_hotspot_distance_m').value

        self._consecutive = 0
        self._homography  = self._load_homography()

        self._tf_buf = tf2_ros.Buffer()
        self._tf_lis = tf2_ros.TransformListener(self._tf_buf, self)

        self.create_subscription(Image, f'/{vid}/thermal_raw', self._cb_thermal, 10)
        self._pub_alert = self.create_publisher(PerceptionAlert, '/fleet/alerts', 10)
        self._pub_viz   = self.create_publisher(Image, f'/{vid}/thermal_viz', 10)
        self._vid       = vid
        self.get_logger().info(
            f'patrol_monitor ready  vehicle={vid}  warn={self._warn_t}°C  '
            f'est_dist={self._est_dist}m')

    def _load_homography(self) -> np.ndarray | None:
        cal_file = self.get_parameter('calibration_file').value
        if not cal_file:
            try:
                share = get_package_share_directory('aip_fleet_perception')
                cal_file = os.path.join(share, 'config', 'calibration.yaml')
            except Exception:
                return None
        try:
            with open(cal_file) as f:
                cfg = yaml.safe_load(f)
            if not cfg.get('homography_thermal_to_rgb', {}).get('calibrated', False):
                self.get_logger().warn('Homography not calibrated — using FOV scale only')
                return None
            data = cfg['homography_thermal_to_rgb']['data']
            return np.array(data, dtype=np.float64).reshape(3, 3)
        except Exception as e:
            self.get_logger().warn(f'calibration load failed: {e}')
            return None

    def _estimate_map_position(self, hot_col: int, hot_row: int) -> Point:
        """열화상 픽셀 위치 → 맵 프레임 추정 좌표.

        FOV 각도 + 차량 yaw + 추정 거리로 ray projection.
        depth 정보가 없으므로 estimated_hotspot_distance_m 파라미터 사용.
        """
        pt = Point()
        try:
            tf = self._tf_buf.lookup_transform(
                'map', f'{self._vid}/base_link',
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=_TF_TIMEOUT))
        except (tf2_ros.LookupException,
                tf2_ros.ConnectivityException,
                tf2_ros.ExtrapolationException):
            return pt

        t   = tf.transform
        vx  = t.translation.x
        vy  = t.translation.y
        vcz = t.translation.z + 0.15   # 센서 마운트 높이 (m)

        q   = t.rotation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                         1.0 - 2.0 * (q.y * q.y + q.z * q.z))

        # 픽셀 → 열화상 FOV 각도 (col=0 → 좌 -55°, col=31 → 우 +55°)
        ang_h = (hot_col / (THERMAL_COLS - 1) - 0.5) * FOV_H_RAD
        # row=0 → 위 +37.5°, row=23 → 아래 -37.5° (카메라 +z = 위쪽)
        ang_v = (0.5 - hot_row / (THERMAL_ROWS - 1)) * FOV_V_RAD

        # 맵 프레임 방위각 = 차량 yaw + 수평 FOV 오프셋
        map_bearing  = yaw + ang_h
        # xy 평면 투영 거리 = 추정 거리 / cos(수직각)
        d_xy = self._est_dist / max(math.cos(ang_v), 0.1)

        pt.x = vx  + d_xy * math.cos(map_bearing)
        pt.y = vy  + d_xy * math.sin(map_bearing)
        pt.z = vcz + self._est_dist * math.tan(ang_v)
        return pt

    def _thermal_to_rgb(self, col: int, row: int,
                        rgb_w: int = 1280, rgb_h: int = 960) -> tuple[int, int]:
        if self._homography is not None:
            import cv2
            pt = np.array([[[float(col), float(row)]]], dtype=np.float32)
            dst = cv2.perspectiveTransform(pt, self._homography.astype(np.float32))
            return int(dst[0, 0, 0]), int(dst[0, 0, 1])

        # 미캘리브레이션: FOV 비율 스케일 + 중앙 정렬
        scale   = 110.0 / 130.0          # thermal_fov / rgb_fov
        off_x   = rgb_w * (1.0 - scale) / 2.0
        off_y   = rgb_h * (1.0 - scale) / 2.0
        u = int(off_x + col * (rgb_w * scale) / THERMAL_COLS)
        v = int(off_y + row * (rgb_h * scale) / THERMAL_ROWS)
        return u, v

    def _cb_thermal(self, msg: Image) -> None:
        arr = np.frombuffer(bytes(msg.data), dtype=np.float32).reshape(
            THERMAL_ROWS, THERMAL_COLS)

        max_temp = float(arr.max())
        hot_idx  = int(arr.argmax())
        hot_row  = hot_idx // THERMAL_COLS
        hot_col  = hot_idx %  THERMAL_COLS

        # 연속 프레임 필터
        if max_temp >= self._warn_t:
            self._consecutive += 1
        else:
            self._consecutive = 0

        if self._consecutive < self._consec_req:
            self._publish_viz(arr)
            return

        # 경보 레벨 결정
        if max_temp >= self._fire_t:
            level = ALERT_HIGH
        elif max_temp >= self._high_t:
            level = ALERT_WARN   # 시각 미확인 → WARN (메인 PC가 HIGH 승격)
        else:
            level = ALERT_WARN

        u, v        = self._thermal_to_rgb(hot_col, hot_row)
        map_pos     = self._estimate_map_position(hot_col, hot_row)

        alert = PerceptionAlert()
        alert.header.stamp    = msg.header.stamp
        alert.header.frame_id = 'map'
        alert.vehicle_id      = self._vid
        alert.alert_level     = level
        alert.max_temp_c      = max_temp
        alert.thermal_zone    = hot_idx
        alert.rgb_bbox_x      = u
        alert.rgb_bbox_y      = v
        alert.rgb_bbox_w      = -1       # 메인 PC에서 채움
        alert.rgb_bbox_h      = -1
        alert.confidence      = 0.0      # 메인 PC에서 채움
        alert.map_position    = map_pos  # TF 기반 추정값

        self._pub_alert.publish(alert)
        self.get_logger().warn(
            f'[{self._vid}] ALERT lv={level} temp={max_temp:.1f}°C '
            f'zone=({hot_col},{hot_row}) '
            f'map=({map_pos.x:.2f},{map_pos.y:.2f})')

        self._publish_viz(arr, hot_row, hot_col, level)

    def _publish_viz(self, arr: np.ndarray,
                     hot_row: int = -1, hot_col: int = -1,
                     level: int = ALERT_NONE) -> None:
        import cv2
        a = np.asarray(arr, dtype=np.float32)
        a = np.nan_to_num(a, nan=float(np.nanmean(a)) if np.isfinite(a).any() else 25.0)
        # 온도 색역: 2~98 퍼센타일 오토스케일(이상치/데드픽셀 robust) — PR #9 thermal_to_bgr 동일.
        finite = a[np.isfinite(a)]
        if finite.size:
            vmin = float(np.percentile(finite, 2)); vmax = float(np.percentile(finite, 98))
        else:
            vmin, vmax = 20.0, 40.0
        if vmax - vmin < 2.0:                       # 거의 균일 → 색역 좁아짐 방지
            mid = (vmax + vmin) / 2.0; vmin, vmax = mid - 1.0, mid + 1.0
        norm  = np.clip((a - vmin) / (vmax - vmin), 0.0, 1.0)
        small = (norm * 255.0).astype(np.uint8)
        heat  = cv2.applyColorMap(small, cv2.COLORMAP_INFERNO)        # BGR (방향은 드라이버에서 처리됨)
        rgb   = np.ascontiguousarray(heat[:, :, ::-1])                # BGR → RGB8

        viz = Image()
        viz.header.stamp    = self.get_clock().now().to_msg()
        viz.header.frame_id = 'thermal_frame'
        viz.height   = a.shape[0]
        viz.width    = a.shape[1]
        viz.encoding = 'rgb8'
        viz.step     = a.shape[1] * 3
        viz.data     = rgb.tobytes()
        self._pub_viz.publish(viz)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PatrolMonitorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
