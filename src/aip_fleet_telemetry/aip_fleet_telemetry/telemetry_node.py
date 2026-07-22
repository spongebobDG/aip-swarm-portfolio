"""Fleet telemetry bridge — writes /fleet/status to InfluxDB 2.x.

Subscribes to /fleet/status (aip_fleet_msgs/FleetStatus) and writes one
InfluxDB point per vehicle per message, plus a separate measurement for
operator override events from /fleet/override.

Parameters (set via docker-compose environment or ROS2 params file):
  influx_url    – http://192.168.0.9:8086
  influx_token  – InfluxDB admin token (from .env INFLUXDB_ADMIN_TOKEN)
  influx_org    – InfluxDB organisation (from .env INFLUXDB_ORG)
  influx_bucket – InfluxDB bucket      (from .env INFLUXDB_BUCKET)
"""
from __future__ import annotations

import os

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy,
)
from std_msgs.msg import String

from aip_fleet_msgs.msg import FleetStatus

try:
    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import SYNCHRONOUS
    _INFLUX_OK = True
except ImportError:
    _INFLUX_OK = False


_STATE_NAMES = {0: 'IDLE', 1: 'AUTO', 2: 'MANUAL', 3: 'ESTOP', 4: 'FAULT'}


class TelemetryNode(Node):
    def __init__(self) -> None:
        super().__init__('aip_fleet_telemetry')

        self.declare_parameter('influx_url',    os.getenv('INFLUX_URL',    'http://localhost:8086'))
        self.declare_parameter('influx_token',  os.getenv('INFLUX_TOKEN',  ''))
        self.declare_parameter('influx_org',    os.getenv('INFLUX_ORG',    'aip'))
        self.declare_parameter('influx_bucket', os.getenv('INFLUX_BUCKET', 'fleet'))

        url    = self.get_parameter('influx_url').get_parameter_value().string_value
        token  = self.get_parameter('influx_token').get_parameter_value().string_value
        org    = self.get_parameter('influx_org').get_parameter_value().string_value
        bucket = self.get_parameter('influx_bucket').get_parameter_value().string_value

        self._org    = org
        self._bucket = bucket
        self._write_api = None

        if not _INFLUX_OK:
            self.get_logger().warning(
                'influxdb_client not installed — running in dry-run mode. '
                'Install with: pip3 install influxdb-client'
            )
        elif not token:
            self.get_logger().warning('influx_token is empty — running in dry-run mode.')
        else:
            client = InfluxDBClient(url=url, token=token, org=org)
            self._write_api = client.write_api(write_options=SYNCHRONOUS)
            self.get_logger().info(f'Connected to InfluxDB at {url} org={org} bucket={bucket}')

        latched_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.create_subscription(FleetStatus, '/fleet/status', self._on_status, latched_qos)

        best_effort_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.create_subscription(String, '/fleet/override', self._on_override, best_effort_qos)

        self.get_logger().info('TelemetryNode ready.')

    # ------------------------------------------------------------------

    def _write(self, points: list) -> None:
        if self._write_api is None:
            for p in points:
                self.get_logger().debug(f'[dry-run] {p.to_line_protocol()}')
            return
        try:
            self._write_api.write(bucket=self._bucket, org=self._org, record=points)
        except Exception as exc:
            self.get_logger().warning(f'InfluxDB write failed: {exc}')

    def _on_status(self, msg: FleetStatus) -> None:
        points = []
        online_ids = {v.vehicle_id for v in msg.vehicles}

        for hb in msg.vehicles:
            p = (
                Point('fleet_vehicle')
                .tag('vehicle_id', hb.vehicle_id)
                .field('battery_pct', float(hb.battery_pct))
                .field('cpu_load',    float(hb.cpu_load))
                .field('state',       int(hb.state))
                .field('state_name',  _STATE_NAMES.get(hb.state, 'UNKNOWN'))
                .field('online',      1)
            )
            points.append(p)

        for vid in msg.offline_vehicle_ids:
            if vid and vid not in online_ids:
                points.append(
                    Point('fleet_vehicle')
                    .tag('vehicle_id', vid)
                    .field('online', 0)
                )

        if points:
            self._write(points)

    def _on_override(self, msg: String) -> None:
        p = (
            Point('fleet_override')
            .field('command', msg.data)
        )
        self._write([p])


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TelemetryNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
