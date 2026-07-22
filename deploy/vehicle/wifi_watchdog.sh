#!/bin/bash
# AIP wifi 워치독 — 게이트웨이 도달 실패 시 wlan0 단계적 재연결.
# 플릿은 wpa_supplicant(NetworkManager 아님) 기반. wpa_supplicant 자체도 자동재연결을
# 시도하지만 power_save 드롭·supplicant 스택·DHCP 멈춤 등 '연결됐다 생각하지만 죽은' 상태는
# 스스로 못 빠져나온다. 이 스크립트가 systemd timer 로 주기 실행되며 강제 복구한다.
# 루트 권한 필요(ip/iw/wpa_cli/systemctl/dhclient). 설치: deploy README 참조.
set -u
GW=${WIFI_GW:-192.168.0.1}
IFACE=${WIFI_IFACE:-wlan0}
log() { logger -t wifi-watchdog "$*"; }

# power_save 는 RPi4 brcmfmac 드롭의 흔한 원인 → 매 실행 off 강제(멱등).
iw dev "$IFACE" set power_save off 2>/dev/null || true

# 1) 게이트웨이 3회 시도 — 한 번이라도 되면 정상.
for _ in 1 2 3; do
  ping -c1 -W2 "$GW" >/dev/null 2>&1 && exit 0
  sleep 2
done
log "GW $GW 무응답 → $IFACE 재연결 (1단계: reassociate)"

# 2) 가벼운 재결합.
wpa_cli -i "$IFACE" reassociate >/dev/null 2>&1 || true
sleep 6
ping -c1 -W2 "$GW" >/dev/null 2>&1 && { log "reassociate 복구"; exit 0; }

# 3) 인터페이스 down/up + wpa reconfigure + DHCP 갱신.
log "2단계: $IFACE down/up + reconfigure"
ip link set "$IFACE" down 2>/dev/null; sleep 2; ip link set "$IFACE" up 2>/dev/null; sleep 2
wpa_cli -i "$IFACE" reconfigure >/dev/null 2>&1 || true
sleep 6
ping -c1 -W2 "$GW" >/dev/null 2>&1 && { log "down/up 복구"; exit 0; }

# 4) 최후: wpa_supplicant 재시작 + DHCP.
log "3단계: wpa_supplicant 재시작 + dhclient"
systemctl restart wpa_supplicant 2>/dev/null || true
sleep 4
dhclient -1 "$IFACE" 2>/dev/null || true
sleep 4
if ping -c1 -W2 "$GW" >/dev/null 2>&1; then
  log "wpa 재시작 복구"
else
  log "복구 실패 — 물리 점검/재부팅 필요(드라이버 행 가능성)"
fi
exit 0
