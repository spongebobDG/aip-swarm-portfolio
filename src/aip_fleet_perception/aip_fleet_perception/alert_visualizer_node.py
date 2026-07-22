"""alert_visualizer_node.py — /fleet/alerts → RViz MarkerArray 변환.

/fleet/alerts (PerceptionAlert) 를 구독하여 탐지된 열원 위치를
RViz에서 볼 수 있는 마커로 변환 발행.

발행:
  /fleet/alert_markers   visualization_msgs/MarkerArray
    - WARN: 주황색 구체 (map_position 기반)
    - HIGH: 빨간색 구체 + 텍스트 레이블

마커 수명: 10초 (연속 경보 시 갱신)
"""
from __future__ import annotations

import math

import rclpy
from rclpy.node import Node
from aip_fleet_msgs.msg import PerceptionAlert
from visualization_msgs.msg import Marker, MarkerArray
from std_msgs.msg import ColorRGBA
from geometry_msgs.msg import Vector3

ALERT_NONE = 0
ALERT_WARN = 1
ALERT_HIGH = 2

_MARKER_LIFETIME_SEC = 10.0
_SPHERE_SCALE        = 0.5   # 구체 지름 (m)
_TEXT_Z_OFFSET       = 0.8   # 텍스트 마커 높이 오프셋 (m)

# 차량별 고유 마커 ID 기반값
_VID_BASE = {'peer_1': 0, 'peer_2': 100, 'peer_3': 200}


class AlertVisualizerNode(Node):
    def __init__(self) -> None:
        super().__init__('alert_visualizer')

        self.declare_parameter('vehicle_ids', ['peer_1', 'peer_2', 'peer_3'])

        self._vids = list(self.get_parameter('vehicle_ids').value)

        self.create_subscription(
            PerceptionAlert, '/fleet/alerts', self._cb_alert, 10)
        self._pub = self.create_publisher(
            MarkerArray, '/fleet/alert_markers', 10)

        # 노드 시작 시 이전 세션 잔여 마커 제거 (0.5s 후 1회)
        self._deleteall_timer = self.create_timer(0.5, self._send_deleteall)

        self.get_logger().info(
            f'alert_visualizer ready  vehicles={self._vids}')

    def _send_deleteall(self) -> None:
        arr = MarkerArray()
        m = Marker()
        m.action = Marker.DELETEALL
        arr.markers.append(m)
        self._pub.publish(arr)
        self.destroy_timer(self._deleteall_timer)

    def _cb_alert(self, msg: PerceptionAlert) -> None:
        if msg.alert_level == ALERT_NONE:
            return

        vid = msg.vehicle_id
        base_id = _VID_BASE.get(vid, 300)
        now = self.get_clock().now().to_msg()

        # 마커 색상 (WARN=주황, HIGH=빨강)
        if msg.alert_level == ALERT_HIGH:
            color = ColorRGBA(r=1.0, g=0.0, b=0.0, a=0.8)
        else:
            color = ColorRGBA(r=1.0, g=0.55, b=0.0, a=0.7)

        # ── 구체 마커 (열원 위치) ──────────────────────────────────────────
        sphere = Marker()
        sphere.header.stamp    = now
        sphere.header.frame_id = 'map'
        sphere.ns              = f'alert_{vid}'
        sphere.id              = base_id
        sphere.type            = Marker.SPHERE
        sphere.action          = Marker.ADD
        sphere.pose.position.x = msg.map_position.x
        sphere.pose.position.y = msg.map_position.y
        sphere.pose.position.z = max(msg.map_position.z, 0.25)
        sphere.pose.orientation.w = 1.0
        sphere.scale           = Vector3(x=_SPHERE_SCALE, y=_SPHERE_SCALE, z=_SPHERE_SCALE)
        sphere.color           = color
        sphere.lifetime.sec    = int(_MARKER_LIFETIME_SEC)

        # ── 텍스트 마커 (온도 + 신뢰도) ──────────────────────────────────
        label_text = (
            f'{vid}: {msg.max_temp_c:.0f}°C'
            + (f' conf={msg.confidence:.2f}' if msg.confidence > 0 else '')
        )
        text = Marker()
        text.header.stamp    = now
        text.header.frame_id = 'map'
        text.ns              = f'alert_text_{vid}'
        text.id              = base_id + 1
        text.type            = Marker.TEXT_VIEW_FACING
        text.action          = Marker.ADD
        text.pose.position.x = msg.map_position.x
        text.pose.position.y = msg.map_position.y
        text.pose.position.z = max(msg.map_position.z, 0.25) + _TEXT_Z_OFFSET
        text.pose.orientation.w = 1.0
        text.scale.z         = 0.3   # 텍스트 높이
        text.color           = ColorRGBA(r=1.0, g=1.0, b=1.0, a=1.0)
        text.text            = label_text
        text.lifetime.sec    = int(_MARKER_LIFETIME_SEC)

        arr = MarkerArray()
        arr.markers.extend([sphere, text])
        self._pub.publish(arr)

        self.get_logger().info(
            f'marker published: {label_text} @ '
            f'({msg.map_position.x:.2f},{msg.map_position.y:.2f})')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = AlertVisualizerNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
