"""Fleet supervisor: aggregates heartbeats and routes override commands.

Subscribes to every `/<vehicle_ns>/heartbeat` (FleetHeartbeat). Publishes
`/fleet/status` (FleetStatus) at 2 Hz. Subscribes to `/fleet/override`
(OverrideCommand) and translates it into per-vehicle
`/<vehicle_ns>/override_cmd_vel` (Twist) and `/<vehicle_ns>/estop` (Bool).
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Set

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from std_msgs.msg import Bool, String

from aip_fleet_msgs.msg import FleetHeartbeat, FleetStatus, OverrideCommand


DEFAULT_VEHICLES = ['aip1', 'aip2', 'aip3']
DEFAULT_VEHICLE_TOPIC_ALIASES = ['aip1=aip1', 'aip2=aip2', 'aip3=aip3']
HEARTBEAT_TIMEOUT_SEC = 2.0
STATUS_PUBLISH_HZ = 2.0
CONTROL_LOCK_TTL_SEC = 3.0


def _parse_vehicle_topic_aliases(entries: Iterable[str]) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for item in entries:
        text = str(item).strip().strip('/')
        if not text:
            continue
        if '=' in text:
            display_id, topic_id = text.split('=', 1)
        elif ':' in text:
            display_id, topic_id = text.split(':', 1)
        else:
            display_id = topic_id = text
        display_id = display_id.strip().strip('/')
        topic_id = topic_id.strip().strip('/')
        if display_id and topic_id:
            aliases[display_id] = topic_id
    return aliases


@dataclass
class ControlLock:
    operator_id: str
    vehicle_id: str
    stamp_wall: float


class SupervisorNode(Node):
    def __init__(self) -> None:
        super().__init__('aip_fleet_supervisor')

        self.declare_parameter('vehicle_ids', DEFAULT_VEHICLES)
        self.declare_parameter('vehicle_topic_aliases', DEFAULT_VEHICLE_TOPIC_ALIASES)
        self.declare_parameter('vehicle_cmd_vel_overrides', [''])
        self.declare_parameter('heartbeat_timeout_sec', HEARTBEAT_TIMEOUT_SEC)
        self.declare_parameter('control_lock_ttl_sec', CONTROL_LOCK_TTL_SEC)
        self.declare_parameter('require_control_lock', False)
        self.vehicle_ids = list(
            self.get_parameter('vehicle_ids').get_parameter_value().string_array_value
        ) or DEFAULT_VEHICLES
        self.heartbeat_timeout = float(
            self.get_parameter('heartbeat_timeout_sec').get_parameter_value().double_value
            or HEARTBEAT_TIMEOUT_SEC
        )
        self.control_lock_ttl = float(
            self.get_parameter('control_lock_ttl_sec').get_parameter_value().double_value
            or CONTROL_LOCK_TTL_SEC
        )
        self.require_control_lock = bool(
            self.get_parameter('require_control_lock').get_parameter_value().bool_value
        )
        alias_values = list(
            self.get_parameter('vehicle_topic_aliases').get_parameter_value().string_array_value
        ) or DEFAULT_VEHICLE_TOPIC_ALIASES
        alias_env = os.environ.get('AIP_VEHICLE_TOPIC_ALIASES', '').strip()
        if alias_env:
            alias_values = [item.strip() for item in alias_env.split(',') if item.strip()]
        self.vehicle_topic_aliases = _parse_vehicle_topic_aliases(alias_values)
        for vid in self.vehicle_ids:
            self.vehicle_topic_aliases.setdefault(vid, vid)
        self.topic_to_vehicle = {
            topic_id: display_id for display_id, topic_id in self.vehicle_topic_aliases.items()
        }

        cmd_vel_override_entries = list(
            self.get_parameter('vehicle_cmd_vel_overrides').get_parameter_value().string_array_value
        )
        self._cmd_vel_overrides: Dict[str, str] = {}
        for entry in cmd_vel_override_entries:
            if entry and '=' in entry:
                k, v = entry.split('=', 1)
                self._cmd_vel_overrides[k.strip()] = v.strip()

        self._last_heartbeat: Dict[str, FleetHeartbeat] = {}
        self._last_heartbeat_wall: Dict[str, float] = {}
        self._estop_locked: Set[str] = set()
        self._control_locks: Dict[str, ControlLock] = {}
        self._subscribed_vehicle_ids: Set[str] = set()

        reliable_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.VOLATILE,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        # Latched status so late-joining dashboards get the most recent snapshot.
        status_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # Per-vehicle subscriptions & override publishers.
        self._reliable_qos = reliable_qos
        self._override_twist_pubs: Dict[str, rclpy.publisher.Publisher] = {}
        self._estop_pubs: Dict[str, rclpy.publisher.Publisher] = {}
        self._estop_lock_pubs: Dict[str, rclpy.publisher.Publisher] = {}
        for vid in self.vehicle_ids:
            self._subscribe_vehicle(vid)

        # Fleet-wide override input & aggregated status output.
        self.create_subscription(
            OverrideCommand, '/fleet/override', self._on_override, reliable_qos
        )
        self.create_subscription(
            String, '/fleet/control_lock', self._on_control_lock, reliable_qos
        )
        self._status_pub = self.create_publisher(FleetStatus, '/fleet/status', status_qos)
        self._control_lock_state_pub = self.create_publisher(
            String, '/fleet/control_lock_state', status_qos
        )

        self.create_timer(1.0 / STATUS_PUBLISH_HZ, self._publish_status)
        self.create_timer(5.0, self._discover_vehicles)
        self.get_logger().info(
            f'Supervisor watching vehicles: {self.vehicle_ids} '
            f'(heartbeat timeout {self.heartbeat_timeout:.1f}s, '
            f'topic aliases {self.vehicle_topic_aliases})'
        )

    def _topic_id(self, vehicle_id: str) -> str:
        vid = str(vehicle_id).strip().strip('/')
        return self.vehicle_topic_aliases.get(vid, vid)

    def _display_id(self, vehicle_id: str) -> str:
        vid = str(vehicle_id).strip().strip('/')
        return self.topic_to_vehicle.get(vid, vid)

    def _subscribe_vehicle(self, vid: str) -> None:
        """차량 1대에 대한 구독·발행 설정. 최초 기동 및 자동 발견 시 모두 사용."""
        vid = self._display_id(vid)
        if vid in self._subscribed_vehicle_ids:
            return
        topic_vid = self._topic_id(vid)
        self.create_subscription(
            FleetHeartbeat, f'/{topic_vid}/heartbeat',
            self._make_heartbeat_cb(vid), self._reliable_qos,
        )
        cmd_vel_topic = self._cmd_vel_overrides.get(vid, f'/{topic_vid}/override_cmd_vel')
        self._override_twist_pubs[vid] = self.create_publisher(
            Twist, cmd_vel_topic, self._reliable_qos)
        self._estop_pubs[vid] = self.create_publisher(
            Bool, f'/{topic_vid}/estop', self._reliable_qos)
        self._estop_lock_pubs[vid] = self.create_publisher(
            Bool, f'/{topic_vid}/estop_lock', self._reliable_qos)
        self._subscribed_vehicle_ids.add(vid)
        if topic_vid != vid:
            self.get_logger().info(f'Alias route: {vid} -> /{topic_vid}/...')

    def _discover_vehicles(self) -> None:
        """5초마다 새 /{vid}/heartbeat 토픽을 발견하면 자동으로 차량 등록."""
        try:
            topic_types = self.get_topic_names_and_types()
        except Exception as exc:
            self.get_logger().debug(f'Vehicle discovery skipped: {exc}')
            return
        for name, types in topic_types:
            parts = name.split('/')
            # /{vid}/heartbeat 패턴: ['', vid, 'heartbeat']
            if len(parts) == 3 and parts[0] == '' and parts[2] == 'heartbeat':
                if 'aip_fleet_msgs/msg/FleetHeartbeat' not in types:
                    continue
                topic_vid = parts[1]
                vid = self._display_id(topic_vid)
                if vid not in self.vehicle_ids:
                    self.get_logger().info(f'[자동발견] 새 차량 등록: {vid}')
                    self.vehicle_ids.append(vid)
                    self.vehicle_topic_aliases.setdefault(vid, topic_vid)
                    self.topic_to_vehicle[topic_vid] = vid
                    self._subscribe_vehicle(vid)

    def _make_heartbeat_cb(self, vehicle_id: str):
        def _cb(msg: FleetHeartbeat) -> None:
            display_id = self._display_id(vehicle_id)
            self._last_heartbeat[display_id] = self._heartbeat_as_display(msg, display_id)
            self._last_heartbeat_wall[display_id] = time.monotonic()
        return _cb

    def _heartbeat_as_display(self, msg: FleetHeartbeat, vehicle_id: str) -> FleetHeartbeat:
        hb = FleetHeartbeat()
        hb.header.stamp = msg.header.stamp
        hb.header.frame_id = vehicle_id
        hb.robot_id = vehicle_id
        hb.mode = msg.mode
        hb.healthy = msg.healthy
        hb.estop = msg.estop
        hb.heartbeat_stale = msg.heartbeat_stale
        hb.obstacle_stop = msg.obstacle_stop
        hb.cmd_stale = msg.cmd_stale
        hb.battery_voltage = msg.battery_voltage
        hb.battery_percentage = msg.battery_percentage
        hb.status = msg.status
        return hb

    def _on_control_lock(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning('Ignoring malformed /fleet/control_lock payload')
            return

        operator_id = str(payload.get('operator_id', '')).strip()
        vehicle_id = str(payload.get('vehicle_id', '')).strip()
        locked = bool(payload.get('locked', False))
        if not operator_id or not vehicle_id:
            self.get_logger().warning('Ignoring incomplete /fleet/control_lock payload')
            return
        if vehicle_id != '*':
            vehicle_id = self._display_id(vehicle_id)

        targets = self.vehicle_ids if vehicle_id == '*' else [vehicle_id]
        now_wall = time.monotonic()
        for vid in targets:
            if vid not in self.vehicle_ids:
                self.get_logger().warning(f'Unknown vehicle in control lock: {vid}')
                continue
            if locked:
                self._control_locks[vid] = ControlLock(
                    operator_id=operator_id,
                    vehicle_id=vid,
                    stamp_wall=now_wall,
                )
            else:
                current = self._control_locks.get(vid)
                if current is None or current.operator_id == operator_id:
                    self._control_locks.pop(vid, None)
        self._publish_control_lock_state()

    def _prune_stale_control_locks(self) -> None:
        now_wall = time.monotonic()
        stale = [
            vid for vid, lock in self._control_locks.items()
            if now_wall - lock.stamp_wall > self.control_lock_ttl
        ]
        for vid in stale:
            self._control_locks.pop(vid, None)
        if stale:
            self._publish_control_lock_state()

    def _publish_control_lock_state(self) -> None:
        payload = {
            'locks': {
                vid: {
                    'operator_id': lock.operator_id,
                    'age_sec': round(time.monotonic() - lock.stamp_wall, 3),
                }
                for vid, lock in sorted(self._control_locks.items())
            },
            'require_control_lock': self.require_control_lock,
            'ttl_sec': self.control_lock_ttl,
        }
        self._control_lock_state_pub.publish(String(data=json.dumps(payload)))

    def _has_valid_control_lock(self, vehicle_id: str) -> bool:
        if not self.require_control_lock:
            return True
        self._prune_stale_control_locks()
        return vehicle_id in self._control_locks

    def _publish_status(self) -> None:
        self._prune_stale_control_locks()
        now_wall = time.monotonic()
        status = FleetStatus()
        status.stamp = self.get_clock().now().to_msg()
        status.vehicles = []
        status.offline_vehicle_ids = []
        for vid in self.vehicle_ids:
            hb = self._last_heartbeat.get(vid)
            last_wall = self._last_heartbeat_wall.get(vid, 0.0)
            if hb is None or (now_wall - last_wall) > self.heartbeat_timeout:
                status.offline_vehicle_ids.append(vid)
            else:
                status.vehicles.append(hb)
        self._status_pub.publish(status)
        # E-Stop 상태를 매 주기 권위적으로 재발행(estop_lock·estop 둘 다, 전 차량).
        # 일회성 VOLATILE 발행이 twist_mux(BEST_EFFORT)에 미도달하던 estop 해제 신뢰성 문제 방지.
        for vid in self.vehicle_ids:
            locked = Bool(data=(vid in self._estop_locked))
            if vid in self._estop_lock_pubs:
                self._estop_lock_pubs[vid].publish(locked)
            if vid in self._estop_pubs:
                self._estop_pubs[vid].publish(locked)

    def _on_override(self, msg: OverrideCommand) -> None:
        targets = self.vehicle_ids if msg.vehicle_id == '*' else [self._display_id(msg.vehicle_id)]
        for vid in targets:
            if vid not in self._override_twist_pubs:
                self.get_logger().warning(f'Unknown vehicle in override: {vid}')
                continue

            if msg.command == OverrideCommand.CMD_ESTOP:
                self._estop_locked.add(vid)
                self._estop_lock_pubs[vid].publish(Bool(data=True))
                self._estop_pubs[vid].publish(Bool(data=True))
                # Also publish zero twist as defense in depth.
                self._override_twist_pubs[vid].publish(Twist())
            elif msg.command in (OverrideCommand.CMD_CLEAR, OverrideCommand.CMD_RESUME):
                # E-Stop 해제는 락 만료 후에도 반드시 가능해야 한다 (데드락 방지).
                self._estop_locked.discard(vid)
                self._estop_lock_pubs[vid].publish(Bool(data=False))
                self._estop_pubs[vid].publish(Bool(data=False))
            elif not self._has_valid_control_lock(vid):
                self.get_logger().warning(
                    f'Ignoring override command {msg.command} for {vid}: no active control lock'
                )
            elif msg.command == OverrideCommand.CMD_PAUSE:
                self._override_twist_pubs[vid].publish(Twist())
            elif msg.command == OverrideCommand.CMD_MANUAL:
                self._override_twist_pubs[vid].publish(msg.manual_cmd_vel)
            else:
                self.get_logger().warning(
                    f'Unhandled override command {msg.command} for {vid}'
                )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SupervisorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
