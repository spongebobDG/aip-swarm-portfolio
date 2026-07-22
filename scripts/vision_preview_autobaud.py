#!/usr/bin/env python3
"""Launch aip_vision.web_preview after detecting the MLX UART baud.

Use this wrapper on the Vision Pi with the same arguments as
`python3 -m aip_vision.web_preview`, but pass `--thermal-baud auto`.
It probes the GY-MCU90640 UART board at high baud first and then falls back
to the safe 115200 baud before exec'ing the real preview server.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


DEFAULT_BAUDS = [460800, 500000, 230400, 115200]


def _arg_value(argv: list[str], name: str, default: str | None = None) -> str | None:
    if name not in argv:
        return default
    idx = argv.index(name)
    if idx + 1 >= len(argv):
        return default
    return argv[idx + 1]


def _replace_arg(argv: list[str], name: str, value: str) -> list[str]:
    out = list(argv)
    if name in out:
        idx = out.index(name)
        if idx + 1 < len(out):
            out[idx + 1] = value
            return out
    out.extend([name, value])
    return out


def detect_baud(port: str, bauds: list[int], duration: float) -> tuple[int, dict]:
    tool = Path(__file__).with_name("mlx90640_uart_board_tool.py")
    cmd = [
        sys.executable,
        str(tool),
        "--port",
        port,
        "scan",
        "--bauds",
        *[str(baud) for baud in bauds],
        "--duration",
        str(duration),
        "--send-auto",
        "--stop-on-ready",
    ]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=max(8.0, duration * len(bauds) + 5.0))
        data = json.loads(proc.stdout)
    except Exception as exc:
        return 115200, {"error": repr(exc), "cmd": cmd}

    best = data.get("best") or {}
    baud = int(best.get("baud") or 115200)
    fps = float(best.get("plausible_fps") or 0.0)
    if fps <= 0:
        baud = 115200
    return baud, data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--autobaud-scan-sec", type=float, default=2.5)
    parser.add_argument("--autobaud-baud", type=int, action="append")
    known, rest = parser.parse_known_args(argv)

    thermal_baud = _arg_value(rest, "--thermal-baud", "115200")
    if str(thermal_baud).lower() not in ("auto", "detect"):
        cmd = [sys.executable, "-m", "aip_vision.web_preview", *rest]
        os.execv(sys.executable, cmd)

    port = _arg_value(rest, "--thermal-port", "/dev/serial0") or "/dev/serial0"
    scan_bauds = known.autobaud_baud or DEFAULT_BAUDS
    baud, evidence = detect_baud(port, scan_bauds, known.autobaud_scan_sec)
    sys.stderr.write(
        "vision_preview_autobaud: selected thermal baud "
        f"{baud}; evidence={json.dumps(evidence.get('best') or evidence, sort_keys=True)}\n"
    )
    sys.stderr.flush()
    next_args = _replace_arg(rest, "--thermal-baud", str(baud))
    cmd = [sys.executable, "-m", "aip_vision.web_preview", *next_args]
    os.execv(sys.executable, cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
