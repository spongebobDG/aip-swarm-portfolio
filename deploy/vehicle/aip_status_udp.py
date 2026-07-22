#!/usr/bin/env python3
"""차량 경량 상태 리포터 → 중앙 대시보드 UDP 오버레이.

순수 UDP + psutil (ROS 의존성 없음, colcon 빌드 불필요). 기본 1 Hz.
대상: 중앙 PC(AIP_CENTRAL_HOST)의 AIP_UDP_STATUS_PORT(기본 19052).
대시보드 dashboard_server._on_udp_status 가 cpu/battery 를 카드에 병합한다.

배포: deploy/vehicle/README.md 참조. (aip1·aip2·aip3 공통, env 로 차량별 분리)

설계 메모:
- battery: 배터리 센서 없는 차량(예: STS3215 자작차)은 0.0(unsupported) 고정.
- estop/mode: 본 리포터는 ROS 토픽에 접근하지 않으므로, 오인 표시 방지를 위해
  mode 만 정적값(기본 manual)으로 보낸다. 실제 estop/모드 추적은 ROS-aware
  리포터로의 확장 과제(별도 진행).
"""
from __future__ import annotations

import json
import os
import socket
import time

VEHICLE_ID = os.environ.get('AIP_VEHICLE_ID', 'aip1')
CENTRAL_HOST = os.environ.get('AIP_CENTRAL_HOST', '192.168.0.10')
# 19052: 대시보드 직접 UDP 오버레이(cpu 카드). 19051: udp_status_heartbeat_adapter
# → FleetHeartbeat 재발행 → supervisor online 인식(watchdog 의 offline estop 방지).
STATUS_PORT = int(os.environ.get('AIP_UDP_STATUS_PORT', '19052'))
ADAPTER_PORT = int(os.environ.get('AIP_UDP_ADAPTER_PORT', '19051'))
HZ = float(os.environ.get('AIP_STATUS_HZ', '1.0'))

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - psutil 미설치 폴백
    psutil = None

NPROC = os.cpu_count() or 1


_PREV_STAT = None  # (idle_all, total) — /proc/stat 델타용 누적값


def _proc_stat_cpu():
    """/proc/stat 첫 줄 델타로 CPU 사용률(0–1)을 직접 계산.

    loadavg(런큐 길이 = 실행+D-state I/O 대기 포함, 1분 지수평균)는 I/O 바운드
    워크로드(serial+wifi 브리지)에서 실제 CPU 사용률의 ~2배로 부풀려진다. 대신
    호출 간격(=리포트 주기) 동안의 비유휴 jiffy 비율을 계산하면 htop/top 의
    '100-idle' 와 일치한다. 첫 호출은 기준점만 잡고 None 반환."""
    global _PREV_STAT
    try:
        with open('/proc/stat') as f:
            # cpu  user nice system idle iowait irq softirq steal guest guest_nice
            vals = [int(x) for x in f.readline().split()[1:]]
    except Exception:
        return None
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)   # idle + iowait = 비유휴에서 제외
    total = sum(vals)
    prev = _PREV_STAT
    _PREV_STAT = (idle, total)
    if prev is None:
        return None
    dt = total - prev[1]
    di = idle - prev[0]
    if dt <= 0:
        return None
    return max(0.0, min(1.0, 1.0 - di / dt))


def cpu_load() -> float:
    """CPU 사용률 0.0–1.0. psutil 우선 → /proc/stat 델타 폴백(loadavg 아님) → loadavg 최후."""
    if psutil is not None:
        try:
            return max(0.0, min(1.0, psutil.cpu_percent(interval=None) / 100.0))
        except Exception:
            pass
    v = _proc_stat_cpu()
    if v is not None:
        return v
    try:   # /proc/stat 조차 못 읽을 때만 (loadavg 는 과대평가라 최후수단)
        return max(0.0, min(1.0, os.getloadavg()[0] / NPROC))
    except Exception:
        return 0.0


def main() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if psutil is not None:
        try:
            psutil.cpu_percent(interval=None)  # prime: 첫 호출은 0 반환
        except Exception:
            pass
    else:
        _proc_stat_cpu()  # prime: /proc/stat 델타 기준점
    period = 1.0 / HZ if HZ > 0 else 1.0
    # 같은 페이로드를 대시보드(19052)와 어댑터(19051) 양쪽으로 송신.
    dests = [(CENTRAL_HOST, STATUS_PORT)]
    if ADAPTER_PORT > 0 and ADAPTER_PORT != STATUS_PORT:
        dests.append((CENTRAL_HOST, ADAPTER_PORT))
    while True:
        payload = {
            'vehicle_id': VEHICLE_ID,
            'cpu_load': round(cpu_load(), 3),
            'battery_percentage': 0.0,   # 배터리 센서 없음(unsupported)
            'battery_voltage': 0.0,
            'mode': os.environ.get('AIP_VEHICLE_MODE', 'manual'),  # 정적값; 실모드는 ROS-aware 확장 과제
            'healthy': True,
            'status': 'ok',
        }
        data = json.dumps(payload).encode('utf-8')
        for dest in dests:
            try:
                sock.sendto(data, dest)
            except OSError:
                pass
        time.sleep(period)


if __name__ == '__main__':
    main()
