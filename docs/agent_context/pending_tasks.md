# Pending Tasks — Prioritized Roadmap

현재 상태 기준: **2026-06-29** (5GHz 밴드 전환 + aip2 5GHz 근본원인 진단; Vision Pi 직접 RGB/MLX 웹관제 연동 PR #6 병합 — 세션 24; 이전: 2026-06-28 DS 재도입).
모든 항목은 `docs/ANALYSIS.md` 또는 `docs/SECURITY.md` 의 finding ID 로 추적.

---

## 📌 2026-06-29 상태 (5GHz 밴드 전환 — 혼합밴드)

- ✅ **중앙·aip1 = 5GHz** (ch36 80MHz, ipTIME AX3000Q SSID `aip5GHz`). 중앙 1134Mbit, aip1 −33dBm 안정. netplan SSID 치환 + detached watchdog 180s 자동롤백 방식, 차량은 `wpa_cli -i wlan0 status`로 탐지(iwgetid 없음).
- ✅ **aip2 = 5GHz 전환 완료** (2026-06-29) — 진짜 원인 = **netplan password가 해시 PSK**(`d9af…`, SSID aip2.4GHz 기준값; SSID 종속+SAE 비호환). **올바른 평문 PSK(값은 저장소에서 제거)로 수정 → 5GHz 결합**(.4 −31dBm), cloud-init net 비활성으로 영구화. regulatory/CLM/HW/SW버전 전부 배제(에이전트 바이트 비교 + **aip1 SD가 aip2 본체서 5GHz 정상**=HW확정). 잔여=컨테이너 DDS 트래픽 업링크 포화(287ms, 정지 시 2~8ms)=데이터대역폭. 상세 `conversation_log.md` 2026-06-29 정정.
- ⏳ **남은 작업**:
  - ✅ **aip3 5GHz 전환 완료** (2026-06-29) — password 이미 평문이라 SSID만 aip5GHz로 변경 → 결합(.5 −38dBm 1.7ms). cloud-init 비활성 영구화. 컨테이너 가동 중에도 저지연(use_nav2=false로 가벼움 = aip2식 트래픽 포화 없음). **→ 전 차량(중앙·aip1·aip2·aip3) 5GHz 완료.**
  - ✅ **DDS = 단일 중앙 DS 유지 확정** (2026-06-29) — 2.4에서 깨졌던 aip2 Nav2 내부 discovery가 **5GHz에선 정상**(저지연 round-trip) → **SIMPLE 복원 불필요**. aip2 Nav2 가동(controller/planner/SLAM 활성) + 중앙 wlan0 RX 1.24MB/s로 차량→중앙 데이터 도달 확인.
  - **(선택·비긴급) aip2 트래픽 최적화** — TX 2.5MB/s(`ros_topic_bridge` scan/map/odom 재발행 추정) throttle하면 효율·헤드룸↑. 단 5GHz가 감당하므로(풀가동에도 7ms) 긴급 아님.
- 메모리: `project_fleet_network`(밴드·MAC·sudo 정책).

---

## 📌 2026-06-28 세션 22 상태 (DDS·대시보드 telemetry)

- ✅ **DDS cross-machine 복구**: 전체 **SIMPLE 통일** + domain42. 대시보드 aip1 scan·odom·poses 표시 성공. DS(Discovery Server) 사용 금지 — 상세 `conversation_log.md` 2026-06-28, memory `project_dds_simple_unified`.
- ✅ **aip1 online 카드 cpu telemetry**: 경량 UDP 리포터(`deploy/vehicle/aip_status_udp.py`) 배포 → 중앙 `AIP_UDP_STATUS_PORT=19052` 직접 오버레이. cpu 실값 표시, ping 경합 제거(`AIP_PING_STATUS_TARGETS=` 빈값).
- ⏳ **후속**:
  - 실 estop/mode 표시 = ROS-aware 리포터 확장(현재 mode 정적 manual). battery = 센서 추가 시.
  - ping↔실 telemetry **코드레벨 우선순위** 수정(`dashboard_server` `_on_udp_status`/`_ping_status_loop`) — 팀원 카메라퓨전 작업과 조율 후.
  - **②  aip2/aip3 SIMPLE 통일 + 리포터 배포** — 차량 전원 ON 필요(클린 재작업 시).
  - ③ `fastdds-ds` no-op(load-bearing) 정식 정리 = base 유닛 수술 필요, 유지보수 창 보류.

---

## 🎥 비전 스트리밍 — Vision Pi 직접 관제 연동

> ✅ **2026-06-29 갱신**: aip1 **온보드 카메라**는 별도 Vision Pi/MJPEG가 아니라 **camera_ros(libcamera HW-ISP)** 로 전환 완료 — camera_ros→`/aip1/arm/image_raw/compressed`→central_fusion→`/fleet/perception_viz`→대시보드 박스 A. CPU 12.5%(소프트경로 57~77%↓), 정합 오버레이/온도 심부 마커 대시보드 합성. 상세: `memory/project_vision_feed_arch.md`, conversation_log 2026-06-29.
> 남은 것: (1) **열상 노드 CPU 과다**(thermal_driver ~49% + patrol_monitor ~38%, 24×32치곤 비정상) 최적화, (2) aip2/aip3 카메라 미장착(플릿 전체 비전), (3) camera_info 캘리브레이션 yaml.
> 아래는 팀원의 **별도 Vision Pi(독립 SBC, MJPEG)** 방향 기록 — aip1 온보드와는 별개 배포.
> 최신 실측 스냅샷: `docs/VISION_PI_STATUS_2026-06-28_KO.md`.

### 완료/검증
- 대시보드 외부 RGB 스트림: `AIP_VISION_STREAM_URLS=aip2=http://192.168.0.108:8081/rgb.mjpg`
- 대시보드 외부 MLX/thermal 스트림: `AIP_THERMAL_STREAM_URLS=aip2=http://192.168.0.108:8081/thermal.mjpg`
- 리뷰/로컬 테스트용 쿼리 지원:
  - `?vision_aip2=http://192.168.0.108:8081/rgb.mjpg&thermal_aip2=http://192.168.0.108:8081/thermal.mjpg`
- Vision Pi 서비스: `aip-vision-preview.service` enabled/active.
- RGB: raw Bayer stream mode. 기존 `400x300`에서는 6 fps 설정 실측 약 `5.66 fps`, 10 fps 설정 실측 약 `7.87 fps`, 20 fps 설정 실측 약 `7.77 fps`였다.
  - Pi 로컬 코드에 raw Bayer 처리 상한 옵션 `--rgb-raw-max-fps`를 추가하고 `320x240`, `--fps 12`, `--rgb-raw-max-fps 14`로 테스트한 결과 RGB 실측 약 `10.46 fps`.
  - 현재 추천 운용값은 `320x240`, `--fps 8`, `--rgb-raw-max-fps 8`. 브라우저 MJPEG 연결 상태에서 RGB 약 `7.86 fps`, thermal 약 `3.93 fps`, Pi 전체 busy 약 `26.2%`, throttled `0x0`.
  - `oneshot` 저부하 모드는 화면 깨짐이 있어 보류.
- MLX thermal: `240x180`, 115200 UART 기준 실측 약 4.0 fps.
  - Pi 수신 코드의 UART read timeout/청크 크기를 낮춰 지연은 줄였지만 실제 frame source는 계속 약 4 fps.
  - host baud만 230400으로 올린 테스트는 프레임 수신 0건으로 실패했다. 10 fps thermal은 MLX 송신 보드 firmware/baud 변경 또는 직접 I2C 경로가 필요하다.
  - 2026-06-28 해결: `8Hz/460800/auto/save` 후 보드/PI 전원 실제 재인가를 수행하자 autobaud가 `460800`을 선택했고 web preview thermal 약 `7.8 fps` 검증 완료.
- `jdedu9807` Wi-Fi 테스트:
  - Vision Pi는 `192.168.0.7`에서 `aip-vision-preview.service` active/enabled 상태로 검증했다.
  - 주행 확인용 권장값은 `rgb.mjpg`/`thermal.mjpg` MJPEG direct stream.
  - 현장 DHCP가 바뀔 수 있으므로 Pi MAC `d8:3a:dd:eb:46:f9`를 공유기에서 고정 IP 예약하는 것이 좋다.
- PC 웹관제 정적 테스트에서 `#vision-a`와 `#vision-b`가 Pi 직접 스트림으로 렌더링됨을 확인.
- 웹 대시보드 RGB 슬롯에 `/fleet/alerts`의 `rgb_bbox_*` 결과를 오버레이한다.
  - Pi에서 YOLO/박스 그리기를 수행하지 않고, 중앙 PC가 발행한 bbox 데이터만 브라우저가 표시한다.
  - 로컬 리뷰 테스트용 `?bbox_aip2=x,y,w,h` 쿼리를 지원한다.
- 지연이 큰 경우를 위해 대시보드 직접 영상에 최신 JPEG polling 모드를 추가했다.
  - 현재 권장 fallback: RGB `300ms`, thermal `1000ms`.
  - 예: `?rgb_poll_ms=300&thermal_poll_ms=1000&vision_aip2=http://192.168.0.108:8081/rgb.jpg&thermal_aip2=http://192.168.0.108:8081/thermal.jpg`
  - MJPEG 장기 연결에서 브라우저/서버 버퍼가 쌓이는 경우, 최신 스냅샷만 다시 가져와 지연 누적을 줄인다.
- 중앙 대시보드 실행 환경변수로 팀원이 RGB/thermal을 별도 조정할 수 있다.
  - `AIP_VISION_STREAM_URLS`, `AIP_THERMAL_STREAM_URLS`
  - `AIP_RGB_POLL_MS`, `AIP_THERMAL_POLL_MS`, `AIP_VISION_POLL_MS`
  - 세부 런북: `docs/VISION_PI_DIRECT_STREAM_KO.md`
- `aip_fleet_perception`에 Vision Pi HTTP-to-ROS adapter를 추가했다.
  - `vision_pi_bridge_node`: Vision Pi `/rgb.jpg` → `/<vehicle_id>/image_raw/compressed`.
  - Vision Pi `/thermal.jpg` → `/<vehicle_id>/thermal_viz`.
  - Vision Pi `/status.json` → `/<vehicle_id>/heartbeat` 및 thermal WARN `/fleet/alerts`.
  - 실행 진입점: `ros2 launch aip_fleet_perception vision_pi_bridge.launch.py vehicle_id:=aip2 base_url:=http://192.168.0.108:8081`
- PR 브랜치: `feat/vision-pi-direct-stream`, 커밋 `3bafc99` 이후 bbox overlay 추가 진행.

### 다음
1. 중앙 대시보드 운영 실행 환경에 `AIP_VISION_STREAM_URLS`/`AIP_THERMAL_STREAM_URLS` 및 필요 시 `AIP_RGB_POLL_MS`/`AIP_THERMAL_POLL_MS` 반영.
2. Vision Pi 직접 실행을 원하면 Pi에 ROS2 Humble runtime/rclpy/aip_fleet_msgs 빌드 환경을 설치.
3. 중앙 PC 선검증을 원하면 adapter를 중앙에서 실행해 Pi HTTP → ROS2 토픽 변환을 먼저 확인.
4. 중앙 인식(`central_fusion_node.py`/YOLOv8)이 실제 Vision Pi RGB 소스와 같은 해상도 기준 bbox를 내는지 통합 시 확인.
5. 현재 추천 설정은 RGB `320x240`, `--fps 8`, `--rgb-raw-max-fps 8` + 기본 MJPEG 직접 연결이다. 지연이 느껴질 때는 JPEG polling fallback `RGB 300ms`, `thermal 1000ms`를 사용한다.
6. thermal은 현재 UART `460800bps` autobaud 상태에서 약 `7.8 fps` 검증 완료. 재부팅/보드 교체 후 문제가 생기면 `journalctl -u aip-vision-preview.service -n 30 --no-pager`에서 `selected thermal baud 460800` 여부를 확인한다.
7. Pi가 스트레스 테스트 이후 ping/SSH/8081에 응답하지 않는 상태가 되면 전원/네트워크를 직접 확인하고 재부팅 후 `aip-vision-preview.service`를 확인한다.
8. ROS2에는 카메라 상태, 탐지 결과, `/fleet/alerts`, 저율 썸네일/이벤트 프레임만 연결.

---

## 🧠 중앙 제어 AI (Fleet Brain) — `feat/fleet-brain` 브랜치 진행 중

> **SSOT 설계 문서: `docs/CENTRAL_AI.md`.**
> 확정 방향: **로컬 규칙/경량 ML · 제안만(human-in-the-loop) · 오프라인(외부망 차단)**.

### ✅ 완료 (feat/fleet-brain 브랜치, 별도 세션)
- **BRAIN-1~4**: `aip_fleet_brain` 패키지 완전 구현 (정책 4종 + 대시보드 연동 + 테스트 25개+)
- **RL 파이프라인**: 3개 환경 CPU 학습 완료 (formation 56%, coverage 80.5%, coverage_grid ~55%)
- **ONNX export/배포 코드**: 완전 구현. GPU PC에 .zip/.onnx 이미 존재
- **Tailscale 설정**: Ubuntu PC 로그인 완료 (100.125.29.37), 원격 Windows PC (100.116.223.0) 확인

### 🔴 즉시 필요 — 원격 GPU PC 접속 환경 정비 (귀가 후)
- **RDP 비밀번호 만료**: `ERRCONNECT_PASSWORD_CERTAINLY_EXPIRED` — Windows 비밀번호 변경 필요
- **OpenSSH 서버 미활성**: `설정 → 앱 → 선택적 기능 → OpenSSH 서버` 설치 후 `net start sshd`
- 정비 완료 후 SSH (`ssh <user>@100.116.223.0`) 또는 RDP로 접속해 학습 실행

### 🔴 다음 작업 (접속 복구 후 순서)
1. **feat/fleet-brain 브랜치 체크아웃 + Brain 빌드/테스트**
   ```bash
   git checkout -b feat/fleet-brain origin/feat/fleet-brain
   colcon build --packages-select aip_fleet_brain
   colcon test --packages-select aip_fleet_brain
   ```
2. **HealthMonitor 도킹 좌표 동적화**
   - `health_monitor.py`: `brain.yaml` 정적값 → `~/aip_maps/dock_positions.json` 동적 읽기
   - 도킹 좌표가 유동적이므로 대시보드 UI 저장값과 자동 동기화 필요
3. **GPU 학습 실행** (원격 Windows WSL2)
   ```bash
   python -m aip_fleet_learning.train --env coverage_grid --device cuda \
     --timesteps 10000000 --n-envs 16 --ent-coef 0.01
   ```
   목표: coverage_grid 90%+ (현재 ~55%, GPU 필요)
4. **ONNX → 중앙 PC 복사 + brain.yaml `coverage_onnx_path` 설정**
5. **E2E 검증**: `with_brain:=true` + 모의 alert → 대시보드 제안 카드 확인
6. **커밋 + main 머지**

### ⚠️ 학교망 환경 제약 (2026-06-27 확인)
- Fortinet SSL 인터셉트로 Tailscale 제어 플레인 차단 (로그인 불가)
- **해결**: 핫스팟으로 1회 로그인 후 학교망 복귀 — 데이터 터널은 유지됨 (ping 응답 확인)
- RDP/SSH는 네트워크는 되나 Windows 자격증명 문제로 미완
- **다음 세션 시작 시**: `tailscale status`로 연결 상태 먼저 확인

안전 가드레일: Brain은 차량 토픽 직접 발행 금지(제안만). 자동 ESTOP은 기존 `watchdog_node` 반사 영역으로 분리 유지.

---

## 🔴 즉시 작업 — 실차 스택 안정화 (2026-06-26 기준)

### ~~N-RPP. 전 차량 DWB → Regulated Pure Pursuit 교체 + RPP 동작 검증~~ — **완료 (2026-06-27)**

- aip1/aip2/aip3 nav2_params FollowPath 블록을 DWB에서 RPP로 교체 완료.
- 중앙 워크스페이스 레퍼런스 파일 동기화 완료.
- **aip1 NavigateToPose SUCCEEDED** — `ros2 action send_goal /aip1/navigate_to_pose` x=0.5m 목표 도달 확인 (2026-06-27)

### N-HW. aip1 ESP32 단절 · aip2 LIDAR 불량 — **하드웨어 점검 필요**

**aip1** (2026-06-27 완료):
- serial_bridge 정상 (`/dev/aip_esp32@115200`, odom 20Hz ✅)
- Nav2 ACTIVE, RPP SUCCEEDED ✅
- FastDDS 로컬 DS 추가: `aip-local-ds.service` (127.0.0.1:11812) → 36초 내 Nav2 활성화
- FastDDS 프로파일: `/home/jh/aip_ws/config/fastdds_aip1_profile.xml`
- **재부팅 자동 기동**: `@reboot /home/jh/aip_start_on_boot.sh` crontab 등록 (linger 대안 — sudo 미확보)
  - 스크립트: `sleep 30 → aip-local-ds.service start → sleep 3 → aip-fleet.service start`

**aip2** (2026-06-27 복구):
- 컨테이너 재시작 후 정상 기동: LIDAR ✅ odom ✅ SLAM ✅ Nav2 ✅
- `/aip2/scan`, `/aip2/map`, `/aip2/odom`, `/aip2/heartbeat` 모두 발행 확인
- Docker RestartPolicy: `unless-stopped`로 변경 → Docker 재시작 시 자동 복구

**현재 상태 요약** (2026-06-27 야간 최종):
| 차량 | Nav2 | SLAM | RPP | 토픽 네임스페이스 | 재부팅 자동 기동 | supervisor ONLINE |
|------|------|------|-----|------------------|---------|---------|
| aip1 | ✅ ACTIVE | ✅ | ✅ SUCCEEDED | ✅ /aip1/* (통일 완료) | ✅ crontab @reboot | 미확인(ssh 부하) |
| aip2 | ✅ | ✅ | 미검증 | ✅ /aip2/* | ✅ unless-stopped | 간헐 flapping |
| aip3 | ✅ | ✅ | 확인 필요 | ✅ /aip3/* | ✅ 조건부 빌드 패치 | 미확인(꺼짐) |

### 🔴 N-NS. aip1 네임스페이스 통일 — **완료 (2026-06-27 야간)**
- aip1 소스(`fleet_main.launch.py`, `twist_mux_main.yaml`, `slam_toolbox_aip1.yaml`): `namespace=main` → `aip1` 전부 치환.
- 중앙(`supervisor.yaml`, `dashboard_server.py`): `/main/central_cmd_vel`, `/main/scan`, `/main` legacy alias 전부 `/aip1/*`로 교체 또는 제거.
- 검증: aip1 재부팅 후 로컬 콘솔에서 `/main` 노드 0개, 전 노드 `__ns:=/aip1` 확인.
- 중앙 DS stale ghost(`/main/*` 13개)는 lease duration 만료 전 자연 소멸 예정, 기능적 무해.

### 🔴 N-BOOT. aip3 부팅 병목 — **패치 완료 (2026-06-27)**
- `docker-compose.yml` 조건부 빌드: `install/setup.bash` 캐시 히트 시 colcon build 생략.
- 검증: `skip-colcon-build:cache-hit` 로그 확인, 기동 마비 해소.
- 잔여: Nav2 동시 로딩 15초 I/O 창 (stagger 고려), combined_safety_node 58-70% CPU (ESP32 busy-poll 의심).

### 🔴 N-LOAD. bringup 부하·SSH 완화 + 운영 AMCL 모드 — **코드 반영 (2026-06-27 야간), 실차 검증 대기**

N-BOOT 잔여(Nav2+SLAM 동시 로딩 I/O 창)의 구조적 해소. SSOT: `docs/ANALYSIS.md §실차 부하…(2026-06-27)`,
운영 절차: `docs/REAL_VEHICLE_OPERATION.md §7`.

- **반영(코드, py_compile 통과)**:
  - 기동 staggering: `turtlebot3.launch.py`(aip2)·`custom_vehicle.launch.py`(aip3) `TimerAction` 추가(기존 전무).
  - `fleet_main.launch.py`(aip1): `localization:={slam|amcl|none}` + `map_yaml` 인자, amcl 그룹(map_server+amcl+lifecycle).
  - 신규 `config/main_agv/amcl.yaml`(RPi4B 부하용: 파티클 400~1500, 빔 120, odom/base_footprint 프레임).
  - `config/main_agv/twist_mux.yaml` `/main/`→`/aip1/` 정합 + central 슬롯 `central_cmd_vel`.
- **🔴 실차 검증(차량 연결 후)**:
  1. 맵 1회 제작: `fleet_main.launch.py localization:=slam` → 주행 → save_map `~/aip_maps/latest_fleet_map`.
  2. 운영: `localization:=amcl map_yaml:=~/aip_maps/latest_fleet_map.yaml` → `/map` latched·amcl 수렴·`map→odom` TF 확인.
  3. 부팅 중 SSH 유지(스파이크 해소) 체감 확인. 중앙 `AIP_NAV_ALLOWED_IDS` 설정 후 대시보드 웨이포인트/순찰.
- ✅ **keepout costmap 차단 구현(2026-06-27)**: `central.launch.py` keepout_zone_node 기동(`with_keepout` 기본 on) +
  실차 nav2.yaml 6 costmap 에 `keepout_cloud` 관측원(clearing:False·저부하). 자율 경로가 위험구역 회피.
  실차 검증: 구역 그리기→`/fleet/keepout_cloud` 발행→자율 goal 우회/거부 확인. (수동 teleop 은 미게이트 = 한계)

---

### ~~C-SNAP. snapd 비활성화~~ — **완료 (2026-06-26)**
- 전 차량(aip1/aip2/aip3) `sudo systemctl disable --now snapd` 적용 완료

### C-AMCL. aip3 AMCL 초기화 문제 — **중앙 측 자동화 완료 / 실차 검증 필요**

**코드 완료 (2026-06-25)**:
- `central_real_combined.py`: `_amcl_init_thread()` 추가 — 중앙 시작 후 `AIP_AMCL_INIT_DELAY_SEC`(기본 8s) 뒤 `/{vid}/initialpose` 자동 발행
- 활성화: `AIP_AMCL_INIT_VEHICLES=aip3` 환경변수 설정
- 포즈 지정: `AIP_AMCL_INIT_POSE_AIP3=x,y,yaw_deg` (기본 `0.0,0.0,0.0`)
- 공분산: x/y ±0.7m, yaw ±30° — AMCL이 LiDAR로 자체 수렴 가능

**실차 검증 절차**:
1. `export AIP_AMCL_INIT_VEHICLES=aip3` 설정 후 `run_central.sh` 실행
2. aip3 docker restart 후 AMCL이 자동 초기화되는지 확인
3. 포즈가 맞지 않으면 `AIP_AMCL_INIT_POSE_AIP3=x,y,yaw_deg` 조정

### ~~C0. aip1 웹 제어 최종 검증~~ — **완료 (2026-06-26)**

- `fastdds_client_profile.xml` (aip1): `CLIENT`→`SUPER_CLIENT`, IP 수정 (2026-06-25)
- `fleet_main.launch.py` with_base:=true → serial_bridge + twist_mux + LiDAR + heartbeat 전체 기동
- 노드 5개 활성: robot_state_publisher / ydlidar / twist_mux / aip_serial_bridge / heartbeat_pub
- 토픽 확인: /main/scan ✅ /main/odom ✅ /main/heartbeat ✅ /main/cmd_vel ✅
- ESP32 연결: `aip_base up on /dev/aip_esp32@115200` ✅
- 중앙 `/main/central_cmd_vel` → twist_mux → `/main/cmd_vel` end-to-end 검증 ✅
- **구동계 정상 활성화 + 제어 명령 정상 동작 사용자 확인 (2026-06-26)** ✅
- 운영 주의: fleet_main 기동 시 반드시 `with_base:=true` / estop 해제 후 조이스틱 사용

### C1. aip3 LiDAR 배치 정보 확인 후 안전거리 재보정 — **사용자 제공 대기**
- `safety_supervisor.py`의 `front_stop_distance`가 LiDAR 중심 기준
- LiDAR가 비대칭/전방 아닌 위치에 있으면 실제 차체 전방 여백이 설정값보다 좁을 수 있음
- 사용자가 배치 정보 제공 후 `front_stop_distance` 파라미터 조정

### C2. 중앙 스택 재부팅 후 자동 기동 검증 — **테스트 대기**
- `fastdds-ds.service` + `aip-central.service` systemd 등록 완료
- 실제 재부팅 후 두 서비스 자동 기동 및 포트 바인딩 확인 필요
- `systemctl --user status fastdds-ds aip-central`로 확인

---

## 🔴 다음 즉시 작업 (실차 제어)

### R-URDF. URDF arm_joint_2/3 pivot 위치 수정 — **팀원 SolidWorks 수정 대기 (2026-06-23)**
- arm_joint_2, arm_joint_3: STL mesh 원점이 링크 기하학적 중심 (±80mm 대칭) → 서보 축 위치로 SolidWorks 좌표계 재배치 필요
- arm_joint_1/4 axis 수정 완료 (세션 13), 바퀴 axis 수정 완료 (세션 13)
- 팀원 SolidWorks 재수출 후: mesh 경로 `aip_fleet_real/meshes/` 유지, check_urdf 검증 후 적용

### R6. 순찰 미션 E2E 테스트 — **대기 중 (patrol.yaml vehicle_id 수정 완료)**
- `patrol.yaml vehicle_id: main` → `aip1` 버그 수정됨 (세션 12)
- 테스트: `ros2 launch aip_fleet_real main_agv.launch.py with_patrol:=true`
- 확인: patrol_node가 `/aip1/navigate_to_pose` 액션에 정상 연결되는지

### R5. RViz 실차 확인 + 웹 대시보드 재검증 — **코드 완료 / 실차 확인 필요 (2026-06-23)**
- `src/aip_fleet_real/rviz/main_agv.rviz` 신규: aip1 실차용 (SLAM 맵 /map, costmap, TF 비네임스페이스)
- `dashboard_server.py`: TF 조회 버그 수정 (aip1 → base_link, 비네임스페이스)
- `dashboard_server.py`: 실차 환경 /map 첫 수신 시 SLAM맵 소스 자동 전환
- `index.html`: 선택 차량 E-Stop 해제 버튼 추가
- **실차 확인 절차**:
  1. `rviz2 -d ~/aip_swarm_ws/install/aip_fleet_real/share/aip_fleet_real/rviz/main_agv.rviz`
  2. LaserScan(/aip1/scan), TF(map→odom→base_footprint→base_link→laser_link), Costmap 표시 확인
  3. 웹 대시보드 재시작 후 aip1 위치 마커 맵에 표시 확인



### R-NEW. fleet_main 토픽 수신 검증 — **완료 (2026-06-23)**
- fleet_main 기동: YDLidar+serial_bridge+twist_mux+heartbeat 모두 정상 기동
- ydlidar.yaml `sample_rate: 9` → `20` 수정 완료 (TG15 실제값 20K)
- docker-compose.yml fastdds-ds IP `192.168.50.10` → `192.168.0.9` 수정 완료
- dev PC에서 토픽 수신 확인: `/aip1/heartbeat`(2Hz ✅), `/aip1/scan`(10Hz ✅), `/aip1/odom` ✅
- FastDDS Simple Discovery (ROS_DOMAIN_ID=42, rmw_fastrtps_cpp) — DS 없이도 통신 정상
- **중요**: nohup 비대화형 쉘 실행 시 `source ~/.bashrc`가 guard로 early return → 반드시 explicit source 경로 사용

### R0. main_agv.launch.py 구현 — **완료 (2026-06-22, 66d654a)**
- SLAM+Nav2(MPPI)+patrol 통합 launch 구현 (placeholder 대체)
- nav2.yaml: map_topic, 전 섹션, bond_timeout, batch_size=500 RPi4B 최적화
- slam_toolbox.yaml: YDLidar TG15 파라미터, throttle_scans=2
- patrol.yaml: 실좌표 교체 필요한 template
- scripts/deploy_main_agv.sh: SSH 원스텝 배포 + 기동 안내

### R1. motor CMD_VEL 구동 검증 — **완료 (2026-06-22)**
- `/main/autonomy_cmd_vel` → twist_mux → `/main/cmd_vel` → serial_bridge → ESP32 체인 검증
- 좌/우 enc_ticks 동기 증가 (L+99K, R+99K, 직진 틱 차 <30) ✅
- 정지 명령 후 틱 변화 없음 ✅
- **주의**: ESP32 serial write timeout 발생 시 fleet_main 재시작 필요 (serial_bridge가 쓰기 없으면 silent reconnect)

### R2. 실차 SLAM 기동 테스트 — **완료 (2026-06-22)**
- slam_toolbox (async_slam_toolbox_node) + Nav2 (DWB) 전체 활성화 확인
- global_costmap 134×250(0.05m) 로 성장 중 → 실시간 맵 생성 확인 ✅
- `odom` 타임아웃 에러 0건, `laser_link` TF 드롭 8건(초기 기동만) ✅

### R2-EXT. main_agv ESP32 부팅 비프 + RPi 소프트 리셋 명령 — **코드 완료 (2026-06-22) / 플래시 필요**
- `firmware/main_agv/buzzer.h/cpp` 신규: 비블로킹 부저 상태머신 4패턴 (BOOT/SINGLE/DOUBLE/ERROR)
- `config.h`: BUZZER_PIN=2, BUZZER_CH=8, PKT_RESET=0x07, PKT_BEEP=0x08 추가
- `aip_firmware.ino`: setup() 끝에 `Buzzer::play(BOOT)`, loop()에 `Buzzer::tick()`, onReset/onBeep 핸들러
- `serial_bridge.py` (RPi): `/main/esp32_reset`(Empty) + `/main/esp32_beep`(UInt8MultiArray) 구독 추가 — SCP 완료
- **잔여**: (1) BUZZER_PIN=2 → 실제 핀으로 `config.h` 수정, (2) Arduino IDE/PlatformIO로 ESP32 플래시, (3) RPi에서 `colcon build --packages-select aip_base` + fleet_main 재시작

### R3. ESP32 펌웨어 소스 확보 — **미완료**
- 현재 플래시된 펌웨어 동작 확인됨 (SERVO_FB, STATUS 응답 ✅)
- 소스 코드 위치 미확인 → 팀원에게 확인 필요
- `servo_test.py`의 PARK_POSE=(90,0,0,90), BOOT_POSE=(90,60,90,125) 기준

### R4. fleet AP 네트워크 확정 — **완료 (2026-06-22)**
- 결정: 서브넷 192.168.0.0/24 유지 (IPTime AX3000Q가 플릿 전용 AP)
- 소스 코드 192.168.50.x → 192.168.0.x 일괄 수정 완료
  - central PC(dev PC): 192.168.0.9, main_agv RPi: 192.168.0.3
  - Discovery Server: 192.168.0.9:11811
- 라우터 DHCP 풀 100~200 변경 ✅ (사용자 완료)
- RPi 고정 IP 192.168.0.3 적용 ✅ (netplan 99-static.yaml)
- main_agv ESP32는 serial(`/dev/aip_esp32`) 방식 → AGENT_IP 재컴파일 불필요 ✅
- **잔여 (scout ESP32만 해당)**: 소스 미확보 → R3 참조

### S1. turtlebot3_sim.launch.py 버그 수정 및 정적 검증 — **완료 (2026-06-22)**
- patrol remapping 버그 수정: `/scout_1/map` → `/map` (slam_toolbox 절대경로 발행)
- nav2_sim.yaml: `bt_navigator.bond_timeout: 0.0` 추가
- 정적 검증: AST/YAML/colcon/--show-args/turtlebot3_gazebo 에셋 모두 통과
- **잔여**: 실제 시뮬 실행 검증 (Gazebo GUI) + patrol_sim.yaml 좌표 미세 조정 (사용자)

---

## ✅ 완료

### C-NAV2. aip3 Nav2 스택 활성화 — **완료 (2026-06-25)**
- FastDDS SHM 충돌 원인: `/dev/shm/fastrtps_*` 스테일 파일이 컨테이너 재시작 후 잔류(ipc:host 공유)
- 수정: `docker-compose.yml` 컨테이너 기동 시 `rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_*` 선행
- 수정: `docker/.env` 심링크 → `~/industrial_sub_vehicle/.env` (YAML 변수 치환에 필요)
  - 기존: `USE_SLAM=true, USE_NAV2=false` (기본값 사용) → 수정 후: `USE_SLAM=false, USE_NAV2=true`
- 결과:
  - `lifecycle_manager_localization`: Managed nodes are active ✅
  - `lifecycle_manager_navigation`: Managed nodes are active ✅
  - TF 체인: `map → scout_2/odom → scout_2/base_link` 확인 ✅
  - 중앙 PC에서 45개 scout_2 토픽 가시 ✅
- 잔여: AMCL 스캔 드롭 (C-AMCL 참조)

### T1. LiDAR 루프 버그 수정 (ANALYSIS B1) — **완료됨 (확인)**
- `fleet_sim.launch.py` 를 코드 리뷰한 결과 이미 `GroupAction(group)` 을 루프 내부에서 `actions.append()` 하는 구조로 구현돼 있어 버그가 존재하지 않음.
- 2026-04-22 Ubuntu 세션에서 코드 전수 검토로 확인.

---

## ✅ 추가 완료 (2026-04-22 Ubuntu 세션 — 코드 리뷰 후)

### ~~B3. twist_mux 런치 통합~~ — **완료 (2026-04-22)**
- `config/twist_mux_vehicle.yaml` 신규: estop_lock(90) > central(80) > fleet_coord(50) > autonomy(10)
- `central.launch.py`: OpaqueFunction으로 scout별 twist_mux 추가, `with_twist_mux` 인자 추가
- `fleet_sim.launch.py`: 차량 루프에 PushRosNamespace + twist_mux 추가, central include 시 `with_twist_mux:=false`

---

## 🟢 Ready to pick up (설계 고정, 구현만 필요)

### ~~T2. Supervisor estop_lock 퍼블리셔~~ — **완료 (2026-04-22)**
- `supervisor_node.py`: `_estop_lock_pubs`, `_estop_locked` 추가. CMD_ESTOP 시 Bool(True), CMD_CLEAR/RESUME 시 Bool(False) 발행. `_publish_status` 타이머마다 잠긴 차량에 Bool(True) 재발행.

### ~~T3. Supervisor 단위 테스트~~ — **완료 (2026-04-22)**
- `src/aip_fleet_supervisor/test/test_supervisor_node.py` 신규. 23개 테스트 전부 PASS.
- 커버리지: CMD_ESTOP/CLEAR/RESUME/PAUSE/MANUAL 분기, 와일드카드, 미지 차량/명령, 온라인/오프라인 판정, estop_lock 재발행.

### ~~T4. Foxglove 배터리 플롯 expression 수정~~ — **완료 (2026-04-22)**
- `fleet_overview.json`: `vehicles[0]` → `vehicles[:]{vehicle_id=="main"}` 필터 표현식.

### ~~T5. ESP32 heartbeat 문자열 안전 처리~~ — **완료 (2026-04-22)**
- `main.cpp`: raw 포인터 3줄 → `rosidl_runtime_c__String__assign()` 1줄.

---

## ✅ 추가 완료 (2026-04-23 Ubuntu 세션)

### ~~B4. OverridePanel HOLD-to-drive 연속 발행~~ — **완료 (2026-04-23)**
- `OverridePanel.tsx`: `onMouseDown` 1회 발행 → `startDriving` / `stopDriving` 으로 교체.
- `setInterval(publishManualFrame, 100)` 으로 10 Hz 스트리밍. `onMouseLeave` 추가로 버튼 밖 드래그 시에도 정지.
- 언마운트 시 `useEffect` cleanup 으로 인터벌 누수 방지.

### ~~T8. FleetHeartbeat.msg bounded~~ — **완료 (2026-04-23)**
- `FleetHeartbeat.msg`: `string→string<=32 vehicle_id`, `string[]→string<=64[<=8] active_behaviors`.
- `FleetStatus.msg`: `FleetHeartbeat[]→[<=4]`, `string[]→string<=32[<=4] offline_vehicle_ids`.
- `aip_fleet_msgs` + `aip_fleet_supervisor` + `aip_fleet_sim` 재빌드 PASS. 단위 테스트 23개 PASS.

### ~~T10. 바인드 주소 제한 (C3/C4)~~ — **완료 (2026-04-23)**
- `docker-compose.yml` foxglove-bridge: `--address 0.0.0.0` → `--address 192.168.0.9`.
- uros-agent: micro XRCE-DDS v2.x에 bind-IP 플래그 없음 → UFW 레이어에서 처리 (주석으로 명시).

### ~~T11. 공급망 digest 고정 (H4/H5)~~ — **완료 (2026-04-23, foxglove-bridge 제외)**
- `docker-compose.yml`: `ros:humble-ros-base`, `microros/micro-ros-agent:humble`, `influxdb:2.7` 에 `@sha256:...` 추가.
- `ghcr.io/foxglove/ros-foxglove-bridge:humble`: 인증 필요. `docker pull` 후 `docker inspect --format '{{index .RepoDigests 0}}'` 로 수동 확인 후 추가 필요 (TODO 주석 남김).
- `platformio.ini`: commit hash 고정 방법 주석 추가. 실제 hash 는 `git ls-remote` 로 확인 후 적용.
- `package-lock.json`: 이미 존재 확인. `.gitignore` 에 차단 없음.

---

## 🟡 설계 필요 (먼저 approach 논의 후 구현)

### ~~T6. aip_fleet_coordinator 스켈레톤~~ — **완료 (2026-04-23)**
- `src/aip_fleet_coordinator/` 신규 패키지.
- `coordinator_node.py`: TF2 기반 map-frame P-controller. 각 scout 가 main 을 offset(-1.5 m 등) 으로 추종.
- `central.launch.py`: `with_coordinator` 인자 추가, `_make_coordinator_nodes` OpaqueFunction.

### T7. Scout 위치추정 — **소프트웨어 완료 / 하드웨어 연동 일시 중단 (2026-04-23)**

**구현 완료 (코드 변경 불필요):**
- `scout_localizer_node.py`: ArUco DICT_4X4_50 검출, TF2 동적 체인, map→scout_N/base_link 발행.
- `camera_mode` 파라미터로 두 가지 배포 모드 지원.

**배포 모드 A — 차체 고정 카메라 (권장)**
- `with_localizer:=true camera_mode:=fixed` 로 활성화.
- 하드웨어 체크리스트: `scout_localizer_node.py` 상단 주석 참조.
- **재개 조건**: 카메라 구매·장착·캘리브레이션 완료 후.

**배포 모드 B — 4-DOF 서보 암 탑재 카메라 (개발 중단)**
- `with_localizer:=true camera_mode:=servo_arm camera_frame:=<암_프레임>` 로 활성화.
- **재개 조건** (모두 충족 시):
  1. 암 제어기 ROS2 드라이버의 발행 토픽 확인 (`ros2 topic list | grep -E 'joint|arm'`)
  2. URDF + `robot_state_publisher` 로 FK → TF 체인 구성 또는 드라이버 직접 TF 발행 확인
  3. 온도 모니터링 ↔ 스캔 모드 전환 로직 설계
- 노드 자체는 동적 TF 지원 완료 — 인프라만 갖추면 즉시 연동 가능.

**예산 참고 (UWB+IMU/엔코더 대안):** DWM1001 기준 약 $230–330 (32–46만 원).

---

## 🔴 보안 Phase 1 (프로덕션 전 필수, SECURITY.md 참조)

### ~~T9. SROS2 도입 (C1/C2/C5/H1/M2/L3/L4 일괄)~~ — **완료 (2026-04-23)**
- `config/security/sros2_policy.xml`: 노드별 publish/subscribe 권한 정의 (supervisor, watchdog, foxglove_bridge, coordinator×2).
- `scripts/sros2_init.sh`: keystore CA 생성 → 노드별 key → permission 일괄 설정 스크립트.
- `central.launch.py`: `with_security` 인자, `_make_security_env` OpaqueFunction (keystore 없으면 RuntimeError).
- `.gitignore`: `config/security/keystore/` 차단, `sros2_policy.xml` 커밋 허용.
- **활성화**: `bash scripts/sros2_init.sh` 후 `ros2 launch ... with_security:=true`.

---

## ⚪ 보안 Phase 2/3 (운영 경험 후)

Phase 2:
- ~~컨테이너 non-root (H6)~~ — **부분 완료 (2026-04-23)**: cap_drop 전 서비스, uros-agent/foxglove-bridge non-root. rosbag-recorder는 custom image 이전 후 완전 해결.
- rosbag 볼륨 LUKS 암호화 (H7)
- ~~ESP32 시리얼 `set_ns` 입력 검증 (H8)~~ — **완료 (2026-04-23)**: ns_valid() 검증 함수
- ~~ROS_DOMAIN_ID 환경변수화 (H9)~~ — **완료 (2026-04-23)**: .env + docker-compose + Dockerfile.central + platformio.ini
- ~~YAML/패널 스키마 검증 (M4/M5)~~ — **완료 (2026-04-23)**: M4 _validate_world/vehicles_yaml(), M5 sim_vehicle_node 서버 클램핑 기존 구현 확인.

Phase 3:
- WPA2-Enterprise 또는 WPA3 (M7)
- ESP32 secure_boot + flash_encryption (L1)
- 서명된 OTA (L2)
- 외부 syslog 감사 로그 (M6)

---

## ✅ 추가 완료 (2026-04-23 Ubuntu 세션 — 마무리)

### ~~setup_ubuntu.sh 생성~~ — **완료 (2026-04-23)**
- `scripts/setup_ubuntu.sh`: 11개 섹션, 멱등성·DRY_RUN 지원. 다른 PC에서 single-command 환경 구성.
- `scripts/sros2_init.sh`: deprecated `create_key` → `create_enclave` 수정.

---

## ✅ 추가 완료 (2026-04-23 — 군집 개념 재정립)

### 군집 설계 철학 문서화 — **완료 (2026-04-23)**
- `docs/VISION.md` 신규: 동등 피어 군집 목표, 세대별 로드맵, 임시 결정 목록
- `docs/SWARM_LOCALIZATION.md` 전면 재작성: scout=예산 제약 피어 관점, 4단계 업그레이드 경로
- `docs/SCOUT_LOCALIZATION_HW.md` → stub으로 교체 (SWARM_LOCALIZATION.md 참조)
- `docs/ARCHITECTURE.md`, `HANDOFF.md` VISION.md 참조 추가

---

## 🔧 잔여 즉시 작업

### ~~Ignition Phase-1 검증~~ — **완료 (2026-04-24)**

5대 스폰, diff_drive_controller active, TF 체인, teleop 이동 모두 확인.
차량 디자인도 후륜 구동 + 전방 캐스터 삼각 지지 구조로 변경 완료.

### ~~Phase-2 런치 버그 수정~~ — **완료 (2026-04-27), Gazebo 정상 시작 확인**

- `fleet_phase2.launch.py` 신규: Ignition + slam_toolbox(peer_1) + twist_mux×3 + coordinator×2 + nav_follower×2 통합
- `nav_follower.launch.py` 토픽 버그 수정 (`auto_cmd_vel` → `autonomy_cmd_vel`)
- `ign_fleet.launch.py` `with_static_tf` arg 추가, 차량 5대 → 3대 (peer_1/2/3)
- `aip_phase2` / `aip_override` alias 추가
- `setup.cfg` 추가 → coordinator_node `ros2 run` 탐색 경로 수정
- spawner 딜레이 3→6 s, `--controller-manager-timeout 30` 추가
- `ros-humble-twist-mux` apt 설치 필요 (사용자 완료)
- **Gazebo 정상 시작 확인** — 잔여: AMCL 수렴 + V 포메이션 팔로잉 검증

---

### ~~UWB 소프트웨어 선행 작업~~ — **완료 (2026-04-27)**

1. `/<ns>/odom` — 시뮬에서 diff_drive_controller odom relay로 이미 제공
2. `uwb_localizer_node.py` — 가중 Gauss-Newton (SLAM w=1.0, 협력 w=0.5, 앵커 w=1.0) + odom 예측 → `map→<ns>/base_link` TF
3. `sim_peer_sensing_node.py` — 고정 앵커 시뮬 추가 (anchor_ids/x/y 파라미터)
4. `coordinator_node.py` — `tf_stale_holdout_sec` 파라미터, TF 미스 시 캐시 pose 사용
5. `central.launch.py with_uwb_localizer:=true` 인자 추가
6. V 포메이션 수식 버그 수정 (대칭 쉐브론 공식)
7. 시뮬 3대 축소 (`supervisor_peers.yaml`, `fleet_phase2.launch.py`)

> 하드웨어: RPi Zero 2W + DWM3001C UWB + 인크리멘탈 엔코더×2 + ICM-42688 IMU (~9만 원)
> 전 차량 BOM (예산 피어 1대 + 메인 1개 UWB): ~$163 / 약 23만 원

---

### ~~MPPI 통합 + 열화상 파이프라인 사전 비행 검사~~ — **완료 (2026-05-21)**

- MPPI 설정 10항목 ALL PASS (batch_size=2000, time_steps=56, DiffDrive, CostCritic.consider_footprint=true)
- patrol_monitor `_estimate_map_position` 단위 테스트 11개 ALL PASS
- alert_visualizer_node DELETEALL 추가 후 마커 로직 10/10 PASS
- 전체 사전 비행 검사 14/14 PASS, aip_fleet_perception + aip_fleet_autonomous 빌드 SUCCESS
- 총 샘플: 112,000 (DWB 대비 280×), 예측 지평선 2.8초

---

### ~~3대 스폰 정상화 (gz_ros2_control 첫 번째 엔티티 버그)~~ — **완료 (2026-05-22)**

- `ign_fleet.launch.py`: gz_warmup RSP(`namespace='gz_warmup'`) + 최소 워밍업 모델 t=1.0s 스폰
- 차량 스폰 딜레이: `2.0+idx*0.8` → `3.5+idx*0.8`
- 검증: peer_1/2/3 모두 JSB+DDC active, `/peer_N/{cmd_vel,odom,scan}` 발행 확인

---

### Phase-2 odom TF 분리 수정 — **코드 완료 / 실행 테스트 필요 (2026-05-18)**

**적용된 수정:**
- `ekf_vehicle.yaml`: `odom0_relative: false` → `odom0_relative: true`
- `scripts/odom_frame_fixer.py`: 초기 pose 영점화 추가 (일반 2D rigid transform, T_rel = T0_inv·T1)
- `params/amcl.yaml`: 파티클 필터 강화 (`min_particles:1000`, `max_beams:180`, `z_rand:0.3`, `sigma_hit:0.15`)
- `launch/nav_follower.launch.py`: `initial_cov_xx/yy:0.05`, `initial_cov_aa:0.025` (tight initial cloud)

**테스트 항목 (사용자):**
1. `aip_phase2` 재실행 → RViz에서 `peer_2/odom` 프레임이 차량과 겹치는지 확인
2. peer_1 teleop 후 peer_2/3 V 포메이션 팔로잉 확인
3. `ros2 run tf2_tools view_frames` → TF 체인 끊김 없는지 확인

---

### ~~이벤트 기반 자율 탐색 아키텍처 런타임 검증~~ — **완료 (2026-05-26)**

`fleet_autonomous.launch.py gui:=false with_patrol:=true` headless 실행.
- 전체 이벤트 체인 PASS: explore_lite → 79% 커버리지 → /fleet/map_ready → peer_2/3 Nav2 자동 기동 → patrol_node 기동.
- ⚠️ TF "jump back in time" 반복 경고: Gazebo 엔티티 스폰 시 발생, 자동 회복, 별도 과제로 등록.

---

### ~~peer_2/3 TF 트리 단절 버그 수정~~ — **코드 완료 (2026-06-11) / 재테스트 필요**

**원인:**
1. `_freeze_map_and_serve()` 3초 고정 sleep → 고부하 환경에서 map_server lifecycle 활성화 실패 → `/map_static` 미발행
2. `_wait_for_tf()`가 EKF TF만 확인 → AMCL이 수렴하기 전에 다음 단계로 진입

**수정 내역 (빌드 SUCCESS):**
- `follower_trigger_node.py`:
  - `_freeze_map_and_serve()`: 고정 sleep → 최대 30초 노드 등장 폴링 + lifecycle 3회 재시도
  - `_wait_for_amcl_tf()` 신규: Nav2 기동 후 `map→{vid}/base_link` TF 수렴 최대 90초 대기
  - `_launch_all()`: `_launch_nav2(vid)` 직후 `_wait_for_amcl_tf(vid)` 호출

**테스트 방법 (사용자):**
```bash
source ~/.bash_aliases && aip sim
aip_auto_patrol   # 또는 auto_patrol_2x 모드
# peer_1 매핑 완료 → peer_2/3 스폰 시 TF 단절 오류 없는지 확인
# 로그에서 "AMCL TF 수렴 완료 ✓" 확인
```

---

### UWB 협력 측위 시뮬 검증 — **낮은 우선순위로 하향 (2026-06-15)**

`with_uwb:=true` 런치 인수 및 uwb_localizer_node×2 통합은 완료.
단, **실차 계획에서 UWB 전면 배제 결정** → 실차 배포 목적으로는 불필요.
알고리즘 연구/시뮬 비교 용도로 코드는 유지하되, 별도 검증 세션은 후순위.

---

### ~~웹 대시보드 라이트 테마 + SLAM 맵 렌더링~~ — **완료 (2026-06-15)**

**추가 수정 (2026-06-15):**
- `dashboard_server.py`:
  - `_state_cache: dict[str, Any]` 전역 추가 — 신규 WebSocket 클라이언트 접속 시 캐시된 상태 재전송.
  - `/map` (절대 경로) 구독 추가 — SLAM toolbox가 `/peer_1/map` 이 아닌 `/map`에 발행함.
  - `central.launch.py` relay: `input_topic: '/peer_1/map'` → `'/map'` 수정.
  - `leader_nav.launch.py`: `behavior_server` lifecycle 제외, `bond_timeout: 0.0` 추가 (WSL2 플러그인 로딩 지연 대응).
- 시뮬 헬퍼 스크립트 `run_sim.sh`, `run_central.sh` (workspace 루트).

**실행 방법 (WSL Ubuntu-22.04):**
```bash
# Terminal A (시뮬):
tmux new-session -d -s sim; tmux send-keys -t sim '/mnt/c/Projects/aip-swarm-ws/run_sim.sh' Enter
# Terminal B (central, 90초 후):
tmux new-session -d -s central; tmux send-keys -t central '/mnt/c/Projects/aip-swarm-ws/run_central.sh' Enter
# 브라우저: http://localhost:8080
```

**검증 완료:** MAP READY (녹색), SLAM 맵 279×200 표시, peer_1 삼각형 위치 마커 표시.

**Foxglove Studio 설정:**
- 3D 패널 추가 → 토픽: `/peer_1/map_relay` (OccupancyGrid), `/peer_1/scan` (LaserScan)
- 차량 위치: `/fleet/peer_poses` 또는 `/peer_N/odom`

---

### ~~대시보드 차량 ONLINE 표시 + peer_2/3 위치 표시~~ — **완료 (2026-06-15)**

**수정 완료:**
1. **fleet_status ONLINE 표시** — `_clients -= dead` UnboundLocalError 수정 (`difference_update` 사용). asyncio 스케줄링 방식도 `call_soon_threadsafe` + `create_task`로 개선.
2. **heartbeat 자동 발행** — `sim_heartbeat_node.py` → `fleet_autonomous.launch.py` t=16s 블록에 통합. 중앙 세션에서 수동 실행 불필요.
3. **차량 위치 표시** — `sim_pose_relay_node.py` 신규. 시뮬 세션 내 TF 직접 조회 → `/fleet/peer_poses` (TRANSIENT_LOCAL) 발행. `/tf` VOLATILE 토픽의 DDS 세션 경계 미통과 문제 우회.
4. **대시보드 타이머 수정** — `central.launch.py`에서 dashboard `use_sim_time: True` → `False`. (시뮬 `/clock`이 세션 경계를 넘지 않아 타이머가 발화하지 않던 근본 원인 제거)

**빌드 필요:** `colcon build --symlink-install --packages-select aip_fleet_gazebo aip_fleet_autonomous aip_fleet_dashboard aip_fleet_bringup`

---

## 📚 문서/기능 잔여

- ~~Foxglove 패널 빌드 체인~~ — **확인 완료 (2026-04-23)**: `npm run build` + `npm run package` PASS, `.foxe` 정상 생성.
- ~~`docs/ANALYSIS.md` 설계 결정 정리~~ — **완료 (2026-04-23)**: 섹션 1~9 현행화.
- ~~systemd unit 파일 독립화~~ — **완료 (2026-04-23)**: `docker/central/aip-central.service` 신규.
- ~~텔레메트리 브릿지 (§8)~~ — **완료 (2026-04-23)**: `aip_fleet_telemetry` 패키지, `with_telemetry:=true`로 활성화.

**잔여 낮은 우선순위**:
- B2: 와일드카드 차량 목록 동적 갱신 (미착수)
- ~~`aip_fleet_sim/test/test_world.py` — ray-cast 단위 테스트~~ — **완료**: `TestRayRectIntersect`(10개), `TestWorldRaycast`(8개), `TestOccupancyGrid`(7개) 구현됨
- ~~`.github/workflows/colcon.yml` — CI 구성~~ — **완료 (2026-06-15)**: `aip_fleet_autonomous` 추가, nav2-msgs/action-msgs apt 패키지, patrol_plan YAML 검증 스텝 추가
- Grafana 대시보드 JSON (InfluxDB 실 데이터 수집 후)
- ESP32 PlatformIO 빌드에서 bounded FleetHeartbeat 검증 (펌웨어 빌드 환경 필요)

---

### ~~TF "jump back in time" 수정~~ — **코드 완료 (2026-06-15) / 실행 테스트 필요**

**원인:**
- Gazebo 물리 스텝 0.004s(250Hz) → /clock 250Hz DDS 메시지 순서 역전 → TF 버퍼 초기화
- BT loop 100Hz + MPPI 3대×1000샘플 = 30,000 traj/s → CPU 과부하 → RTF 순간 저하

**수정 완료:**
- `fleet_world.sdf`: max_step_size 0.004→0.01 (250Hz→100Hz, /clock 60% 감소)
- `nav2_full.yaml`: bt_loop_duration 10→25ms, batch_size 1000→500, local costmap 5→2Hz, AMCL 3000→1000
- `ekf_vehicle.yaml`: odom0/odom1 queue_size 10→3, imu0 10→5
- `slam_toolbox_online.yaml`: throttle_scans: 2 추가 (SLAM CPU 50% 절감)
- `spawn_vehicle.launch.py`: _make_master_yaml() dead code 제거

**테스트 항목:**
```bash
source ~/.bash_aliases && aip sim
aip_auto_patrol   # ~10분 이상 운용
# 기대: "BT tick rate exceeded" 경고 없음, TF jump 없음
# 전 차량 순찰 지속 확인
```

---

### ~~MPPI 궤적 시각화 remapping + peer_2 joint TF + arm 회전~~ — **완료 (2026-06-18, 사용자 확인)**

**수정 완료:**
- `autonomous_nav.launch.py` + `leader_nav.launch.py`: `/trajectories` → `/{vid}/trajectories` remapping
- `spawn_vehicle.launch.py`: JSB/DDC/arm spawner timeout 180→600s + relay 노드 추가 (20Hz)
- `ros2_controllers_base.yaml`: update_rate 100Hz (CM 제어 주기 고정)
- `main_agv.urdf.xacro` arm link 관성 **1e-5 → 0.001 kg·m²** (ODE 수치 안정화)
- `arm_scan_node.py`: dead-reckoning velocity 제어 + FOV 25Hz 보간 (±90° 고착 + 끊김 동시 해결)
- `nav2_full.yaml`: movement_time_allowance 15→8s
- `navigate_w_collision_recovery.xml`: BackUp 0.15m/s, Wait 3s (peer_1 초기 고착 ~57→20s)

---

### 순찰 웨이포인트 추종 품질 개선 — **코드 완료 (2026-06-16) / 실행 테스트 필요**

**문제 (사용자 보고):** 도달 시간 느림, 지정 좌표 오버슛, 고착 시 회피 대응 미흡, 경로 최적화 기대 이하.

**수정 완료 (전체):**
- `nav2_full.yaml`: `GoalCritic.cost_weight 8.0→10.0`, `PathFollowCritic.threshold_to_consider 1.4→1.0`,
  `analytic_expansion_max_length 3.0→5.0`, wz_max 1.40(TB3)/1.70(FIT0186 override),
  `update_min_d 0.05→0.02m`, `update_min_a 0.10→0.05rad`
- `nav2_override_peer1.yaml` 신규: FIT0186 전용 vx_max/wz_max/footprint/turning_radius 오버라이드
- `leader_nav.launch.py`: nav2_yaml + nav2_override 병합 로드 구조
- `spawn_vehicle.launch.py`: stuck_escape 파라미터 조정
- `stuck_escape_node.py`: `escape_angular` 파라미터 추가 (후진+회전 탈출)
- `autonomous_nav.launch.py`: behavior_server 추가 + BT XML → `navigate_w_collision_recovery.xml`
- `phase2.rviz`: MPPI 시각화 토픽 수정(`/trajectories` MarkerArray), Nav Plan 색상 차별화

**테스트 항목:**
```bash
source ~/.bash_aliases && aip sim
aip_auto_patrol   # 3대 동시 순찰 ~10분 이상
# peer_2/3 오버슛 감소, 경로재탐색 루프 해소 확인
# ros2 node list | grep behavior_server  (peer_2/3 behavior_server 기동 확인)
# RViz: /peer_N/trajectories MarkerArray MPPI 시각화 확인
```

**보류 (의도적 미적용):**
- `xy_goal_tolerance: 0.35` — 과거 spin-drift 회귀 방지 위해 유지
- `iteration_count: 1→2` — CPU 여유 확인 후 검토

---

### ~~순찰 경로 구석 커버리지 확장~~ — **완료 (2026-06-15)**

- `fleet_autonomous.launch.py` `_PATROL_WP`:
  - peer_1: 9점 → 11점 — 북동(4.5,7.5)/북서(-4.5,7.5) 구석 추가
  - peer_2: 동쪽 x=3.0 → x=4.5 + 남부 y=-5.0 → y=-7.5 심층
  - peer_3: peer_2 대칭 확장
- `config/patrol_plan_template.yaml`: 구석 커버리지 경로로 전면 교체 (27 웨이포인트)
- 전 좌표 inflation_radius=0.35m 기준 안전 검증 완료

---

### ~~웹 관제 전면 개선 (Dashboard 2.0)~~ — **완료 (2026-06-15)**

**목표:** 딜레이 없는 60fps 부드러운 관제, 시뮬 및 실제 로봇 모두 지원.

**완료 항목:**
- 60fps rAF 루프 + 지수 평활 보간 (α=0.16) — 포즈 업데이트를 부드러운 마커 이동으로
- 맵 팬/줌 (드래그·마우스휠, zoomAt() 함수)
- 맵 툴바 4모드: view / goto / patrol / keepout
- 이동 명령 클릭 (goto 모드 → navigate_to WS → /{vid}/goal_pose)
- Keepout 폴리곤 드로잉 → `/fleet/keepout_zones` String(JSON) 발행
- 도킹 스테이션 위치 설정 + NavigateToPose 연동
- 5개 탭 패널: 제어 / 순찰 / 구역 / 시스템 / 비전
- 속도(m/s)·누적 거리(m) 텔레메트리 (Odometry 구독 → odom WS 메시지)
- 커버리지 진행률 바 (전역 + 차량별)
- HIGH 알림음 (Web Audio API 3단 비프) + 알림 자동 맵 팬
- MCAP 녹화 버튼 (subprocess ros2 bag record 원격 제어)
- 키보드 단축키: V/G/P/K/F/±/WASD/Esc
- Toast 알림 (3초 자동 사라짐)

**검증:** preview 서버에서 레이아웃·카드·탭·모크 데이터 모두 정상 확인.

---

### ~~런타임 에러 3종 + 카메라 UX~~ — **완료 (2026-06-16)**

**SHM 락 / 8080 충돌 / 화면 멈춤 해결:**
- `fastdds_local.xml`: SHM 비활성 + localhost UDP-only (`useBuiltinTransports=false`) → `RTPS_TRANSPORT_SHM open_and_lock_file failed` 원천 제거
- `run_sim.sh` / `run_central.sh`: `FASTRTPS_DEFAULT_PROFILES_FILE` export 추가
- `run_central.sh`: central 기동 전 `pkill dashboard_server` + `fuser -k 8080/tcp` → 8080 충돌(dashboard 사망=화면 멈춤) 방지
- `run_sim.sh`: 기동 전 stale `/dev/shm/fastrtps_*` 정리

**카메라 UX:**
- 비전 2박스를 오른쪽 탭 → **맵 패널 아래 2분할**로 이동 (탭은 4개로 축소)
- 박스 클릭 → 확대 라이트박스 모달(라이브 갱신, Esc 닫기)
- `!connected` 시 맵에 "서버 연결 끊김" 오버레이 (멈춤 원인 가시화)

### ~~peer_1 TF 단절 (`map↔peer_1/base_link`)~~ — **완료 (2026-06-19) — TF 에러 0건 확인**

**근본 원인:** slam_toolbox(t=16s)가 EKF(t=3.5+17=20.5s)보다 4.5초 먼저 시작
→ `peer_1/odom→base_link` TF 없이 실행 → transform_timeout=3.0s 재시도 4.5s 지속.

**수정:** `fleet_autonomous.launch.py` slam_toolbox t=16s → t=21s 분리.
EKF(t=20.5s) 이후 0.5s에 시작 → TF 경쟁 조건 제거.

**실행 테스트 결과 (2026-06-19 headless):**
- TF 에러 0건, 제어 루프 누락 0건, 33회 Navigation Goal 전송, 87.0㎡ 커버리지 진행.

---

### ~~lethal space 루프 수정~~ — **완료 (2026-06-19) — 커버리지 87→135㎡, 오류 0건 확인**

**증상:** peer_1이 (-6.74, -2.28) 코너 frontier에서 costmap LETHAL 고착
→ BackUp 후방 벽 감지 반복 실패 (143회 lethal / 216회 backup failed).

**수정 (3종, 커밋 e6a8a70):**
1. `navigate_w_collision_recovery.xml`: ClearAll+Spin(1.57rad)+BackUp 단계 추가 (코너 탈출 회전)
2. `fleet_autonomous.launch.py` explore_lite: `min_frontier_size 0.5→0.75m`, `progress_timeout 60→30s`
3. `nav2_full.yaml` local_costmap: `footprint_padding 0.05 제거` (local LETHAL 0.155m→0.105m 축소)

---

## 작업 선택 가이드

- **먼저 스모크 테스트 통과를 목표** 로 한다면: T1 → T5 → T4 → T3 (sim 안정화 → ESP32 기초 → 대시보드 → 테스트).
- **보안 강화를 목표** 로 한다면: T11 → T9 → T10 (공급망 고정 → SROS2 → 바인드 제한).
- **군집 기능 확장을 목표** 로 한다면: T7 (Scout 위치) → T6 (coordinator) → T2 (estop_lock 확정).

각 작업 시작 시 `docs/agent_context/conversation_log.md` 하단에 날짜·결정·결과 섹션 추가할 것.

---

## 🔧 실차 전환 준비 (별도 세션 예정)

> 2026-06-15 하드웨어 확정 기반. 시뮬 개발 완료 후 순차 진행.

### HW-1. use_sim_time 일괄 전환
- `src/aip_fleet_autonomous/params/nav2_full.yaml` 외 16곳 `use_sim_time: true` → `false`
- 하드웨어 bringup launch에서 `use_sim_time` 인수 기본값 `false`

### HW-2. 차량별 LiDAR 설정 파일 작성
- 각 차량 LiDAR 모델 확정 후 개별 파라미터 파일 작성
- scan topic name, frame_id, range_min/max, 앵글 범위 등

### HW-3. TurtleBot 통합
- 로보티즈 TurtleBot 모델 확정 (TurtleBot3 vs TurtleBot4)
- 공식 bringup 패키지 설치 + AIP 네임스페이스 규약으로 리매핑

### HW-4. STS3215 서보 ROS2 드라이버 선정 및 연동
- Feetech STS3215 ROS2 드라이버 선정 (feetech_ros2 / Waveshare / 자작)
- ros2_control hardware_interface 구현
- diff_drive_controller 파라미터 조정

### HW-5. 멀티 SLAM 맵 공유 전략
- 전 차량 독립 slam_toolbox 실행 시 맵 병합 방식 결정
- 옵션: m-explore multirobot_map_merge / 중앙 집중 맵 서버 / 독립 내비게이션

### HW-6. 실차 하드웨어 bringup launch 작성
- 차량별 bringup launch 파일 (per-vehicle)
- UWB 관련 노드/파라미터 제거

---

## ✅ 추가 완료 (2026-06-19 세션 6 — 메인 차량 RPi 세팅)

### ~~RPi 기본 세팅~~ — **완료**
- AP 전환: jdedu9807 → aip2.4GHz (IP: 192.168.0.18) ✅
- 스왑 2GB 추가 ✅
- ROS_DOMAIN_ID 42 설정 ✅
- SSH 키 등록 (dev PC ed25519) ✅
- twist_mux 설치 (ros-humble-twist-mux) ✅
- `aip_bringup/launch/fleet_main.launch.py` 신규 (namespace='main' + twist_mux + heartbeat) ✅
- `aip_bringup/config/twist_mux_main.yaml` 신규 ✅
- `aip_bringup/scripts/heartbeat_pub.py` 신규 ✅
- FastDDS 양방향 통신 검증 (Simple Discovery, 192.168.0.x) ✅

### 잔여 실차 작업

- **YDLidar 연결 확인**: 차량에 물리적으로 연결 후 `/dev/ydlidar` symlink 확인
- **fleet_main.launch.py 실차 구동**: `ros2 launch aip_bringup fleet_main.launch.py`
- **fleet AP 확정**: 192.168.0.0/24 유지 결정, 코드 수정 완료 (R4 참조)

---

## ✅ 추가 완료 (2026-06-17 — 실차 nav2 버그 수정)

### ~~실차 turtlebot3.launch.py nav2 GroupAction 버그~~ — **완료 (2026-06-17, 00eaea5)**

- `turtlebot3.launch.py`: nav2 GroupAction에 `PushRosNamespace(namespace)` + `SetRemap('/tf','/tf')` + `SetRemap('/tf_static','/tf_static')` 추가
  - 이유: `navigation_launch.py`는 namespace를 RewriteYaml root_key로만 사용 → PushRosNamespace 없으면 MPPI params 미매칭, `/scout_1/tf` TF 경로 불일치
- `nav2.yaml`: `global_costmap.static_layer`에 `map_topic: /map` 추가
  - 이유: `slam_toolbox`는 절대 `/map` 발행, namespaced costmap은 `/scout_1/map` 구독 → 맵 미수신

**잔여 sim 파일 (미커밋, 테스트 전용):**
- `turtlebot3_sim.launch.py`, `nav2_sim.yaml`, `slam_toolbox_sim.yaml`, `patrol_sim.yaml`
- patrol_sim.yaml waypoints 조정 필요 (현재 ±1.8m 자리표시자 → turtlebot3_world 자유공간 실좌표로 교체)

---

### ~~웹 UI 미구현 기능 전면 구현~~ — **완료 (2026-06-19, fe28832~60639dc)**

- ~~순찰 시작/정지 버튼~~: patrol_node.py start/stop/mode:loop 처리 + 버튼 색상 피드백
- ~~도킹 위치 영속화~~: ~/aip_maps/dock_positions.json 저장 + WS 재접속 복원
- ~~금지구역 영속화~~: ~/aip_maps/keepout_zones.json 저장 + 새로고침 후 자동 복원
- ~~patrol 버튼 상태 동기화~~: selectVehicle() 시 캐시된 patrolStatus로 버튼 갱신

---

### ~~금지구역(keepout zone) 실제 동작 구현~~ — **완료 (2026-06-19, 87faf57)**

**문제:** 대시보드에서 금지구역 폴리곤을 그리고 WS로 전송해도 Nav2 costmap에 실제 반영되지 않았음.

**구현 (커밋 87faf57):**
- `keepout_zone_node.py` (신규): `/fleet/keepout_zones` JSON 구독 → 폴리곤 내부 0.05m 격자 채우기 → `/fleet/keepout_cloud` (PointCloud2, TRANSIENT_LOCAL) 1Hz 발행. 구역 감소 시 전 차량 ClearEntireCostmap 서비스 자동 호출.
- `nav2_full.yaml`: global/local costmap observation_sources에 `keepout_cloud` 추가 (`marking:True`, `clearing:False`, `obstacle_max_range:200m`)
- `dashboard_server.py`: `cmd_keepout`에 zones 저장; `cmd_navigate`에서 ray-casting으로 목표 좌표가 금지구역 내부이면 WS로 `navigate_rejected` 전송 후 Nav2 발행 차단
- `index.html`: `navigate_rejected` 수신 시 고경고(red) toast 표시
- `fleet_autonomous.launch.py`: t=16s 블록에 `keepout_zone_node` 추가
- `setup.py`: `keepout_zone_node` 엔트리포인트 추가

**빌드:** `colcon build` 2 packages PASS (경고만, 에러 없음)

---

## 🔮 심화 과제 — 스탠드얼론 관제 앱 (미착수 / 추후 참조)

> **착수 조건**: 실차 전환 완료 후, 현장 운용에서 웹 대시보드의 한계가 체감될 때.
> 현 단계(시뮬 개발)에서는 `dashboard_server.py` + 웹 대시보드로 충분.

### 배경 및 동기

`foxglove_bridge`는 ROS2 CDR → Protobuf 재직렬화 + WebSocket 전송으로
시뮬 PC CPU를 상당 부분 점유한다. 반면 `dashboard_server.py`는 필요한
토픽만 직접 구독하므로 이미 효율적이지만, 웹 브라우저 레이어(JSON 직렬화
+ WebSocket)가 남아있다. 스탠드얼론 앱은 이 레이어를 제거하고 DDS SHM
에서 GUI 렌더러까지 데이터가 메모리 내에서 직접 이동한다.

```
현재: DDS(SHM) → dashboard_server.py → WebSocket(JSON) → 브라우저(JS)
목표: DDS(SHM) → PyQt6 앱 내부 rclpy 노드 → Qt 시그널 → QPainter 렌더링
```

별도 PC 실행 시 시뮬 PC 부담을 완전히 분리할 수 있다.

### 권장 스택: PyQt6 + rclpy

현 프로젝트가 Python(rclpy) 기반이므로 기존 코드 재활용 범위가 넓다.

```python
# 기본 구조 스케치
class FleetMonitorApp(QMainWindow):
    # ROS 콜백 → Qt 스레드 안전 전달용 시그널
    sig_pose   = pyqtSignal(dict)   # /fleet/peer_poses
    sig_status = pyqtSignal(dict)   # /fleet/status
    sig_alert  = pyqtSignal(str)    # /fleet/alerts

    def __init__(self):
        self.node = FleetMonitorNode(self)          # rclpy 노드
        self.ros_thread = threading.Thread(
            target=rclpy.spin, args=(self.node,), daemon=True)
        self.ros_thread.start()
        self._build_ui()

    def _build_ui(self):
        self.map_widget  = MapWidget()              # OccupancyGrid 렌더
        self.fleet_panel = FleetStatusPanel()       # 차량별 배터리/모드
        self.estop_panel = EStopPanel()             # E-Stop / Override
```

### 구현 모듈 분류

| 모듈 | 역할 | 기존 코드 재활용 가능 범위 |
|---|---|---|
| `FleetMonitorNode` | rclpy 노드, 토픽 구독·명령 발행 | `dashboard_server.py`의 구독·발행 로직 그대로 |
| `MapWidget` | OccupancyGrid → QImage + 차량/LiDAR 오버레이 | `index.html` 캔버스 로직을 QPainter로 이식 |
| `FleetStatusPanel` | 차량별 배터리·모드·속도 표시 | `dashboard_server.py` `_cb_status` 로직 |
| `EStopPanel` | E-Stop · Override 버튼 | supervisor 토픽 발행 로직 |
| `PatrolEditor` | 웨이포인트 클릭 편집 | `index.html` patrol 모드 좌표 변환 로직 |
| `AlertView` | 열화상 알림 목록 | `/fleet/alerts` 구독 |

### 핵심 구현 주의사항

**1. ROS-Qt 스레드 분리**
rclpy spin은 반드시 별도 스레드에서 실행해야 한다.
Qt GUI는 메인 스레드에서만 갱신할 수 있으므로 데이터 전달에
`pyqtSignal`을 사용한다 (직접 위젯 갱신 시 세그폴트).

```python
# 올바른 패턴
def _cb_poses(self, msg):                    # ROS 콜백 스레드
    self.app_ref.sig_pose.emit(to_dict(msg)) # 시그널 emit은 스레드 안전

def _on_pose_updated(self, data):            # Qt 메인 스레드
    self.map_widget.update_poses(data)       # 여기서만 위젯 갱신
```

**2. OccupancyGrid → QImage 변환**
```python
def occupancy_to_qimage(grid: OccupancyGrid) -> QImage:
    data = np.array(grid.data, dtype=np.int8).reshape(
        grid.info.height, grid.info.width)
    rgb = np.full((*data.shape, 3), 128, dtype=np.uint8)  # unknown=회색
    rgb[data == 0]   = 255   # free=흰색
    rgb[data == 100] = 0     # occupied=검정
    return QImage(rgb.tobytes(), grid.info.width,
                  grid.info.height, QImage.Format.Format_RGB888)
```

**3. 맵 좌표 ↔ 화면 좌표 변환**
```python
# map_origin + resolution 기반 변환 (index.html canvasToWorld 로직과 동일)
def world_to_screen(self, wx, wy):
    px = (wx - self.map_origin_x) / self.resolution
    py = self.map_height - (wy - self.map_origin_y) / self.resolution
    return QPointF(px * self.scale + self.offset_x,
                   py * self.scale + self.offset_y)
```

### 배포 전략 (별도 PC 운용)

```bash
# 관제 PC에서 (같은 WiFi, ROS_DOMAIN_ID=42)
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
pip install PyQt6
python3 src/aip_fleet_monitor/fleet_monitor_app.py
```

시뮬 PC는 추가 설정 없이 DDS UDP로 토픽을 브로드캐스트하므로
관제 PC가 자동으로 탐색·구독한다.

### 착수 우선순위 판단 기준

- 실차 전환 후 현장에서 태블릿/노트북 전용 앱이 필요해질 때
- 열화상 이미지(`sensor_msgs/Image`) 실시간 스트리밍이 필요할 때
  (JSON base64 인코딩 없이 QImage 직접 렌더링 가능)
- 시뮬 + 관제를 단일 PC에서 돌릴 때 실측 RTF가 0.5 미만으로 떨어질 때
  (RTF=0.5는 gz_ros2_control 초기화 타이밍 기준 실험적으로 확인한 최소값.
   추가 부하로 실측 RTF가 더 낮아지면 spawner 타임아웃·컨트롤러 초기화 실패 재현 가능)

---

## 2026-06-23 추가 대기 작업 — main 표준 통합 후 실차 온라인화

### P0. aip1 heartbeat 수신 확인

- 통합본은 이제 팀 main 표준 `FleetHeartbeat.msg`와 Simple Discovery 기본값을 사용한다.
- `192.168.0.3` SSH 포트는 열려 있으나 `aip1/<REDACTED_PASSWORD>` 로그인은 실패했다.
- `<REDACTED_PASSWORD>`로도 `aip`, `ubuntu`, `pi`, `robot`, `user`, `main`, `agv`, `aip1` 계정 로그인 모두 실패했다.
- 현재 웹의 `aip1` online 표시는 ping 기반 임시 overlay다.
- 팀원에게 `.3` 로그인 계정 또는 `/aip1/heartbeat` 상태 확인이 필요하다.
- 다음 확인:
  - 중앙 PC에서 `/aip1/heartbeat` 토픽 발견 여부
  - `/aip1/heartbeat` 타입이 `aip_fleet_msgs/msg/FleetHeartbeat` 구형 계약인지
  - `/fleet/status`에 `aip1` online이 들어오는지

### P0. aip2/aip3 표준 heartbeat 전환

- 현재 실차 `scout_1`은 신형 heartbeat를 `/scout_1/heartbeat`로 발행한다.
- 팀 main 표준과 맞추려면 차량 쪽에서 `/aip2/heartbeat`를 구형 `FleetHeartbeat`로 발행해야 한다.
- 현재 `scout_2`는 heartbeat publisher가 꺼져 있었으므로 `/aip3/heartbeat` 표준 발행이 필요하다.
- 중앙 PC 한 프로세스에서 같은 이름의 `aip_fleet_msgs/FleetHeartbeat` 구형/신형을 동시에 받을 수 없으므로, 임시 변환은 중앙보다 차량 쪽 adapter가 안전하다.
- 임시 표시 복구로 UDP status overlay를 사용 중이다.
  - `.4`: `/tmp/status_aip2.py`
  - `.5`: `/tmp/status_aip3.py`
  - 중앙 수신: `dashboard_server.py` UDP `19050`
  - 브라우저 확인: `aip2/aip3` online, `aip1` offline.

### P1. 현장 alias 모드 사용 조건 정리

- 기본 통합본은 `aip1/aip2/aip3` 표준만 사용한다.
- 실차가 아직 `scout_1/scout_2` 네임스페이스라면 테스트 때만 다음 환경변수로 alias를 명시한다.

```bash
export AIP_VEHICLE_TOPIC_ALIASES=aip1=aip1,aip2=scout_1,aip3=scout_2
```

- 이 alias는 토픽 이름만 바꿔줄 뿐, heartbeat 메시지 계약 불일치는 해결하지 못한다.
---

## 2026-06-23 추가 대기 작업 — main+sub 3대 표시 이후

### P0. DDS heartbeat 정식 통합

- 현재 웹의 `3 online`은 UDP status overlay 기반이다.
- aip1의 `/aip1/heartbeat`는 aip1 내부에서는 정상 발행되지만 중앙 WSL에서는 discovery되지 않는다.
- Simple Discovery, Discovery Server, Discovery Server 재기동 후에도 중앙 WSL `ros2 topic echo /aip1/heartbeat`는 실패했다.
- 다음 중 하나를 선택해 정식화해야 한다.
  - 중앙을 team main과 동일한 네이티브 Linux/discovery 조건에서 실행.
  - WSL mirrored networking + FastDDS Discovery Server locator 문제를 tcpdump로 분석.
  - 차량 side adapter를 만들어 `/aipN/heartbeat`를 team main 구형 `FleetHeartbeat` 스키마로 발행.

### P0. UDP status overlay 임시 프로세스 영구화 여부 결정

- 현재 임시 프로세스:
  - aip1 `.3`: `/tmp/status_aip1.py`
  - aip2 `.4`: `/tmp/status_aip2.py`
  - aip3 `.5`: `/tmp/status_aip3.py`
- 재부팅하면 사라질 수 있다.
- 계속 시연이 필요하면 systemd user service 또는 차량 bringup script에 별도 status forwarder로 넣을 수 있다.
- 단, 이것은 표시용 보완이며 ROS heartbeat 정식 통합은 아니다.

### P1. 맵/pose 표시 복구 유지

- 중앙 재시작 후 저장맵은 수동으로 다시 불러왔다.
- 현재 확인된 저장맵:
  - `전체맵/저장맵 · 201x167 · 0.05 m/cell`
- 다음 작업에서 중앙을 재시작하면 먼저 저장맵 로드 상태를 확인한다.
- 2026-06-23 현재 웹 카드 3대 모두 `pose:--` 상태다.
- 로봇 위치 marker는 `/fleet/peer_poses`, `map -> base_link` TF, 또는 `/<vehicle>/odom`이 들어와야 표시된다.
- 현재 UDP status helper는 상태/CPU/battery/container만 보내므로 위치를 만들 수 없다.
- 다음 선택지:
  - UDP helper에 odom/pose 읽기를 추가하고 중앙 adapter가 `/fleet/peer_poses`를 발행한다.
  - 중앙 실행 환경에 `AIP_VEHICLE_TOPIC_ALIASES=aip2=scout_1,aip3=scout_2`를 적용해 `/scout_N/odom` 수신 여부를 재검증한다.
  - 팀 main 정식 방식에 맞춰 차량이 `/fleet/peer_poses` 또는 `/aipN/odom`을 직접 제공하게 한다.
- 2026-06-23 구현 완료:
  - UDP helper가 odom 후보 토픽을 읽어 pose를 payload에 포함하도록 확장했다.
  - 중앙 adapter가 pose payload를 `/fleet/peer_poses`로 발행하도록 확장했다.
- 남은 현장 절차:
  - `python3 scripts/manage_status_overlays.py start`로 차량의 `/tmp/status_aipN.py`를 재배포한다.
  - helper 재시작 후 웹 카드에 `pose_udp` 태그가 생기는지 확인한다.
  - 그래도 `pose:--`면 차량 내부 odom 후보 토픽(`/odom`, `/scout_N/odom`, `/aipN/odom`)이 실제로 있는지 SSH로 확인한다.

### P1. Discovery Server 운영 helper 정리

- `scripts/start_fastdds_ds.sh`를 추가해 WSL에서 Discovery Server를 안정적으로 재기동할 수 있게 했다.
- 추후 팀 main 기준 운영 방식이 Simple Discovery로 확정되면 이 helper는 선택사항으로 문서화하거나 제거한다.

### P1. 상태 overlay helper 정식 위치 결정

- `scripts/manage_status_overlays.py`를 추가해 `/tmp/status_aipN.py` 임시 프로세스를 일괄 시작/중지/확인할 수 있게 했다.
- 이 helper는 원본 main 폴더와 차량 소스 코드를 수정하지 않는다.
- 팀과 합의 후 다음 중 하나를 선택한다.
  - 시연용 helper로 유지.
  - systemd/user service로 영구화.
  - ROS heartbeat 정식 통합 완료 후 제거.

### P0. UDP heartbeat adapter 완전 정식화 여부 결정

- `udp_status_heartbeat_adapter.py`를 추가해 UDP helper 입력을 표준 `/aipN/heartbeat`로 변환한다.
- 현재 dashboard는 `/fleet/status` 경로로 3대 online을 받는다.
- dashboard direct UDP overlay는 기본 비활성화했다.
- 기본 경로는 `UDP 19051 -> /aipN/heartbeat -> /fleet/status -> dashboard`다.
- adapter 변환 로직 테스트를 추가했다.
  - `colcon test --packages-select aip_fleet_bringup`
  - `6 passed`
- 남은 선택지:
  - 이 adapter를 중앙 통합본의 공식 compatibility layer로 PR 제안.
  - 각 차량이 직접 `/aipN/heartbeat`를 발행하도록 차량 side adapter로 이동.
  - WSL DDS discovery 문제를 해결한 뒤 adapter 제거.

### P0. 팀원 리뷰/PR 준비

- `docs/PR_REVIEW_NOTES_KO.md` 추가 완료.
- `scripts/check_web_control_stack.sh` 추가 완료.
- 다음에 할 일:
  - 통합본 변경 파일 목록을 팀원에게 공유.
  - 원본 main 폴더를 수정하지 않았음을 설명.
  - adapter를 임시 compatibility layer로 유지할지, 차량 side adapter로 옮길지 팀원과 결정.
  - Git 저장소/브랜치가 준비되면 이 통합본 변경을 PR 형태로 정리.

### P1. 시연 안정화

- 매 시연 전:
  - `scripts/start_fastdds_ds.sh`
  - `run_central.sh`
  - `scripts/manage_status_overlays.py start`
  - `scripts/check_web_control_stack.sh`
- 자동 환경에서 helper 상태만 빠르게 확인해야 하면:
  - `scripts/manage_status_overlays.py status --no-prompt`
  - 비밀번호 환경변수가 없으면 `[SKIP]`으로 즉시 안내하고 종료한다.
- 웹에서:
  - `3 online`
  - `전체맵/저장맵`
  - `19050` direct overlay 비활성화
  - `udp_status_only` 태그가 보이는지 확인.
## 2026-06-23 추가 현재 상태 - 웹 pose 표시

- 완료:
  - dock marker/UI 제거.
  - 저장맵 기본 표시 유지: `전체맵/저장맵 · 201x167 0.05 m/cell`.
  - `aip2` pose 표시 복구: `(0.26, -0.30)`, `pose:fleet+cal+poseflip`, `pose_udp`.
  - `aip3` pose 표시 유지: `(-0.22, -0.39)`, `pose:fleet+cal`.
  - `scripts/manage_status_overlays.py` helper가 Discovery Server 환경에서 odom 매칭을 기다리도록 pose probe timeout을 늘림.
- 남음:
  - `aip1`은 현재 `pose:--`. main 차량에는 heartbeat/status helper만 확인되고 `/aip1/odom`, `/main/odom` 또는 명시적인 pose source가 아직 확인되지 않음.
  - `aip1` helper에는 generic `/odom`, `/pose`를 넣지 않는다. 다른 차량 odom을 main 위치로 오인할 수 있음.
  - team main 차량 SW/원본 main 폴더는 수정하지 않는다.
  - `aip1` 위치 표시를 위해 팀원이 main 주행/SLAM/odom stack을 실행했는지, 또는 실제 pose 토픽 이름이 무엇인지 확인해야 한다.
  - 자율 goal/patrol은 계속 보류. 현재는 수동 주행/상태/pose 표시 검증 범위로 제한한다.
