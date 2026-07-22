#!/usr/bin/env python3
"""AIP Fleet Central Dashboard — FastAPI + rclpy WebSocket bridge."""
from __future__ import annotations

import asyncio
import base64
import datetime
import io
import json
import math
import os
import socket
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

import rclpy
import rclpy.time
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy, HistoryPolicy
import tf2_ros
from geometry_msgs.msg import Twist, PoseStamped, PoseWithCovarianceStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from nav2_msgs.action import NavigateToPose
from std_msgs.msg import Bool, Float32, String, UInt8MultiArray
from std_srvs.srv import Trigger
from sensor_msgs.msg import BatteryState, CompressedImage, LaserScan
from sensor_msgs.msg import Image as RosImage

from aip_fleet_msgs.msg import (
    FleetStatus,
    OverrideCommand,
    PeerPoseArray,
    PerceptionAlert,
)

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from ament_index_python.packages import get_package_share_directory

# ── Constants ─────────────────────────────────────────────────────────────
def _csv_env(name: str, default: str) -> list[str]:
    values = [item.strip().strip('/') for item in os.environ.get(name, default).split(',')]
    return [item for item in values if item]


def _alias_env(name: str, default: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for item in os.environ.get(name, default).split(','):
        item = item.strip()
        if not item:
            continue
        if '=' in item:
            display_id, topic_id = item.split('=', 1)
        else:
            display_id, topic_id = item, item
        display_id = display_id.strip().strip('/')
        topic_id = topic_id.strip().strip('/')
        if display_id and topic_id:
            aliases[display_id] = topic_id
    return aliases


def _stream_env(name: str, default: str) -> dict[str, str]:
    streams: dict[str, str] = {}
    for item in os.environ.get(name, default).split(','):
        item = item.strip()
        if not item or '=' not in item:
            continue
        vehicle_id, url = item.split('=', 1)
        vehicle_id = vehicle_id.strip().strip('/')
        url = url.strip()
        if vehicle_id and url:
            streams[vehicle_id] = url
    return streams


def _int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(float(raw))
    except ValueError:
        value = int(default)
    return max(min_value, min(max_value, value))


_VEHICLES = _csv_env(
    'AIP_DASHBOARD_VEHICLES',
    'aip1,aip2,aip3',
)
_VEHICLE_TOPIC_ALIASES = _alias_env(
    'AIP_VEHICLE_TOPIC_ALIASES',
    'aip1=aip1,aip2=aip2,aip3=aip3',
)
for _vid in _VEHICLES:
    _VEHICLE_TOPIC_ALIASES.setdefault(_vid, _vid)
_TOPIC_TO_DISPLAY = {
    topic_id: display_id for display_id, topic_id in _VEHICLE_TOPIC_ALIASES.items()
}
_VISION_STREAM_URLS = _stream_env('AIP_VISION_STREAM_URLS', '')
_THERMAL_STREAM_URLS = _stream_env('AIP_THERMAL_STREAM_URLS', '')
_VISION_POLL_MS = _int_env('AIP_VISION_POLL_MS', 0, 0, 3000)
_RGB_POLL_MS = _int_env('AIP_RGB_POLL_MS', _VISION_POLL_MS, 0, 2000)
_THERMAL_POLL_MS = _int_env('AIP_THERMAL_POLL_MS', _VISION_POLL_MS, 0, 3000)
_LEGACY_TOPIC_TO_DISPLAY: dict[str, str] = {
    # /main 네임스페이스는 aip1 토픽 트리 통일(2026-06-27)로 폐기됨.
}

# 차량별 수동 cmd_vel 토픽 오버라이드 (표준 /<ns>/override_cmd_vel 대신 사용)
# aip1: /aip1 namespace + twist_mux central 슬롯 topic=central_cmd_vel → /aip1/central_cmd_vel
_VEHICLE_CMD_VEL_OVERRIDES: dict[str, str] = _alias_env(
    'AIP_VEHICLE_CMD_VEL_OVERRIDES',
    'aip1=/aip1/central_cmd_vel',
)

# 차량별 속도 한계 (수동 제어 클램핑)
# 한계를 초과하는 명령은 거부 대신 한계값까지 허용
_VEHICLE_VEL_LIMITS: dict[str, tuple[float, float]] = {
    'aip1': (0.30, 1.0),   # (max_linear m/s, max_angular rad/s)
    'aip2': (0.30, 1.0),
    'aip3': (0.30, 1.0),
}
_DEFAULT_VEL_LIMIT = (0.30, 1.0)

# 차량별 LaserScan 토픽 오버라이드
# 전 차량 /<ns>/scan 으로 통일됨(2026-06-28 클린 재작업). aip3도 /aip3/scan 발행.
_VEHICLE_SCAN_OVERRIDES: dict[str, str] = {
    'aip1': '/aip1/scan',
    'aip3': '/aip3/scan',
}

# 배터리 모니터링 모듈 보유 차량 → BatteryState 토픽 (실 게이지).
# 미보유 차량은 게이지 null → 프런트에서 "N/A"(0%와 구별) 표시.
_VEHICLE_BATTERY_TOPIC: dict[str, str] = {
    'aip2': '/battery_state',   # TurtleBot3 OpenCR (실 배터리)
}
_battery_pct: dict[str, tuple] = {}  # vid -> (monotonic_ts, percentage 0-100), 실모듈 차량만
_BATTERY_TTL_SEC = 15.0  # 이보다 오래 BatteryState 미수신이면 stale → N/A (스택 다운/캐시 방지)


def _battery_for(vid: str):
    """실모듈 차량은 최신 퍼센트(stale·미수신 시 None), 미보유 차량은 None → 프런트 N/A."""
    if vid in _VEHICLE_BATTERY_TOPIC:
        entry = _battery_pct.get(vid)
        if entry and (time.monotonic() - entry[0]) <= _BATTERY_TTL_SEC:
            return entry[1]
    return None

# ESP32 리셋 — fleet_main launch 재시작으로 시리얼 포트를 닫았다 열어 DTR 토글
_ESP32_RESET_SSH_TARGETS: dict[str, tuple[str, str, str]] = {
    'aip1': ('jh', '192.168.0.3', 'AIP1_SSH_PASSWORD'),
}

# 서보암(4축 MG996R) — aip1 전용. 대시보드가 /{ns}/servo_cmd(UInt8MultiArray deg×4)로
# 직접 발행 → serial_bridge → PKT_SERVO → ESP32 PWM (구동모터 cmd_vel 과 동일하게 상시 가능).
_ARM_VEHICLE = os.environ.get('AIP_ARM_VEHICLE', 'aip1').strip().strip('/')
_ARM_SERVO_N = 4   # firmware PKT_SERVO 페이로드 = 4바이트
# 관절별 방향 반전(서보 장착 방향이 대시보드 직관과 반대일 때 명령각=180-deg).
# 베이스(joint 0): 슬라이더/패드 방향이 실제 동작과 반전돼 있어 보정.
# 단일 지점(대시보드)이라 펌웨어/브리지 무수정 + 수동·프리셋 모두 일관 보정.
# (주: aip1 arm_scan_node 자동스캔은 차량측에서 servo_cmd 를 직접 발행하므로 이 보정을
#  거치지 않는다 → 자동스캔 베이스 방향까지 통일하려면 브리지/펌웨어 reverse 로 이전.)
_ARM_REVERSED = (True, False, False, False)

_FLEET_MAIN_RESTART_SCRIPT = r"""
set -e
pkill -f 'ros2 launch aip_bringup fleet_main' 2>/dev/null || true
sleep 1.5
source /opt/ros/humble/setup.bash
source ~/aip_ws/install/setup.bash
export ROS_DOMAIN_ID=42 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DISCOVERY_SERVER=192.168.0.10:11811
export FASTRTPS_DEFAULT_PROFILES_FILE=$HOME/aip_ws/install/aip_bringup/share/aip_bringup/config/fastdds_client_profile.xml
nohup ros2 launch aip_bringup fleet_main.launch.py with_base:=true > /tmp/fleet_main.log 2>&1 &
printf 'Launch PID=%s\n' "$!"
sleep 4
pgrep -f aip_serial_bridge > /dev/null && printf 'SERIAL_OK\n' || printf 'SERIAL_FAIL\n'
"""


def _ssh_esp32_reset_blocking(vid: str) -> tuple[bool, str]:
    import shlex
    info = _ESP32_RESET_SSH_TARGETS.get(vid)
    if info is None:
        return False, f'{vid}: ESP32 reset not supported (aip1 only)'
    user, host, pw_env = info
    pw = os.environ.get(pw_env, '')
    b64 = base64.b64encode(_FLEET_MAIN_RESTART_SCRIPT.encode()).decode()
    ssh_cmd = [
        'ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=12',
        '-o', 'BatchMode=yes',
    ]
    if not pw or not pw.strip():
        ssh_cmd += ['-o', 'PasswordAuthentication=no']
    ssh_cmd += [f'{user}@{host}', f'base64 -d <<< {shlex.quote(b64)} | bash']
    try:
        r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=40)
        ok = 'SERIAL_OK' in r.stdout
        return ok, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, 'SSH timeout (40s)'
    except Exception as exc:
        return False, str(exc)


def _topic_id(vehicle_id: str) -> str:
    vid = str(vehicle_id).strip().strip('/')
    return _VEHICLE_TOPIC_ALIASES.get(vid, vid)


def _display_id(vehicle_id: str) -> str:
    vid = str(vehicle_id).strip().strip('/')
    return _TOPIC_TO_DISPLAY.get(vid, _LEGACY_TOPIC_TO_DISPLAY.get(vid, vid))


def _normalize_vehicle_map(data: dict) -> dict:
    return {
        _display_id(str(key)): value
        for key, value in data.items()
        if str(key).strip().strip('/')
    }


_MAP_SOURCES = tuple(['map_static', 'map'] + list(_VEHICLES))
_STATIC_DIR  = Path(get_package_share_directory('aip_fleet_dashboard')) / 'static'
_MAP_DIR     = Path.home() / 'aip_maps'
_DOCK_FILE   = Path.home() / 'aip_maps' / 'dock_positions.json'
_POSE_CAL_FILE = Path.home() / 'aip_maps' / 'pose_calibrations.json'

_LATCHED_QOS = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)
_MAP_VOLATILE_QOS = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.VOLATILE,
    reliability=ReliabilityPolicy.RELIABLE,
)
_SENSOR_QOS = QoSProfile(
    depth=5,
    durability=DurabilityPolicy.VOLATILE,
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
)

# ── Shared state ───────────────────────────────────────────────────────────
_clients:        set[WebSocket]            = set()
_main_loop:      asyncio.AbstractEventLoop | None = None
_ros_node:       'DashboardNode | None'   = None
_state_cache:    dict[str, Any]           = {}
# 일회성 이벤트 — _state_cache 에 넣지 않음(접속/새로고침 시 재전송돼 재발사되는 것 방지).
# 알림은 라이브 스트림으로만 전달; 새 클라이언트는 다음 실제 이벤트부터 수신.
_EVENT_TYPES: set[str] = {'alert'}
_bag_process:    subprocess.Popen | None  = None
_dock_positions:    dict[str, dict]  = {}
_pose_calibrations: dict[str, dict]  = {}
_keepout_zones_file = Path.home() / 'aip_maps' / 'keepout_zones.json'
_thermal_viz_ts: dict[str, float]        = {}  # 2Hz throttle per vehicle
_thermal_spots_ts: dict[str, float]      = {}  # 4Hz throttle per vehicle (최고/최저온 심부)
_scan_ts:        dict[str, float]        = {}  # 2Hz throttle per vehicle


def _load_dock_positions() -> None:
    global _dock_positions
    try:
        if _DOCK_FILE.exists():
            _dock_positions = _normalize_vehicle_map(json.loads(_DOCK_FILE.read_text()))
    except Exception:
        _dock_positions = {}
    _state_cache['dock_positions'] = {'type': 'dock_positions', 'positions': _dock_positions}


def _save_dock_positions() -> None:
    try:
        _DOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        _DOCK_FILE.write_text(json.dumps(_dock_positions, ensure_ascii=False))
    except Exception:
        pass


def _load_pose_calibrations() -> None:
    global _pose_calibrations
    try:
        if _POSE_CAL_FILE.exists():
            data = json.loads(_POSE_CAL_FILE.read_text())
            _pose_calibrations = {
                _display_id(str(k)): v for k, v in data.items()
                if isinstance(v, dict)
                and all(key in v for key in ('tx', 'ty', 'yaw_offset'))
            }
    except Exception:
        _pose_calibrations = {}
    _state_cache['pose_calibrations'] = {
        'type': 'pose_calibrations',
        'calibrations': _pose_calibrations,
    }


def _save_pose_calibrations() -> None:
    try:
        _POSE_CAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        _POSE_CAL_FILE.write_text(json.dumps(_pose_calibrations, ensure_ascii=False))
    except Exception:
        pass


def _normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def _load_keepout_zones() -> list:
    try:
        if _keepout_zones_file.exists():
            return json.loads(_keepout_zones_file.read_text())
    except Exception:
        pass
    return []


def _save_keepout_zones(zones: list) -> None:
    try:
        _keepout_zones_file.parent.mkdir(parents=True, exist_ok=True)
        _keepout_zones_file.write_text(json.dumps(zones, ensure_ascii=False))
    except Exception:
        pass


# ── Helpers ────────────────────────────────────────────────────────────────

def _quat_to_yaw(qx: float, qy: float, qz: float, qw: float) -> float:
    siny = 2.0 * (qw * qz + qx * qy)
    cosy = 1.0 - 2.0 * (qy * qy + qz * qz)
    return math.atan2(siny, cosy)


def _occupancy_grid_to_png_b64(msg: OccupancyGrid) -> str:
    w, h = msg.info.width, msg.info.height
    data = np.array(msg.data, dtype=np.int8).reshape((h, w))
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    free     = data == 0
    occupied = data > 0
    unknown  = data < 0
    rgba[free,     0] = 240; rgba[free,     1] = 245; rgba[free,     2] = 250; rgba[free,     3] = 255
    rgba[occupied, 0] = 40;  rgba[occupied, 1] = 40;  rgba[occupied, 2] = 40;  rgba[occupied, 3] = 255
    rgba[unknown,  0] = 180; rgba[unknown,  1] = 185; rgba[unknown,  2] = 190; rgba[unknown,  3] = 200
    buf = io.BytesIO()
    Image.fromarray(rgba, mode='RGBA').save(buf, format='PNG', optimize=False)
    return base64.b64encode(buf.getvalue()).decode('ascii')


async def _broadcast(msg: dict[str, Any]) -> None:
    if not _clients:
        return
    data = json.dumps(msg, ensure_ascii=False)
    dead: set[WebSocket] = set()
    for ws in list(_clients):
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


def _push(msg: dict[str, Any]) -> None:
    if _main_loop is None or _main_loop.is_closed():
        return
    t = msg.get('type')
    if t and t not in _EVENT_TYPES:
        _state_cache[t] = msg
    _main_loop.call_soon_threadsafe(_main_loop.create_task, _broadcast(msg))


def _start_bag() -> None:
    global _bag_process
    if _bag_process and _bag_process.poll() is None:
        return
    name = f'aip_{datetime.datetime.now():%Y%m%d_%H%M%S}'
    topics = [
        '/fleet/status', '/fleet/peer_poses', '/fleet/alerts',
        '/fleet/control_lock_state', '/map', '/map_static',
        '/fleet/coverage_pct',
    ]
    for vid in _VEHICLES:
        topic_id = _topic_id(vid)
        topics.extend([
            f'/{topic_id}/heartbeat',
            f'/{topic_id}/scan',
            f'/{topic_id}/odom',
            f'/{topic_id}/map',
            f'/{topic_id}/cmd_vel',
            f'/{topic_id}/override_cmd_vel',
        ])
    _bag_process = subprocess.Popen(
        ['ros2', 'bag', 'record', '-o', f'/tmp/{name}'] + topics,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    _push({'type': 'bag_state', 'recording': True, 'name': name})


def _stop_bag() -> None:
    global _bag_process
    if _bag_process:
        _bag_process.terminate()
        _bag_process = None
    _push({'type': 'bag_state', 'recording': False, 'name': ''})


# ── ROS2 Node ──────────────────────────────────────────────────────────────

class DashboardNode(Node):

    _STATE_NAMES = ['IDLE', 'AUTO', 'MANUAL', 'ESTOP', 'FAULT']
    _ALERT_NAMES = ['NONE', 'WARN', 'HIGH']

    def __init__(self) -> None:
        super().__init__('aip_dashboard_server')

        # ── Publishers ────────────────────────────────────────────────────
        self._estop_pubs = {
            vid: self.create_publisher(Bool, f'/{_topic_id(vid)}/estop', 10)
            for vid in _VEHICLES
        }
        # Nav2/AMCL 초기 위치추정 — '지도 위치 보정'이 절대 맵 포즈를 여기에 발행(map 프레임).
        self._initialpose_pubs = {
            vid: self.create_publisher(
                PoseWithCovarianceStamped, f'/{_topic_id(vid)}/initialpose', 10)
            for vid in _VEHICLES
        }
        self._override_twist_pubs = {
            vid: self.create_publisher(
                Twist,
                _VEHICLE_CMD_VEL_OVERRIDES.get(vid, f'/{_topic_id(vid)}/override_cmd_vel'),
                10,
            )
            for vid in _VEHICLES
        }
        self._goal_pubs = {
            vid: self.create_publisher(PoseStamped, f'/{_topic_id(vid)}/goal_pose', 10)
            for vid in _VEHICLES
        }
        self._mode_pubs = {
            vid: self.create_publisher(String, f'/{_topic_id(vid)}/mode', 10)
            for vid in _VEHICLES
        }
        self._nav_clients = {
            vid: ActionClient(self, NavigateToPose, f'/{_topic_id(vid)}/navigate_to_pose')
            for vid in _VEHICLES
        }
        self._override_pub     = self.create_publisher(OverrideCommand, '/fleet/override', 10)
        self._control_lock_pub = self.create_publisher(String, '/fleet/control_lock', 10)
        self._scenario_pub     = self.create_publisher(String, '/sim/set_scenario', 10)
        self._map_ready_pub    = self.create_publisher(Bool, '/fleet/map_ready', _LATCHED_QOS)
        self._patrol_cmd_pub   = self.create_publisher(String, '/patrol_planner/cmd', 10)
        self._keepout_pub      = self.create_publisher(String, '/fleet/keepout_zones', 10)
        # 서보암(aip1) 수동 제어: servo_cmd 직접 발행 + 자동 스캔/스토우 트리거.
        _arm_ns = _topic_id(_ARM_VEHICLE)
        self._arm_servo_pub = self.create_publisher(UInt8MultiArray, f'/{_arm_ns}/servo_cmd', 10)
        self._arm_scan_pub  = self.create_publisher(Bool, f'/{_arm_ns}/arm/scan_request', 10)
        self._arm_estop_pub = self.create_publisher(Bool, f'/{_arm_ns}/arm/estop', 10)
        self._udp_cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_cmd_targets = self._load_udp_command_targets()
        self._udp_nav_targets = self._load_udp_nav_targets()
        self._udp_status_ttl_sec = float(os.environ.get('AIP_UDP_STATUS_TTL_SEC', '4.0'))
        self._udp_status_by_vehicle: dict[str, tuple[float, dict[str, Any]]] = {}
        self._start_udp_status_listener()
        self._start_ping_status_monitors()

        # ── Subscribers ───────────────────────────────────────────────────
        self.create_subscription(FleetStatus,    '/fleet/status',              self._cb_status,     10)
        self.create_subscription(PerceptionAlert,'/fleet/alerts',              self._cb_alert,      10)
        self.create_subscription(String,         '/fleet/coverage_pct',        self._cb_coverage,   10)
        self.create_subscription(String,         '/fleet/vehicle_coverage_pct',self._cb_vcoverage,  10)
        self.create_subscription(Bool,           '/fleet/map_ready',           self._cb_map_ready,  _LATCHED_QOS)
        # map / map_static 소스별로 분리 구독 — 어느 토픽이 나중에 와도 소스 태그 유지.
        # source는 항상 dashboard 표시 ID(aip1/aip2/aip3)를 사용하고, topic은
        # AIP_VEHICLE_TOPIC_ALIASES에 따라 현재 실차 토픽(scout_1/scout_2 등)을 본다.
        self.create_subscription(OccupancyGrid, '/map',
            lambda m, s='map': self._cb_map(m, s), _LATCHED_QOS)
        self.create_subscription(OccupancyGrid, '/map_static',
            lambda m, s='map_static': self._cb_map(m, s), _LATCHED_QOS)
        # topic_id ≠ display_id인 alias 환경에서는 양쪽을 모두 등록해 데이터 유실 방지.
        # /dashboard/map도 구독 — slam_toolbox가 발행하는 실제 토픽 경로.
        map_topics: dict[str, str] = {}
        for display_id in _VEHICLES:
            topic_id = _topic_id(display_id)
            map_topics[f'/{topic_id}/map'] = display_id
            map_topics[f'/{topic_id}/dashboard/map'] = display_id
            if topic_id != display_id:
                map_topics[f'/{display_id}/map'] = display_id
                map_topics[f'/{display_id}/dashboard/map'] = display_id
        for topic, source in sorted(map_topics.items()):
            # 차량 map 토픽: VOLATILE 구독 — dashboard_adapter(VOLATILE) + slam_toolbox(TRANSIENT_LOCAL) 모두 호환
            # TRANSIENT_LOCAL pub + VOLATILE sub = 호환; VOLATILE pub + TRANSIENT_LOCAL sub = 비호환
            self.create_subscription(
                OccupancyGrid, topic,
                lambda m, s=source: self._cb_map(m, s), _MAP_VOLATILE_QOS)
        self.create_subscription(PeerPoseArray,  '/fleet/peer_poses',          self._cb_poses,      _LATCHED_QOS)
        self.create_subscription(String,         '/fleet/control_lock_state',  self._cb_lock_state, _LATCHED_QOS)
        self.create_subscription(String,         '/patrol_planner/plan_state', self._cb_plan_state, _LATCHED_QOS)

        self._patrol_running: dict[str, bool] = {}
        self._active_map_source: str                    = 'map_static'
        self._map_cache:         dict[str, dict | None] = {s: None for s in _MAP_SOURCES}
        self._map_grid_cache:    dict[str, OccupancyGrid | None] = {s: None for s in _MAP_SOURCES}
        self._thermal:    dict[str, float]          = {}
        self._odom_dist:  dict[str, float]          = {}
        self._odom_prev:  dict[str, tuple | None]   = {}
        self._odom_pose:  dict[str, dict]           = {}
        self._odom_pose_ts: dict[str, float]        = {}
        self._latest_raw_pose: dict[str, dict]      = {}
        self._keepout_zones: list[list[dict]]       = []   # [[{x,y}, ...], ...]
        self._registered_vids: set[str]             = set()
        self._tf_vehicle_ids: list[str]             = list(_VEHICLES)

        for vid in _VEHICLES:
            self._register_vehicle(vid)

        self._save_cli = self.create_client(Trigger, '/save_map_now')

        # TF fallback for autonomous mode (no coordinator publishing /fleet/peer_poses)
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)
        self._fleet_poses_active = False
        self.create_timer(0.2, self._cb_tf_poses)
        self._load_saved_map_static(push=False)

        self.get_logger().info('AIP Dashboard server started → http://localhost:8080')

    # ── Vehicle registration ───────────────────────────────────────────────

    def _register_vehicle(self, vid: str) -> None:
        """새 차량 발견 시 구독·상태 딕셔너리 초기화. 중복 호출 안전."""
        if vid in self._registered_vids:
            return
        self._registered_vids.add(vid)
        self._patrol_running.setdefault(vid, False)
        self._odom_dist.setdefault(vid, 0.0)
        self._odom_prev.setdefault(vid, None)
        if vid not in self._tf_vehicle_ids:
            self._tf_vehicle_ids.append(vid)
        topic_id = _topic_id(vid)
        self.create_subscription(
            String, f'/{topic_id}/patrol_status',
            lambda msg, v=vid: self._cb_patrol_status(msg, v), _LATCHED_QOS,
        )
        self.create_subscription(
            Float32, f'/{topic_id}/thermal_temp',
            lambda msg, v=vid: self._cb_thermal(msg, v), 10,
        )
        self.create_subscription(
            CompressedImage, f'/fleet/perception_viz/{vid}',
            lambda msg, v=vid: self._cb_vision(msg, v), 10,
        )
        if topic_id != vid:
            self.create_subscription(
                CompressedImage, f'/fleet/perception_viz/{topic_id}',
                lambda msg, v=vid: self._cb_vision(msg, v), 10,
            )
        self.create_subscription(
            RosImage, f'/{topic_id}/thermal_viz',
            lambda msg, v=vid: self._cb_thermal_viz(msg, v), 10,
        )
        # 열상 원본(32FC1, 24×32, 방향보정됨) → 최고/최저온 심부 좌표+온도 계산용
        self.create_subscription(
            RosImage, f'/{topic_id}/thermal_raw',
            lambda msg, v=vid: self._cb_thermal_raw(msg, v), 10,
        )
        self.create_subscription(
            Odometry, f'/{topic_id}/odom',
            lambda msg, v=vid: self._cb_odom(msg, v), 10,
        )
        scan_topic = _VEHICLE_SCAN_OVERRIDES.get(vid, f'/{topic_id}/scan')
        self.create_subscription(
            LaserScan, scan_topic,
            lambda msg, v=vid: self._cb_scan(msg, v), _SENSOR_QOS,
        )
        batt_topic = _VEHICLE_BATTERY_TOPIC.get(vid)
        if batt_topic:
            self.create_subscription(
                BatteryState, batt_topic,
                lambda msg, v=vid: self._cb_battery(msg, v), _SENSOR_QOS,
            )
        self.get_logger().info(f'[자동등록] 차량 구독 추가: {vid} (scan: {scan_topic})')

    # ── Subscribers ────────────────────────────────────────────────────────

    def _cb_status(self, msg: FleetStatus) -> None:
        vehicles = []
        for v in msg.vehicles:
            raw_id = getattr(v, 'vehicle_id', None) or getattr(v, 'robot_id', '')
            vid = _display_id(raw_id)
            if hasattr(v, 'state'):
                state_idx = int(v.state) if int(v.state) < len(self._STATE_NAMES) else 0
                state = self._STATE_NAMES[state_idx]
                battery = round(float(getattr(v, 'battery_pct', 0.0)), 1)
                cpu = round(float(getattr(v, 'cpu_load', 0.0)) * 100, 1)
                behaviors = list(getattr(v, 'active_behaviors', []))
                extra = {
                    'mode': state.lower(),
                    'healthy': state != 'FAULT',
                    'estop': state == 'ESTOP',
                    'heartbeat_stale': False,
                    'obstacle_stop': False,
                    'cmd_stale': False,
                    'battery_voltage': 0.0,
                    'status': ','.join(behaviors),
                }
            else:
                # FleetHeartbeat v1 (current scout stack) has no state enum / cpu_load.
                # Derive the UI state from the contract booleans/mode.
                mode_lower = (getattr(v, 'mode', '') or '').lower()
                status_lower = (getattr(v, 'status', '') or '').lower()
                safety_idle = (
                    bool(getattr(v, 'cmd_stale', False))
                    and status_lower == 'blocked'
                    and not bool(getattr(v, 'estop', False))
                    and not bool(getattr(v, 'heartbeat_stale', False))
                    and not bool(getattr(v, 'obstacle_stop', False))
                )
                if bool(getattr(v, 'estop', False)):
                    state = 'ESTOP'
                elif safety_idle:
                    state = 'MANUAL' if 'manual' in mode_lower else 'IDLE'
                elif not bool(getattr(v, 'healthy', True)):
                    state = 'FAULT'
                elif 'auto' in mode_lower:
                    state = 'AUTO'
                elif 'manual' in mode_lower:
                    state = 'MANUAL'
                else:
                    state = 'IDLE'
                battery = round(float(getattr(v, 'battery_percentage', 0.0)), 1)
                cpu = 0.0
                behaviors = [getattr(v, 'status', '')] if getattr(v, 'status', '') else []
                extra = {
                    'mode': getattr(v, 'mode', ''),
                    'healthy': bool(getattr(v, 'healthy', True)),
                    'estop': bool(getattr(v, 'estop', False)),
                    'heartbeat_stale': bool(getattr(v, 'heartbeat_stale', False)),
                    'obstacle_stop': bool(getattr(v, 'obstacle_stop', False)),
                    'cmd_stale': bool(getattr(v, 'cmd_stale', False)),
                    'battery_voltage': round(float(getattr(v, 'battery_voltage', 0.0)), 2),
                    'status': getattr(v, 'status', ''),
                }
            self._register_vehicle(vid)  # 새 차량 자동 등록
            vehicles.append({
                'id':        vid,
                'state':     state,
                'battery':   _battery_for(vid),
                'cpu':       cpu,
                'behaviors': behaviors,
                **extra,
            })
        offline = [_display_id(v) for v in msg.offline_vehicle_ids]
        for vid in offline:
            self._register_vehicle(vid)  # 오프라인 차량도 자동 등록
        offline = self._merge_udp_status_overlay(vehicles, offline)
        _push({
            'type': 'fleet_status',
            'vehicles': vehicles,
            'offline': offline,
        })

    def _cb_alert(self, msg: PerceptionAlert) -> None:
        level_idx = msg.alert_level if msg.alert_level < len(self._ALERT_NAMES) else 0
        _push({
            'type':       'alert',
            'vehicle_id': _display_id(msg.vehicle_id),
            'level':      self._ALERT_NAMES[level_idx],
            'max_temp':   round(float(msg.max_temp_c), 1),
            'confidence': round(float(msg.confidence), 2),
            'map_x':      round(float(msg.map_position.x), 2),
            'map_y':      round(float(msg.map_position.y), 2),
            'bbox': {
                'x': int(msg.rgb_bbox_x), 'y': int(msg.rgb_bbox_y),
                'w': int(msg.rgb_bbox_w), 'h': int(msg.rgb_bbox_h),
            },
        })

    def _cb_coverage(self, msg: String) -> None:
        try:
            _push({'type': 'coverage_total', 'value': json.loads(msg.data)})
        except Exception:
            pass

    def _cb_vcoverage(self, msg: String) -> None:
        try:
            parsed = json.loads(msg.data)
            data = parsed.get('per_vehicle', parsed)
            if isinstance(data, dict):
                data = _normalize_vehicle_map(data)
            _push({'type': 'coverage_per_vehicle', 'data': data})
        except Exception:
            pass

    def _cb_map_ready(self, msg: Bool) -> None:
        _push({'type': 'map_ready', 'value': msg.data})

    def _cb_map(self, msg: OccupancyGrid, source: str) -> None:
        try:
            if source not in self._map_grid_cache:
                self._map_grid_cache[source] = None
                self._map_cache[source] = None
            self._map_grid_cache[source] = msg
            png_b64 = _occupancy_grid_to_png_b64(msg)
            payload = {
                'type':       'slam_map',
                'source':     source,
                'png_b64':    png_b64,
                'width':      msg.info.width,
                'height':     msg.info.height,
                'resolution': round(float(msg.info.resolution), 4),
                'origin_x':   round(float(msg.info.origin.position.x), 4),
                'origin_y':   round(float(msg.info.origin.position.y), 4),
            }
            self._map_cache[source] = payload
            # 현재 활성 소스와 일치할 때만 클라이언트에 전송
            if source == self._active_map_source:
                _push(payload)
        except Exception as e:
            self.get_logger().warn(f'map convert error: {e}')

    def _make_pose_payload(self, vid: str, x: float, y: float,
                           yaw: float, source: str) -> dict:
        self._latest_raw_pose[vid] = {
            'x': float(x),
            'y': float(y),
            'yaw': float(yaw),
            'source': source,
        }
        cal = _pose_calibrations.get(vid)
        out_x, out_y, out_yaw = float(x), float(y), float(yaw)
        out_source = source
        if cal is not None:
            yaw_offset = float(cal.get('yaw_offset', 0.0))
            c = math.cos(yaw_offset)
            s = math.sin(yaw_offset)
            out_x = c * float(x) - s * float(y) + float(cal.get('tx', 0.0))
            out_y = s * float(x) + c * float(y) + float(cal.get('ty', 0.0))
            out_yaw = _normalize_angle(out_yaw + yaw_offset)
            out_source = f'{source}+cal'
        out_x, out_y, out_yaw, out_source = self._apply_display_pose_fix(
            vid, out_x, out_y, out_yaw, out_source, cal
        )
        out_yaw, out_source = self._apply_display_yaw_fix(vid, out_yaw, out_source)
        return {
            'id': vid,
            'x': round(out_x, 3),
            'y': round(out_y, 3),
            'yaw': round(out_yaw, 4),
            'source': out_source,
        }

    def _apply_display_pose_fix(
        self,
        vid: str,
        x: float,
        y: float,
        yaw: float,
        source: str,
        cal: dict | None,
    ) -> tuple[float, float, float, str]:
        if vid != 'aip2' and _topic_id(vid) != 'aip2':
            return x, y, yaw, source
        enabled = os.environ.get('AIP_SCOUT1_DISPLAY_POSE_FLIP', '1').strip().lower()
        if enabled not in ('1', 'true', 'yes', 'on'):
            return x, y, yaw, source
        if cal is None:
            return x, y, yaw, source
        anchor_x = float(cal.get('target_x', x))
        anchor_y = float(cal.get('target_y', y))
        flipped_x = 2.0 * anchor_x - float(x)
        flipped_y = 2.0 * anchor_y - float(y)
        return flipped_x, flipped_y, _normalize_angle(yaw + math.pi), f'{source}+poseflip'

    def _apply_display_yaw_fix(self, vid: str, yaw: float, source: str) -> tuple[float, str]:
        if vid != 'aip2' and _topic_id(vid) != 'aip2':
            return yaw, source
        raw_extra = os.environ.get('AIP_SCOUT1_DISPLAY_YAW_EXTRA', '0').strip()
        try:
            extra = float(raw_extra)
        except ValueError:
            self.get_logger().warning(
                f'Invalid AIP_SCOUT1_DISPLAY_YAW_EXTRA={raw_extra!r}; using 0 for scout_1'
            )
            extra = 0.0
        if abs(extra) < 1e-9:
            return yaw, source
        return _normalize_angle(yaw + extra), f'{source}+yawfix'

    def _cb_poses(self, msg: PeerPoseArray) -> None:
        poses = []
        for p in msg.poses:
            q = p.pose.orientation
            poses.append(self._make_pose_payload(
                _display_id(p.vehicle_id),
                float(p.pose.position.x),
                float(p.pose.position.y),
                _quat_to_yaw(q.x, q.y, q.z, q.w),
                'fleet',
            ))
        # Only let the coordinator take over (and suppress the TF/odom fallback)
        # when it is actually publishing poses. An empty /fleet/peer_poses —
        # coordinator up but no vehicle localized — must NOT blank out the map
        # nor disable _cb_tf_poses, otherwise live odom/TF positions vanish.
        if poses:
            self._fleet_poses_active = True
            _push({'type': 'poses', 'poses': poses})
        else:
            self._fleet_poses_active = False

    def _cb_tf_poses(self) -> None:
        if self._fleet_poses_active:
            return
        poses = []
        seen: set[str] = set()
        for vid in self._tf_vehicle_ids:
            frame_id = _topic_id(vid)
            candidates = [
                f'{frame_id}/base_link',
                f'{frame_id}/base_footprint',
                f'{vid}/base_link',
                f'{vid}/base_footprint',
            ]
            if vid == 'aip1':
                candidates.extend(['base_link', 'base_footprint'])
            for base_frame in dict.fromkeys(candidates):
                try:
                    t = self._tf_buffer.lookup_transform('map', base_frame, rclpy.time.Time())
                    q = t.transform.rotation
                    poses.append(self._make_pose_payload(
                        vid,
                        float(t.transform.translation.x),
                        float(t.transform.translation.y),
                        _quat_to_yaw(q.x, q.y, q.z, q.w),
                        'tf',
                    ))
                    seen.add(vid)
                    break
                except Exception:
                    pass
        now = time.monotonic()
        for vid, pose in self._odom_pose.items():
            if vid in seen:
                continue
            if now - self._odom_pose_ts.get(vid, 0.0) > 3.0:
                continue
            # Real scouts may have odom before a map->base_link TF exists.
            # Show that live relative pose as an operator-facing fallback,
            # while TF/map remains the source of truth whenever available.
            poses.append(pose)
        if poses:
            _push({'type': 'poses', 'poses': poses})

    def _cb_thermal(self, msg: Float32, vid: str) -> None:
        self._thermal[vid] = round(float(msg.data), 1)
        _push({'type': 'thermal', 'data': dict(self._thermal)})

    def _cb_vision(self, msg: CompressedImage, vid: str) -> None:
        try:
            mime = 'image/png' if 'png' in msg.format.lower() else 'image/jpeg'
            _push({
                'type': 'vision', 'vehicle_id': vid, 'mime': mime,
                'data_b64': base64.b64encode(bytes(msg.data)).decode('ascii'),
            })
        except Exception as e:
            self.get_logger().warn(f'vision convert error: {e}')

    def _cb_thermal_viz(self, msg: RosImage, vid: str) -> None:
        """raw Image(rgb8, 24×32) → 8× PIL upscale → PNG base64 → WS vision (2Hz throttle)."""
        now = time.monotonic()
        if now - _thermal_viz_ts.get(vid, 0.0) < 0.5:
            return
        _thermal_viz_ts[vid] = now
        try:
            w, h = msg.width, msg.height
            arr = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape((h, w, 3))
            pil_img = Image.fromarray(arr, mode='RGB')
            pil_img = pil_img.resize((w * 8, h * 8), Image.NEAREST)
            buf = io.BytesIO()
            pil_img.save(buf, format='PNG', optimize=False)
            _push({
                'type': 'vision',
                'vehicle_id': vid,
                'source': 'thermal',
                'mime': 'image/png',
                'data_b64': base64.b64encode(buf.getvalue()).decode('ascii'),
            })
        except Exception as e:
            self.get_logger().warn(f'thermal_viz convert error: {e}')

    def _cb_thermal_raw(self, msg: RosImage, vid: str) -> None:
        """열상 원본(32FC1, 방향보정됨) → 최고/최저온 심부 정규화좌표+온도 → WS thermal_spots(4Hz)."""
        now = time.monotonic()
        if now - _thermal_spots_ts.get(vid, 0.0) < 0.25:
            return
        _thermal_spots_ts[vid] = now
        try:
            h, w = int(msg.height), int(msg.width)
            arr = np.frombuffer(bytes(msg.data), dtype=np.float32).reshape((h, w))
            a = np.where(np.isfinite(arr), arr, np.nan)
            if not np.isfinite(a).any():
                return
            hot = int(np.nanargmax(a)); cold = int(np.nanargmin(a))
            hr, hc = divmod(hot, w); cr, cc = divmod(cold, w)
            dw = max(1, w - 1); dh = max(1, h - 1)
            _push({
                'type': 'thermal_spots', 'vehicle_id': vid,
                'hot':  {'u': hc / dw, 'v': hr / dh, 'c': round(float(a[hr, hc]), 1)},
                'cold': {'u': cc / dw, 'v': cr / dh, 'c': round(float(a[cr, cc]), 1)},
            })
        except Exception as e:
            self.get_logger().warn(f'thermal_raw spots error: {e}')

    def _cb_lock_state(self, msg: String) -> None:
        try:
            _push({'type': 'control_lock_state', **json.loads(msg.data)})
        except Exception:
            pass

    def _cb_plan_state(self, msg: String) -> None:
        try:
            _push({'type': 'patrol_plan', **json.loads(msg.data)})
        except Exception:
            pass

    def _cb_battery(self, msg: BatteryState, vid: str) -> None:
        pct = msg.percentage
        if pct is not None and pct == pct:  # NaN(미측정) 제외
            pct = pct * 100.0 if pct <= 1.0 else pct
            _battery_pct[vid] = (time.monotonic(), round(max(0.0, min(100.0, float(pct))), 1))

    def _cb_scan(self, msg: LaserScan, vid: str) -> None:
        """LaserScan → map frame XY 포인트 변환 → WebSocket (2Hz throttle).

        포즈는 slam 보정 map→base TF(스캔 시각)를 사용한다. raw odom 포즈(_latest_raw_pose)를
        쓰면 map→odom 보정량만큼 포인트가 맵과 어긋나(특히 선회 중) '틀어짐'. TF 미가용 시에만 폴백.
        """
        now = time.monotonic()
        if now - _scan_ts.get(vid, 0.0) < 0.5:
            return
        _scan_ts[vid] = now
        px = py = pyaw = None
        topic_id = _topic_id(vid)
        base_cands = [f'{topic_id}/base_footprint', f'{topic_id}/base_link']
        if vid == 'aip1':
            base_cands += ['base_footprint', 'base_link']
        for base_frame in base_cands:
            for when in (rclpy.time.Time.from_msg(msg.header.stamp), rclpy.time.Time()):
                try:
                    t = self._tf_buffer.lookup_transform('map', base_frame, when)
                    q = t.transform.rotation
                    px = float(t.transform.translation.x)
                    py = float(t.transform.translation.y)
                    pyaw = _quat_to_yaw(q.x, q.y, q.z, q.w)
                    break
                except Exception:
                    continue
            if px is not None:
                break
        if px is None:   # TF 미가용 시 기존 동작(odom 포즈) 폴백
            pose = self._latest_raw_pose.get(vid)
            if pose is None:
                return
            px, py, pyaw = pose['x'], pose['y'], pose['yaw']
        cos_yaw, sin_yaw = math.cos(pyaw), math.sin(pyaw)
        points: list[list[float]] = []
        angle = msg.angle_min
        stride = 4  # ~1/4 포인트 전송 (WebSocket 부하 절감)
        for i, r in enumerate(msg.ranges):
            if i % stride != 0:
                angle += msg.angle_increment
                continue
            if math.isfinite(r) and msg.range_min <= r <= msg.range_max:
                lx = r * math.cos(angle)
                ly = r * math.sin(angle)
                mx = px + lx * cos_yaw - ly * sin_yaw
                my = py + lx * sin_yaw + ly * cos_yaw
                points.append([round(mx, 3), round(my, 3)])
            angle += msg.angle_increment
        if points:
            _push({'type': 'scan', 'vehicle_id': vid, 'points': points})

    def _cb_patrol_status(self, msg: String, vid: str) -> None:
        try:
            data = json.loads(msg.data)
            self._patrol_running[vid] = data.get('running', False)
            payload = {'type': 'patrol_status', **data}
            # 차량별 캐시 키로 분리 저장 — WS 재접속 시 전 차량 상태 복원
            _state_cache[f'patrol_status_{vid}'] = payload
            _push(payload)
        except Exception:
            pass

    def _cb_odom(self, msg: Odometry, vid: str) -> None:
        vx = msg.twist.twist.linear.x
        vy = msg.twist.twist.linear.y
        speed = math.sqrt(vx * vx + vy * vy)
        px = msg.pose.pose.position.x
        py = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        prev = self._odom_prev.get(vid)
        if prev is not None:
            d = math.sqrt((px - prev[0]) ** 2 + (py - prev[1]) ** 2)
            if d < 0.5:  # filter teleport/jumps
                self._odom_dist[vid] = self._odom_dist.get(vid, 0.0) + d
        self._odom_prev[vid] = (px, py)
        self._odom_pose[vid] = self._make_pose_payload(
            vid,
            float(px),
            float(py),
            _quat_to_yaw(q.x, q.y, q.z, q.w),
            'odom',
        )
        self._odom_pose_ts[vid] = time.monotonic()
        _push({
            'type':       'odom',
            'vehicle_id': vid,
            'speed_mps':  round(speed, 3),
            'distance_m': round(self._odom_dist.get(vid, 0.0), 1),
        })

    # ── Command handlers ───────────────────────────────────────────────────

    def cmd_estop(self, vid: str, active: bool) -> None:
        if vid in self._estop_pubs:
            self._estop_pubs[vid].publish(Bool(data=active))
            self._override_twist_pubs[vid].publish(Twist())
            self._publish_override(vid, OverrideCommand.CMD_ESTOP if active else OverrideCommand.CMD_CLEAR)

    def cmd_estop_all(self, active: bool) -> None:
        self._publish_override('*', OverrideCommand.CMD_ESTOP if active else OverrideCommand.CMD_CLEAR)
        for vid in _VEHICLES:
            self._estop_pubs[vid].publish(Bool(data=active))
            self._override_twist_pubs[vid].publish(Twist())

    def cmd_scenario(self, scenario: str) -> None:
        self._scenario_pub.publish(String(data=scenario))

    def _publish_servo_burst(self, msg, repeats: int = 3, interval: float = 0.06) -> None:
        """단발 servo_cmd 를 짧은 구간 같은 목표각으로 N회 반복 발행.

        구동(프론트 setInterval 80ms 연속 스트림)과 달리 서보는 슬라이더 onchange/버튼
        단발이라, lossy·고지연 wifi 링크에서 그 한 패킷의 유실·reliable 재전송 지연이
        그대로 'start 지연'으로 노출된다. 같은 각도를 반복(멱등 — 다른 명령 연발 버스트
        아님, 안전)해 즉시 도달 확률을 높인다. WS 핸들러를 막지 않도록 1회차만 즉시
        발행하고 나머지는 데몬 스레드에서 보낸다."""
        self._arm_servo_pub.publish(msg)
        if repeats <= 1:
            return

        def _rest() -> None:
            for _ in range(repeats - 1):
                time.sleep(interval)
                self._arm_servo_pub.publish(msg)

        threading.Thread(target=_rest, daemon=True).start()

    def cmd_arm(self, action: str, degrees=None) -> None:
        """서보암(aip1) 수동 제어. action: 'servo'(deg×4 직접)|'scan'(자동스캔)|'stow'.
        servo_cmd 직접 발행 → serial_bridge → ESP32 PWM. 0~180 클램프(안전)."""
        action = str(action or '').strip().lower()
        if action == 'servo':
            degs = list(degrees or [])
            out = []
            for i in range(_ARM_SERVO_N):
                try:
                    v = int(round(float(degs[i]))) if i < len(degs) else 90
                except (TypeError, ValueError):
                    v = 90
                out.append(max(0, min(180, v)))      # 서보 물리 한계 클램프
            for i in range(_ARM_SERVO_N):            # 장착 방향 반전 보정(베이스 등)
                if _ARM_REVERSED[i]:
                    out[i] = 180 - out[i]
            msg = UInt8MultiArray()
            msg.data = out
            self._publish_servo_burst(msg)   # 단발→짧은 반복(같은 목표각) 으로 지연·유실 억제
            self.get_logger().info(f'arm servo → {out}')
        elif action == 'scan':
            self._arm_scan_pub.publish(Bool(data=True))
            self.get_logger().info('arm 자동 스캔 요청')
        elif action == 'stow':
            self._arm_estop_pub.publish(Bool(data=True))   # arm_scan_node: estop → stow
            self.get_logger().info('arm stow 요청')
        else:
            self.get_logger().warn(f'arm: 알 수 없는 action={action!r}')

    def cmd_map_ready(self) -> None:
        self._map_ready_pub.publish(Bool(data=True))

    def cmd_save_map(self) -> None:
        ok, detail = self._save_cached_map()
        _push({'type': 'map_saved', 'ok': ok, 'detail': detail})
        if ok:
            self.get_logger().info(detail)
            return
        if self._save_cli.service_is_ready():
            self._save_cli.call_async(Trigger.Request())
        else:
            self.get_logger().warn(f'/save_map_now service unavailable and no cached map: {detail}')

    def _save_cached_map(self) -> tuple[bool, str]:
        source = self._active_map_source
        msg = self._map_grid_cache.get(source)
        if msg is None:
            for fallback in _MAP_SOURCES:
                source = fallback
                msg = self._map_grid_cache.get(source)
                if msg is not None:
                    break
        if msg is None:
            return False, 'no /map or /map_static has been received yet'

        try:
            _MAP_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            stamped = _MAP_DIR / f'fleet_map_{stamp}_{source}'
            latest = _MAP_DIR / 'latest_fleet_map'
            self._write_map_files(msg, stamped)
            self._write_map_files(msg, latest)
            return True, (
                f'saved {source} map to {latest}.yaml '
                f'({msg.info.width}x{msg.info.height}, {msg.info.resolution:.3f} m/cell)'
            )
        except Exception as exc:
            return False, f'cached map save failed: {exc}'

    @staticmethod
    def _write_map_files(msg: OccupancyGrid, stem: Path) -> None:
        width = int(msg.info.width)
        height = int(msg.info.height)
        data = np.array(msg.data, dtype=np.int16).reshape((height, width))

        image = np.full((height, width), 205, dtype=np.uint8)
        image[data >= 65] = 0
        image[(data >= 0) & (data <= 25)] = 254
        image = np.flipud(image)

        pgm_path = stem.with_suffix('.pgm')
        yaml_path = stem.with_suffix('.yaml')
        with pgm_path.open('wb') as f:
            f.write(f'P5\n# AIP dashboard cached map\n{width} {height}\n255\n'.encode('ascii'))
            f.write(image.tobytes())

        origin = msg.info.origin
        yaw = _quat_to_yaw(
            float(origin.orientation.x),
            float(origin.orientation.y),
            float(origin.orientation.z),
            float(origin.orientation.w),
        )
        yaml_path.write_text(
            '\n'.join([
                f'image: {pgm_path.name}',
                'mode: trinary',
                f'resolution: {float(msg.info.resolution):.8g}',
                'origin: ['
                f'{float(origin.position.x):.8g}, '
                f'{float(origin.position.y):.8g}, '
                f'{yaw:.8g}]',
                'negate: 0',
                'occupied_thresh: 0.65',
                'free_thresh: 0.25',
                '',
            ]),
            encoding='utf-8',
        )

    def cmd_load_saved_map(self) -> None:
        ok, detail = self._load_saved_map_static(push=True)
        _push({'type': 'map_loaded', 'ok': ok, 'detail': detail})

    def _load_saved_map_static(self, push: bool) -> tuple[bool, str]:
        yaml_path = _MAP_DIR / 'latest_fleet_map.yaml'
        if not yaml_path.exists():
            return False, f'no saved map: {yaml_path}'

        try:
            meta: dict[str, str] = {}
            for line in yaml_path.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if not line or line.startswith('#') or ':' not in line:
                    continue
                key, value = line.split(':', 1)
                meta[key.strip()] = value.strip()

            image_name = meta.get('image', 'latest_fleet_map.pgm')
            image_path = Path(image_name)
            if not image_path.is_absolute():
                image_path = yaml_path.parent / image_path
            if not image_path.exists():
                return False, f'saved map image missing: {image_path}'

            with Image.open(image_path) as pil_img:
                arr = np.array(pil_img.convert('L'), dtype=np.uint8)
            height, width = arr.shape
            data_img = np.flipud(arr)
            occ = np.full((height, width), -1, dtype=np.int8)
            occ[data_img >= 250] = 0
            occ[data_img <= 5] = 100

            origin_vals = [0.0, 0.0, 0.0]
            origin_raw = meta.get('origin', '')
            if origin_raw.startswith('[') and origin_raw.endswith(']'):
                parts = [p.strip() for p in origin_raw[1:-1].split(',')]
                for i, part in enumerate(parts[:3]):
                    origin_vals[i] = float(part)

            msg = OccupancyGrid()
            msg.header.frame_id = 'map'
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.info.map_load_time = self.get_clock().now().to_msg()
            msg.info.resolution = float(meta.get('resolution', 0.05))
            msg.info.width = int(width)
            msg.info.height = int(height)
            msg.info.origin.position.x = origin_vals[0]
            msg.info.origin.position.y = origin_vals[1]
            msg.info.origin.position.z = 0.0
            yaw = origin_vals[2]
            msg.info.origin.orientation.z = math.sin(yaw / 2.0)
            msg.info.origin.orientation.w = math.cos(yaw / 2.0)
            msg.data = occ.reshape(-1).astype(int).tolist()

            self._cb_map(msg, 'map_static')
            if push:
                self.cmd_set_map_source('map_static')
            return True, (
                f'loaded saved map {yaml_path} as map_static '
                f'({width}x{height}, {msg.info.resolution:.3f} m/cell)'
            )
        except Exception as exc:
            return False, f'saved map load failed: {exc}'

    def cmd_patrol(self, patrol_cmd: str) -> None:
        self._patrol_cmd_pub.publish(String(data=patrol_cmd))

    def cmd_lock(self, operator_id: str, vehicle_id: str, locked: bool) -> None:
        payload = {
            'operator_id': operator_id,
            'vehicle_id':  vehicle_id,
            'locked':      locked,
            'stamp_ms':    int(self.get_clock().now().nanoseconds / 1_000_000),
        }
        self._control_lock_pub.publish(String(data=json.dumps(payload)))

    def cmd_override(self, vehicle_id: str, command: int,
                     linear_x: float = 0.0, angular_z: float = 0.0) -> None:
        twist = Twist()
        lx = self._correct_manual_linear_x(vehicle_id, int(command), float(linear_x))
        az = float(angular_z)
        max_lin, max_ang = _VEHICLE_VEL_LIMITS.get(vehicle_id, _DEFAULT_VEL_LIMIT)
        twist.linear.x  = max(-max_lin, min(max_lin, lx))
        twist.angular.z = max(-max_ang, min(max_ang, az))
        # CMD_PAUSE means "hold position, keep autonomy loaded".  Sending a
        # vehicle mode change to manual here cancels an active Nav2 goal on the
        # scout bridge; leave mode changes to explicit manual/estop commands.
        if int(command) in (
            OverrideCommand.CMD_MANUAL,
            OverrideCommand.CMD_ESTOP,
        ):
            self._publish_vehicle_mode(vehicle_id, 'manual')
        if vehicle_id in self._override_twist_pubs:
            self._override_twist_pubs[vehicle_id].publish(twist)
        self._publish_override(vehicle_id, int(command), twist)
        self._send_udp_override(vehicle_id, int(command), twist)

    async def esp32_reset(self, vid: str) -> None:
        self.get_logger().info(f'ESP32 reset requested: {vid}')
        loop = asyncio.get_event_loop()
        ok, msg = await loop.run_in_executor(None, _ssh_esp32_reset_blocking, vid)
        if ok:
            self.get_logger().info(f'ESP32 reset {vid}: OK')
        else:
            self.get_logger().warning(f'ESP32 reset {vid}: FAIL — {msg[:300]}')
        await _broadcast({'type': 'esp32_reset_result', 'vehicle_id': vid, 'ok': ok, 'msg': msg[:400]})

    def _correct_manual_linear_x(self, vehicle_id: str, command: int, linear_x: float) -> float:
        if command != OverrideCommand.CMD_MANUAL:
            return linear_x
        vid = vehicle_id.strip().strip('/')
        if vid != 'aip2' and _topic_id(vid) != 'aip2':
            return linear_x
        sign = os.environ.get('AIP_SCOUT1_MANUAL_LINEAR_SIGN', '1').strip()
        try:
            return float(sign) * linear_x
        except ValueError:
            self.get_logger().warning(
                f'Invalid AIP_SCOUT1_MANUAL_LINEAR_SIGN={sign!r}; using 1 for scout_1'
            )
            return linear_x

    def _publish_vehicle_mode(self, vehicle_id: str, mode: str) -> None:
        msg = String(data=mode)
        if vehicle_id == '*':
            for pub in self._mode_pubs.values():
                pub.publish(msg)
            for vid in self._mode_pubs:
                self._send_udp_nav_mode(vid, mode)
            return
        pub = self._mode_pubs.get(vehicle_id)
        if pub is not None:
            pub.publish(msg)
            self._send_udp_nav_mode(vehicle_id, mode)

    def _load_udp_command_targets(self) -> dict[str, tuple[str, int]]:
        raw = os.environ.get(
            'AIP_UDP_COMMAND_TARGETS',
            'aip2=192.168.0.4:19051,aip3=192.168.0.5:19052',
        )
        return self._parse_udp_targets(raw, 'command')

    def _load_udp_nav_targets(self) -> dict[str, tuple[str, int]]:
        raw = os.environ.get(
            'AIP_UDP_NAV_TARGETS',
            'aip2=192.168.0.4:19151,aip3=192.168.0.5:19152',
        )
        return self._parse_udp_targets(raw, 'navigate')

    def _parse_udp_targets(self, raw: str, label: str) -> dict[str, tuple[str, int]]:
        targets: dict[str, tuple[str, int]] = {}
        for item in raw.split(','):
            item = item.strip()
            if not item or '=' not in item or ':' not in item:
                continue
            vid, endpoint = item.split('=', 1)
            host, port = endpoint.rsplit(':', 1)
            try:
                targets[_display_id(vid.strip())] = (host.strip(), int(port))
            except ValueError:
                self.get_logger().warning(f'Invalid UDP {label} target ignored: {item}')
        return targets

    def _start_udp_status_listener(self) -> None:
        port = int(os.environ.get('AIP_UDP_STATUS_PORT', '0'))
        if port <= 0:
            self.get_logger().info('UDP status overlay disabled')
            return
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('0.0.0.0', port))
            sock.settimeout(0.5)
        except OSError as exc:
            self.get_logger().warning(f'UDP status overlay bind failed on {port}: {exc}')
            return
        self._udp_status_sock = sock
        threading.Thread(target=self._udp_status_loop, daemon=True).start()
        self.get_logger().info(f'UDP status overlay listening on 0.0.0.0:{port}')

    def _start_ping_status_monitors(self) -> None:
        raw = os.environ.get('AIP_PING_STATUS_TARGETS', 'aip1=192.168.0.3')
        targets = self._parse_ping_targets(raw)
        for vid, host in targets.items():
            threading.Thread(
                target=self._ping_status_loop,
                args=(vid, host),
                daemon=True,
            ).start()
        if targets:
            self.get_logger().info(f'Ping status overlay targets: {targets}')

    def _parse_ping_targets(self, raw: str) -> dict[str, str]:
        targets: dict[str, str] = {}
        for item in raw.split(','):
            item = item.strip()
            if not item or '=' not in item:
                continue
            vid, host = item.split('=', 1)
            vid = _display_id(vid.strip())
            host = host.strip()
            if vid in _VEHICLES and host:
                targets[vid] = host
        return targets

    def _ping_status_loop(self, vehicle_id: str, host: str) -> None:
        while rclpy.ok():
            ok = False
            try:
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '1', host],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=2.0,
                )
                ok = result.returncode == 0
            except Exception:
                ok = False
            self._on_udp_status({
                'vehicle_id': vehicle_id,
                'mode': 'manual',
                'healthy': ok,
                'estop': False,
                'battery': 0.0,
                'cpu': 0.0,
                'status': 'network_ping_only_no_ssh' if ok else 'ping_failed',
            })
            time.sleep(1.0)

    def _udp_status_loop(self) -> None:
        sock = getattr(self, '_udp_status_sock', None)
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
                self._on_udp_status(payload)

    def _on_udp_status(self, payload: dict[str, Any]) -> None:
        raw_id = (
            payload.get('vehicle_id')
            or payload.get('robot_id')
            or payload.get('id')
        )
        vid = _display_id(str(raw_id or ''))
        if not vid or vid not in _VEHICLES:
            return
        vehicle = self._udp_payload_to_vehicle(vid, payload)
        self._udp_status_by_vehicle[vid] = (time.monotonic(), vehicle)
        # _push_udp_status_snapshot() 를 직접 호출하지 않는다.
        # DDS 기반 _cb_status 가 0.5s 내로 UDP 오버레이를 병합해서 push 한다.
        # (직접 호출 시 UDP 캐시에 없는 DDS 차량이 offline 으로 잘못 표시됨)

    def _udp_payload_to_vehicle(self, vid: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = str(payload.get('state', '')).strip().upper()
        if state.isdigit():
            idx = int(state)
            state = self._STATE_NAMES[idx] if 0 <= idx < len(self._STATE_NAMES) else 'IDLE'
        mode = str(payload.get('mode', '')).strip().lower()
        status = str(payload.get('status', '')).strip()
        healthy = bool(payload.get('healthy', True))
        estop = bool(payload.get('estop', False))
        if not state:
            if estop:
                state = 'ESTOP'
            elif not healthy:
                state = 'FAULT'
            elif 'auto' in mode:
                state = 'AUTO'
            elif 'manual' in mode:
                state = 'MANUAL'
            else:
                state = 'IDLE'
        battery = payload.get('battery', payload.get('battery_percentage', payload.get('battery_pct', 0.0)))
        cpu = payload.get('cpu', None)
        if cpu is None:
            cpu_load = float(payload.get('cpu_load', 0.0) or 0.0)
            cpu = cpu_load * 100.0 if cpu_load <= 1.0 else cpu_load
        behaviors = payload.get('behaviors', payload.get('active_behaviors', []))
        if isinstance(behaviors, str):
            behaviors = [behaviors] if behaviors else []
        return {
            'id': vid,
            'state': state,
            'battery': _battery_for(vid),
            'cpu': round(float(cpu or 0.0), 1),
            'behaviors': list(behaviors or []),
            'mode': mode or state.lower(),
            'healthy': healthy,
            'estop': estop,
            'heartbeat_stale': bool(payload.get('heartbeat_stale', False)),
            'obstacle_stop': bool(payload.get('obstacle_stop', False)),
            'cmd_stale': bool(payload.get('cmd_stale', False)),
            'battery_voltage': round(float(payload.get('battery_voltage', 0.0) or 0.0), 2),
            'status': status,
            'source': 'udp_status',
        }

    def _merge_udp_status_overlay(self, vehicles: list[dict[str, Any]], offline: list[str]) -> list[str]:
        now = time.monotonic()
        existing = {v.get('id') for v in vehicles}
        offline_set = set(offline)
        for vid, (stamp, vehicle) in list(self._udp_status_by_vehicle.items()):
            if now - stamp > self._udp_status_ttl_sec:
                self._udp_status_by_vehicle.pop(vid, None)
                continue
            if vid not in existing:
                vehicles.append(dict(vehicle))
            else:
                # FleetHeartbeat 카드에는 cpu 필드가 없음 → UDP 상태의 cpu(및 미지원 배터리)만 오버레이.
                for card in vehicles:
                    if card.get('id') == vid:
                        if vehicle.get('cpu'):
                            card['cpu'] = vehicle['cpu']
                        break
            offline_set.discard(vid)
        return [vid for vid in _VEHICLES if vid in offline_set]

    def _push_udp_status_snapshot(self) -> None:
        vehicles: list[dict[str, Any]] = []
        offline = list(_VEHICLES)
        offline = self._merge_udp_status_overlay(vehicles, offline)
        _push({'type': 'fleet_status', 'vehicles': vehicles, 'offline': offline})

    def _send_udp_override(self, vehicle_id: str, command: int, twist: Twist) -> None:
        target = self._udp_cmd_targets.get(vehicle_id)
        if target is None:
            return
        payload = {
            'vehicle_id': _topic_id(vehicle_id),
            'command': command,
            'linear_x': float(twist.linear.x),
            'angular_z': float(twist.angular.z),
            'stamp_ns': int(self.get_clock().now().nanoseconds),
        }
        try:
            self._udp_cmd_sock.sendto(json.dumps(payload).encode('utf-8'), target)
        except OSError as exc:
            self.get_logger().warning(f'UDP override fallback failed for {vehicle_id}: {exc}')

    def _send_udp_nav_mode(self, vehicle_id: str, mode: str) -> None:
        target = self._udp_nav_targets.get(vehicle_id)
        if target is None:
            return
        payload = {
            'kind': 'mode',
            'vehicle_id': _topic_id(vehicle_id),
            'mode': mode,
            'stamp_ns': int(self.get_clock().now().nanoseconds),
        }
        try:
            self._udp_cmd_sock.sendto(json.dumps(payload).encode('utf-8'), target)
        except OSError as exc:
            self.get_logger().warning(f'UDP navigate mode fallback failed for {vehicle_id}: {exc}')

    def _send_udp_navigate(self, vehicle_id: str, pose: PoseStamped) -> None:
        target = self._udp_nav_targets.get(vehicle_id)
        if target is None:
            return
        payload = {
            'kind': 'navigate',
            'vehicle_id': _topic_id(vehicle_id),
            'frame_id': pose.header.frame_id or 'map',
            'x': float(pose.pose.position.x),
            'y': float(pose.pose.position.y),
            'z': float(pose.pose.position.z),
            'qx': float(pose.pose.orientation.x),
            'qy': float(pose.pose.orientation.y),
            'qz': float(pose.pose.orientation.z),
            'qw': float(pose.pose.orientation.w),
            'stamp_ns': int(self.get_clock().now().nanoseconds),
        }
        try:
            self._udp_cmd_sock.sendto(json.dumps(payload).encode('utf-8'), target)
        except OSError as exc:
            self.get_logger().warning(f'UDP navigate fallback failed for {vehicle_id}: {exc}')

    def _nav_allowed(self, vid: str) -> bool:
        if vid.startswith('peer_'):
            return True
        allowed = set(_csv_env('AIP_NAV_ALLOWED_IDS', ''))
        topic_id = _topic_id(vid)
        if '*' in allowed or vid in allowed or topic_id in allowed:
            return True
        legacy = os.environ.get('AIP_ALLOW_SCOUT1_NAV', '').strip().lower()
        if topic_id == 'aip2' and legacy in ('1', 'true', 'yes', 'on'):
            return True
        return False

    def cmd_navigate(self, vid: str, x: float, y: float, yaw_rad: float,
                     transport: str = 'topic') -> None:
        if vid not in self._goal_pubs:
            return
        if not self._nav_allowed(vid):
            _push({'type': 'navigate_rejected', 'vehicle_id': vid,
                   'x': x, 'y': y, 'zone': 'nav_disabled',
                   'detail': 'Autonomous navigation is disabled until map/localization is verified'})
            self.get_logger().warn(
                f'navigate {vid} rejected: autonomous navigation disabled; '
                'set AIP_NAV_ALLOWED_IDS explicitly after live localization verification'
            )
            return
        zone_hit = self._keepout_zone_name(float(x), float(y))
        if zone_hit is not None:
            _push({'type': 'navigate_rejected', 'vehicle_id': vid,
                   'x': x, 'y': y, 'zone': zone_hit})
            self.get_logger().warn(
                f'navigate {vid} → ({x:.2f}, {y:.2f}) 거부: 금지구역 "{zone_hit}" 내부'
            )
            return
        msg = PoseStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp    = self.get_clock().now().to_msg()
        msg.pose.position.x = float(x)
        msg.pose.position.y = float(y)
        msg.pose.position.z = 0.0
        cy = math.cos(float(yaw_rad) / 2.0)
        sy = math.sin(float(yaw_rad) / 2.0)
        msg.pose.orientation.w = cy
        msg.pose.orientation.z = sy
        msg.pose.orientation.x = 0.0
        msg.pose.orientation.y = 0.0
        if transport == 'action':
            self._send_navigate_action(vid, msg)
            return
        self._publish_vehicle_mode(vid, 'autonomous')
        # Real vehicles configured for UDP navigation should receive only one
        # goal. If DDS /goal_pose and UDP fallback both arrive, the robot-side
        # bridge may treat them as rapid preemptions.
        if vid not in self._udp_nav_targets:
            self._goal_pubs[vid].publish(msg)
        self._send_udp_navigate(vid, msg)
        self.get_logger().info(
            f'navigate {vid} → ({x:.2f}, {y:.2f}, yaw={math.degrees(yaw_rad):.0f}°)'
        )

    def _send_navigate_action(self, vid: str, pose: PoseStamped) -> None:
        client = self._nav_clients.get(vid)
        if client is None:
            return
        payload = {
            'type': 'navigate_action_status',
            'vehicle_id': vid,
            'state': 'not_ready',
            'detail': f'/{vid}/navigate_to_pose action server not ready',
        }
        if not client.server_is_ready():
            _push(payload)
            self.get_logger().warn(payload['detail'])
            return

        goal = NavigateToPose.Goal()
        goal.pose = pose
        send_future = client.send_goal_async(goal)
        _push({
            'type': 'navigate_action_status',
            'vehicle_id': vid,
            'state': 'sent',
            'x': round(float(pose.pose.position.x), 3),
            'y': round(float(pose.pose.position.y), 3),
        })

        def _on_goal_response(future):
            try:
                handle = future.result()
                accepted = bool(handle.accepted)
                _push({
                    'type': 'navigate_action_status',
                    'vehicle_id': vid,
                    'state': 'accepted' if accepted else 'rejected',
                })
                if accepted:
                    handle.get_result_async().add_done_callback(_on_result)
            except Exception as exc:
                _push({
                    'type': 'navigate_action_status',
                    'vehicle_id': vid,
                    'state': 'error',
                    'detail': str(exc),
                })

        def _on_result(future):
            try:
                result = future.result()
                _push({
                    'type': 'navigate_action_status',
                    'vehicle_id': vid,
                    'state': 'result',
                    'status': int(result.status),
                })
            except Exception as exc:
                _push({
                    'type': 'navigate_action_status',
                    'vehicle_id': vid,
                    'state': 'error',
                    'detail': str(exc),
                })

        send_future.add_done_callback(_on_goal_response)
        self.get_logger().info(
            f'navigate action {vid} → ({pose.pose.position.x:.2f}, '
            f'{pose.pose.position.y:.2f})'
        )

    def _keepout_zone_name(self, px: float, py: float) -> str | None:
        """점이 금지구역 안에 있으면 구역 인덱스 문자열 반환, 없으면 None."""
        for i, zone in enumerate(self._keepout_zones):
            if self._point_in_polygon(px, py, zone):
                return f'구역{i + 1}'
        return None

    @staticmethod
    def _point_in_polygon(px: float, py: float, polygon: list[dict]) -> bool:
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

    def cmd_set_map_source(self, source: str) -> None:
        if source not in _MAP_SOURCES:
            return
        self._active_map_source = source
        _push({'type': 'map_source_changed', 'source': source})
        # 전환 즉시 캐시된 맵 이미지 전송 — 없으면 clear 로 직전(타차량) 맵 잔상 제거
        cached = self._map_cache.get(source)
        if cached:
            _push(cached)
        else:
            _push({'type': 'map_clear', 'source': source})

    def cmd_reset_map(self, vid: str) -> None:
        """대시보드 맵 표시/캐시 초기화 + 전 클라이언트 clear 브로드캐스트.

        표시·캐시만 초기화한다. 실제 SLAM 누적 데이터 wipe 는 slam_toolbox 노드
        재시작이 필요(운영자) — 매핑 중이면 다음 /map 발행 시 현재 맵이 다시 채워진다."""
        for s in {vid, 'map', self._active_map_source}:
            if s and s in self._map_cache:
                self._map_cache[s] = None
                self._map_grid_cache[s] = None
        _push({'type': 'map_clear', 'source': self._active_map_source})
        self.get_logger().info(f'맵 표시/캐시 초기화 (vehicle={vid or "-"})')

    # ── 매핑 오케스트레이션 (대시보드 → 중앙 SLAM 스택 subprocess) ──────────────
    _MAPPING_LAUNCH = {'manual':   'aip1_mapping.launch.py',
                       'auto':     'aip1_auto_mapping.launch.py',
                       'localize': 'aip1_localization.launch.py'}

    @staticmethod
    def _latest_saved_map() -> str | None:
        """~/aip_maps 에서 가장 최근 맵 yaml(image: 키 보유) 경로 반환. 없으면 None."""
        try:
            cands = sorted(_MAP_DIR.glob('*.yaml'),
                           key=lambda p: p.stat().st_mtime, reverse=True)
        except Exception:
            return None
        for p in cands:
            try:
                if 'image:' in p.read_text():
                    return str(p)
            except Exception:
                continue
        return None

    def cmd_start_mapping(self, vid: str, mode: str) -> None:
        """매핑/로컬라이제이션 시작 — 중앙 스택을 subprocess 로 기동.
        manual=SLAM(teleop) / auto=SLAM+Nav2+explore(자율 탐색) / localize=저장맵+AMCL. 현재 aip1 만."""
        if vid != 'aip1':
            _push({'type': 'mapping_status', 'state': 'error',
                   'detail': f'{vid} 는 중앙 스택 미지원(현재 aip1)'})
            return
        m = str(mode).lower()
        mode = 'localize' if m.startswith('local') else ('auto' if m.startswith('auto') else 'manual')
        launch = self._MAPPING_LAUNCH[mode]
        extra = ''
        if mode == 'localize':
            mp = self._latest_saved_map()
            if mp is None:
                _push({'type': 'mapping_status', 'state': 'error',
                       'detail': '저장된 맵이 없습니다 — 먼저 매핑 후 맵 저장하세요'})
                return
            extra = f' map:={mp}'
        self.cmd_stop_mapping(quiet=True)   # 중복/orphan 방지(pre-clean)
        cmd = ('source /opt/ros/humble/setup.bash && '
               'source /home/kde/aip_swarm_ws/install/setup.bash && '
               'export ROS_DOMAIN_ID=42 RMW_IMPLEMENTATION=rmw_fastrtps_cpp && '
               'unset ROS_DISCOVERY_SERVER FASTRTPS_DEFAULT_PROFILES_FILE && '
               f'exec ros2 launch aip_fleet_real {launch}{extra}')
        try:
            self._mapping_proc = subprocess.Popen(
                ['bash', '-lc', cmd], start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.get_logger().info(f'{mode} 시작 {vid} pid={self._mapping_proc.pid}{extra}')
            state = 'localizing' if mode == 'localize' else 'mapping'
            _push({'type': 'mapping_status', 'state': state, 'mode': mode, 'vehicle_id': vid})
        except Exception as e:
            _push({'type': 'mapping_status', 'state': 'error', 'detail': str(e)})

    def cmd_stop_mapping(self, vid: str = '', quiet: bool = False) -> None:
        proc = getattr(self, '_mapping_proc', None)
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
        self._mapping_proc = None
        # 잔류 SLAM/explore/static TF 정리(orphan 방지 — 이번 세션에서 겪은 그 문제)
        for pat in ('async_slam_toolbox', 'aip1_auto_mapping.launch', 'aip1_mapping.launch',
                    'aip1_localization.launch', 'explore_node',
                    'lifecycle_manager_localization', 'nav2_amcl/amcl', 'nav2_map_server/map_server',
                    'tf_base_footprint_to_base_link_devpc',
                    'tf_base_link_to_laser_link_devpc'):
            subprocess.run(['pkill', '-9', '-f', pat], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not quiet:
            self.get_logger().info('매핑 정지')
            _push({'type': 'mapping_status', 'state': 'idle'})

    def cmd_keepout(self, zones: list) -> None:
        self._keepout_zones = zones
        self._keepout_pub.publish(String(data=json.dumps({'zones': zones})))
        _save_keepout_zones(zones)
        payload = {'type': 'keepout_zones_restore', 'zones': zones}
        _state_cache['keepout_zones_restore'] = payload
        _push(payload)

    def cmd_set_dock(self, vid: str, x: float, y: float, yaw_rad: float) -> None:
        _dock_positions[vid] = {'x': x, 'y': y, 'yaw_rad': yaw_rad}
        _save_dock_positions()
        _push({'type': 'dock_positions', 'positions': dict(_dock_positions)})

    def _push_pose_calibrations(self) -> None:
        payload = {
            'type': 'pose_calibrations',
            'calibrations': dict(_pose_calibrations),
        }
        _state_cache['pose_calibrations'] = payload
        _push(payload)

    def cmd_set_pose_calibration(self, vid: str, x: float, y: float, yaw_rad: float) -> None:
        raw = self._latest_raw_pose.get(vid)
        if raw is None:
            _push({
                'type': 'pose_calibration_error',
                'vehicle_id': vid,
                'reason': 'pose_not_available',
            })
            return
        yaw_offset = _normalize_angle(float(yaw_rad) - float(raw['yaw']))
        c = math.cos(yaw_offset)
        s = math.sin(yaw_offset)
        raw_x = float(raw['x'])
        raw_y = float(raw['y'])
        tx = float(x) - (c * raw_x - s * raw_y)
        ty = float(y) - (s * raw_x + c * raw_y)
        _pose_calibrations[vid] = {
            'tx': tx,
            'ty': ty,
            'yaw_offset': yaw_offset,
            'target_x': float(x),
            'target_y': float(y),
            'target_yaw': float(yaw_rad),
            'raw_x': raw_x,
            'raw_y': raw_y,
            'raw_yaw': float(raw['yaw']),
            'raw_source': raw.get('source', 'unknown'),
            'stamp_ms': int(self.get_clock().now().nanoseconds / 1_000_000),
        }
        _save_pose_calibrations()
        self._push_pose_calibrations()
        # Nav2/AMCL 위치추정 통합 — 찍은 절대 맵 포즈를 initialpose 로도 발행.
        self._publish_initialpose(vid, float(x), float(y), float(yaw_rad))

    def _publish_initialpose(self, vid: str, x: float, y: float, yaw_rad: float) -> None:
        """'지도 위치 보정'과 통합된 Nav2/AMCL 초기 위치추정 발행(map 프레임).
        AMCL 미실행(매핑 중)이면 구독자 없어 무해. 로컬라이제이션 모드에서 해당 위치로 초기화."""
        pub = self._initialpose_pubs.get(vid)
        if pub is None:
            return
        ip = PoseWithCovarianceStamped()
        ip.header.frame_id = 'map'
        ip.header.stamp = self.get_clock().now().to_msg()
        ip.pose.pose.position.x = x
        ip.pose.pose.position.y = y
        ip.pose.pose.orientation.z = math.sin(yaw_rad / 2.0)
        ip.pose.pose.orientation.w = math.cos(yaw_rad / 2.0)
        ip.pose.covariance[0]  = 0.25     # x: 0.5m std
        ip.pose.covariance[7]  = 0.25     # y: 0.5m std
        ip.pose.covariance[35] = 0.0685   # yaw: ~15° std
        pub.publish(ip)
        self.get_logger().info(
            f'[{vid}] initialpose 발행 ({x:.2f}, {y:.2f}, {math.degrees(yaw_rad):.0f}°)')

    def cmd_clear_pose_calibration(self, vid: str) -> None:
        _pose_calibrations.pop(vid, None)
        _save_pose_calibrations()
        self._push_pose_calibrations()

    def _publish_override(self, vehicle_id: str, command: int,
                          twist: Twist | None = None) -> None:
        msg = OverrideCommand()
        msg.vehicle_id     = vehicle_id
        msg.stamp          = self.get_clock().now().to_msg()
        msg.command        = int(command)
        msg.manual_cmd_vel = twist if twist is not None else Twist()
        self._override_pub.publish(msg)


# ── FastAPI app ────────────────────────────────────────────────────────────

app = FastAPI(title='AIP Fleet Dashboard')


@app.on_event('startup')
async def _startup() -> None:
    global _main_loop, _ros_node
    import sys
    _main_loop = asyncio.get_running_loop()
    _load_dock_positions()
    _load_pose_calibrations()
    # keepout_zones: 파일에서 복원 후 _state_cache에 저장 (WS 재접속 시 자동 전달)
    _saved_zones = _load_keepout_zones()
    if _saved_zones:
        _state_cache['keepout_zones_restore'] = {
            'type': 'keepout_zones_restore', 'zones': _saved_zones,
        }
    if _VISION_STREAM_URLS:
        _state_cache['vision_streams'] = {
            'type': 'vision_streams',
            'streams': dict(_VISION_STREAM_URLS),
        }
    if _THERMAL_STREAM_URLS:
        _state_cache['thermal_streams'] = {
            'type': 'thermal_streams',
            'streams': dict(_THERMAL_STREAM_URLS),
        }
    _state_cache['vision_config'] = {
        'type': 'vision_config',
        'poll_ms': _VISION_POLL_MS,
        'rgb_poll_ms': _RGB_POLL_MS,
        'thermal_poll_ms': _THERMAL_POLL_MS,
    }

    if _ros_node is not None:
        # 외부(단일 프로세스 결합 실행기)에서 이미 DashboardNode를 만들어 같은
        # rclpy context/participant를 공유하는 경우 — 자체 스레드/participant를
        # 새로 만들지 않는다 (로컬-로컬 DDS 디스커버리 회피용).
        return

    def _ros_spin() -> None:
        global _ros_node
        rclpy.init(args=sys.argv)
        _ros_node = DashboardNode()
        try:
            rclpy.spin(_ros_node)
        except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
            pass
        finally:
            try:
                _ros_node.destroy_node()
            except Exception:
                pass
            rclpy.try_shutdown()

    threading.Thread(target=_ros_spin, daemon=True).start()


@app.websocket('/ws')
async def _ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _clients.add(ws)
    await ws.send_text(json.dumps({'type': 'connected'}))
    for cached_msg in list(_state_cache.values()):
        try:
            await ws.send_text(json.dumps(cached_msg, ensure_ascii=False))
        except Exception:
            break
    try:
        while True:
            data = await ws.receive_json()
            if _ros_node is None:
                continue
            cmd = data.get('cmd', '')
            if cmd == 'estop':
                _ros_node.cmd_estop(data['vehicle_id'], True)
            elif cmd == 'release_estop':
                _ros_node.cmd_estop(data['vehicle_id'], False)
            elif cmd == 'estop_all':
                _ros_node.cmd_estop_all(True)
            elif cmd == 'release_all':
                _ros_node.cmd_estop_all(False)
            elif cmd == 'set_scenario':
                _ros_node.cmd_scenario(data.get('scenario', 'NORMAL'))
            elif cmd == 'arm':
                _ros_node.cmd_arm(data.get('action', ''), data.get('degrees'))
            elif cmd == 'save_map':
                _ros_node.cmd_save_map()
            elif cmd == 'start_mapping':
                _ros_node.cmd_start_mapping(str(data.get('vehicle_id', 'aip1')),
                                            str(data.get('mode', 'manual')))
            elif cmd == 'stop_mapping':
                _ros_node.cmd_stop_mapping(str(data.get('vehicle_id', '')))
            elif cmd == 'load_saved_map':
                _ros_node.cmd_load_saved_map()
            elif cmd == 'publish_map_ready':
                _ros_node.cmd_map_ready()
            elif cmd == 'patrol_planner':
                _ros_node.cmd_patrol(data.get('patrol_cmd', ''))
            elif cmd == 'control_lock':
                _ros_node.cmd_lock(
                    str(data.get('operator_id', 'web')),
                    str(data.get('vehicle_id', 'aip2')),
                    bool(data.get('locked', False)),
                )
            elif cmd == 'override':
                _ros_node.cmd_override(
                    str(data.get('vehicle_id', 'aip2')),
                    int(data.get('command', 1)),
                    float(data.get('linear_x', 0.0)),
                    float(data.get('angular_z', 0.0)),
                )
            elif cmd == 'navigate_to':
                _ros_node.cmd_navigate(
                    str(data.get('vehicle_id', 'aip2')),
                    float(data.get('x', 0.0)),
                    float(data.get('y', 0.0)),
                    float(data.get('yaw_rad', 0.0)),
                    str(data.get('transport', 'topic')),
                )
            elif cmd == 'set_map_source':
                _ros_node.cmd_set_map_source(data.get('source', 'map_static'))
            elif cmd == 'reset_map':
                _ros_node.cmd_reset_map(str(data.get('vehicle_id', '')))
            elif cmd == 'keepout_zones':
                _ros_node.cmd_keepout(data.get('zones', []))
            elif cmd == 'set_dock':
                _ros_node.cmd_set_dock(
                    str(data.get('vehicle_id', 'aip2')),
                    float(data.get('x', 0.0)),
                    float(data.get('y', 0.0)),
                    float(data.get('yaw_rad', 0.0)),
                )
            elif cmd == 'set_pose_calibration':
                _ros_node.cmd_set_pose_calibration(
                    str(data.get('vehicle_id', 'aip2')),
                    float(data.get('x', 0.0)),
                    float(data.get('y', 0.0)),
                    float(data.get('yaw_rad', 0.0)),
                )
            elif cmd == 'clear_pose_calibration':
                _ros_node.cmd_clear_pose_calibration(
                    str(data.get('vehicle_id', 'aip2')),
                )
            elif cmd == 'esp32_reset':
                asyncio.create_task(_ros_node.esp32_reset(str(data.get('vehicle_id', ''))))
            elif cmd == 'start_bag':
                _start_bag()
            elif cmd == 'stop_bag':
                _stop_bag()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _clients.discard(ws)


app.mount('/static', StaticFiles(directory=str(_STATIC_DIR)), name='static')


@app.get('/')
async def _index() -> FileResponse:
    return FileResponse(str(_STATIC_DIR / 'index.html'))


def main() -> None:
    uvicorn.run(app, host='0.0.0.0', port=8080, log_level='warning')


if __name__ == '__main__':
    main()
