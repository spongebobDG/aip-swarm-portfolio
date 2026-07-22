"""thermal_uart_driver_node.py — GY-MCU90640 UART 열화상 드라이버 (Pi 4 실행).

핀 8/10(GPIO14 TXD / GPIO15 RXD) UART 에 연결된 GY-MCU90640 보드의
`ZZ 02 06` 바이너리 스트림을 읽어 I2C 드라이버(thermal_driver_node)와 **동일한
토픽 계약**으로 발행 → patrol_monitor_node / central_fusion_node 무수정 동작:
  /{vehicle_id}/thermal_raw   sensor_msgs/Image (32FC1, °C)
  /{vehicle_id}/thermal_temp  std_msgs/Float32  (프레임 최고온도 °C)

프레임 형식 (scripts/mlx90640_uart_board_tool.py 와 동일):
  헤더 ZZ 02 06 + 768 × uint16(little-endian), temp_c = v * 0.01.

하드웨어 요구사항:
  pip3 install pyserial
  UART 활성: /boot/firmware/config.txt → enable_uart=1, 시리얼 콘솔 비활성화
  포트 기본 /dev/serial0 (= 핀 8/10). aip1 은 disable-bt 미적용 → ttyS0(mini-UART).

시뮬레이션 모드 (sim:=true): 센서 없이 랜덤 온도 배열 발행.
"""
from __future__ import annotations

import struct
import threading

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Float32

THERMAL_COLS = 32
THERMAL_ROWS = 24
FRAME_VALUES = THERMAL_COLS * THERMAL_ROWS          # 768
ZZ_HEADER = b"ZZ\x02\x06"
ZZ_FRAME_LEN = len(ZZ_HEADER) + FRAME_VALUES * 2    # 4 + 1536 = 1540
_CMD_AUTO = bytes.fromhex("A5 35 02 DC")            # 보드 auto 출력 명령


class ThermalUartDriverNode(Node):
    def __init__(self) -> None:
        super().__init__('thermal_uart_driver')

        self.declare_parameter('vehicle_id', 'aip1')
        self.declare_parameter('port',       '/dev/serial0')
        self.declare_parameter('baud',       460800)   # GY-MCU90640 보드 460800/8Hz (PR#9·실측 확인). 115200은 4배 불일치 쓰레기
        self.declare_parameter('send_auto',  True)    # 시작 시 auto 출력 요청
        self.declare_parameter('sim',        False)

        vid              = self.get_parameter('vehicle_id').value
        self._port       = self.get_parameter('port').value
        self._baud       = int(self.get_parameter('baud').value)
        self._send_auto  = bool(self.get_parameter('send_auto').value)
        self._sim        = bool(self.get_parameter('sim').value)
        self._frame_id   = f'{vid}/arm/thermal_optical_frame'

        self._pub_raw  = self.create_publisher(Image,   f'/{vid}/thermal_raw',  10)
        self._pub_temp = self.create_publisher(Float32, f'/{vid}/thermal_temp', 10)

        if self._sim:
            self.create_timer(0.125, self._publish_sim)   # 8Hz
            self.get_logger().info(f'thermal_uart_driver SIM  vehicle={vid}')
            return

        self._ser = self._open_serial()
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()
        self.get_logger().info(
            f'thermal_uart_driver ready  vehicle={vid}  {self._port}@{self._baud}')

    def _open_serial(self):
        import serial
        ser = serial.Serial(self._port, self._baud, timeout=0.05)
        if self._send_auto:
            try:
                ser.reset_input_buffer()
                ser.write(_CMD_AUTO)
                ser.flush()
            except Exception as exc:  # noqa: BLE001
                self.get_logger().warn(f'auto 명령 전송 실패: {exc}')
        return ser

    def _rx_loop(self) -> None:
        buf = bytearray()
        while rclpy.ok():
            try:
                # 블로킹 읽기: 프레임 크기만큼 요청 → 데이터 없으면 OS가 스레드를 sleep(busy-wait 제거).
                # timeout(0.05s) 시 받은 만큼 반환, 부분 프레임은 buf 에 누적·정렬됨.
                chunk = self._ser.read(ZZ_FRAME_LEN)
            except Exception as exc:  # noqa: BLE001
                self.get_logger().warn(f'serial read error: {exc}')
                continue
            if chunk:
                buf.extend(chunk)
            # 버퍼에 든 완성 프레임 모두 drain (mlx90640_uart_board_tool 와 동일 로직)
            while True:
                idx = buf.find(ZZ_HEADER)
                if idx < 0:
                    if len(buf) > len(ZZ_HEADER) - 1:
                        del buf[:-(len(ZZ_HEADER) - 1)]
                    break
                if len(buf) - idx < ZZ_FRAME_LEN:
                    if idx > 0:
                        del buf[:idx]
                    break
                payload = bytes(buf[idx + len(ZZ_HEADER): idx + ZZ_FRAME_LEN])
                del buf[: idx + ZZ_FRAME_LEN]
                self._handle_frame(payload)

    def _handle_frame(self, payload: bytes) -> None:
        try:
            vals = struct.unpack('<768H', payload)
        except struct.error:
            return
        arr = np.asarray(vals, dtype=np.float32).reshape(THERMAL_ROWS, THERMAL_COLS) * 0.01
        # 데드픽셀: 비정상(>200°C 또는 비유한) → 유효값 median (PR #9 thermal_uart 동일)
        bad = ~np.isfinite(arr) | (arr > 200.0)
        if np.any(bad):
            good = arr[~bad]
            arr[bad] = float(np.median(good)) if good.size else 25.0
        # 이미지셋 방향: rotate 180(rot90×2) + flip_y(flipud) — PR #9 기본
        arr = np.flipud(np.rot90(arr, 2)).copy()
        valid = arr[(arr > -80.0) & (arr < 500.0)]
        if valid.size < FRAME_VALUES * 0.5:      # 깨진 프레임 폐기
            return
        self._publish(arr, float(valid.max()))

    def _publish(self, arr: np.ndarray, max_c: float) -> None:
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self._frame_id
        msg.height = THERMAL_ROWS
        msg.width = THERMAL_COLS
        msg.encoding = '32FC1'
        msg.is_bigendian = 0
        msg.step = THERMAL_COLS * 4
        msg.data = arr.astype(np.float32).tobytes()
        self._pub_raw.publish(msg)
        self._pub_temp.publish(Float32(data=max_c))

    def _publish_sim(self) -> None:
        arr = np.random.rand(THERMAL_ROWS, THERMAL_COLS).astype(np.float32) * 10.0 + 25.0
        self._publish(arr, float(arr.max()))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ThermalUartDriverNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
