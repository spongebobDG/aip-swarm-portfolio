"""Fleet coordinator node — publishes /<follower_ns>/coord_cmd_vel at 10 Hz.

One instance per follower vehicle. The follower tracks the leader at a
configurable (offset_x, offset_y) in the leader's body frame using a
bearing-based proportional controller resolved in the shared map frame.

TF requirement: both vehicles must publish <ns>/odom → <ns>/base_link,
and the world must provide the static map → <ns>/odom transform
(slam_toolbox / AMCL does this).

TF stale fallback
─────────────────
When a TF lookup fails transiently, the node holds the last known pose
for up to tf_stale_holdout_sec before zeroing.
This prevents sudden velocity spikes caused by momentary localization gaps.

Typical usage — spawn one node per scout:
  ros2 run aip_fleet_coordinator coordinator_node \\
      --ros-args -p leader_ns:=aip1 -p follower_ns:=aip2 -p offset_x:=-1.5
"""
from __future__ import annotations

import math
import time

import rclpy
import rclpy.duration
import rclpy.time
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
import tf2_ros


CONTROL_HZ = 10.0
TF_TIMEOUT_SEC = 0.05


def _quat_to_yaw(q) -> float:
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


def _wrap(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


class CoordinatorNode(Node):
    def __init__(self) -> None:
        super().__init__('coordinator_node')

        self.declare_parameter('leader_ns', 'aip1')
        self.declare_parameter('follower_ns', 'aip2')
        self.declare_parameter('offset_x', -1.5)   # m: negative = behind, positive = ahead (leader body frame +x)
        self.declare_parameter('offset_y', 0.0)    # m: positive = left of leader (leader body frame +y)
        self.declare_parameter('tf_stale_holdout_sec', 1.0)  # hold last pose on TF miss
        self.declare_parameter('kp_linear', 0.8)
        self.declare_parameter('kp_angular', 1.5)
        self.declare_parameter('max_linear_vel', 0.5)
        self.declare_parameter('max_angular_vel', 1.5)
        self.declare_parameter('goal_tolerance', 0.15)   # m: dead-band radius
        self.declare_parameter('alpha_turn_threshold', 1.05)  # rad (~60°): turn-in-place above this

        def p(name):
            return self.get_parameter(name).value

        self._leader = str(p('leader_ns'))
        self._follower = str(p('follower_ns'))
        self._offset_x = float(p('offset_x'))
        self._offset_y = float(p('offset_y'))
        self._kp_lin = float(p('kp_linear'))
        self._kp_ang = float(p('kp_angular'))
        self._v_max = float(p('max_linear_vel'))
        self._w_max = float(p('max_angular_vel'))
        self._tol = float(p('goal_tolerance'))
        self._alpha_thr = float(p('alpha_turn_threshold'))
        self._holdout = float(p('tf_stale_holdout_sec'))

        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)

        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self._cmd_pub = self.create_publisher(
            Twist, f'/{self._follower}/coord_cmd_vel', qos
        )

        # TF stale fallback: cache last known poses with timestamp
        self._last_pose: dict[str, tuple[float, float, float]] = {}
        self._last_pose_time: dict[str, float] = {}

        self.create_timer(1.0 / CONTROL_HZ, self._tick)

        self.get_logger().info(
            f'Coordinator: {self._follower} tracks {self._leader} '
            f'at offset ({self._offset_x:.2f}, {self._offset_y:.2f}) m'
            f' (stale holdout {self._holdout}s)'
        )

    # ------------------------------------------------------------------

    def _pose_in_map(self, ns: str):
        """Return (x, y, yaw) in the map frame.

        On TF success: updates cache and returns fresh data.
        On TF miss within holdout window: returns last cached pose.
        Beyond holdout: returns None (triggers zero velocity).
        """
        try:
            tf = self._tf_buffer.lookup_transform(
                'map',
                f'{ns}/base_link',
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=TF_TIMEOUT_SEC),
            )
            t = tf.transform
            pose = (t.translation.x, t.translation.y, _quat_to_yaw(t.rotation))
            self._last_pose[ns] = pose
            self._last_pose_time[ns] = time.monotonic()
            return pose
        except (tf2_ros.LookupException,
                tf2_ros.ConnectivityException,
                tf2_ros.ExtrapolationException):
            pass

        # TF miss — use cached pose within holdout window
        age = time.monotonic() - self._last_pose_time.get(ns, 0.0)
        if age <= self._holdout and ns in self._last_pose:
            self.get_logger().warn(
                f'TF miss for {ns}, using cached pose ({age:.2f}s old)',
                throttle_duration_sec=2.0,
            )
            return self._last_pose[ns]

        return None

    def _tick(self) -> None:
        leader = self._pose_in_map(self._leader)
        follower = self._pose_in_map(self._follower)

        cmd = Twist()  # zero by default — safe if TF unavailable

        if leader is None or follower is None:
            self._cmd_pub.publish(cmd)
            return

        lx, ly, lθ = leader
        fx, fy, fθ = follower

        # Target position in map frame: offset applied in leader body frame.
        tx = lx + self._offset_x * math.cos(lθ) - self._offset_y * math.sin(lθ)
        ty = ly + self._offset_x * math.sin(lθ) + self._offset_y * math.cos(lθ)

        dist = math.hypot(tx - fx, ty - fy)
        if dist < self._tol:
            self._cmd_pub.publish(cmd)
            return

        # Bearing to target in follower body frame.
        alpha = _wrap(math.atan2(ty - fy, tx - fx) - fθ)

        # Two-phase control — decouples angular correction from linear progress:
        #   Phase 1 (|alpha| > threshold): turn in place, no forward motion.
        #     Prevents cos(alpha) → 0 stall while the target keeps moving.
        #   Phase 2 (|alpha| <= threshold): drive forward at kp_lin * dist.
        #     No cos(alpha) penalty — heading is close enough to proceed.
        if abs(alpha) > self._alpha_thr:
            v = 0.0
        else:
            v = self._kp_lin * dist
        cmd.linear.x = max(-self._v_max, min(self._v_max, v))
        cmd.angular.z = max(-self._w_max, min(self._w_max, self._kp_ang * alpha))
        self._cmd_pub.publish(cmd)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CoordinatorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
