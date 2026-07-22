"""Fleet heartbeat 발행 노드 (실차 aip1).

2 Hz 주기로 FleetHeartbeat 를 발행한다.
supervisor_node 는 2초 이상 수신 없으면 watchdog ESTOP 경로를 활성화한다.

발행:
  /<ns>/heartbeat  aip_fleet_msgs/FleetHeartbeat  (2 Hz)
"""
from __future__ import annotations

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

from aip_fleet_msgs.msg import FleetHeartbeat

_RELIABLE = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)

HEARTBEAT_HZ = 2.0


class HeartbeatPubNode(Node):
    def __init__(self) -> None:
        super().__init__('heartbeat_pub')

        self.declare_parameter('vehicle_id', 'aip1')
        self._vid = self.get_parameter('vehicle_id').get_parameter_value().string_value

        self._pub = self.create_publisher(
            FleetHeartbeat, 'heartbeat', _RELIABLE)
        self._timer = self.create_timer(1.0 / HEARTBEAT_HZ, self._publish)

        self.get_logger().info(f'heartbeat_pub: vid={self._vid} @ {HEARTBEAT_HZ} Hz')

    def _publish(self) -> None:
        msg = FleetHeartbeat()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self._vid
        msg.robot_id = self._vid
        msg.mode = 'autonomous'
        msg.healthy = True
        msg.estop = False
        msg.heartbeat_stale = False
        msg.obstacle_stop = False
        msg.cmd_stale = False
        msg.battery_voltage = 0.0       # aip1은 유선 전원 — 배터리 센서 없음
        msg.battery_percentage = 0.0
        msg.status = 'ok'
        self._pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = HeartbeatPubNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
