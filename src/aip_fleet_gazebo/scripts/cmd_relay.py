#!/usr/bin/env python3
"""cmd_relay.py — relay /<ns>/cmd_vel → /<ns>/diff_drive_controller/cmd_vel_unstamped.

Bridges the fleet-standard /<ns>/cmd_vel (output of twist_mux) to the
ros2_control diff_drive_controller input topic.

Called by spawn_vehicle.launch.py with:
  python3 cmd_relay.py --ros-args -p vehicle_id:=peer_1
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


class CmdRelay(Node):
    def __init__(self):
        super().__init__('cmd_relay')
        self.declare_parameter('vehicle_id', 'peer_1')
        vid = self.get_parameter('vehicle_id').value

        self._pub = self.create_publisher(
            Twist, f'/{vid}/diff_drive_controller/cmd_vel_unstamped', 10)
        self.create_subscription(
            Twist, f'/{vid}/cmd_vel', self._cb, 10)
        self.get_logger().info(
            f'relay: /{vid}/cmd_vel → /{vid}/diff_drive_controller/cmd_vel_unstamped')

    def _cb(self, msg: Twist):
        self._pub.publish(msg)


def main():
    rclpy.init()
    node = CmdRelay()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
