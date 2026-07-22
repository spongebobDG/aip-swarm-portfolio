#!/usr/bin/env python3
"""Probe MLX90640 direct-I2C frame readiness rate.

This is meant for the Vision Pi after the GY-MCU90640 board is switched to
I2C pass-through mode, usually by tying PS to GND and wiring SDA/SCL to the
Pi I2C bus. It does not calculate temperatures; it only verifies that the
sensor is visible at 0x33 and can produce data-ready events near the requested
refresh rate.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import os
import time


I2C_M_RD = 0x0001
I2C_RDWR = 0x0707

MLX_STATUS_REG = 0x8000
MLX_CONTROL_REG = 0x800D
MLX_DATA_READY = 0x0008
MLX_REFRESH_MASK = 0x0380

RATE_LABELS = {
    0: "0.5Hz",
    1: "1Hz",
    2: "2Hz",
    3: "4Hz",
    4: "8Hz",
    5: "16Hz",
    6: "32Hz",
    7: "64Hz",
}


class I2CMsg(ctypes.Structure):
    _fields_ = [
        ("addr", ctypes.c_uint16),
        ("flags", ctypes.c_uint16),
        ("len", ctypes.c_uint16),
        ("buf", ctypes.POINTER(ctypes.c_uint8)),
    ]


class I2CRdwrIoctlData(ctypes.Structure):
    _fields_ = [
        ("msgs", ctypes.POINTER(I2CMsg)),
        ("nmsgs", ctypes.c_uint32),
    ]


class I2CBus:
    def __init__(self, bus: int, addr: int):
        self.path = f"/dev/i2c-{bus}"
        self.addr = int(addr)
        self.fd = os.open(self.path, os.O_RDWR)

    def close(self) -> None:
        os.close(self.fd)

    def _rdwr(self, messages: list[tuple[int, bytes | bytearray]]) -> None:
        msg_objs = []
        buffers = []
        for flags, data in messages:
            if isinstance(data, bytes):
                buf = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
            else:
                buf = (ctypes.c_uint8 * len(data)).from_buffer(data)
            buffers.append(buf)
            msg_objs.append(I2CMsg(self.addr, flags, len(data), buf))
        msg_array = (I2CMsg * len(msg_objs))(*msg_objs)
        ioctl_data = I2CRdwrIoctlData(msg_array, len(msg_objs))
        fcntl.ioctl(self.fd, I2C_RDWR, ioctl_data)

    def read_word(self, register: int) -> int:
        reg = bytes([(register >> 8) & 0xFF, register & 0xFF])
        out = bytearray(2)
        self._rdwr([(0, reg), (I2C_M_RD, out)])
        return (out[0] << 8) | out[1]

    def write_word(self, register: int, value: int) -> None:
        data = bytes([
            (register >> 8) & 0xFF,
            register & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ])
        self._rdwr([(0, data)])


def rate_from_control(control: int) -> int:
    return (control & MLX_REFRESH_MASK) >> 7


def set_refresh_rate(bus: I2CBus, rate_code: int) -> tuple[int, int]:
    before = bus.read_word(MLX_CONTROL_REG)
    after = (before & ~MLX_REFRESH_MASK) | ((rate_code & 0x7) << 7)
    if after != before:
        bus.write_word(MLX_CONTROL_REG, after)
        time.sleep(0.05)
    return before, bus.read_word(MLX_CONTROL_REG)


def clear_data_ready(bus: I2CBus) -> None:
    status = bus.read_word(MLX_STATUS_REG)
    bus.write_word(MLX_STATUS_REG, status & ~MLX_DATA_READY)


def count_ready_events(bus: I2CBus, duration: float, poll_sec: float) -> tuple[int, int, int]:
    count = 0
    polls = 0
    last_status = 0
    start = time.monotonic()
    while time.monotonic() - start < duration:
        status = bus.read_word(MLX_STATUS_REG)
        polls += 1
        last_status = status
        if status & MLX_DATA_READY:
            count += 1
            bus.write_word(MLX_STATUS_REG, status & ~MLX_DATA_READY)
        time.sleep(poll_sec)
    return count, polls, last_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bus", type=int, default=1, help="Linux I2C bus number, e.g. 1 for /dev/i2c-1.")
    parser.add_argument("--addr", type=lambda value: int(value, 0), default=0x33, help="MLX90640 I2C address.")
    parser.add_argument("--duration", type=float, default=15.0, help="Seconds to count data-ready events.")
    parser.add_argument("--poll-sec", type=float, default=0.002, help="Status register polling interval.")
    parser.add_argument("--rate-code", type=int, default=4, choices=range(0, 8), help="MLX refresh-rate code. 4 is 8Hz.")
    parser.add_argument("--no-set-rate", action="store_true", help="Do not write the MLX refresh-rate bits.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bus = I2CBus(args.bus, args.addr)
    try:
        try:
            status = bus.read_word(MLX_STATUS_REG)
        except OSError as exc:
            if exc.errno in (errno.EREMOTEIO, errno.ENXIO, errno.EIO):
                print(
                    f"MLX90640 not detected at /dev/i2c-{args.bus} "
                    f"addr=0x{args.addr:02x}: {exc}"
                )
                print(
                    "Check that the GY-MCU90640 board is in I2C pass-through "
                    "mode, PS is tied to GND, and SDA/SCL are wired to the Pi."
                )
                return 3
            raise
        control_before = bus.read_word(MLX_CONTROL_REG)
        control_after = control_before
        if not args.no_set_rate:
            control_before, control_after = set_refresh_rate(bus, args.rate_code)
            clear_data_ready(bus)

        events, polls, last_status = count_ready_events(bus, args.duration, args.poll_sec)
        fps = events / args.duration if args.duration > 0 else 0.0

        before_rate = rate_from_control(control_before)
        after_rate = rate_from_control(control_after)
        print(f"device=/dev/i2c-{args.bus} addr=0x{args.addr:02x}")
        print(f"initial_status=0x{status:04x} last_status=0x{last_status:04x}")
        print(f"control_before=0x{control_before:04x} rate={before_rate}({RATE_LABELS.get(before_rate, '?')})")
        print(f"control_after=0x{control_after:04x} rate={after_rate}({RATE_LABELS.get(after_rate, '?')})")
        print(f"events={events} polls={polls} duration={args.duration:.2f}s fps={fps:.2f}")
        return 0 if events > 0 else 2
    finally:
        bus.close()


if __name__ == "__main__":
    raise SystemExit(main())
