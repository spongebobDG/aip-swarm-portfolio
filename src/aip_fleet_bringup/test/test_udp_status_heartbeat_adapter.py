from __future__ import annotations

import importlib.util
import math
from pathlib import Path

from builtin_interfaces.msg import Time

from aip_fleet_msgs.msg import FleetHeartbeat


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts'
    / 'udp_status_heartbeat_adapter.py'
)
SPEC = importlib.util.spec_from_file_location('udp_status_heartbeat_adapter', MODULE_PATH)
adapter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(adapter)


# ── vehicle_id_from_payload ──────────────────────────────────────────────────

def test_vehicle_id_accepts_legacy_keys_and_strips_slashes():
    assert adapter.vehicle_id_from_payload({'vehicle_id': '/aip1'}) == 'aip1'
    assert adapter.vehicle_id_from_payload({'robot_id': 'aip2'}) == 'aip2'
    assert adapter.vehicle_id_from_payload({'id': 'aip3'}) == 'aip3'
    assert adapter.vehicle_id_from_payload({}) == ''


# ── mode_from_payload ────────────────────────────────────────────────────────

def test_mode_from_payload_explicit_mode_field():
    assert adapter.mode_from_payload({'mode': 'autonomous'}) == 'autonomous'
    assert adapter.mode_from_payload({'mode': 'manual'}) == 'manual'
    assert adapter.mode_from_payload({'mode': 'AUTONOMOUS'}) == 'autonomous'


def test_mode_from_payload_falls_back_to_state_field():
    assert adapter.mode_from_payload({'state': 'AUTO'}) == 'autonomous'
    assert adapter.mode_from_payload({'state': 'AUTONOMOUS'}) == 'autonomous'
    assert adapter.mode_from_payload({'state': 'MANUAL'}) == 'manual'


def test_mode_from_payload_defaults_to_manual():
    assert adapter.mode_from_payload({}) == 'manual'
    assert adapter.mode_from_payload({'estop': True}) == 'manual'


# ── battery_from_payload ─────────────────────────────────────────────────────

def test_battery_clamps_high_value():
    _voltage, pct = adapter.battery_from_payload({'battery': 150})
    assert pct == 100.0


def test_battery_clamps_negative_value():
    _voltage, pct = adapter.battery_from_payload({'battery_percentage': -5})
    assert pct == 0.0


def test_battery_accepts_multiple_key_names():
    _, pct1 = adapter.battery_from_payload({'battery': 73.4})
    _, pct2 = adapter.battery_from_payload({'battery_pct': 73.4})
    _, pct3 = adapter.battery_from_payload({'battery_percentage': 73.4})
    assert pct1 == pct2 == pct3 == 73.4


# ── cpu_load_from_payload ────────────────────────────────────────────────────

def test_cpu_load_normalizes_percent_integer():
    assert adapter.cpu_load_from_payload({'cpu': 43}) == 0.43


def test_cpu_load_keeps_fraction_as_is():
    assert adapter.cpu_load_from_payload({'cpu': 0.5}) == 0.5


def test_cpu_load_clamps_over_100():
    assert adapter.cpu_load_from_payload({'cpu_load': 3.0}) == 1.0


def test_cpu_load_defaults_to_zero():
    assert adapter.cpu_load_from_payload({}) == 0.0


# ── behaviors_from_payload ───────────────────────────────────────────────────

def test_behaviors_are_bounded_to_8_items():
    payload = {'behaviors': [f'behavior-{i}' for i in range(12)]}
    behaviors = adapter.behaviors_from_payload(payload)
    assert len(behaviors) == 8


def test_behaviors_each_item_max_64_chars():
    payload = {'behaviors': ['x' * 80]}
    behaviors = adapter.behaviors_from_payload(payload)
    assert all(len(item) <= 64 for item in behaviors)


def test_behaviors_status_appended_if_not_duplicate():
    payload = {'behaviors': ['udp_status_only'], 'status': 'container_up'}
    behaviors = adapter.behaviors_from_payload(payload)
    assert behaviors == ['udp_status_only', 'container_up']


def test_behaviors_status_not_duplicated():
    payload = {'behaviors': ['ok'], 'status': 'ok'}
    behaviors = adapter.behaviors_from_payload(payload)
    assert behaviors.count('ok') == 1


def test_behaviors_status_over_64_chars_truncated():
    payload = {'status': 'x' * 80}
    behaviors = adapter.behaviors_from_payload(payload)
    assert len(behaviors[0]) == 64


# ── heartbeat_from_payload ───────────────────────────────────────────────────

def test_heartbeat_from_payload_uses_current_schema_fields():
    stamp = Time(sec=123, nanosec=456)
    msg = adapter.heartbeat_from_payload(
        'aip2',
        {
            'mode': 'manual',
            'battery': 73.4,
            'cpu': 25,
            'behaviors': ['udp_status_only'],
            'status': 'container_up',
            'healthy': True,
            'estop': False,
        },
        stamp,
    )
    assert msg.robot_id == 'aip2'
    assert msg.header.stamp == stamp
    assert msg.header.frame_id == 'aip2'
    assert msg.mode == 'manual'
    assert msg.healthy is True
    assert msg.estop is False
    assert msg.heartbeat_stale is False
    _, expected_pct = adapter.battery_from_payload({'battery': 73.4})
    assert msg.battery_percentage == expected_pct
    assert msg.status == 'container_up'


def test_heartbeat_from_payload_estop_flag():
    stamp = Time(sec=0, nanosec=0)
    msg = adapter.heartbeat_from_payload('aip3', {'estop': True}, stamp)
    assert msg.estop is True
    assert msg.healthy is True   # healthy 필드는 별도 판단


def test_heartbeat_from_payload_healthy_defaults_true():
    stamp = Time(sec=0, nanosec=0)
    msg = adapter.heartbeat_from_payload('aip1', {}, stamp)
    assert msg.healthy is True
    assert msg.mode == 'manual'
    assert msg.status == 'ok'


# ── peer_pose_from_payload ───────────────────────────────────────────────────

def test_peer_pose_from_nested_pose_payload():
    msg = adapter.peer_pose_from_payload(
        'aip2',
        {
            'pose': {
                'x': 1.25,
                'y': -0.5,
                'yaw_rad': math.pi / 2,
                'covariance_xy_m': 0.12,
            },
        },
    )
    assert msg is not None
    assert msg.vehicle_id == 'aip2'
    assert msg.pose.position.x == 1.25
    assert msg.pose.position.y == -0.5
    assert round(msg.pose.orientation.z, 6) == round(math.sin(math.pi / 4), 6)
    assert round(msg.pose.orientation.w, 6) == round(math.cos(math.pi / 4), 6)
    assert msg.covariance_xy_m == 0.12


def test_peer_pose_accepts_top_level_legacy_pose_keys():
    msg = adapter.peer_pose_from_payload(
        'aip3',
        {
            'pose_x': -2.0,
            'pose_y': 3.5,
            'pose_yaw': -0.25,
        },
    )
    assert msg is not None
    assert msg.vehicle_id == 'aip3'
    assert msg.pose.position.x == -2.0
    assert msg.pose.position.y == 3.5


def test_peer_pose_missing_coordinates_returns_none():
    assert adapter.peer_pose_from_payload('aip1', {'pose': {'yaw_rad': 1.0}}) is None
    assert adapter.peer_pose_from_payload('aip1', {}) is None
