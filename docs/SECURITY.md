# AIP Swarm — Security Findings

전체 스택 보안 감사 결과. **36건** 발견 (기존 인지 2건 포함).
이 문서는 발견 사항 catalog이며, **대응 단계(Phase)는 문서 하단** 참조.

현재 워크스페이스에서 **즉시 조치된 항목**은 각 Finding 하단에 `Status: mitigated (YYYY-MM-DD)` 로 표기. 나머지는 `Status: deferred`.

감사 기준일: 2026-04-20.

---

## 위협 모델 요약

| 위협 행위자 | 접근 경로 | 권한 |
|---|---|---|
| 외부 공격자 (인터넷) | 라우터 포워딩 없음 → 직접 접근 불가 | 없음 |
| **Wi-Fi 침투자** (AIP_FLEET 접속 성공) | WPA2-PSK 크래킹 또는 내부자 유출 | **DDS 전 토픽 publish/subscribe** |
| 내부 악성 노드 (합법 참여자) | 정상 DDS 조인 | **/fleet/override, /*/estop 전권** |
| 물리 접근자 (차량 탈취) | ESP32 USB/UART | NVS 재설정, 펌웨어 덤프, PSK 추출 |
| 감염된 중앙 PC 컨테이너 | 이미지 공급망 또는 RCE | 호스트 네트워크 루트 |

신뢰 경계: 현재 **암묵적으로 WiFi 내부 = 신뢰 영역**. 방어 레이어 사실상 0.

---

## Critical (6)

### C1. `/fleet/override` 미인증·미서명
- **위치**: `src/aip_fleet_supervisor/aip_fleet_supervisor/supervisor_node.py:108`, `src/aip_fleet_supervisor/aip_fleet_supervisor/watchdog_node.py:68`
- **공격**: DDS 도메인 참여자면 누구나 `OverrideCommand(vehicle_id="*", CMD_ESTOP)` 발행 → 전 차량 즉시 정지
- **완화**: SROS2 AccessControl 정책으로 `/fleet/override` publish를 특정 노드로 제한 + 메시지 서명
- **Status**: deferred (Phase 1)

### C2. FastDDS Discovery Server 미인증 개방
- **위치**: `config/fastdds_discovery_server.xml`, `docker/central/docker-compose.yml:24-33`
- **공격**: AIP_FLEET Wi-Fi 접속자는 UDP `192.168.0.9:11811` DS에 자유 조인 → 전 토픽 열거
- **완화**: FastDDS Security (AuthenticationPlugin + CryptoPlugin) + X.509 인증서
- **Status**: deferred (Phase 1)

### C3. micro-ROS Agent UDP 0.0.0.0 바인드·레이트리밋 없음
- **위치**: `docker/central/docker-compose.yml:43`
- **공격**: `CREATE_SESSION` 플러드 → 세션 테이블 고갈, 정상 스카우트 재접속 차단
- **완화**: agent를 `192.168.0.9` 바인드, 호스트 방화벽 룰(`iptables -m recent`)
- **Status**: deferred (Phase 1)

### C4. Foxglove Bridge 0.0.0.0:8765 평문 + 무인증
- **위치**: `src/aip_fleet_bringup/launch/central.launch.py:68`, `docker/central/docker-compose.yml:50-61`
- **공격**: 동일 서브넷 임의 호스트가 `ws://...:8765` 접속 → OverridePanel로 ESTOP, 전 토픽 스니핑
- **완화**: TLS(wss) + client cert 인증, address `192.168.0.9`로 제한
- **Status**: deferred (Phase 1)

### C5. 하트비트 사칭
- **위치**: `src/aip_fleet_supervisor/aip_fleet_supervisor/supervisor_node.py:62`, `src/aip_fleet_sim/aip_fleet_sim/sim_vehicle_node.py`
- **공격**: 악성 노드가 `vehicle_id="main"` heartbeat 발행 → 실제 메인 AGV 오프라인인데 watchdog 미발동
- **완화**: HMAC/PSK 서명 필드 추가 또는 SROS2 Participant 인증
- **Status**: deferred (Phase 1)

### C6. Watchdog 2초 단일 miss 자동 ESTOP (가짜 오프라인 DoS)
- **위치**: `src/aip_fleet_supervisor/aip_fleet_supervisor/watchdog_node.py:49`
- **공격**: UDP 정크로 scout 프로세스 hang 유도 → 2초 내 watchdog가 전차량 정지. **정상 운영 중 Wi-Fi 지터만으로도 오작동**
- **완화**: 연속 N회 오프라인 확인 후 ESTOP (히스테리시스)
- **Status**: **mitigated (2026-04-20)** — `OFFLINE_CONFIRM_COUNT=3` 도입, `watchdog_node.py` 참고

---

## High (10)

### H1. Replay 방어 부재
`stamp` 필드 미검증. 포착된 `OverrideCommand` 무기한 재생 가능.
- **위치**: `supervisor_node.py:115`, Foxglove 패널 publish
- **완화**: monotonic sequence + skew 윈도우 검증
- **Status**: deferred

### H2. Wi-Fi PSK "change-me" 소스 커밋
- **위치**: `firmware/scout_microros/platformio.ini:24` (이전 상태)
- **완화**: 빌드 플래그를 `secrets.ini` (gitignore) 로 분리, 예시는 `secrets.ini.example`
- **Status**: **mitigated (2026-04-20)**

### H3. InfluxDB 자격증명·토큰 커밋
- **위치**: `docker/central/docker-compose.yml:100-105` (이전 상태)
- **완화**: `docker/central/.env` 파일로 분리 + gitignore, 예시 `.env.example` 제공
- **Status**: **mitigated (2026-04-20)**

### H4. 공급망 미고정 (펌웨어/컨테이너/npm)
- `platformio.ini:20` `micro_ros_platformio#humble` (브랜치)
- `Dockerfile.central:1` `ros:humble-ros-base` (태그)
- `package.json` `^` 캐럿 범위
- **완화**: git commit hash, image digest, `package-lock.json`
- **Status**: deferred (Phase 1)

### H5. 컨테이너 이미지 digest 미고정
- **위치**: `docker/central/docker-compose.yml` 모든 `image:` 라인
- **완화**: `image: foo@sha256:...`
- **Status**: **mitigated (2026-04-23)** — `ros:humble-ros-base`, `microros/micro-ros-agent:humble`, `influxdb:2.7` digest 고정 완료. `foxglove-bridge`는 컨테이너 이미지 배포 중단 → apt(`ros-humble-foxglove-bridge`) 호스트 설치로 전환, digest pinning 대상 해소.

### H6. 컨테이너 root 실행
- **위치**: `docker/central/Dockerfile.central` (USER 없음), `docker-compose.yml` (user 지시자 없음)
- **완화**: non-root user, `cap_drop: [ALL]`, read-only volume
- **Status**: **partially mitigated (2026-04-23)** — `cap_drop: [ALL]` 전 서비스 적용. `uros-agent` `user: "65534:65534"` 적용. `foxglove-bridge`는 컨테이너 제거 → apt 호스트 노드로 전환(컨테이너 공격면 자체 해소). `rosbag-recorder`는 인-컨테이너 apt-get 때문에 root 유지(TODO: custom image 이전 시 해결).

### H7. rosbag 평문 저장
- **위치**: `docker/central/docker-compose.yml:67-87`
- **공격**: `/rosbags` 접근 시 과거 override 명령·위치·scan 복원 가능
- **완화**: LUKS/dm-crypt 볼륨, 또는 `/fleet/override` 제외 토픽 리스트
- **Status**: deferred (Phase 2)

### H8. ESP32 시리얼 `set_ns` 입력 미검증
- **위치**: `firmware/scout_microros/src/main.cpp:79-98`
- **공격**: 물리 접근자가 1000자 namespace 입력 → NVS 경계 훼손
- **완화**: 길이/포맷 검증(`^[a-z][a-z0-9_]{0,31}$`), challenge-response
- **Status**: **mitigated (2026-04-23)** — `ns_valid()` 함수로 길이(1~31)·첫 문자(소문자)·허용 문자(a-z0-9_) 검증. 불통과 시 에러 메시지만 출력하고 NVS 기록 거부.

### H9. ROS_DOMAIN_ID=42 단일 하드코딩
- **위치**: `platformio.ini:27`, `docker-compose.yml:14`, `Dockerfile.central`
- **공격**: 같은 서브넷 두 플릿 간 교차 오버라이드
- **완화**: 환경변수화 + per-fleet 할당 가이드
- **Status**: **mitigated (2026-04-23)** — `docker-compose.yml`: `${ROS_DOMAIN_ID:-42}` 환경변수 참조. `Dockerfile.central`: `ARG ROS_DOMAIN_ID=42` 빌드 인자 추가. `.env.example`: 항목 추가 및 안내 주석. `platformio.ini`: per-fleet 변경 가이드 주석 추가.

### H10. Wildcard `"*"` 미확인·레이트리밋 없음
- **위치**: `src/aip_fleet_foxglove_panels/OverridePanel/src/OverridePanel.tsx` (이전 상태)
- **공격**: 운영자 오클릭 한 번으로 전 차량 정지
- **완화**: `"*"` 선택 시 confirm() + 연속 publish debounce
- **Status**: **mitigated (2026-04-20)**

---

## Medium (9)

| # | Finding | 위치 | Status |
|---|---------|------|--------|
| M1 | DDS SHM 전송 평문 노출 | `fastdds_*.xml` | deferred |
| M2 | SROS2 ACL 부재 — 전 토픽 자유 구독 | 전체 | deferred (Phase 1) |
| M3 | npm lock 파일 없음 | `aip_fleet_foxglove_panels/` | deferred |
| M4 | YAML 스키마 검증 없음 | `sim_world_node.py:40`, `sim_lidar_node.py:44` | **mitigated (2026-04-23)** — `_validate_world_yaml()` / `_validate_vehicles_yaml()` 추가. 필수 키·타입·양수 범위 검증. 불통과 시 명확한 ValueError로 fail-fast. |
| M5 | 패널 입력 프론트 전용 검증 | `OverridePanel.tsx:71-92` | **mitigated (기존)** — `sim_vehicle_node.py:88-89`에서 `max(-v_max, min(v_max, ...))` 서버 측 클램핑 이미 구현. |
| M6 | 감사 로그 persistent 아님 (docker logs 삭제 가능) | 전체 | deferred (Phase 3) |
| M7 | WPA2-PSK 오프라인 크랙 가능 | `config/network/dhcp_reservations.md` | deferred (Phase 3) |
| M8 | 토픽 publish 레이트리밋 없음 | 전체 | deferred |
| M9 | launch 인자 경로 검증 없음 (`world_yaml:=/etc/passwd`) | `fleet_sim.launch.py:36-50` | deferred |

---

## Low (9)

| # | Finding | 위치 | Status |
|---|---------|------|--------|
| L1 | ESP32 secure_boot/flash_encryption off | `platformio.ini` | deferred (Phase 3) |
| L2 | OTA 갱신 메커니즘 없음 | `main.cpp` | deferred (Phase 3) |
| L3 | micro-ROS UDP 평문 | `main.cpp:115`, agent | deferred (Phase 1 커버) |
| L4 | Foxglove WS 평문 | `central.launch.py:68` | deferred (Phase 1 커버) |
| L5 | watchdog 1s 주기 재발행 — 로그/대역폭 낭비 | `watchdog_node.py` | deferred |
| L6 | supervisor 차량 리스트 코드 하드코딩 | `supervisor_node.py:22` | deferred |
| L7 | 볼륨 ro 미지정 | `docker-compose.yml:56-57` | deferred |
| L8 | 패널 버튼 debounce 없음 | `EStopPanel.tsx` | deferred |
| L9 | compose `depends_on`·graceful shutdown 없음 | `docker-compose.yml` | deferred |

---

## 대응 단계 (Phase Roadmap)

### Phase 1 — 프로덕션 전 필수 (DDS 레이어 하드닝)
1. **SROS2 도입** — C1/C2/C5/H1/M2/L3/L4 한 번에 해결
   - `config/security/` keystore 생성
   - `launch` 에서 `SROS2_SECURITY_ROOT_DIRECTORY` 주입
2. **바인드 주소 제한** — C3/C4
   - `docker-compose.yml` agent 명령: `udp4 --port 8888 --bind 192.168.0.9`
   - Foxglove bridge launch arg: `address:=192.168.0.9`
3. **공급망 고정** — H4/H5
   - `platformio.ini` `lib_deps` 에 commit hash 표기
   - `docker-compose.yml` `image: ros:humble-ros-base@sha256:...`
   - `package.json` → `package-lock.json` 커밋

### Phase 2 — 운영 경험치 후
- H6 container non-root
- H7 rosbag 볼륨 암호화
- H8 serial 입력 검증
- H9 ROS_DOMAIN_ID 환경변수화
- M4/M5 YAML + 패널 입력 스키마 검증

### Phase 3 — 장기 하드닝
- WPA2-Enterprise(802.1X) + 차량별 인증서 (M7)
- ESP32 secure_boot + flash_encryption (L1)
- 외부 syslog 감사 로그 (M6)
- 서명된 OTA (L2)

---

## 현재 완화된 항목 요약 (2026-04-20)

| ID | 파일 변경 |
|----|-----------|
| C6 | `src/aip_fleet_supervisor/aip_fleet_supervisor/watchdog_node.py` — `OFFLINE_CONFIRM_COUNT=3` 히스테리시스 |
| H2 | `firmware/scout_microros/platformio.ini` — `WIFI_PASS` 제거, `secrets.ini` (gitignored) 로 분리 |
| H3 | `docker/central/docker-compose.yml` — InfluxDB 자격증명을 `${VAR}` 형태로 전환, `docker/central/.env` 사용 |
| H10 | `src/aip_fleet_foxglove_panels/OverridePanel/src/OverridePanel.tsx` — `"*"` 선택 시 `window.confirm` 다이얼로그 + debounce |
| — | `.gitignore` 신규 — `secrets.ini`, `.env` 등 기밀 파일 포함 |
