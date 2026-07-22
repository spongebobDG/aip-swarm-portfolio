"""central_fusion_node.py — 메인 PC RGB+열화상 융합 및 YOLOv8 추론 노드.

역할:
  - patrol_monitor_node 가 발행한 WARN 경보 수신
  - 해당 차량의 RGB 이미지에서 YOLOv8로 화재/연기 탐지
  - 열화상 + RGB 결과 융합 → 신뢰도 계산
  - HIGH 경보 확정 시 /fleet/alerts 재발행 (confidence, bbox, map_position 채움)
  - TF로 차량 위치 조회 → map_position 계산

구독:
  /fleet/alerts                          (aip_fleet_msgs/PerceptionAlert, Pi 4 발행)
  /{vehicle_id}/image_raw/compressed     (sensor_msgs/CompressedImage)

발행:
  /fleet/alerts                          (aip_fleet_msgs/PerceptionAlert, 융합 결과)
  /fleet/perception_viz/{vehicle_id}     (sensor_msgs/CompressedImage, 시각화)

요구사항 (메인 PC):
  pip install ultralytics opencv-python
"""
from __future__ import annotations

import threading
from collections import deque

import cv2
import numpy as np
import rclpy
from aip_fleet_msgs.msg import PerceptionAlert
from geometry_msgs.msg import Point
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage

try:
    from ultralytics import YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False

ALERT_NONE = 0
ALERT_WARN = 1
ALERT_HIGH = 2

# YOLOv8 클래스명 (fire/smoke 사전학습 모델 기준)
_FIRE_CLASSES  = {'fire', 'flame'}
_SMOKE_CLASSES = {'smoke'}


class CentralFusionNode(Node):
    def __init__(self) -> None:
        super().__init__('central_fusion')

        self.declare_parameter('vehicle_ids',        ['aip1', 'aip2', 'aip3'])
        self.declare_parameter('model_path',         'yolov8n.pt')
        self.declare_parameter('fire_confidence',    0.55)
        self.declare_parameter('smoke_confidence',   0.50)
        self.declare_parameter('high_temp_c',        80.0)
        # 카메라 압축 토픽 템플릿 ({vid} 치환). camera_driver.launch.py 는 arm/ 하위로 발행.
        self.declare_parameter('image_topic',        '/{vid}/arm/image_raw/compressed')
        # 라이브 영상피드 재발행 주파수(Hz, 0=비활성) + 다운스케일 폭(px, 0=원본)
        self.declare_parameter('viz_stream_hz',      6.0)
        self.declare_parameter('viz_max_width',      640)
        # 카메라 물리 장착 회전 보정(0/90/180/270°). camera_ros orientation 미동작 보완.
        self.declare_parameter('image_rotate',       0)

        self._vids      = self.get_parameter('vehicle_ids').value
        model_path      = self.get_parameter('model_path').value
        self._fire_thr  = self.get_parameter('fire_confidence').value
        self._smoke_thr = self.get_parameter('smoke_confidence').value
        self._high_t    = self.get_parameter('high_temp_c').value
        self._img_tmpl  = self.get_parameter('image_topic').value
        self._viz_hz    = float(self.get_parameter('viz_stream_hz').value)
        self._viz_w     = int(self.get_parameter('viz_max_width').value)
        self._rotate_code = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                             270: cv2.ROTATE_90_COUNTERCLOCKWISE}.get(
                                 int(self.get_parameter('image_rotate').value) % 360, None)

        self._model  = self._load_model(model_path)
        self._lock   = threading.Lock()

        # 차량별 최신 RGB 프레임 버퍼
        self._rgb_buf: dict[str, np.ndarray | None] = {v: None for v in self._vids}

        # 차량별 미처리 경보 큐
        self._alert_q: dict[str, deque] = {v: deque(maxlen=5) for v in self._vids}

        # 차량별 최신 경보 오버레이 상태(bbox/level/temp/conf, TTL 3s) — 스트림 타이머가 그림
        self._overlay: dict[str, dict | None] = {v: None for v in self._vids}

        self._sub_alerts = self.create_subscription(
            PerceptionAlert, '/fleet/alerts', self._cb_alert, 10)

        for vid in self._vids:
            topic = self._img_tmpl.format(vid=vid)
            self.create_subscription(
                CompressedImage,
                topic,
                lambda msg, v=vid: self._cb_image(msg, v),
                5)
            self.get_logger().info(f'[{vid}] RGB 구독: {topic}')

        self._pub_alert = self.create_publisher(PerceptionAlert, '/fleet/alerts', 10)
        self._pub_viz: dict[str, object] = {
            v: self.create_publisher(
                CompressedImage, f'/fleet/perception_viz/{v}', 5)
            for v in self._vids
        }

        self.create_timer(0.1, self._process_queue)
        # 라이브 영상피드: 최신 RGB 프레임을 상시 재발행(YOLO 무관). 0Hz면 비활성.
        if self._viz_hz > 0.0:
            self.create_timer(1.0 / self._viz_hz, self._stream_viz)
        self.get_logger().info(
            f'central_fusion ready  vehicles={self._vids}  '
            f'yolo={_YOLO_AVAILABLE}')

    def _load_model(self, path: str):
        if not _YOLO_AVAILABLE:
            self.get_logger().warn('ultralytics not installed — visual check disabled')
            return None
        try:
            model = YOLO(path)
            self.get_logger().info(f'YOLOv8 loaded: {path}')
            return model
        except Exception as e:
            self.get_logger().error(f'YOLO load failed: {e}')
            return None

    def _cb_image(self, msg: CompressedImage, vid: str) -> None:
        buf = np.frombuffer(bytes(msg.data), dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is not None and self._rotate_code is not None:
            img = cv2.rotate(img, self._rotate_code)
        with self._lock:
            self._rgb_buf[vid] = img

    def _cb_alert(self, msg: PerceptionAlert) -> None:
        # 이미 메인 PC가 발행한 HIGH 경보는 재처리하지 않음
        if msg.confidence > 0.0:
            return
        vid = msg.vehicle_id
        if vid in self._alert_q:
            self._alert_q[vid].append(msg)

    def _process_queue(self) -> None:
        for vid in self._vids:
            if not self._alert_q[vid]:
                continue
            alert: PerceptionAlert = self._alert_q[vid].popleft()
            with self._lock:
                rgb = self._rgb_buf.get(vid)

            if rgb is None:
                self.get_logger().debug(f'{vid}: RGB not yet available, skip')
                continue

            self._fuse_and_publish(alert, rgb, vid)

    def _fuse_and_publish(self, alert: PerceptionAlert,
                          rgb: np.ndarray, vid: str) -> None:
        h, w = rgb.shape[:2]
        bx, by, bw, bh = alert.rgb_bbox_x, alert.rgb_bbox_y, -1, -1
        roi_cx, roi_cy = bx, by
        if alert.rgb_bbox_w > 0 and alert.rgb_bbox_h > 0:
            roi_cx = alert.rgb_bbox_x + alert.rgb_bbox_w // 2
            roi_cy = alert.rgb_bbox_y + alert.rgb_bbox_h // 2

        # YOLOv8 추론 (roi: 열화상 대응 영역 중심 ±200px)
        roi_x1 = max(0, roi_cx - 200)
        roi_y1 = max(0, roi_cy - 200)
        roi_x2 = min(w, roi_cx + 200)
        roi_y2 = min(h, roi_cy + 200)
        roi = rgb[roi_y1:roi_y2, roi_x1:roi_x2]

        visual_conf = 0.0
        if self._model is not None and roi.size > 0:
            results = self._model(roi, verbose=False)
            for r in results:
                for box in r.boxes:
                    cls_name = r.names[int(box.cls)].lower()
                    conf     = float(box.conf)
                    if cls_name in _FIRE_CLASSES and conf >= self._fire_thr:
                        visual_conf = max(visual_conf, conf)
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        bx = roi_x1 + x1
                        by = roi_y1 + y1
                        bw = x2 - x1
                        bh = y2 - y1
                    elif cls_name in _SMOKE_CLASSES and conf >= self._smoke_thr:
                        visual_conf = max(visual_conf, conf * 0.8)

        # 융합 신뢰도: 열화상 온도 기여 + 시각 탐지 기여
        temp_score   = min(1.0, (alert.max_temp_c - 60.0) / 90.0)  # 60→0, 150→1
        fused_conf   = 0.4 * temp_score + 0.6 * visual_conf

        level = ALERT_WARN
        if alert.max_temp_c >= 150.0 or fused_conf >= 0.6:
            level = ALERT_HIGH
        elif fused_conf < 0.2 and alert.max_temp_c < self._high_t:
            return  # 신뢰도 낮음 → 발행 생략

        out = PerceptionAlert()
        out.header        = alert.header
        out.vehicle_id    = vid
        out.alert_level   = level
        out.max_temp_c    = alert.max_temp_c
        out.thermal_zone  = alert.thermal_zone
        out.rgb_bbox_x    = bx
        out.rgb_bbox_y    = by
        out.rgb_bbox_w    = bw
        out.rgb_bbox_h    = bh
        out.confidence    = fused_conf
        out.map_position  = Point()  # TF 조회로 채울 수 있음 (추후 확장)

        self._pub_alert.publish(out)
        self.get_logger().warn(
            f'[{vid}] FUSED lv={level} temp={alert.max_temp_c:.1f}°C '
            f'vis={visual_conf:.2f} conf={fused_conf:.2f}')

        # 라이브 스트림 타이머가 그릴 경보 오버레이 상태 갱신(TTL 3s)
        self._overlay[vid] = {
            'bbox':  (out.rgb_bbox_x, out.rgb_bbox_y, out.rgb_bbox_w, out.rgb_bbox_h),
            'level': out.alert_level,
            'temp':  out.max_temp_c,
            'conf':  out.confidence,
            'ts':    self.get_clock().now().nanoseconds * 1e-9,
        }

    def _stream_viz(self) -> None:
        """최신 RGB 프레임(+있으면 경보 오버레이)을 /fleet/perception_viz/{vid} 로 상시 재발행.

        YOLO 추론과 무관하게 viz_stream_hz 주기로 호출돼 대시보드 박스 A 에 라이브 영상을 공급.
        """
        now = self.get_clock().now().nanoseconds * 1e-9
        for vid in self._vids:
            with self._lock:
                rgb = self._rgb_buf.get(vid)
            if rgb is None:
                continue
            vis = rgb.copy()
            ov = self._overlay.get(vid)
            if ov is not None and now - ov['ts'] < 3.0:
                color = (0, 0, 255) if ov['level'] == ALERT_HIGH else (0, 165, 255)
                bx, by, bw, bh = ov['bbox']
                if bw > 0:
                    cv2.rectangle(vis, (bx, by), (bx + bw, by + bh), color, 2)
                cv2.putText(vis, f"{vid} {ov['temp']:.0f}C conf={ov['conf']:.2f}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            else:
                cv2.putText(vis, vid, (10, 28),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            # 대시보드 썸네일용 다운스케일(대역폭 절감)
            h, w = vis.shape[:2]
            if self._viz_w > 0 and w > self._viz_w:
                vis = cv2.resize(vis, (self._viz_w, int(h * self._viz_w / w)),
                                 interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode('.jpg', vis, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ok:
                continue
            msg = CompressedImage()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.format       = 'jpeg'
            msg.data         = buf.tobytes()
            self._pub_viz[vid].publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CentralFusionNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
