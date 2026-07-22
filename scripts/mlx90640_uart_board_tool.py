#!/usr/bin/env python3
"""Configure and verify a GY-MCU90640 UART board.

The Vision Pi normally reads the board's ZZ 02 06 binary stream. This tool is
for bench bring-up when trying to move the board from the safe 115200 baud
mode to a higher-baud 8 Hz mode.

Important: many GY-MCU90640 firmware builds apply saved baud/rate settings
only after the module MCU is power-cycled. Rebooting Linux may not remove
power from a GPIO-powered board.
"""

from __future__ import annotations

import argparse
import json
import struct
import time


try:
    import serial
except Exception as exc:  # pragma: no cover - depends on target Pi packages.
    serial = None
    _SERIAL_IMPORT_ERROR = exc
else:
    _SERIAL_IMPORT_ERROR = None


FRAME_W = 32
FRAME_H = 24
FRAME_VALUES = FRAME_W * FRAME_H
ZZ_HEADER = b"ZZ\x02\x06"
ZZ_FRAME_LEN = len(ZZ_HEADER) + FRAME_VALUES * 2

COMMANDS = {
    "emissivity": bytes.fromhex("A5 55 01 FB"),
    "baud_9600": bytes.fromhex("A5 15 01 BB"),
    "baud_115200": bytes.fromhex("A5 15 02 BC"),
    "baud_460800": bytes.fromhex("A5 15 03 BD"),
    "rate_0_5hz": bytes.fromhex("A5 25 00 CA"),
    "rate_1hz": bytes.fromhex("A5 25 01 CB"),
    "rate_2hz": bytes.fromhex("A5 25 02 CC"),
    "rate_4hz": bytes.fromhex("A5 25 03 CD"),
    "rate_8hz": bytes.fromhex("A5 25 04 CE"),
    "manual": bytes.fromhex("A5 35 01 DB"),
    "auto": bytes.fromhex("A5 35 02 DC"),
    "save": bytes.fromhex("A5 65 01 0B"),
}

DEFAULT_SCAN_BAUDS = [
    9600,
    19200,
    38400,
    57600,
    115200,
    230400,
    250000,
    256000,
    460800,
    500000,
    921600,
    1000000,
]


def require_serial() -> None:
    if serial is None:
        raise SystemExit(f"pyserial is required: {_SERIAL_IMPORT_ERROR!r}")


def write_commands(port: str, baud: int, names: list[str], delay: float = 0.25) -> dict:
    require_serial()
    rec = {
        "port": port,
        "baud": baud,
        "commands": names,
        "ok": True,
        "error": None,
        "rx_len": 0,
        "rx_hex": "",
    }
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=0.04, write_timeout=1.0)
        time.sleep(0.08)
        try:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
        except Exception:
            pass
        rx = bytearray()
        for name in names:
            ser.write(COMMANDS[name])
            ser.flush()
            time.sleep(delay)
            waiting = ser.in_waiting
            if waiting:
                rx.extend(ser.read(min(waiting, 2048)))
        time.sleep(0.1)
        waiting = ser.in_waiting
        if waiting:
            rx.extend(ser.read(min(waiting, 2048)))
        ser.close()
        rec["rx_len"] = len(rx)
        rec["rx_hex"] = bytes(rx[:96]).hex(" ")
    except Exception as exc:
        rec["ok"] = False
        rec["error"] = repr(exc)
    return rec


def _plausible_temps(payload: bytes) -> tuple[bool, dict | None]:
    try:
        vals = struct.unpack("<768H", payload)
    except Exception:
        return False, None
    temps = [v * 0.01 for v in vals if v < 20000]
    if len(temps) < FRAME_VALUES * 0.95:
        return False, None
    mn = min(temps)
    mx = max(temps)
    mean = sum(temps) / len(temps)
    ok = -80.0 <= mn <= 250.0 and -60.0 <= mx <= 500.0 and (mx - mn) <= 400.0
    return ok, {"min_c": round(mn, 2), "max_c": round(mx, 2), "mean_c": round(mean, 2)}


def measure(port: str, baud: int, duration: float, send_auto: bool = False) -> dict:
    require_serial()
    rec = {
        "port": port,
        "baud": baud,
        "duration_sec": duration,
        "frames": 0,
        "plausible_frames": 0,
        "fps": 0.0,
        "plausible_fps": 0.0,
        "bytes": 0,
        "sample_hex": "",
        "temps": None,
        "error": None,
    }
    buf = bytearray()
    sample = bytearray()
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=0.02, write_timeout=1.0)
        time.sleep(0.08)
        try:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
        except Exception:
            pass
        if send_auto:
            ser.write(COMMANDS["auto"])
            ser.flush()
            time.sleep(0.2)
        start = time.monotonic()
        while time.monotonic() - start < duration:
            waiting = ser.in_waiting
            chunk = ser.read(max(waiting, 1))
            if chunk:
                rec["bytes"] += len(chunk)
                if len(sample) < 96:
                    sample.extend(chunk[: 96 - len(sample)])
                buf.extend(chunk)
            while True:
                idx = buf.find(ZZ_HEADER)
                if idx < 0:
                    if len(buf) > len(ZZ_HEADER) - 1:
                        del buf[: -(len(ZZ_HEADER) - 1)]
                    break
                if len(buf) - idx < ZZ_FRAME_LEN:
                    if idx > 0:
                        del buf[:idx]
                    break
                payload = bytes(buf[idx + len(ZZ_HEADER) : idx + ZZ_FRAME_LEN])
                del buf[: idx + ZZ_FRAME_LEN]
                rec["frames"] += 1
                ok, temps = _plausible_temps(payload)
                if ok:
                    rec["plausible_frames"] += 1
                    if rec["temps"] is None:
                        rec["temps"] = temps
            time.sleep(0.001)
        ser.close()
    except Exception as exc:
        rec["error"] = repr(exc)
    rec["fps"] = round(rec["frames"] / duration, 3) if duration else 0.0
    rec["plausible_fps"] = round(rec["plausible_frames"] / duration, 3) if duration else 0.0
    rec["sample_hex"] = bytes(sample).hex(" ")
    return rec


def scan(port: str, bauds: list[int], duration: float, send_auto: bool, stop_on_ready: bool = False) -> dict:
    results = []
    for baud in bauds:
        rec = measure(port, baud, duration, send_auto=send_auto)
        results.append(rec)
        if stop_on_ready and baud >= 460800 and rec.get("plausible_fps", 0.0) >= 6.5:
            break
    best = max(results, key=lambda item: item.get("plausible_fps", 0.0), default=None)
    ok = bool(best and best.get("baud") == 460800 and best.get("plausible_fps", 0.0) >= 6.5)
    return {"results": results, "best": best, "uart_8fps_ready": ok}


def stage_high(args: argparse.Namespace) -> dict:
    steps = []
    steps.append({"step": "manual_safe", "result": write_commands(args.port, args.baud, ["manual"])})
    # Match known public setup first, then request high baud and save.
    steps.append(
        {
            "step": "rate8_baud460_auto_save",
            "result": write_commands(
                args.port,
                args.baud,
                ["rate_8hz", "baud_460800", "auto", "save"],
                delay=args.delay,
            ),
        }
    )
    return {
        "mode": "stage-high",
        "steps": steps,
        "next": (
            "Power-cycle the GY-MCU90640 board MCU completely, then run "
            "`scan --send-auto`. A Linux reboot may not power-cycle the board."
        ),
    }


def restore_safe(args: argparse.Namespace) -> dict:
    steps = []
    for baud in args.restore_bauds:
        steps.append(
            {
                "baud": baud,
                "result": write_commands(args.port, baud, ["baud_115200"], delay=args.delay),
            }
        )
    steps.append(
        {
            "baud": 115200,
            "result": write_commands(
                args.port,
                115200,
                ["rate_4hz", "auto", "save"],
                delay=args.delay,
            ),
        }
    )
    steps.append({"baud": 115200, "result": measure(args.port, 115200, args.duration)})
    return {"mode": "restore-safe", "steps": steps}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/serial0")
    sub = parser.add_subparsers(dest="command", required=True)

    p_measure = sub.add_parser("measure", help="Measure ZZ frame rate at one baud.")
    p_measure.add_argument("--baud", type=int, default=115200)
    p_measure.add_argument("--duration", type=float, default=5.0)
    p_measure.add_argument("--send-auto", action="store_true")

    p_scan = sub.add_parser("scan", help="Scan common baud rates for valid ZZ frames.")
    p_scan.add_argument("--bauds", type=int, nargs="+", default=DEFAULT_SCAN_BAUDS)
    p_scan.add_argument("--duration", type=float, default=3.0)
    p_scan.add_argument("--send-auto", action="store_true")
    p_scan.add_argument("--stop-on-ready", action="store_true")

    p_stage = sub.add_parser("stage-high", help="Save 8Hz/460800 settings before a physical power-cycle.")
    p_stage.add_argument("--baud", type=int, default=115200)
    p_stage.add_argument("--delay", type=float, default=0.3)

    p_restore = sub.add_parser("restore-safe", help="Restore 115200/4Hz/auto output.")
    p_restore.add_argument("--duration", type=float, default=5.0)
    p_restore.add_argument("--delay", type=float, default=0.25)
    p_restore.add_argument(
        "--restore-bauds",
        type=int,
        nargs="+",
        default=[460800, 500000, 921600, 1000000, 230400, 115200],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "measure":
        out = measure(args.port, args.baud, args.duration, send_auto=args.send_auto)
    elif args.command == "scan":
        out = scan(args.port, args.bauds, args.duration, send_auto=args.send_auto, stop_on_ready=args.stop_on_ready)
    elif args.command == "stage-high":
        out = stage_high(args)
    elif args.command == "restore-safe":
        out = restore_safe(args)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
