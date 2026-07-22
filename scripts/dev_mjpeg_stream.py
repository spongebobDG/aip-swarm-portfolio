#!/usr/bin/env python3
"""Tiny dependency-free multipart image stream for dashboard vision testing.

This is only a local development stand-in for a Vision Pi stream. On the real
Pi, replace it with uStreamer, MediaMTX, go2rtc, or another camera streamer.
"""
from __future__ import annotations

import argparse
import math
import struct
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _svg_frame(width: int, height: int, tick: int) -> bytes:
    cx = int((math.sin(tick * 0.11) * 0.35 + 0.5) * width)
    cy = int((math.cos(tick * 0.09) * 0.35 + 0.5) * height)
    hue = (tick * 9) % 360
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="hsl({hue},72%,35%)"/>
      <stop offset="100%" stop-color="hsl({(hue + 95) % 360},72%,48%)"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#g)"/>
  <g stroke="rgba(255,255,255,.35)" stroke-width="1">
    <path d="M0 {height // 2} H{width}"/>
    <path d="M{width // 2} 0 V{height}"/>
  </g>
  <circle cx="{cx}" cy="{cy}" r="34" fill="rgba(255,255,255,.82)"/>
  <rect x="{max(0, cx - 70)}" y="{max(0, cy - 10)}" width="140" height="20" rx="4" fill="rgba(15,23,42,.85)"/>
  <text x="{cx}" y="{cy + 5}" fill="white" font-family="Arial, sans-serif" font-size="15" text-anchor="middle">AIP VISION {tick:04d}</text>
</svg>'''.encode('utf-8')


def _bmp_frame(width: int, height: int, tick: int) -> bytes:
    row_stride = (width * 3 + 3) & ~3
    pixels = bytearray(row_stride * height)
    cx = int((math.sin(tick * 0.11) * 0.35 + 0.5) * width)
    cy = int((math.cos(tick * 0.09) * 0.35 + 0.5) * height)

    for y in range(height):
        for x in range(width):
            dx = abs(x - cx)
            dy = abs(y - cy)
            band = 255 if dx < 18 or dy < 12 else 0
            r = (30 + x * 180 // max(1, width - 1) + band) & 0xFF
            g = (70 + y * 150 // max(1, height - 1)) & 0xFF
            b = (160 + tick * 5 + (x + y) // 8) & 0xFF
            offset = (height - 1 - y) * row_stride + x * 3
            pixels[offset:offset + 3] = bytes((b, g, r))

    size = 54 + len(pixels)
    header = (
        b'BM'
        + struct.pack('<IHHI', size, 0, 0, 54)
        + struct.pack('<IiiHHIIiiII', 40, width, height, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)
    )
    return header + pixels


class Handler(BaseHTTPRequestHandler):
    width = 480
    height = 270
    fps = 8.0

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ('/', '/index.html'):
            stream_url = f'http://{self.server.server_address[0]}:{self.server.server_address[1]}/stream.mjpg'
            body = f'''<!doctype html>
<html><head><meta charset="utf-8"><title>AIP Vision Test Stream</title></head>
<body style="margin:0;background:#111;color:#eee;font:14px sans-serif">
<div style="padding:10px">AIP dev stream: <code>{stream_url}</code></div>
<img src="/stream.mjpg" style="width:100vw;max-height:85vh;object-fit:contain">
</body></html>'''.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path.startswith('/snapshot.bmp'):
            frame = _bmp_frame(self.width, self.height, int(time.time() * self.fps))
            self.send_response(200)
            self.send_header('Content-Type', 'image/bmp')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)
            return

        if not self.path.startswith('/stream.mjpg'):
            self.send_error(404)
            return

        boundary = 'aipvision'
        delay = 1.0 / max(1.0, self.fps)
        self.send_response(200)
        self.send_header('Content-Type', f'multipart/x-mixed-replace; boundary={boundary}')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.end_headers()

        tick = 0
        try:
            while True:
                frame = _svg_frame(self.width, self.height, tick)
                self.wfile.write(f'--{boundary}\r\n'.encode('ascii'))
                self.wfile.write(b'Content-Type: image/svg+xml\r\n')
                self.wfile.write(f'Content-Length: {len(frame)}\r\n\r\n'.encode('ascii'))
                self.wfile.write(frame)
                self.wfile.write(b'\r\n')
                self.wfile.flush()
                tick += 1
                time.sleep(delay)
        except (BrokenPipeError, ConnectionResetError):
            return


def main() -> None:
    parser = argparse.ArgumentParser(description='Serve a local AIP test image stream.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8091)
    parser.add_argument('--width', type=int, default=480)
    parser.add_argument('--height', type=int, default=270)
    parser.add_argument('--fps', type=float, default=8.0)
    args = parser.parse_args()

    Handler.width = args.width
    Handler.height = args.height
    Handler.fps = args.fps
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'AIP dev stream: http://{args.host}:{args.port}/stream.mjpg')
    print('Stop with Ctrl+C')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
