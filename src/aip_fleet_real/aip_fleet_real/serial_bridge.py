"""ESP32 ↔ RPi4B 시리얼 브릿지 노드.

프로토콜 (firmware/main_agv/README.md):
  패킷: AA 55 [type] [payload...] [XOR_cks]
  XOR: type ⊕ payload[0] ⊕ ... ⊕ payload[N-1]

  0x01 CMD_VEL   RPi→ESP32  <ff 8B  linear_m/s · angular_rad/s
  0x02 MOTOR_FB  ESP32→RPi  <ll 8B  enc_L · enc_R (20 Hz 누적 틱)
  0x03 SERVO     RPi→ESP32  4×uint8 서보 각도 0–180
  0x04 SERVO_FB  ESP32→RPi  4×uint8 현재 서보 각도
  0x05 STATUS    ESP32→RPi  <IHHHH 12B  업타임·플래그·bad_pkts·loop_hz·heap_kb
  0x06 SERVO_RELEASE RPi→ESP32  1B mode
  0x07 RESET     RPi→ESP32  1B mode=0
  0x08 BEEP      RPi→ESP32  1B pattern

발행:
  /<ns>/odom          nav_msgs/Odometry  (20 Hz)
  /<ns>/enc_ticks     std_msgs/Int32MultiArray  (20 Hz)
  TF: odom → base_footprint  (동적, 20 Hz)

구독:
  /<ns>/cmd_vel          → 0x01 CMD_VEL 전송
  /<ns>/servo_cmd        → 0x03 SERVO 전송
  /<ns>/esp32_reset      → 0x07 RESET 전송
  /<ns>/esp32_beep       → 0x08 BEEP 전송
"""
from __future__ import annotations

import math
import struct
import threading
import time

import rclpy
from geometry_msgs.msg import TransformStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from std_msgs.msg import Empty, Int32MultiArray, UInt8MultiArray
from tf2_ros import TransformBroadcaster

_PREAMBLE = bytes([0xAA, 0x55])

PKT_CMD_VEL        = 0x01
PKT_MOTOR_FB       = 0x02
PKT_SERVO          = 0x03
PKT_SERVO_FB       = 0x04
PKT_STATUS         = 0x05
PKT_SERVO_RELEASE  = 0x06
PKT_RESET          = 0x07
PKT_BEEP           = 0x08

PAYLOAD_LEN = {
    PKT_CMD_VEL:       8,
    PKT_MOTOR_FB:      8,
    PKT_SERVO:         4,
    PKT_SERVO_FB:      4,
    PKT_STATUS:       12,
    PKT_SERVO_RELEASE: 1,
    PKT_RESET:         1,
    PKT_BEEP:          1,
}

_RELIABLE = QoSProfile(
    reliability=QoSReliabilityPolicy.RELIABLE,
    history=QoSHistoryPolicy.KEEP_LAST,
    depth=10,
)


def _xor_cks(pkt_type: int, payload: bytes) -> int:
    cks = pkt_type
    for b in payload:
        cks ^= b
    return cks & 0xFF


def _make_packet(pkt_type: int, payload: bytes) -> bytes:
    return _PREAMBLE + bytes([pkt_type]) + payload + bytes([_xor_cks(pkt_type, payload)])


def _yaw_to_quat(theta: float):
    return (0.0, 0.0, math.sin(theta / 2.0), math.cos(theta / 2.0))


class SerialBridgeNode(Node):
    def __init__(self) -> None:
        super().__init__('aip_serial_bridge')

        self.declare_parameter('port', '/dev/aip_esp32')
        self.declare_parameter('baud', 115200)
        self.declare_parameter('vehicle_id', 'aip1')
        self.declare_parameter('wheel_base', 0.290)
        self.declare_parameter('wheel_radius', 0.060)
        self.declare_parameter('ticks_per_rev', 700)
        self.declare_parameter('odom_frame', 'odom')
        self.declare_parameter('base_frame', 'base_footprint')

        self._port  = self.get_parameter('port').get_parameter_value().string_value
        self._baud  = self.get_parameter('baud').get_parameter_value().integer_value
        self._vid   = self.get_parameter('vehicle_id').get_parameter_value().string_value
        self._wb    = self.get_parameter('wheel_base').get_parameter_value().double_value
        self._wr    = self.get_parameter('wheel_radius').get_parameter_value().double_value
        self._tpr   = self.get_parameter('ticks_per_rev').get_parameter_value().integer_value
        self._odom_frame = self.get_parameter('odom_frame').get_parameter_value().string_value
        self._base_frame = self.get_parameter('base_frame').get_parameter_value().string_value

        self._meters_per_tick = (2.0 * math.pi * self._wr) / self._tpr

        # 오도메트리 상태
        self._x = self._y = self._theta = 0.0
        self._prev_enc_L: int | None = None
        self._prev_enc_R: int | None = None
        self._lock = threading.Lock()

        # 퍼블리셔
        self._pub_odom = self.create_publisher(Odometry, 'odom', _RELIABLE)
        self._pub_ticks = self.create_publisher(Int32MultiArray, 'enc_ticks', 10)
        self._tf_bc = TransformBroadcaster(self)

        # 구독자
        self.create_subscription(Twist, 'cmd_vel', self._cb_cmd_vel, 10)
        self.create_subscription(UInt8MultiArray, 'servo_cmd', self._cb_servo, 10)
        self.create_subscription(Empty, 'esp32_reset', self._cb_reset, 10)
        self.create_subscription(UInt8MultiArray, 'esp32_beep', self._cb_beep, 10)

        # 시리얼 포트
        self._serial = None
        self._rx_buf = bytearray()
        self._open_serial()

        # 수신 스레드
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

        self.get_logger().info(
            f'serial_bridge: {self._port}@{self._baud} vid={self._vid} '
            f'wb={self._wb}m wr={self._wr}m tpr={self._tpr}'
        )

    def _open_serial(self) -> None:
        try:
            import serial  # pyserial
            self._serial = serial.Serial(self._port, self._baud, timeout=0.1)
            self.get_logger().info(f'Opened {self._port}')
        except Exception as e:  # noqa: BLE001
            self.get_logger().error(f'Cannot open serial: {e}')
            self._serial = None

    def _send(self, pkt_type: int, payload: bytes) -> None:
        if self._serial is None or not self._serial.is_open:
            return
        try:
            self._serial.write(_make_packet(pkt_type, payload))
        except Exception as e:  # noqa: BLE001
            self.get_logger().warn(f'Serial write error: {e}')

    # ── 구독 콜백 ─────────────────────────────────────────────────────────────

    def _cb_cmd_vel(self, msg: Twist) -> None:
        payload = struct.pack('<ff', msg.linear.x, msg.angular.z)
        self._send(PKT_CMD_VEL, payload)

    def _cb_servo(self, msg: UInt8MultiArray) -> None:
        angles = list(msg.data)[:4]
        angles += [90] * (4 - len(angles))
        self._send(PKT_SERVO, bytes(angles))

    def _cb_reset(self, _: Empty) -> None:
        self._send(PKT_RESET, bytes([0]))

    def _cb_beep(self, msg: UInt8MultiArray) -> None:
        pattern = msg.data[0] if msg.data else 0
        self._send(PKT_BEEP, bytes([pattern]))

    # ── 수신 루프 (별도 스레드) ───────────────────────────────────────────────

    def _rx_loop(self) -> None:
        while rclpy.ok():
            if self._serial is None or not self._serial.is_open:
                time.sleep(1.0)
                self._open_serial()
                continue
            try:
                chunk = self._serial.read(64)
            except Exception as e:  # noqa: BLE001
                self.get_logger().warn(f'Serial read error: {e}')
                time.sleep(0.5)
                continue
            self._rx_buf.extend(chunk)
            self._parse_rx()

    def _parse_rx(self) -> None:
        buf = self._rx_buf
        while len(buf) >= 4:
            # 프리앰블 탐색
            if buf[0] != 0xAA or buf[1] != 0x55:
                del buf[0]
                continue
            pkt_type = buf[2]
            payload_len = PAYLOAD_LEN.get(pkt_type)
            if payload_len is None:
                del buf[0]
                continue
            total = 3 + payload_len + 1  # AA 55 type payload cks
            if len(buf) < total:
                break
            payload = bytes(buf[3:3 + payload_len])
            cks_rx = buf[3 + payload_len]
            cks_exp = _xor_cks(pkt_type, payload)
            del buf[:total]
            if cks_rx != cks_exp:
                self.get_logger().debug(f'Bad checksum pkt=0x{pkt_type:02x}')
                continue
            self._handle_packet(pkt_type, payload)

    def _handle_packet(self, pkt_type: int, payload: bytes) -> None:
        if pkt_type == PKT_MOTOR_FB:
            enc_L, enc_R = struct.unpack('<ll', payload)
            self._update_odom(enc_L, enc_R)
        elif pkt_type == PKT_STATUS:
            uptime, flags, bad_pkts, loop_hz, heap_kb = struct.unpack('<IHHHH', payload)
            self.get_logger().debug(
                f'ESP32 status: uptime={uptime}s flags=0x{flags:04x} '
                f'loop={loop_hz}Hz heap={heap_kb}KB bad={bad_pkts}'
            )

    # ── 오도메트리 계산 ────────────────────────────────────────────────────────

    def _update_odom(self, enc_L: int, enc_R: int) -> None:
        with self._lock:
            if self._prev_enc_L is None:
                self._prev_enc_L = enc_L
                self._prev_enc_R = enc_R
                return

            d_L = (enc_L - self._prev_enc_L) * self._meters_per_tick
            d_R = (enc_R - self._prev_enc_R) * self._meters_per_tick
            self._prev_enc_L = enc_L
            self._prev_enc_R = enc_R

            d   = (d_L + d_R) / 2.0
            dth = (d_R - d_L) / self._wb

            self._x     += d * math.cos(self._theta + dth / 2.0)
            self._y     += d * math.sin(self._theta + dth / 2.0)
            self._theta += dth
            x, y, th = self._x, self._y, self._theta

        now = self.get_clock().now().to_msg()
        qx, qy, qz, qw = _yaw_to_quat(th)

        # Odometry
        odom = Odometry()
        odom.header.stamp = now
        odom.header.frame_id = self._odom_frame
        odom.child_frame_id = self._base_frame
        odom.pose.pose.position.x = x
        odom.pose.pose.position.y = y
        odom.pose.pose.orientation.x = qx
        odom.pose.pose.orientation.y = qy
        odom.pose.pose.orientation.z = qz
        odom.pose.pose.orientation.w = qw
        self._pub_odom.publish(odom)

        # TF: odom → base_footprint
        tf = TransformStamped()
        tf.header.stamp = now
        tf.header.frame_id = self._odom_frame
        tf.child_frame_id = self._base_frame
        tf.transform.translation.x = x
        tf.transform.translation.y = y
        tf.transform.rotation.x = qx
        tf.transform.rotation.y = qy
        tf.transform.rotation.z = qz
        tf.transform.rotation.w = qw
        self._tf_bc.sendTransform(tf)

        # enc_ticks
        ticks = Int32MultiArray()
        ticks.data = [enc_L, enc_R]
        self._pub_ticks.publish(ticks)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SerialBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
