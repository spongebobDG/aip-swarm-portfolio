---
name: project_fleet_network
description: "플릿 네트워크 — 공유기 ipTIME AX3000Q(듀얼밴드 Wi-Fi6), 현재 2.4GHz(SSID aip2.4GHz), 5GHz는 별도 SSID. DDS=Discovery Server"
metadata: 
  node_type: memory
  type: project
  originSessionId: 731ef982-9656-4ae1-b294-0960d1f0b260
---

플릿 네트워크 인프라 (2026-06-28):

- **공유기: ipTIME AX3000Q** (Wi-Fi6 AX3000 듀얼밴드). 관리자 `192.168.0.1`.
- **현재 2.4GHz** 사용 (SSID `aip2.4GHz`). **5GHz는 별도 SSID로 서비스 중**(수동 설정 필요).
- 서브넷 `192.168.0.0/24`: 중앙 PC `.10`, aip1 `.3`, aip2 `.4`, aip3 `.5`.
- **wifi MAC / 연결방식 (DHCP 예약·5GHz 전환용, 2026-06-29 수집)**:
  - 중앙 PC `wlp4s0` MAC `e0:d4:64:26:d1:80` → `.10`, **NetworkManager**(nmcli로 전환).
  - aip1 `wlan0` MAC `d8:3a:dd:f0:00:1b` → `.3`, **netplan**(50-cloud-init+99-static).
  - aip2 `wlan0` MAC `2c:cf:67:47:36:e6` → `.4`, **netplan**(50-cloud-init).
  - aip3 `wlan0` MAC `d8:3a:dd:ef:93:06` → `.5`, **netplan**(50-cloud-init).
  - 중앙은 유선 아닌 wifi → 5GHz 전환 시 같이 이동. 차량 3대는 netplan yaml에 5GHz SSID 추가(2.4 fallback 유지)→`netplan apply`.

**DDS = Discovery Server (2026-06-28 재도입)** — [[project_dds_simple_unified]] 의 SIMPLE에서 전환:
- 중앙 PC가 **DS 서버**(`fast-discovery-server -i 0 -l 192.168.0.10 -p 11811`, fastdds-ds.service). 중앙·차량 전부 **SUPER_CLIENT**(`ROS_DISCOVERY_SERVER=192.168.0.10:11811`).
- 차량은 **wifi 전용 interfaceWhiteList 프로파일**(docker0 172.17 오염 차단) — 템플릿 `deploy/vehicle/fastdds_ds_wifi.xml.template`. RemoteServer prefix=`44.53.00.5f.45.50.52.4f.53.49.4d.41`(server id 0).
- 이유: SIMPLE 멀티캐스트 discovery가 3대 풀스택(70+ participant)에서 wifi airtime 포화 → discovery 매칭 실패(aip1 scan)·heartbeat 불안정·SSH 마비. DS=유니캐스트 discovery로 해소.

**남은 부분 = 데이터 대역폭**: DS는 discovery만 고침. scan/costmap 데이터 스트림은 여전히 2.4GHz 포화 → **5GHz 전환(IP 유지 위해 같은 서브넷+MAC DHCP 예약)** + scan throttle 필요. 5GHz가 별도 SSID라 같은 LAN 브리지 확인 필수.

**5GHz 전환 진행 (2026-06-29)** — 별도 SSID `aip5GHz`(ch36, 80MHz, WPA2, 비밀번호 값은 저장소에서 제거). ipTIME은 MAC 예약이 밴드무관이라 IP 유지(.10/.3/.4/.5). 차량 전환=netplan `aip2.4GHz→aip5GHz` 치환+`netplan apply`(detached 180s 자동롤백 watchdog로 안전). 차량은 `iwgetid` 없고 **`wpa_cli -i wlan0 status`** 로 SSID/freq/state 확인.
- **중앙 PC: 5GHz** (wlp4s0, 1134Mbit, −33dBm) ✓
- **aip1: 5GHz** (ch36 −33dBm 안정) ✓ — 고정IP(99-static .3)
- **aip2: 5GHz 전환 완료** (2026-06-29) — 진짜 원인은 **netplan YAML의 password가 해시 PSK**(`d9af…`, SSID aip2.4GHz 기준 계산값)였음. SSID마다 PSK 다름 + 해시는 SAE 비호환 → aip5GHz에서 **틀린 키로 association 실패**(`status_code=16`). **올바른 평문 PSK(값은 저장소에서 제거)로 수정 → 즉시 5GHz 결합**(.4 −31dBm). 영구화=cloud-init net 비활성. **regulatory·CLM·HW·SW버전 전부 배제**(에이전트 바이트 비교, **aip1 SD가 aip2 본체에서 5GHz 정상**으로 HW 확정). 잔여: 컨테이너 가동 시 DDS 트래픽이 업링크 포화(287ms, 컨테이너 정지 시 2~8ms) = 데이터대역폭 과제. 교훈: 생성된 `wpa-wlan0.conf`를 aip1과 diff했으면 즉시 보였음.
- **aip3: 5GHz 전환 완료** (2026-06-29) — password 평문이라 SSID만 aip5GHz로 변경 → 결합(.5 −38dBm 1.7ms). cloud-init 비활성 영구화. use_nav2=false로 가벼워 컨테이너 가동 중에도 저지연(aip2식 포화 없음). **→ 전 차량 5GHz 완료.**
- **DDS = 단일 중앙 DS 유지 확정 (5GHz에서 정상)**: 2.4에서 깨졌던 aip2 Nav2 내부(intra-vehicle) discovery가 5GHz 저지연으로 정상화(aip2 Nav2 가동, 중앙 wlan0 RX 1.24MB/s 데이터 도달) → **SIMPLE 복원 불필요**. 잔여(선택): aip2 TX 2.5MB/s(ros_topic_bridge 재발행) throttle — 5GHz가 감당하므로 비긴급.
- **혼합밴드 정상**: 2.4·5GHz 같은 서브넷 브리지 → 교차밴드 통신 검증됨(중앙5GHz↔차량2.4 ping 0%). DDS 무관.
- 차량 netplan은 root 600 + 무비번 sudo 불가 → 편집 시 sudo 비번 필요(사용자에게 요청, 평문 저장 금지).
