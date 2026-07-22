"""thermal_driver_node.py — MLX90640 열화상 센서 드라이버 (Pi 4 실행).

센서에서 32×24 온도 배열을 읽어 두 토픽으로 발행:
  /{vehicle_id}/thermal_raw   sensor_msgs/Image (32FC1, °C)
  /{vehicle_id}/thermal_temp  std_msgs/Float32  (프레임 최고온도 °C)

하드웨어 요구사항:
  pip3 install adafruit-circuitpython-mlx90640
  I2C 활성화: /boot/config.txt → dtparam=i2c_arm=on,i2c_arm_baudrate=400000

시뮬레이션 모드 (sim:=true):
  실제 센서 없이 랜덤 온도 배열 발행 → 개발/테스트용
"""
from __future__ import annotations

import random

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Float32

THERMAL_COLS = 32
THERMAL_ROWS = 24


class ThermalDriverNode(Node):
    def __init__(self) -> None:
        super().__init__('thermal_driver')

        self.declare_parameter('vehicle_id',    'peer_1')
        self.declare_parameter('publish_hz',    8.0)
        self.declare_parameter('sim',           False)
        self.declare_parameter('i2c_bus',       1)

        vid        = self.get_parameter('vehicle_id').value
        hz         = self.get_parameter('publish_hz').value
        self._sim  = self.get_parameter('sim').value
        i2c_bus    = self.get_parameter('i2c_bus').value

        self._mlx = None
        if not self._sim:
            self._mlx = self._init_sensor(i2c_bus)

        self._pub_raw  = self.create_publisher(Image,   f'/{vid}/thermal_raw',  10)
        self._pub_temp = self.create_publisher(Float32, f'/{vid}/thermal_temp', 10)
        self.create_timer(1.0 / hz, self._read_and_publish)
        self.get_logger().info(f'thermal_driver ready  vehicle={vid}  sim={self._sim}')

    def _init_sensor(self, bus: int):
        try:
            import board
            import busio
            import adafruit_mlx90640
            i2c = busio.I2C(board.SCL, board.SDA, frequency=400_000)
            mlx = adafruit_mlx90640.MLX90640(i2c)
            mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_8_HZ
            self.get_logger().info('MLX90640 initialised on I2C')
            return mlx
        except Exception as e:
            self.get_logger().error(f'MLX90640 init failed: {e}')
            return None

    def _read_and_publish(self) -> None:
        frame = [0.0] * (THERMAL_COLS * THERMAL_ROWS)

        if self._sim:
            # 시뮬: 배경 25°C + 임의 열점 1개
            frame = [25.0 + random.gauss(0, 0.5) for _ in frame]
            hot_idx = random.randint(0, len(frame) - 1)
            frame[hot_idx] = random.uniform(30.0, 90.0)
        elif self._mlx is not None:
            try:
                self._mlx.getFrame(frame)
            except Exception as e:
                self.get_logger().warn(f'sensor read error: {e}')
                return

        arr = np.array(frame, dtype=np.float32).reshape(THERMAL_ROWS, THERMAL_COLS)

        img_msg = Image()
        img_msg.header.stamp    = self.get_clock().now().to_msg()
        img_msg.header.frame_id = 'thermal_frame'
        img_msg.height    = THERMAL_ROWS
        img_msg.width     = THERMAL_COLS
        img_msg.encoding  = '32FC1'
        img_msg.step      = THERMAL_COLS * 4
        img_msg.data      = arr.tobytes()
        self._pub_raw.publish(img_msg)

        temp_msg = Float32(data=float(arr.max()))
        self._pub_temp.publish(temp_msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ThermalDriverNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
