"""Fleet watchdog.

Subscribes to `/fleet/status` and forces an ESTOP OverrideCommand on any
vehicle that disappears from the heartbeat roster. The supervisor is
responsible for the actual per-vehicle plumbing; the watchdog only
publishes the fleet-level trigger so the two responsibilities stay split.

Hysteresis: a vehicle must appear in `offline_vehicle_ids` for
`OFFLINE_CONFIRM_COUNT` consecutive status cycles before ESTOP fires.
Status is published at 2 Hz by the supervisor, so with the default of 3
the minimum time-to-ESTOP after true loss is ~1.5 s while a single
dropped heartbeat (≤1 cycle) is absorbed silently. This prevents
transient Wi-Fi jitter from stopping the fleet.
"""
from __future__ import annotations

from typing import Dict, Set

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

from aip_fleet_msgs.msg import FleetStatus, OverrideCommand


REPEAT_SEC = 1.0           # how often to re-assert ESTOP while a vehicle stays offline
OFFLINE_CONFIRM_COUNT = 3  # consecutive status cycles before declaring offline


class WatchdogNode(Node):
    def __init__(self) -> None:
        super().__init__('aip_fleet_watchdog')

        self.declare_parameter('offline_confirm_count', OFFLINE_CONFIRM_COUNT)
        self._confirm_threshold = int(
            self.get_parameter('offline_confirm_count').get_parameter_value().integer_value
            or OFFLINE_CONFIRM_COUNT
        )

        reliable_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )
        # Must match the supervisor's /fleet/status publisher durability.
        status_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # Confirmed-offline set (ESTOP already asserted).
        self._offline: Set[str] = set()
        # Consecutive-miss counters; tracked only for vehicles currently
        # reported offline by the supervisor but not yet confirmed.
        self._miss_counts: Dict[str, int] = {}

        self._override_pub = self.create_publisher(
            OverrideCommand, '/fleet/override', reliable_qos
        )
        self.create_subscription(
            FleetStatus, '/fleet/status', self._on_status, status_qos
        )
        self.create_timer(REPEAT_SEC, self._reassert_offline)
        self.get_logger().info(
            f'Watchdog armed (offline_confirm_count={self._confirm_threshold}).'
        )

    def _on_status(self, msg: FleetStatus) -> None:
        reported = set(msg.offline_vehicle_ids)

        # Reset counters for anyone who recovered in this cycle.
        for vid in list(self._miss_counts.keys()):
            if vid not in reported:
                del self._miss_counts[vid]

        # Vehicles that have recovered *after* we already ESTOP'd them.
        recovered = self._offline - reported
        for vid in recovered:
            self.get_logger().info(f'Vehicle {vid} recovered — clearing ESTOP')
            self._send_clear(vid)
        self._offline -= recovered

        # Accumulate misses; promote to confirmed-offline once threshold hit.
        for vid in reported:
            if vid in self._offline:
                continue  # already ESTOP'd; handled by _reassert_offline
            self._miss_counts[vid] = self._miss_counts.get(vid, 0) + 1
            if self._miss_counts[vid] >= self._confirm_threshold:
                self.get_logger().warning(
                    f'Vehicle {vid} offline for {self._miss_counts[vid]} cycles — forcing ESTOP'
                )
                self._offline.add(vid)
                del self._miss_counts[vid]
                self._send_estop(vid)
            else:
                self.get_logger().debug(
                    f'Vehicle {vid} missing ({self._miss_counts[vid]}/{self._confirm_threshold})'
                )

    def _reassert_offline(self) -> None:
        for vid in self._offline:
            self._send_estop(vid)

    def _send_estop(self, vehicle_id: str) -> None:
        msg = OverrideCommand()
        msg.vehicle_id = vehicle_id
        msg.stamp = self.get_clock().now().to_msg()
        msg.command = OverrideCommand.CMD_ESTOP
        self._override_pub.publish(msg)

    def _send_clear(self, vehicle_id: str) -> None:
        msg = OverrideCommand()
        msg.vehicle_id = vehicle_id
        msg.stamp = self.get_clock().now().to_msg()
        msg.command = OverrideCommand.CMD_CLEAR
        self._override_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = WatchdogNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
