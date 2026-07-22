#!/usr/bin/env python3
"""sim_peer_sensing_node.py — inter-vehicle + anchor sensing simulator.

Reads each vehicle's pose from the TF tree (map → <ns>/base_link) and publishes:

  /fleet/peer_poses   PeerPoseArray  — SLAM-derived absolute positions (10 Hz)
  /fleet/peer_ranges  PeerRangeArray — pairwise ranges + AoA with noise (10 Hz)

PDoA angle-of-arrival (AoA) simulation
────────────────────────────────────────
For each pair (A, B) the node computes:
  aoa_a_rad: bearing from B to A as seen by A's antenna, in A's body frame.
             = atan2(Bᵧ - Aᵧ, Bₓ - Aₓ) - θ_A + Gaussian noise
  aoa_b_rad: same from B's perspective.

Vehicle heading θ is extracted from the TF rotation quaternion.
If heading is unavailable (TF lookup partial), AoA fields are set to NaN.

Fixed infrastructure anchors (optional)
────────────────────────────────────────
UWB beacons at known fixed positions can be simulated via the anchor_*
parameters.  Fixed anchors have no heading → aoa fields are always NaN.

Design intent
─────────────
  Sim path  : TF + anchor parameters → this node
  Real path : UWB driver (DWM3001C …) + SLAM pose publisher → same topics

ROS parameters
──────────────
  vehicle_ids              string[]  vehicles to track       default: peer_1..peer_3
  range_noise_stddev_m     float     UWB-like range noise σ  default: 0.05 m
  aoa_noise_stddev_rad     float     PDoA AoA noise σ        default: 0.087 rad (5 deg)
  max_range_m              float     drop pairs beyond this  default: 10.0 m
  publish_hz               float     publish rate            default: 10.0 Hz
  tf_timeout_sec           float     TF lookup timeout       default: 0.05 s
  anchor_ids               string[]  fixed anchor IDs        default: []
  anchor_x                 float[]   anchor X positions (m)  default: []
  anchor_y                 float[]   anchor Y positions (m)  default: []
"""
from __future__ import annotations

import math
import random

import rclpy
import rclpy.duration
import rclpy.time
from rclpy.node import Node
import tf2_ros

from aip_fleet_msgs.msg import (
    PeerPose,
    PeerPoseArray,
    PeerRange,
    PeerRangeArray,
)

_DEFAULT_VEHICLES = ['peer_1', 'peer_2', 'peer_3']
_NAN = float('nan')


def _quat_to_yaw(rot) -> float:
    siny = 2.0 * (rot.w * rot.z + rot.x * rot.y)
    cosy = 1.0 - 2.0 * (rot.y * rot.y + rot.z * rot.z)
    return math.atan2(siny, cosy)


def _wrap(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


class SimPeerSensingNode(Node):

    def __init__(self) -> None:
        super().__init__('sim_peer_sensing_node')

        self.declare_parameter('vehicle_ids',            _DEFAULT_VEHICLES)
        self.declare_parameter('range_noise_stddev_m',   0.05)
        self.declare_parameter('aoa_noise_stddev_rad',   0.087)   # ~5 degrees
        self.declare_parameter('max_range_m',            10.0)
        self.declare_parameter('publish_hz',             10.0)
        self.declare_parameter('tf_timeout_sec',         0.05)
        self.declare_parameter('anchor_ids',             [''])
        self.declare_parameter('anchor_x',               [0.0])
        self.declare_parameter('anchor_y',               [0.0])

        self._ids        = list(self.get_parameter('vehicle_ids').value)
        self._noise_r    = float(self.get_parameter('range_noise_stddev_m').value)
        self._noise_aoa  = float(self.get_parameter('aoa_noise_stddev_rad').value)
        self._max_range  = float(self.get_parameter('max_range_m').value)
        self._tf_timeout = float(self.get_parameter('tf_timeout_sec').value)

        # Fixed infrastructure anchors {id: (x, y)}
        raw_ids = list(self.get_parameter('anchor_ids').value)
        raw_x   = list(self.get_parameter('anchor_x').value)
        raw_y   = list(self.get_parameter('anchor_y').value)
        self._anchors: dict[str, tuple[float, float]] = {
            aid: (ax, ay)
            for aid, ax, ay in zip(raw_ids, raw_x, raw_y)
            if aid
        }
        if self._anchors:
            self.get_logger().info(f'Simulating fixed anchors: {list(self._anchors.keys())}')

        self._tf_buf      = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buf, self)

        self._pub_poses  = self.create_publisher(PeerPoseArray,  '/fleet/peer_poses',  10)
        self._pub_ranges = self.create_publisher(PeerRangeArray, '/fleet/peer_ranges', 10)

        hz = float(self.get_parameter('publish_hz').value)
        self.create_timer(1.0 / hz, self._tick)

        self.get_logger().info(
            f'sim_peer_sensing: {self._ids}, '
            f'noise_r={self._noise_r} m, '
            f'noise_aoa={math.degrees(self._noise_aoa):.1f} deg, '
            f'max_range={self._max_range} m, '
            f'anchors={len(self._anchors)} @ {hz} Hz'
        )

    # ── helpers ────────────────────────────────────────────────────────────────

    def _lookup(self, vehicle_id: str):
        """Return (x, y, yaw) in map frame, or None on TF miss."""
        try:
            tf = self._tf_buf.lookup_transform(
                'map',
                f'{vehicle_id}/base_link',
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=self._tf_timeout),
            )
        except (tf2_ros.LookupException,
                tf2_ros.ConnectivityException,
                tf2_ros.ExtrapolationException):
            return None
        t = tf.transform
        return t.translation.x, t.translation.y, _quat_to_yaw(t.rotation)

    def _noisy_range(self, x1: float, y1: float,
                     x2: float, y2: float) -> float | None:
        """Noisy Euclidean range, or None if beyond max_range_m."""
        d = math.hypot(x1 - x2, y1 - y2)
        if d > self._max_range:
            return None
        return max(0.0, d + random.gauss(0.0, self._noise_r))

    def _noisy_aoa(self, rx: float, ry: float, r_yaw: float,
                   tx: float, ty: float) -> float:
        """AoA of transmitter signal as seen at receiver antenna, body frame.

        Computes the true bearing from receiver to transmitter in map frame,
        rotates into receiver's body frame, and adds Gaussian noise.
        """
        bearing_map = math.atan2(ty - ry, tx - rx)
        aoa_body    = _wrap(bearing_map - r_yaw)
        return _wrap(aoa_body + random.gauss(0.0, self._noise_aoa))

    # ── main loop ──────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        now = self.get_clock().now().to_msg()

        # ── 1. collect vehicle poses from TF ────────────────────────────────
        poses: dict[str, tuple[float, float, float]] = {}   # vid → (x, y, yaw)
        for vid in self._ids:
            result = self._lookup(vid)
            if result is not None:
                poses[vid] = result

        if not poses:
            return

        # ── 2. /fleet/peer_poses ────────────────────────────────────────────
        pose_array = PeerPoseArray()
        pose_array.stamp = now
        for vid, (x, y, yaw) in poses.items():
            half = yaw * 0.5
            pp = PeerPose()
            pp.vehicle_id              = vid
            pp.pose.position.x         = x
            pp.pose.position.y         = y
            pp.pose.position.z         = 0.0
            pp.pose.orientation.z      = math.sin(half)
            pp.pose.orientation.w      = math.cos(half)
            pp.covariance_xy_m         = 0.0
            pose_array.poses.append(pp)
        self._pub_poses.publish(pose_array)

        # ── 3. /fleet/peer_ranges ───────────────────────────────────────────
        range_array = PeerRangeArray()
        range_array.stamp = now

        ids = list(poses.keys())

        # Vehicle ↔ vehicle pairs (bilateral AoA: both sides measured)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                xa, ya, θa = poses[a]
                xb, yb, θb = poses[b]

                r = self._noisy_range(xa, ya, xb, yb)
                if r is None:
                    continue

                # AoA at A's antenna: direction FROM which B's signal arrives
                # = bearing from A to B, in A's body frame
                aoa_a = self._noisy_aoa(xa, ya, θa, xb, yb)
                # AoA at B's antenna: direction FROM which A's signal arrives
                aoa_b = self._noisy_aoa(xb, yb, θb, xa, ya)

                pr = PeerRange()
                pr.vehicle_a             = a
                pr.vehicle_b             = b
                pr.range_m               = r
                pr.noise_stddev_m        = self._noise_r
                pr.aoa_a_rad             = aoa_a
                pr.aoa_b_rad             = aoa_b
                pr.aoa_noise_stddev_rad  = self._noise_aoa
                range_array.ranges.append(pr)

        # Vehicle ↔ fixed anchor pairs (anchors have no heading → AoA = NaN)
        for vid, (vx, vy, _) in poses.items():
            for aid, (ax, ay) in self._anchors.items():
                r = self._noisy_range(vx, vy, ax, ay)
                if r is None:
                    continue
                pr = PeerRange()
                pr.vehicle_a             = vid
                pr.vehicle_b             = aid
                pr.range_m               = r
                pr.noise_stddev_m        = self._noise_r
                pr.aoa_a_rad             = _NAN  # anchor has no heading
                pr.aoa_b_rad             = _NAN
                pr.aoa_noise_stddev_rad  = _NAN
                range_array.ranges.append(pr)

        self._pub_ranges.publish(range_array)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SimPeerSensingNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
