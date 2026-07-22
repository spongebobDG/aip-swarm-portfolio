# wifi 워치독 — 설치 안내

플릿(aip1/2/3)은 **wpa_supplicant**(NetworkManager 아님, wlan0, ssid `aip5GHz`, GW 192.168.0.1)
기반이다. wpa_supplicant 도 자동재연결을 시도하지만 **power_save 드롭·supplicant 스택·
드라이버 행** 같은 '연결됐다 착각하지만 죽은' 상태는 스스로 못 빠져나온다(공유기 가까이 둬도
복구 안 됨). 이 워치독이 45초 주기로 게이트웨이 도달을 확인하고 단계적으로 강제 복구한다.

자율 주행은 wifi 가 제어루프 안에 있으므로(중앙 Nav2) 이 워치독은 안전 마진에 직접 기여한다.

## 설치 (각 차량에서, 루트 권한 필요)

```bash
# deploy/vehicle/ 의 파일을 차량으로 복사한 뒤:
sudo cp wifi_watchdog.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/wifi_watchdog.sh
sudo cp wifi-watchdog.service wifi-watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wifi-watchdog.timer
```

## 확인 / 동작

```bash
systemctl status wifi-watchdog.timer
journalctl -t wifi-watchdog -f      # 복구 로그 실시간
```

복구 단계: ① power_save off → ② `wpa_cli reassociate` → ③ wlan0 down/up + `wpa_cli reconfigure`
→ ④ wpa_supplicant 재시작 + dhclient. 각 단계 후 GW 재확인, 복구되면 종료.

## 주의
- 인터페이스/GW 가 다르면 `wifi-watchdog.service` 의 `Environment=WIFI_IFACE/WIFI_GW` 주석 해제.
- 드라이버 자체가 행(hang)이면 소프트 복구로 안 되고 재부팅이 필요할 수 있음 — 로그에 "물리 점검 필요" 출력.
