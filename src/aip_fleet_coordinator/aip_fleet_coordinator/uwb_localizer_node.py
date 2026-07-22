"""uwb_localizer_node.py — cooperative UWB + PDoA + odom fusion localizer.

.. deprecated::
    DEPRECATED (2026-06-15): 전 차량 LiDAR+SLAM 채택으로 UWB 측위 불필요.
    실차에서 이 노드를 실행하지 않는다. 코드는 참고용으로 보존.

Estimates map → <ns>/base_link TF for vehicles that lack LiDAR.

Anchor hierarchy (highest → lowest weight)
───────────────────────────────────────────
1. Fixed infrastructure anchors  — UWB beacons at known positions (weight = 1.0)
2. SLAM peers                    — vehicles in slam_peer_ids (weight = 1.0)
3. Cooperative estimated peers   — other vehicles also running this node
                                   (weight = estimated_peer_weight, default 0.5)

Cooperative localization
────────────────────────
When peer_1 has SLAM and peer_2/3 run this node:

  peer_1 (SLAM) → /fleet/peer_poses with peer_1 position
  sim/UWB       → /fleet/peer_ranges with pairwise distances + AoA
  peer_2 node   : uses peer_1 (w=1.0) + peer_3 estimate (w=0.5) as anchors
  peer_3 node   : uses peer_1 (w=1.0) + peer_2 estimate (w=0.5) as anchors

Algorithm (weighted Gauss-Newton with range + AoA)
────────────────────────────────────────────────────
  Prediction : odom delta → update (x_est, y_est, θ_est)
  Correction : per anchor i, two residuals accumulated into the same
               2×2 normal equation (JᵀWJ)Δ = −JᵀWf:

    ① Range residual (radial, meters):
         f_r = ‖[x,y] − aᵢ‖ − r_meas
         J_r = [(x−aₓ)/d,  (y−aᵧ)/d]
         weight: w / σ_r²

    ② AoA tangential residual (perpendicular to ①, meters):
         φ_exp = atan2(aᵧ−y, aₓ−x) − θ_est   ← expected AoA in body frame
         f_t   = d · wrap(φ_meas − φ_exp)      ← tangential displacement (m)
         J_t   = [−(aᵧ−y)/d,  (aₓ−x)/d]       ← tangential unit vector
         weight: w / σ_t²  where σ_t = d · σ_aoa

    Both residuals are normalised to meters so they accumulate without
    unit mismatch.  AoA weight decreases with distance (σ_t = d·σ_aoa),
    which correctly reflects that ranging precision (fixed σ_r) dominates
    at long distances while AoA adds most value at short range.

    θ_est is odom-only (UWB provides no heading information).
    With 0 usable anchors: pure odom dead-reckoning.
    With 1 anchor + AoA : full 2-D position fix possible.
    With 1 anchor, no AoA: range-circle constraint only.
    With ≥2 anchors     : over-determined, robust 2-D position fix.

Sim / real swap
───────────────
  Sim  : sim_peer_sensing_node  → /fleet/peer_ranges (range + AoA)
                                → /fleet/peer_poses
  Real : UWB driver (DWM3001C…) → /fleet/peer_ranges
         SLAM nodes per vehicle  → /fleet/peer_poses  (aggregated centrally)

ROS parameters
──────────────
  vehicle_id             string      own namespace           default: peer_2
  slam_peer_ids          string[]    peers with SLAM (w=1.0) default: [peer_1]
  estimated_peer_weight  float       weight for cooperative  default: 0.5
  anchor_ids             string[]    fixed anchor IDs        default: []
  anchor_x               float[]     anchor X positions (m)  default: []
  anchor_y               float[]     anchor Y positions (m)  default: []
  publish_hz             float       TF publish rate         default: 20.0
  gn_iter                int         Gauss-Newton iterations default: 5
  gn_alpha               float       GN step damping         default: 0.6
  stale_timeout_sec      float       suppress TF after stale default: 2.0
  range_noise_m          float       expected range σ (m)    default: 0.05
  aoa_noise_rad          float       expected AoA σ (rad)    default: 0.087 (~5°)
  child_frame_suffix     string      suffix appended to base_link frame
                                     default: '' (no suffix, real-operation mode)
                                     set to '_uwb_est' for shadow / comparison mode
                                     so TF child = peer_N/base_link_uwb_est
  initial_x              float       initial map-frame x estimate (m)  default: 0.0
  initial_y              float       initial map-frame y estimate (m)  default: 0.0
  initial_yaw            float       initial heading (rad)             default: 0.0
                                     These MUST match the vehicle's spawn position.
                                     Without them the estimator initialises at odom
                                     origin (0,0) which may be far from the anchor,
                                     causing a d=0 singularity in the first correction.
  d_min_aoa_m            float       min anchor distance (m) to apply AoA constraint
                                     default: 0.30 m.  AoA Jacobian ∝ 1/d → diverges
                                     at short range; skip AoA below this threshold.
  uwb_trigger_dist_m     float       odom travel distance (m) between UWB corrections
                                     default: 0.0 (disabled → correct on every odom cb).
                                     Set > 0 for real hardware to suppress UWB correction
                                     during short moves where odom is more accurate than
                                     UWB (e.g. 0.5 m).  UWB then fires only when
                                     accumulated drift is large enough to benefit.
"""
from __future__ import annotations

import math
import time

import rclpy
import rclpy.duration
import rclpy.time
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
import tf2_ros

from aip_fleet_msgs.msg import PeerPoseArray, PeerRangeArray

_NAN = float('nan')


def _quat_to_yaw(q) -> float:
    siny = 2.0 * (q.w * q.z + q.x * q.y)
    cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny, cosy)


def _yaw_to_quat(yaw: float) -> tuple[float, float, float, float]:
    half = yaw * 0.5
    return 0.0, 0.0, math.sin(half), math.cos(half)


def _wrap(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


# Measurement stored per ranging anchor:
#   (range_m, range_noise_m, aoa_rad_or_nan, aoa_noise_rad_or_nan)
_RangeMeas = tuple[float, float, float, float]


class UwbLocalizerNode(Node):

    def __init__(self) -> None:
        super().__init__('uwb_localizer_node')

        self.declare_parameter('vehicle_id',            'peer_2')
        self.declare_parameter('slam_peer_ids',         ['peer_1'])
        self.declare_parameter('estimated_peer_weight', 0.5)
        self.declare_parameter('anchor_ids',            [''])    # string[] workaround
        self.declare_parameter('anchor_x',              [0.0])
        self.declare_parameter('anchor_y',              [0.0])
        self.declare_parameter('publish_hz',            20.0)
        self.declare_parameter('gn_iter',               5)
        self.declare_parameter('gn_alpha',              0.6)
        self.declare_parameter('stale_timeout_sec',     2.0)
        self.declare_parameter('range_noise_m',         0.05)
        self.declare_parameter('aoa_noise_rad',         0.087)   # ~5 degrees
        self.declare_parameter('child_frame_suffix',    '')
        self.declare_parameter('initial_x',             0.0)
        self.declare_parameter('initial_y',             0.0)
        self.declare_parameter('initial_yaw',           0.0)
        self.declare_parameter('d_min_aoa_m',           0.30)
        self.declare_parameter('uwb_trigger_dist_m',    0.0)

        def p(n):
            return self.get_parameter(n).value

        self._vid          = str(p('vehicle_id'))
        self._slam_ids     = set(p('slam_peer_ids'))
        self._est_w        = float(p('estimated_peer_weight'))
        self._gn_iter      = int(p('gn_iter'))
        self._gn_alpha     = float(p('gn_alpha'))
        self._stale_to     = float(p('stale_timeout_sec'))
        self._sigma_r      = float(p('range_noise_m'))
        self._sigma_aoa    = float(p('aoa_noise_rad'))
        self._frame_suffix = str(p('child_frame_suffix'))
        self._init_x       = float(p('initial_x'))
        self._init_y       = float(p('initial_y'))
        self._init_yaw     = float(p('initial_yaw'))
        self._d_min_aoa       = float(p('d_min_aoa_m'))
        self._trigger_dist    = float(p('uwb_trigger_dist_m'))
        self._odom_dist_acc   = 0.0   # accumulated odom travel since last UWB correction

        # ── Fixed infrastructure anchors ───────────────────────────────────────
        raw_ids = list(p('anchor_ids'))
        raw_x   = list(p('anchor_x'))
        raw_y   = list(p('anchor_y'))
        self._fixed_anchors: dict[str, tuple[float, float]] = {
            aid: (ax, ay)
            for aid, ax, ay in zip(raw_ids, raw_x, raw_y)
            if aid
        }
        if self._fixed_anchors:
            self.get_logger().info(
                f'Fixed anchors: {list(self._fixed_anchors.keys())}'
            )

        # ── Estimated state (map frame) ────────────────────────────────────────
        # Seeded from initial_x/y/yaw parameters (must match spawn position).
        # Odom delta is applied on top of this estimate.
        self._x = self._init_x
        self._y = self._init_y
        self._θ = self._init_yaw
        self._initialized = False

        # ── Odom tracking ─────────────────────────────────────────────────────
        self._odom_x: float | None = None
        self._odom_y: float | None = None
        self._odom_θ: float | None = None
        self._last_odom_time: float = 0.0

        # ── Latest peer data ──────────────────────────────────────────────────
        self._anchor_poses: dict[str, tuple[float, float]] = {}
        # _ranges: anchor_id → (range_m, range_noise_m, aoa_rad, aoa_noise_rad)
        #   aoa_rad / aoa_noise_rad are NaN when PDoA unavailable
        self._ranges: dict[str, _RangeMeas] = {}

        # ── TF broadcaster ────────────────────────────────────────────────────
        self._tf_broadcaster = tf2_ros.TransformBroadcaster(self)

        # ── Subscriptions ──────────────────────────────────────────────────────
        self.create_subscription(
            Odometry,       f'/{self._vid}/odom',  self._odom_cb,   10)
        self.create_subscription(
            PeerPoseArray,  '/fleet/peer_poses',   self._poses_cb,  10)
        self.create_subscription(
            PeerRangeArray, '/fleet/peer_ranges',  self._ranges_cb, 10)

        hz = float(p('publish_hz'))
        self.create_timer(1.0 / hz, self._publish_tf)

        child_frame = f'{self._vid}/base_link{self._frame_suffix}'
        self.get_logger().info(
            f'uwb_localizer/{self._vid}: '
            f'SLAM peers={list(self._slam_ids)}, '
            f'est_weight={self._est_w}, '
            f'fixed_anchors={len(self._fixed_anchors)}, '
            f'sigma_r={self._sigma_r} m, '
            f'sigma_aoa={math.degrees(self._sigma_aoa):.1f} deg, '
            f'child_frame={child_frame}, '
            f'@ {hz} Hz'
        )

    # ── callbacks ──────────────────────────────────────────────────────────────

    def _odom_cb(self, msg: Odometry) -> None:
        ox = msg.pose.pose.position.x
        oy = msg.pose.pose.position.y
        oθ = _quat_to_yaw(msg.pose.pose.orientation)

        if not self._initialized:
            # Keep self._x, self._y, self._θ from initial_* parameters.
            # Only record the odom reference so delta tracking starts correctly.
            self._odom_x, self._odom_y, self._odom_θ = ox, oy, oθ
            self._initialized = True
            self._last_odom_time = time.monotonic()
            return

        # ── odom delta → world-frame prediction ───────────────────────────────
        dx_o = ox - self._odom_x
        dy_o = oy - self._odom_y
        dθ_o = _wrap(oθ - self._odom_θ)

        cos_o, sin_o = math.cos(self._odom_θ), math.sin(self._odom_θ)
        d_fwd  =  dx_o * cos_o + dy_o * sin_o
        d_side = -dx_o * sin_o + dy_o * cos_o

        cos_e, sin_e = math.cos(self._θ), math.sin(self._θ)
        self._x += d_fwd * cos_e - d_side * sin_e
        self._y += d_fwd * sin_e + d_side * cos_e
        self._θ  = _wrap(self._θ + dθ_o)

        step = math.hypot(dx_o, dy_o)
        self._odom_dist_acc  += step
        self._odom_x, self._odom_y, self._odom_θ = ox, oy, oθ
        self._last_odom_time = time.monotonic()

        # UWB correction: always when trigger_dist==0, else only after
        # sufficient odom travel (prevents UWB from overriding accurate odom
        # during short moves where σ_odom < σ_uwb).
        if (self._trigger_dist <= 0.0
                or self._odom_dist_acc >= self._trigger_dist):
            self._uwb_correct()
            self._odom_dist_acc = 0.0

    def _poses_cb(self, msg: PeerPoseArray) -> None:
        self._anchor_poses = {
            pp.vehicle_id: (pp.pose.position.x, pp.pose.position.y)
            for pp in msg.poses
            if pp.vehicle_id != self._vid
        }

    def _ranges_cb(self, msg: PeerRangeArray) -> None:
        ranges: dict[str, _RangeMeas] = {}
        for pr in msg.ranges:
            # Determine which AoA field corresponds to our antenna
            if pr.vehicle_a == self._vid:
                aoa = pr.aoa_a_rad
                other = pr.vehicle_b
            elif pr.vehicle_b == self._vid:
                aoa = pr.aoa_b_rad
                other = pr.vehicle_a
            else:
                continue
            ranges[other] = (
                pr.range_m,
                pr.noise_stddev_m if pr.noise_stddev_m > 0.0 else self._sigma_r,
                aoa,
                pr.aoa_noise_stddev_rad,
            )
        self._ranges = ranges

    # ── anchor weight ──────────────────────────────────────────────────────────

    def _weight(self, aid: str) -> float:
        if aid in self._fixed_anchors:
            return 1.0
        if aid in self._slam_ids:
            return 1.0
        if aid in self._anchor_poses:
            return self._est_w
        return 0.0

    def _anchor_pos(self, aid: str) -> tuple[float, float] | None:
        if aid in self._fixed_anchors:
            return self._fixed_anchors[aid]
        if aid in self._anchor_poses:
            return self._anchor_poses[aid]
        return None

    # ── weighted Gauss-Newton correction (range + PDoA AoA) ───────────────────

    def _uwb_correct(self) -> None:
        """Correct (x, y) using range and optional AoA measurements.

        Both residuals accumulate into the same 2×2 normal equation, so the
        single linear solve handles mixed range/AoA constraints naturally.

        Normalisation
        ─────────────
        To make range (meters) and tangential-AoA (also meters after d·angle)
        commensurable, each residual is divided by its expected 1-σ noise:

          f_r_norm = f_r / σ_r            (≈ dimensionless "sigma units")
          f_t_norm = d·angle_err / σ_t    (where σ_t = d·σ_aoa → simplifies to
                                           angle_err / σ_aoa — distance cancels)

        Jacobians (scaled by sqrt(w) / σ_*):
          J_r = sqrt(w)/σ_r  · [(x−aₓ)/d, (y−aᵧ)/d]   ← radial unit vector
          J_t = sqrt(w)/σ_aoa · [−(aᵧ−y)/d², (aₓ−x)/d²]
              = sqrt(w)/σ_aoa · [−(aᵧ−y), (aₓ−x)] / d²
        """
        if not self._ranges:
            return

        x, y = self._x, self._y

        for _ in range(self._gn_iter):
            jtj00 = jtj01 = jtj11 = jtf0 = jtf1 = 0.0

            for aid, (r_meas, sigma_r_meas, aoa_meas, aoa_noise_meas) in self._ranges.items():
                w = self._weight(aid)
                if w <= 0.0:
                    continue
                pos = self._anchor_pos(aid)
                if pos is None:
                    continue

                ax, ay = pos
                d = math.hypot(x - ax, y - ay)
                if d < 1e-6:
                    continue

                # ── ① Range residual ────────────────────────────────────────
                sigma_r = sigma_r_meas if sigma_r_meas > 0.0 else self._sigma_r
                sw_r    = math.sqrt(w) / sigma_r
                jx_r    = sw_r * (x - ax) / d
                jy_r    = sw_r * (y - ay) / d
                fr_r    = sw_r * (d - r_meas)

                jtj00 += jx_r * jx_r
                jtj01 += jx_r * jy_r
                jtj11 += jy_r * jy_r
                jtf0  += jx_r * fr_r
                jtf1  += jy_r * fr_r

                # ── ② AoA tangential residual ───────────────────────────────
                # Skip if AoA is NaN (non-PDoA hardware or fixed anchor).
                # Also skip when d < d_min_aoa: J_t ∝ 1/d diverges at short range.
                if math.isnan(aoa_meas) or d < self._d_min_aoa:
                    continue

                sigma_aoa = (aoa_noise_meas
                             if (not math.isnan(aoa_noise_meas) and aoa_noise_meas > 0.0)
                             else self._sigma_aoa)

                # Expected AoA in our body frame:
                #   bearing from us to anchor in map frame, then minus our heading
                phi_exp = _wrap(math.atan2(ay - y, ax - x) - self._θ)
                angle_err = _wrap(aoa_meas - phi_exp)

                # Normalised tangential residual (distance cancels):
                #   f_t_norm = d·angle_err / (d·σ_aoa) = angle_err / σ_aoa
                sw_t = math.sqrt(w) / sigma_aoa
                fr_t = sw_t * angle_err

                # Tangential Jacobian (⊥ to radial):
                #   ∂f_t_norm/∂x = −(aᵧ−y) / (d² · σ_aoa)
                #   ∂f_t_norm/∂y =  (aₓ−x) / (d² · σ_aoa)
                d2   = d * d
                jx_t = -sw_t * (ay - y) / d2
                jy_t =  sw_t * (ax - x) / d2

                jtj00 += jx_t * jx_t
                jtj01 += jx_t * jy_t
                jtj11 += jy_t * jy_t
                jtf0  += jx_t * fr_t
                jtf1  += jy_t * fr_t

            det = jtj00 * jtj11 - jtj01 ** 2
            if abs(det) < 1e-12:
                break   # singular (anchors collinear or no usable constraints)

            dx = -(jtj11 * jtf0 - jtj01 * jtf1) / det * self._gn_alpha
            dy = -(-jtj01 * jtf0 + jtj00 * jtf1) / det * self._gn_alpha

            x += dx
            y += dy

            if math.hypot(dx, dy) < 1e-4:
                break

        self._x, self._y = x, y

    # ── TF publish ─────────────────────────────────────────────────────────────

    def _publish_tf(self) -> None:
        if not self._initialized:
            return

        age = time.monotonic() - self._last_odom_time
        if age > self._stale_to:
            self.get_logger().warn(
                f'uwb_localizer/{self._vid}: odom stale {age:.1f}s — TF suppressed',
                throttle_duration_sec=5.0,
            )
            return

        qx, qy, qz, qw = _yaw_to_quat(self._θ)
        tf_msg = TransformStamped()
        tf_msg.header.stamp    = self.get_clock().now().to_msg()
        tf_msg.header.frame_id = 'map'
        tf_msg.child_frame_id  = f'{self._vid}/base_link{self._frame_suffix}'
        tf_msg.transform.translation.x = self._x
        tf_msg.transform.translation.y = self._y
        tf_msg.transform.translation.z = 0.0
        tf_msg.transform.rotation.x    = qx
        tf_msg.transform.rotation.y    = qy
        tf_msg.transform.rotation.z    = qz
        tf_msg.transform.rotation.w    = qw
        self._tf_broadcaster.sendTransform(tf_msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = UwbLocalizerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
