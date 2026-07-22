"""Kinematic diff-drive simulator for a single vehicle.

Integrates `<ns>/cmd_vel` at 50 Hz, publishes `<ns>/odom`, the dynamic TF
`<ns>/odom → <ns>/base_link`, a `<ns>/heartbeat` at 2 Hz, and an `<ns>/estop`
latch handler that freezes motion until cleared.
"""
from __future__ import annotations

import math
import time

import rclpy
from geometry_msgs.msg import TransformStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from std_msgs.msg import Bool
from tf2_ros import TransformBroadcaster

from aip_fleet_msgs.msg import FleetHeartbeat


INTEGRATION_HZ = 50.0
HEARTBEAT_HZ = 2.0


def _yaw_to_quat(theta: float):
    return (0.0, 0.0, math.sin(theta / 2.0), math.cos(theta / 2.0))


class SimVehicleNode(Node):
    def __init__(self) -> None:
        super().__init__('sim_vehicle_node')

        self.declare_parameter('vehicle_id', 'aip1')
        self.declare_parameter('initial_x', 0.0)
        self.declare_parameter('initial_y', 0.0)
        self.declare_parameter('initial_theta', 0.0)
        self.declare_parameter('max_linear_vel', 0.8)
        self.declare_parameter('max_angular_vel', 1.5)
        self.declare_parameter('battery_drain_per_sec', 0.02)

        self.vid = self.get_parameter('vehicle_id').get_parameter_value().string_value
        self.x = float(self.get_parameter('initial_x').value)
        self.y = float(self.get_parameter('initial_y').value)
        self.theta = float(self.get_parameter('initial_theta').value)
        self.v_max = float(self.get_parameter('max_linear_vel').value)
        self.w_max = float(self.get_parameter('max_angular_vel').value)
        self.battery_drain = float(self.get_parameter('battery_drain_per_sec').value)

        self._cmd_v = 0.0
        self._cmd_w = 0.0
        self._cmd_stamp = time.monotonic()
        self._estop = False
        self._battery = 100.0
        self._last_integrate = time.monotonic()

        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self.create_subscription(Twist, f'/{self.vid}/cmd_vel', self._on_cmd_vel, qos)
        self.create_subscription(Bool, f'/{self.vid}/estop', self._on_estop, qos)

        self._odom_pub = self.create_publisher(Odometry, f'/{self.vid}/odom', qos)
        self._heartbeat_pub = self.create_publisher(
            FleetHeartbeat, f'/{self.vid}/heartbeat', qos
        )
        self._tf = TransformBroadcaster(self)

        self.create_timer(1.0 / INTEGRATION_HZ, self._tick)
        self.create_timer(1.0 / HEARTBEAT_HZ, self._publish_heartbeat)

        # When Foxglove/operator manually drives via override_cmd_vel, the
        # twist_mux output reaches us as cmd_vel already — no separate handling.
        # We also accept override_cmd_vel directly so the sim is usable without
        # twist_mux installed. Lower priority than cmd_vel (last write wins).
        self.create_subscription(Twist, f'/{self.vid}/override_cmd_vel', self._on_cmd_vel, qos)

        self.get_logger().info(
            f'[{self.vid}] spawn x={self.x:.2f} y={self.y:.2f} θ={self.theta:.2f}'
        )

    # ------------------------------------------------------------------
    def _on_cmd_vel(self, msg: Twist) -> None:
        self._cmd_v = max(-self.v_max, min(self.v_max, msg.linear.x))
        self._cmd_w = max(-self.w_max, min(self.w_max, msg.angular.z))
        self._cmd_stamp = time.monotonic()

    def _on_estop(self, msg: Bool) -> None:
        if msg.data != self._estop:
            self.get_logger().warning(
                f'[{self.vid}] ESTOP = {msg.data}'
            )
        self._estop = msg.data

    # ------------------------------------------------------------------
    def _tick(self) -> None:
        now = time.monotonic()
        dt = now - self._last_integrate
        self._last_integrate = now

        # Command freshness watchdog — stop if no cmd_vel for 0.5 s.
        stale = (now - self._cmd_stamp) > 0.5
        v = 0.0 if (self._estop or stale) else self._cmd_v
        w = 0.0 if (self._estop or stale) else self._cmd_w

        self.theta += w * dt
        self.theta = math.atan2(math.sin(self.theta), math.cos(self.theta))
        self.x += v * math.cos(self.theta) * dt
        self.y += v * math.sin(self.theta) * dt

        self._battery = max(0.0, self._battery - self.battery_drain * dt)

        self._publish_odom(v, w)
        self._publish_tf()

    def _publish_odom(self, v: float, w: float) -> None:
        msg = Odometry()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = f'{self.vid}/odom'
        msg.child_frame_id = f'{self.vid}/base_link'
        msg.pose.pose.position.x = self.x
        msg.pose.pose.position.y = self.y
        qx, qy, qz, qw = _yaw_to_quat(self.theta)
        msg.pose.pose.orientation.x = qx
        msg.pose.pose.orientation.y = qy
        msg.pose.pose.orientation.z = qz
        msg.pose.pose.orientation.w = qw
        msg.twist.twist.linear.x = v
        msg.twist.twist.angular.z = w
        self._odom_pub.publish(msg)

    def _publish_tf(self) -> None:
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = f'{self.vid}/odom'
        t.child_frame_id = f'{self.vid}/base_link'
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        qx, qy, qz, qw = _yaw_to_quat(self.theta)
        t.transform.rotation.x = qx
        t.transform.rotation.y = qy
        t.transform.rotation.z = qz
        t.transform.rotation.w = qw
        self._tf.sendTransform(t)

    def _publish_heartbeat(self) -> None:
        stale = (time.monotonic() - self._cmd_stamp) > 0.5
        m = FleetHeartbeat()
        m.header.stamp = self.get_clock().now().to_msg()
        m.header.frame_id = self.vid
        m.robot_id = self.vid
        moving_cmd = (abs(self._cmd_v) + abs(self._cmd_w)) > 1e-3
        m.mode = 'autonomous' if moving_cmd and not stale else 'manual'
        m.healthy = not self._estop
        m.estop = self._estop
        m.heartbeat_stale = False
        m.obstacle_stop = False
        m.cmd_stale = stale
        m.battery_voltage = 0.0
        m.battery_percentage = self._battery
        m.status = 'estop' if self._estop else ('cmd_stale' if stale else 'ok')
        self._heartbeat_pub.publish(m)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SimVehicleNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
