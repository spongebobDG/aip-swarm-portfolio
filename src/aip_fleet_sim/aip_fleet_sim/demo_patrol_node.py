"""Autonomous demo driver for the simulated leader vehicle.

This node is intentionally part of aip_fleet_sim only. It publishes a gentle
waypoint loop into /<leader_ns>/autonomy_cmd_vel so the web dashboard shows
live motion even when no real robot or Nav2 stack is present.
"""
from __future__ import annotations

import math
from typing import Optional

import rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _wrap_pi(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


class DemoPatrolNode(Node):
    def __init__(self) -> None:
        super().__init__('demo_patrol_node')

        self.declare_parameter('leader_ns', 'aip1')
        self.declare_parameter('rate_hz', 10.0)
        self.declare_parameter('max_linear_vel', 0.35)
        self.declare_parameter('max_angular_vel', 0.9)
        self.declare_parameter('goal_tolerance', 0.35)

        self.leader_ns = self.get_parameter('leader_ns').value
        self.max_v = float(self.get_parameter('max_linear_vel').value)
        self.max_w = float(self.get_parameter('max_angular_vel').value)
        self.goal_tol = float(self.get_parameter('goal_tolerance').value)

        # Waypoints stay in the leader odom frame. They are chosen to run
        # through the open aisles in config/world.yaml.
        self._waypoints = [
            (0.0, 0.0),
            (4.6, 0.0),
            (4.6, 4.7),
            (0.6, 4.7),
            (0.6, 1.0),
            (-4.7, 1.0),
            (-4.7, -4.7),
            (3.8, -4.7),
            (4.8, -0.6),
            (0.0, 0.0),
        ]
        self._goal_index = 1
        self._pose: Optional[tuple[float, float, float]] = None

        self._cmd_pub = self.create_publisher(
            Twist, f'/{self.leader_ns}/autonomy_cmd_vel', 10
        )
        self.create_subscription(
            Odometry, f'/{self.leader_ns}/odom', self._on_odom, 10
        )

        rate = float(self.get_parameter('rate_hz').value)
        self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(
            f'Demo patrol driving /{self.leader_ns}/autonomy_cmd_vel '
            f'with {len(self._waypoints)} waypoints'
        )

    def _on_odom(self, msg: Odometry) -> None:
        q = msg.pose.pose.orientation
        yaw = 2.0 * math.atan2(q.z, q.w)
        self._pose = (
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
            yaw,
        )

    def _tick(self) -> None:
        if self._pose is None:
            return

        x, y, yaw = self._pose
        gx, gy = self._waypoints[self._goal_index]
        dx = gx - x
        dy = gy - y
        dist = math.hypot(dx, dy)

        if dist < self.goal_tol:
            self._goal_index = (self._goal_index + 1) % len(self._waypoints)
            gx, gy = self._waypoints[self._goal_index]
            dx = gx - x
            dy = gy - y
            dist = math.hypot(dx, dy)
            self.get_logger().info(
                f'Next demo waypoint {self._goal_index}: ({gx:.1f}, {gy:.1f})'
            )

        desired = math.atan2(dy, dx)
        heading_error = _wrap_pi(desired - yaw)

        msg = Twist()
        msg.angular.z = _clamp(1.6 * heading_error, -self.max_w, self.max_w)

        # Slow down while turning sharply so the leader visibly follows aisles.
        heading_scale = max(0.15, 1.0 - abs(heading_error) / 1.4)
        distance_scale = _clamp(dist / 1.0, 0.25, 1.0)
        msg.linear.x = self.max_v * heading_scale * distance_scale

        self._cmd_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DemoPatrolNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
