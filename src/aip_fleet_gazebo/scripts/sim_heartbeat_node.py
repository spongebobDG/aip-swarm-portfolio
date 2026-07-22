#!/usr/bin/env python3
"""sim_heartbeat_node — 시뮬 환경용 FleetHeartbeat 더미 퍼블리셔.

실제 차량에서는 하드웨어 드라이버가 heartbeat를 발행하지만,
Gazebo 시뮬에서는 하드웨어가 없으므로 이 노드가 대신 발행.
supervisor_node의 OFFLINE 판정을 방지하여 대시보드/Foxglove에서
차량 상태를 ONLINE으로 표시하기 위해 사용.

파라미터
----------
vehicle_ids : string[]  heartbeat를 발행할 차량 ID 목록 (기본: [peer_1, peer_2, peer_3])
publish_hz  : double    발행 주파수 (기본: 2.0 Hz — supervisor timeout=5s의 2배 이상)
state       : int       FleetHeartbeat.state 값 (기본: 1 = STATE_AUTO)
battery_pct : double    더미 배터리 값 (기본: 80.0)
cpu_load    : double    더미 CPU 부하 값 (기본: 0.3)
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from aip_fleet_msgs.msg import FleetHeartbeat


class SimHeartbeatNode(Node):
    def __init__(self):
        super().__init__('sim_heartbeat')

        self.declare_parameter('vehicle_ids', ['peer_1', 'peer_2', 'peer_3'])
        self.declare_parameter('publish_hz',  2.0)
        self.declare_parameter('state',       FleetHeartbeat.STATE_AUTO)
        self.declare_parameter('battery_pct', 80.0)
        self.declare_parameter('cpu_load',    0.3)

        self._vehicle_ids = list(self.get_parameter('vehicle_ids').value)
        self._state       = int(self.get_parameter('state').value)
        self._battery     = float(self.get_parameter('battery_pct').value)
        self._cpu         = float(self.get_parameter('cpu_load').value)
        hz                = float(self.get_parameter('publish_hz').value)

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self._pubs = {
            vid: self.create_publisher(FleetHeartbeat, f'/{vid}/heartbeat', qos)
            for vid in self._vehicle_ids
        }

        self.create_timer(1.0 / hz, self._publish_all)
        self.get_logger().info(
            f'sim_heartbeat: publishing for {self._vehicle_ids} at {hz:.1f} Hz'
        )

    def _publish_all(self):
        now = self.get_clock().now().to_msg()
        for vid, pub in self._pubs.items():
            msg = FleetHeartbeat()
            msg.vehicle_id  = vid
            msg.stamp       = now
            msg.state       = self._state
            msg.battery_pct = self._battery
            msg.cpu_load    = self._cpu
            pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = SimHeartbeatNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
