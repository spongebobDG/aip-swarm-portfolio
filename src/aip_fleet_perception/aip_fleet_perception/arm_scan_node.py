"""arm_scan_node.py — 서보암 스캔 패턴 실행 노드.

설계 변경 대응 원칙:
  - 관절 수·이름·자세: arm_config.yaml 에서만 정의
  - 제어 인터페이스: controller_type 파라미터로 분기
    'servo'      → /{vid}/servo_cmd (UInt8MultiArray deg) — ESP32 PWM(MG996R×4). 실차 aip1.
    'trajectory' → JointTrajectoryAction (ros2_control 표준)
    'position'   → Float64 토픽 (단순 PWM 서보 드라이버)
  - 코드는 YAML 구조를 읽어 동작 → 하드웨어 변경 시 코드 수정 최소

상태 머신:
  IDLE → (scan_request) → MOVING → COLLECTING → MOVING → ... → STOWING → IDLE

구독:
  /{vid}/arm/scan_request   std_msgs/Bool    (true: 스캔 시작)
  /{vid}/arm/estop          std_msgs/Bool    (true: 즉시 stow)

발행:
  /{vid}/arm/state          std_msgs/String  (IDLE/MOVING/COLLECTING/STOWING/ERROR)
  /{vid}/arm/scan_complete  std_msgs/Bool    (스캔 완료 신호)
  /{vid}/servo_cmd          std_msgs/UInt8MultiArray (servo 모드, deg 0~180 ×4 → serial_bridge)
  /{vid}/arm/joint_cmd      trajectory_msgs/JointTrajectory  (trajectory 모드)
  /{vid}/arm/joint_N_cmd    std_msgs/Float64 (position 모드, N = 0,1,2,...)
"""
from __future__ import annotations

import os
import threading
import time
from enum import Enum, auto

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Bool, Float64, String, UInt8MultiArray

try:
    from control_msgs.action import FollowJointTrajectory
    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
    from builtin_interfaces.msg import Duration
    _TRAJ_AVAILABLE = True
except ImportError:
    _TRAJ_AVAILABLE = False


class ArmState(Enum):
    IDLE       = auto()
    MOVING     = auto()
    COLLECTING = auto()
    STOWING    = auto()
    ERROR      = auto()


class ArmScanNode(Node):
    def __init__(self) -> None:
        super().__init__('arm_scan')

        self.declare_parameter('vehicle_id',   'peer_1')
        self.declare_parameter('config_file',  '')

        vid = self.get_parameter('vehicle_id').value
        self._vid = vid

        cfg_file = self.get_parameter('config_file').value
        if not cfg_file:
            share = get_package_share_directory('aip_fleet_perception')
            cfg_file = os.path.join(share, 'config', 'arm_config.yaml')

        with open(cfg_file) as f:
            cfg = yaml.safe_load(f)

        self._arm_cfg     = cfg['arm']
        self._ctrl_cfg    = cfg['control']
        self._mount_frame = cfg['sensor_mount']['frame_id']

        self._joints      = self._arm_cfg['joint_names']
        self._poses       = self._arm_cfg['poses']
        self._sequence    = self._arm_cfg['scan_sequence']
        self._dwell       = float(self._arm_cfg['dwell_time_s'])
        self._move_dur    = float(self._arm_cfg['move_duration_s'])
        self._return_stow = bool(self._arm_cfg.get('return_to_stow', True))
        self._ctrl_type   = self._ctrl_cfg['controller_type']

        self._state  = ArmState.IDLE
        self._estop  = False
        self._lock   = threading.Lock()
        self._thread: threading.Thread | None = None

        # ── 제어 인터페이스 초기화 ────────────────────────────────────────
        if self._ctrl_type == 'servo':
            # servo 모드: rad → deg 변환 후 /{vid}/servo_cmd (UInt8MultiArray) 발행.
            # serial_bridge 가 동일 토픽을 구독 → PKT_SERVO → ESP32 PWM(MG996R×4).
            self._servo_calib = self._build_servo_calib()
            self._servo_pub = self.create_publisher(
                UInt8MultiArray, f'/{vid}/servo_cmd', 10)
            self.get_logger().info(
                f'servo mode → /{vid}/servo_cmd (deg 0~180 ×{len(self._joints)})')
        elif self._ctrl_type == 'trajectory' and _TRAJ_AVAILABLE:
            action_name = f'/{vid}/{self._ctrl_cfg["action_name"]}'
            self._traj_client = ActionClient(
                self, FollowJointTrajectory, action_name)
            self.get_logger().info(f'trajectory mode → {action_name}')
        else:
            # position 모드: 관절별 Float64 토픽
            prefix = self._ctrl_cfg.get('position_topic_prefix', 'arm_joint_cmd')
            self._pos_pubs = [
                self.create_publisher(Float64, f'/{vid}/{prefix}_{i}', 10)
                for i in range(len(self._joints))
            ]
            self.get_logger().info(
                f'position mode → {len(self._joints)} joint topics')

        # ── 발행 ──────────────────────────────────────────────────────────
        self._pub_state    = self.create_publisher(String, f'/{vid}/arm/state',         10)
        self._pub_complete = self.create_publisher(Bool,   f'/{vid}/arm/scan_complete',  10)

        # ── 구독 ──────────────────────────────────────────────────────────
        self.create_subscription(Bool, f'/{vid}/arm/scan_request', self._cb_request, 10)
        self.create_subscription(Bool, f'/{vid}/arm/estop',        self._cb_estop,   10)

        self.create_timer(0.5, self._publish_state)

        self.get_logger().info(
            f'arm_scan ready  vehicle={vid}  joints={self._joints}  '
            f'sequence={self._sequence}  ctrl={self._ctrl_type}')
        self.get_logger().info(
            '스캔 트리거: ros2 topic pub --once '
            f'/{vid}/arm/scan_request std_msgs/Bool \'{{data: true}}\'')

    # ── 콜백 ─────────────────────────────────────────────────────────────
    def _cb_request(self, msg: Bool) -> None:
        if not msg.data:
            return
        with self._lock:
            if self._state != ArmState.IDLE:
                self.get_logger().warn('스캔 요청 무시 — 현재 동작 중')
                return
        self._thread = threading.Thread(target=self._run_scan, daemon=True)
        self._thread.start()

    def _cb_estop(self, msg: Bool) -> None:
        if msg.data:
            self._estop = True
            self.get_logger().warn('ESTOP 수신 — 즉시 stow 이동')
            threading.Thread(target=self._stow, daemon=True).start()

    # ── 스캔 실행 ─────────────────────────────────────────────────────────
    def _run_scan(self) -> None:
        self.get_logger().info(f'스캔 시작: {self._sequence}')
        try:
            for pose_name in self._sequence:
                if self._estop:
                    break
                if pose_name not in self._poses:
                    self.get_logger().warn(f'정의되지 않은 자세: {pose_name} — 건너뜀')
                    continue

                self._set_state(ArmState.MOVING)
                self._move_to(pose_name)

                if self._estop:
                    break

                self._set_state(ArmState.COLLECTING)
                self.get_logger().info(f'수집 중: {pose_name}  ({self._dwell}s)')
                time.sleep(self._dwell)

            if self._return_stow and not self._estop:
                self._stow()
            else:
                self._set_state(ArmState.IDLE)

            self._pub_complete.publish(Bool(data=True))
            self.get_logger().info('스캔 완료')

        except Exception as e:
            self.get_logger().error(f'스캔 오류: {e}')
            self._set_state(ArmState.ERROR)

    def _stow(self) -> None:
        self._set_state(ArmState.STOWING)
        self._move_to('stow')
        self._estop = False
        self._set_state(ArmState.IDLE)

    # ── 관절 이동 (controller_type 분기) ──────────────────────────────────
    def _move_to(self, pose_name: str) -> None:
        angles = self._poses[pose_name]

        if len(angles) != len(self._joints):
            self.get_logger().error(
                f'{pose_name}: 관절 수 불일치 '
                f'(설정={len(angles)}, 실제={len(self._joints)})')
            return

        self.get_logger().info(
            f'→ {pose_name}: {[f"{a:.2f}" for a in angles]}')

        if self._ctrl_type == 'servo':
            self._send_servo(angles)
        elif self._ctrl_type == 'trajectory' and _TRAJ_AVAILABLE:
            self._send_trajectory(angles)
        else:
            self._send_position(angles)

        # 이동 완료 대기 (간이 대기 — action feedback 사용 시 교체)
        time.sleep(self._move_dur)

    def _send_trajectory(self, angles: list[float]) -> None:
        if not self._traj_client.wait_for_server(timeout_sec=2.0):
            self.get_logger().warn('trajectory action 서버 미응답 — position 모드로 폴백')
            self._send_position(angles)
            return

        point = JointTrajectoryPoint()
        point.positions = angles
        point.time_from_start = Duration(
            sec=int(self._move_dur),
            nanosec=int((self._move_dur % 1.0) * 1e9))

        traj = JointTrajectory()
        traj.joint_names = self._joints
        traj.points      = [point]

        goal = FollowJointTrajectory.Goal()
        goal.trajectory = traj
        self._traj_client.send_goal_async(goal)

    def _send_position(self, angles: list[float]) -> None:
        for i, angle in enumerate(angles):
            if hasattr(self, '_pos_pubs'):
                self._pos_pubs[i].publish(Float64(data=angle))

    # ── servo 모드: rad → MG996R deg(0~180) 변환 후 servo_cmd 발행 ──────────
    def _build_servo_calib(self) -> list[dict]:
        raw = self._ctrl_cfg.get('servo', {}) or {}
        calib = []
        for j in self._joints:
            c = raw.get(j, {}) or {}
            calib.append({
                'neutral': float(c.get('neutral_deg', 90.0)),
                'dpr':     float(c.get('deg_per_rad', 57.29578)),  # 1 rad ≈ 57.3°
                'sign':    -1.0 if c.get('invert', False) else 1.0,
                'min':     float(c.get('min_deg', 0.0)),
                'max':     float(c.get('max_deg', 180.0)),
            })
        return calib

    def _rad_to_servo(self, angles: list[float]) -> list[int]:
        out: list[int] = []
        for i, a in enumerate(angles):
            c = (self._servo_calib[i] if i < len(self._servo_calib)
                 else {'neutral': 90.0, 'dpr': 57.29578, 'sign': 1.0,
                       'min': 0.0, 'max': 180.0})
            deg = c['neutral'] + c['sign'] * float(a) * c['dpr']
            deg = max(c['min'], min(c['max'], deg))            # 관절별 운용 범위 클램프
            out.append(int(round(max(0.0, min(180.0, deg)))))  # 서보 물리 한계 0~180
        return out

    def _send_servo(self, angles: list[float]) -> None:
        msg = UInt8MultiArray()
        msg.data = self._rad_to_servo(angles)
        self._servo_pub.publish(msg)

    # ── 상태 관리 ─────────────────────────────────────────────────────────
    def _set_state(self, state: ArmState) -> None:
        with self._lock:
            self._state = state

    def _publish_state(self) -> None:
        with self._lock:
            s = self._state.name
        self._pub_state.publish(String(data=s))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ArmScanNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
