#!/usr/bin/env python3
"""odom_frame_fixer.py — fix diff_drive_controller odom frame IDs and zero initial pose.

Ignition Fortress diff_drive_controller publishes nav_msgs/Odometry with:
  frame_id:       bare or namespaced (depends on plugin version)
  child_frame_id: bare or namespaced
  pose:           WORLD-FRAME absolute coordinates — at spawn the pose is the
                  spawn position, NOT (0, 0, 0).

slam_toolbox, AMCL, and robot_localization EKF all expect:
  frame_id:       'peer_N/odom'
  child_frame_id: 'peer_N/base_link'
  pose:           (0, 0, 0) at startup, integrating relative displacements.

This node:
  1. Rewrites frame_id / child_frame_id to namespaced equivalents.
  2. Stores the first received pose as the origin and subtracts it from all
     subsequent messages so the odom frame starts at (0, 0, 0).
     Without zeroing, EKF anchors peer_N/odom at world (0, 0) while the
     vehicle is at its spawn offset — causing odom TF to appear detached from
     the vehicle body in RViz and all downstream position estimates to be wrong.

Called by spawn_vehicle.launch.py with:
  python3 odom_frame_fixer.py --ros-args -p vehicle_id:=peer_1
"""
import math

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Quaternion
from nav_msgs.msg import Odometry


def _yaw_from_quat(q: Quaternion) -> float:
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def _quat_from_yaw(yaw: float) -> Quaternion:
    q = Quaternion()
    q.x = 0.0
    q.y = 0.0
    q.z = math.sin(yaw / 2.0)
    q.w = math.cos(yaw / 2.0)
    return q


class OdomFrameFixer(Node):
    def __init__(self):
        super().__init__('odom_frame_fixer')
        self.declare_parameter('vehicle_id', 'peer_1')
        vid = self.get_parameter('vehicle_id').value

        self._odom_frame      = f'{vid}/odom'
        self._base_link_frame = f'{vid}/base_link'
        self._origin: tuple[float, float, float] | None = None  # (x0, y0, yaw0)

        self._pub = self.create_publisher(
            Odometry, f'/{vid}/diff_drive_controller/odom_corrected', 10)
        self.create_subscription(
            Odometry, f'/{vid}/diff_drive_controller/odom', self._cb, 10)
        self.get_logger().info(
            f'odom_frame_fixer: /{vid}/diff_drive_controller/odom '
            f'→ /{vid}/diff_drive_controller/odom_corrected '
            f'(frame_id={self._odom_frame})')

    def _cb(self, msg: Odometry):
        if self._origin is None:
            x0   = msg.pose.pose.position.x
            y0   = msg.pose.pose.position.y
            yaw0 = _yaw_from_quat(msg.pose.pose.orientation)
            self._origin = (x0, y0, yaw0)
            self.get_logger().info(
                f'odom_frame_fixer: origin set to '
                f'({x0:.3f}, {y0:.3f}, {math.degrees(yaw0):.1f}°)')

        x0, y0, yaw0 = self._origin
        x1   = msg.pose.pose.position.x
        y1   = msg.pose.pose.position.y
        yaw1 = _yaw_from_quat(msg.pose.pose.orientation)

        # Express pose relative to initial position (general 2D rigid transform).
        # Equivalent to: T_rel = T0_inv * T1
        c, s = math.cos(yaw0), math.sin(yaw0)
        msg.pose.pose.position.x =  (x1 - x0) * c + (y1 - y0) * s
        msg.pose.pose.position.y = -(x1 - x0) * s + (y1 - y0) * c
        msg.pose.pose.position.z = 0.0
        msg.pose.pose.orientation = _quat_from_yaw(yaw1 - yaw0)

        msg.header.frame_id = self._odom_frame
        msg.child_frame_id  = self._base_link_frame
        self._pub.publish(msg)


def main():
    rclpy.init()
    node = OdomFrameFixer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
