#!/usr/bin/env python3
"""Adapt temporary UDP vehicle status packets into standard fleet topics."""
from __future__ import annotations

import json
import math
import os
import socket
import threading
import time
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

from aip_fleet_msgs.msg import FleetHeartbeat, PeerPose, PeerPoseArray


def _csv_env(name: str, default: str) -> list[str]:
    values = [item.strip().strip('/') for item in os.environ.get(name, default).split(',')]
    return [item for item in values if item]


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ('1', 'true', 'yes', 'y', 'on'):
        return True
    if text in ('0', 'false', 'no', 'n', 'off'):
        return False
    return default


def vehicle_id_from_payload(payload: dict[str, Any]) -> str:
    return str(
        payload.get('vehicle_id')
        or payload.get('robot_id')
        or payload.get('id')
        or ''
    ).strip().strip('/')


def mode_from_payload(payload: dict[str, Any]) -> str:
    """'autonomous' or 'manual' from various payload field names."""
    mode = str(payload.get('mode', '')).strip().lower()
    if 'auto' in mode:
        return 'autonomous'
    state = str(payload.get('state', '')).strip().upper()
    if state in ('AUTO', 'AUTONOMOUS'):
        return 'autonomous'
    return 'manual'


def battery_from_payload(payload: dict[str, Any]) -> tuple[float, float]:
    """Return (voltage, percentage). percentage는 0.0–100.0 범위로 클램핑."""
    voltage = _float(payload.get('battery_voltage', 0.0), 0.0)
    pct = payload.get(
        'battery_percentage',
        payload.get('battery_pct', payload.get('battery', 0.0)),
    )
    percentage = max(0.0, min(100.0, _float(pct, 0.0)))
    return voltage, percentage


def cpu_load_from_payload(payload: dict[str, Any]) -> float:
    """CPU 부하를 0.0–1.0 범위로 정규화.

    입력이 1.0 초과이면 퍼센트(0–100) 로 간주해 100으로 나눈다.
    예) {'cpu': 43} → 0.43,  {'cpu': 0.5} → 0.5,  {'cpu': 120} → 1.0
    """
    raw = payload.get('cpu_load', payload.get('cpu', 0.0))
    value = _float(raw, 0.0)
    if value > 1.0:
        value /= 100.0
    return max(0.0, min(1.0, value))


def behaviors_from_payload(payload: dict[str, Any]) -> list[str]:
    """active_behaviors 목록을 FleetHeartbeat 스키마 한계에 맞게 클램핑.

    FleetHeartbeat.msg: string<=64[<=8] active_behaviors
    behaviors 리스트를 최대 7개로 자른 뒤 status 문자열을 마지막에 추가(중복 제외).
    """
    items: list[str] = []
    for b in payload.get('behaviors', []):
        items.append(str(b)[:64])
    status = str(payload.get('status', '')).strip()
    if status and status not in items:
        items.append(status[:64])
    return items[:8]


def heartbeat_from_payload(vehicle_id: str, payload: dict[str, Any], stamp: Any) -> FleetHeartbeat:
    msg = FleetHeartbeat()
    msg.header.stamp = stamp
    msg.header.frame_id = vehicle_id
    msg.robot_id = vehicle_id
    msg.mode = mode_from_payload(payload)
    msg.healthy = _bool(payload.get('healthy'), True)
    msg.estop = _bool(payload.get('estop'), False)
    msg.heartbeat_stale = False
    msg.obstacle_stop = _bool(payload.get('obstacle_stop'), False)
    msg.cmd_stale = _bool(payload.get('cmd_stale'), False)
    msg.battery_voltage, msg.battery_percentage = battery_from_payload(payload)
    msg.status = str(payload.get('status', 'ok')).strip() or 'ok'
    return msg


def _quat_to_yaw(x: float, y: float, z: float, w: float) -> float:
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def _pose_source(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw = payload.get('pose')
    if isinstance(raw, dict):
        return raw
    if any(key in payload for key in ('x', 'y', 'pose_x', 'pose_y')):
        return payload
    return None


def peer_pose_from_payload(vehicle_id: str, payload: dict[str, Any]) -> PeerPose | None:
    raw = _pose_source(payload)
    if raw is None:
        return None

    position = raw.get('position') if isinstance(raw.get('position'), dict) else {}
    orientation = raw.get('orientation') if isinstance(raw.get('orientation'), dict) else {}

    x_value = raw.get('x', raw.get('pose_x', position.get('x')))
    y_value = raw.get('y', raw.get('pose_y', position.get('y')))
    if x_value is None or y_value is None:
        return None

    yaw_value = raw.get('yaw_rad', raw.get('yaw', raw.get('theta', raw.get('pose_yaw'))))
    if yaw_value is None and orientation:
        yaw = _quat_to_yaw(
            _float(orientation.get('x'), 0.0),
            _float(orientation.get('y'), 0.0),
            _float(orientation.get('z'), 0.0),
            _float(orientation.get('w'), 1.0),
        )
    else:
        yaw = _float(yaw_value, 0.0)

    pose = PeerPose()
    pose.vehicle_id = vehicle_id
    pose.pose.position.x = _float(x_value, 0.0)
    pose.pose.position.y = _float(y_value, 0.0)
    pose.pose.position.z = _float(raw.get('z', raw.get('pose_z', position.get('z'))), 0.0)
    pose.pose.orientation.x = 0.0
    pose.pose.orientation.y = 0.0
    pose.pose.orientation.z = math.sin(yaw / 2.0)
    pose.pose.orientation.w = math.cos(yaw / 2.0)
    pose.covariance_xy_m = max(
        0.0,
        _float(raw.get('covariance_xy_m', payload.get('covariance_xy_m', 0.0)), 0.0),
    )
    return pose


class UdpStatusHeartbeatAdapter(Node):
    """Receive UDP JSON status and publish team-main fleet messages."""

    def __init__(self) -> None:
        super().__init__('udp_status_heartbeat_adapter')
        self._vehicles = set(_csv_env('AIP_DASHBOARD_VEHICLES', 'aip1,aip2,aip3'))
        self._port = int(os.environ.get('AIP_UDP_HEARTBEAT_ADAPTER_PORT', '19051'))
        self._bind_host = os.environ.get('AIP_UDP_HEARTBEAT_ADAPTER_HOST', '0.0.0.0')
        self._enabled = os.environ.get(
            'AIP_UDP_HEARTBEAT_ADAPTER_ENABLE', '1'
        ).strip().lower() not in ('0', 'false', 'no', 'off')

        heartbeat_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        pose_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        self._pubs = {
            vid: self.create_publisher(FleetHeartbeat, f'/{vid}/heartbeat', heartbeat_qos)
            for vid in sorted(self._vehicles)
        }
        self._pose_pub = self.create_publisher(PeerPoseArray, '/fleet/peer_poses', pose_qos)
        self._latest_poses: dict[str, tuple[PeerPose, float]] = {}
        self._pose_timeout_sec = _float(os.environ.get('AIP_UDP_POSE_TIMEOUT_SEC'), 5.0)
        self._sock: socket.socket | None = None
        if not self._enabled:
            self.get_logger().info('UDP heartbeat adapter disabled')
            return
        self._start_listener()

    def _start_listener(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self._bind_host, self._port))
            sock.settimeout(0.5)
        except OSError as exc:
            self.get_logger().error(
                f'UDP heartbeat adapter bind failed on {self._bind_host}:{self._port}: {exc}'
            )
            return
        self._sock = sock
        threading.Thread(target=self._loop, daemon=True).start()
        self.get_logger().info(
            f'UDP heartbeat adapter listening on {self._bind_host}:{self._port} '
            f'for {sorted(self._vehicles)}'
        )

    def _loop(self) -> None:
        sock = self._sock
        if sock is None:
            return
        while rclpy.ok():
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                payload = json.loads(data.decode('utf-8'))
            except Exception:
                continue
            if isinstance(payload, dict):
                self._publish_payload(payload)

    def _publish_payload(self, payload: dict[str, Any]) -> None:
        vid = vehicle_id_from_payload(payload)
        if vid not in self._pubs:
            return

        msg = heartbeat_from_payload(vid, payload, self.get_clock().now().to_msg())
        self._pubs[vid].publish(msg)

        pose = peer_pose_from_payload(vid, payload)
        if pose is not None:
            self._latest_poses[vid] = (pose, time.monotonic())
        self._publish_pose_array()

    def _publish_pose_array(self) -> None:
        now = time.monotonic()
        self._latest_poses = {
            vid: pose_entry
            for vid, pose_entry in self._latest_poses.items()
            if now - pose_entry[1] <= self._pose_timeout_sec
        }

        msg = PeerPoseArray()
        msg.stamp = self.get_clock().now().to_msg()
        msg.poses = [latest_pose for latest_pose, _pose_ts in self._latest_poses.values()][:8]
        self._pose_pub.publish(msg)
