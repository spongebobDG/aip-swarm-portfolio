"""Bridge a standalone Vision Pi HTTP preview into AIP ROS topics.

This node is intentionally lightweight.  The Vision Pi keeps serving RGB and
thermal MJPEG/JPEG over HTTP, while this bridge publishes the small ROS side of
the contract: heartbeat, RGB compressed frames for central fusion, thermal
visualization, and WARN alerts from the Pi thermal status.
"""
from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urljoin
from urllib.request import urlopen

import cv2
import numpy as np
import rclpy
from aip_fleet_msgs.msg import FleetHeartbeat, PerceptionAlert
from geometry_msgs.msg import Point
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, Image

ALERT_WARN = 1


class VisionPiBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__('vision_pi_bridge')

        self.declare_parameter('vehicle_id', 'aip2')
        self.declare_parameter('base_url', 'http://192.168.0.108:8081')
        self.declare_parameter('status_path', '/status.json')
        self.declare_parameter('rgb_jpeg_path', '/rgb.jpg')
        self.declare_parameter('thermal_jpeg_path', '/thermal.jpg')
        self.declare_parameter('request_timeout_sec', 1.5)
        self.declare_parameter('heartbeat_hz', 1.0)
        self.declare_parameter('rgb_publish_hz', 2.0)
        self.declare_parameter('thermal_viz_hz', 2.0)
        self.declare_parameter('alert_check_hz', 2.0)
        self.declare_parameter('warn_temp_c', 45.0)
        self.declare_parameter('alert_cooldown_sec', 10.0)
        self.declare_parameter('publish_hotspot_bbox', True)
        self.declare_parameter('hotspot_bbox_px', 48)

        self._vehicle_id = str(self.get_parameter('vehicle_id').value)
        base_url = str(self.get_parameter('base_url').value).rstrip('/') + '/'
        self._status_url = urljoin(base_url, str(self.get_parameter('status_path').value).lstrip('/'))
        self._rgb_url = urljoin(base_url, str(self.get_parameter('rgb_jpeg_path').value).lstrip('/'))
        self._thermal_url = urljoin(base_url, str(self.get_parameter('thermal_jpeg_path').value).lstrip('/'))
        self._timeout = float(self.get_parameter('request_timeout_sec').value)
        self._warn_temp_c = float(self.get_parameter('warn_temp_c').value)
        self._alert_cooldown_sec = float(self.get_parameter('alert_cooldown_sec').value)
        self._publish_hotspot_bbox = bool(self.get_parameter('publish_hotspot_bbox').value)
        self._hotspot_bbox_px = int(self.get_parameter('hotspot_bbox_px').value)
        self._last_status: dict[str, Any] = {}
        self._last_alert_ts = 0.0

        self._pub_heartbeat = self.create_publisher(
            FleetHeartbeat, f'/{self._vehicle_id}/heartbeat', 10)
        self._pub_rgb = self.create_publisher(
            CompressedImage, f'/{self._vehicle_id}/image_raw/compressed', 5)
        self._pub_thermal_viz = self.create_publisher(
            Image, f'/{self._vehicle_id}/thermal_viz', 5)
        self._pub_alert = self.create_publisher(PerceptionAlert, '/fleet/alerts', 10)

        self._timer(self.get_parameter('heartbeat_hz').value, self._publish_heartbeat)
        self._timer(self.get_parameter('rgb_publish_hz').value, self._publish_rgb)
        self._timer(self.get_parameter('thermal_viz_hz').value, self._publish_thermal_viz)
        self._timer(self.get_parameter('alert_check_hz').value, self._check_alert)

        self.get_logger().info(
            f'vision_pi_bridge ready vehicle={self._vehicle_id} base={base_url}')

    def _timer(self, hz: float, callback) -> None:
        hz = max(float(hz), 0.01)
        self.create_timer(1.0 / hz, callback)

    def _fetch_bytes(self, url: str) -> bytes:
        with urlopen(url, timeout=self._timeout) as res:
            return res.read()

    def _fetch_status(self) -> dict[str, Any]:
        data = json.loads(self._fetch_bytes(self._status_url).decode('utf-8'))
        self._last_status = data
        return data

    def _status(self) -> dict[str, Any]:
        if self._last_status:
            return self._last_status
        return self._fetch_status()

    def _publish_heartbeat(self) -> None:
        ok = False
        status_text = 'vision_http_unreachable'
        try:
            status = self._fetch_status()
            ok = bool(status.get('ok', False))
            camera_err = status.get('camera', {}).get('last_error')
            thermal_err = status.get('thermal', {}).get('last_error')
            status_text = 'ok' if ok and not camera_err and not thermal_err else 'vision_sensor_error'
        except Exception as exc:
            self.get_logger().warn(f'status fetch failed: {exc}')

        msg = FleetHeartbeat()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.robot_id = self._vehicle_id
        msg.mode = 'manual'
        msg.healthy = ok
        msg.estop = False
        msg.heartbeat_stale = False
        msg.obstacle_stop = False
        msg.cmd_stale = False
        msg.battery_voltage = 0.0
        msg.battery_percentage = 0.0
        msg.status = status_text
        self._pub_heartbeat.publish(msg)

    def _publish_rgb(self) -> None:
        try:
            jpeg = self._fetch_bytes(self._rgb_url)
        except Exception as exc:
            self.get_logger().warn(f'rgb fetch failed: {exc}')
            return
        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = f'{self._vehicle_id}/rgb_camera'
        msg.format = 'jpeg'
        msg.data = jpeg
        self._pub_rgb.publish(msg)

    def _publish_thermal_viz(self) -> None:
        try:
            jpeg = self._fetch_bytes(self._thermal_url)
            arr = np.frombuffer(jpeg, dtype=np.uint8)
            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception as exc:
            self.get_logger().warn(f'thermal fetch failed: {exc}')
            return
        if bgr is None:
            return

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = f'{self._vehicle_id}/thermal_camera'
        msg.height = int(rgb.shape[0])
        msg.width = int(rgb.shape[1])
        msg.encoding = 'rgb8'
        msg.is_bigendian = False
        msg.step = int(rgb.shape[1] * 3)
        msg.data = rgb.tobytes()
        self._pub_thermal_viz.publish(msg)

    def _check_alert(self) -> None:
        try:
            status = self._fetch_status()
        except Exception:
            return

        monitor = status.get('monitor', {})
        thermal = status.get('thermal', {})
        max_c = float(monitor.get('max_c', thermal.get('max_c', 0.0)) or 0.0)
        threshold = float(monitor.get('threshold_c', self._warn_temp_c) or self._warn_temp_c)
        if max_c < max(self._warn_temp_c, threshold):
            return

        now = time.monotonic()
        if now - self._last_alert_ts < self._alert_cooldown_sec:
            return
        self._last_alert_ts = now

        rgb_w = int(status.get('camera', {}).get('preview_width', 400) or 400)
        rgb_h = int(status.get('camera', {}).get('preview_height', 300) or 300)
        hot_x = int(monitor.get('hot_x', thermal.get('hot_x', -1)) or -1)
        hot_y = int(monitor.get('hot_y', thermal.get('hot_y', -1)) or -1)
        hot_norm_x = float(monitor.get('hot_norm_x', thermal.get('hot_norm_x', 0.5)) or 0.5)
        hot_norm_y = float(monitor.get('hot_norm_y', thermal.get('hot_norm_y', 0.5)) or 0.5)
        center_x = int(max(0, min(rgb_w - 1, hot_norm_x * rgb_w)))
        center_y = int(max(0, min(rgb_h - 1, hot_norm_y * rgb_h)))
        bbox_px = max(2, self._hotspot_bbox_px)
        bbox_x = max(0, center_x - bbox_px // 2)
        bbox_y = max(0, center_y - bbox_px // 2)

        alert = PerceptionAlert()
        alert.header.stamp = self.get_clock().now().to_msg()
        alert.header.frame_id = f'{self._vehicle_id}/thermal_camera'
        alert.vehicle_id = self._vehicle_id
        alert.alert_level = ALERT_WARN
        alert.max_temp_c = max_c
        alert.thermal_zone = int(hot_y * 32 + hot_x) if hot_x >= 0 and hot_y >= 0 else -1
        alert.rgb_bbox_x = bbox_x if self._publish_hotspot_bbox else center_x
        alert.rgb_bbox_y = bbox_y if self._publish_hotspot_bbox else center_y
        alert.rgb_bbox_w = bbox_px if self._publish_hotspot_bbox else -1
        alert.rgb_bbox_h = bbox_px if self._publish_hotspot_bbox else -1
        alert.confidence = 0.0
        alert.map_position = Point()
        self._pub_alert.publish(alert)
        self.get_logger().warn(
            f'[{self._vehicle_id}] thermal WARN temp={max_c:.1f}C '
            f'hot=({hot_x},{hot_y}) rgb=({center_x},{center_y})')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = VisionPiBridgeNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
