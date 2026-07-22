# Conversation / Decision Log

이 워크스페이스에서 이뤄진 **주요 결정과 그 이유** 의 누적 로그.
파일 자체의 상태는 git 에서 추적 가능하지만, "왜 이렇게 했는가" 는 따로 기록하지 않으면 소실됨.

각 에이전트 세션이 끝날 때마다 이 파일을 업데이트할 것.

---

## 2026-04-20 — 초기 스캐폴딩 및 문서화 (Windows 세션)

### 의사결정
- **RMW 선택**: `rmw_fastrtps_cpp` + Discovery Server.
  - 대안: multicast 기본, Zenoh (`rmw_zenoh_cpp`).
  - 이유: Wi-Fi 에서 multicast 불안정. Zenoh 는 네임스페이스/QoS 유지하며 스왑 가능한 구조로 설계해 옵션으로 남김.
- **ESP32 브릿지**: micro-ROS Agent (UDP4) on 중앙 PC.
  - 이유: ROS2 토픽 계약을 그대로 유지 → Scout 를 Pi/Jetson 으로 업그레이드해도 같은 네임스페이스 유지.
- **단일 ROS_DOMAIN_ID=42**. H9 에서 환경변수화 예정이지만 현재는 전 스택 하드코딩.
- **대시보드**: Foxglove Studio + foxglove-bridge + 커스텀 TS 패널 2 종 (E-Stop, Override).
  - 대안: rqt, Grafana+InfluxDB (뷰어용).
  - 이유: 3D·이미지·다차량 동시 뷰 + TypeScript 확장 API 의 유연성.
- **안전 우선순위 체인** (`twist_mux.yaml`): HW-EStop(100) > estop_lock(90) > central(80) > fleet_coord(50) > autonomy(10).
  - estop_lock 이 central 보다 높은 이유: supervisor 가 assert 한 lock 은 운영자 실수 override 로 풀리지 않아야 함.
- **시뮬 전략**: Gazebo 없이 numpy 레이캐스팅 기반 2D kinematic. sim ↔ prod drift 방지를 위해 `fleet_sim.launch.py` 가 `central.launch.py` 를 그대로 include.

### 사용자 피드백
- "현재는 저성능 ESP32 Scout 를 쓰지만 이후 **동급/고성능 차량 제작 가능성**이 있으니 확장성 반영" → `memory/feedback_future_proof_comm.md` 에 기록.
- 한국어 선호.

### 결과물
- 패키지 5 종 + 펌웨어 + docker/central + 문서(ANALYSIS, ARCHITECTURE).
- README 에 차량 SW 팀원용 인터페이스 계약 섹션 명시.

---

## 2026-04-20 (계속) — 구조 재분석 + 보안 감사 + 치명 취약점 대응

### 구조 재분석 주요 발견 (docs/ANALYSIS.md)
- **B1** (High): `fleet_sim.launch.py` 에서 `has_lidar=true` 차량 여러 대일 때 루프 변수 덮어쓰기로 **마지막 차량만 LiDAR 노드 확보**. 현재 설정(main 만 lidar) 에서는 표면화 안 됨.
- **B2** (Medium): supervisor 와일드카드 오버라이드가 supervisor 시작 시점의 차량 목록으로만 브로드캐스트.
- **B3** (High): ESP32 heartbeat `vehicle_id` 문자열 버퍼 처리 위험 (`micro_ros` 문자열 할당 헬퍼 미사용).
- **B4** (Medium): ESP32 펌웨어가 state 값으로 IDLE/MANUAL 미사용.
- **D1~D8**: 설계상 개선 포인트 — ROS2 콜백 순서 비결정성, TF 조회 로깅 없음, estop_lock 주석 부족 등.

### 보안 감사 (docs/SECURITY.md)
- 총 **36 건** (Critical 6, High 10, Medium 9, Low 9). 사용자가 이미 인지하던 2 건(WiFi PSK, InfluxDB 자격증명) 외 34 건 신규 발견.
- 신뢰 경계 없음 — "Wi-Fi 침투 = 전 토픽 publish/subscribe 권한" 이 현재 스택의 근본 문제.

### 사용자 지시에 따른 완화 조치 (기동 영향 최소화 원칙)
사용자가 "**시스템 구동에 지장 없는 부분은 문서로만 정리, 치명적 부분만 처리**" 라고 명시함.

즉시 적용:
- **C6** watchdog 히스테리시스 (`OFFLINE_CONFIRM_COUNT=3`) — 단발 Wi-Fi 지터로 인한 오 ESTOP 방지. `src/aip_fleet_supervisor/aip_fleet_supervisor/watchdog_node.py`.
- **H2** Wi-Fi PSK 를 `secrets.ini` (gitignored) 로 분리. `firmware/scout_microros/platformio.ini` 수정 + `secrets.ini.example` 제공.
- **H3** InfluxDB 자격증명을 `.env` 로 외부화. `${VAR:?msg}` 형태로 placeholder 남으면 **compose 기동 실패** — 의도된 동작. `docker/central/.env.example` 제공.
- **H10** Foxglove 패널 wildcard `"*"` 확인/debounce. `OverridePanel.tsx` 는 비상긴급 외 모든 명령 confirm, `EStopPanel.tsx` 는 E-Stop 자체는 반사 속도 우선이라 confirm 없이 debounce 만, **Clear E-Stop 은 confirm 필수** (해제가 더 위험).

신규 파일:
- `.gitignore` (secrets, build 산출물, PEM 키 등)

deferred (Phase 1/2/3 로드맵에 SECURITY.md 에 분류됨):
- SROS2 도입, 바인드 주소 제한, 공급망 digest 고정, 컨테이너 non-root, rosbag 암호화 등 32 건.

---

## 2026-04-20 (계속) — 개발환경 docker 스택 구축

### 사용자 환경 확인
- 호스트: Windows 11 + Docker Desktop (WSL2).
- 목표: **시뮬 전용 E2E 스모크 테스트**.
- Foxglove Studio 미설치 상태.

### 설계 결정
- **시뮬 전용 docker 이미지 분리**: `docker/sim/` 생성. `docker/central/` 는 host-net + 분리 서비스인데 Windows Docker Desktop 에서는 host net 신뢰성 떨어짐.
- **단일 컨테이너 전략**: supervisor + watchdog + foxglove-bridge + sim world/vehicle/lidar 전부 한 컨테이너 안에서 loopback DDS 로 통신. bridge network + `8765` 포트만 publish 로 Docker Desktop 에서도 무리 없이 동작.
- **src/ bind mount**: Python 노드 편집 시 rebuild 불필요 (`--symlink-install`). msg/srv 수정 시만 재빌드.
- **entrypoint.sh** 에서 `exec` 으로 PID 1 유지 → `docker stop` 신호가 ros2 launch 트리에 제대로 전파.

### 결과물
- `docker/sim/Dockerfile`, `docker/sim/entrypoint.sh`, `docker/sim/docker-compose.yml`
- `docs/SETUP_WINDOWS.md` — Windows 개발 루프 전체 절차 + Foxglove 설치 + 스모크 테스트 + 패널 빌드
- `docs/SETUP_UBUNTU.md` — Ubuntu 22.04 중앙 PC 설정 (Docker + ROS2 네이티브 + systemd 자동 기동 + UFW 방화벽 룰)

---

## 2026-04-20 (현재 세션) — Ubuntu 에이전트용 handoff 번들 생성

### 배경
사용자가 외부 Ubuntu PC 에서 Claude Code 로 이 워크스페이스 작업을 이어갈 예정.
새 에이전트는 이 대화 기록 · Windows `~/.claude/` 아래 메모리 · 승인 계획서에 접근 불가.

### 조치
- `docs/agent_context/approved_plan.md` — 원본 계획서 복사
- `docs/agent_context/memory/*.md` — Windows 메모리 5 개 + 인덱스(MEMORY.md) 복사
- `docs/HANDOFF.md` — 새 에이전트 진입점
- `docs/agent_context/conversation_log.md` (이 파일)
- `docs/agent_context/pending_tasks.md` — 미완 작업 로드맵
- `CLAUDE.md` — 워크스페이스 루트에 자동 로드되는 에이전트 지침

---

## 2026-04-22 — Ubuntu 환경 진단 및 개발환경 설정

### 배경
Windows에서 스캐폴딩된 워크스페이스를 Ubuntu 22.04 중앙 PC로 이전 후 첫 Ubuntu 세션.

### 환경 전수 검토 결과

**정상 확인:**
- ROS2 Humble `/opt/ros/humble/` 설치됨, `source` 후 동작 확인
- 모든 Python 패키지(aip_fleet_msgs/supervisor/sim/bringup) 빌드·import 성공
- `aip/sim:humble` Docker 이미지(1.16 GB) 이미 빌드돼 있음
- Docker v29.4.1 + Compose v5.1.3 설치됨
- `.env` 파일에 InfluxDB 자격증명 채워져 있음 (H3 mitigation 정상)
- sim 이미지 내부: foxglove-bridge, tf2-ros 포함 확인

**이슈 발견:**
- T1 버그: 코드 리뷰 결과 실제로는 이미 수정돼 있음 → pending_tasks.md에서 완료 처리
- PATH: ROS2 Humble은 `.bashrc`에 등록됐으나 워크스페이스(`install/`) source는 미등록
- git repo: 미초기화 상태 → `.gitignore`가 무효
- central Docker 이미지: 미pull 상태
- Node.js/npm: 미설치 → Foxglove 패널 빌드 불가
- `rosbag-recorder` 서비스: 컨테이너 시작마다 `apt-get install` 수행 (비효율, 추후 개선 검토)

### 조치 완료
1. `~/.bashrc`에 `source ~/aip_swarm_ws/install/setup.bash` 추가
2. `.gitignore`에 `.claude/` 항목 추가
3. `git init` + 브랜치 `main` 설정 + 초기 커밋 (69 files, 4368 insertions)
   - 시크릿 파일(`docker/central/.env`, `firmware/scout_microros/secrets.ini`) 커밋 차단 확인
4. `pending_tasks.md` — T1 완료 처리, 날짜 2026-04-22 로 갱신

### 미완료 (사용자 sudo 필요)
- Node.js 20.x 설치: `curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt-get install -y nodejs`
- (Node 설치 후) Foxglove 패널: `cd src/aip_fleet_foxglove_panels && npm install && npm run build`

---

## 2026-04-22 — B3 twist_mux 런치 통합

### 배경
전체 코드 리뷰(code_review_2026-04-22.md) 결과 twist_mux가 CLAUDE.md에 명시된
우선순위 체인(HW-EStop 100 > estop_lock 90 > central 80 > fleet_coord 50 > autonomy 10)에서
필수 구성 요소임에도 어느 런치 파일에도 존재하지 않음을 발견.
`estop_lock`이 twist_mux 없이는 실제 차량 모션을 차단하지 못함.

### 결정 및 구현

**신규 파일:**
- `src/aip_fleet_bringup/config/twist_mux_vehicle.yaml`
  - 상대 topic 이름 사용 (PushRosNamespace로 자동 네임스페이스 적용)
  - locks: `estop_lock` (priority 90)
  - topics: `override_cmd_vel`(80), `coord_cmd_vel`(50), `autonomy_cmd_vel`(10)
  - output: `cmd_vel_out` → remap → `cmd_vel`

**수정 파일:**
- `src/aip_fleet_bringup/launch/central.launch.py`
  - `OpaqueFunction` + `PushRosNamespace`로 scout 차량별 twist_mux 추가
  - main AGV는 제외 (타 팀 관할)
  - `with_twist_mux` 인자 추가 (기본 true; sim에서 false로 호출)
- `src/aip_fleet_sim/launch/fleet_sim.launch.py`
  - 차량 루프 내 GroupAction에 PushRosNamespace + twist_mux 추가 (main 포함 전 차량)
  - central include 시 `with_twist_mux:=false` 전달 (중복 방지)
- `src/aip_fleet_sim/package.xml`
  - `<exec_depend>twist_mux</exec_depend>` 추가

### 주요 설계 선택
- 시뮬에서 직접 드라이브 테스트 시 `/main/cmd_vel` 대신 `/main/autonomy_cmd_vel` 사용 필요
- sim_vehicle_node의 `override_cmd_vel` 직접 구독(fallback)은 유지 — twist_mux 없이 단독 실행 가능성 보존

### 결과
- 구문 검증 PASS (ast.parse + yaml.safe_load)
- pending_tasks.md: B3 완료 처리

---

## 2026-04-23 — B4·T8·T10·T11 완료

### B4. OverridePanel HOLD-to-drive 10 Hz 스트리밍

**문제**: `onMouseDown={publishManualFrame}` 이 마우스 누름 순간 1회만 발행.

**수정** (`src/aip_fleet_foxglove_panels/OverridePanel/src/OverridePanel.tsx`):
- `driveIntervalRef` (setInterval ID 보관) 추가.
- `startDriving`: 즉시 1회 발행 + `setInterval(100ms)` 시작.
- `stopDriving`: 인터벌 정리 → `doPublish(1, false)` (PAUSE). 인터벌이 없으면 PAUSE 발행하지 않아 중복 방지.
- 버튼에 `onMouseDown={startDriving}`, `onMouseUp={stopDriving}`, `onMouseLeave={stopDriving}` 연결.
- 언마운트 시 `useEffect` cleanup으로 인터벌 누수 방지.
- `npm run build` PASS.

### T8. FleetHeartbeat.msg / FleetStatus.msg bounded 선언

**문제**: `string[] active_behaviors`(unbounded 시퀀스)가 micro-ROS 정적 메모리 모델과 충돌.

**수정**:
- `FleetHeartbeat.msg`: `string vehicle_id` → `string<=32 vehicle_id`, `string[] active_behaviors` → `string<=64[<=8] active_behaviors`.
- `FleetStatus.msg`: `FleetHeartbeat[]` → `FleetHeartbeat[<=4]`, `string[]` → `string<=32[<=4] offline_vehicle_ids`.
- Python 코드 무수정 (bounded 시퀀스는 Python 레벨에서 동일하게 사용 가능).
- `colcon build` PASS (aip_fleet_msgs, supervisor, sim). 단위 테스트 23개 PASS.

### T10. 바인드 주소 제한 (C3/C4)

- `foxglove-bridge` command: `--address 0.0.0.0` → `--address 192.168.50.10`.
- `uros-agent`: micro XRCE-DDS v2.x에 bind-IP 플래그 없음. UFW 방화벽 레이어에서 처리하므로 주석으로 명시.

### T11. 공급망 digest 고정 (H4/H5)

- `docker-compose.yml`: `ros:humble-ros-base`, `microros/micro-ros-agent:humble`, `influxdb:2.7`, `rosbag-recorder` 이미지에 `@sha256:...` 고정.
- `ghcr.io/foxglove/ros-foxglove-bridge:humble`: ghcr.io 인증 필요로 자동 조회 불가 → TODO 주석 + 수동 pin 명령 남김.
- `platformio.ini`: `humble` 브랜치 → commit hash 고정 방법 주석 추가.
- `package-lock.json`: 이미 존재 확인, `.gitignore` 차단 없음.

### 결과
- 빌드/테스트 전부 PASS.
- pending_tasks.md: B4·T8·T10·T11 완료 처리.
- 잔여: T6(coordinator 설계), T7(Scout 위치추정), T9(SROS2), foxglove-bridge digest 수동 pin.

---

## 2026-04-23 (계속) — T6·T7·T9 완료

### T6. aip_fleet_coordinator 스켈레톤

신규 패키지 `src/aip_fleet_coordinator/`:
- `coordinator_node.py`: TF2 map-frame P-controller. `_pose_in_map()` 으로 leader·follower pose 조회. 베어링 방향으로 선속도 스케일(cos α). 10 Hz 제어 루프.
- `central.launch.py` `_make_coordinator_nodes()`: supervisor.yaml 차량 목록 기반으로 scout 당 노드 1개. offset_y 스태거(scout_1: 0 m, scout_2: +1 m, …).
- `with_coordinator:=true` 기본값 (비활성: `false`).

### T7. Scout 위치추정 전략

**결정**: 메인 AGV 카메라로 Scout ArUco 마커 인식 (옵션 a 변형).

- `scout_localizer_node.py`: cv2.aruco 4.5 API + cv_bridge + TF2. 마커 → 카메라 homogeneous matrix → TF buffer lookup(map→camera) 으로 map→scout_N/base_link TF 발행.
- `central.launch.py` `_make_localizer_nodes()`: static_transform_publisher(`main/base_link → main/camera_link`) + `scout_localizer_node`. `with_localizer:=false`(기본) → 하드웨어 준비 후 `true` 로 켬.
- 카메라 mount offset 파라미터: `camera_offset_x/y/z` (launch arg로 노출).

**UWB+IMU/엔코더 예산 비교** (사용자 요청):
- DWM1001 기준: 앵커 4개 + 태그 2개 + IMU + 엔코더 ≈ $230–330 (약 32–46만 원).
- 상용(Pozyx): ≈ $1,100+.

**하드웨어 to-do** (사용자):
1. 광각 USB 카메라 구매 ($20–40), `main/base_link → main/camera_link` 정적 TF offset 측정.
2. ArUco 마커 DICT_4X4_50 ID 1(scout_1), ID 2(scout_2) 인쇄·부착.
3. 카메라 캘리브레이션: `ros2 run camera_calibration cameracalibrator`.

### T9. SROS2 도입 (C1/C2/C5/H1/M2/L3/L4)

- `config/security/sros2_policy.xml`: 5개 노드 enclave 별 publish/subscribe whitelist. foxglove_bridge 는 subscribe-all + publish /fleet/override 만.
- `scripts/sros2_init.sh`: `ros2 security create_keystore|create_key|create_permission` 순차 실행. 이미 keystore 존재 시 재초기화 여부 확인.
- `.gitignore`: `config/security/keystore/` 차단, `sros2_policy.xml` 허용.
- `central.launch.py` `_make_security_env()`: `ROS_SECURITY_ENABLE/STRATEGY/KEYSTORE` 주입.

### 결과
- 빌드 PASS (aip_fleet_coordinator, aip_fleet_bringup). 단위 테스트 23개 PASS.
- 잔여: foxglove-bridge digest 수동 pin, Phase 2/3 보안, B2(와일드카드 차량 목록 저성능 이슈).

---

## 2026-04-23 (계속) — T7 Scout 위치추정 개발 일시 중단 및 정리

### 배경
메인 AGV에 4-DOF 서보 암 끝에 RGB+열화상 퓨전 센서 탑재 예정. 암의 동적 TF 문제로 위치추정 하드웨어 연동 일시 중단.

### 정리 내용

**scout_localizer_node.py 문서화:**
- MODE A (차체 고정 카메라) / MODE B (서보 암) 두 배포 모드 명시.
- MODE B 재개 조건 체크리스트 코드 주석으로 삽입.
- 노드 자체는 동적 TF 지원 완료 — 인프라만 갖추면 즉시 연동 가능.

**central.launch.py 확장:**
- `camera_mode` 인자 추가: `fixed`(기본) / `servo_arm`.
- `servo_arm` 모드: static_transform_publisher 생략, `camera_frame` 파라미터로 암 end-effector 프레임 지정.
- `fixed` 모드: 기존 static TF 발행 유지.

### 결정
- 소프트웨어 구현은 유지, 하드웨어 연동만 중단.
- 재개 시 별도 코드 수정 없이 암 드라이버 TF 확인 후 launch 파라미터만 변경하면 됨.

---

## 2026-04-23 (계속) — Phase 2 보안 완료 + 텔레메트리 브릿지 + 문서 현행화

### Phase 2 보안 (H6/H8/H9/M4/M5)

| Finding | 조치 |
|---|---|
| H6 컨테이너 root | 전 서비스 `cap_drop:[ALL]`. uros-agent·foxglove-bridge `user:65534:65534`. rosbag-recorder는 apt 의존으로 root 유지(TODO). |
| H8 ESP32 set_ns 미검증 | `ns_valid()`: 길이(1~31)·소문자 시작·허용 문자 검증. NVS 기록 거부. |
| H9 ROS_DOMAIN_ID 하드코딩 | `.env.example` 항목 추가. `docker-compose.yml` `${ROS_DOMAIN_ID:-42}`. `Dockerfile.central` ARG 추가. `platformio.ini` 주석. |
| M4 YAML 스키마 없음 | `_validate_world_yaml()` / `_validate_vehicles_yaml()` 추가. fail-fast ValueError. |
| M5 패널 입력 서버 미검증 | `sim_vehicle_node.py:88-89` 기존 클램핑 확인 → mitigated(기존)으로 기록. |

### 텔레메트리 브릿지 (§8)

- `src/aip_fleet_telemetry/` 패키지 신설.
- `telemetry_node.py`: `/fleet/status` → InfluxDB `fleet_vehicle` (battery_pct, cpu_load, state, online).
- `/fleet/override` → `fleet_override` measurement.
- `influxdb-client` 미설치 시 dry-run 모드. `with_telemetry:=true`로 활성화.
- 빌드 PASS.

### 기타 완료

- `docker/central/aip-central.service`: systemd unit 파일 독립화.
- `docs/ANALYSIS.md`: 섹션 1~9 현행화.
- `docs/SETUP_UBUNTU.md`: systemd 섹션을 파일 참조로 교체.
- 미커밋 파일(fleet_sim, package.xml, twist_mux_vehicle.yaml) 정리 커밋.

### 잔여 (낮은 우선순위)

- B2 와일드카드 차량 목록 동적 갱신
- aip_fleet_sim ray-cast 단위 테스트
- GitHub Actions CI
- Grafana 대시보드 JSON
- foxglove-bridge digest 수동 pin (`docker login ghcr.io` 필요)

---

## 2026-04-23 (계속) — 환경설정 스크립트 및 세션 마무리

### setup_ubuntu.sh 생성

**목표**: 다른 PC에서도 single-command 로 개발 환경 구성 가능.

**구현** (`scripts/setup_ubuntu.sh`):
- 11개 섹션: ROS2 Humble, Docker, Node.js, python 의존성, ros-packages, colcon 빌드, InfluxDB .env, UFW 방화벽, systemd unit, SROS2 초기화.
- 옵션 플래그: `--skip-ros2`, `--skip-docker`, `--skip-nodejs`, `--with-systemd`, `--with-ufw`, `--with-sros2`, `--dry-run`.
- 멱등성: `# >>> AIP Fleet Setup <<<` 마커로 .bashrc 중복 추가 방지. 기존 설치 확인 후 스킵.
- DRY_RUN: 실제 변경 없이 실행 내용 미리 확인 가능.

**sros2_init.sh 수정**: deprecated `create_key` → `create_enclave` (ROS2 Humble FutureWaning 제거).

### SROS2 키스토어 상태
- `config/security/keystore/` 이미 생성됨 (5개 enclave: supervisor, watchdog, foxglove_bridge, coordinator_scout_1/2).
- `with_security:=true` 로 launch 시 즉시 사용 가능.
- **잔여**: `ghcr.io/foxglove/ros-foxglove-bridge:humble` digest 수동 pin (`docker pull` → `docker inspect --format '{{index .RepoDigests 0}}'`).

### 현재 진행도 요약 (2026-04-23 기준)
- T1~T5, B3, B4, T6~T11(일부) 완료.
- T7: 소프트웨어 완료, 하드웨어(카메라) 연동 대기.
- Phase 2/3 보안: 운영 경험 후 진행 예정.
- B2(와일드카드 차량 목록 동적 갱신): 낮은 우선순위, 미착수.

---

## 2026-04-23 (계속) — 군집 개념 재정립 + 예산 피어 하드웨어 전략 문서화

### 사용자 설계 의도 명확화

사용자가 명시: **"플릿(fleet)이 아니라, 각 차량이 메인처럼 독립·유기적으로 활동하는 군집(swarm)이 목표."**
현재 scout 개념이 발생한 것은 메인 AGV급을 여러 대 동시 제작할 예산이 없기 때문. 역할 구분이 아님.

### 의사결정

| 결정 | 이유 |
|---|---|
| `scout_N` → **예산 제약 피어** 로 인식 변경 | 보조 차량이 아닌 동등 자율 피어, 사양 향상 목표 |
| `docs/VISION.md` 신규 생성 | 설계 철학(동등 피어 군집)을 코드베이스 단일 진실로 명시 |
| `docs/ARCHITECTURE.md` / `HANDOFF.md` / `SCOUT_LOCALIZATION_HW.md` 갱신 | VISION.md 참조 추가, scout=보조 관점 문구 제거 |
| `docs/SWARM_LOCALIZATION.md` 전면 재작성 | "scout가 어떻게 따라가는가" → "각 차량이 어떻게 독립 측위하는가" |

### 예산 피어 하드웨어 업그레이드 전략 (SWARM_LOCALIZATION.md)

**컴퓨팅 아키텍처 원칙:**
- ESP32-S3: 하드 실시간 안전 코프로세서 (모터 PWM, 인코더, 하드 E-Stop, WDT)
- RPi Zero 2W: ROS2 네이티브 인격체 (/odom 발행, UWB 융합, DDS Wi-Fi)
- UART 브릿지로 연결 → micro-ROS Agent 의존성 제거 가능

**단계별 경로:**

| 단계 | 추가 하드웨어 | 비용 | 달성 능력 |
|---|---|---|---|
| 0단계 (현재) | ESP32-S3만 | 0 | 카메라 의존, 시야 이탈=정지 |
| 1단계 | RPi Zero 2W + DWM3001C UWB + 엔코더×2 + ICM-42688 | ~9만 원 | 독립 위치 추정 (20-30cm) |
| 2단계 | VL53L5CX×4 ToF + 선택 OV2640 카메라 | +5만 원 | 장애물 자율 회피 |
| 3단계 | RPi 4B(Zero→교체) + YDLIDAR X2 | +22만 원 | Full SLAM, 완전 사양 피어 동등 |

**UWB V2V 측위 원리:**
- 메인 AGV의 SLAM 절대 위치를 앵커로 사용 (고정 인프라 불필요)
- 예산 피어는 메인과의 UWB ranging + IMU heading으로 위치 추정
- 3대 교차 ranging으로 상호 보정 가능

**소프트웨어 선행 체크리스트 (하드웨어 구매 전):**
- `/<ns>/odom` 발행 노드 (엔코더 + IMU dead reckoning)
- `uwb_localizer_node.py` (UWB ranging → map→base_link TF 발행)
- `coordinator_node.py` fallback: TF stale 시 odom 추정 연장
- `central.launch.py with_uwb_localizer:=true` 인자

### 잔여 소프트웨어 작업 (1단계 하드웨어 전 선행)

- `uwb_localizer_node.py` 스켈레톤 작성 (`aip_fleet_bringup` 또는 신규 패키지)
- `coordinator_node.py` TF-stale fallback 로직
- `central.launch.py with_uwb_localizer:=true` 인자 추가

---

## 2026-04-24 — Ignition Fortress 5-peer 시뮬레이션 기반 구축

### 결정: 시뮬레이터 채택

**Gazebo Ignition Fortress** 채택 (Gazebo Classic 대신).

이유: `ros2_control` 하드웨어 인터페이스 추상화.
- 시뮬: `ign_ros2_control/IgnitionSystem` 플러그인
- 실차: `aip_hardware/MainAGVHardware` 플러그인으로 교체
- diff_drive_controller YAML, coordinator_node, SLAM/Nav2 파라미터는 변경 없음

### 새로 생성된 패키지

| 패키지 | 역할 |
|---|---|
| `aip_main_description` | URDF/xacro (use_sim arg로 시뮬·실차 전환) |
| `aip_fleet_gazebo` | fleet_world.sdf, spawn_vehicle.launch.py, ign_fleet.launch.py |
| `aip_fleet_nav` | slam_toolbox / AMCL / Nav2 파라미터 + launch |

### 5-peer fleet 구성

- `peer_1` (리더): slam_toolbox → /map 생성
- `peer_2`~`peer_5` (팔로워): AMCL으로 /map 위에서 위치 추정
- V 포메이션: peer_1 중심, 2대씩 좌우 후방 배치
- 모든 차량 동일 URDF (namespace xacro arg만 다름) → VISION.md 동등 피어 원칙 반영

### central.launch.py 변경

- `leader_ns` arg 추가 (default: `main`, Gazebo sim에서는 `peer_1`)
- `supervisor_peers.yaml` 신규 (peer_1~5, 기존 supervisor.yaml 유지)
- coordinator의 V 포메이션 오프셋 계산 로직 일반화

### 빌드 결과

- 3개 신규 패키지 빌드 PASS
- URDF xacro 검증 PASS (namespace=peer_1/peer_2, use_sim:=false 실차 plugin 분기)
- 모든 launch 파일 AST syntax PASS

### 다음 단계

1. `sudo apt install ros-humble-ros-gz ros-humble-ign-ros2-control` 설치
2. `ros2 launch aip_fleet_gazebo ign_fleet.launch.py` Phase-1 스폰 테스트
3. 스폰 확인 후 `slam_leader.launch.py` + `nav_follower.launch.py` Phase-2 SLAM 테스트

---

## 2026-04-24 (계속) — Phase-1 실행 검증 완료

### 수정된 버그 (실행 중 발견)

| 파일 | 문제 | 수정 |
|------|------|------|
| `fleet_world.sdf` | 존재하지 않는 `ignition-gazebo-gpu-lidar-sensor-system` 플러그인 | 제거 (sensors-system이 처리) |
| `main_agv.urdf.xacro` | `type="gpu_lidar"` — GPU 없는 환경에서 실패 | `type="lidar"` (CPU ray-cast)로 변경 |
| `main_agv.urdf.xacro` | `gz_ros2_control::GazeboSimROS2ControlPlugin` 클래스 이름 불일치 | `ign_ros2_control::IgnROS2ControlPlugin` → `gz_ros2_control::GazeboSimROS2ControlPlugin` |
| `spawn_vehicle.launch.py` | controller YAML 최상위 키가 네임스페이스 없어 타입 미인식 | `/**:` 와일드카드로 변경 |
| `spawn_vehicle.launch.py` | spawner가 controller type 미인식 | `--controller-type` 플래그 추가 |
| `spawn_vehicle.launch.py` | `odom_frame_id`에 네임스페이스 중복 (`peer_1/peer_1/odom`) | `peer_1/odom` → `odom` (컨트롤러가 자동 prefix) |
| `cmd_relay.py` | `diff_drive_controller/cmd_vel` 발행 → subscriber 없음 | `cmd_vel_unstamped`로 변경 |
| `spawn_vehicle.launch.py` | `/peer_N/odom` 토픽 없음 | `topic_tools relay` 노드 추가 |
| `~/.bash_aliases` | `aip_topics`/`aip_odom`이 잘못된 odom 토픽 패턴 참조 | `diff_drive_controller/odom`으로 수정 |
| `~/.bash_aliases` | `aip_tf` alias → 함수 정의 오류 | 외부 스크립트(`~/.local/bin/aip_tf`)로 분리 |

### 차량 디자인 변경

- `main_agv.urdf.xacro`: `wheel_x = -0.080` 추가, 구동 바퀴를 후방으로 이동
- 지지 구조: 후방 좌우 구동 바퀴(x=-0.08) + 전방 캐스터(x=+0.10) → 삼각 지지, 기울어짐 없음

### Phase-1 최종 결과

| 항목 | 결과 |
|------|------|
| 5대 스폰 | ✅ |
| `diff_drive_controller` active | ✅ |
| `map → peer_N/odom → peer_N/base_link` × 5 TF 체인 | ✅ |
| teleop 이동 (peer_1) | ✅ |
| 차량 디자인 (후륜 + 전방 캐스터) | ✅ |

### 다음 단계

Phase-2: `aip_slam` (peer_1 SLAM) + `aip_nav peer_2..5` (팔로워 Nav2) 실행

---

## 2026-04-24 (계속) — Phase-1 실행 전 환경 확인 + alias 기반 실행 가이드 정립

### 배경

컨텍스트 압축 후 세션 재개. 이전 세션에서 구축한 Ignition Fortress 시뮬 스택을
실제로 실행하는 Phase-1 단계에 진입 직전 상태.

### 확인 완료

- 빌드 산출물(`install/aip_fleet_gazebo/`, `install/aip_fleet_nav/`, `install/aip_fleet_bringup/`) 모두 존재
- 필요 ROS2 패키지 전부 설치됨: `ros_gz_sim`, `ign_ros2_control`, `slam_toolbox`, `nav2_*`
- `~/.bash_aliases` 로드 확인 (14 aliases + 6 functions)

### Phase-1 실행 가이드 (확정)

**터미널 1**:
```bash
source ~/.bash_aliases && aip && aip_ign
```

**터미널 2** (약 10~15초 후):
```bash
aip_topics           # peer_1~5 /scan /odom /cmd_vel 존재 확인
aip_ctrl peer_1      # diff_drive_controller [active] 확인
aip_tf               # map → peer_N/odom → peer_N/base_link 체인 확인
```

**터미널 3** (컨트롤러 active 후):
```bash
aip_tele peer_1      # i=전진 ,=후진 j=좌 l=우 k=정지
aip_odom peer_1      # 위치 변화 확인
```

### 성공 기준

| 항목 | 기대 결과 |
|------|-----------|
| `aip_topics` | peer_1~5 각각 `/scan`, `/odom` 라인 표시 |
| `aip_ctrl peer_1` | `diff_drive_controller` → active |
| TF 트리 | `map → peer_N/odom → peer_N/base_link` 5개 체인 |
| teleop | i 키 입력 시 Ignition GUI에서 peer_1 이동 |

### 상태

Phase-1 실행 대기 중. 사용자가 터미널에서 직접 `aip_ign` 실행 후 결과 공유 예정.

---

## 2026-04-27 — Phase-2 SLAM + Nav2 + 코디네이터 통합 런치

### 배경

Phase-1(5대 스폰, TF 체인, teleop) 완료 확인 후 Phase-2 진입.

### 수정 내용

| 파일 | 변경 | 이유 |
|---|---|---|
| `nav_follower.launch.py` | `cmd_vel` remap `auto_cmd_vel` → `autonomy_cmd_vel` | twist_mux 설정(`twist_mux_vehicle.yaml`)과 불일치 버그 수정 |
| `ign_fleet.launch.py` | `with_static_tf` arg 추가 (기본 `true`) | Phase-2에서 slam_toolbox/AMCL이 동적 TF 발행 → static TF가 충돌하므로 비활성화 필요 |
| `fleet_phase2.launch.py` (신규) | Phase-2 통합 런치 | Ignition + twist_mux×5 + slam_leader + coordinator×4 + nav_follower×4 타이밍 조율 |
| `~/.bash_aliases` | `aip_phase2`, `aip_phase2_headless`, `aip_override` 추가 | Phase-2 원커맨드 실행, twist_mux 통과 teleop |

### 설계 결정

- **타이밍 체계**: `fleet_phase2.launch.py`는 TimerAction으로 순서 보장
  - t=0: Ignition + 5대 스폰
  - t=10s: twist_mux×5 (컨트롤러 활성화 후)
  - t=12s: slam_toolbox (peer_1)
  - t=15s: coordinator×4 (TF 미사용 시 zero-vel 안전 발행)
  - t=35s~: nav_follower×4 (SLAM 맵 생성 ~20s 대기, 1.5s 간격 스태거)

- **teleop 분리**: Phase-1은 `aip_tele` (→ `cmd_vel` 직접), Phase-2는 `aip_override` (→ `override_cmd_vel`, twist_mux priority 80 경유)

- **`ign_fleet.launch.py` 하위 호환**: `with_static_tf` 기본값 `true` — Phase-1 `aip_ign` 명령 변경 없음

### 검증

- 3개 런치 파일 Python AST 구문 PASS
- `colcon build --symlink-install` (aip_fleet_gazebo, aip_fleet_nav) PASS
- autonomy_cmd_vel 토픽 일치 확인

### 다음 단계

`aip_phase2` 실행 → t=35s 이후 AMCL 수렴 확인 → peer_1 `aip_override` 조종 시 V 포메이션 팔로잉 확인

---

## 2026-04-27 (계속) — 시뮬 차량간 위치·거리 공유 파이프라인 + UWB 소프트웨어

### 배경

실차 위치추정 모듈 미정 상태에서 시뮬 환경에 하드웨어 교체 가능한 파이프라인 구현.

### 구현 내용

#### 메시지 4종 (aip_fleet_msgs)

| 메시지 | 토픽 | 내용 |
|---|---|---|
| `PeerPose` / `PeerPoseArray` | `/fleet/peer_poses` | SLAM 산출 절대 위치 배열 |
| `PeerRange` / `PeerRangeArray` | `/fleet/peer_ranges` | 차량 쌍별 거리 + 노이즈 파라미터 |

#### sim_peer_sensing_node.py (신규, aip_fleet_gazebo)

- TF(`map→<ns>/base_link`) 기반 절대 위치 수집 → `/fleet/peer_poses` 발행
- 차량 쌍별 유클리드 거리 + Gaussian 노이즈(σ=0.05 m) → `/fleet/peer_ranges` 발행
- `max_range_m` 파라미터로 UWB FOV 시뮬레이션
- `fleet_phase2.launch.py` t=12s 슬롯에 통합

#### uwb_localizer_node.py (신규, aip_fleet_coordinator)

- 구독: `/fleet/peer_ranges` + `/fleet/peer_poses` + `/<ns>/odom`
- Gauss-Newton(최대 5회)으로 (x,y) 보정; θ는 odom 전용
- `stale_timeout_sec` 초과 시 TF 발행 중단
- `central.launch.py with_uwb_localizer:=true`로 실차 비-리더 차량에 일괄 launch

#### coordinator_node.py TF stale fallback (수정)

- `tf_stale_holdout_sec` 파라미터(기본 1.0s) 추가
- TF 미스 시 holdout 이내면 캐시된 pose 사용 → 순간 UWB 단절 시 급정지 방지

### 하드웨어 교체 경로

```
시뮬                              실차 UWB 붙을 때
───────────────────────────────────────────────────────
sim_peer_sensing_node            UWB 드라이버 (DWM3001C 등)
  TF 읽기 + Gaussian 노이즈       실제 TWR ranging
  → /fleet/peer_ranges           동일 토픽·메시지

TF lookup (SLAM)                 각 차량 SLAM → 중앙 집계
  → /fleet/peer_poses            동일 토픽·메시지
```

### 잔여 낮은 우선순위

- B2: 와일드카드 차량 목록 동적 갱신
- GitHub Actions CI
- Grafana 대시보드 JSON
- foxglove-bridge digest 수동 pin

---

## 2026-04-27 (계속) — 시뮬 3대 축소 + 협력 측위 + 고정 앵커 지원

### 결정: 시뮬 차량 수 5 → 3 (실차와 동일)

실제 제작 차량(메인 1대 + 예산 피어 2대)과 대응하도록 시뮬 fleet 축소.

| 파일 | 변경 |
|---|---|
| `ign_fleet.launch.py` | `_FLEET` 5대 → 3대 (peer_1/2/3) |
| `fleet_phase2.launch.py` | `_FOLLOWERS=['peer_2','peer_3']`, offsets 2개만 |
| `supervisor_peers.yaml` | `vehicle_ids: ["peer_1","peer_2","peer_3"]` |

### 결정: uwb_localizer_node.py 협력 측위 + 고정 앵커 지원으로 재작성

**동기**: peer_1만 SLAM, peer_2/3는 LiDAR 없는 예산 피어 → 절대 위치 참조가 peer_1 하나뿐이면 취약.

**계층별 가중치**:
- 고정 인프라 앵커 (`anchor_ids/x/y` 파라미터): w=1.0
- SLAM 피어 (`slam_peer_ids`): w=1.0
- 협력 추정 피어 (`estimated_peer_weight` 파라미터, 기본 0.5): 다른 uwb_localizer 추정값 활용

**알고리즘**: 가중 Gauss-Newton — `sqrt(w)`로 Jacobian·잔차 스케일링 → 표준 정규방정식

```python
sw = math.sqrt(w)
jx = sw * (x - ax) / d
jy = sw * (y - ay) / d
fr = sw * residual
# JᵀWJ·Δ = -JᵀW·f 풀기
```

**시나리오별 동작**:
- 앵커 0개: 순수 odom 추측항법 (dead reckoning)
- 앵커 1개: 거리-원 구속 (방사 방향 개선)
- 앵커 ≥2개: 완전한 2D 위치 결정

### V 포메이션 수식 버그 수정 (central.launch.py)

구버전: `i==0` 특례 분기 → peer_2가 (-1.5, 0) 타겟 (직선 후방)으로 스폰과 불일치.

신버전 대칭 쉐브론:
```python
row  = i // 2 + 1              # 1, 1, 2, 2, ...
side = 1 if i % 2 == 0 else -1  # +1=좌, -1=우
offset_x = -row * 1.5
offset_y  = side * row * 1.0
```

### sim_peer_sensing_node.py 고정 앵커 추가

`anchor_ids/anchor_x/anchor_y` 파라미터로 고정 비콘 시뮬 — 차량↔앵커 거리도 `/fleet/peer_ranges`에 포함.

### 커밋

`35ffc10 feat(sim): 시뮬 3대 축소 + 협력 측위 + 고정 앵커 지원`

### 다음 단계

- Phase-2 실행 검증 (`aip_phase2` → AMCL 수렴 → V 포메이션 확인)
- UWB 협력 측위 시뮬 검증 (`with_uwb_localizer:=true`, AMCL ground truth 비교)

---

## 2026-04-27 (계속) — Phase-2 런치 버그 수정

### 원인 1: `twist_mux` 미설치

`fleet_phase2.launch.py`가 t=14s에 `Node(package='twist_mux', ...)` 시작 시
`"package 'twist_mux' not found"` launch 예외 → 전체 cascade 종료.

**수정**: `sudo apt install ros-humble-twist-mux` (사용자 수동 설치)

### 원인 2: peer_1 diff_drive_controller FATAL 로드 실패

`[FATAL] peer_1.ddc_spawner_peer_1: Failed loading controller diff_drive_controller`

gz_ros2_control 플러그인이 state interface 생성 후 command interface를 생성하는 순서로 동작.
JSB(state interface만 사용)는 3s에도 성공하지만, DDC(command interface 필요)는 3s 타이밍에 실패.
peer_2/3는 0.8/1.6s 늦게 spawner가 실행되어 command interface가 준비된 후에 로드 성공.

**수정 (spawn_vehicle.launch.py)**:
- spawner 딜레이: `TimerAction(period=3.0)` → `TimerAction(period=6.0)`
- relay 딜레이: `TimerAction(period=4.0)` → `TimerAction(period=7.0)`
- `--controller-manager-timeout 30` 추가 (CM 서비스 대기 강화)

### 원인 3: aip_fleet_coordinator `setup.cfg` 누락

`ros2 run aip_fleet_coordinator coordinator_node` → `No executable found`

ament_python 패키지에서 `setup.cfg`가 없으면 console_scripts가
`install/lib/<pkg>/` 대신 `install/bin/`에 설치됨.
ros2 run은 `lib/<pkg>/` 경로만 탐색.

**수정**: `setup.cfg` 신규 생성
```ini
[develop]
script_dir=$base/lib/aip_fleet_coordinator
[install]
install_scripts=$base/lib/aip_fleet_coordinator
```

### 결과

**Gazebo 정상 시작 확인** (2026-04-27).
t=38s 이후 AMCL 수렴 및 V 포메이션 팔로잉 검증 필요.

---

## 2026-05-07 — AMCL 파라미터 수정 + CI 구성

### AMCL 파라미터 네임스페이스 버그 수정 (커밋 f98798c)

PushRosNamespace로 배치된 노드는 `/peer_N/amcl` 경로에 위치하는데,
파라미터 YAML의 최상위 키가 bare 이름(`amcl:`)이면 `/amcl`(루트 ns)에만 매칭돼
파라미터가 전혀 적용되지 않던 문제 수정.

| 파일 | 변경 |
|---|---|
| `amcl.yaml` | `amcl:` → `/${vehicle_id}/amcl:` |
| `slam_toolbox_online.yaml` | `slam_toolbox:` → `/${vehicle_id}/slam_toolbox:` |
| `nav2_params.yaml` | 모든 노드 FQDN, `voxel_layer` → `obstacle_layer` (Humble 호환), `lifecycle_manager_controller` 섹션 제거 |
| `nav_follower.launch.py` | peer_2/3 spawn 좌표 기준 `initial_pose_x/y/a` 주입 (파티클 (0,0) 집중 → 수렴 실패 방지) |
| `ros2_controllers_base.yaml` | `controller_manager:` → `/**:` (네임스페이스 무관 컨트롤러 타입 인식) |

### GitHub Actions CI 구성 (커밋 7a23ab7)

`.github/workflows/colcon.yml` 신규:
- 트리거: main push / PR
- 컨테이너: `ros:humble-ros-base`
- 빌드: `aip_fleet_msgs` 선행 → supervisor/coordinator/sim/telemetry/bringup
- 테스트: `aip_fleet_supervisor` 23개 pytest 단위 테스트
- 제외: aip_fleet_gazebo/nav/main_description(Ignition 의존), foxglove_panels(npm 의존)

### 잔여

- Phase-2 실행 검증 (AMCL 수렴 + V 포메이션) — 사용자 업무 해소 후
- UWB 협력 측위 시뮬 검증
- foxglove-bridge digest 수동 pin (`docker login ghcr.io` 필요)

---

## 2026-05-12 — odom_frame_fixer 구현 (peer_N/odom TF 수정)

### 문제
`diff_drive_controller`가 `enable_odom_tf: True`여도 TF를 `odom → base_link`(비네임스페이스)로 발행.
`slam_toolbox`와 AMCL은 `peer_N/odom → peer_N/base_link` TF를 요구 → TF 없음 → SLAM 순수 스캔매칭(드리프트), AMCL 위치추정 실패, V포메이션 불가.

### 원인 분석
- spawner `--param-file`로 `odom_frame_id: peer_1/odom` 전달해도 컨트롤러가 적용하지 않거나, `ros2_control` 플러그인 init 이후 파라미터가 무시됨.
- EKF는 `publish_tf: false`라 TF 미발행.

### 해결책: odom_frame_fixer.py
| 역할 | 동작 |
|---|---|
| 구독 | `/{vid}/diff_drive_controller/odom` (frame_id='odom') |
| 발행 | `/{vid}/diff_drive_controller/odom_corrected` (frame_id='{vid}/odom') |
| EKF | `odom0: odom_corrected` 구독 + `publish_tf: true` |
| diff_drive | `enable_odom_tf: False` (TF 충돌 방지) |

### 변경 파일
| 파일 | 변경 내용 |
|---|---|
| `scripts/odom_frame_fixer.py` | 신규: frame_id 교정 relay 노드 |
| `ekf_vehicle.yaml` | `odom0` → `odom_corrected`, `publish_tf: true` |
| `spawn_vehicle.launch.py` | `enable_odom_tf: False`, fixer t=7s에 추가 |
| `CMakeLists.txt` | `odom_frame_fixer.py` install 등록 |

### 예상 결과
- EKF가 `peer_N/odom → peer_N/base_link` TF 발행
- slam_toolbox odom prior 사용 → 드리프트 감소
- AMCL 위치추정 정상 → coordinator `coord_cmd_vel` 발행 → V포메이션 동작

### 잔여
- Phase-2 실행 후 `aip_check_follow peer_2` 로 5단계 체인 검증 필요

---

## 2026-05-18 — odom TF 분리 현상 진단 및 수정

### 배경

이전 세션에서 Phase-2 시뮬을 실행한 결과, peer_1 teleop 주행 후에도 peer_2/3의 AMCL 위치 추정 오차가 유지됨. AMCL 파라미터 조정(z_rand/sigma_hit/initial_cov 개선)을 적용했으나 오차가 해소되지 않음.

### 신규 증상 발견

사용자가 RViz 관찰을 통해 **각 peer의 odom TF 프레임이 차량 모델과 공간적으로 분리**되어 있음을 발견. odom 프레임 원점이 차량 스폰 위치가 아닌 맵 (0,0)에 고정되어 있음.

### 근본 원인

Ignition Fortress diff_drive_controller가 오도메트리 pose 필드에 **절대 월드 좌표**를 출력 (스폰 위치 (−1.5,+1.0)이 t=0 pose값). 기존 odom_frame_fixer는 frame_id만 교정하고 pose 값은 그대로 통과시켰으며, EKF의 `odom0_relative: false` 설정으로 인해 절대 좌표로 해석 → `peer_N/odom→base_link = (−1.5,+1.0)` at spawn → AMCL이 `map→peer_N/odom = (0,0)` 로 세팅 → odom 프레임이 맵 원점에 고정.

### 수정 내용

| 파일 | 변경 | 이유 |
|---|---|---|
| `ekf_vehicle.yaml` | `odom0_relative: false` → `odom0_relative: true` | EKF가 첫 메시지를 기준점으로 해석, 이후 상대 델타만 적분 |
| `scripts/odom_frame_fixer.py` | 초기 pose 영점화 추가 (일반 2D rigid transform) | 절대 좌표 → 상대 좌표 변환, EKF 수정과 이중 안전장치 |

### 정적 분석 결과 (테스트 불필요 확인 사항)

- `spawn_vehicle.launch.py` 타이밍: fixer(t=7s) → EKF(t=8s) 순서 정상
- `nav2_params.yaml`: DWB 파라미터 이상 없음, `robot_radius:0.18` (차량 외접원 ~0.16m 대비 적절)
- `fleet_phase2.launch.py`: 전체 실행 순서 이상 없음, twist_mux `use_sim_time:false` 의도적 설정 확인
- peer_4/5 미사용 (3대 시뮬 현재 설계 범위): 추가 불필요

### 잔여 작업 (사용자 테스트 필요)

1. 시뮬 재시작 후 RViz에서 odom 프레임이 차량과 일치하는지 확인
2. peer_1 teleop 후 peer_2/3 AMCL 수렴 및 V 포메이션 팔로잉 검증
3. `with_uwb:=true` 모드에서 UWB 추정 오차 < 0.30 m 확인

## 2026-05-12 (계속) — AMCL 맵 구독 버그 수정 + set_initial_pose + 두-단계 제어기 + AMCL 정확도 개선

### 문제 1: AMCL이 `/peer_N/map` 구독

`PushRosNamespace("peer_2")` 안에서 상대 토픽 `map`을 구독하면
ROS2 네임스페이스 규칙에 의해 `/peer_2/map`으로 변환됨.
peer_1 slam_toolbox는 `/map`(절대)으로 발행 → 구독자 불일치 → AMCL에 맵 전달 안 됨 → TF 미발행.

**수정** (`nav_follower.launch.py`): `remappings=[('map', '/map')]` 명시

### 문제 2: AMCL `set_initial_pose` 누락

`initial_pose_x/y/a` 파라미터는 `set_initial_pose: true`가 설정될 때만 적용됨.
없으면 `initial_pose_is_known_ = false` → `laserReceived()` 즉시 리턴 → TF 영구 미발행.
AMCL 노드는 active 상태였지만 TF를 발행하지 않는 증상.

**수정** (`nav_follower.launch.py` + `amcl.yaml`): `set_initial_pose: true` 추가

### 문제 3: 코디네이터 정지 버그 (추종 못 도달)

기존 제어식 `v = kp_lin * dist * cos(alpha)`:
alpha가 크면 cos(alpha)→0 → 선속도 소멸 → 리더가 이동하면 새 타겟 발생 → 반복 → 도달 불가.

**수정** (`coordinator_node.py`): 두-단계(two-phase) 제어기
- |alpha| > 1.05 rad (~60°): 제자리 회전만, 선속도=0
- |alpha| ≤ 1.05 rad: 전진 `v = kp_lin * dist` (cos 감쇠 없음)
- `goal_tolerance`: 0.05 → 0.15 m (dead-band 확장, 진동 방지)

### 문제 4: AMCL 위치 추정 부정확 (RViz)

- `max_beams: 60` — 360점 LiDAR에서 너무 적음
- `laser_likelihood_max_dist: 2.0` — 매칭 필드가 너무 넓어 모호한 수렴
- `z_hit`/`z_rand` 동등 가중치

**수정** (`amcl.yaml`): 시뮬 환경 최적화 파라미터 튜닝
```yaml
min_particles: 1000 / max_particles: 3000
update_min_d: 0.05 / update_min_a: 0.10
max_beams: 180
laser_likelihood_max_dist: 0.5
z_hit: 0.7 / z_rand: 0.2 / sigma_hit: 0.1
alpha1~4: 0.1 / alpha5: 0.05
```

### 검증 결과

| 항목 | 결과 |
|---|---|
| peer_2 AMCL 수렴 + TF 발행 | ✅ |
| peer_2 V포메이션 추종 | ✅ |
| peer_3 V포메이션 추종 | ✅ (Gazebo 재실행 후) |
| 코디네이터 목표 좌표 도달 | ✅ (두-단계 제어기) |
| AMCL 위치 추정 정확도 | 향상됨 (파라미터 튜닝) |

### 결정: 동적 장애물 필터링 미구현

peer_1 LiDAR 스캔에 peer_2/3 차체가 정적 장애물로 매핑되는 문제 논의.
`scan_dynamic_filter.py` 노드로 필터링 가능하나, 현재 시나리오가 **사전 매핑된 환경 순찰** 방식이므로 불필요.
사용자 결정: "변경 없이 이대로 진행할게."

### 잔여

- UWB 협력 측위 시뮬 검증 (`with_uwb_localizer:=true`)
- foxglove-bridge digest 수동 pin

---

## 2026-05-13 — UWB 시뮬 검증 인프라 + 독자 제어 전환 경로 검토

### UWB shadow 모드 구현

AMCL과 UWB localizer가 동일 TF(`map → peer_N/base_link`)를 경쟁 발행하는 충돌 문제를 해결.
**shadow 모드**: UWB localizer가 `peer_N/base_link_uwb_est` 프레임으로 발행 → AMCL과 공존, 오차 비교 가능.

| 파일 | 변경 |
|---|---|
| `uwb_localizer_node.py` | `child_frame_suffix` 파라미터 추가 (기본 `''`, shadow 모드 `'_uwb_est'`) |
| `fleet_phase2.launch.py` | `with_uwb` 인자 추가. t=20s에 uwb_localizer×2 (IfCondition) |
| `uwb_accuracy_check.py` | 신규: AMCL vs UWB 위치 오차 실시간 출력 (10Hz) |
| `CMakeLists.txt` | `uwb_accuracy_check.py` install 등록 |
| `~/.bash_aliases` | `aip_phase2_uwb`, `aip_uwb_compare` 추가 |

#### 검증 절차
```
터미널 1: aip_phase2_uwb   → AMCL + UWB shadow 동시 기동
터미널 2: aip_uwb_compare  → AMCL vs UWB 오차 수치 출력
터미널 3: aip_rviz         → peer_N/base_link vs peer_N/base_link_uwb_est 시각 비교
```
허용 오차 기준: 정상 주행 시 < 0.3 m (UWB σ=0.05 m, Gauss-Newton 5회)

### 독자적 제어·조율 시스템 전환 경로

현재 아키텍처(중앙 코디네이터 → 속도 명령)에서 분산 군집으로의 4단계 전환 경로 설계:

| Stage | 핵심 변경 | 효과 |
|---|---|---|
| 1 (독립 항법) | coordinator가 Twist 대신 Nav2 `NavigateToPose` action 호출 | 오프셋 추종 → 자율 목표 도달, 장애물 우회 자동화 |
| 2 (임무 할당) | `task_allocator_node`: 웨이포인트 목록 → 최근접 차량 배분 | 중앙 태스크 큐, 완료 후 자동 재할당 |
| 3 (분산 조율) | 중앙 코디네이터 제거, 경매 기반 `/fleet/bid_msg` 토픽 | 리더 없는 완전 분산 |
| 4 (군집 행동) | BehaviorTree.CPP + Patrol/Search/Rendezvous 행동 모듈 | 완전 자율 군집 |

**첫 단계 권고**: `coordinator_node.py` Twist → Nav2 action (~60줄 변경). 가장 적은 변경으로 가장 큰 기능 도약.
**현재 재사용 가능**: uwb_localizer, /fleet/peer_poses, twist_mux, DWB local planner, TF 체인 모두 유지.

---

## 2026-05-14 — UWB 시뮬 검증 실행 + 버그 수정 + 알고리즘 개선

### 검증 실행 결과

```
peer_2: AMCL TF missing (uwb_est at (-1.5, 1.0))  ← AMCL 기동 실패
peer_3: AMCL(-0.007,-1.002)  UWB(-0.24~-0.36, -0.25~-0.47)  err=0.6~0.87m → 0.242m
```

### 발견 및 수정 (4건)

| 파일 | 수정 내용 |
|---|---|
| `scripts/uwb_accuracy_check.py`, `odom_frame_fixer.py` | 실행 권한 누락(chmod +x) |
| `uwb_localizer_node.py` | `initial_x/y/yaw` 파라미터 추가 — odom(0,0) 초기화 시 d=0 특이점 방지 |
| `fleet_phase2.launch.py` | `_SPAWN_POS` 딕셔너리로 스폰 좌표 → `initial_x/y` 주입 |
| `sim_peer_sensing_node.py` | `_lookup()` UWB TF fallback 추가 — AMCL 없어도 `base_link_uwb_est` 로 range 계산 가능 |
| `uwb_localizer_node.py` | `d_min_aoa_m` 파라미터(기본 0.30m) — 근거리 AoA Jacobian 발산 방지 |
| `uwb_localizer_node.py` | `uwb_trigger_dist_m` 파라미터(기본 0.0=항상 보정) — odom drift 누산 후 보정 (실차용) |

### 핵심 설계 결정

**UWB 보정이 odom보다 나빠지는 조건** (이번 테스트에서 발생):
- 앵커 1개만 유효 (peer_2 AMCL 불능 → sim_peer_sensing range 없음)
- 단거리 이동 → odom drift ≈ 0, UWB σ=5cm가 더 큰 노이즈

**해결 방향**: `uwb_trigger_dist_m > 0` 설정 시 odom 누적 이동거리 초과 후에만 UWB 보정 실행.
실차에서는 0.5m 권장. 시뮬 기본값 0.0 유지 (하위 호환).

**UWB → AMCL 영향 없음 확인**: shadow 모드 TF 프레임 분리(`base_link` vs `base_link_uwb_est`)로 네비게이션 파이프라인과 완전 격리.

### 전 차량 LiDAR 시나리오에서의 UWB 가치 평가

- localization 정확도 향상 효과 없음 (SLAM 2~5cm > UWB 10~15cm)
- 앵커 용도 전환: 코드 이미 지원(`anchor_ids/x/y`), 장거리 drift 보정에만 유효
- 예산 피어(LiDAR 없는 차량) 혼재 시나리오가 UWB의 적정 용도

---

## 2026-05-14 (2) — RViz/Ignition 위치 오프셋 원인 분석 및 AMCL 튜닝

### 조사 범위

전 파일 검토: `fleet_phase2.launch.py`, `ign_fleet.launch.py`, `nav_follower.launch.py`,
`amcl.yaml`, `slam_toolbox_online.yaml`, `spawn_vehicle.launch.py`, `ekf_vehicle.yaml`,
`odom_frame_fixer.py`, `main_agv.urdf.xacro`

### 확인된 정상 항목 (버그 없음)

- 포메이션 오프셋 수식 (`coordinator_node.py` 154~156): 올바른 회전 행렬 ✓
- AMCL initial_pose: `nav_follower.launch.py`에서 스폰 좌표와 일치 ✓
- EKF: `odom0_relative:false` + odom(0,0,0) 시작 + AMCL이 `map→odom=(−1.5,+1.0)` 설정 → chain 올바름 ✓
- 프레임 ID: 전부 네임스페이스 포함 (`peer_N/odom`, `peer_N/base_link`) ✓
- 스캔 토픽: `/peer_N/scan` — URDF bridge `scan_gz→scan` 리맵핑 ✓

### 근본 원인: SLAM 맵 피어 바디 오염

```
t=  2.8s  peer_2 스폰 (Ignition에 물리적 존재)
t=  3.6s  peer_3 스폰
t= 16.0s  SLAM 시작 → peer_1 LiDAR가 peer_2/3 바디 스캔 시작
t= 55.0s  AMCL 시작 (39초간 peer_2/3 바디가 맵에 정적 장애물로 기록됨)
```

`likelihood_field` 모델 + `laser_likelihood_max_dist: 0.5m` 조건에서:
- 이동 시작 후 peer_2 LiDAR가 peer_3을 새 위치에서 관측
- 맵에는 peer_3 바디가 구 위치에 고정 기록 → 스캔-맵 불일치
- AMCL 파티클이 불일치를 설명하는 약간 오프셋된 위치로 수렴 → 계통적 오프셋

### 적용 수정

| 파일 | 변경 |
|---|---|
| `amcl.yaml` | `z_hit: 0.7→0.6`, `z_rand: 0.2→0.3`, `sigma_hit: 0.1m→0.15m` — 동적 장애물 내성 향상 |
| `nav_follower.launch.py` | `initial_cov_xx/yy: 0.05`, `initial_cov_aa: 0.025` 추가 — 스폰 좌표 확실 시 파티클 분산 최소화 |

### 장기 근본 해결책 (미적용)

peer_2/3를 SLAM 맵에 포함시키지 않는 방법:
1. **지연 스폰**: peer_2/3을 t=52s 이후에 스폰 (ign_fleet.launch.py 수정 필요)
2. **scan_filter 노드**: `laser_filters` 패키지로 SLAM 입력 스캔에서 근거리(<0.8m) 레이 제거
3. **Ignition visibility_flags**: URDF에서 차량 충돌 geometry를 LiDAR 비감지 그룹으로 설정

---

## 2026-05-20 — 자율 순찰 개선 + 프로젝트 종합 문서 작성

### 결정 및 구현

| 항목 | 결정 내용 |
|---|---|
| peer_1 탐색 우선 아키텍처 | peer_1이 전체 맵 탐색(loop=False) 완료 후 peer_2/3 시작 (t=155s/163s) |
| leader_nav.launch.py 신규 | peer_1 전용 Nav2 (AMCL 없음) — slam_toolbox TF 사용 |
| _NAV_START 조정 | peer_2: 55→155s, peer_3: 63→163s (peer_1 탐색 완주 대기) |
| patrol start_delay | peer_2/3: 15→40s (AMCL 수렴 대기) |
| base_footprint TF 추가 | spawn_vehicle.launch.py에 identity TF 발행 (RViz 경고 해결) |
| nav2_full.yaml 수정 | progress_checker: 0.5→0.3m/10→20s, DWB transform_tolerance: 0.5→1.0s |
| 종합 문서 작성 | `docs/PROJECT_OVERVIEW.md` — 피드백 요청용 전체 설계·구현·한계 기록 |

---

## 2026-05-21 — 열화상 인식 파이프라인 시뮬 통합

### 구현 내용

| 파일 | 변경 |
|---|---|
| `aip_fleet_perception/patrol_monitor_node.py` | TF 기반 `map_position` 추정 추가: `_estimate_map_position()` — FOV 각도 + 차량 yaw + 추정 거리로 열원 위치 ray projection |
| `aip_fleet_perception/alert_visualizer_node.py` | 신규: `/fleet/alerts` → RViz `MarkerArray` 변환. WARN=주황/HIGH=빨강 구체 + 텍스트 레이블, 수명 10초 |
| `aip_fleet_autonomous/fleet_autonomous.launch.py` | `with_thermal:=true` 인자 추가: t=16s에 scenario_manager + sim_thermal, t=22s에 patrol_monitor×3 + alert_visualizer 시작 |
| `aip_fleet_perception/package.xml` | `tf2_ros`, `visualization_msgs` 의존성 추가 |
| `aip_fleet_autonomous/package.xml` | `aip_fleet_perception` exec_depend 추가 |
| `aip_fleet_perception/setup.py` | `alert_visualizer_node` entry_point 등록 |

### 열화상 파이프라인 전체 흐름

```
scenario_manager_node.py  — /sim/set_scenario → /sim/heat_sources (2 Hz)
        ↓
sim_thermal_node.py       — TF + 열원 목록 → /<vid>/thermal_raw (8 Hz)
        ↓
patrol_monitor_node.py    — 임계값 필터 + TF map_position → /fleet/alerts
        ↓
alert_visualizer_node.py  — /fleet/alerts → /fleet/alert_markers (RViz)
```

### 빌드 필요
`aip_fleet_perception`은 `setup.py` 기반이므로 새 entry_point 등록 후 재빌드 필요:
```bash
source aip_env.sh && colcon build --packages-select aip_fleet_perception aip_fleet_autonomous --symlink-install
```

### 사용 방법
```bash
# 전체 파이프라인 실행
ros2 launch aip_fleet_autonomous fleet_autonomous.launch.py \
    with_patrol:=true with_thermal:=true

# 시나리오 전환 (실행 중에 다른 터미널에서)
ros2 topic pub --once /sim/set_scenario std_msgs/String '{data: FIRE}'
ros2 topic pub --once /sim/set_scenario std_msgs/String '{data: NORMAL}'
```

RViz에서 `/fleet/alert_markers` 토픽 추가 → MarkerArray 형식으로 열원 위치 시각화.

### 문서 내용 (`docs/PROJECT_OVERVIEW.md`)

- 프로젝트 개요 (컨셉, 시나리오, 개발 단계)
- 차량 하드웨어 스펙 (FIT0186, 바퀴 치수, 센서)
- 시스템 환경 (네트워크, OS, ROS2 패키지 구성)
- 소프트웨어 스택 상세 (EKF, Nav2, SLAM, coordinator, UWB, twist_mux)
- 브링업 타임라인 (fleet_autonomous.launch.py 전체 순서)
- 순찰 경로 설계 (peer_1/2/3 waypoint 설명)
- 피드백 요청 사항 10개 (F-01~F-10)


---

## 2026-05-21 — MPPI 통합 + 열화상 파이프라인 최종 사전 비행 검사

### 수행한 검증

| 검사 항목 | 결과 |
|---|---|
| MPPI 설정 10항목 (plugin, batch_size, time_steps, critics 등) | ALL PASS |
| patrol_monitor `_estimate_map_position` 수식 단위 테스트 11개 | ALL PASS |
| alert_visualizer_node 마커 로직 검증 10항목 | PASS (DELETEALL 추가 후) |
| 열화상 파이프라인 파일 통합 검증 21항목 | ALL PASS |
| 전체 사전 비행 검사 14항목 (SO 파일, yaml, 파일 존재, 의존성) | ALL PASS |
| `aip_fleet_perception`, `aip_fleet_autonomous` 재빌드 | SUCCESS |

### 결정

- `alert_visualizer_node.py`에 시작 시 `DELETEALL` 마커 발행 추가 (0.5s 타이머, 1회 실행): RViz 이전 세션 잔여 마커 정리
- MPPI 총 샘플: 2000×56=112,000 (DWB 대비 280×), 예측 지평선 2.8초
- `CostCritic.consider_footprint=true` → 실제 footprint 대 lethal cell 비교 (doorway 핵심)
- `PathAlignCritic.cost_weight=14.0` → 문 입장 각도 강제

### 다음 단계 (사용자 직접 실행 필요 — display 필요)

```bash
# 전체 자율 순찰 + 열화상 (Ignition Fortress GUI 필요)
source aip_env.sh
ros2 launch aip_fleet_autonomous fleet_autonomous.launch.py \
    with_patrol:=true with_thermal:=true

# 시나리오 전환 (별도 터미널)
ros2 topic pub --once /sim/set_scenario std_msgs/String '{data: FIRE}'

# 모니터링
ros2 topic echo /fleet/alerts
```

---

## 2026-05-21 — FleetDashboard Foxglove 패널 구현

### 결정
- **AIP Fleet Dashboard** 패널 신규 추가 (`FleetDashboard/src/FleetDashboard.tsx`)
- 기존 EStopPanel / OverridePanel 에 이어 세 번째 Foxglove 패널
- 빌드·패키징 PASS → `aip.fleet-foxglove-panels-0.1.0.foxe` 갱신

### 구현 내용
| 섹션 | 구독 토픽 | 기능 |
|---|---|---|
| 차량 상태 카드 | `/fleet/status` | peer_1/2/3 상태배지·배터리·CPU·행동태그·인라인 경보 |
| 차량별 제어 | `/fleet/override` (발행) | PAUSE/RESUME/CLEAR/ESTOP 버튼 |
| 전체 ESTOP | `/fleet/override` (발행) | confirm 후 `vehicle_id="*"` ESTOP |
| 시나리오 제어 | `/sim/active_scenario` 구독, `/sim/set_scenario` 발행 | 6종 시나리오 버튼, 활성 시나리오 강조 |
| 탐색 커버리지 | `/fleet/coverage_pct`, `/fleet/vehicle_coverage_pct` | 전체 % 바 + 차량별 % 칩 |
| 열화상 경보 | `/{peer_N}/perception_alert` | WARN/HIGH 경보 목록, 온도·confidence·좌표 |

### 설치 방법
```
Foxglove Studio → 확장 관리 → .foxe 파일 설치
→ src/aip_fleet_foxglove_panels/aip.fleet-foxglove-panels-0.1.0.foxe
패널 추가 → "AIP Fleet Dashboard"
```

RViz → `/fleet/alert_markers` (MarkerArray) 추가 → 열원 위치 주황/빨강 구체로 시각화.

---

## 2026-05-22 — gz_ros2_control 첫 번째 엔티티 버그 수정 (3대 스폰 정상화)

### 배경
`aip_auto_patrol` 실행 시 peer_1 CM이 시작되지 않아 차량이 2대만 제어 가능한 상태였음. 이전 세션에서 ros2_control 2.54.0 자동 활성화 버그는 수정됐으나, peer_1 CM 시작 실패 문제가 미해결 상태였음.

### 근본 원인 분석

**gz_ros2_control-system 0.7.19 싱글톤 처리 특성:**
gz_ros2_control-system 플러그인은 Ignition 프로세스 내에서 엔티티를 **순차 처리**한다. 첫 번째 엔티티의 `Configure()` 완료 전까지 이후 엔티티(peer_1/2/3)의 `Configure()`가 실행되지 않는다.

이전 테스트에서 peer_1이 첫 번째 엔티티로 처리될 때:
- rclcpp 초기화 경쟁 조건 또는 좀비 CM 노드 충돌로 인해 노드 생성 실패
- `Configure()` 빠르게 종료(fast fail) → peer_2/3는 두 번째·세 번째 엔티티로 정상 처리
- 결과: peer_1 CM 없음, peer_2/3 CM 있음

### 해결책: 워밍업 모델 (gz_ros2_control 첫 번째 엔티티 흡수)

`ign_fleet.launch.py`에 최소 워밍업 모델을 추가:
- t=1.0s: `gz_warmup` RSP (`/gz_warmup/robot_state_publisher`) + `gz_ctrl_warmup` 모델 스폰
- t=3.5s: peer_1 스폰 (기존 2.0s → 1.5s 지연 추가)

워밍업 모델이 첫 번째 엔티티로 처리됨 → `gz_warmup.gz_ros2_control: System Successfully configured!` 완료 → peer_1이 두 번째 엔티티로 처리 → CM 정상 시작.

**핵심: 워밍업 RSP 네임스페이스 필수**
- 워밍업 플러그인이 `/gz_warmup/robot_state_publisher`를 찾음
- RSP가 `gz_warmup` 네임스페이스 없이 `/robot_state_publisher`에 있으면 → RSP 대기 루프가 영구 블록 → peer_1/2/3 Configure()가 실행 불가
- RSP에 `namespace='gz_warmup'` 명시적 설정으로 해결

### 변경 파일

**`src/aip_fleet_gazebo/launch/ign_fleet.launch.py`:**
- `desc_share`, `ctrl_yaml` 변수 추가
- 워밍업 URDF 인라인 생성 (warmup_joint 포함, gz_ros2_control/GazeboSimSystem 하드웨어)
- `warmup_rsp`: `namespace='gz_warmup'`, t=1.0s 실행
- `warmup_spawn`: `-topic /gz_warmup/robot_description`, (-45,-45) 위치
- 차량 스폰 딜레이: `2.0 + idx*0.8` → `3.5 + idx*0.8` (peer_1=3.5s, peer_2=4.3s, peer_3=5.1s)

### 검증 결과 (2026-05-22 실행)

```
gz_warmup:  System Successfully configured! ✓
peer_1:     System Successfully configured! ✓
peer_2:     System Successfully configured! ✓
peer_3:     System Successfully configured! ✓

/peer_1/controller_manager, /peer_2/controller_manager, /peer_3/controller_manager ← 모두 활성
joint_state_broadcaster: active (peer_1/2/3)
diff_drive_controller:   active (peer_1/2/3)
/peer_N/{cmd_vel, odom, joint_states, scan, odometry/filtered} ← 모두 발행 중
```

### 재실행 주의사항
이전 시뮬 프로세스가 남아있으면 좀비 CM 노드가 새 CM 노드 이름과 충돌할 수 있음. 재실행 전 정리:
```bash
pkill -9 -f "controller_manager" || true
pkill -9 -f "robot_state_publisher" || true
```

---

## 2026-05-22 — SLAM 오염·TF 루프·AMCL 수렴 버그 수정

### 의사결정

**TF 루프 제거**
- `spawn_vehicle.launch.py`의 `base_footprint_tf` static_transform_publisher 제거.
- 이유: URDF `base_joint`(parent=`base_footprint`, child=`base_link`)를 RSP가 이미 발행. 역방향 static TF가 루프 형성 → `tf tree is invalid` 오류로 peer_3 Nav2 전체 불능.

**follower_spawn_delay 도입**
- `ign_fleet.launch.py`: `follower_spawn_delay` LaunchArg(OpaqueFunction 처리) 추가.
- `fleet_autonomous.launch.py`: `follower_spawn_delay='181'` 전달 → peer_2/3 스폰 t≈185s.
- 이유: peer_2/3가 t≈4s에 스폰되면 peer_1 SLAM이 차체를 150초간 스캔 → `P(occupied)` 최대치 수렴 → 맵에 영구 벽 기록 → `Starting point in lethal space` 오류.

**map_update_interval 상향 (5.0 → 30.0)**
- `slam_toolbox_online.yaml` 수정.
- 이유: AMCL은 새 맵 수신마다 `createLaserObject()` 호출. 5Hz 맵 업데이트는 파티클이 수렴하기 전에 likelihood field를 반복 리셋.

**_NAV_START 재조정**
- `peer_2: 155 → 200`, `peer_3: 163 → 210`.
- 이유: 팔로워 스폰(185s) + CM·EKF 준비 여유(15~24s) 확보.

### 결과

```
peer_2 AMCL 수렴 성공 ✅
peer_3 AMCL 수렴 성공 ✅  (타이밍 조정 후)
TF 루프 오류 해소 ✅
lethal space 오류 해소 ✅ (follower_spawn_delay 적용 후)
```

---

## 2026-05-22 — 이벤트 기반 자율 탐색 아키텍처

### 의사결정

**타이머 기반 → 이벤트 기반 팔로워 시작**
- 기존: `_NAV_START['peer_2']=200.0, 'peer_3'=210.0` 고정 타이머.
- 신규: `map_readiness_node`가 `/map` 커버리지 모니터링 → `/fleet/map_ready` 발행 → `follower_trigger_node`가 팔로워 Nav2 기동.
- 이유: 맵 크기·순찰 경로 변경 시마다 타이머 수동 조정 필요 → 유지보수 부담 및 실패 위험.

**explore_lite 프론티어 탐색**
- peer_1의 고정 웨이포인트 순찰(`patrol_node`)을 `explore_lite`로 교체.
- 이유: 고정 웨이포인트는 맵 변경 시 재설계 필요. 프론티어 탐색은 Free↔Unknown 경계를 자동 발견, 전 구역 커버 보장.
- 패키지: `m-explore-ros2` (robo-friends fork), 소스 빌드.

**patrol_node 맵 필터링 추가**
- 웨이포인트 전송 전 `/map`에서 목적지 셀이 Unknown(-1)인지 확인 → Unknown이면 건너뜀.
- 이유: 팔로워가 peer_1 미탐색 구역으로 이동 시도 시 `Goal pose is out of costmap` 오류 방지.

### 신규 파일

| 파일 | 역할 |
|---|---|
| `map_readiness_node.py` | `/map` 커버리지 모니터 → `/fleet/map_ready` |
| `follower_trigger_node.py` | 맵 준비 신호 → 팔로워 Nav2 subprocess 기동 |

### 핵심 설계 논의 (기록)

**동적 물체 맵 오염 원리**
- LiDAR는 기하학만 인식. 정지한 동적 물체(사람, 차량 등)는 벽과 구분 불가.
- 맵핑 중 정지한 물체 → `P(occupied)` 최대 수렴 → 물체 이동 후에도 오랫동안 잔류.
- 해결: 맵핑 시 동적 물체 배제(운영 절차) 또는 multi-session averaging 또는 카메라+ML 분류.

**유리/반사면 LiDAR 한계**
- 투명 유리: LiDAR 빔 통과 → 셀 Free 기록 → 유리 너머 Unknown → 프론티어 생성 → 충돌.
- 반사 유리(정반사): 빔이 다른 방향으로 반사 → 허상 장애물 생성.
- 완화: `laser_filters` intensity 필터, `min_frontier_size` 상향, 지오펜싱.

**운용 구역 외 진입 방지**
- 물리적 위험(계단/낭떠러지): 하향 IR/ToF 센서 → 자율 감지 가능.
- 의미론적 제한(출입금지/실외): LiDAR 기하학으로 판단 불가 → 사전 수동 정의 필수.
- ROS2 권장 방법: Nav2 `KeepoutFilter` + `filter_mask.pgm` (건물 외곽/계단/출입금지 구역 lethal 마킹).
- 다음 단계: `fleet_world.sdf` 경계에 맞는 keepout_mask 작성 예정.

---

## 2026-05-26 — 이벤트 기반 자율 탐색 아키텍처 런타임 검증 (Ubuntu 세션)

### 검증 결과: PASS ✅

`fleet_autonomous.launch.py gui:=false with_patrol:=true` headless 실행, 전체 이벤트 체인 확인.

### 검증된 이벤트 타임라인

| 시간 | 이벤트 | 상태 |
|---|---|---|
| t=16s | slam_toolbox + map_readiness_node 기동 | ✅ |
| t=22s | explore_lite → peer_1 Nav2 연결, follower_trigger_node 대기 시작 | ✅ |
| t≈185s | peer_2 스폰 (follower_spawn_delay=181) | ✅ |
| t≈186s | peer_3 스폰 | ✅ |
| t≈190s | peer_2 DDC+JSB Configured and Activated | ✅ |
| t≈192s | peer_3 DDC+JSB Configured and Activated | ✅ |
| t≈370s | 커버리지 79% 달성 → /fleet/map_ready 발행 (TRANSIENT_LOCAL) | ✅ |
| 즉시 | follower_trigger_node 수신 → peer_2 CM 확인 (즉시 준비) → Nav2 기동 (pid=19567) | ✅ |
| +16s | peer_2 lifecycle: Managed nodes are active | ✅ |
| +10s | peer_3 Nav2 기동 (+10s 스태거, pid=19669) | ✅ |
| +16s | peer_3 lifecycle: Managed nodes are active | ✅ |
| 이후 | peer_2 patrol_node 기동 (10 waypoints, loop=True) | ✅ |
| 이후 | peer_3 patrol_node 기동 (6 waypoints, loop=True) | ✅ |

### 주요 관찰 사항 (Findings)

**⚠️ TF "jump back in time" 경고 반복 발생**
- Gazebo에서 새 물리 엔티티 추가 시(peer_2/3 스폰, Nav2 프로세스 기동) sim_time 불연속 발생.
- `bt_navigator`, `explore_lite`, `planner_server` 등 모든 TF 소비자가 영향받음.
- 매번 자동 회복: 에러 후 수십ms 내 새 목표 재설정 또는 계속 진행.
- 결론: Gazebo의 기존 알려진 이슈로 우리 코드 문제 아님. 운영 영향 없음.

**🔍 커버리지 진행 패턴**
- explore_lite가 먼 프론티어 이동 시 SLAM 맵 경계 확장 → 비율 일시 하락(44%→35%).
- 환경 경계(20×20m 벽) 도달 후 총 셀 수 안정화(113k~127k) → 이후 비율 단조 증가.
- 70% 임계값: 약 370s에 79% 달성. 적절한 임계값.

**🔍 peer_3 JSB spawner 첫 시도 타임아웃**
- `Failed getting a result from calling list_controllers in 10.0. (Attempt 1 of 3.)` → 재시도에서 성공.
- controller_manager 초기화 타이밍 이슈. 허용 가능한 수준.

### 결정 사항

- 이벤트 기반 아키텍처 검증 완료. 타이머 기반 접근의 한계를 극복함.
- TF 시간 점프는 별도 개선 과제로 등록 (향후 `use_sim_time` 동기화 개선 고려).
- 다음 단계: UWB 협력 측위 시뮬 검증, Foxglove 접속 확인.

---

## 2026-05-26 — peer_3 TF 트리 단절 버그 수정 (Ubuntu 세션)

### 문제 상황

GUI 모드(`aip_auto_patrol`) 직접 시뮬 실행 시 peer_3의 global_costmap에서
`Timed out waiting for transform from peer_3/base_link to map` 오류가 영구적으로 반복됨.
동시에 `ekf_node-42`(peer_3 EKF)에서 "jump back in time" 경고 반복.

### 근본 원인 분석

```
GUI 모드 → CPU 부하 증가 → Gazebo sim_time 불규칙 심화
peer_2 Nav2 기동 → 새 DDS 참여자 → /clock 구독 → sim_time 추가 점프
ekf_node(peer_3) → "jump back in time" → odom→base_link TF 발행 불안정
AMCL 초기화 중 odom→base_link TF 누락 → 파티클 전파 실패
→ AMCL이 map→peer_3/odom TF 발행 못함 → TF 트리 단절
```

### 결정 사항 및 수정 내역

1. **`follower_trigger_node.py`**: peer_3 스태거 `10s → 30s`
   - peer_2 Nav2 기동 후 DDS 참여자 증가로 인한 sim_time 불규칙이 안정화될 시간 확보
   - `_wait_for_tf()` 메서드 신규 추가: EKF TF(odom→base_link)가 3회 연속 조회 성공 후에만 Nav2 기동
   - `tf2_ros` import 및 Buffer/TransformListener 초기화 추가

2. **`ekf_vehicle.yaml`**: `transform_timeout: 0.1 → 0.5`
   - EKF가 TF 조회 시 대기하는 시간 증가 → sim_time 점프 후 복구 허용

3. **`nav2_full.yaml`** (AMCL 섹션):
   - `min_particles: 1000 → 500` — 더 빠른 초기화
   - `max_particles: 3000 → 2000` — GUI 모드 CPU 부하 절감
   - `transform_tolerance: 1.0 → 2.0` — AMCL이 TF 시간 차이 더 허용

4. **`autonomous_nav.launch.py`**: AMCL 초기 공분산 타이트하게
   - `initial_cov_xx/yy: 0.05 → 0.02`, `initial_cov_aa: 0.025 → 0.01`
   - 파티클 초기 분포 집중 → 빠른 수렴 → TF 발행 전까지 취약 시간 최소화

5. **`package.xml`**: `<depend>tf2_ros</depend>` 추가

### 빌드 결과

`colcon build --packages-select aip_fleet_autonomous aip_fleet_nav` → **SUCCESS** (경고 없음)

---

## 2026-05-27 — peer_1 Nav2 자율 주행 디버깅 및 수정

### 문제 및 원인 분석

#### 1. `type="lidar"` → `type="gpu_lidar"` (Ignition Fortress 미지원)
- 증상: `/peer_1/scan` 토픽 데이터 없음
- 원인: Ignition Fortress는 CPU lidar 미지원 (`SdfEntityCreator.cc:910` 경고)
- 수정: `main_agv.urdf.xacro` sensor type 변경

#### 2. explore_lite `costmap_topic` 절대 경로 오류
- 증상: frontier 탐색 즉시 종료
- 원인: `'/map'`(절대) → slam_toolbox가 `/peer_1/map`에 발행하므로 구독 실패
- 수정: `'map'`(상대, 네임스페이스 자동 해석)으로 변경

#### 3. global_costmap `static_layer` 맵 경계 데드락
- 증상: `Robot is out of bounds of the costmap` 지속 경고, 경로 계획 불가
- 원인: slam_toolbox 초기 맵 4.98×4.98m, 로봇 (0,0) 시작 → 부동소수점으로 경계 바깥 판정
- 수정: `nav2_full.yaml` global_costmap에서 static_layer 제거, 고정 30×30m costmap 적용

#### 4. `/clock` 다중 브리지 → TF 타임스탬프 역행
- 증상: `Detected jump back in time` → TF 버퍼 초기화 → `Extrapolation Error` → goal ABORTED
- 원인: `spawn_vehicle.launch.py`가 차량마다 `/clock` 브리지를 생성, 3개의 브리지가 동일 토픽 발행
- 수정: `spawn_vehicle.launch.py`에서 `/clock` 제거, `ign_fleet.launch.py`에 단일 `clock_bridge` 노드 추가

### 결과
- `aip_goal peer_1 3.0 3.0` → **SUCCEEDED** ✅
- `Detected jump back in time` 경고 해소
- peer_1 Nav2 자율 주행 정상 동작 확인

### 수정 파일
- `src/aip_main_description/urdf/main_agv.urdf.xacro`
- `src/aip_fleet_autonomous/launch/fleet_autonomous.launch.py`
- `src/aip_fleet_autonomous/params/nav2_full.yaml`
- `src/aip_fleet_gazebo/launch/spawn_vehicle.launch.py`
- `src/aip_fleet_gazebo/launch/ign_fleet.launch.py`

---

## 2026-06-02 — explore_lite SLAM 드리프트 원인 제거 + 탐색 안정성 강화

### 상황
- `aip_auto_patrol` 실행 중 맵 데이터 오염 반복 발생
- 차량이 회전 복구 중 벽과 충돌하면서 바퀴 슬립 → yaw 오차 → SLAM 드리프트
- 오염된 맵으로 peer_2/3 AMCL 수렴 실패

### 핵심 의사결정

#### 1. BT 복구에서 Spin 제거 (가장 중요)
- **원인**: 충돌 복구 위치는 이미 벽 근처 → 제자리 선회 시 반대쪽 벽 또는 같은 벽과 재충돌 → 바퀴 슬립 → yaw 오차 → SLAM 드리프트
- **결정**: BackUp(0.60m) → ClearCostmap → Wait 시퀀스로 대체. MPPI가 새 경로 계획 시 자연스럽게 방향 전환
- **이전**: BackUp(0.50m) → Spin(1.57rad) → ClearCostmap → Wait

#### 2. SLAM 스캔 매처 강화
- `angle_variance_penalty`: 0.8 → 1.5 (슬립 유발 각도 오차 매칭 거부)
- `distance_variance_penalty`: 0.3 → 0.5 (odom 예측 괴리 강하게 패널티)
- `minimum_travel_heading`: 0.08 → 0.18 rad (회전 중 불량 스캔 누적 억제)

#### 3. explore_lite 안정성
- `same_point` 임계값: 0.01 → 0.20m (SLAM jitter 억제, 목표 빈번 교체 방지)
- ABORT blacklist TTL: 600s (코너 반복 재도전 루프 차단)
- `min_frontier_size`: 0.5 → 0.6m (SLAM 위치 오차~0.1m 보정 포함)
- `goal_continuity_scale`: 2.0 (인근 구역 연속 탐색 유도)

#### 4. map_readiness stall 감지
- 90s간 셀 증가 < 200개 → 접근불가 구역으로 판단 → 강제 map_ready 트리거
- 기존: explore_lite가 프론티어 소진 시에만 종료 → 접근 불가 코너로 무한 탐색 루프

#### 5. rf2o 로그 억제
- `output='log'` + `--log-level ERROR`: 터미널 노이즈 제거

### 커밋
- `fbd9bc0`: fix(explore): SLAM 드리프트 원인 제거 및 탐색 안정성 강화

### 잔여 과제
- 재시작 후 수정된 복구 시퀀스(Spin 제거) 효과 검증 필요
- peer_3 AMCL TF 체인 GUI 모드 재테스트 필요
- 수정 후 완전 맵 커버리지 달성 여부 확인

---

## 2026-06-10 — FleetDashboard 최신 빌드 동기화

### 변경 배경
Phase-2 자율주행 빌드(9aa2284) 이후 추가된 노드/토픽에 맞춰 FleetDashboard 패널 최신화.

### 주요 변경 사항 (FleetDashboard.tsx)

| 항목 | 이전 | 이후 |
|---|---|---|
| 경보 토픽 | `/{peer_N}/perception_alert` × 3 | `/fleet/alerts` 단일 집계 토픽 |
| 커버리지 JSON | `{peer_2: N, ...}` 평탄 구조 | `{per_vehicle: {peer_2: N}}` 중첩 구조 |
| 열화상 온도 | 없음 | `/{peer_N}/thermal_temp` 구독 → 차량 카드 표시 |
| 맵 준비 상태 | 없음 | `/fleet/map_ready` 구독 → 헤더 MAP READY 뱃지 |
| PerceptionAlert 타입 | 기본 필드만 | `thermal_zone`, `rgb_bbox_*` 추가 |
| CMD 상수 | 0~3 | CMD_MANUAL = 4 추가 |

### 결과
- `npm run build` — 오류 없음
- `npm run local-install` — `/home/kde/.foxglove-studio/extensions/` 설치 완료
- `.foxe` 재생성: `aip.fleet-foxglove-panels-0.1.0.foxe`


---

## 2026-06-10 — explore_lite 두 점 루프 고착 수정

### 변경 배경
4배속 단독 매핑 테스트 중 커버리지 71,374셀에서 정체. peer_1이
(-3.59, 2.93) ↔ (-5.43, 1.39) 사이를 반복하며 매핑 진행 없음.

### 근본 원인 분석

m-explore-ros2 frontier 비용 함수:
`cost = potential_scale × distance × res - gain_scale × size × res + goal_continuity_scale × dist_from_prev_goal`

| 원인 | 이전 값 | 문제 |
|---|---|---|
| `goal_continuity_scale: 2.0` | 기본값 0.0 | 이전 목표에서 먼 frontier +2.0m/m 비용 → 지역 고착 (북쪽 10m frontier: +20 비용 추가) |
| `potential_scale: 0.5` | 기본값 1e-3 | 기본값의 500배 → 원거리 frontier 비용이 로컬의 25배 |
| `min_frontier_size: 0.15` | 기본값 0.5 | 벽 틈새 0.15m 슬릿 frontier 허용 → 도달 불가 지점 반복 선택 |
| `blacklist_abort_ttl: 150s` | 기본값 600s | Nav2 실패 frontier 150s 후 재진입 → 루프 사이클과 일치 |
| `max_blacklist_retries: 6` | 기본값 3 | 블랙리스트 6회 초기화 → 같은 두 점 7+회 재시도 |

### 수정 내용 (fleet_autonomous.launch.py)

| 파라미터 | 이전 | 이후 | 이유 |
|---|---|---|---|
| `goal_continuity_scale` | 2.0 | 0.0 | 지역 고착 제거 (소스 기본값 복원) |
| `potential_scale` | 0.5 | 0.003 | 거리 패널티 사실상 제거 → 크기 우선 |
| `gain_scale` | 0.5 | 1.0 | 소스 기본값 복원 |
| `min_frontier_size` | 0.15 | 0.5 | 소형 슬릿 frontier 필터링 (기본값 복원) |
| `blacklist_ttl` | 60 | 120 | 기본값 복원 |
| `blacklist_abort_ttl` | 150 | 300 | Nav2 실패 frontier 5분 제외 |
| `max_blacklist_retries` | 6 | 2 | 반복 실패 구역 조기 포기 |
| `progress_timeout` | 90 | 60 | 더 빠른 블랙리스트 등록 |

### 빌드
- `aip_fleet_autonomous` colcon 빌드 PASS

---

## 2026-06-10 — 전역/로컬 코스트맵 인플레이션 불일치 수정

### 변경 배경
SmacHybrid-A*가 벽에 0.115m까지 근접한 경로를 계획 → MPPI 실행 시
로컬 코스트맵 LETHAL 구역(0.165m) 안에 경로 위치 → CostCritic 1만 페널티
→ "Failed to make progress" → stuck_escape 후진 → ClearCostmap(전역 동일)
→ 동일 경로 재생성 → 고착 악순환.

### 근본 원인 (구조적 불일치)

```
전역 코스트맵: inflation_radius=0.15m, LETHAL 경계=0.115m(inscribed)
로컬 코스트맵: inflation_radius=0.25m, LETHAL 경계=0.165m(0.115+padding 0.05)
→ 플래너 경로가 벽에서 0.115~0.165m 구간에 위치 시
  전역에서는 "안전", 로컬에서는 "LETHAL" → MPPI 실패
```

### 수정 내용 (nav2_full.yaml)

| 코스트맵 | 파라미터 | 이전 | 이후 |
|---|---|---|---|
| 전역 | `inflation_radius` | 0.15 | **0.35** |
| 전역 | `cost_scaling_factor` | 3.0 | **5.0** |
| 로컬 | `inflation_radius` | 0.25 | **0.35** |
| 로컬 | `cost_scaling_factor` | 3.0 | **5.0** |

0.35m 선택 이유:
- 차체 내접원 0.115m + 여유 0.235m = 벽에서 0.235m 실질 간격 확보
- 0.70m 도어웨이: 중앙에서 양벽까지 0.35m = inflation 경계에서 cost≈78 < LETHAL(253) → 통과 가능
- cost_scaling_factor 5.0: 빠른 경사 → 도어웨이 중앙 cost(78) < 3.0 시(124)보다 낮음 → 통과 용이

### 빌드
- `aip_fleet_autonomous` colcon 빌드 PASS

---

## 2026-06-11 — peer_2/3 스폰 후 TF 단절 수정

### 문제 재현
`auto_patrol_2x` 모드에서 peer_1 매핑 완료 후 peer_2/3 스폰 시:
```
[planner_server-2] Timed out waiting for transform from peer_2/base_link to map:
Could not find a connection between 'map' and 'peer_2/base_link'
because they are not part of the same tree. Tf has two or more unconnected trees.
```
peer_2/3 동시에 반복 발생 → AMCL이 map→odom TF를 영구 미발행 의심.

### 근본 원인

**이중 타이밍 문제:**

1. **map_server 활성화 경쟁** — `_freeze_map_and_serve()`에서 `time.sleep(3.0)` 고정 대기 후 lifecycle 전환.
   고부하(rtf≥2, 4배속) 환경에서 map_server 노드가 3초 내 등장하지 않으면 lifecycle 명령이 UNKNOWN 노드에 전달 → 활성화 실패 → `/map_static` 미발행 → AMCL 수신 맵 없음.

2. **AMCL 수렴 전 planner_server 기동** — `_wait_for_tf()`가 EKF의 `peer_N/odom→peer_N/base_link`만 확인.
   `_launch_nav2()` 직후 lifecycle_manager가 amcl + planner_server를 동시 activate.
   planner_server의 global_costmap이 즉시 `map→peer_N/base_link` TF 조회하지만,
   AMCL은 map_static 수신 + 첫 레이저 스캔 처리 완료 후에야 `map→odom` TF 발행.

### 수정 내용 (follower_trigger_node.py)

**수정 1 — map_server 노드 등장 확인 (고정 sleep 제거)**
- 이전: `time.sleep(3.0)` + 재시도 없는 lifecycle 전환
- 이후: 최대 30초 노드 등장 폴링 + 최대 3회 재시도 lifecycle 전환

**수정 2 — AMCL TF 수렴 확인 (`_wait_for_amcl_tf()` 신규)**
- `_launch_nav2(vid)` 이후 `_wait_for_amcl_tf(vid)` 직렬 호출
- `map→{vid}/base_link` TF 3회 연속 성공 시까지 최대 90초 대기
- peer_3 스폰 전 peer_2 AMCL 수렴이 보장됨 (90s 스태거 + AMCL 대기 직렬화)

### 빌드
- `aip_fleet_autonomous` colcon 빌드 PASS

---

## 2026-06-11 — peer_2/3 EKF TF 타임아웃 근본 원인 수정

### 증상
- `skip_explore` 모드에서 peer_2/3의 EKF TF (`peer_N/odom → peer_N/base_link`) 60초 타임아웃
- AMCL TF 수렴 불가 → 모든 Nav2 goal 거부
- follower_trigger 로그: "TF 안정화 타임아웃 — Nav2 강제 기동"

### 근본 원인 분석

**Gazebo 서버 로그 확인** (`ign gazebo server_130024_1781165976479.log`):
- peer_1: 정상 초기화 (CM, diff_drive_controller 모두 로드)
- peer_2: `gz_ros2_control connected to service` 이후 **575초 침묵** — 하드웨어 초기화 없음
- peer_3: 동일

**robot_state_publisher 로그** (`robot_state_publisher_130731_...log`):
```
[WARN] failed to send response to /peer_2/robot_state_publisher/get_parameters (timeout)
```

**확정된 원인**: `spawn_vehicle.launch.py`에서 `rsp`(robot_state_publisher)와 `spawn`(entity 생성)이 **동시에** 시작됨.

peer_1이 이미 20+ ROS2 노드를 운용 중인 상태에서 peer_2 스폰 시 DDS 네트워크 포화. gz_ros2_control 플러그인이 `/{ns}/robot_state_publisher/get_parameters` 서비스를 호출할 때 RSP가 DDS 등록을 완료하지 않은 상태 → 응답이 드롭됨. gz_ros2_control은 무한 대기 상태에 진입 → controller_manager 생성 불가 → diff_drive_controller 없음 → EKF 오도메트리 데이터 없음 → TF 미발행.

**부수 확인**: spawner 3개 모두 180s 타임아웃 후 exit code 1 → CM이 끝까지 정상 동작 안 함.

### 수정 내용

**1. `spawn_vehicle.launch.py`** — entity spawn을 RSP보다 3초 지연

이전:
```python
retun [rsp, spawn, bridge, ...]
```

이후:
```python
retun [
    rsp,
    bridge,
    TimerAction(period=3.0, actions=[spawn]),  # RSP 완전 등록 후 entity 스폰
    ...
]
```

RSP가 3초간 DDS 등록을 완료한 후 entity를 스폰 → gz_ros2_control의 get_parameters 서비스 콜 성공 → CM 정상 생성 → diff_drive_controller 활성화 → EKF 정상 동작.

**2. `follower_trigger_node.py`** — `_wait_for_cm()` 개선

CM 서비스 존재 여부(false positive 가능)가 아닌, **diff_drive_controller 활성 상태**를 직접 확인:
```python
ros2 control list_controllers --controller-manager /{vid}/controller_manager
# 'diff_drive_controller' + 'active' 모두 포함 시 True
```

### 빌드
- `aip_fleet_gazebo`, `aip_fleet_autonomous` colcon 빌드 PASS

---

## 2026-06-12 — 웹 대시보드 라이트 테마 + SLAM 맵 렌더링 + Foxglove TRANSIENT_LOCAL 버그 우회

### 배경
사용자가 `aip_central` 실행 후 RViz에서 맵이 로드됨을 확인했으나, 웹 대시보드와 Foxglove Studio 양쪽 모두에서 맵과 peer_1 데이터가 렌더링되지 않는 문제를 제기.

### 진단 결과

**웹 대시보드 3가지 원인:**
1. **캔버스 구조적 결함**: 캔버스가 좌표 격자 + 차량 위치 점만 그렸고, OccupancyGrid 렌더링 기능이 아예 없었음.
2. **`/fleet/peer_poses` 타이밍**: 해당 토픽은 `sim_peer_sensing_node`만 발행하며, `fleet_autonomous.launch.py` 내에서 t=16s 이후 시작 → 그 전에는 점이 안 나타남.
3. **TF 조회 초기 실패**: `sim_peer_sensing_node`는 TF 전부 실패 시 `retun`으로 조용히 건너뜀 (line 172).

**Foxglove Studio 2가지 원인:**
1. **foxglove_bridge TRANSIENT_LOCAL 버그**: 바이너리에서 확인한 문자열 `"cached transient_local messages will not be replayed (reconnecting?)"`. 재연결 시 캐시된 `/peer_1/map` 메시지가 클라이언트로 재전송되지 않음 (foxglove_bridge 3.3.0 버그).
2. **`use_sim_time` 미설정**: foxglove_bridge와 dashboard_server 모두 `use_sim_time: False`(기본값)였음.

### 적용된 수정

**1. 웹 UI 라이트 테마** (`src/aip_fleet_dashboard/static/index.html`)
- 버튼·배지·경고 아이템·캔버스 전체 다크 색상 → 라이트 계열로 교체.

**2. SLAM 맵 렌더링 구현**
- `dashboard_server.py`: `_occupancy_grid_to_png_b64()` 추가 (numpy+PIL, RGBA: free=밝은회, occupied=어두운, unknown=중간회). `/peer_1/map`을 `_LATCHED_QOS`(TRANSIENT_LOCAL+RELIABLE)로 구독. `_cb_map()`에서 PNG→base64 변환 후 WebSocket `slam_map` 메시지 전송.
- `index.html`: `slamMapImg`/`slamMapMeta` 상태 변수 추가. `drawMap()`에서 배경 직후 `ctx.drawImage()`로 SLAM 맵 오버레이 (좌표 변환: `px0=mx(origin_x)`, `py0=my(origin_y+height*resolution)`, `pw=width*resolution/MAP_RANGE*cSize`). WebSocket `slam_map` 메시지 핸들러 추가.

**3. `central.launch.py` 수정**
- foxglove_bridge 파라미터에 `'use_sim_time': True` 추가.
- dashboard_server 파라미터에 `'use_sim_time': True` 추가.
- `topic_tools relay` 노드 추가: `/peer_1/map` → `/peer_1/map_relay` (TRANSIENT_LOCAL 재발행). Foxglove Studio에서 `/peer_1/map_relay`로 구독 시 재연결 후에도 맵 수신 가능.

### 빌드
`colcon build --symlink-install --packages-select aip_fleet_dashboard` — 1.78s, SUCCESS.
(stderr는 pkg_resources deprecation 경고만 — 오류 아님)

### 잔여
- 실제 시뮬레이션(`aip_auto_skip_2x` + `aip_central`)에서 브라우저 테스트 필요.
- Foxglove Studio: `/peer_1/map_relay` 토픽 구독 설정 안내 필요.

---

## 2026-06-12 — 전체 순찰 경로 RViz 시각화 추가

### 배경
Nav2 `/plan` 토픽은 "현재 목표까지의 경로"만 보여주므로 각 차량의 순찰 커버리지 전체를 파악하기 어려움.
사용자 요청: RViz에서 전체 순찰 루프를 항상 표시해달라.

### 변경 내용

**1. `patrol_node.py` 시각화 기능 추가**
- `_VIZ_COLORS` dict: peer_1=green, peer_2=blue, peer_3=orange (Nav Plan과 통일).
- `self._viz_pub`: `/{vid}/patrol_path_viz` (MarkerArray, TRANSIENT_LOCAL+RELIABLE, depth=1). 늦게 접속하는 RViz도 즉시 수신.
- `_publish_viz()` 메서드:
  - `{vid}_route`: LINE_STRIP — 모든 웨이포인트를 잇는 루프 선 (scale.x=0.06, alpha=0.7, 마지막 점=첫 점 추가로 닫힘).
  - `{vid}_waypoints`: CYLINDER — 각 위치 (직경 0.18m, 높이 0.10m, alpha=0.6).
  - `{vid}_labels`: TEXT_VIEW_FACING — 1-based 번호 (scale.z=0.22, 흰색).
  - `{vid}_target`: SPHERE — 현재 목표 강조 (직경 0.35m, 노란색, alpha=0.9).
  - 모든 마커 `lifetime.sec=0` (영구 표시).
- `__init__()` 끝에 `self._publish_viz()` — 노드 시작 직후 즉시 발행.
- `_send_next()` 목표 로그 직후에 `self._publish_viz()` — 웨이포인트 전환 시 target 마커 갱신.

**2. `phase2.rviz` MarkerArray 표시 3개 추가**
Nav Plan peer_3 항목 뒤에 삽입:
- `Patrol Path peer_1` → `/peer_1/patrol_path_viz` (Transient Local)
- `Patrol Path peer_2` → `/peer_2/patrol_path_viz` (Transient Local)
- `Patrol Path peer_3` → `/peer_3/patrol_path_viz` (Transient Local)

### 빌드
`colcon build --packages-select aip_fleet_autonomous --symlink-install` — 2.45s, SUCCESS.

### 동작 방식
- `aip_auto_patrol` 또는 `aip_auto_skip_2x` 실행 → patrol_node가 시작되면서 즉시 마커 발행.
- RViz가 나중에 시작되어도 TRANSIENT_LOCAL QoS 덕분에 마지막 MarkerArray 수신 가능.
- 웨이포인트 이동 시마다 노란 구체(target 마커)가 현재 목표로 이동.

### 잔여
- `aip_auto_skip_2x`로 실제 시뮬 테스트 필요.
- 필요 시 LINE_STRIP 두께(scale.x) 및 CYLINDER 크기 조정.

---

## 2026-06-12 — Foxglove bridge 연결 시 시뮬 속도 저하 + TF 외삽 오류 수정

### 원인 분석
`aip_central` (foxglove_bridge) 실행 중 Foxglove Studio 연결 시:
1. 브리지가 DDS 도메인의 **모든 토픽에 자동 구독** 생성 → DDS 트래픽 폭발 → CPU 포화
2. Gazebo 클록은 독립 프로세스라 계속 전진 (sim time: 1578s → 1814s)
3. Nav2/EKF 노드가 CPU 부족으로 TF를 발행하지 못해 TF 버퍼 공백 236초 발생
4. bt_navigator가 goal 발행 시점(1578s) 기준 TF 조회 → 버퍼에 없어 `Extrapolation Error`
5. BT tick rate exceeded: bt_navigator 100Hz 행동 트리 실행 불가

### 수정 내용

**1. `central.launch.py` — foxglove_bridge topic_whitelist + scan 스로틀**
- `topic_whitelist` 추가: Foxglove Studio가 구독 가능한 토픽을 모니터링 필수 항목으로 제한
  - `/tf`, `/tf_static`, `/clock` — TF/시간
  - `/map_static`, `/peer_1/map_relay` — 지도
  - `/fleet/.*` — 플릿 상태
  - `/peer_[123]/(amcl_pose|plan|patrol_path_viz|arm_fov_marker|scan_slow|odometry/filtered|particlecloud)$`
  - `/peer_1/explore/goal_marker$`
- `num_threads: 4` 추가: 브리지 CPU 점유 상한 설정
- `scan_throttle_peer_{1,2,3}` 노드 추가: `/peer_N/scan` (10Hz) → `/peer_N/scan_slow` (5Hz)
  - Foxglove LaserScan 시각화는 `scan_slow` 사용 (충분한 갱신율)

**2. `patrol_node.py` — goal 실패 시 재시도 로직**
- `_consec_fail` 카운터 + `_MAX_FAIL=3` 추가
- `_on_result`: 성공 시 → 다음 웨이포인트. 실패 시:
  - consec_fail < 3: 5s 대기(STEADY_TIME) 후 동일 웨이포인트 재시도 (TF 복구 기다림)
  - consec_fail ≥ 3: 경고 후 건너뜀
- `_on_fail_timeout` 헬퍼 메서드 추가

### 빌드
`colcon build --packages-select aip_fleet_autonomous aip_fleet_bringup` — SUCCESS

### Foxglove LaserScan 구독 변경 사항
Foxglove Studio에서 레이저 스캔 시각화 시:
- 기존: `/peer_N/scan` (이제 whitelist에서 제외됨)
- 변경: `/peer_N/scan_slow` (5Hz 스로틀, whitelist에 포함)

---

## 2026-06-12 — 실배치용 순찰 경로 계획 기능 추가

### 배경
하드코딩된 `_PATROL_WP`는 시뮬 전용. 실제 현장 투입 시 지형/맵에 맞는 경로 계획 도구 필요.

### 추가된 기능

**1. `patrol_planner_node.py` (신규 ROS2 노드)**
- **웨이포인트 모드**: RViz "2D Goal Pose" 클릭 → 차량별 웨이포인트 순서대로 기록
- **커버리지 모드**: RViz "Publish Point"로 폴리곤 꼭짓점 → `generate_coverage <spacing>` 명령으로 잔디깎기 경로 자동 생성
- `/patrol_planner/cmd` String 토픽으로 명령 수신 (switch/mode/undo/clear/save/load/generate_coverage/heading)
- `/patrol_planner/preview` MarkerArray (TRANSIENT_LOCAL) 발행 — 실시간 경로 프리뷰
- `save` 명령으로 YAML 저장, `load:<path>` 로 기존 계획 불러오기
- 외부 의존성 없는 순수 Python 잔디깎기 알고리즘 (`_boustrophedon`)

**2. `patrol_plan_template.yaml` (신규 템플릿)**
- 웨이포인트 직접 편집 예시 포함
- 커버리지 모드 사용법 주석 포함
- 현재 시뮬 기본값 포함 (실제 환경에 맞게 수정하도록 안내)

**3. `fleet_autonomous.launch.py` 수정**
- `patrol_plan` LaunchArgument 추가 (기본값: 빈 문자열 = 기본 경로 사용)
- `_load_patrol_plan(path)` 함수: YAML → 차량별 flat 웨이포인트 dict
- follower_trigger 섹션을 OpaqueFunction으로 교체 → 런치 시점에 YAML 로드
- 외부 YAML이 없으면 기존 `_PATROL_WP` 사용 (하위 호환)

**4. `setup.py` 수정**: `patrol_planner_node` 엔트리포인트 추가

### 사용법
```bash
# 1. 계획 노드 실행 (시뮬 or 맵 서버 실행 중일 때)
ros2 run aip_fleet_autonomous patrol_planner_node --ros-args \
    -p output_path:=$HOME/aip_maps/patrol_plan.yaml \
    -p active_vehicle:=peer_1

# 2. RViz에서 /patrol_planner/preview 추가 후 경로 설계
#    웨이포인트: "2D Goal Pose" 클릭
#    커버리지: mode:coverage 명령 후 "Publish Point" 클릭

# 3. 저장
ros2 topic pub --once /patrol_planner/cmd std_msgs/String '{data: "save"}'

# 4. 저장된 계획으로 시뮬 실행
ros2 launch aip_fleet_autonomous fleet_autonomous.launch.py \
    with_patrol:=true patrol_plan:=$HOME/aip_maps/patrol_plan.yaml
```

### 커버리지 알고리즘 검증
4×4m 정사각형, 1m 간격 → 8개 웨이포인트, 올바른 zigzag 패턴 및 yaw 확인됨.

---

## 2026-06-12 — 대시보드 양방향 순찰 계획 UI 구현

### 의사결정

#### 1. patrol_planner_node.py 확장
- `/patrol_planner/plan_state` (String, TRANSIENT_LOCAL) 발행 추가 — JSON 포맷:
  ```json
  {"vehicles": {"peer_1": [[x,y,yawDeg],...], ...}, "active": "peer_1", "mode": "waypoints", "polygon": [[x,y],...]}
  ```
- 새 명령 2개 추가:
  - `set_wp_list:<vid>:<x,y,yawDeg>;...` — UI에서 웨이포인트 일괄 설정
  - `coverage_box:<vid>:<x1,y1>:<x2,y2>:<spacing>:<heading>` — UI 드래그 박스로 boustrophedon 생성
- 모든 상태 변경 후 `_publish_plan_state()` 호출하여 UI 동기화

#### 2. Foxglove 패널 — AIP Patrol Planner
- `PatrolPlannerPanel/src/PatrolPlannerPanel.tsx` 신규 생성 (~290줄)
- `/map_static` (OccupancyGrid) 구독 → HTML5 canvas 렌더링 (Y축 반전)
- 클릭: 웨이포인트 추가 (yaw 자동 계산)
- 드래그: 커버리지 박스 지정 → `coverage_box:...` 명령 발행
- `/patrol_planner/plan_state` 구독 → 서버 상태와 UI 동기화
- `src/index.ts`에 "AIP Patrol Planner" 패널 등록

#### 3. FastAPI 대시보드 확장 (dashboard_server.py)
- `cmd_patrol()` → `/patrol_planner/cmd` 발행
- `_cb_plan_state()` → plan_state를 WebSocket 브로드캐스트 (`patrol_plan` 타입)
- WebSocket 핸들러에 `patrol_planner` 명령 추가

#### 4. Web 대시보드 UI (index.html)
- "🗺 순찰 경로 계획…" 버튼 → 모달 오픈
- 모달 내 2D 맵 캔버스 (SLAM 맵 렌더링 + 차량 경로 시각화)
- 차량 선택 탭 (peer_1/2/3)
- 편집 모드: 클릭-WP / 드래그-박스
- 박스 모드: 간격·방향 입력 → 실시간 노란 박스 미리보기
- 웨이포인트 목록 + 요약 패널
- Undo / 초기화 / YAML 저장 버튼
- `patrol_plan` WebSocket 메시지로 노드 상태와 양방향 동기화

### 결과물
- `patrol_planner_node.py` — plan_state 발행 + set_wp_list/coverage_box 명령
- `PatrolPlannerPanel/src/PatrolPlannerPanel.tsx` (신규)
- `src/aip_fleet_foxglove_panels/src/index.ts` — 패널 등록
- `dashboard_server.py` — patrol_cmd 퍼블리셔 + plan_state 구독
- `static/index.html` — 순찰 계획 모달 UI
- Foxglove 확장: `npm run build && npm run package` 성공
- colcon 빌드: aip_fleet_autonomous, aip_fleet_dashboard 정상 완료

---

## 2026-06-12 — 순찰 경로 3-zone 분할 재설계

### 배경
- 이전 peer_1/peer_2 경로가 북부 구역(doorway → 열원)을 완전 겹쳐 순찰 → 충돌 위험 + 커버리지 중복
- peer_3이 남부를 단독 담당하여 부하 불균형
- peer_1의 일부 웨이포인트가 벽 근처라 경로 계획 실패 발생

### 의사결정: 3-zone 분할

| 차량 | 구역 | 범위 |
|------|------|------|
| peer_1 | 북부 전담 | y ≥ 1.0 (doorway 통과 독점, 열원 순환) |
| peer_2 | 동남 전담 | y < 1.5, x > 0 (동쪽 벽 + 남동 적재) |
| peer_3 | 서남 전담 | y < 1.5, x < 0 (서쪽 벽 + 남서 적재) |

- **doorway (x=2.5, y=4.0)**: peer_1 만 통과, peer_2/3 불진입 → 병목 충돌 제거
- **적재 구역 (y=-4~-5.5)**: peer_2 동측(x>0), peer_3 서측(x<0) 분리 커버

### 변경 파일
- `src/aip_fleet_autonomous/launch/fleet_autonomous.launch.py`
  - `_PATROL_WP` 딕셔너리 전면 재설계 (peer_1: 10점, peer_2: 8점, peer_3: 8점)
  - docstring 구역 설명 업데이트

### 빌드 결과
- `aip_fleet_autonomous` colcon 빌드 정상 완료 (경고 없음)

---

## 2026-06-12 — 순찰 경로 구석 커버리지 확장

### 배경
- 기존 경로가 중앙부(x=[-3,3], y=[-5,8]) 위주 → 동/서쪽 벽 근처 및 남부 깊은 구역 미커버
- 사용자 요청: "구석진 곳도 돌아볼 수 있도록" 개선

### 의사결정: 웨이포인트 확장

| 차량 | 기존 범위 | 확장 범위 | 핵심 추가 포인트 |
|------|-----------|-----------|-----------------|
| peer_1 | x=[-3.5,3.5], y=[1.5,7.5] | x=[-4.5,4.5], y=[1.5,7.5] | 북동(4.5,7.5), 북서(-4.5,7.5) 구석 |
| peer_2 | x=[0.5,3.0], y=[-5.0,1.0] | x=[0.5,4.5], y=[-7.5,0.5] | 동쪽 x=4.5 + 남부 y=-7.5 심층 |
| peer_3 | x=[-3.0,-0.5], y=[-5.0,1.0] | x=[-4.5,-0.5], y=[-7.5,0.5] | 서쪽 x=-4.5 + 남부 y=-7.5 심층 |

### 안전 검증 (inflation_radius=0.35m 기준)
- Python 스크립트로 전체 27개 웨이포인트 전수 검증: 전부 안전
- 주요 이격 확인:
  - peer_2 (4.5, 0.5): pillar_2/4 에서 2.21/3.21m ✓
  - peer_2 (4.5, -5.5): col_loading_E(4.5,-4.0) 에서 1.3m ✓ (col과 x 동일하나 y 이격)
  - peer_2 (3.0, -7.5): crate_S_center에서 1.62m ✓
  - peer_1 (4.5, 7.5): shelf_N_east(6.5,7.5) 에서 1.8m ✓
  - 유일한 ⚠️: peer_1 doorway 동측(3.5,4.6) doorway_wall_east 에서 0.50m — 기존 설계 유지

### 변경 파일
- `src/aip_fleet_autonomous/launch/fleet_autonomous.launch.py`
  - `_PATROL_WP` peer_1: 9점→11점, peer_2: 8점 재배치, peer_3: 8점 재배치
  - 상단 docstring 구역 설명 업데이트

### 빌드 결과
- `aip_fleet_autonomous` colcon 빌드 정상 완료

---

## 2026-06-15 — UWB 협력 측위 시뮬 통합 (fleet_autonomous.launch.py)

### 배경
- `sim_peer_sensing_node` 가 이미 t=16s에 실행 중이지만 앵커 파라미터 없이 차량간 거리만 발행
- `uwb_localizer_node` 는 `aip_fleet_coordinator` 패키지에 구현 완료 (weighted Gauss-Newton)
- 목표: `with_uwb:=true` 하나로 UWB 측위 파이프라인 전체를 켤 수 있도록 통합

### 의사결정

#### 앵커 배치 (fleet_world 20×20m 맵 기준)
```
anchor_0: (-8.0, -8.0)  남서
anchor_1: ( 8.0, -8.0)  남동
anchor_2: ( 8.0,  8.0)  북동
anchor_3: (-8.0,  8.0)  북서
```
- 외벽(±10m) 안쪽 2m: 실제 UWB 앵커 마운팅 위치를 반영
- 4코너 배치 → 어느 위치에서도 최소 2개 앵커에 가시선 확보

#### 노드 구성
- `sim_peer_sensing_node`: 앵커 파라미터 항상 포함 (with_uwb=false여도 무해)
- `uwb_localizer_node × 2`: peer_2, peer_3 각각 — `IfCondition(with_uwb)`
  - `child_frame_suffix='_uwb_est'`: shadow 모드, AMCL TF와 분리
  - `initial_x/y`: _SPAWN_POS에서 초기화 (d=0 특이점 방지)
  - `slam_peer_ids=['peer_1']`: SLAM 리더를 weight=1.0 앵커로 활용
- `uwb_accuracy_check.py`: AMCL vs UWB 실시간 오차 비교 — `IfCondition(with_uwb)`

### 변경 파일
- `src/aip_fleet_autonomous/launch/fleet_autonomous.launch.py`
  - `with_uwb = LaunchConfiguration('with_uwb')` 변수 추가
  - `DeclareLaunchArgument('with_uwb', default_value='false', ...)` 추가
  - `sim_peer_sensing_node` 파라미터에 `anchor_ids/x/y` 추가 (4코너)
  - t=16s 블록에 `uwb_localizer_node × 2` + `uwb_accuracy_check` 조건부 추가
  - docstring Usage 및 브링업 타임라인 업데이트

### 사용법
```bash
# UWB 협력 측위 검증 포함 실행
ros2 launch aip_fleet_autonomous fleet_autonomous.launch.py with_uwb:=true

# 실행 중 실시간 오차 확인
aip_uwb_compare   # peer_2/3 AMCL vs UWB 추정 오차 출력 (10Hz)
```

### 빌드/검증 결과
- `aip_fleet_autonomous` colcon 빌드 정상 완료
- `ros2 launch --show-args`: `with_uwb` 인수 정상 등록 확인 (총 12개 인수)

---

## 2026-06-15 — diff_drive_controller 로딩 실패 근본 수정 (ros2_control 2.54 DDS 경쟁 조건)

### 문제
시뮬레이션 실행 시 peer_1의 diff_drive_controller가 반복적으로 로딩 실패:
```
[INFO] Setting controller param "type" to "diff_drive_controller/DiffDriveController"
[ERROR] The 'type' param was not defined for 'diff_drive_controller'.
[FATAL] Failed loading controller diff_drive_controller
```
spawner의 `set_parameters` 서비스 응답이 DDS 부하 상황에서 드롭되어 타입 파라미터가
controller_manager에 반영되기 전에 `load_controller`가 호출되는 경쟁 조건.

### 근본 원인 분석
- ros2_control 2.54.0 spawner: `--controller-type` 사용 시 DDS `set_parameters` 서비스 호출
- Gazebo 초기화 시 (t=16-18s): DDS 부하 최고조 → 서비스 응답 드롭 가능
- 드롭 시: spawner는 성공 로그 출력 후 `load_controller` 호출 → CM은 타입 미정의 오류
- spawner 소스(`spawner.py:209-228`): `set_parameters` 실패 시 FATAL 출력 후 종료되나,
  DDS가 응답을 드롭하면 `call_async` future가 완료 응답을 받아 성공으로 처리됨

### 해결책: master_yaml 기반 사전 정의 (spawner의 DDS 파라미터 설정 제거)

1. **`_make_master_yaml(vid, ctrl_yaml, arm_yaml)`** 새 함수 추가 (`spawn_vehicle.launch.py`)
   - 컨트롤러 타입 + `params_file` 참조를 CM 초기화 YAML에 포함
   - gz_ros2_control이 CM 시작 시 이 YAML을 읽어 컨트롤러를 자동 로드 (UNCONFIGURED 상태)
   - 자동 로드 시 `params_file`도 읽으므로 차량별 파라미터(바퀴 간격, odom 프레임)가 적용됨

2. **`main_agv.urdf.xacro`** 수정
   - `ns_ctrl_yaml` xacro 인수 추가
   - gz_ros2_control 플러그인에 조건부 두 번째 `<parameters>` 태그 추가

3. **spawner 단순화**: `--controller-type`, `--param-file` 인수 제거
   - spawner가 CM에서 컨트롤러를 이미 로드된 상태로 발견 → `set_parameters` 건너뜀
   - spawner는 `configure_controller` + `switch_controllers`(활성화)만 수행
   - DDS 파라미터 설정 경쟁 조건 완전 제거

### 변경 파일
- `src/aip_fleet_gazebo/launch/spawn_vehicle.launch.py`
  - `_make_master_yaml()` 함수 추가
  - `_make_controller_yaml()` 독스트링 업데이트
  - `_spawn_one()`: master_yaml 생성 + xacro에 `ns_ctrl_yaml` 전달
  - jsb/ddc/arm_ctrl 스포너: `--controller-type` + `--param-file` 제거
- `src/aip_main_description/urdf/main_agv.urdf.xacro`
  - `ns_ctrl_yaml` xacro:arg 추가
  - gz_ros2_control 플러그인에 조건부 두 번째 `<parameters>` 블록 추가
- `src/aip_main_description/config/ros2_controllers_base.yaml`
  - 코멘트 업데이트 (새로운 두 YAML 구조 설명)

### 빌드 결과
- `aip_main_description`, `aip_fleet_gazebo` colcon 빌드 정상 완료
- xacro 검증: `ns_ctrl_yaml` 없으면 단일 `<parameters>` (gz_warmup/실차 호환),
  있으면 두 번째 `<parameters>` 태그 정상 출력 확인

### 다음 단계
- `aip_auto_patrol` 실행 후 peer_1 diff_drive_controller 로딩 성공 여부 확인
- 기대 로그: "Controller already loaded, skipping load_controller" (WARNING) →
  configure/activate 성공 → peer_1 주행 시작

---

## 2026-06-15 — 실차 워크스페이스 모노레포 통합

### 배경
- 실차 bringup(`aip_fleet_real`)이 별도 워크스페이스 `~/aip_real_ws`(overlay)로 스캐폴딩돼 있었음.
- 사용자가 "GitHub 브랜치로 sim/real 분리 가능?" 문의.
- 분석: 브랜치 분리는 overlay-underlay(real이 sim을 동시에 underlay로 소싱)와 충돌.
  한 번에 한 브랜치만 체크아웃 → 공용 패키지 동시 빌드·소싱 불가, 복제 시 드리프트.

### 결정: 모노레포 흡수
- `aip_real_ws` 폐기. `aip_fleet_real`를 단일 레포 `aip-swarm-ws`의 `src/`로 이동.
- sim/real 분리는 브랜치가 아니라 colcon 빌드 타겟(`--packages-select/skip`).
- 공용(`aip_fleet_msgs` 등)은 같은 WS 공존 → 드리프트 0. 향후 갈라지면 공용 레포 추출로 진화.

### 이동/갱신
- `src/aip_fleet_real/`(패키지 자체 무수정), `docs/SETUP_RPI4.md`, `docs/REAL_WS.md`(구 README) 이동.
- `docs/SETUP_RPI4.md`·`docs/REAL_WS.md` 빌드 절차를 단일 WS 기준으로 재작성.
- `docs/HANDOFF_REAL_WS.md`의 "별도 WS / aip_swarm_ws 무수정" 전제(§3·§5·§9 일부)는 무효.
  최신 진입점은 `docs/REAL_WS.md`.

### 잔여
- TB3 TF frame_prefix 배선(Phase 2 하드웨어).
- colcon build 검증, 커밋.
- STS3215/LiDAR 드라이버, 공용 노드(coordinator/autonomy) 실차 launch 통합.

---

## 2026-06-15 — TF "jump back in time" 근본 원인 분석 및 수정

### 문제
- 시뮬 ~10분 후 전체 차량 정지: "BT tick rate 100Hz exceeded" + "TF jump back in time" + "map↔base_link 연결 끊김"
- 이전 세션: EKF 큐 오버플로우 추정 → 오진

### 근본 원인
**Gazebo /clock DDS 메시지 순서 역전**:
- `fleet_world.sdf` 물리 스텝 0.004s(250Hz) → `/clock` 토픽 250Hz 발행
- 3대 SLAM+EKF+Nav2 DDS 트래픽 + 250Hz `/clock` 혼잡 → DDS 순서 역전
- 역순 도착한 `/clock` 타임스탬프를 tf2_buffer가 감지 → "jump back in time" → 전체 TF 버퍼 초기화

**CPU 과부하 연쇄**:
- BT loop 100Hz (bt_loop_duration=10ms) + MPPI 1000샘플 × 3대 = 30,000 traj/s → CPU 과부하
- 순간 RTF < 1.0 구간 → /clock 발행 불규칙 → 타임스탬프 불일치 가중

**slam_toolbox 스캔 처리 지연**:
- CPU 과부하 시 스캔 큐 적체 → 회복 후 과거 타임스탬프 스캔 처리 → 과거 map→odom TF 발행

### 수정 내역

#### 1. `src/aip_fleet_gazebo/worlds/fleet_world.sdf`
- `max_step_size: 0.004` → `0.01` (250Hz → 100Hz)
- `/clock` 발행 60% 감소 → DDS 혼잡 완화, 메시지 역전 위험 대폭 감소
- 컨트롤러 update_rate=100Hz와 동기화 → "slower than gazebo sim period" 경고 제거

#### 2. `src/aip_fleet_autonomous/params/nav2_full.yaml`
- `bt_loop_duration: 10` → `25` (100Hz → 40Hz): "tick rate exceeded" 직접 해소
- `batch_size: 1000` → `500`: MPPI CPU 50% 절감 (30,000→7,500 traj/s)
- local costmap `update_frequency: 5.0` → `2.0` Hz (60% 절감)
- local costmap `publish_frequency: 2.0` → `1.0` Hz
- AMCL `max_particles: 3000→1000`, `min_particles: 500→200` (67% 절감)

#### 3. `src/aip_fleet_nav/params/ekf_vehicle.yaml`
- `odom0_queue_size: 10` → `3` (CPU 복구 시 과거 wheel odom 플러시 차단)
- `imu0_queue_size: 10` → `5`
- `odom1_queue_size: 10` → `3` (rf2o 과거 스캔 오도메트리 차단)

#### 4. `src/aip_fleet_nav/params/slam_toolbox_online.yaml`
- `throttle_scans: 2` 추가: 10Hz LiDAR → 5Hz 처리, SLAM CPU 50% 절감 + TF 발행 빈도 감소

#### 5. `src/aip_fleet_gazebo/launch/spawn_vehicle.launch.py`
- `_make_master_yaml()` dead code 제거 (이전 세션 실패한 master_yaml 방식의 잔재)

### 빌드 결과
- `aip_fleet_autonomous`, `aip_fleet_nav`, `aip_fleet_gazebo` 빌드 정상 완료 (1.66s)

### 다음 단계
- `aip_auto_patrol` 실행 → ~10분 이상 정상 운용 여부 확인
- 기대 결과: "BT tick rate exceeded" 경고 사라짐, TF jump 발생 안 함
- AMCL 파티클 1000개로 수렴 품질 저하 시 1500개로 상향 검토

## 2026-06-16 — 순찰 웨이포인트 추종 품질 개선 (도달시간/오버슛/고착회피/경로최적화)

### 배경
사용자 보고: 전 차량(peer_1/2/3) 순찰 중 4가지 문제 — ① 웨이포인트 도달 시간 느림,
② 지정 좌표 오버슛, ③ 고착 시 회피 대응 미흡, ④ 경로 최적화 기대 이하.

### 진단
`nav2_full.yaml`(MPPI/SmacPlannerHybrid), `patrol_node.py`, `stuck_escape_node.py` 전체 분석:
- **도달시간**: `vx_max: 0.20m/s`가 미션 스펙(0.2~0.5m/s) 하한에 고정.
- **오버슛**: `GoalCritic`(threshold 1.5m)과 `PathFollowCritic`(threshold 1.4m)의 활성
  구간이 거의 겹쳐 목표 근접 시에도 "경로 추종 지속" 압력이 남아 수렴 정확도 저하.
- **고착회피**: `stuck_escape_node`가 직선 후진만 수행(0.06m/s×2s=12cm) — 코너에 낀
  경우 탈출 불가. 감지(8s)+쿨다운(6s) 합산 지연 큼.
- **경로최적화**: `analytic_expansion_max_length: 3.0m`이 짧아 긴 직선 구간에서도
  Hybrid-A* 곡선 탐색에 의존 → 불필요하게 꺾인 경로.

### 변경 사항

#### 1. `src/aip_fleet_autonomous/params/nav2_full.yaml`
- `vx_max: 0.20 → 0.30` m/s, `vx_std: 0.10 → 0.14` (비율 유지, 도달시간 단축)
- `GoalCritic.cost_weight: 8.0 → 10.0` (목표 수렴력 강화)
- `PathFollowCritic.threshold_to_consider: 1.4 → 1.0` (GoalCritic threshold 1.5m보다
  작게 설정 — 목표 근접 시 경로추종 압력 우선 해제, 두 critic 경쟁 해소)
- `analytic_expansion_max_length: 3.0 → 5.0` (긴 직선 구간 직결 우선, 경로 품질 개선)

#### 2. `src/aip_fleet_gazebo/launch/spawn_vehicle.launch.py` (stuck_escape 파라미터)
- `stuck_timeout_sec: 8.0 → 5.0`, `escape_speed: 0.06 → 0.08`,
  `escape_duration: 2.0 → 3.0` (후진거리 12cm→24cm), `cooldown_sec: 6.0 → 4.0`

#### 3. `src/aip_fleet_gazebo/scripts/stuck_escape_node.py`
- `escape_angular` 파라미터(0.15 rad/s) 추가 — 탈출 후진에 미세 회전을 더해 직선
  후진만으로 탈출 불가능한 코너 상황 대응. 매 탈출마다 좌우 번갈아 적용해 동일
  방향 재고착 방지(`_escape_dir` 토글).
- declare_parameter 기본값들을 launch 오버라이드 값과 동기화.

### 빌드 결과
- `aip_fleet_autonomous`, `aip_fleet_gazebo` 빌드 정상 완료, YAML/Python 문법 검증 통과.
- 실제 시뮬 재테스트(`aip_auto_patrol`)는 아직 미실시.

### 다음 단계
- `aip_auto_patrol`로 3대 동시 순찰 ~10분 이상 실행, 도달시간/오버슛/고착탈출/경로
  품질 개선 여부 육안 확인 (RViz `local_plan_viz`, `patrol_path_viz` 마커 비교)
- CPU 여유 확인 후 `iteration_count: 1→2` 적용 검토 (MPPI 궤적 최적화 추가 개선,
  단 3대 동시 CPU 부하 증가 — 이번 변경에는 미포함, 기존 CPU 절감 튜닝과 상충 우려)
- `xy_goal_tolerance: 0.35`는 과거 spin-drift 회귀 방지를 위해 유지 (변경 안 함)

## 2026-06-16 — peer_2/3 오버슛·경로재탐색 구조적 원인 수정

### 배경
이전 수정(MPPI wz_max/GoalCritic/BT 파라미터)으로 peer_1은 안정되었으나,
peer_2/3는 여전히 목표 좌표 오버슛 및 반복 경로재탐색 문제 지속.

### 진단 (원인 3종)

1. **BT XML 구조 차이**
   - peer_1 (`navigate_w_collision_recovery.xml`): RecoveryNode(3회) — ClearCostmap + BackUp + Spin + Wait 물리적 복구 포함
   - peer_2/3 (`navigate_w_replanning_only_if_path_becomes_invalid.xml`): FollowPath 실패 시 경로재계산만 → 물리 복구 없이 동일 조건 재시도 → 무한 재계획 루프

2. **behavior_server 미실행 (peer_2/3)**
   - `autonomous_nav.launch.py`에 behavior_server Node 없음 → BackUp/Spin/Wait action 서버 미존재
   - BT에 recovery 시퀀스가 있었어도 action 서버 없이는 실행 불가

3. **AMCL 포즈 갱신 지연 → 오버슛**
   - `update_min_d: 0.05m`, `update_min_a: 0.10rad` — 목표 근접 감속 구간에서 이동량이 임계값 미달
   → AMCL 파티클 갱신 중단 → goal_checker가 stale pose 기준으로 "미도달" 판정
   → 속도 유지 → 실제로는 이미 통과한 상태에서 계속 주행 → 오버슛

### 변경 사항

#### 1. `src/aip_fleet_autonomous/launch/autonomous_nav.launch.py`
- **BT XML 교체**: `navigate_w_replanning_only_if_path_becomes_invalid.xml` (nav2_bt_navigator)
  → `navigate_w_collision_recovery.xml` (aip_fleet_autonomous, peer_1과 동일)
- **behavior_server Node 추가**: `nav2_behaviors/behavior_server` (BackUp/Spin/Wait 제공)
  - `cmd_vel` → `/{vid}/autonomy_cmd_vel` remapping
- **lifecycle_manager node_names**: `behavior_server` 추가 (4→5개 노드 관리)
- `bt_share` 변수(nav2_bt_navigator 참조) 제거, `auto_share` 통일

#### 2. `src/aip_fleet_autonomous/params/nav2_full.yaml` (AMCL)
- `update_min_d: 0.05 → 0.02m`: 목표 근접 감속 구간에서도 파티클 갱신 지속
- `update_min_a: 0.10 → 0.05rad`: 저속 회전 시 AMCL 포즈 지연 최소화

### 빌드 결과
- `aip_fleet_autonomous` 빌드 정상 완료 (2.18s)

### 다음 단계
- `aip_auto_patrol`로 peer_2/3 오버슛 감소 및 재탐색 루프 해소 여부 확인
- behavior_server 정상 기동 확인: `ros2 node list | grep behavior_server`

---

## 2026-06-17 — MPPI 궤적 시각화 remapping + peer_2 joint TF 누락 수정

### 배경
시뮬 테스트 중 두 가지 이슈 발생:
1. MPPI 궤적이 RViz에서 시각화되지 않음 (`/peer_N/trajectories`에 publisher 없음)
2. peer_2의 wheel/arm joint TF가 완전히 누락, peer_1/3은 1.3~1.5Hz 저발행

### 진단 결과

#### 이슈 1: MPPI 궤적 절대 경로 발행
- `ros2 topic info /trajectories --verbose` 에서 node namespace `/peer_1`이지만 토픽이 절대경로 `/trajectories`로 발행됨을 확인
- Nav2 Humble MPPI `trajectory_visualizer`가 hardcode `"/trajectories"` 절대 경로 사용 (namespace 무시)

#### 이슈 2: peer_2 joint_state_broadcaster 미로딩
- `aip_ctrl peer_2` 결과: DDC/arm_position_controller는 active, JSB 없음
- 원인: JSB spawner timeout=180s (t=15s 시작 → t=195s 포기)
  - peer_2 controller_manager 초기화가 극단적 부하 시 최대 541s 소요(실측)
  - DDC spawner(t=25+180=205s)보다 JSB 포기 시점이 10s 빠름 → DDC는 성공, JSB 실패
- peer_1/3 1.5Hz 저발행: JSB가 CM update_rate 100Hz로 발행 → 3대×100Hz=300msg/s DDS 혼잡

### 변경 사항

#### 1. `src/aip_fleet_autonomous/launch/autonomous_nav.launch.py` (이전 세션 완료)
- controller_server remapping에 `/trajectories` → `/{vid}/trajectories` 추가

#### 2. `src/aip_fleet_autonomous/launch/leader_nav.launch.py` (이전 세션 완료)
- 동일한 MPPI trajectories remapping 추가

#### 3. `src/aip_fleet_gazebo/launch/spawn_vehicle.launch.py`
- JSB spawner `--controller-manager-timeout` 180→**600** (peer_2 CM 지연 대응)
- DDC spawner `--controller-manager-timeout` 180→**600** (동일 이유, 예방적 연장)

#### 4. `src/aip_main_description/config/ros2_controllers_base.yaml`
- `update_rate: 100 → 30` Hz
  - JSB 3대×100Hz=300msg/s → 90msg/s로 DDS 혼잡 완화
  - 0.2m/s 저속 운용에 30Hz 충분

### 빌드 결과
- `aip_fleet_gazebo` 빌드 정상 완료 (0.20s)
- `aip_main_description` 빌드 정상 완료 (0.46s)

### 다음 단계
- 시뮬 재실행 후 peer_2 `aip_ctrl peer_2`에서 JSB active 확인
- peer_1/3 joint TF 발행률 개선 여부 확인 (`ros2 run tf2_tools view_frames`)
- MPPI 궤적 `/peer_N/trajectories` 토픽 publisher 확인

---

## 2026-06-17 — joint TF 10Hz 달성 + CM 100Hz 복구 + arm 관성 안정화

### 배경 (직전 세션 이어받기)
- MPPI trajectories 정상 ✅, 순찰 품질 양호 ✅, batch_size 300 성능 양호 ✅
- joint TF 1.25Hz → 10Hz 달성 (relay 노드 + CM 100Hz) ✅
- arm_position_controller active ✅, 10Hz 명령 ✅, TF ~10.5Hz ✅
- 단, **arm_link_1 좌우 회전 미동작** 지속

### 근본 원인 분석 — ODE 수치 불안정

gz_ros2_control 0.7.x (Humble)는 position command interface에 대해 force 기반 P 제어를 사용:
```
force = position_proportional_gain × (cmd - actual)
```

기존 arm link 관성 `I = 1e-5 kg·m²` + 댐핑 `Kd = 0.05` + Gazebo 물리 스텝 `dt = 0.004s` (250Hz):
- **수치 안정 기준**: `Kd × dt / I < 1` 필요
- 기존값: `0.05 × 0.004 / 1e-5 = 20 >> 1` → **ODE 발산 불안정**

CM 1Hz 시에는 느린 발산 진동이 JSB 1Hz 샘플에 잡혀 "회전처럼 보임",
CM 100Hz에서는 고주파 불안정 진동이 JSB 100Hz 평균 ≈ 0 → arm 정지처럼 보임.

### 변경 사항

#### `src/aip_main_description/urdf/main_agv.urdf.xacro`
arm_link_1/2/3 + thermal_frame 관성 `1e-5 → 0.001 kg·m²`:
- 안정 기준 재확인: `Kd × dt / I = 0.05 × 0.004 / 0.001 = 0.2 < 1` ✅
- 연속 극점: s₁ ≈ -2 (τ = 0.5s), s₂ ≈ -48 (fast)
- 이산 극점: z₁ = 0.992, z₂ = 0.825 → 단위원 내 ✅ (안정)
- 60° 수렴 시간: ~1.5s (3τ @ 95%) ≪ 스캔 주기 6.67s ✓
- thermal_frame 관성도 동일하게 1e-6 → 0.001 (wrist joint 안정성)

### 빌드 결과
- `aip_main_description` 빌드 완료

### 다음 단계
- 시뮬 재실행 → arm_link_1 좌우 회전 확인 (`ros2 topic echo /peer_1/joint_states` arm_pan 값 변화)
- 기대값: arm_pan_joint가 ±1.0472 rad sin파 추종 (±60°, 0.15Hz, ~1.5s 수렴 지연)

---

## 2026-06-22 — 메인 AGV SLAM+Nav2+patrol 파이프라인 이식 (66d654a)

### 목표
aip_swarm_ws 에서 검증된 SLAM→Nav2→twist_mux→patrol 파이프라인을
메인 차량(RPi4B)에 이식. `main_agv.launch.py` placeholder 를 완전 구현으로 교체.

### 설계 결정

**TF/네임스페이스**: scout_1(turtlebot3.launch.py) 에서 검증된 패턴 그대로 적용.
- `PushRosNamespace('main')` + `SetRemap('/tf', '/tf')`: Nav2 노드를 /main/* 에 배치,
  navigation_launch 내부 TF remap 이 /main/tf 구독으로 바뀌는 것 방지.
- `SetRemap('cmd_vel', 'autonomy_cmd_vel')`: fleet_main twist_mux autonomy(10) 슬롯 입력.
  fleet_main.launch.py 가 이미 twist_mux 를 관리하므로 별도 twist_mux 미추가.

**플래너**: SmacHybrid(Reeds-Shepp) 대신 NavFn 선택.
- 실내 저속 순찰에서 NavFn 이 더 안정적, 가볍고 첫 실차 테스트에 적합.
- SmacHybrid 는 좁은 통로 정밀 주행 필요 시 교체 검토.

**MPPI batch_size: 500** (sim 의 1000 에서 절반): RPi4B 4GB 예산 고려.

**기동 순서**: slam(즉시) → nav2(t=5s) → patrol(t=6s). fleet_main 은 별도 터미널.

### 변경 파일 (66d654a)

| 파일 | 내용 |
|---|---|
| `launch/main_agv.launch.py` | placeholder → SLAM+Nav2+patrol 완전 구현 |
| `config/main_agv/nav2.yaml` | 전 섹션 추가, map_topic: /map, bond_timeout: 0.0 |
| `config/main_agv/slam_toolbox.yaml` | YDLidar TG15 파라미터, throttle_scans: 2 |
| `config/main_agv/patrol.yaml` | 신규 (template waypoints, 실좌표 교체 필요) |
| `scripts/deploy_main_agv.sh` | SSH 원스텝 배포 스크립트 |

### 다음 단계 (RPi 온라인 시)
1. `bash scripts/deploy_main_agv.sh jh@192.168.0.18` 로 배포
2. 터미널1: `ros2 launch aip_bringup fleet_main.launch.py with_base:=true`
3. 터미널2: `ros2 launch aip_fleet_real main_agv.launch.py`
4. dev PC 에서 `ros2 topic hz /main/scan`, TF tree, Nav2 활성화 확인
5. 목표 전송 테스트: `ros2 topic pub /main/goal_pose ...`
6. 맵 생성 후 patrol.yaml 실좌표 교체 → with_patrol:=true 로 재기동

---

## 2026-06-17 — 실차 nav2 GroupAction 버그 수정 (00eaea5)

### 배경

`aip_fleet_real` 시뮬 검증(turtlebot3_sim.launch.py) 과정에서 두 가지 치명적 버그 발견:
1. **Nav2 노드 네임스페이스 누락**: `navigation_launch.py`는 `namespace` 인수를 `RewriteYaml root_key`로만 사용하고, 노드 자체에 네임스페이스를 적용하지 않는다. `PushRosNamespace` 없이는 Nav2 노드가 `/scout_1/*`가 아닌 루트에 생성되어 MPPI 파라미터 미매칭 → DWB 폴백 → "No critics defined" FATAL.
2. **TF 구독 경로 불일치**: `PushRosNamespace` + `navigation_launch`의 내부 `('/tf','tf')` remap 결합 → Nav2가 `/scout_1/tf` 구독. Gazebo/turtlebot3_bringup은 글로벌 `/tf` 발행 → "frame does not exist" 414회.
3. **static_layer 맵 미수신**: `slam_toolbox`는 절대 경로 `/map` 발행. `PushRosNamespace` 적용된 `global_costmap`은 상대 `map` → `/scout_1/map` 구독 → "Can't update static costmap layer, no map received".

시뮬(nav2_sim.yaml + turtlebot3_sim.launch.py)에서 세 가지 수정 모두 검증 완료 후 실차 파일에 역이식.

### 수정 내역

**`src/aip_fleet_real/launch/turtlebot3.launch.py`**
- nav2 `GroupAction`에 `PushRosNamespace(namespace)` 추가 → Nav2 노드 `/scout_1/*` 배치 및 MPPI params 매칭
- `SetRemap('/tf', '/tf')`, `SetRemap('/tf_static', '/tf_static')` 추가 → TF 글로벌 경로 강제 유지

**`src/aip_fleet_real/config/turtlebot3/nav2.yaml`**
- `global_costmap.static_layer`에 `map_topic: /map` 추가 → slam_toolbox 발행 토픽과 구독 경로 일치

### 검증

시뮬에서: NAV2_ACTIVE(iter=8), frame-does-not-exist=0, no-map-received=0, cmd_vel 20Hz, 로봇 (0,0)→(0.83, 1.46) 이동 확인.
실차 파일에 동일 패턴 적용, colcon 빌드 PASS (00eaea5).

---

## 2026-06-18 — 시뮬 안정화 3종 (서보암 고착 / FOV 끊김 / peer_1 초기 고착)

### 배경

전체 시뮬 검증 과정에서 3가지 문제 식별:
1. 서보암 ±90° ODE hard stop 고착
2. FOV 시각화 뚝뚝 끊김 (1Hz)
3. peer_1 초기 장애물 고착 장기화 (~57s)

### 결정 및 수정

#### 1. 서보암 고착 — dead-reckoning velocity 제어 (6aa57d6)

**원인 체인**: JSB 1Hz 피드백 → P제어기 스테일 데이터 기반 오버슈팅 → ODE hard stop(CFM=0) 충돌 → velocity 명령으로 탈출 불가.

**position interface 시도 → 포기**: gz_ros2_control 0.7.x에서 position command가 GazeboSimSystem에 반영되지 않음(no-op). velocity interface만 동작 확인.

**최종 해결**: `arm_scan_node.py` 전면 재작성.
- `est_pos += prev_vcmd × dt` (10Hz dead-reckoning 위치 추정)
- JSB 피드백 도착 시 `est_pos` 보정 (1Hz JSB → 보정 용도만)
- soft limit (`_SOFT_LIMIT = 1.0 rad`) dead-reckoning 기준 적용 → URDF ±90° 한계 도달 전 반전
- ODE `stopCfm=0.05` 추가 (무한 강성 완화)

#### 2. FOV 끊김 — base_link TF + est_pos 보간 (6aa57d6)

**원인**: `_publish_fov`가 `thermal_frame` TF에 의존 → JSB→relay→RSP 체인 통해 1Hz 갱신.

**수정**: base_link TF(EKF, 25Hz 안정) + tick 이후 경과시간 보간 `arm_pan = est_pos + prev_vcmd × dt`.
- 25Hz FOV 발행 → 실질적 25Hz 부드러운 갱신
- marker lifetime 1s → 80ms (stale 마커 잔류 제거)

#### 3. peer_1 초기 장애물 고착 장기화

**원인 1**: `movement_time_allowance: 15.0s` → 장애물에 막혀도 15초 후에야 recovery 진입.
→ `nav2_full.yaml`: `8.0s`로 단축.

**원인 2**: BackUp 0.10m/s 느린 속도 + Wait 5s × 3 retry = 최악 ~57s 고착.
→ `navigate_w_collision_recovery.xml`: BackUp 0.15m/s, 2단계 거리 0.40m, Wait 3s → 최악 ~20s.

**원인 3 (해당 없음)**: peer_1은 slam_toolbox 사용(AMCL 없음), patrol_node는 t≈115s 시작(Nav2 활성화 t≈60s 대비 55s 여유) → 타이밍 문제 없음.

### 검증

- 서보암 동작 정상화 (사용자 확인)
- FOV 시각화 25Hz 부드러운 갱신 (사용자 확인)
- 전체 시뮬: TF jump 없음, peer TF 단절 없음, MPPI 궤적 정상, 순찰 추종 정상 (사용자 확인)
- peer_1 초기 고착 해소 (사용자 확인 — "이상 없어보임")

### 파일 변경 목록

| 파일 | 변경 내용 |
|---|---|
| `src/aip_fleet_gazebo/scripts/arm_scan_node.py` | dead-reckoning + FOV 보간 전면 재작성 |
| `src/aip_main_description/urdf/main_agv.urdf.xacro` | velocity interface 유지, stopCfm=0.05, 관성 1e-5→0.001 |
| `src/aip_fleet_autonomous/params/nav2_full.yaml` | movement_time_allowance 15→8s |
| `src/aip_fleet_autonomous/behavior_trees/navigate_w_collision_recovery.xml` | BackUp 0.15m/s, dist 0.40m, Wait 3s |

---

## 2026-06-15 — 웹 관제 Foxglove 패널 안전/감시 기능 확장

### 배경
- 산업 감시 로봇 웹 관제에 필요한 FleetDashboard, OverridePanel, EStopPanel 기능 요구사항을 반영.
- 실차 네임스페이스 `main`, `scout_1`, `scout_2`를 기본 지원하되, 현재 시뮬레이션 네임스페이스 `peer_1`, `peer_2`, `peer_3`도 같은 패널에서 함께 지원하도록 결정.

### 구현 결과
- `FleetDashboard.tsx`
  - `/fleet/status`와 개별 `/<ns>/heartbeat`를 함께 반영하는 차량 상태 카드 구현.
  - `/fleet/alerts`, `/<ns>/detections`, `/fleet/perception_viz/<ns>`, `/<ns>/image_raw/compressed` 기반 AI 비전 캔버스와 bbox 오버레이 구현.
  - `/map_static` 또는 `/peer_1/map_relay` OccupancyGrid 캔버스 렌더링 및 열지도 토글 구현.
  - 고빈도 프레임 처리를 125ms 주기(약 8Hz)로 throttle하여 브라우저 부하를 제한.
- `OverridePanel.tsx`
  - `/fleet/control_lock` 세션 락 추가. 타 오퍼레이터 락 감지 시 view-only 상태 표시.
  - `/<ns>/override_cmd_vel` 직접 Twist 발행과 `/fleet/override` `CMD_MANUAL` 발행을 함께 수행.
  - HOLD-to-drive 10Hz 스트리밍, 키보드 WASD/Arrow 입력, 언마운트/해제 시 zero twist + PAUSE fail-safe 처리.
- `EStopPanel.tsx`
  - 전역 E-Stop은 `/fleet/override` `vehicle_id="*", command=3`과 모든 `/<ns>/estop=True`를 동시에 발행.
  - 개별 차량 E-Stop 버튼 추가.
  - 해제는 confirm 후 `/fleet/override` CLEAR 및 `/<ns>/estop=False` 발행.

### 검증
- `python -m py_compile src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py` PASS.
- `git diff --check` PASS.
- 현재 Windows 세션에 `npm`/`npx`/`tsc`/`foxglove-extension` 실행 파일이 없어 Foxglove 확장 빌드는 미수행. Node/npm 설치 환경에서 `cd src/aip_fleet_foxglove_panels && npm install && npm run build && npm run package` 재검증 필요.

### 추가 진행
- `aip_fleet_supervisor/supervisor_node.py`에 `/fleet/control_lock` 구독 및 `/fleet/control_lock_state` 발행을 추가.
- `require_control_lock` 파라미터를 추가해 운영 모드에서 락 없는 수동/해제 명령을 거부할 수 있게 준비. 기본값은 기존 호환을 위해 `false`.
- `control_lock_ttl_sec` 기본 3초로 stale operator lock 자동 정리.
- `test_supervisor_node.py`에 lock/unlock, stale prune, require-lock 수동 명령 차단/허용 테스트 추가.
- Windows에는 `rclpy`가 없어 pytest는 수집 단계에서 실패. `supervisor_node.py` py_compile 및 `git diff --check`는 PASS.

---

## 2026-06-15 — 독립 웹 관제 대시보드 제품 UI 전환

### 배경
- 사용자가 의도한 "새로운 웹"은 Foxglove 내부 패널보다 `src/aip_fleet_dashboard`의 FastAPI 기반 독립 웹 관제에 가깝다고 확인.
- Foxglove 패널은 개발/운영 보조 콘솔로 두고, 브라우저 `http://localhost:8080`에서 여는 독립 관제 화면을 메인 UI로 확장하기로 결정.

### 구현 결과
- `dashboard_server.py`
  - 차량 목록을 `main`, `scout_1`, `scout_2`, `peer_1`, `peer_2`, `peer_3`로 확장.
  - `/fleet/override`, `/fleet/control_lock`, `/<ns>/override_cmd_vel`, `/<ns>/estop` 발행 추가.
  - `/fleet/control_lock_state` 구독 및 WebSocket 브로드캐스트 추가.
  - `/fleet/perception_viz/<ns>` CompressedImage 구독 후 base64 이미지로 WebSocket 전송.
  - `/map_static`, `/peer_1/map`, `/peer_1/map_relay` OccupancyGrid를 모두 수신 가능하게 확장.
- `static/index.html`
  - 깨진 한글/마크업을 정리하고 독립 관제용 UI로 전면 교체.
  - 차량 상태 카드, SLAM 지도/열 알림 레이어, AI 비전 스트림, 알림 피드, 제어/안전 패널 구현.
  - 제어권 획득/해제, 전체/개별 E-Stop, 수동 속도 슬라이더, 누르는 동안 10Hz 수동 주행 구현.
- `package.xml`
  - `geometry_msgs`, `nav_msgs`, `sensor_msgs` 의존성 추가.

### 검증
- `python -m py_compile src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py` PASS.
- `git diff --check` PASS.
- Codex in-app Browser는 Windows 샌드박스 권한 문제로 실행 확인 불가. ROS2/WSL 환경에서 `colcon build --packages-select aip_fleet_dashboard` 후 `ros2 run aip_fleet_dashboard dashboard_server`로 브라우저 확인 필요.

---

## 2026-06-15 웹 대시보드 다크모드 및 지도 전체화면 추가

### 배경
- 사용자가 독립 웹 관제 화면에 다크모드 전환 버튼과 지도만 크게 보는 전체화면 기능을 요청.
- 현재 웹 관제는 `src/aip_fleet_dashboard/static/index.html` 기반 FastAPI 정적 UI가 메인 화면이고, Foxglove 패널은 보조/개발자용 관제 패널로 유지.

### 구현 결과
- 헤더에 `Dark/Light` 토글 버튼을 추가하고 선택한 테마를 `localStorage`에 저장하도록 구현.
- `body.dark` CSS 변수를 추가하여 기존 UI 색상 체계를 유지하면서 다크모드가 전체 대시보드에 적용되도록 변경.
- SLAM 지도 패널에 `지도 전체화면` 버튼을 추가.
- 지도 전체화면 상태에서는 지도 패널만 화면 전체를 차지하고, ESC 키로 즉시 복귀할 수 있도록 구현.

### 검증
- `python -m py_compile src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py` PASS.
- `git diff --check` PASS.
- 코드 검색으로 `theme-toggle`, `toggleTheme`, `toggleMapFullscreen`, `map-fullscreen`, `Escape` 핸들러 존재 확인.

---

## 2026-06-15 웹 지도 기반 순찰 웨이포인트 편집 추가

### 배경
- 웹 대시보드가 정상 실행됨을 확인한 뒤, 다음 단계로 지도에서 직접 임무를 만드는 기능을 진행.
- 기존 `dashboard_server.py`에는 `/patrol_planner/cmd` 브릿지와 `/patrol_planner/plan_state` 구독이 이미 있어, 웹 UI만 확장하면 ROS2 순찰 플래너와 연결 가능.

### 구현 결과
- `src/aip_fleet_dashboard/static/index.html`에 `순찰 경로 계획` 패널 추가.
- `지도 클릭으로 Waypoint 추가` 모드 추가.
- 클릭한 Canvas 좌표를 기존 `canvasToWorld()` 변환으로 ROS map frame 좌표로 변환해 선택 차량의 waypoint 목록에 추가.
- waypoint 목록, 지도 위 경로선, 번호 마커를 렌더링.
- `Undo`, `Clear`, `전송`, `저장` 버튼 추가.
- 전송 시 `/patrol_planner/cmd`로 `switch:<vehicle>`, `mode:waypoints`, `set_wp_list:<vehicle>:...` 명령을 발행.
- 저장 시 `save` 명령까지 발행해 `patrol_planner_node`의 YAML 저장 흐름과 연결.

### 검증
- `python -m py_compile src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py` PASS.
- `git diff --check` PASS.
- `planner-click-mode`, `plannerSend`, `plannerSave`, `addPlannerWaypointFromEvent`, `patrol_planner`, `plannerWaypoints` 연결점 검색 확인.
- 현재 Windows 셸에는 `node` 실행 파일이 없어 JS 정적 문법 검사는 미수행. 브라우저에서 새로고침 후 기능 확인 필요.

---

## 2026-06-15 aip_main_description 빌드 설치 경로 수정

### 배경
- 사용자가 `colcon build --symlink-install --packages-up-to aip_fleet_autonomous aip_fleet_dashboard` 실행 시 `aip_main_description` 빌드 실패.
- 원인: `CMakeLists.txt`가 존재하지 않는 `launch/` 디렉터리를 `install(DIRECTORY ...)` 대상으로 포함.

### 구현 결과
- `src/aip_main_description/CMakeLists.txt`에서 설치 대상 디렉터리를 `urdf config launch`에서 `urdf config`로 수정.
- `aip_main_description`에는 현재 `urdf/`, `config/`만 존재하므로 실제 패키지 구성과 CMake 설치 규칙을 일치시킴.

### 다음 확인
- WSL에서 `colcon build --symlink-install --packages-up-to aip_fleet_autonomous aip_fleet_dashboard` 재실행 필요.

---

## 2026-06-15 autonomous launch twist_mux 의존성 명시

### 배경
- Gazebo 단독 실행은 정상이나 `fleet_autonomous.launch.py gui:=false` 실행 시 launch가 종료됨.
- `/tmp/aip_auto.log` grep 결과 원인은 `package 'twist_mux' not found`.
- `fleet_autonomous.launch.py`가 `twist_mux` 노드를 직접 실행하지만 `aip_fleet_autonomous/package.xml`에 런타임 의존성이 없었음.

### 구현 결과
- `src/aip_fleet_autonomous/package.xml`에 `<exec_depend>twist_mux</exec_depend>` 추가.

### 다음 확인
- WSL에서 `sudo apt install ros-humble-twist-mux` 또는 `rosdep install --from-paths src --ignore-src -r -y --rosdistro humble` 실행 후 재빌드 필요.

---

## 2026-06-15 autonomous launch topic_tools 의존성 명시

### 배경
- `twist_mux` 설치 후 autonomous launch가 더 진행됐으나 `/tmp/aip_auto.log`에서 `package 'topic_tools' not found` 예외 확인.
- `spawn_vehicle.launch.py`와 `central.launch.py`에서 `topic_tools` relay/throttle을 사용하지만 `aip_fleet_gazebo/package.xml`에 의존성이 없었음.
- `sim_peer_sensing_node.py` exit code 127도 함께 관찰되어, topic_tools 설치 후 재실행 시 별도 원인 여부 확인 필요.

### 구현 결과
- `src/aip_fleet_gazebo/package.xml`에 `<depend>topic_tools</depend>` 추가.

### 다음 확인
- WSL에서 `sudo apt install ros-humble-topic-tools` 후 재빌드/재실행 필요.
- `sim_peer_sensing_node.py`가 계속 exit 127이면 WSL에서 shebang/실행권한/CRLF 여부 확인 필요.

---

## 2026-06-15 Gazebo 실행 스크립트 CRLF shebang 문제 수정

### 배경
- WSL에서 `install/aip_fleet_gazebo/lib/aip_fleet_gazebo/sim_peer_sensing_node.py --help` 실행 시 `/usr/bin/env: ‘python3\r’: No such file or directory` 발생.
- 원인: `src/aip_fleet_gazebo/scripts/*.py`가 Windows CRLF 줄바꿈이라 WSL shebang이 `python3\r`로 해석됨.
- `--symlink-install` 환경에서는 install 경로가 src 원본을 가리키므로 원본 scripts 줄바꿈 수정이 필요.

### 구현 결과
- `src/aip_fleet_gazebo/scripts/*.py` 전체를 LF 줄바꿈으로 변환.
- `.gitattributes`를 추가해 `src/aip_fleet_gazebo/scripts/*.py text eol=lf`로 고정.

### 검증
- PowerShell byte scan으로 `src/aip_fleet_gazebo/scripts/*.py`에 CRLF가 남아 있지 않음을 확인.
- `git diff --check` PASS.

---

## 2026-06-15 웹 관제 대시보드 맵·포즈 표시 완성

### 배경
- 사용자 요청: `http://localhost:8080` 대시보드에서 SLAM 맵과 차량 위치를 표시하고 싶음.
- 이전 세션에서 코드 수정 완료 (SLAM `/map` 구독 추가, relay topic 수정, leader_nav lifecycle 수정) 했으나 런타임에서 맵이 표시되지 않음.

### 원인 분석
1. **SLAM 클럭 리셋**: `fleet_autonomous.launch.py` 실행 초반 시뮬 클럭이 갑작스럽게 초기화되면서 SLAM toolbox가 TF 타임스탬프 오류로 모든 스캔을 드롭함. `async_slam_toolbox_node` 로그에 연속적인 `jump back in time` 경고와 `frame '...laser_frame' discarded` 메시지 발생.
2. **대시보드 상태 캐시 없음**: `dashboard_server.py`의 `_push()` 함수가 현재 연결된 WebSocket 클라이언트에만 실시간 push하고, 신규 클라이언트 접속 시 마지막 상태(`slam_map`, `poses` 등)를 재전송하는 로직이 없었음. 따라서 브라우저를 나중에 열면 빈 화면이 됨.
3. **FastDDS XML 오류**: `fastdds_local.xml`에서 빈 `<metatrafficMulticastLocatorList/>` 요소가 파서 에러를 발생시킴 → 사용하지 않도록 제거.

### 구현 결과
- `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py`:
  - `_state_cache: dict[str, Any]` 전역 추가 — 타입별 마지막 메시지를 저장.
  - `_push()` 함수에서 메시지 타입별로 `_state_cache[msg_type] = msg` 업데이트.
  - WebSocket 신규 접속 시 `_state_cache.values()` 전부를 전송해 초기 상태를 즉시 복원.
- `run_sim.sh`, `run_central.sh` 헬퍼 스크립트 생성:
  - `rtf:=0.5` (클럭 안정화), `skip_explore:=true`, `with_patrol:=true`.
  - `supervisor_params:=supervisor_peers.yaml`, `leader_ns:=peer_1`, `with_coordinator:=false`, `with_twist_mux:=false`.
- build 디렉터리의 `dashboard_server.py`에도 변경 사항 직접 동기화 (egg-link 빌드 방식).

### 검증
- WebSocket 연결 시 수신 메시지 타입: `connected → fleet_status → slam_map (279x200, 0.05 m/cell) → poses (peer_1) → patrol_plan → map_ready`.
- Edge 브라우저 `http://localhost:8080` 에서 MAP READY (녹색), SLAM 맵 표시, peer_1 삼각형 위치 마커 확인.

### 잔여 문제 (코스메틱)
- 차량 OFFLINE 표시: 시뮬레이션에 heartbeat 퍼블리셔가 없음 (supervisor 설계상 실차 전용 기능).
- peer_2/peer_3 위치 미표시: 팔로워 AMCL 초기화 완료 후 표시될 것으로 예상.

---

## 2026-06-15 rf2o_laser_odometry optional launch 처리

### 배경
- autonomous launch 재실행 시 `package 'rf2o_laser_odometry' not found` 예외로 전체 launch가 종료됨.
- `src/rf2o_laser_odometry` 디렉터리는 존재하지만 패키지 파일이 없는 빈 디렉터리 상태.
- 현재 목표는 SLAM/웹 관제 시뮬 bringup이므로 rf2o LiDAR odometry를 필수로 요구하지 않는 쪽이 적절.

### 구현 결과
- `src/aip_fleet_gazebo/launch/spawn_vehicle.launch.py`에 `with_rf2o` launch argument 추가, 기본값 `false`.
- 기본 실행에서는 EKF만 시작하고, `with_rf2o:=true`일 때만 `rf2o_laser_odometry_node`를 함께 시작하도록 변경.

### 검증
- `python -m py_compile src/aip_fleet_gazebo/launch/spawn_vehicle.launch.py` PASS.

---

## 2026-06-15 대시보드 차량 상태 ONLINE 표시 + 차량 위치 표시 수정

### 배경
- 브라우저 대시보드에서 "0 online" 표시 문제(fleet_status 메시지는 WebSocket으로 수신되지만 UI 미갱신).
- peer_2/peer_3 차량 위치 마커 미표시 (peer_1은 정상).

---

### 문제 1: fleet_status "0 online" — `_broadcast()` UnboundLocalError

**원인:** `dashboard_server.py`의 `_broadcast()` 함수에서 `_clients -= dead` (augmented assignment)가 Python 스코핑 규칙에 의해 `_clients`를 지역 변수로 간주하게 만들어 함수 실행 중 `UnboundLocalError` 발생. 이 예외는 `asyncio.run_coroutine_threadsafe`의 Future 래퍼에 의해 silently swallowed되어 디버깅이 어려웠음.

**수정:**
- `_clients -= dead` → `_clients.difference_update(dead)` (in-place 메서드, 새 binding 없음)
- `asyncio.run_coroutine_threadsafe` → `call_soon_threadsafe(_main_loop.create_task, ...)` (예외가 실제로 노출됨)
- `_startup()`에서 `asyncio.get_event_loop()` → `asyncio.get_running_loop()` (async context에서 신뢰성 향상)
- `rclpy.init(args=sys.argv)` — `--ros-args` 파라미터 올바르게 처리
- `ExtenalShutdownException` catch 추가 (SIGTERM 시 정상 종료)

**결과:** fleet_status 수신 시 WebSocket 클라이언트에 정상 push, peer_1/2/3 모두 AUTO/ONLINE 표시.

---

### 문제 2: 시뮬레이션 heartbeat 없음 — OFFLINE 표시

**원인:** supervisor 설계상 heartbeat는 실제 차량이 자체 SW로 발행. 시뮬에는 발행 노드가 없어 watchdog이 2초 후 OFFLINE으로 전환.

**수정:**
- `src/aip_fleet_gazebo/scripts/sim_heartbeat_node.py` 신규 생성 — peer_1/2/3 heartbeat 2Hz 발행.
- `src/aip_fleet_gazebo/CMakeLists.txt`에 install PROGRAMS 추가.
- `fleet_autonomous.launch.py` t=16s 블록에 `sim_heartbeat_node.py` 노드 추가 (`use_sim_time: False` — 벽시계 기준 발행).

---

### 문제 3: 차량 위치 미표시 — `/tf` DDS 세션 경계 미통과

**원인 분석:**
1. `dashboard_server.py`의 TF fallback 타이머(`_cb_tf_poses`)가 `use_sim_time: True`로 실행되었으나 `/clock` 토픽이 sim 세션 → central 세션으로 전달되지 않아 타이머가 한 번도 발화하지 않음.
2. `use_sim_time: False`로 수정 후 타이머는 발화하지만 `/tf` 토픽이 VOLATILE QoS라 DDS 세션 경계를 넘지 못해 `map` 프레임이 대시보드 TF 버퍼에 존재하지 않음.

**수정:**
- `src/aip_fleet_bringup/launch/central.launch.py`: dashboard 파라미터 `use_sim_time: True` → `False`.
- `src/aip_fleet_gazebo/scripts/sim_pose_relay_node.py` 신규 생성 — 시뮬 세션 내에서 TF 조회 후 `/fleet/peer_poses` (RELIABLE + TRANSIENT_LOCAL QoS)로 PeerPoseArray 재발행. 이 토픽은 DDS 세션 경계를 넘어 중앙 대시보드가 수신.
- `src/aip_fleet_gazebo/CMakeLists.txt`: `sim_pose_relay_node.py` install 추가.
- `fleet_autonomous.launch.py` t=16s 블록에 `sim_pose_relay_node.py` 추가 (`use_sim_time: True` — 시뮬 클럭 기반 TF 조회).
- `dashboard_server.py` `_cb_tf_poses()`: 디버그 파일 쓰기 코드 제거, `_fleet_poses_active=True`시 즉시 early retun 유지.

**설계 원칙:** `/fleet/peer_poses`는 TRANSIENT_LOCAL이므로 대시보드가 늦게 연결되어도 최신 위치를 수신. `_cb_poses()` 수신 시 `_fleet_poses_active=True`로 전환되어 TF fallback 완전 비활성화.

---

### 수정된 파일 목록
| 파일 | 변경 내용 |
|---|---|
| `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py` | UnboundLocalError 수정, use_sim_time 제거, 디버그 코드 정리 |
| `src/aip_fleet_bringup/launch/central.launch.py` | dashboard `use_sim_time: True` → `False` |
| `src/aip_fleet_autonomous/launch/fleet_autonomous.launch.py` | sim_heartbeat + sim_pose_relay 노드 추가 |
| `src/aip_fleet_gazebo/scripts/sim_heartbeat_node.py` | 신규 — heartbeat 더미 퍼블리셔 |
| `src/aip_fleet_gazebo/scripts/sim_pose_relay_node.py` | 신규 — TF→PeerPoseArray 릴레이 |
| `src/aip_fleet_gazebo/CMakeLists.txt` | 두 스크립트 install PROGRAMS 추가 |

---

## 2026-06-15 — 웹 관제 전면 개선 (dashboard 2.0)

### 배경

사용자 요청: 시뮬레이션 웹 관제에서 모든 기능(컨트롤·순찰·구역·비전)을 딜레이 없이 부드럽게 사용 가능하도록. 실제 로봇 연결 시에도 동일하게 동작.

### 결정

| 결정 | 이유 |
|---|---|
| `index.html` 전면 재작성 (875줄 → 1560줄) | 3열 레이아웃 유지하되 탭 패널·맵 툴바·60fps 애니메이션 등 신규 아키텍처 필요 |
| 60fps rAF 루프 + 지수 평활 보간 (α=0.16) | 2Hz ROS pose 업데이트를 부드러운 마커 이동으로 변환 |
| 맵 팬/줌 (드래그·휠) 추가 | 넓은 구역 순찰 시 세부 조작 불가능 문제 해소 |
| 맵 모드 시스템 (view/goto/patrol/keepout) | 단일 클릭 핸들러로 여러 모드를 전환하는 toolbar 패턴 |
| Keepout zone: polygon 드로잉 → `/fleet/keepout_zones` (JSON String) | Nav2 costmap 필터 마스크와 독립적으로 시각화·전달 |
| 도킹 스테이션: `/goal_pose` 발행 (NavigateToPose) | 별도 서비스 없이 표준 Nav2 인터페이스 재사용 |
| Web Audio API 알림음 | 외부 라이브러리 없이 HIGH 알림 즉시 청각 피드백 |
| MCAP 녹화: `ros2 bag record` subprocess | 녹화 시작/정지를 WS 명령으로 원격 제어 |

### backend 추가 (dashboard_server.py)

- `Odometry` 구독 per vehicle → 속도(m/s)·누적 거리(m) push
- `PoseStamped` 발행 per vehicle → `/goal_pose` → NavigateToPose
- `keepout_zones` 발행 → `/fleet/keepout_zones` String(JSON)
- `cmd_navigate(vid, x, y, yaw_rad)` 메서드 신규
- `cmd_keepout(zones)` 메서드 신규
- `_start_bag()` / `_stop_bag()` 전역 함수 — subprocess.Popen ros2 bag record
- WS 커맨드 추가: `navigate_to`, `keepout_zones`, `start_bag`, `stop_bag`

### frontend 추가 (index.html)

| 기능 | 구현 |
|---|---|
| 60fps 애니메이션 | `requestAnimationFrame` + `interpolatePoses()` 지수 평활 |
| 맵 팬/줌 | `view.{tx,ty,scale}` + drag + wheel + `zoomAt()` |
| 맵 툴바 | 4모드 버튼 (view/goto/patrol/keepout) + 줌+−/fit/전체화면 |
| 이동 명령 클릭 | goto 모드 클릭 → `navigate_to` WS 전송 |
| Keepout 폴리곤 | 클릭으로 꼭짓점 추가, 더블클릭/시작점 클릭으로 닫기 |
| 도킹 스테이션 | 클릭으로 dock 위치 설정, "⚡ 도킹 이동" 버튼 |
| 탭 패널 5개 | 제어/순찰/구역/시스템/비전 |
| 차량 카드 개선 | 속도·거리·thermal 표시, 클릭으로 제어 차량 선택 |
| 커버리지 바 | 전역 + 차량별 진행률 |
| 알림음 | Web Audio API 3단 비프 (HIGH 알림 시) |
| 알림 자동 팬 | HIGH 알림 위치로 맵 자동 이동 |
| MCAP 녹화 버튼 | 헤더에 ● REC 버튼 (펄스 애니메이션) |
| 키보드 단축키 | V/G/P/K 모드·F 뷰 초기화·±줌·WASD 주행·Esc |
| Toast 알림 | 하단 토스트 (3초 자동 사라짐) |

### 검증 결과 (preview 서버 via Python http.server)

- 3열 레이아웃 1440×860: 왼쪽 255px / 중앙 857px / 오른쪽 296px ✓
- 캔버스 855×735 정상 ✓
- 6개 차량 카드 렌더링 ✓
- 목 데이터 주입: 3 online, 67% 커버리지, HIGH/WARN 알림, 3개 순찰 WP ✓
- 탭 전환 동작 확인 ✓
- `dashboard_server.py` Python 문법 검사 PASS ✓

### 수정 파일 목록

| 파일 | 변경 |
|---|---|
| `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py` | Odometry 구독, PoseStamped 발행, navigate/keepout/bag 커맨드 추가 |
| `src/aip_fleet_dashboard/static/index.html` | 전면 재작성 — 60fps·팬줌·모드·탭·keepout·dock·오디오 알림 |

### 다음 단계

- 실제 시뮬(`run_sim.sh` + `run_central.sh`) 연동 테스트
- `colcon build --symlink-install --packages-select aip_fleet_dashboard` 빌드 (symlink이므로 Python 변경은 즉시 반영)

---

## 2026-06-16 — 런타임 에러 3종 + 대시보드 카메라 UX

### 증상 (사용자 로그)

1. `RTPS_TRANSPORT_SHM Error ... open_and_lock_file failed` 대량 — WSL2 stale SHM 락
2. `[Erno 98] ... ('0.0.0.0', 8080): address already in use` → `dashboard_server` 프로세스 사망 → **웹 화면 멈춤** (WebSocket 끊김으로 맵·포즈 갱신 정지)
3. `Could not find a connection between 'map' and 'peer_1/base_link'` — peer_1 TF 트리 단절 (SLAM/AMCL 초기화 타이밍, 별도 추적)
4. UX 요청: 카메라를 크게 보고 싶다 + 맵 아래 2분할로 되돌려달라

### 결정·조치

| 문제 | 조치 | 파일 |
|---|---|---|
| SHM 락 에러 | FastDDS SHM 전송 비활성 → localhost UDP-only 프로파일 | `fastdds_local.xml` (`useBuiltinTransports=false` + UDPv4 userTransport) |
| 프로파일 미적용 | 두 스크립트에 `FASTRTPS_DEFAULT_PROFILES_FILE` export | `run_sim.sh`, `run_central.sh` |
| 8080 충돌 (화면 멈춤 직접 원인) | central 시작 전 `pkill dashboard_server` + `fuser -k 8080/tcp` | `run_central.sh` |
| stale SHM 파일 | sim 시작 전 `/dev/shm/fastrtps_*` 정리 | `run_sim.sh` |
| 카메라 위치 | 오른쪽 "비전 탭" → **중앙 맵 패널 아래 2분할 패널**로 이동 | `index.html` |
| 카메라 확대 | 박스 클릭 → 라이트박스 모달(라이브 갱신, Esc 닫기) | `index.html` |
| 멈춤 원인 가시화 | `!connected` 시 맵에 "● 서버 연결 끊김 — 자동 재연결 중" 오버레이 | `index.html` |
| 탭 정리 | 비전 탭 제거 → 제어/순찰/구역/시스템 4개 | `index.html` |

### 검증 (preview, eval 기반)

- 중앙 컬럼 = map-panel(857×577) + vision-panel(857×213, 맵 아래) ✓
- 카메라 박스 2개 나란히 (각 416×158, 동일 y=685) ✓
- mock 영상 주입 → box A/B 모두 `<img>` 렌더 ✓
- `openVisionModal('a')` → 모달 open + 라벨 "📹 peer_1" + 이미지 세팅 ✓
- 탭 4개, 구 `tab-vision` 제거 확인 ✓
- 콘솔 에러 0 ✓
- (스크린샷은 60fps rAF 루프로 캡처 도구 타임아웃 — eval 좌표로 대체 검증)

### 남은 추적

- **peer_1 TF 단절**: 재시작(정리된 스크립트) 후에도 재현되면 `ros2 run tf2_tools view_frames`로 `map→peer_1/odom`(slam_toolbox) / `peer_1/odom→peer_1/base_link`(ekf) 끊긴 지점 확인 필요. 초기화 타이밍이면 수렴 후 자동 해소.
- `git diff --check` PASS.

---

## 2026-06-19 — 시뮬 초기화 타이밍 수정 + 팀원 온보딩 문서화

### 작업 배경

실차 전환 준비 문서 작업 완료 후 시뮬레이션 작업 재개.

### 분석 및 결정

**peer_1 TF 단절 근본 원인 발견:**
- `fleet_autonomous.launch.py` t=16s: slam_toolbox 시작
- `spawn_vehicle.launch.py` t=3.5+17=20.5s: EKF 시작 (절대 시각)
- SLAM이 EKF보다 4.5초 먼저 시작 → `peer_1/odom→base_link` TF 없이 실행
- `transform_timeout=3.0s` 재시도가 4.5s 지속 → 첫 스캔 처리 지연

**bond_timeout 누락 발견:**
- `leader_nav.launch.py`: `bond_timeout: 0.0` 있음 ✓
- `autonomous_nav.launch.py` (팔로워): 누락 ❌
- `nav_follower.launch.py` (V포메이션 팔로워): 누락 ❌

### 조치

| 파일 | 변경 내용 |
|---|---|
| `fleet_autonomous.launch.py` | slam_toolbox t=16s → t=21s 분리 (EKF t=20.5s 이후 0.5s) |
| `fleet_autonomous.launch.py` | 헤더 주석 실제 타이밍과 일치 (follower_trigger t=50s, explore_lite t=60s) |
| `autonomous_nav.launch.py` | lifecycle_manager에 `bond_timeout: 0.0` 추가 |
| `nav_follower.launch.py` | AMCL + controller 두 lifecycle_manager에 `bond_timeout: 0.0` 추가 |
| `docs/TEAM_ONBOARDING.md` | 팀원 온보딩 체크리스트 신규 작성 (커밋 `b0f06c9`) |

### 커밋

- `83f96a9` fix(sim): SLAM 시작 타이밍 조정 + 팔로워 lifecycle bond_timeout 추가
- `f3ecef5` fix(nav2): 전 lifecycle_manager에 bond_timeout=0.0 추가 + 헤더 주석 정합
- `b0f06c9` docs(onboarding): 팀원 온보딩 체크리스트 추가

### 실행 테스트 결과 (headless, 2026-06-19)

TF 수정 확인: headless 시뮬 실행 후 로그 분석.
- TF 에러 ("could not find a connection"): **0건** ✅
- 제어 루프 누락 (10Hz miss): **0건** ✅
- EKF(line 156) → SLAM(line 157) 시작 순서 정상 ✅
- Navigation Goal 33회, 커버리지 87.0㎡ (34,813셀)

**신규 발견 이슈:** "Starting point in lethal space" 143건 / backup failed 216건.
peer_1이 (-6.74, -2.28) 코너 frontier에서 costmap LETHAL 고착 → BackUp 후방 벽 반복 실패.

---

## 2026-06-19 — lethal space 루프 수정

### 원인 분석

- explore_lite가 코너 소형 frontier (-6.74, -2.28)로 목표 전송
- 로봇 접근 시 벽 근거리 obstacle_layer → local costmap LETHAL(footprint_padding=0.05로 경계 0.155m)
- `ClearEntireCostmap` 후 LiDAR 즉시 재업데이트 → lethal 재지정
- BackUp: 후방 벽 0.155m 내 → "Collision Ahead" 반복

### 수정

| 파일 | 변경 |
|---|---|
| `navigate_w_collision_recovery.xml` | RoundRobin에 `ClearAll+Spin(1.57rad)+BackUp` 단계 추가 (코너 탈출 회전) |
| `fleet_autonomous.launch.py` | explore_lite `min_frontier_size: 0.5→0.75m`, `progress_timeout: 60→30s` |
| `nav2_full.yaml` (local_costmap) | `footprint_padding: 0.05 제거` → local LETHAL 경계 0.155m→0.105m |

### 커밋

- `e6a8a70` fix(nav2): lethal space 루프 3종 개선

### 테스트 결과 (재시뮬 — 수정 효과 확인)

| 지표 | 수정 전 | 수정 후 |
|---|---|---|
| lethal space 오류 | 143건 | **0건** ✅ |
| backup failed / Collision Ahead | 216건 | **0건** ✅ |
| 커버리지 | 87.0㎡ (정체) | 135.1㎡+ (진행 중) |
| Navigation 목표 | 33건 (탐색 멈춤) | 16건 (탐색 계속) |

세 가지 수정 모두 효과 발휘. 커버리지 55% 이상 추가 확보, 탐색 정체 해소.

---

## 2026-06-19 (세션 3 계속) — 금지구역 keepout zone 실제 동작 구현

### 배경

대시보드 UI에 금지구역 폴리곤 드로잉 기능이 있었으나 Nav2 costmap에 실제 반영되지 않았음.
`/fleet/keepout_zones` (String JSON) 구독 → costmap obstacle 변환 노드가 없었던 것이 원인.

### 결정

1. **costmap 주입 방식:** Nav2 ObstacleLayer `observation_sources`에 PointCloud2 토픽 추가.
   - `clearing:False` → 금지구역 포인트는 자동 소거 없이 영구 마킹.
   - 금지구역 감소 시 ClearEntireCostmap 서비스로 수동 초기화 후 현재 구역 재마킹.
2. **goal 사전 차단:** `SmacPlannerHybrid tolerance:0.75m` 스냅 → BT ABORT 루프 가능성 → 대시보드 서버단 ray-casting으로 사전 거부.

### 구현 완료

| 파일 | 변경 |
|---|---|
| `keepout_zone_node.py` (신규) | `/fleet/keepout_zones` JSON → 0.05m 격자 채우기 → `/fleet/keepout_cloud` PointCloud2 1Hz 발행; 구역 감소 시 ClearEntireCostmap 자동 호출 |
| `nav2_full.yaml` | global/local costmap observation_sources에 `keepout_cloud` 추가 |
| `dashboard_server.py` | `cmd_keepout`에 zones 저장; `cmd_navigate`에서 ray-casting 금지구역 내부 검사 → `navigate_rejected` WS 전송 + Nav2 발행 차단 |
| `index.html` | `navigate_rejected` 수신 시 고경고 toast 표시 |
| `fleet_autonomous.launch.py` | t=16s 블록에 `keepout_zone_node` 추가 |
| `setup.py` | `keepout_zone_node` 엔트리포인트 추가 |

### 커밋

- `87faf57` feat(keepout): 금지구역 costmap 주입 및 목표 좌표 사전 차단 구현

### 빌드

colcon build 2 packages PASS (경고 없음)

### 다음 작업 후보

- `feat/real-monorepo → main` PR 생성 (keepout + m-explore-ros2 직접 소스 포함 등 변경 통합)
- 실차 전환 준비 (HW-1~HW-6)

---

## 2026-06-19 (세션 4) — 웹 UI 미구현 기능 전면 구현

### 배경

에이전트가 UI에 있지만 실제 동작하지 않는 기능 4개를 발견 후 순차 구현.

### 구현 완료 항목

| 기능 | 커밋 | 상세 |
|---|---|---|
| 순찰 시작/정지 버튼 | fe28832 | patrol_node.py: /patrol_planner/cmd 구독, _paused 상태, start/stop/mode:loop 처리. UI 버튼 색상 피드백 |
| 도킹 위치 영속화 | f9c8ed8 | ~/aip_maps/dock_positions.json 저장. WS 재접속 시 자동 복원. 차량별 patrol_status 캐시 |
| 금지구역 영속화 | 60639dc | ~/aip_maps/keepout_zones.json 저장. WS 재접속/페이지 새로고침 후 자동 복원 |
| patrol 버튼 상태 동기화 | f9c8ed8 | selectVehicle() 호출 시 캐시된 상태로 버튼 즉시 갱신 |

### 확인된 기존 구현

- 순찰 경로 맵 시각화 (plannerWps): 이미 구현됨 (1119줄)
- keepout zone 맵 폴리곤: 이미 구현됨 (1074줄)
- 시뮬 시나리오 버튼: scenario_manager_node.py가 존재, with_thermal:=true 시 동작

### 다음 작업 후보

- feat/real-monorepo → main PR 생성
- 실차 전환 준비 (HW-1~HW-6)

---

## 2026-06-19 (세션 5) — 열화상 비전 대시보드 연동 + 구동 테스트

### 배경

비전 탭에 열화상 이미지가 표시되지 않던 문제. `central_fusion_node`가 `perception_central.launch.py`에만 있어 `fleet_autonomous.launch.py`에서 `/fleet/perception_viz/{vid}` 미발행.

### 결정: A 방식 채택

`/{vid}/thermal_viz` (patrol_monitor 직접 발행, sensor_msgs/Image rgb8, 24×32, 8Hz) → `dashboard_server.py`에서 구독 → 2Hz 스로틀 + PIL 8× 업스케일(→192×256) + PNG base64 → WS vision 메시지.

### 구현 내용

| 파일 | 변경 내용 |
|---|---|
| `dashboard_server.py` | `import time`, `_thermal_viz_ts` dict 추가, `/{vid}/thermal_viz` 구독, `_cb_thermal_viz()` 메서드 구현 |
| `static/index.html` | `state.thermalVision{}` 분리, `onVision()` source='thermal' 분기, `renderVision()` slot-b 열화상 전용, vision-label-b 업데이트 |

### 구동 테스트 결과

- `aip_ign_headless` + `aip_auto_thermal` + `aip_central` 순차 기동
- `/peer_1/thermal_viz` 8Hz 발행 확인
- `dashboard_server` 3대 모두 구독 (`Subscription count: 1`)
- WS 직접 검증: `type=vision, source=thermal, mime=image/png, is_png=True, size=~1.9KB` 수신 확인
- 대시보드 HTTP → 최신 코드(thermalVision, 열화상 대기) 서빙 확인
- peer_2/3 thermal은 SLAM 미완 상태에서 TF 미확립으로 sim_thermal이 skip → 정상 동작

### 현재 상태

모든 핵심 노드 실행 중: `keepout_zone_node`, `aip_fleet_dashboard`, `patrol_monitor_peer_{1,2,3}`, `sim_thermal`

### 다음 작업 후보

- feat/real-monorepo → main PR 생성
- 실차 전환 준비 (HW-1~HW-6)

---

## 2026-06-19 (세션 6) — 메인 차량 RPi 실차 세팅 완료 + FastDDS 통신 검증

### 배경

시뮬 개발 보류, 메인 차량 RPi 4B 실차 전환 준비 시작.
AP 전환(jdedu9807 → aip2.4GHz), 스왑/DOMAIN_ID/SSH 키는 직전 세션에서 완료.
이번 세션에서는 aip_ws 패키지 구조 파악 + twist_mux 통합 + FastDDS 통신 검증 진행.

### RPi 환경 현황

| 항목 | 상태 |
|---|---|
| IP | 192.168.0.18 (aip2.4GHz) |
| OS | Ubuntu 22.04 LTS Server (aarch64) |
| ROS | Humble |
| RMW | rmw_fastrtps_cpp |
| ROS_DOMAIN_ID | 42 ✅ |
| 스왑 | 2GB ✅ |
| SSH 키 | dev PC ed25519 등록 ✅ |
| Docker | 없음 (직접 설치) |
| aip_ws | `~/aip_ws/` (6패키지 빌드 완료) |

### aip_ws 패키지 구조 확인

```
~/aip_ws/src/
  aip_base/          — serial_bridge 노드 (ESP32 ↔ ROS2 브릿지)
  aip_bringup/       — robot.launch.py, ydlidar.launch.py
  aip_description/   — URDF
  aip_navigation2/   — Nav2 파라미터
  aip_slam/          — SLAM 설정
  ydlidar_ros2_driver/
```

**발견 사항:**
- `serial_bridge`: 네임스페이스 없이 `/cmd_vel`, `/odom` 발행 → PushRosNamespace로 래핑 필요
- twist_mux 미설치, heartbeat/estop 노드 없음
- FastDDS Discovery Server XML 없음 (Simple Discovery 동작)

### 변경 내용 (~/aip_ws)

#### 1. twist_mux 설치
```bash
sudo apt install ros-humble-twist-mux  # PASS
```

#### 2. `aip_bringup/config/twist_mux_main.yaml` 신규
- estop_lock(90) > central(80) > fleet_coord(50) > autonomy(10) 우선순위 규약 적용
- `/main/estop` 토픽으로 twist_mux lock

#### 3. `aip_bringup/launch/fleet_main.launch.py` 신규
- `robot.launch.py`를 `PushRosNamespace('main')`으로 래핑 → 모든 토픽이 `/main/` prefix 획득
- twist_mux 노드 추가 (`/main/cmd_vel` 출력)
- heartbeat_pub 노드 추가

#### 4. `aip_bringup/scripts/heartbeat_pub.py` 신규
- 1Hz `/main/heartbeat` (std_msgs/Bool) 발행
- `aip_bringup/CMakeLists.txt`에 install(PROGRAMS) 추가

#### 5. aip_bringup 빌드 완료
```
colcon build --packages-select aip_bringup --symlink-install → SUCCESS
```

### FastDDS 통신 검증 (Simple Discovery, aip2.4GHz)

```
RPi (192.168.0.18) → /main/heartbeat → dev PC (192.168.0.6) 수신 ✅
dev PC → /main/cmd_vel 발행 → RPi topic list에 표시 ✅
```

Simple Discovery가 동일 LAN(192.168.0.x)에서 정상 동작 확인.
fleet AP(192.168.50.x) 전환 시 Discovery Server(192.168.50.10:11811) XML 설정 필요.

### 잔여 작업

- **YDLidar 연결 확인**: `/dev/ydlidar` symlink 없음 (현재 ttyUSB0=ESP32만 연결된 상태)
- **fleet_main.launch.py 실차 구동 테스트**: ESP32 + YDLidar 모두 연결 후
- **fleet AP 전환**: `192.168.50.x` 이동 시 Discovery Server 설정
- **실차 Nav2/SLAM 설정**: `use_sim_time: false` 확인 필요

---

## 2026-06-19 — 세션 7: 실차 fleet_main 완전 구동 검증

### RPi 정보

| 항목 | 값 |
|------|-----|
| 호스트명 | AIP |
| 사용자명 | jh |
| IP (aip2.4GHz) | 192.168.0.18 |
| SSH | `ssh jh@192.168.0.18` (id_ed25519 키 등록됨) |
| ROS workspace | `~/aip_ws/` |
| 환경 | ROS2 Humble, `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`, `ROS_DOMAIN_ID=42` |

### ESP32 펌웨어 상태 확인

기존에 ESP32에 **0xAA/0x55 serial 프로토콜 펌웨어가 이미 플래시**돼 있었음을 `servo_test.py`로 확인.

```
$ python3 ~/aip_ws/src/servo_test.py 90 90 90 90
opened /dev/aip_esp32@115200
<- SERVO_FB current angles = [90, 90, 90, 90]   ✅
!! ESP32 flags: WATCHDOG                          (CMD_VEL 미수신 정상)
```

이전 세션의 "micro-ROS 펌웨어 불일치" 진단은 오판이었음. 실제로는 올바른 펌웨어가 탑재돼 있었으나
serial_bridge가 실행되지 않아 WATCHDOG 상태였던 것.

### USB 장치 매핑 (udev 규칙: `/etc/udev/rules.d/99-aip.rules`)

| 심링크 | 실제 장치 | VID | 용도 |
|--------|-----------|-----|------|
| `/dev/ydlidar` | `ttyUSB0` | 10c4 (CP210x) | YDLidar TG15 |
| `/dev/aip_esp32` | `ttyUSB1` | 10c4 (CP210x) | ESP32-S3 (serial_bridge) |

### robot.launch.py 수정 — `with_base` 인자 추가

기존 robot.launch.py는 항상 serial_bridge(base)를 기동했음.
ESP32 펌웨어 미확인 상태에서 테스트할 수 있도록 `with_base` 인자 추가:

```python
DeclareLaunchArgument("with_base", default_value="false",
                      description="ESP32 serial_bridge 활성화 여부")
```

- `with_base:=false` → YDLidar + RSP만 (ESP32 없어도 기동 가능)
- `with_base:=true` → 전체 (YDLidar + RSP + serial_bridge)

### fleet_main.launch.py 전체 구동 검증

```bash
# RPi에서 실행
source /opt/ros/humble/setup.bash && source ~/aip_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && export ROS_DOMAIN_ID=42
ros2 launch aip_bringup fleet_main.launch.py with_base:=true
```

**발행되는 토픽 (전부 `/main/` namespace)**

| 토픽 | 발행원 | 상태 |
|------|--------|------|
| `/main/scan` | YDLidar TG15 (10Hz) | ✅ |
| `/main/odom` | serial_bridge (20Hz) | ✅ |
| `/main/enc_ticks` | serial_bridge, ESP32 엔코더 (20Hz) | ✅ |
| `/main/heartbeat` | heartbeat_pub (1Hz) | ✅ |
| `/main/cmd_vel` | twist_mux 출력 | ✅ |
| `/main/servo_cmd` | serial_bridge 구독 | ✅ |
| `/main/joint_states` | robot_state_publisher | ✅ |
| `/main/robot_description` | robot_state_publisher | ✅ |

**실행 중인 노드**
```
/main/aip_serial_bridge
/main/heartbeat_pub
/main/robot_state_publisher
/main/twist_mux
/main/ydlidar_ros2_driver_node
```

### 알려진 이슈

1. **중복 노드 경고**: fleet_main을 연속 재실행 시 이전 프로세스가 완전히 죽기 전에 새 프로세스가 뜨는 경우 발생. 재실행 전 반드시 `pkill -9 -f "ros2 launch|ydlidar|twist_mux|heartbeat|serial_bridge|robot_state"` 후 2초 대기.

2. **YDLidar 체크섬 에러 (초기화 단계)**: 시작 직후 "Checksum error" 수 줄 발생하나, "Lidar has started!" 이후 자동 해소. 무해함.

### 잔여 작업

- **Nav2/SLAM 실차 파라미터 검증**: `aip_navigation2/config/nav2_params.yaml`, `use_sim_time: false` 확인
- **실차 SLAM 기동 테스트**: `ros2 launch aip_slam slam.launch.py`
- **fleet AP 전환 (192.168.50.x)**: Discovery Server XML 설정 후 재연결 테스트
- **ESP32 펌웨어 소스 확보**: 현재 플래시된 펌웨어 소스 미확인 (servo_test.py로 동작 검증만 완료)
- **motor 구동 검증**: CMD_VEL 발행 후 실제 바퀴 회전 여부 확인

---

## 2026-06-22 — main_agv SLAM+Nav2 파이프라인 실차 포팅 및 검증

### 컨텍스트
이전 세션에서 시작한 `main_agv.launch.py` 실차 포팅을 완료하고 RPi4B에서 동작 검증.

### 의사결정 및 결과

#### 1. TF 프레임 이름 수정 (가장 중요한 수정)
- **증상**: SLAM `Message Filter dropping message: frame 'laser_link' queue is full` 지속
- **원인**: fleet_main(aip_bringup)의 RSP/serial_bridge는 `frame_prefix` 없이 TF 발행:
  - RSP: `base_footprint`, `base_link`, `laser_link` (prefix 없음)
  - serial_bridge: `odom_frame: odom`, `base_frame: base_footprint` (prefix 없음)
- **수정 파일**: `config/main_agv/slam_toolbox.yaml`, `config/main_agv/nav2.yaml`
  - `odom_frame: main/odom` → `odom`
  - `base_frame: main/base_link` → `base_footprint`
  - nav2.yaml: `robot_base_frame`, `global_frame`, `local_frame` 모두 동일하게 수정

#### 2. MPPI→DWB 컨트롤러 교체
- **증상**: controller_server가 MPPI 초기화 직후 exit code -4 (SIGILL) 크래시
- **원인**: RPi4B Cortex-A72 ARM64에서 nav2_mppi_controller 사전 빌드 바이너리의 SIMD 명령어 비호환
- **수정**: `FollowPath.plugin: 'nav2_rotation_shim_controller::RotationShimController'` → `'dwb_core::DWBLocalPlanner'`
- **결과**: 크래시 없이 정상 초기화

#### 3. 구 세션 좀비 프로세스 정리
- **증상**: DDS 충돌 + CPU 과부하 (load avg 5.2~7.4)로 TF 드롭 빈번
- **원인**: 이전 launch 세션의 smoother_server(4220), waypoint_follower(4228), velocity_smoother(4230)가 종료 안 됨
- **조치**: `kill -9 4220 4228 4230`으로 수동 정리
- **결과**: load avg 5.2→3.49, TF 드롭 소멸

#### 4. Nav2 처리 주기 최적화 (RPi4B CPU 예산)
- `controller_frequency: 10→5Hz`
- `local_costmap update: 5→3Hz`
- `global_costmap update/publish: 1→0.5Hz`
- 다음 재시작 시 적용

### 최종 검증 결과

```
[lifecycle_manager]: Managed nodes are active  ← Nav2 전체 활성화 ✅
/map 발행: width=122, height=237, resolution=0.05m  ← SLAM 맵 생성 ✅
Nav2 compute_path_to_pose → SUCCEEDED (12.5ms)  ← 경로 계획 ✅
/main/autonomy_cmd_vel → twist_mux → /main/cmd_vel  ← 모터 체인 확인 ✅
DWB controller_server: no crash  ← ARM64 호환 컨트롤러 ✅
```

### 잔여 문제
1. **TF 드롭 (간헐적)**: DDS daemon 재시작 후 일시 증가, 구 프로세스 정리 후 소멸. 재발 시 `ros2 daemon stop`하지 말 것
2. **실제 주행 테스트 미완**: Nav2 goal 전송 → 실제 바퀴 회전 확인 (사용자 직접)
3. **patrol.yaml 좌표**: SLAM으로 실내 맵 완성 후 실제 좌표 입력 필요

---

## 2026-06-22 — turtlebot3_sim.launch.py 버그 수정 및 검증

### 컨텍스트
이전 세션에서 구현된 `turtlebot3_sim.launch.py` + sim config 파일들의 버그를 발견·수정.
플랜 `squishy-bubbling-barto.md`에 따른 시뮬 검증 준비.

### 수정 내용

#### 1. patrol remapping 버그 수정
- **파일**: `launch/turtlebot3_sim.launch.py`
- **증상**: patrol_node가 `/map_static` 구독 → 결코 map을 수신 못함
- **원인**: `remappings=[('/map_static', '/scout_1/map')]`로 되어 있었으나 slam_toolbox는 네임스페이스와 무관하게 절대경로 `/map`에 발행 (main_agv에서 이미 검증된 사실)
- **수정**: `('/map_static', '/scout_1/map')` → `('/map_static', '/map')`

#### 2. bt_navigator bond_timeout 추가
- **파일**: `config/turtlebot3/nav2_sim.yaml`
- **수정**: `bond_timeout: 0.0` 추가 (DDS 재연결 시 lifecycle false positive 방지. main_agv에서 검증된 설정)

### 정적 검증 결과
- Python AST: OK
- YAML 파싱 (4개 파일): OK
- colcon build: OK
- `--show-args`: 4개 인자 정상 노출
- turtlebot3_gazebo 에셋 (URDF/SDF/world): 존재 확인

### 잔여
- **실제 시뮬 실행 검증**: `ros2 launch aip_fleet_real turtlebot3_sim.launch.py with_patrol:=true` 후 Gazebo GUI + RViz2 확인 (디스플레이 필요, 사용자 직접)
- **patrol_sim.yaml 좌표**: turtlebot3_world placeholder → RViz2 보며 미세 조정 권장

---

## 2026-06-22 — 실차 R1(모터) + R2(SLAM) 검증 완료

### 문제 발생 및 원인 분석

**초기 증상 (세션 시작 시)**
- fleet_main + main_agv 이미 실행 중이었으나 `ros2 topic list` SSH에서 발견 불가 (FastDDS 디스커버리 문제)
- `laser_link` TF 타임스탬프 드롭 반복 → main_agv의 SLAM/costmap 비정상

**근본 원인**
- `serial_bridge`가 ESP32(`/dev/aip_esp32` = `ttyUSB1`)에 `write timeout` 반복 (11:22~11:24 KST)
- 이후 silent reconnect loop 진입 (로깅 중단, 22% CPU 지속)
- `/main/odom` 미발행 → `odom` TF 프레임 없음 → Nav2 전체 대기

**serial_bridge 동작 특성 파악**
- `_reconnect_step(1Hz)`: `ser.is_open == True`면 재연결 시도 안 함
- write 명령 없으면 ESP32에 전혀 쓰지 않음 → write timeout 트리거 불가
- ESP32 리셋만으로는 serial_bridge 재연결 불충분

### 해결 방법

1. **ESP32 리셋** (사용자 물리 조작)
2. **fleet_main 재시작** (tmux fleet:0에서 Ctrl+C → 재기동)
   - 재기동 후 `aip_base up on /dev/aip_esp32@115200` 로그 → ESP32 연결 즉시 확인
3. **main_agv 재시작** (tmux main_agv에서 재기동)
   - `odom` 타임아웃 에러 0건 확인

### 검증 결과

| 항목 | 결과 |
|---|---|
| R1. 모터 CMD_VEL 구동 | ✅ PASS — enc_ticks L/R +99K 동기 증가, 직진 틱 차 <30 |
| R2. 실차 SLAM 기동 | ✅ PASS — slam_toolbox 활성, global_costmap 134×250 성장 |
| R4. fleet AP 네트워크 | ✅ PASS — RPi 192.168.0.3 고정 IP, ESP32 serial 방식 무재컴파일 |

### 의사결정

| 결정 | 이유 |
|---|---|
| fleet_main 재시작 (not kill only serial_bridge) | serial_bridge가 OS 레벨 serial 상태를 초기화해야 ESP32 재연결 안정 |
| main_agv만 재시작 (fleet_main 유지) → fleet_main도 재시작 | 초기엔 main_agv만 재시작했으나 odom 여전히 없어 fleet_main 재시작 필요 |
| ESP32 firmware AGENT_IP 재컴파일 불필요 (main_agv) | main_agv ESP32는 serial 통신 방식 — WiFi UDP(AGENT_IP) 미사용 |

### 잔여 작업

- **R3. ESP32 펌웨어 소스 확보** (scout용 WiFi ESP32, 팀원 확인 필요)
- **S1. turtlebot3_sim 실제 시뮬 실행 검증** (Gazebo GUI, 디스플레이 필요)

---

## 2026-06-22 (세션 8 — main_agv ESP32 펌웨어 부팅 비프 + RPi 리셋 명령)

### 요청
사용자: 메인 차량 ESP32 펌웨어를 수정해 (1) 정상 부팅 후 초기화 완료 시 비프음 출력, (2) RPi에서 ESP32를 소프트 리셋할 수 있는 시리얼 명령 추가.

### 의사결정

| 결정 | 이유 |
|---|---|
| LEDC 채널 8 사용 (부저) | 채널 0-3 모터, 4-7 서보 이미 사용 중 |
| GPIO2 (BUZZER_PIN 기본값) | 미사용 PWM 핀 중 안전하고 보드별 기본 LED 핀 |
| `PKT_RESET=0x07`, `PKT_BEEP=0x08` | 0x06=PKT_SERVO_RELEASE 이미 사용 중 |
| payload 1B 필수 | protocol.cpp: `s.len==0` 이면 패킷 거부됨 |
| 비블로킹 상태 머신 (buzzer.cpp) | 루프 블로킹 시 watchdog(1000ms) 이내지만 모터 피드백 샘플 누락 방지 |
| onReset: 모터 정지 → flush → 30ms delay → esp_restart() | 재시작 전 모터 안전 정지 보장 |
| serial_bridge.py SCP 방식 | SSH 원격 Python 실행이 auto-mode에서 차단됨 |

### 변경 파일

| 파일 | 변경 내용 |
|---|---|
| `firmware/main_agv/config.h` | BUZZER_ENABLED, BUZZER_PIN=2, BUZZER_CH=8, PKT_RESET=0x07, PKT_BEEP=0x08 추가 |
| `firmware/main_agv/protocol.h` | ResetPacket, BeepPacket 구조체 추가 |
| `firmware/main_agv/buzzer.h` | 신규: 비블로킹 부저 인터페이스 (BUZZER_ENABLED 조건부 noop 지원) |
| `firmware/main_agv/buzzer.cpp` | 신규: 4개 패턴 상태 머신 (SINGLE/DOUBLE/BOOT/ERROR) |
| `firmware/main_agv/aip_firmware.ino` | buzzer.h/esp_system.h include, onReset/onBeep 핸들러, setup() 끝에 BOOT 비프, loop()에 tick() 추가 |
| `jh@192.168.0.3:~/aip_ws/src/aip_base/aip_base/serial_bridge.py` | CMD_RESET/CMD_BEEP 상수, Empty import, esp32_reset/esp32_beep 구독 추가 |

### RPi 적용 절차
1. `serial_bridge_patch.py` → SCP 완료 (`/home/jh/aip_ws/src/aip_base/aip_base/serial_bridge.py`)
2. `colcon build --symlink-install --packages-select aip_base` (RPi에서) + fleet_main 재시작
3. 펌웨어 플래시: Arduino IDE / PlatformIO 에서 `firmware/main_agv/` 빌드 → ESP32 플래시
4. BUZZER_PIN=2 → 실제 부저 핀으로 config.h에서 수정 필요

### 테스트 방법
```bash
# 부팅 비프: ESP32 리셋 후 비프음 2회(880Hz→1320Hz) 확인

# RPi에서 리셋 명령
ros2 topic pub --once /main/esp32_reset std_msgs/msg/Empty "{}"

# RPi에서 비프음 (패턴: 0=단음 1=이중 2=부팅 3=오류)
ros2 topic pub --once /main/esp32_beep std_msgs/msg/UInt8MultiArray "{data: [2]}"
```

### 잔여 작업
- **BUZZER_PIN 확정**: GPIO2 기본값 → 실제 부저 연결 핀으로 config.h 수정 후 플래시
- **fleet_main 재시작**: serial_bridge.py 교체 후 RPi에서 재빌드 + 재기동 필요


---

## 2026-06-22 — 차량 ROS 네임스페이스 전면 변경 (aip1/aip2/aip3)

### 결정
3개 차량의 ROS 네임스페이스를 역할 기반 명칭에서 차량 ID 기반으로 통일.

| 이전 | 이후 | 차량 |
|---|---|---|
| `main` | `aip1` | FIT0186 메인 AGV (BTS7960+MG996R) |
| `scout_1` | `aip2` | TurtleBot3 Burger |
| `scout_2` | `aip3` | STS3215 기반 커스텀 차량 |

### 이유
- 역할 기반 이름('main', 'scout')은 차량이 추가되거나 역할이 바뀔 때 혼란 발생
- 프로젝트 전용 ID(aip1~3)로 고정해 모든 노드·토픽·문서가 동일한 기준을 사용

### 변경 범위 (커밋 488eb21)
- launch 파일 6종 (main_agv, turtlebot3, custom_vehicle, fleet_real, turtlebot3_sim)
- YAML config 11종 (nav2, slam_toolbox, patrol, twist_mux — main_agv/turtlebot3/custom_vehicle)
- Python 노드 7종 (supervisor, coordinator, localizer, dashboard, sim_vehicle, sim_lidar)
- TypeScript Foxglove 패널 3종 (EStopPanel, FleetDashboard, OverridePanel)
- 보안 정책 (sros2_policy.xml), 초기화 스크립트 (sros2_init.sh)
- 네트워크 문서 (dhcp_reservations.md), FleetHeartbeat 메시지 주석
- CLAUDE.md 네임스페이스 규약 업데이트

### 빌드 결과
colcon build 6 packages — 오류 없음 (deprecation waning 3건은 기존 환경 이슈, 무관)

### 잔여 작업
- **실차 배포**: RPi들에서 `colcon build` + 노드 재시작 필요 (fleet_main 포함)
- **SROS2 키스토어 재생성**: `config/security/keystore/` 내 enclave 디렉토리명 및 permissions.xml 이 구버전(scout_1/scout_2) — `scripts/sros2_init.sh`(이미 수정됨)로 재생성 필요
- **firmware/main_agv README**: `/main/esp32_*` 예시가 `/aip1/esp32_*` 로 업데이트 완료

---

## 2026-06-22 — aip_ws 의존 제거 / fleet_main 을 aip_fleet_real 로 통합

### 결정
RPi4B 에서 `~/aip_ws`(구 aip_bringup 패키지)를 대신해 `~/aip_swarm_ws`를 단독 워크스페이스로 사용.
`fleet_main.launch.py` 하드웨어 스택을 `src/aip_fleet_real` 패키지 내로 이식.

### 이유
- `aip_ws` 는 모노레포 통합 이전의 역사적 산물. `aip_swarm_ws`의 `aip_fleet_real` 가 이미 실차 런치를 담당하므로 두 곳을 유지할 이유 없음.
- RPi4B 에서 `~/aip_ws` 폴더 자체는 보존 (팀원 참조용), 하지만 실행은 `aip_swarm_ws` 에서만.

### 추가된 파일 (커밋 29613d2)
| 파일 | 내용 |
|---|---|
| `launch/fleet_main.launch.py` | YDLidar TG15 + static TF ×2 + serial_bridge + twist_mux + heartbeat_pub |
| `aip_fleet_real/serial_bridge.py` | AA55 프로토콜, diff-drive 오도메트리, TF odom→base_footprint 발행 |
| `aip_fleet_real/heartbeat_pub.py` | 2Hz FleetHeartbeat, /proc/stat CPU 부하 |
| `config/main_agv/ydlidar.yaml` | TG15 512000 baud, frame_id=laser_link, range 0.12~12m |
| `config/main_agv/twist_mux.yaml` | central(80)/fleet_coord(50)/stuck_escape(15)/autonomy(10) |

### 아키텍처 변화
- `base_footprint → base_link → laser_link` 정적 TF 는 robot_state_publisher 대신 `static_transform_publisher` 두 개로 단순화 (URDF 의존 제거).
- `odom → base_footprint` 동적 TF: serial_bridge (diff-drive 적분).
- TF 프레임은 prefix 없음 (`base_footprint`, `base_link`, `laser_link`) — slam_toolbox.yaml과 일치.

### 빌드 검증
`colcon build --packages-select aip_fleet_real` 성공.
`ros2 pkg list | grep aip_fleet_real` + `ls install/.../lib/aip_fleet_real/` → serial_bridge, heartbeat_pub 확인.

### RPi4B 배포 절차
```bash
ssh jh@192.168.0.3
cd ~/aip_swarm_ws && git pull
pip3 install pyserial   # serial_bridge 의존
colcon build --symlink-install --packages-select aip_fleet_real
source install/setup.bash
ros2 launch aip_fleet_real fleet_main.launch.py
```

### 잔여 작업
- ESP32 BUZZER_PIN 확정 → `config.h` 수정 → Arduino 플래시 (R2-EXT)
- aip2/aip3 차량 배포 및 검증
- SROS2 키스토어 재생성 (aip1/aip2/aip3 enclave)
- PR #3 머지 (feat/real-monorepo → main)

---

## 2026-06-22 (계속) — RPi4B 실차 기동 테스트

### 진행 내용

**환경 구성**
- RPi4B(`jh@192.168.0.3`)의 `~/aip_swarm_ws`가 git 저장소가 아닌 복사본이었음 → SSH 키 생성 후 GitHub 등록, `git clone` 대신 SSH URL로 클론
- `feat/real-monorepo` 브랜치 — fleet_main 통합 커밋 2개가 미push 상태였음
- `git push` 후 PR #3(feat/real-monorepo → main) 머지 완료 → RPi에서 `git checkout main && git pull`

**빌드**
- `colcon build --symlink-install --packages-up-to aip_fleet_real --packages-skip aip_fleet_gazebo aip_fleet_sim aip_fleet_foxglove_panels`
- 첫 빌드 시 install 캐시 충돌 → `rm -rf build/aip_fleet_real install/aip_fleet_real` 후 재빌드 성공

**fleet_main.launch.py 기동 결과**
- YDLidar TG15: `/dev/ydlidar` 연결 + 10Hz 스캔 시작 ✅
- serial_bridge: `/dev/aip_esp32` 115200 baud 연결 ✅
- twist_mux: 4개 채널(central/fleet_coord/stuck_escape/autonomy) 등록 ✅
- heartbeat_pub: 2Hz 발행 ✅
- static TF: base_footprint→base_link(z=0.06), base_link→laser_link(z=0.16) ✅

**발견된 이슈**
1. `[error] Incorrect Lidar Type setting` — `ydlidar.yaml`의 `sample_rate: 9`가 TG15 실제값(20K)과 불일치. 스캔 동작에는 영향 없으나 수정 필요.
2. DS 없이 fleet_main 기동 시 DDS CLIENT 모드 노드들이 topic publish/subscribe 불가 → **DS를 먼저 기동한 뒤 fleet_main을 시작해야 함** (기동 순서 확정)
3. `docker/central/docker-compose.yml`의 fastdds-ds 서비스가 구버전 IP(192.168.50.9) 사용 중 → 직접 `fastdds discovery -i 0 -l 192.168.0.9 -p 11811` 실행으로 우회

### 확정된 기동 순서
1. Dev PC: `fastdds discovery -i 0 -l 192.168.0.9 -p 11811`
2. RPi4B: `ros2 launch aip_fleet_real fleet_main.launch.py` (DS 환경변수 포함)
3. Dev PC: `ros2 launch aip_fleet_bringup central.launch.py`
4. Dev PC: `ros2 launch aip_fleet_real main_agv.launch.py`

### 잔여 (세션 종료 시점 기준)
- fleet_main 재기동 후 토픽 수신 검증 미완료 (DS 기동 후 재시작 진행 중)
- ydlidar.yaml `sample_rate: 9` → `20` 수정 필요
- docker-compose.yml DS IP 수정 필요 (192.168.50.10 → 192.168.0.9)

---

## 2026-06-23 — 세션 10: fleet_main DDS 통신 검증 완료 (R-NEW 완료)

### 완료 항목
- **ydlidar.yaml `sample_rate: 9 → 20` 수정**: TG15 실제 샘플레이트 20K 반영, "Real points > fixed points" 경고 제거
- **docker-compose.yml DS IP 수정**: `192.168.50.10 → 192.168.0.9` (fleet 실제 서브넷 일치)
- **RPi fleet_main nohup 기동 방법 확정**:
  - ❌ `source ~/.bashrc`: 비대화형 쉘에서 `[ -z "$PS1" ] && retun` guard로 early retun → ros2 not found
  - ✅ explicit source 경로 지정:
    ```bash
    nohup bash -c "
      export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
      export ROS_DOMAIN_ID=42
      source /opt/ros/humble/setup.bash
      source /home/jh/aip_swarm_ws/install/setup.bash
      ros2 launch aip_fleet_real fleet_main.launch.py
    " > /tmp/fleet_main.log 2>&1 </dev/null &
    ```
- **dev PC ↔ RPi DDS 통신 검증 완료**:
  - FastDDS Simple Discovery (ROS_DOMAIN_ID=42, rmw_fastrtps_cpp) — DS 없이도 동작
  - `/aip1/heartbeat`: `vehicle_id=aip1, state=1, battery_pct=100.0` ✅
  - `/aip1/scan`: `frame_id=laser_link` (YDLidar 10Hz) ✅
  - `/aip1/odom`: `frame_id=odom, child_frame_id=base_footprint` ✅
  - `/aip1/cmd_vel`, `/aip1/enc_ticks`, `/aip1/override_cmd_vel` 등 13개 토픽 전부 수신 ✅
- **`REAL_VEHICLE_OPERATION.md` 수정**:
  - SSH IP 192.168.0.18 → 192.168.0.3 수정
  - nohup 백그라운드 실행 예제 explicit source 경로로 업데이트

### 주요 결정
- DS(Discovery Server) 없이 Simple Discovery만으로 fleet 네트워크 내 DDS 통신 정상 동작 확인
  → 이전 "DS 먼저 기동 필수" 요건이 틀렸음. 같은 서브넷 내에서는 multicast Simple Discovery 충분.
- `docker-compose.yml`의 DS 서비스는 외부/이기종 네트워크 연결 시만 필요

### 다음 단계
1. **R2-실차**: main_agv.launch.py 실행 → SLAM 맵 생성 + Nav2 자율주행 테스트
2. **R2-EXT**: ESP32 부저 펌웨어 플래시 (BUZZER_PIN 실핀 확인 후)
3. **R3**: ESP32 펌웨어 소스 위치 팀원 확인

---

## 2026-06-23 — 세션 11: RViz 실차 설정 + 웹 대시보드 버그 수정

### 배경
세션 10에서 실차 가동 + Nav2 활성화까지 완료. 이번 세션에서 RViz 실차 구성 파일 신규 작성 및 웹 대시보드 미구현/버그 항목 수정.

### 수정 완료

**1. `src/aip_fleet_real/rviz/main_agv.rviz` 신규 생성 (aip1 실차용 RViz)**
- 기존 `phase2.rviz`(시뮬 peer_1/2/3 기준)를 실차 aip1용으로 재작성
- 주요 변경:
  - Map 토픽: `/map_static` → `/map` (SLAM toolbox 발행 토픽)
  - peer_1/2/3 RobotModel 제거 (실차 robot_description 없음)
  - peer_1/2/3 LaserScan → `/aip1/scan` (Best Effort)
  - AMCL particles/pose 제거 (SLAM 모드)
  - TF 프레임: `map, odom, base_footprint, base_link, laser_link` (비네임스페이스)
  - Global/Local Costmap 추가 (`/aip1/global_costmap/costmap`, `/aip1/local_costmap/costmap`)
  - Nav Plan → `/aip1/plan`, MPPI Trajectories → `/aip1/trajectories`
  - Patrol Path → `/aip1/patrol_path_viz`, Thermal FOV → `/aip1/arm_fov_marker`
  - Odom 표시 추가 (`/aip1/odom`, RELIABLE)
  - SetGoal → `/aip1/goal_pose`, SetInitialPose → `/aip1/initialpose`
- `setup.py`: `rviz/*.rviz` 설치 규칙 추가
- 실행: `rviz2 -d ~/aip_swarm_ws/install/aip_fleet_real/share/aip_fleet_real/rviz/main_agv.rviz`

**2. `dashboard_server.py` TF 조회 버그 수정**
- 버그: `_cb_tf_poses`에서 모든 차량을 `{vid}/base_link` 형태로 조회 → 실차(aip1/2/3)는 `base_link` (비네임스페이스)라 위치 미표시
- 수정: `_TF_BASE_FRAME` 클래스 변수 추가 → 실차는 `base_link`, 시뮬은 `{vid}/base_link`로 분기
  ```python
  _TF_BASE_FRAME = {'aip1': 'base_link', 'aip2': 'base_link', 'aip3': 'base_link'}
  base_frame = self._TF_BASE_FRAME.get(vid, f'{vid}/base_link')
  ```

**3. `dashboard_server.py` SLAM 맵 자동 소스 전환**
- 실차 환경에서 `/map_static`이 없고 `/map`만 있을 때 사용자가 수동으로 "SLAM맵" 버튼을 눌러야 지도가 보이는 UX 문제
- 수정: `_cb_map`에서 `/map` 첫 수신 시 `map_static` 캐시가 없으면 자동으로 `map` 소스로 전환

**4. `index.html` 선택 차량 E-Stop 해제 버튼 추가**
- 버그: "선택 차량 정지"(`estopOne()`)는 있었으나 "선택 차량 해제" 버튼이 없어 단일 차량 estop 해제가 불가능했음
- 수정:
  - `releaseOne()` JS 함수 추가 (`release_estop` WS 명령)
  - UI에 "선택 차량 해제" (btn-orange) 버튼 추가 (선택 차량 정지 옆)
  - "전체 정지 해제"를 별도 행(전체 너비)으로 분리하여 구분 명확화

### 빌드 결과
- `colcon build --packages-select aip_fleet_real aip_fleet_dashboard --symlink-install` → 2 packages finished ✅

### 주요 결정
- 실차 TF 프레임은 네임스페이스 없음(`base_link`) — fleet_main.launch.py의 RSP가 `frame_prefix=''`로 기동되기 때문
- 대시보드는 실차/시뮬 혼용 환경 지원: `_TF_BASE_FRAME` dict로 차량별 프레임 분기
- SLAM 맵 자동 소스 전환: `map_static` 캐시 없을 때만 전환 → 시뮬 환경 영향 없음

### 다음 단계
1. RViz 실차 확인: `rviz2 -d main_agv.rviz` 후 LaserScan/TF/Costmap 표시 확인
2. 웹 대시보드 재시작 후 aip1 위치 마커 표시 확인
3. R2-EXT: ESP32 부저 펌웨어 플래시 (BUZZER_PIN 실핀 확인 후)
4. 순찰 미션 end-to-end 테스트 (`main_agv.launch.py with_patrol:=true`)

---

## 2026-06-23 — 세션 12: 토픽 구조 버그 수정 + 문서 전면 현행화

### 배경
세션 11 이어받기. 문서 현행화 + 실차 토픽 구조 일관성 점검 요청.

### 토픽 구조 점검 결과

기존 네임스페이스(`main`/`scout_N`/`peer_N`)와 현재 실차(`aip1/2/3`) 간 불일치 전수조사.

**발견된 버그 2건 수정:**

**1. `config/main_agv/patrol.yaml` — vehicle_id: `main` → `aip1`**
- 버그: `patrol_node`가 `/main/navigate_to_pose` 액션을 찾으려 함
- 위치: `src/aip_fleet_real/config/main_agv/patrol.yaml` line 17
- 수정: `vehicle_id: main` → `vehicle_id: aip1`
- 영향: `with_patrol:=true`로 기동 시 순찰 미션 즉시 실패하는 버그

**2. `keepout_zone_node.py` — `_VEHICLES` 하드코딩 → 파라미터화**
- 버그: `_VEHICLES = ['peer_1', 'peer_2', 'peer_3']` 하드코딩 → 실차 배포 시 costmap clear 서비스 경로 오류
- 수정: `declare_parameter('vehicle_ids', ['aip1', 'aip2', 'aip3'])` 로 파라미터화
- 참고: 현재 시뮬 launch에서만 실행되므로 실차 즉각 영향은 없었으나 추후 통합 시 버그

**정상 확인된 항목 (이미 aip1/2/3 사용):**
- `supervisor_node.py`: DEFAULT_VEHICLES = ['aip1', 'aip2', 'aip3'] ✅
- `supervisor.yaml`: vehicle_ids: ["aip1", "aip2", "aip3"] ✅
- `coordinator_node.py`: leader_ns='aip1', follower_ns='aip2' (기본값) ✅
- `central.launch.py`: supervisor.yaml에서 읽어옴 ✅
- `turtlebot3.launch.py` / `turtlebot3/patrol.yaml`: vehicle_id: aip2 ✅

**시뮬 전용 (정상 — 시뮬에서만 실행):**
- `fleet_autonomous.launch.py`: peer_1/2/3 (시뮬 전용)
- `scout_localizer_node.py`: scout_N (UWB 전용, 실차 배제 결정)

### 빌드 결과
- `colcon build --packages-select aip_fleet_autonomous aip_fleet_real --symlink-install` → 2 packages finished ✅

### 문서 현행화 완료

| 문서 | 변경 내용 |
|---|---|
| `docs/ARCHITECTURE.md` | 전면 재작성 — aip1/2/3 실차 토픽 그래프, TF 구조, 파이프라인, QoS 매트릭스 |
| `docs/TEAM_ONBOARDING.md` | 전면 재작성 — aip2/aip3 팀원용 (IP/네임스페이스/launch/TF CAVEAT) |
| `docs/HANDOFF.md` | §3 암묵적 규칙 + §5 현재 상태 업데이트 (2026-04-20 → 2026-06-23) |
| `docs/HANDOFF_REAL_WS.md` | deprecation 강화 + 현재 실차 현황 표 추가, scout_N → aip1/2/3 |
| `docs/SETUP_RPI4.md` | 헤더 scout_1/2/main → aip1/2/3 수정, FastDDS DS 설명 현행화 |

### 주요 결정
- 시뮬 전용 파일(`fleet_autonomous.launch.py`, `scout_localizer_node.py`)의 peer_N/scout_N은 수정하지 않음 — 시뮬용이므로 정상
- keepout_zone_node의 vehicle_ids는 파라미터로 외부화. 기본값이 ['aip1','aip2','aip3']이므로 실차 배포 시 별도 설정 불필요

### 다음 단계
1. **R5 실차 확인**: RViz + 대시보드 실차 검증 (이전 세션에서 코드 완료)
2. **aip2 TF frame_prefix**: 담당 팀원이 실차 테스트 후 결정 필요
3. **R2-EXT**: ESP32 부저 플래시
4. **순찰 미션**: `with_patrol:=true` end-to-end 테스트 (patrol.yaml vehicle_id 수정됨)

---

## 2026-06-23 (세션 10) — Docker 구조 논의 + deploy_main_agv.sh 기동 안내 현행화

### Docker 유지 결정

**결정**: `docker/central/docker-compose.yml` 현행 구조 그대로 유지.

**이유**:
- 개발 PC(Ubuntu 22.04 Desktop)와 차량 온보드(RPi4B Ubuntu 22.04 Server) 환경이 다름
- Docker는 환경 차이를 흡수하는 레이어로 적합 (restart 정책, 이식성)
- InfluxDB는 서드파티 DB이므로 Docker가 가장 적합한 배포 방식

**현재 컨테이너별 역할 재확인**:

| 서비스 | 이미지 | 실제 필요성 |
|---|---|---|
| `fastdds-ds` | ros:humble-ros-base | 동일 서브넷에서 Simple Discovery로 동작하지만, 재부팅 자동복구를 위해 유지 |
| `uros-agent` | microros/micro-ros-agent | aip1은 serial_bridge 사용 중 — ESP32 직접 UDP 연결 계획 시 활성화 |
| `dashboard` | ros:humble-ros-base + install/ 볼륨 | 커스텀 ROS2 패키지 의존으로 공개 이미지 불가 → 볼륨 마운트로 해결 |
| `rosbag-recorder` | ros:humble-ros-base | 자동 롤링 rosbag 기록 |
| `influxdb` | influxdb:2.7 | 서드파티 DB — Docker가 가장 적합. 아직 ROS2 노드 연결 미완 |

### deploy_main_agv.sh 기동 안내 현행화

기존 기동 안내 섹션이 구 네임스페이스(`/main/`, `~/aip_ws/`, `aip_bringup` 패키지)를 참조하고 있어 수정:
- `~/aip_ws/install/setup.bash` → `rpi_bringup.sh aip1` 사용으로 대체
- `/main/scan`, `/main/odom` → `/aip1/scan`, `/aip1/odom`
- Nav2 목표: `ros2 topic pub /main/goal_pose` → `ros2 action send_goal /aip1/navigate_to_pose`
- 맵 저장 경로: `/home/jh/maps/` → `/home/$(whoami)/maps/` (범용화)

### 다음 단계 (변동 없음)
1. **R5 실차 확인**: lidar_type 0 수정 후 ydlidar + SLAM 재테스트 필요
2. **aip2 TF frame_prefix**: 담당 팀원 실차 테스트 후 결정
3. **R2-EXT**: ESP32 부저 플래시 (BUZZER_PIN 실핀 확인 필요)
4. **순찰 미션**: `with_patrol:=true` end-to-end 테스트

---

## 2026-06-23 — 세션 13: 커버리지 개선 + URDF 0623 리뷰/수정

### 배경
- 커버리지 UI 기능 개선 요청 + 팀원이 제공한 새 URDF 파일 검토/수정 요청.

---

### 1. 커버리지 플래너 OccupancyGrid 장애물 필터링 (patrol_planner_node.py)

**문제:** 커버리지 웨이포인트가 벽/장애물을 통과하는 경로를 생성해도 필터링 없음.

**구현:**
- `/map` + `/{ns}/map` TRANSIENT_LOCAL QoS 구독 → `self._occ_grid` 캐시
- `_is_free(wx, wy, inflation_cells=1)`: 월드 좌표 → 격자 변환, 인플레이션 1셀 검사 (val ≥ 65 = 장애물)
- `set_coverage_polygon`, `coverage_box`, `_generate_coverage`에 `[wp for wp in wps if self._is_free(*wp)]` 적용
- OccupancyGrid 없을 때 → 필터 패스 (기존 동작 유지)

---

### 2. 커버리지 UI 개선 (index.html)

**문제 및 수정:**

1. **커버리지 폴리곤 영속화**: 경로 생성 후에도 초록 반투명 폴리곤 유지.
   - `coveragePolygon` 상태 추가, `generateCoverage()` 시 `state.coveragePolygon=[...draft]`

2. **커버리지 영역 삭제 버튼**: "🗑 커버리지 영역 삭제" 버튼 추가.
   - `clearCoveragePolygon()`: coverageDraft/Polygon/coverageGenVids 초기화

3. **드래그 사각형 그리기 방식**: 점 클릭 폴리곤 → 마우스 드래그 사각형으로 교체.
   - `coverageRectDrag: {active, x1,y1,x2,y2}` 상태, mousedown/move/up 핸들러
   - 최소 크기 0.2m×0.2m 이상 드래그 시 4꼭짓점 폴리곤 자동 확정

4. **커버리지 경로 시각화 수정**: 행별 쌍 연결 (i=0→1, 2→3 …)으로 벽 통과 연결선 제거.
   - `coverageGenVids[vid]` 플래그: 커버리지 생성된 차량 여부 추적

---

### 3. URDF 0623 (final_agv_project_assembly_0623) 리뷰 및 수정

**원본 문제 (SolidWorks 수출 버그):**
- `base_link` STL 없음 → 팀원이 0623 재수출로 해결
- 바퀴 pitch 오차: left=0.60835rad, right=-1.0729rad → 0 으로 수정
- ball_caster fixed → 스위블(Z)+롤(Y) 2-DOF continuous
- arm_joint effort=0/velocity=0 → STS3215 사양 (1.5 N·m, 5.0 rad/s)
- lidar_link mass=0 → 0.152 kg, 원통 근사 관성 추가
- ROS 표준 `base_footprint` 추가 (z=0.049338m: wheel_radius 60mm - wheel_joint_z 10.662mm)

**RViz 확인 결과 — 바퀴 높이 수정:**
- 바퀴 아래 절반이 지면 아래 잠김 → `base_footprint_joint z=0.049338m` 으로 해결
- `urdf_preview.rviz` Fixed Frame: `base_link` → `base_footprint`

---

### 4. URDF joint axis 수정 (세션 13 후반)

**근본 원인 분석:**

| 문제 | 원인 | 우리 책임? |
|---|---|---|
| 바퀴 동전 스핀 (axis green) | pitch→0 수정 후 child frame 회전, 기존 axis "0 1 0" 이 -Z(수직) 로 매핑 | ✅ 우리가 도입 |
| arm_joint_1 파란축 회전 | 원본 axis "0 0 1" (Z), 수직 yaw는 "0 1 0" (Y) 이어야 함 | ❌ 원본 SolidWorks |
| arm_joint_4 초록축 회전 | 원본 axis "0 -1 0" (-Y), "0 0 1" (Z/파랑) 이어야 함 | ❌ 원본 SolidWorks |
| arm_joint_2,3 pivot 위치 | STL mesh 원점이 링크 중심 (±80mm 대칭) — SolidWorks 좌표계 재배치 필요 | ❌ 원본 SolidWorks |

**수학적 근거 (바퀴):**
- `T_left(rpy="-1.5708 0 -1.5708") * [0,1,0]ᵀ = [0,0,-1]` → 수직축 스핀 (버그)
- `T_left * [0,0,1]ᵀ = [1,0,0]` → 바퀴 횡축(X) = 정상 롤링

**수정 완료:**
- 좌/우 바퀴: `axis xyz="0 1 0"` → `"0 0 1"` (로컬 Z = 바퀴 회전축)
- arm_joint_1: `axis xyz="0 0 1"` → `"0 1 0"` (수직 yaw 초록축)
- arm_joint_4: `axis xyz="0 -1 0"` → `"0 0 1"` (손목 파란축)

**보류:**
- arm_joint_2, arm_joint_3 pivot 위치: SolidWorks 좌표계 재배치 필요 → 팀원에게 수정 요청 (2026-06-23)

### 커밋 현황
- 커버리지/URDF 수정 내용 커밋+푸시 완료 (세션 13 초반)
- arm axis 수정 (세션 13 후반) — 추가 커밋 예정

### 다음 단계
1. **arm_joint_2/3 pivot** — 팀원 SolidWorks 수정 후 재수출 대기
2. **R6 순찰 미션 E2E 테스트** — patrol.yaml aip1 수정 완료, 실차 테스트 대기
3. **R5 RViz 실차 확인 + 대시보드 재검증** — 코드 완료, 실차 연결 후 테스트

---

## 2026-06-23 — main+sub 통합본을 팀 main 표준으로 재정렬

### 배경

팀 main 폴더의 최신 `ARCHITECTURE.md`를 확인한 결과, 표준 차량 ID는 `aip1`, `aip2`, `aip3`이며 구형 `main`, `scout_1`, `scout_2` 네임스페이스는 폐기 대상으로 문서화되어 있었다. 또한 팀 main의 `FleetHeartbeat.msg`는 `vehicle_id`, `stamp`, `state`, `battery_pct`, `cpu_load`, `active_behaviors` 필드를 가진 구형 계약이었다.

기존 통합본은 `scout_1` 실차 heartbeat를 받기 위해 신형 heartbeat 계약으로 바뀌어 있었고, 이 상태에서는 팀 main에서 이미 동작하는 `aip1` heartbeat와 같은 프로세스에서 호환될 수 없었다.

### 결정

- 원본 팀 main 폴더는 수정하지 않는다.
- `C:\Projects\aip-swarm-ws-main+sub` 통합본을 팀 main 구조에 맞춘다.
- 기본 토픽/차량 ID는 `aip1`, `aip2`, `aip3`로 고정한다.
- `scout_1`/`scout_2` alias는 기본값이 아니라 현장 임시 호환 옵션으로만 둔다.
- 팀 main 문서 기준에 맞춰 `run_central.sh` 기본 discovery를 FastDDS Simple Discovery로 둔다.
- Discovery Server가 필요한 현장 조건에서는 `AIP_DISCOVERY_MODE=server`로 명시 실행한다.

### 변경 결과

- `src/aip_fleet_msgs/msg/FleetHeartbeat.msg`를 팀 main 표준 계약으로 복구.
- `aip_fleet_supervisor/supervisor_node.py` heartbeat 복사 로직을 구형 표준 필드 기준으로 수정.
- `src/aip_fleet_bringup/config/supervisor.yaml` 기본 alias를 `aip1=aip1`, `aip2=aip2`, `aip3=aip3`로 변경.
- `aip_fleet_dashboard/dashboard_server.py` 기본 alias도 동일하게 변경.
- `supervisor_node.py`가 `AIP_VEHICLE_TOPIC_ALIASES` 환경변수를 읽어 임시 alias를 적용할 수 있게 수정.
- `run_central.sh`에서 Discovery Server 강제 기본값을 제거하고 Simple Discovery 기본값으로 변경.

### 검증

- `colcon build --symlink-install --packages-select aip_fleet_msgs aip_fleet_supervisor aip_fleet_dashboard aip_fleet_bringup` 통과.
- `python3 -m py_compile`로 supervisor/dashboard/combined script 문법 확인 통과.
- `colcon test --packages-select aip_fleet_supervisor` 통과: 30개 테스트 전부 통과.
- 통합본 서버 재시작 후 `http://127.0.0.1:8080/` 응답 200 확인.
- 브라우저에서 `aip1`, `aip2`, `aip3` 카드 표시 확인.

### 다음 시작점

현재 세 차량은 웹에서 모두 `OFFLINE`이다. 이는 카드 렌더링 문제가 아니라 표준 `/aip1/heartbeat`, `/aip2/heartbeat`, `/aip3/heartbeat`가 중앙에 들어오지 않는 상태다.

다음 세션에서는 먼저 `aip1`이 Simple Discovery 환경에서 `/aip1/heartbeat`를 실제로 중앙 PC에 노출하는지 확인한다. 그 다음 `scout_1`과 `scout_2`는 팀 표준에 맞춰 `/aip2/heartbeat`, `/aip3/heartbeat` 구형 계약 발행으로 전환하거나, 차량 쪽 adapter를 추가하는 방향으로 진행한다.

---

## 2026-06-23 — UDP status overlay로 aip2/aip3 웹 online 임시 복구

### 배경

통합본을 팀 main 표준 `FleetHeartbeat`로 되돌린 뒤, sub 실차 두 대는 여전히 신형 heartbeat 계약을 사용하고 있음이 확인됐다. `.4`의 `ros_topic_bridge.py`는 `robot_id`, `healthy`, `cmd_stale`, `battery_percentage` 등 신형 필드를 사용한다. `.5` workspace의 `aip_fleet_msgs` 생성물도 신형 필드 기반이다.

중앙 한 프로세스에서 구형/신형 `aip_fleet_msgs/msg/FleetHeartbeat`를 동시에 import할 수 없으므로, 토픽 alias만으로는 웹 online 표시를 복구할 수 없었다.

### 변경

- `dashboard_server.py`에 UDP status overlay listener 추가.
- 기본 포트는 `0.0.0.0:19050`.
- legacy 표시 매핑 추가:
  - `main -> aip1`
  - `scout_1 -> aip2`
  - `scout_2 -> aip3`
- `/fleet/status`가 offline을 내더라도 UDP status가 TTL 안에 들어오면 웹 표시에서 online으로 합성.

### 임시 실행

- `.4` 호스트에 `/tmp/status_aip2.py` 실행.
  - `turtlebot3_humble` 컨테이너 running 여부를 `aip2` status로 송신.
- `.5` 호스트에 `/tmp/status_aip3.py` 실행.
  - `docker-robot-1` 컨테이너 running 여부를 `aip3` status로 송신.

### 검증

- `colcon build --symlink-install --packages-select aip_fleet_dashboard aip_fleet_bringup` 통과.
- `dashboard_server.py` py_compile 통과.
- 중앙 웹 재시작 후 `UDP status overlay listening on 0.0.0.0:19050` 로그 확인.
- 브라우저에서 `2 online` 확인.
- `aip2`, `aip3`는 `MANUAL`로 표시됨.
- `aip1`은 아직 `OFFLINE`.

### 다음 시작점

`aip1`은 `192.168.0.3` SSH 포트가 열려 있으나 `aip1/<REDACTED_PASSWORD>` 로그인은 실패했다. 팀원에게 `.3` 접속 계정 또는 `/aip1/heartbeat` 실행 상태 확인을 받아야 한다.

UDP status overlay는 임시 표시 계층이다. 정식 해결은 `aip2/aip3` 차량 쪽에서 팀 main 표준 `/aip2/heartbeat`, `/aip3/heartbeat` 구형 계약을 발행하도록 전환하는 것이다.

---

## 2026-06-23 — aip1 ping overlay로 3대 웹 표시 달성

### 확인

사용자가 `<REDACTED_PASSWORD>`을 제공해 `192.168.0.3` SSH 로그인을 재시도했다. `aip1@192.168.0.3` + `<REDACTED_PASSWORD>`은 실패했고, `aip`, `ubuntu`, `pi`, `robot`, `user`, `main`, `agv`, `aip1` 계정명에 대해서도 `<REDACTED_PASSWORD>` 로그인이 모두 실패했다.

다만 `192.168.0.3` ping과 SSH 포트는 살아 있으므로 네트워크 생존은 확인됐다.

### 변경

- main 차량 내부는 수정하지 않음.
- `dashboard_server.py`에 ping status overlay 추가.
- 기본 ping target은 `aip1=192.168.0.3`.
- ping 성공 시 `aip1`을 웹 표시에서 `MANUAL` 상태로 합성하되, status는 `network_ping_only_no_ssh`로 둔다.

### 검증

- `colcon build --symlink-install --packages-select aip_fleet_dashboard aip_fleet_bringup` 통과.
- `dashboard_server.py` py_compile 통과.
- 중앙 웹 재시작 후 `Ping status overlay targets: {'aip1': '192.168.0.3'}` 로그 확인.
- 브라우저에서 `3 online` 확인.
- `aip1`, `aip2`, `aip3` 모두 `MANUAL` 표시.

### 다음 시작점

현재 `3 online`은 웹 표시 관점의 임시 상태다. `aip1`은 ping 기반, `aip2/aip3`는 컨테이너 생존 기반 UDP overlay다. 정식 상태는 각 차량의 표준 `/aipN/heartbeat` 수신으로 전환해야 한다.
---

## 2026-06-23 — aip1 접속 확인 및 3대 웹 표시 복구

### 배경

사용자가 aip1 접속 정보로 `jh@192.168.0.3`, 비밀번호 `<REDACTED_PASSWORD>`, 장치명 `AIP`를 제공했다. 목표는 원본 team main 폴더를 수정하지 않고 `C:\Projects\aip-swarm-ws-main+sub` 통합본에서 `aip1/aip2/aip3` 세 대를 웹 관제에 표시하는 것이다.

### 확인된 것

- `jh@192.168.0.3` SSH 접속 성공.
- aip1 hostname은 `AIP`, IP는 `192.168.0.3/24`.
- aip1에는 Docker가 없고 `/home/jh/aip_swarm_ws` ROS workspace가 있다.
- `aip_fleet_real heartbeat_pub`는 `/aip1/heartbeat`만 발행하는 안전한 heartbeat 전용 노드다.
- aip1 내부에서 `/aip1/heartbeat` echo는 성공했다.
- 중앙 WSL에서는 Simple Discovery와 Discovery Server 모드 모두 `/aip1/heartbeat` discovery가 실패했다.
- Discovery Server를 재기동한 뒤에도 중앙 WSL echo는 실패했다.
- aip1 -> 중앙 `192.168.0.8` ping은 성공해 L3 네트워크 문제보다는 DDS discovery/locator 문제로 판단했다.

### 결정 및 조치

- 원본 main 폴더와 aip1 workspace 코드는 수정하지 않았다.
- aip1에는 runtime 프로세스만 실행했다.
  - `heartbeat_pub`: 실제 구형 스키마 heartbeat 확인용.
  - `/tmp/status_aip1.py`: 웹 표시용 UDP status overlay.
- aip2/aip3의 `/tmp/status_aip2.py`, `/tmp/status_aip3.py`도 재기동했다.
- 중앙 dashboard는 ping overlay 없이 UDP overlay만으로 검증했다.

### 결과

- 웹 브라우저에서 `3 online` 확인.
- 카드 상태:
  - `aip1 MANUAL`, `udp_status_only`
  - `aip2 MANUAL`, `udp_status_only`, `turtlebot3_humble`
  - `aip3 MANUAL`, `udp_status_only`, `docker-robot-1`
- 저장맵 로드 성공:
  - `전체맵/저장맵 · 201x167 · 0.05 m/cell`
- Discovery Server 안정 기동용 helper 추가:
  - `scripts/start_fastdds_ds.sh`
  - `setsid`로 shell과 분리해 `fast-discovery-server -i 0 -l 192.168.0.8 -p 11811`를 유지한다.
- 상태 overlay 운영 helper 추가:
  - `scripts/manage_status_overlays.py`
  - `start`, `stop`, `status` 지원.
  - 비밀번호는 파일에 저장하지 않는다.
  - 실제 `status` 검증에서 `aip1/aip2/aip3` overlay 및 컨테이너 상태 확인 성공.
- 한글 운영 절차서 추가:
  - `docs/WEB_CONTROL_RUNBOOK_KO.md`

---

## 2026-06-23 — UDP 상태 표시를 중앙 ROS heartbeat adapter로 승격

### 배경

사용자가 정식으로 밀고 가면 팀원이 만든 main 폴더를 건드려야 하는지 질문했다. 기존 상태는 dashboard가 UDP status overlay를 직접 받아 카드 online 표시를 복구한 상태였고, 이는 웹 표시에는 충분하지만 team main의 표준 경로(`/aipN/heartbeat` -> `/fleet/status`)와는 한 단계 떨어져 있었다.

### 결정

- team main 원본 폴더는 수정하지 않는다.
- 팀원 설계의 표준 차량 ID와 토픽 경로는 유지한다.
- 중앙 통합본에만 compatibility adapter를 추가한다.
- 차량 소스 코드는 수정하지 않고 `/tmp/status_aipN.py` helper만 유지한다.

### 변경

- `src/aip_fleet_bringup/scripts/udp_status_heartbeat_adapter.py` 추가.
- `central_real_combined.py`에 adapter 노드 추가.
- `aip_fleet_bringup/CMakeLists.txt`에 adapter 설치 추가.
- `scripts/manage_status_overlays.py` 기본 송신 포트를 `19051`로 변경.
- `docs/WEB_CONTROL_RUNBOOK_KO.md`를 adapter 경로 기준으로 갱신.

### 검증

- `python3 -m py_compile` 통과.
- `colcon build --symlink-install --packages-select aip_fleet_bringup` 통과.
- 중앙 재시작 후 adapter 로그 확인:
  - `UDP heartbeat adapter listening on 0.0.0.0:19051 for ['aip1', 'aip2', 'aip3']`
- 차량 helper 재시작 후 브라우저 확인:
  - `3 online`
  - `aip1/aip2/aip3` 모두 `MANUAL`
  - 저장맵 `전체맵/저장맵 · 201x167 · 0.05 m/cell`

### 다음 세션 시작점

현재 상태는 dashboard direct UDP overlay보다 정식화되었다. 웹은 supervisor의 `/fleet/status`를 통해 상태를 받는다. 그러나 완전 정식은 아직 아니다. 차량이 직접 `/aipN/heartbeat`를 발행하거나, 중앙 WSL DDS discovery 문제가 해결되어야 한다.

---

## 2026-06-23 — adapter 단독 경로 검증

### 배경

UDP heartbeat adapter를 추가했지만 dashboard의 예전 direct UDP overlay 포트 `19050`도 기본으로 열려 있어, 나중에 상태 표시 문제가 생겼을 때 원인을 가릴 수 있었다.

### 변경

- `dashboard_server.py`의 `AIP_UDP_STATUS_PORT` 기본값을 `0`으로 변경했다.
- direct UDP overlay는 기본 비활성화하고, 필요한 경우에만 `AIP_UDP_STATUS_PORT=19050`으로 켜도록 했다.
- `WEB_CONTROL_RUNBOOK_KO.md`의 포트 확인 절차를 갱신했다.

### 검증

- `py_compile` 통과.
- `colcon build --symlink-install --packages-select aip_fleet_dashboard aip_fleet_bringup` 통과.
- 중앙 재시작 후 `19050`은 열리지 않고 `19051` adapter만 열림.
- 로그:
  - `UDP heartbeat adapter listening on 0.0.0.0:19051`
  - `UDP status overlay disabled`
- 브라우저:
  - `3 online`
  - 저장맵 `전체맵/저장맵 · 201x167 · 0.05 m/cell`

### 결정

기본 운용 경로는 `vehicle /tmp/status_aipN.py -> 중앙 UDP 19051 -> /aipN/heartbeat -> /fleet/status -> dashboard`로 확정한다. dashboard direct UDP overlay는 fallback으로만 남긴다.

---

## 2026-06-23 — UDP heartbeat adapter 테스트 추가

### 배경

adapter 경로가 동작하는 것은 확인했지만, PR로 팀원에게 제안하려면 핵심 변환 로직에 대한 테스트가 필요했다.

### 변경

- `udp_status_heartbeat_adapter.py`의 변환 로직을 순수 함수로 분리했다.
- `src/aip_fleet_bringup/test/test_udp_status_heartbeat_adapter.py` 추가.
- `aip_fleet_bringup`에 `ament_cmake_pytest` 테스트 등록.
- `package.xml`에 `ament_cmake_pytest` test dependency 추가.

### 검증

- `python3 -m py_compile` 통과.
- `colcon build --symlink-install --packages-select aip_fleet_bringup` 통과.
- `colcon test --packages-select aip_fleet_bringup` 통과:
  - `6 passed`
- 중앙 재시작 후 웹 확인:
  - `3 online`
  - `19051` adapter만 사용.
  - 저장맵 `전체맵/저장맵 · 201x167 · 0.05 m/cell`

### 결정

현재 adapter는 테스트가 붙은 중앙 compatibility layer로 유지한다. 완전 정식화는 추후 차량 side `/aipN/heartbeat` 직접 발행 또는 WSL DDS discovery 문제 해결로 진행한다.

---

## 2026-06-23 — PR 검토 메모 및 운영 헬스체크 추가

### 배경

사용자가 다음 단계와 남은 단계를 요청했다. 현재 통합본은 동작하지만, 팀원 검토/PR 관점에서 변경 범위와 검증 절차가 더 명확해야 했다.

### 변경

- `docs/PR_REVIEW_NOTES_KO.md` 추가.
- `scripts/check_web_control_stack.sh` 추가.
- `WEB_CONTROL_RUNBOOK_KO.md`에 자동 점검 명령 추가.

### 검증

- `bash -n scripts/check_web_control_stack.sh` 통과.
- `bash scripts/check_web_control_stack.sh` 통과.
- 헬스체크 결과:
  - `8080/tcp` dashboard listening.
  - `19051/udp` adapter listening.
  - `11811/udp` Discovery Server listening.
  - `19050/udp` direct overlay disabled.
  - dashboard HTTP 응답.
  - 중앙 로그 정상.
  - saved latest_fleet_map 존재.

### 다음 세션 시작점

남은 큰 단계는 `시연 안정화`, `팀원 리뷰/PR`, `완전 정식화` 세 갈래다. 현재는 PR 검토 가능한 중앙 compatibility layer 상태다.

---

## 2026-06-23 — 상태 overlay helper 자동 실행 안정화

### 배경

`scripts/manage_status_overlays.py status`를 Codex 자동 실행 환경에서 호출하면 SSH 비밀번호 입력을 기다리다가 타임아웃될 수 있었다. 실제 터미널에서는 프롬프트 입력이 필요하지만, 자동 점검에서는 빠르게 실패하고 안내하는 편이 안전하다.

### 변경

- `manage_status_overlays.py`에 `--no-prompt` 옵션을 추가했다.
- 비밀번호 환경변수가 없고 입력 가능한 터미널도 없으면 `[SKIP]` 메시지를 내고 즉시 다음 대상으로 넘어가게 했다.
- `WEB_CONTROL_RUNBOOK_KO.md`에 자동 환경용 `status --no-prompt` 사용법을 추가했다.

### 검증

- `python3 -m py_compile scripts/manage_status_overlays.py` 통과.
- `python3 scripts/manage_status_overlays.py status --no-prompt --timeout 3` 실행 시 세 차량 모두 비밀번호 환경변수 누락을 즉시 안내하고 종료했다.
- `bash scripts/check_web_control_stack.sh`는 계속 통과했다.

### 다음 세션 시작점

자동 점검은 `check_web_control_stack.sh`로 확인하고, 차량 내부 helper 상태까지 확인하려면 실제 터미널에서 비밀번호를 입력하거나 현재 셸에만 `AIP*_SSH_PASSWORD`를 설정한 뒤 `manage_status_overlays.py status`를 실행한다.

---

## 2026-06-23 — PR 변경 파일 목록 문서화

### 배경

`C:\Projects\aip-swarm-ws-main+sub`는 원본 main 폴더를 복사해 만든 통합본이며 Git 저장소가 아니다. 실제 PR을 만들 때 어떤 파일을 브랜치에 반영해야 하는지 별도 목록이 필요했다.

### 변경

- `docs/CHANGESET_FOR_PR_KO.md` 추가.
- `docs/PR_REVIEW_NOTES_KO.md`에서 변경 파일 목록 문서를 참조하도록 갱신.

### 결정

팀원 리뷰 때는 `PR_REVIEW_NOTES_KO.md`로 설계 의도와 리스크를 설명하고, `CHANGESET_FOR_PR_KO.md`로 실제 반영 대상 파일을 확인한다.

---

## 2026-06-23 — 도킹 마커 제거 및 pose 미수신 확인

### 배경

웹 지도 위에 `dock:aip1`, `dock:aip2` 마커가 표시되어 실제 로봇 위치처럼 보일 수 있었다. 사용자가 해당 마커가 필요 없다고 요청했고, 동시에 실제 로봇 위치가 보이지 않는지 확인을 요청했다.

### 변경

- `~/aip_maps/dock_positions.json`을 `{}`로 비웠다.
- `src/aip_fleet_dashboard/static/index.html`에서 지도 위 도킹 위치 마커 렌더링을 제거했다.
- 같은 파일에서 현재 실차 운영에 필요하지 않은 `충전/도킹 스테이션` UI 블록을 숨겼다.
- 중앙 웹 스택을 재시작해 서버 메모리에 남아 있던 도킹 좌표도 제거했다.

### 확인

- 브라우저 새로고침 후 `dock:aip*` 텍스트 없음.
- `충전/도킹 스테이션` 패널 없음.
- 브라우저 console error 없음.
- `bash scripts/check_web_control_stack.sh` 통과.
- 차량 카드 3대는 online이지만 모두 `pose:--` 상태다.

### 판단

현재 3대 online 표시는 UDP status helper 기반이며, helper는 상태/배터리/CPU/container 정보만 보내고 실제 지도 pose를 보내지 않는다. 웹의 로봇 마커는 `/fleet/peer_poses`, `map -> base_link` TF, 또는 `/<vehicle>/odom` 중 하나가 들어와야 표시된다. 따라서 현재 `pose:--`는 로봇 위치 표시 데이터가 중앙 웹까지 오지 않는 상태를 의미한다.

### 다음 시작점

로봇 위치를 보이게 하려면 다음 중 하나가 필요하다.

- 차량별 실제 pose를 `/fleet/peer_poses`로 집계해 발행한다.
- 현재 UDP helper에 pose 전송을 추가하고 중앙 adapter가 `/fleet/peer_poses`로 변환한다.
- `AIP_VEHICLE_TOPIC_ALIASES=aip2=scout_1,aip3=scout_2` 등 alias를 적용한 상태에서 중앙이 `/scout_N/odom` 또는 TF를 discovery할 수 있는지 확인한다.

---

## 2026-06-23 — UDP helper pose 전송 및 /fleet/peer_poses adapter 추가

### 배경

웹의 차량 카드는 `3 online`이지만 세 차량 모두 `pose:--`였다. 현재 UDP status helper는 상태/CPU/battery/container만 보내고 위치를 보내지 않으므로, 웹 로봇 화살표 marker가 뜰 수 없었다.

### 변경

- `udp_status_heartbeat_adapter.py`
  - UDP payload에 `pose`가 있으면 `PeerPoseArray`를 `/fleet/peer_poses`로 발행하도록 확장했다.
  - 최근 pose를 차량별로 최대 5초 유지해, 한 차량 pose만 갱신되어도 다른 차량 pose가 즉시 사라지지 않게 했다.
- `manage_status_overlays.py`
  - 차량 내부 odom 후보 토픽을 짧게 구독해 pose를 읽는다.
  - 후보 토픽:
    - `aip1`: `/aip1/odom`, `/main/odom`
    - `aip2`: `/aip2/odom`, `/scout_1/odom`, `/odom`
    - `aip3`: `/aip3/odom`, `/scout_2/odom`, `/odom`
  - pose를 읽으면 UDP payload에 `pose`를 포함하고 behavior에 `pose_udp`를 추가한다.
- 테스트에 `PeerPose` 변환 케이스를 추가했다.

### 검증

- `python3 -m py_compile scripts/manage_status_overlays.py src/aip_fleet_bringup/scripts/udp_status_heartbeat_adapter.py` 통과.
- remote helper script generation 확인 통과.
- `colcon test --packages-select aip_fleet_bringup` 통과.
  - `9 passed`
- `colcon build --symlink-install --packages-select aip_fleet_bringup aip_fleet_dashboard` 통과.
- WSL이 일시적으로 hung 상태가 되어 stale `wsl.exe` 프로세스를 정리한 뒤 복구했다.
- FastDDS Discovery Server와 중앙 웹 스택 재기동 완료.
- `bash scripts/check_web_control_stack.sh` 통과.
- 브라우저 확인:
  - `3 online`
  - 도킹 UI/마커 없음
  - 아직 `pose:--` 상태. 이유는 차량에서 실행 중인 `/tmp/status_aipN.py`가 구버전 helper라 pose를 보내지 않기 때문.

### 다음 시작점

pose marker를 실제로 띄우려면 차량 helper를 재시작해야 한다.

```bash
cd /mnt/c/Projects/aip-swarm-ws-main+sub
python3 scripts/manage_status_overlays.py start
```

비밀번호는 파일에 저장하지 말고 프롬프트에 입력하거나, 현재 셸에만 `AIP1_SSH_PASSWORD`, `AIP2_SSH_PASSWORD`, `AIP3_SSH_PASSWORD`를 설정한다. helper 재시작 후 웹 카드에 `pose_udp` 태그와 `pose:odom`/`pose:fleet` 계열 표시가 뜨는지 확인한다.

### 다음 세션 시작점

- 현재 3대 표시는 정식 heartbeat 통합이 아니라 UDP overlay이다.
- 정식화하려면 다음 중 하나를 선택해야 한다.
  - 중앙을 team main과 동일한 네이티브 Linux/discovery 조건에서 실행해 `/aip1/heartbeat` discovery를 복구한다.
  - 각 차량 side adapter가 team main 구형 `FleetHeartbeat` 스키마로 `/aipN/heartbeat`를 발행하게 한다.
  - 임시 UDP overlay를 systemd 서비스로 영구화하되, 이는 표시 계층 보완이지 ROS heartbeat 정식 통합은 아님을 문서화한다.
## 2026-06-23 (계속) - aip2/aip3 웹 pose 표시 복구, aip1 pose source 미확인

### 배경

대시보드에서 3대가 online으로 표시되지만 로봇 위치 마커가 보이지 않는 문제가 남아 있었다. dock marker와 docking UI는 제거된 상태였고, 저장맵은 `전체맵/저장맵 · 201x167 0.05 m/cell`로 정상 로드되고 있었다.

### 확인

- 브라우저 상태:
  - `3 online`
  - dock marker/UI 없음
  - `aip3`: `(-0.22, -0.39)`, `pose:fleet+cal`
  - `aip2`: 초기에는 `pose:--`
  - `aip1`: `pose:--`
- `aip2` 컨테이너 내부에서 직접 확인:
  - `/odom`, `/scout_1/odom`, `/scout_1/dashboard/odom`은 `nav_msgs/msg/Odometry`를 실제로 발행 중.
  - Discovery Server 환경에서는 `ros2 topic list -t --no-daemon`이 `/parameter_events`, `/rosout`만 보이지만, exact topic echo는 몇 초 기다리면 odom을 수신한다.
  - 따라서 `aip2`의 pose 원천은 살아 있고, 새 rclpy probe의 discovery 대기시간이 너무 짧았던 것이 원인이었다.

### 변경

- `scripts/manage_status_overlays.py`
  - pose 후보 토픽을 확장:
    - `aip2`: `/aip2/odom`, `/scout_1/odom`, `/scout_1/dashboard/odom`, `/odom`, `/aip2/pose`, `/scout_1/pose`, `/scout_1/dashboard/pose`, `/pose`
    - `aip3`: `/aip3/odom`, `/scout_2/odom`, `/scout_2/dashboard/odom`, `/odom`, `/aip3/pose`, `/scout_2/pose`, `/scout_2/dashboard/pose`, `/pose`
    - `aip1`: `/aip1/odom`, `/main/odom`, `/aip1/pose`, `/main/pose`
  - helper pose probe 대기시간을 1.5초에서 5초로 늘리고, subprocess timeout을 8초로 늘렸다.
  - probe 주기를 8초, stale 허용 시간을 24초로 조정했다.
  - Odometry 토픽을 우선 구독하고 PoseStamped 후보는 별도로만 구독하도록 보수화했다.
- `aip2` helper를 재배포했다.

### 결과

- `aip2` 웹 표시 복구:
  - `(0.26, -0.30)`
  - `pose:fleet+cal+poseflip`
  - `pose_udp`
- `aip3` 웹 표시 유지:
  - `(-0.22, -0.39)`
  - `pose:fleet+cal`
- `aip1`은 여전히 `pose:--`.
  - 현재 관찰상 `aip1`에는 status helper와 heartbeat process만 있고, `/aip1/odom`, `/main/odom` 또는 pose를 제공하는 팀 main 주행/SLAM stack은 확인되지 않았다.
  - 원본 main 폴더와 main 차량 SW는 건드리지 않았다.

### 검증

- `python -m py_compile scripts/manage_status_overlays.py` 통과.
- WSL `python3 -m py_compile scripts/manage_status_overlays.py` 통과.
- `bash scripts/check_web_control_stack.sh` 통과.
- 브라우저 console error 없음.

### 다음 시작점

- 웹 로봇 위치 표시는 현재 `aip2/aip3`까지 복구됨.
- `aip1` 위치를 띄우려면 팀원이 main 차량에서 odom/pose/map stack을 실행하거나, main 차량의 pose source 토픽을 확인해야 한다.
- 자율 goal/patrol은 여전히 보류한다. 현재 단계에서는 `aip2/aip3` 수동 주행/상태 표시와 `aip1` pose source 확인이 우선이다.

### 추가 정정

- `aip1` helper에서 generic `/odom`, `/pose` 후보를 제거했다.
  - 이유: main 차량 host는 컨테이너 격리 없이 같은 Discovery Server를 보므로, generic `/odom`이 다른 차량의 odom을 잡아 `aip1` 위치처럼 보일 위험이 있다.
  - `aip1` 후보는 `/aip1/odom`, `/main/odom`, `/aip1/pose`, `/main/pose`만 허용한다.
- `udp_status_heartbeat_adapter.py`에서 stale pose pruning을 수정했다.
  - 이전에는 새 pose payload가 들어올 때만 `/fleet/peer_poses`를 다시 발행해서, 한 번 잘못 들어온 pose가 오래 남을 수 있었다.
  - 이제 heartbeat payload가 들어올 때마다 오래된 pose cache를 정리하고 `/fleet/peer_poses`를 다시 발행한다.
- 중앙 stack 재시작 후 확인:
  - `aip1`: `pose:--`
  - `aip2`: `(0.26, -0.30)`, `pose:fleet+cal+poseflip`, `pose_udp`
  - `aip3`: `(-0.22, -0.39)`, `pose:fleet+cal`, `pose_udp`
  - 저장맵 재로드 완료: `전체맵/저장맵 · 201x167 0.05 m/cell`

## 2026-06-23 — 사용자 fork PR 준비 브랜치 업로드

### 배경

사용자가 지금까지의 `main+sub` 웹 관제 통합 작업을 사용자 GitHub fork에 올리고, 팀원에게 Pull Request로 검토받고 싶다고 요청했다. 원본 team main 폴더는 수정하지 않고, 사용자 fork 저장소 `spongebobDG/aip-swarm-ws`의 새 브랜치에 작업본을 반영하는 방식으로 진행했다.

### 결과

- 브랜치: `codex/main-sub-web-integration`
- 원격: `origin` = `https://github.com/spongebobDG/aip-swarm-ws.git`
- 커밋: `bed5eda` (`통합 웹 관제 3대 표시 준비`)
- 차량별 정리 문서 추가:
  - `docs/vehicles/1_aip1_main/README.md`
  - `docs/vehicles/2_aip2_scout_1/README.md`
  - `docs/vehicles/3_aip3_scout_2/README.md`
- 실제 비밀번호 값은 커밋 전에 제거했다. 문서에는 placeholder 또는 환경변수명만 남겼다.
- 기존 unstaged `.gitignore` 변경은 이번 PR 범위가 아니므로 커밋하지 않았다.

### 팀원 검토 포인트

- `aip1/aip2/aip3`를 웹 표준 차량 ID로 쓰는 방향이 팀 main 구조와 맞는지.
- `aip2 -> scout_1`, `aip3 -> scout_2` alias 계층을 임시 compatibility layer로 둘지.
- `aip1`의 정식 pose source가 `/aip1/odom`, `/main/odom`, `/aip1/pose`, `/main/pose` 중 무엇인지.
- 자율 goal/patrol은 아직 차단하고, 수동 주행/상태/지도 표시 검증을 먼저 진행하는 방향이 맞는지.

---

## 2026-06-24 — PR#4 수동 병합 완료 (session-14)

### 배경

팀원(spongebobDG)의 PR#4 (`codex/main-sub-web-integration`)를 main 브랜치에 수동 병합했다. 자동 머지 불가한 6개 충돌 파일을 모두 해결했다.

### 충돌 해결 내역

| 파일 | 전략 |
|---|---|
| `supervisor.yaml` | PR 버전 채택 (vehicle_topic_aliases + control_lock_ttl_sec + require_control_lock 파라미터 추가) |
| `run_central.sh` | PR 버전 채택 (SUPERVISOR_PEERS 제거, central_real_single_process.launch.py 사용) |
| `supervisor_node.py` | PR 버전(alias 시스템) + HEAD의 자동발견 타이머/로직 병합 |
| `dashboard_server.py` | PR 버전 기반 + HEAD의 `_register_vehicle()` 동적 등록 로직 병합 |
| `index.html` | 9개 블록 전체 병합: coverage 모드(HEAD) + pose_align 모드(PR) 동시 보존 |
| `conversation_log.md` / `pending_tasks.md` | HEAD 내용 유지 + PR의 신규 섹션 추가 |

### 결과

- 커밋 `dc16330` 생성
- `colcon build --symlink-install --packages-select aip_fleet_msgs aip_fleet_supervisor aip_fleet_dashboard aip_fleet_bringup` 4개 패키지 전부 통과
- 빌드 오류 없음 (pytest 경고는 기존 환경 문제, 무관)

### 주요 기술 결정

- **index.html modes 배열**: `['view','goto','patrol','keepout','coverage','pose_align']` — 두 기능 공존
- **VEHICLES 배열**: peer_1/2/3 제거, aip1/2/3만 유지 (자동발견으로 동적 추가)
- **selectedVehicle 기본값**: aip2 (PR 결정 채택)
- **CMD_CLEAR/CMD_RESUME 순서 버그**: PR에서 수정된 버전 채택 (control_lock 검사 전에 E-Stop 해제 처리)

### 다음 단계

- PR#4 병합 완료. 팀원에게 병합 결과 공유 권장
- R-URDF: arm_joint_2/3 pivot — 팀원 SolidWorks 재수출 대기
- R6: 순찰 미션 E2E 테스트 (실차)
- R5: RViz 실차 확인 + 웹 대시보드 재검증

---

## 2026-06-24 — 실차 플릿 central 스택 정상화 (세션 14)

### 배경

PR#4 병합 완료 후 실차 3대(aip1/scout_1/scout_2) 연결 테스트 진행.
이전 세션에서 FleetHeartbeat.msg 신형 포맷 확정 + DDS 연결(scout_1/2 모두 heartbeat 수신) 완료.
본 세션에서는 central 스택 기동 블로킹 오류 3건을 순차 해결.

### 해결한 오류

| # | 오류 | 원인 | 수정 파일 |
|---|---|---|---|
| 1 | `AttributeError: FleetHeartbeat has no attribute 'STATE_IDLE'` | `udp_status_heartbeat_adapter.py` 가 구형 enum 상수 참조 | 어댑터 전면 재작성 |
| 2 | `AttributeError: 'DashboardNode' object has no attribute '_tf_vehicle_ids'` | `__init__` 에서 `_tf_vehicle_ids` 초기화 전에 `_register_vehicle()` 호출 | `dashboard_server.py` 초기화 순서 수정 |
| 3 | supervisor가 scout 하트비트 미수신 | `fastdds_client_profile.xml` 에 DS 주소 `192.168.0.9` 하드코딩 (실제는 `192.168.0.106`) | XML + `aip_env.sh` 주소 수정 |

### 의사결정

- **UDP 어댑터 재설계**: 구형 STATE 열거형 제거. `mode_from_payload()` 로 'manual'/'autonomous' 문자열 반환. bool 필드(`healthy`, `estop`, `obstacle_stop`, `cmd_stale`) 직접 파싱.
- **DS IP 일원화**: `192.168.0.9` → `192.168.0.106` (우리 PC). 관련 파일 3곳 동시 수정.
- **`_tf_vehicle_ids` 초기화 위치**: `for vid in _VEHICLES:` 루프 직전으로 이동.

### 검증 결과

```
/fleet/status WebSocket (http://localhost:8080/ws):
  aip2 (scout_1): ONLINE — healthy: true, status: ok
  aip3 (scout_2): ONLINE — obstacle_stop: true, cmd_stale: true, status: blocked
  aip1:           ONLINE — ping overlay (network_ping_only_no_ssh)
  offline: []
```

### 다음 단계

- aip1 heartbeat_pub 실차 실행 후 DDS 하트비트 수신 검증
- aip3(scout_2) obstacle_stop 원인 조사 (실차 cmd_stale 해소)
- 수동 조종 테스트: 대시보드 → UDP override_cmd_vel 전송
- R-URDF: arm_joint_2/3 pivot — 팀원 SolidWorks 재수출 대기

---

## 2026-06-24 — aip1 온보드 SLAM/Nav2 + UI 개선 + DS IP 수정

### 작업 내용

1. **aip1 fleet_main.launch.py 전면 개편** (`with_slam=true`, `with_nav2=true` 기본값)
   - slam_toolbox(async) 온보드 실행 (2s 타이머)
   - Nav2 full stack 온보드 실행 (7s 타이머, SLAM 맵 초기화 후)
   - patrol_node 선택적 실행 (`with_patrol=false` 기본)
   - 이유: aip2/3(scout)와 동일한 구조로 통일. 오프로드 구조의 TF 중계 오버헤드 및 네트워크 의존성 제거.

2. **UI: 차량 카드 클릭 → control 탭 자동 전환**
   - `index.html`의 `selectVehicle()` 함수에 `switchTab('control')` 추가

3. **docker-compose.yml DS IP 수정** (`192.168.0.9` → `192.168.0.106`)
   - fastdds-ds 컨테이너 command: `-l 192.168.0.106`
   - `ROS_DISCOVERY_SERVER` 환경변수

4. **docker-compose.yml 볼륨 수정** (dashboard symlink-install 호환)
   - `build/` 및 `src/` 디렉터리를 호스트 절대경로로 마운트 추가

### 해결한 오류

| # | 오류 | 원인 | 수정 |
|---|---|---|---|
| 1 | aip1 두 개의 fleet_main 인스턴스 충돌 | 이전 PID(3846)를 종료하지 않은 채 새 launch | 이전 launch 강제 종료 |
| 2 | Docker dashboard `PackageNotFoundError: aip-fleet-dashboard` | `--symlink-install` build의 egg-link가 Docker 내 호스트 절대경로 참조 | build/src 볼륨 추가 + 정규 빌드 |
| 3 | Docker fastdds-ds 포트 충돌 | 호스트에 fast-discovery-server(PID 20838)와 Docker DS 동시 기동 | Docker DS 컨테이너 중단, 호스트 DS 유지 |

### 의사결정

- **dashboard 정규 빌드 (`--symlink-install` 미사용)**: Docker 볼륨 마운트에서 egg-link → 호스트 경로 심링크 체인 문제. `aip_fleet_dashboard` + `aip_fleet_msgs` 를 `colcon build` (정규)로 재빌드.
- **DS/dashboard는 호스트에서 실행**: `central_real_combined.py`(PID 30733)이 이미 포트 8080에서 실행 중. Docker DS(포트 충돌)·dashboard(Python 의존성) 컨테이너 중단하고 호스트 프로세스 유지.
- **aip1 ESP32 serial 오류는 물리적 점검 필요**: `/dev/aip_esp32`(ttyUSB1)에서 데이터 없음 → USB-Serial CP2102는 인식되나 ESP32가 데이터 미전송. odom TF 없어 SLAM/Nav2 성능 저하.

### 검증 결과

```
aip1 DDS heartbeat (중앙 PC에서 수신):
  robot_id: aip1, mode: autonomous, healthy: true, status: ok
  battery_voltage: 0.0 (유선 전원), timestamp: 1782274521

aip1 실행 중 프로세스:
  ydlidar_ros2_driver_node (LiDAR scan 정상)
  heartbeat_pub @ 2Hz (DDS 발행 확인)
  slam_toolbox (async, 온보드)
  Nav2 full stack (controller, planner, behavior, bt_navigator, smoother, waypoint_follower)
  twist_mux
  serial_bridge (ESP32 오류 지속 — 물리 점검 필요)
```

### 다음 단계

- aip1 ESP32 USB 케이블/전원 물리 점검 (`/dev/aip_esp32` 데이터 없음)
- odom TF 없는 상태에서 SLAM 동작 검증 (scan-only 모드 가능 여부)
- aip3(scout_2) obstacle_stop 원인 물리 조사 (combined_safety_node 45cm 거리 감지)
- docker-compose DS/dashboard 컨테이너: 의존성 패키지 포함 Dockerfile.central 작성 고려
- scout_2 docker-compose 의 `ROS_DISCOVERY_SERVER` fallback IP 수정 (`192.168.0.8` → `192.168.0.106`)

---

## 2026-06-24 — 차량 카드 클릭 불가 버그 수정 (Ubuntu 세션)

### 증상

웹 UI 왼쪽 차량 카드(vcard)를 클릭해도 아무 반응 없음 ("클릭 자체가 불가능").

### 근본 원인 분석

- `supervisor_node.py` 가 `/fleet/status` 를 **2Hz**(500ms마다) 발행
- `dashboard_server.py` → WebSocket → `handleMsg` → `onFleetStatus` → **`renderVehicles()`** 호출
- `renderVehicles()` 는 `$('vlist').innerHTML = ...` 로 vlist 전체 DOM 교체
- **레이스 컨디션**: mousedown 후 mouseup 전에 DOM 교체가 발생하면 클릭 대상 element가
  분리(detached)되어 브라우저가 click 이벤트를 발화하지 않음
- 부수 효과: 500ms마다 hover CSS 리셋 → 커서 깜빡임 → "활성화 안 됨" 느낌

### 수정 사항 (9727ad1)

1. **`_vcardKeys` 렌더 캐시** — 배터리/CPU/상태 등 표시 키를 비교해 데이터가 실제로
   변경된 경우에만 innerHTML 교체 → 불필요한 DOM 파괴/재생성 차단, hover 깜빡임 제거
2. **`data-vid` 속성 전환** — article의 `onclick="selectVehicle(...)"` 제거,
   `data-vid="${id}"` 속성으로 대체
3. **mousedown 이벤트 위임** — `#vlist.addEventListener('mousedown', ...)` 에서
   `e.target.closest('[data-vid]')` 로 카드 탐색 후 `selectVehicle()` 호출
   → mousedown 은 JS 싱글스레드 보장으로 WS 콜백과 레이스 없이 항상 실행됨

### 결과

차량 카드 클릭 즉시 반응, 탭 자동 전환(control), hover 깜빡임 제거.

---

## 2026-06-24 — 실차 플릿 세팅 완료 (Session 14 후속)

### 배경
aip2 OS 계정/hostname 수정, aip2/aip3 컨테이너 실행 이후 중앙 스택 안정화 및 차량별 설정 수정.

### 문제 및 해결

#### 1. FastDDS Discovery Server 관리 방식 재정비
- **문제**: docker compose `fastdds-ds` 컨테이너가 재시작 루프. 원인: 호스트에서 이미 `fast-discovery-server`(터미널 실행)가 UDP 11811 점유.
- **해결**: 
  - docker `fastdds-ds` 서비스 → `profiles: [docker-ds]` (기본 up에서 제외)
  - `~/.config/systemd/user/fastdds-ds.service` 등록 및 활성화 (LD_LIBRARY_PATH 필요)
  - 재부팅 시 자동 실행 보장

#### 2. 중앙 PC IP 고정 (192.168.0.10)
- **문제**: DHCP로 IP 할당되어 재부팅 시 IP 변경 가능 → FastDDS DS 주소 깨짐
- **최초 설정**: 192.168.0.106 (잘못됨 — 공유기 DHCP 범위 100-200과 겹침)
- **재수정**: 192.168.0.10 (DHCP 범위 외, 99 이하)
- **해결**: `nmcli` 로 `aip2.4GHz` Wi-Fi 연결을 static IP로 변경

#### 3. Dashboard 서버 관리 방식 재정비
- **문제**: docker `dashboard` 컨테이너 반복 실패
  - Python 메타데이터(egg-link 절대경로 vs. importlib.metadata 불일치)
  - 호스트에서 이미 `central_real_combined.py` (PID 30733)가 포트 8080 점유
- **해결**:
  - docker `dashboard` 서비스 → `profiles: [docker-dashboard]` (기본 up에서 제외)
  - `~/.config/systemd/user/aip-central.service` 등록 (DashboardNode + SupervisorNode + WatchdogNode 통합)
  - `Dockerfile.dashboard` 생성 (pip: pillow, numpy, uvicon, fastapi + apt: nav2-msgs, tf2-ros)
  - build 볼륨을 두 경로 모두 마운트: `/opt/aip/build` (symlink 상대경로) + `/home/kde/aip_swarm_ws/build` (egg-link 절대경로)

#### 4. InfluxDB 비활성화
- **문제**: `cap_drop: [ALL]` + 기존 볼륨 퍼미션 불일치로 Permission denied 재시작 루프
- **해결**: `profiles: [telemetry]` 로 이동. 필요 시 `docker compose --profile telemetry up -d influxdb`

#### 5. aip3 SLAM 최소 거리 경고 수정
- **문제**: `slam_toolbox.yaml`에 `minimum_laser_range` 미설정 → 기본값 0.0m가 YDLIDAR X4 PRO 최소 0.1m 초과 경고
- **해결**: `slam_toolbox.yaml`에 `minimum_laser_range: 0.12` 추가 후 컨테이너 재시작 → 경고 소멸

### 현재 상태 (2026-06-24 기준)

| 구성 요소 | 상태 | 관리 방식 |
|---|---|---|
| FastDDS DS | ✅ active | systemd user (fastdds-ds.service) |
| Dashboard+Supervisor+Watchdog | ✅ PID 30733 | 수동 실행 → 재부팅 시 aip-central.service |
| aip_uros_agent | ✅ Up | docker compose |
| aip_rosbag_recorder | ✅ Up | docker compose |
| aip_influxdb | ⏸ profiles[telemetry] | 볼륨 퍼미션 수정 후 활성화 예정 |
| aip2 turtlebot3 | ✅ Up 40min | docker-compose (aip2 차량) |
| aip3 sub_vehicle | ✅ Up | docker compose (aip3 차량) |
| 중앙 PC IP | ✅ 192.168.0.10 (static) | nmcli |

### 미결 사항
- aip2 TF_OLD_DATA 경고: 재시작 직후 일시적, 자동 해소 예상
- aip2 E-stop 반복: TF 체인 완성 후 해소 예상 (SLAM 초기화 시간 필요)
- `docker compose up -d` 실행 시 uros_agent, rosbag_recorder만 시작됨 (DS/dashboard/influxdb는 systemd 또는 profiles로 분리)

---

## 2026-06-24 (계속) — 중앙 PC IP 재수정 + aip2 CPU 원인 분석

### 배경

이전 세션에서 중앙 PC IP를 192.168.0.106으로 고정했으나, 공유기 DHCP 할당 범위가 100-200대임을 확인.
192.168.0.106은 DHCP 충돌 위험 존재 → 범위 밖인 192.168.0.10으로 재수정.

### IP 재수정 내역

| 파일 | 변경 내용 |
|---|---|
| `nmcli` (시스템) | Wi-Fi 정적 IP 192.168.0.106 → 192.168.0.10 |
| `docker/central/docker-compose.yml` | `ROS_DISCOVERY_SERVER`, `fastdds-ds` command, `foxglove-bridge --address` |
| `~/.config/systemd/user/fastdds-ds.service` | `-l 192.168.0.10` |
| `~/.config/systemd/user/aip-central.service` | `ROS_DISCOVERY_SERVER=192.168.0.10:11811` |
| `config/fastdds_client_profile.xml` | `<address>192.168.0.10</address>` |
| aip2 `~/scout_1_turtlebot3/docker-compose.yml` | `ROS_DISCOVERY_SERVER=192.168.0.10:11811` |
| aip3 `~/industrial_sub_vehicle/.env` | `ROS_DISCOVERY_SERVER=192.168.0.10:11811` |

### aip2 CPU 고원인 분석

**증상**: aip2에서 `ros_topic_bridge.py`가 단일 코어 67.3% 점유.

**근본 원인**: TurtleBot3 공식 bringup이 네임스페이스 없이 실행됨 → `/tf` 토픽을 `odom → base_link`(비네임스페이스)로 발행. `ros_topic_bridge.py`가 이를 받아 `scout_1/` prefix 추가 후 다시 `/tf`로 재퍼블리시. 이 재퍼블리시 메시지도 같은 구독자가 받아서 `namespaced_tf_message()`가 다시 호출됨(필터링은 되나 콜백 오버헤드 남음). TB3 odom TF는 30~50Hz로 발행 → Python GIL 환경에서 초당 60~100 콜백 발화.

**다른 차량과의 비교:**

| 차량 | 네임스페이스 처리 방식 | CPU 원인 |
|---|---|---|
| aip1 | 타 팀원 자체 ROS2 스택 (네이티브 네임스페이스) | 없음 |
| aip2 | TB3 공식 bringup (비네임스페이스) + Python 브릿지 | `ros_topic_bridge.py` TF 재퍼블리시 콜백 오버헤드 |
| aip3 | `sub_vehicle_bringup`이 처음부터 `scout_2` 네임스페이스로 노드 실행 | 없음 |

**제안된 수정 (사용자 승인 후 적용 예정)**:

```python
def tf_callback(self, msg: TFMessage):
    prefix = f'{self.vehicle_id}/'
    if msg.transforms and (
        msg.transforms[0].header.frame_id.lstrip('/').startswith(prefix)
        or msg.transforms[0].child_frame_id.lstrip('/').startswith(prefix)
    ):
        retun   # 자신이 발행한 메시지 조기 리턴
    namespaced_msg = self.namespaced_tf_message(msg)
    if namespaced_msg.transforms:
        self.tf_pub.publish(namespaced_msg)
```

### 안전거리 LiDAR 기반 분석

`safety_supervisor.py`의 `on_scan()`:
- 구독 토픽: `scan` (LaserScan)
- TF 조회 없이 `LaserScan.ranges`를 직접 사용
- → 안전거리는 **LiDAR 센서 중심** 기준

**비대칭 설치 위험 분석**:
- LiDAR가 차량 전방 중심에서 벗어나면 전방 차체 돌출부 충돌 위험
- LiDAR가 차량 무게 중심 뒤에 있으면 전진 시 실제 전방 여백이 front_stop_distance보다 좁음
- 정밀한 배치 정보 확보 후 안전거리 재보정 필요 (사용자 추후 제공 예정)

### 미결 사항

- aip2 `ros_topic_bridge.py` CPU 수정 (차량 SW 수정 → 사용자 승인 후 적용)
- aip2 TF_OLD_DATA 경고: SLAM 안정화 후 자동 해소 예상
- aip3 URDF arm_joint_2/3 pivot 위치: 팀원 SolidWorks 재수출 대기
- aip3 LiDAR 비대칭 배치 상세 정보: 사용자 제공 후 safety_supervisor.py 파라미터 조정

---

## 2026-06-25 — 세션 16/17: aip3 Nav2 스택 정상화

### 주요 문제 발견 및 해결

#### 1. docker/.env 심볼릭 링크 누락 (치명적 버그)
- **증상**: `use_slam:=true use_nav2:=false` 로 컨테이너가 시작됨 (SLAM ON, Nav2 OFF)
- **원인**: `docker-compose.yml`의 `${USE_SLAM:-true}` 변수가 Docker Compose YAML 레벨에서
  치환될 때 `.env` 파일이 `docker/` 디렉토리에 없어 기본값(true/false)이 사용됨.
  `env_file: ../.env` 는 컨테이너 환경변수는 올바르게 설정하지만 YAML 치환은 별개.
- **해결**: `~/industrial_sub_vehicle/docker/.env → ../.env` 심볼릭 링크 생성
- **확인**: `docker compose config` 로 `use_slam:=false use_nav2:=true` 치환 검증

#### 2. stale FastDDS SHM 파일 (intra-container TF 차단)
- **증상**: `local_costmap` 이 `scout_2/odom` 프레임을 찾지 못함 (prev 세션에서 분석)
- **원인**: 이전 컨테이너 실행의 `/dev/shm/fastrtps_*` 파일이 남아 새 컨테이너의
  FastDDS SHM 전송을 오염. ipc:host로 인해 컨테이너-호스트 IPC 공유.
- **해결**: 컨테이너 재시작 전 SHM 파일 수동 삭제, docker-compose.yml 시작 커맨드에
  `rm -f /dev/shm/fastrtps_*` 추가하여 자동화
- **확인**: `local_costmap: start` 로그, `map→scout_2/odom→scout_2/base_link` TF 체인 완성

#### 3. Nav2 전체 스택 활성화
- `lifecycle_manager_localization`: Managed nodes are active ✅
- `lifecycle_manager_navigation`: Managed nodes are active ✅
- AMCL 초기 자세(0,0,0) central PC에서 `/scout_2/initialpose` 발행으로 설정

### 잔존 문제: AMCL 레이저 스캔 처리 실패
- **증상**: "Message Filter dropping message: frame 'scout_2/laser_frame' at time T for reason
  'the timestamp on the message is earlier than all the data in the transform cache'"
- **원인**: RPi4 CPU 과부하(nav2 114%, combined_safety 61.7%)로 AMCL 처리 속도가
  scan 도달 속도보다 느려 큐에 쌓인 오래된 스캔이 TF 버퍼 범위를 벗어남.
- **영향**: AMCL 위치 교정 불가. 초기 자세(0,0,0) 기준 dead-reckoning 네비게이션만 가능.
- **잠재적 해결책** (미적용, 사용자 승인 필요):
  - ydlidar 스캔 주파수 축소 (4.5Hz → 2Hz)
  - AMCL 파티클 수 감소 (`min_particles`/`max_particles`)
  - nav2_params.yaml `amcl.transform_tolerance` 증가

### 커밋 사항
- `config/fastdds_no_shm_profile.xml`: UDP-only 전송 프로파일 (참고용, 현재 미사용)
- aip3 `docker/.env` 심볼릭 링크 (aip3 현장 파일, git 외)
- aip3 `docker/docker-compose.yml` SHM 자동 정리 추가 (aip3 현장 파일, git 외)

---

## 2026-06-25 — 세 차량 연결 확인 + aip1 웹 제어 수정 + 전 차량 CPU 부하 최적화

### 결정 1: aip1 cmd_vel 라우팅 수정 (vehicle_cmd_vel_overrides)

- **문제**: aip1의 twist_mux는 `/main/central_cmd_vel`을 입력으로 사용하는데, 중앙 supervisor/dashboard가 `/aip1/override_cmd_vel`에 발행하고 있어 웹 제어가 동작하지 않음.
- **해결**: `supervisor_node.py`, `dashboard_server.py`에 `vehicle_cmd_vel_overrides` 파라미터 추가. `supervisor.yaml`에 `vehicle_cmd_vel_overrides: ["aip1=/main/central_cmd_vel"]` 설정.
- **빌드**: `aip_fleet_supervisor`, `aip_fleet_dashboard`, `aip_fleet_bringup` 재빌드 후 `aip-central.service` 재시작.

### 결정 2: heartbeat_timeout 3.5s (2.0→3.5)

- **이유**: Wi-Fi 환경에서 2.0s 타임아웃이 너무 짧아 차량이 자주 offline/recovered 반복. 3.5s로 늘려 플래핑 억제.

### 결정 3: aip2/aip3 Docker 재부팅 자동 브링업

- aip2 `aip2_robot` 컨테이너: `--restart=unless-stopped` 정책으로 재생성 (기존 AutoRemove 컨테이너 대체).
- aip3 `docker-robot-1`: `docker update --restart=unless-stopped` 적용 (이전 세션 완료).
- Docker 데몬은 두 차량 모두 `systemctl enable docker`로 부팅 시 자동 시작됨.

### 결정 4: 전 차량 CPU 부하 최적화 (2026-06-25)

**배경**: aip2 load avg 14.0 (4코어 350%), aip3 load avg 4.32 (107%). SSH 불가 수준.

**aip2 수정** (`~/scout_1_turtlebot3/` 관할):
| 항목 | 변경 전 | 변경 후 | 효과 |
|---|---|---|---|
| SLAM 모드 | sync_slam_toolbox_node | async_slam_toolbox_node | 41% → 7% |
| Nav2 controller_frequency | 10 Hz | 5 Hz | 26% → 13% |
| Nav2 expected_planner_frequency | 20 Hz | 10 Hz | 25% → 8% |
| Nav2 waypoint_follower loop_rate | 2000 Hz | 20 Hz | 폭주 방지 |
| bt_navigator groot_monitoring | True | False | ZMQ 소켓 제거 |
| slam transform_publish_period | 0.1s | 0.2s | TF 발행 5Hz |
| ros_topic_bridge TF 재발행 | enabled | disabled | Foxglove 미사용 |
| ros_topic_bridge dashboard_ 토픽들 | 6개 발행 | 비활성화 | Wi-Fi 트래픽 감소 |

**aip3 수정** (`/home/aip3/industrial_sub_vehicle/` 관할):
| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| combined_safety_node num_threads | 2 | 4 |
| SafetySupervisor publish_safe_command | 0.1s (10Hz) | 0.2s (5Hz) |
| Esp32BaseNode enforce_cmd_timeout | 0.05s (20Hz) | 0.1s (10Hz) |
| Esp32BaseNode send_heartbeat | 0.1s (10Hz) | 0.2s (5Hz) |

**결과**:
- aip2: load avg 14.0 → **1.62** (88% 감소)
- aip3: load avg 4.32 → **1.84** (57% 감소), nav2_container 78% → 9%

**미완료 (사용자 직접 실행 필요)**:
- `sudo systemctl disable --now snapd` — aip2, aip3 모두. SSH에서 sudo 비밀번호 입력 불가.

### 잔존 확인 사항
- aip1 웹 대시보드 제어 동작 여부 — 사용자 확인 필요
- aip3 combined_safety_node 재시작 후 CPU 측정 — 수정 반영 완료됐으나 측정 미완
- Foxglove 완전 비사용 확정 → CLAUDE.md 대시보드 관련 주석 업데이트 예정

---

## 2026-06-25 (계속) — aip1 DDS 통신 단절 원인 발견 및 수정

### 배경

이전 세션에서 aip1 수동제어를 위해 twist_mux YAML 및 launch 수정을 완료했으나, 중앙 PC에서 발행한 `/main/central_cmd_vel`이 aip1 twist_mux에 도달하지 않아 `/main/cmd_vel` 출력이 없었음. DDS 라우팅 자체가 끊어진 상태.

### 근본 원인 발견: fastdds_client_profile.xml 이중 오류

aip1의 `~/aip_swarm_ws/config/fastdds_client_profile.xml`에 두 가지 오류가 있었음:

| 항목 | 잘못된 값 | 올바른 값 |
|---|---|---|
| `<discoveryProtocol>` | `CLIENT` | `SUPER_CLIENT` |
| `<address>` | `192.168.0.106` | `192.168.0.10` |

- `CLIENT`는 DS에서 필요한 endpoint 정보만 선택적으로 받음 → `ros2 topic list`에 원격 토픽 미표시
- `SUPER_CLIENT`는 DS가 모든 endpoint 정보를 push → 전체 플릿 토픽 가시성 확보
- IP `192.168.0.106`은 구 중앙 PC 주소 (현재 DS는 `192.168.0.10`)

`.bashrc`의 `ROS_DISCOVERY_SERVER=192.168.0.10:11811`은 이미 수정되어 있었지만, `FASTRTPS_DEFAULT_PROFILES_FILE`이 XML을 우선하므로 XML의 구 IP가 실제 연결에 사용되고 있었음.

### 수정 내용

**aip1 `~/aip_swarm_ws/config/fastdds_client_profile.xml`**:
```xml
<!-- 변경 전 -->
<discoveryProtocol>CLIENT</discoveryProtocol>
<address>192.168.0.106</address>

<!-- 변경 후 -->
<discoveryProtocol>SUPER_CLIENT</discoveryProtocol>
<address>192.168.0.10</address>
```

SSH 명령으로 직접 수정 (`sed -i`):
- `CLIENT` → `SUPER_CLIENT`
- `192.168.0.106` → `192.168.0.10`

### 현재 상태

- XML 수정 완료 ✅
- 차량 리셋 후 fleet_main.launch.py 수동 기동 완료 (LiDAR 10Hz 확인 ✅)
- **미완료**: twist_mux 재시작 필요 (리셋 후 SSH 부하 타임아웃으로 중단)
- **미완료**: 수동제어 end-to-end 검증 (중앙 발행 → `/main/cmd_vel` 수신)

### 다음 세션 작업 순서

1. aip1 SSH 접속 (`jh@192.168.0.3`)
2. twist_mux 시작:
```bash
source /opt/ros/humble/setup.bash && source ~/aip_ws/install/setup.bash
export ROS_DOMAIN_ID=42 RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DISCOVERY_SERVER=192.168.0.10:11811
export FASTRTPS_DEFAULT_PROFILES_FILE=$HOME/aip_swarm_ws/config/fastdds_client_profile.xml
nohup /opt/ros/humble/lib/twist_mux/twist_mux \
  --ros-args -r __node:=twist_mux -r __ns:=/main \
  --params-file ~/aip_ws/install/aip_bringup/share/aip_bringup/config/twist_mux_main.yaml \
  -r cmd_vel_out:=/main/cmd_vel > /tmp/tmx.log 2>&1 &
```
3. 중앙 PC에서 `/main/central_cmd_vel` 발행 → aip1 로컬 `/main/cmd_vel` 에코 확인
4. 웹 대시보드 조이스틱 → aip1 이동 최종 검증

### 중요 메모: twist_mux를 fleet_main에 통합해야 함

현재 twist_mux는 수동으로 별도 기동해야 함. 영구 해결을 위해 `fleet_main.launch.py`에 twist_mux Node를 추가하거나 systemd 서비스로 등록 필요.


---

## 2026-06-25 — 세션 18: 차량 독립 코드 수정 3종

### 작업 배경

차량이 오프라인 상태에서 처리할 수 있는 코드 수정만 진행.

---

### 수정 1: central.launch.py foxglove 화이트리스트 버그 수정

**원인**: 시뮬 phase에서 사용하던 peer_[123] 네임스페이스가 실차 전환 후에도 foxglove 화이트리스트에 남아 있었음.
- /peer_[123]/amcl_pose, /peer_[123]/plan, /peer_[123]/patrol_path_viz, /peer_[123]/arm_fov_marker, /peer_[123]/odometry/filtered, /peer_[123]/particlecloud, /peer_1/explore/goal_marker — 모두 실차에서 존재하지 않는 토픽.
- /aip[123]/scan_slow 와 /peer_[123]/scan_slow 가 중복 등재.

**수정**: 전부 ip[123] / ip1 패턴으로 교체, 중복 제거.

---

### 수정 2: central.launch.py scan_throttle 노드 동적 생성

**원인**: scan throttle 노드 3개가 ip1/aip2/aip3로 하드코딩. 차량 목록이 supervisor.yaml에서 관리되는데 launch 파일과 이중 관리.

**수정**: _make_scan_throttle_nodes() OpaqueFunction 추가.
- supervisor_params YAML에서 ehicle_ids 읽어 동적 생성.
- 차량 추가/삭제 시 YAML 한 곳만 수정하면 됨.

---

### 수정 3: C-AMCL 자동화 — central_real_combined.py

**원인**: aip3 docker restart 후 AMCL이 초기 포즈를 잃어 매번 수동으로 /aip3/initialpose 발행 필요.

**수정**: _amcl_init_thread() 추가 (백그라운드 스레드).
- 환경변수 AIP_AMCL_INIT_VEHICLES=aip3 설정 시 활성화.
- 중앙 기동 후 AIP_AMCL_INIT_DELAY_SEC(기본 8s) 대기 후 자동 발행.
- 포즈: AIP_AMCL_INIT_POSE_AIP3=x,y,yaw_deg 로 지정 (기본 원점).
- 공분산 0.5m / ±30° — AMCL이 LiDAR로 자체 수렴 가능한 수준.

**활성화 방법**:
`ash
export AIP_AMCL_INIT_VEHICLES=aip3
./run_central.sh
`

---

### pending_tasks.md 업데이트

- C0: leet_main.launch.py의 twist_mux 통합이 이미 완료되어 있음을 확인 → 문서 정정.
- C-AMCL: 코드 완료 상태로 갱신, 실차 검증 절차 추가.


---

## 2026-06-26 — PR #5 머지 + aip1 수동 제어 최종 검증

### PR #5 (codex/session18-refactor) 리뷰 및 머지

**리뷰 결과:**
- 이전 세션 "CRITICAL: AMCL position.x/y 미할당" → REFUTED (실제 diff에 두 줄 모두 존재)
- HIGH: dashboard_server.py 차량 /map 구독 QoS가 `_MAP_VOLATILE_QOS`로 변경됨 — slam_toolbox TRANSIENT_LOCAL 호환 불가 → `_LATCHED_QOS`로 수정 후 머지
- MEDIUM: `_systemd_unit_for()`의 ExecStartPre multi-line heredoc이 systemd 단일행 제약에 위배 → --install-systemd 기능 사용 금지 (기존 기능은 영향 없음)

**머지 처리:**
1. `fix(dashboard)` 커밋(a7f0a68): 웹 UI 수정(停→정지, map suffix 정리, supervisor 로깅) main에 선적용
2. PR #5 브랜치 `git merge` → dashboard_server.py 충돌 발생
3. 충돌 해소: `_MAP_VOLATILE_QOS` → `_LATCHED_QOS` 유지 (HEAD 버전 선택)
4. 머지 커밋(5c716fb) push → GitHub PR #5 MERGED 자동 처리

**PR #5에서 추가된 기능:**
- C-AMCL: `_amcl_init_thread()` — `AIP_AMCL_INIT_VEHICLES=aip3` 환경변수로 활성화
- follower_trigger_node: leader/follower_ids/spawn_in_gazebo 파라미터화 (시뮬/실차 분리)
- udp_status_heartbeat_adapter: `behaviors_from_payload()` + 테스트 보강
- supervisor_node: vehicle discovery 예외 시 debug 로그

---

### aip1 twist_mux 재시작 및 수동 제어 검증

**조치:**
- `fleet_main.launch.py`에 twist_mux Node 이미 통합됨 (별도 기동 불필요)
- ssh jh@192.168.0.3 → `nohup ros2 launch aip_bringup fleet_main.launch.py` 기동 (PID 1475)
- 기동 노드: ydlidar_ros2_driver_node, twist_mux, heartbeat_pub, robot_state_publisher

**DDS 이슈 및 해소:**
- 중앙 PC `ros2 topic list` → /parameter_events, /rosout만 표시
- 원인: ros2 daemon이 환경변수 없이 SIMPLE 모드로 실행 중
- 해소: FASTRTPS_DEFAULT_PROFILES_FILE 포함 환경에서 `ros2 daemon stop && ros2 daemon start`
- 결과: /main/* 토픽 10개 가시

**end-to-end 검증 결과 (모두 통과):**
- /main/twist_mux Subscriber: /main/central_cmd_vel, Publisher: /main/cmd_vel ✅
- /main/estop Bool(false) 발행 → estop_lock 해제
- 중앙 /main/central_cmd_vel linear.x=0.05 → aip1 /main/cmd_vel 수신 확인 ✅
- 웹 대시보드 http://localhost:8080 응답 ✅
- C0 항목 완료로 처리

**주의사항 (운영):**
- twist_mux estop_lock timeout=0.0 (무기한) → 웹 대시보드 "전체 정지 해제" 선행 필요
- 새 터미널에서 `ros2 daemon`을 올바른 환경(ROS_DOMAIN_ID=42, RMW, ROS_DISCOVERY_SERVER, FASTRTPS_DEFAULT_PROFILES_FILE)으로 재시작해야 중앙 PC에서 /main/* 토픽이 가시됨

---

## 2026-06-26 — aip2/aip3 웹 대시보드 OFFLINE 원인 분석 및 복구

### 원인
- UDP status overlay 스크립트(`/tmp/status_aip2.py`, `/tmp/status_aip3.py`)가 차량 호스트에서 중단됨
- `udp_status_heartbeat_adapter`는 실행 중이나 UDP 수신 없어 heartbeat 미게시 → supervisor OFFLINE 판정
- 진단 시 `ros2 daemon`이 `aip` (Simple Discovery) 모드로 실행되어 real 스택 노드가 불가시 상태

### 수정사항
- `scripts/manage_status_overlays.py`: aip2 SSH user `"aip1"` → `"aip2"` 오기 수정
- `docs/vehicles/2_aip2_scout_1/README.md`: SSH 접속 정보 `aip2@192.168.0.4` 추가

### 조치
- aip3 (`aip3@192.168.0.5`): overlay 재시작 → `/aip3/heartbeat` 0.9Hz 수신 ✅
- aip2 (`aip2@192.168.0.4`, pw=12345): overlay 재시작 → `/aip2/heartbeat` ~1.6Hz 수신 ✅
- `ros2 daemon`을 `aip real` 환경(FastDDS SUPER_CLIENT)으로 재시작 필수

### 운영 주의사항
- overlay 스크립트는 `/tmp/` 경로라 재부팅 시 소실 → 재부팅 후 반드시 재실행
- 중앙 PC에서 `ros2` CLI 사용 시 항상 `aip real` 소싱 후 daemon 상태 확인
- 영구 해결: systemd user service 설치 (`manage_status_overlays.py install-systemd`) 필요 (현재 미구현)

---

## 2026-06-26 — aip1 수동 주행 불가 원인 분석 및 ESP32 리셋 기능 구현

### 원인 분석 (순서대로)
1. **supervisor alias 오류**: 이전 세션에서 `supervisor.yaml` `aip1=main` 잘못 변경 → supervisor가 `/main/heartbeat`(Bool) 구독 → 타입 불일치로 aip1 OFFLINE. `aip1=aip1`로 복원 + 스택 재시작으로 해결
2. **수동 주행 불가**: 경로(웹→`/main/central_cmd_vel`→twist_mux) 자체는 정상. 실제 원인은 `aip_serial_bridge`의 ESP32 시리얼 쓰기 타임아웃 반복
3. **ESP32 타임아웃**: `/dev/aip_esp32`(CP2102, ttyUSB1) 장치는 존재하나 write timeout. fleet_main launch 재시작 시 포트가 닫혔다 열리면서 DTR 토글 → ESP32 EN 핀 리셋 → `aip_base up` 복귀

### aip1 이중 네임스페이스 확정 구조
- heartbeat: UDP overlay → `/aip1/heartbeat` (FleetHeartbeat) — supervisor `aip1=aip1`
- cmd_vel: 중앙 supervisor → `/main/central_cmd_vel` → aip1 `/main/twist_mux` — `vehicle_cmd_vel_overrides: aip1=/main/central_cmd_vel` 의도적 유지

### ESP32 리셋 기능 구현
- **`dashboard_server.py`**: `_ssh_esp32_reset_blocking(vid)` + `DashboardNode.esp32_reset()` + WebSocket `esp32_reset` 핸들러
- **`static/index.html`**: 수동 주행 섹션 하단 "⚡ ESP32 재시작 (aip1)" 버튼, 결과 토스트 표시
- **`scripts/manage_status_overlays.py`**: `remote_script_for_esp32_reset()` + CLI `esp32_reset` 명령
- 동작: 웹 버튼 → WebSocket → SSH → `pkill fleet_main` → 재시작 → 포트 재오픈 → DTR 토글
- aip1 전용 (aip2/aip3는 TurtleBot3 기반, 시리얼 브리지 없음)

---

## 2026-06-26 — 웹 대시보드 SLAM 맵 + LaserScan 포인트 오버레이 구현

### 문제
1. **SLAM 맵 표시 안 됨**: `dashboard_server.py`가 `/{topic_id}/map` 구독 중이나 실제 발행 토픽은 `/{topic_id}/dashboard/map` (slam_toolbox 직접 발행)
2. **LaserScan 구독 없음**: 웹 대시보드에 scan 포인트 렌더링 코드 자체가 없었음
3. **QoS 불일치**: LaserScan publisher가 BEST_EFFORT QoS 사용 → 기본 RELIABLE로 구독 시 메시지 미수신

### 조치 — `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py`
- `LaserScan`, `HistoryPolicy` import 추가
- `_VEHICLE_SCAN_OVERRIDES = {'aip1': '/main/scan'}` 상수 추가 (aip1은 /main ns)
- `_SENSOR_QOS` (BEST_EFFORT + VOLATILE + KEEP_LAST 5) 정의
- `_scan_ts: dict[str, float]` 2Hz throttle 상태 추가
- map 구독에 `/{topic_id}/dashboard/map` 경로 추가
- `_register_vehicle()` 내 LaserScan 구독 추가 (SENSOR_QOS)
- `_cb_scan()` 구현: polar→map frame XY 변환 (pose 기반), stride=4 downsampling, WebSocket `{type:'scan', vehicle_id, points}` push

### 조치 — `src/aip_fleet_dashboard/static/index.html`
- `state.scanPoints: {}` 추가
- WebSocket switch에 `case 'scan': onScan(msg)` 추가
- `onScan(msg)` 함수 추가 (포인트 저장 + redraw)
- `drawAll()` 내 Vehicle trails 전에 scan 포인트 렌더링 블록 추가 (차량별 COLORS + 60% 투명도, 2×2px 픽셀)

### 토픽 매핑 확정
| 차량 | scan 토픽 | map 토픽 |
|------|-----------|---------|
| aip1 | `/main/scan` (override) | `/aip1/dashboard/map` |
| aip2 | `/aip2/scan` | `/aip2/dashboard/map` |
| aip3 | `/aip3/scan` | `/aip3/dashboard/map` |

---

## 2026-06-26 — 중앙 제어 AI (Fleet Brain) 설계 기본 틀 확정

### 배경
사용자 요청: "다중 차량 관제 플랫폼을 기반으로 순찰 관리와 상황 판단을 직접 진행하는 AI 모델 구현."
다른 작업에 집중해야 하는 상황이라 **이번 세션은 기본 틀(설계 프레임워크) 문서화로 한정** (코드 미구현).

### 결정 (사전 질답 기반)
| 항목 | 결정 |
|---|---|
| AI 유형 | **로컬 규칙/경량 ML** (클라우드 LLM 배제 — 인터넷 외부망 차단) |
| 자율성 | **제안만 (human-in-the-loop)** — 운영자 승인 후 실행 |
| 책임 범위 | ① 이상징후 트리아지+출동 ② 순찰 스케줄링/최적화 ③ 차량 상태·장애 대응 |
| 인터넷 | 플릿망만, 외부 차단 → 전부 중앙 PC 로컬 실행 |

### 핵심 아키텍처 판단
- 입력 토픽(`/fleet/status`·`/fleet/alerts`·`/fleet/peer_poses`·`/fleet/coverage_pct`)과
  출력 명령 경로(`dashboard_server.py` 의 `cmd_navigate`/`cmd_patrol`/`cmd_override`,
  `/patrol_planner/cmd`)가 **모두 이미 존재**. 신규 `aip_fleet_brain` 노드는 그 사이에서
  `/fleet/suggestions`(std_msgs/String JSON, MVP)만 추가하고 차량 토픽에 직접 발행하지 않음.
- 자동 ESTOP은 기존 `watchdog_node` 의 반사적 안전 영역으로 분리 유지. Brain은 그 위의
  느린 전략적 자문 레이어.

### 결과 (산출물)
- `docs/CENTRAL_AI.md` 신규 — 설계 단일 진실(SSOT). 데이터 흐름·패키지 골격·정책 3종·
  JSON 계약·안전 가드레일·구현 로드맵 수록.
- `docs/agent_context/pending_tasks.md` — "🧠 중앙 제어 AI (Fleet Brain)" 미착수 섹션 추가
  (BRAIN-1~5 로드맵).
- `docs/HANDOFF.md` — 읽을 파일 목록에 `docs/CENTRAL_AI.md` 추가.

### 다음 단계 (미착수)
BRAIN-1 (`aip_fleet_brain` 패키지 + `brain_node` 골격)부터. 별도 세션에서 착수.

---

## 2026-06-26 — Nav2·SLAM 기능 재확보 작업

### 목표
전 차량(aip1·aip2·aip3)에서 Nav2 + SLAM 기능을 독립적으로 재확보.
각 차량에 `/aipN/navigate_to_pose` 액션 서버 활성화.

### 핵심 문제 & 해결

#### 문제 1: DWB critics 로드 실패 (aip1)
- **증상**: `[controller_server]: Couldn't load critics! Couldn't find 'aip1.controller_server.ros__parameters.FollowPath.critics'`
- **원인**: `navigation_launch.py`는 `RewrittenYaml(root_key=namespace)`로 파라미터를 `aip1:` 키 아래 감싸지만,
  `PushRosNamespace`가 `IncludeLaunchDescription`에서 제대로 적용되지 않아 노드가 루트 네임스페이스에서
  실행됨. 노드는 `controller_server.FollowPath.critics`를 찾지만 파일에는 `aip1.controller_server...`만 존재.
- **해결**: `/home/jh/aip_ws/src/aip_bringup/launch/nav2_aip1.launch.py` 신규 생성.
  각 노드에 명시적 `namespace=namespace` 및 `('tf', '/tf')` 리매핑 적용.

#### 문제 2: TF 분리 문제 (aip1)
- **증상**: `Timed out waiting for transform from base_footprint to odom — Invalid frame ID "odom"`
- **원인**: 시스템 `navigation_launch.py`의 `remappings=[('/tf', 'tf')]`가 `/aip1/` 네임스페이스 노드들을
  `/aip1/tf`를 구독하게 만들지만, 하드웨어는 전역 `/tf`에 발행 → TF 트리 분리.
- **해결**: `nav2_aip1.launch.py`에서 `('tf', '/tf')` (상대→절대) 리매핑. slam_node에도 동일 적용.

#### 문제 3: nav2_aip1.launch.py 심볼릭 링크 없음
- **증상**: `[Erno 2] No such file or directory: '.../nav2_aip1.launch.py'`
- **원인**: `--symlink-install`은 빌드 시점에 없던 신규 파일의 심볼릭 링크를 생성하지 않음.
- **해결**: 수동 심볼릭 링크 생성.
  ```bash
  ln -sf /home/jh/aip_ws/src/aip_bringup/launch/nav2_aip1.launch.py \
         /home/jh/aip_ws/install/aip_bringup/share/aip_bringup/launch/nav2_aip1.launch.py
  ```

#### 문제 4: aip2 SLAM 미시작
- **원인**: `aip2_robot` 컨테이너가 `start_robot_stack.sh` 대신 `/entrypoint.sh bash`로 시작됨 → SLAM 미실행.
- **임시 해결**: `docker exec -d aip2_robot bash -c "ros2 run slam_toolbox async_slam_toolbox_node ..."` 수동 실행.
- **미완**: `/scan_fixed` 미발행 → aip2 LIDAR 하드웨어 문제로 SLAM 맵 구축 불가.

### 결과 (확인됨)

| 차량 | Nav2 `/navigate_to_pose` | SLAM 상태 | 대시보드 맵 |
|------|--------------------------|-----------|-------------|
| aip1 | ✅ `/aip1/navigate_to_pose` 활성 | 실행 중, ESP32 단절로 오도메트리 없음 | `/aip1/map` pub=0 (맵 미생성) |
| aip2 | ✅ `/aip2/navigate_to_pose` 활성 | 수동 시작, LIDAR 데이터 없음 (`/scan_fixed` 미발행) | `/aip2/dashboard/map` pub=0 |
| aip3 | ✅ `/aip3/navigate_to_pose` 활성 | 정상 (이전 세션) | `/aip3/dashboard/map` pub=2 ✅ |

**중앙 PC에서 전 차량 `/navigate_to_pose` 액션 서버 확인 완료.**

### 수정된 파일 (aip1 SSH)
- `/home/jh/aip_ws/src/aip_bringup/launch/fleet_main.launch.py` — nav2 launch 경로 변경, slam_node TF 리매핑 추가
- `/home/jh/aip_ws/src/aip_bringup/launch/nav2_aip1.launch.py` (신규) — 네임스페이스·TF 리매핑 명시적 적용

### 미완 (하드웨어 기인)
- **aip1 serial_bridge**: ESP32 반복 단절 오류 → 오도메트리 없음 → SLAM 맵 미생성. 물리적 재연결 필요.
- **aip2 LIDAR**: `/scan_fixed` 미발행. turtlebot3 LIDAR 연결 또는 브링업 확인 필요.
- **aip2 컨테이너**: 재부팅 시 `start_robot_stack.sh`로 자동 시작되도록 compose 설정 확인 필요.

### 다음 단계
1. aip1 ESP32 물리 재연결 후 오도메트리/SLAM 정상화 확인
2. aip2 LIDAR 하드웨어 점검 (`/scan_fixed` 발행 여부 확인)
3. aip2 컨테이너 재시작 설정 수정 (CMD → `start_robot_stack.sh`)

---

## 2026-06-26 — 전 차량 DWB → Regulated Pure Pursuit (RPP) 컨트롤러 교체

### 목표
RPi4B Cortex-A72에서 MPPI SIGILL 크래시 및 고부하 문제를 근본 해결하기 위해
전 차량 컨트롤러를 DWB(동적 샘플링) → RPP(O(1) 경로 추종)로 통일 교체.

### 의사결정 배경

- **MPPI 불가**: `SIGILL` (Illegal Instruction) — Cortex-A72(ARMv8.0-A)가 ARMv8.2+ SIMD 명령 미지원.
- **DWB 부하**: 각 제어 주기마다 수십~수백 개 궤적 시뮬레이션 → 5Hz에서도 RPi4B CPU 30~40% 점유.
- **RPP 선택 이유**: 순수 SW, O(1) 연산, CPU < 1%, 순찰·직선·약한 곡선 미션에 최적.
  동적 장애물에 대해서는 속도 조절(regulated scaling)로 대응.
- **속도 스펙 차별화**:
  - aip1(대형 자작 차량): `desired_linear_vel: 0.30 m/s` (최대 0.40 m/s까지 가능)
  - aip2(TB3 Burger): `desired_linear_vel: 0.18 m/s` (Burger 한계 0.22 m/s 안전마진)
  - aip3(자작 소형 차량): `desired_linear_vel: 0.20 m/s`

### 수정된 파일

**실차 (SSH 직접 수정)**:
| 파일 | 변경 내용 |
|------|-----------|
| `/home/jh/aip_ws/src/aip_bringup/config/nav2_params_aip1.yaml` | FollowPath 블록 41줄 → RPP 22줄 |
| `/home/aip2/scout_1_turtlebot3/ros2_ws/src/scout_1_bringup/config/nav2_params.yaml` | FollowPath 블록 43줄 → RPP 22줄 |
| `/home/aip3/industrial_sub_vehicle/ros2_ws/src/sub_vehicle_bringup/config/nav2_params.yaml` | FollowPath 블록 42줄 → RPP 22줄 |

**중앙 워크스페이스 레퍼런스 (동기화)**:
- `src/aip_fleet_real/config/main_agv/nav2.yaml` — DWB → RPP 교체
- `src/aip_fleet_real/config/turtlebot3/nav2.yaml` — RotationShim+MPPI → RPP 교체
- `src/aip_fleet_real/config/custom_vehicle/nav2.yaml` — MPPI → RPP 교체

각 차량 `.yaml.bak` 백업 파일 생성됨 (`nav2_params.yaml.bak`).

### 공통 RPP 파라미터

```yaml
FollowPath:
  plugin: 'nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController'
  use_velocity_scaled_lookahead_dist: true   # 속도에 비례한 전방 추종 거리
  use_regulated_linear_velocity_scaling: true # 곡률 구간 자동 감속
  use_rotate_to_heading: true                 # 큰 헤딩 오차 시 제자리 회전 먼저
  rotate_to_heading_min_angle: 0.785          # ~45° 이상 헤딩 오차 시 제자리 회전
  allow_reversing: false                      # 후진 금지
  max_angular_accel: 3.2                      # 급회전 방지
```

### 패키지 설치 확인

- aip1: `ros-humble-nav2-regulated-pure-pursuit-controller 1.1.20` ✅
- aip2: Docker 이미지 내 동일 패키지 ✅
- aip3: Docker 이미지 내 동일 패키지 ✅

### 다음 단계
1. aip1 ESP32 재연결 → `nohup bash ~/start_fleet.sh with_base:=true &` 로 스택 재시작
2. aip2/aip3 Docker 컨테이너 재시작 후 RPP 파라미터 로드 확인
3. NavigateToPose goal 테스트로 실제 경로 추종 동작 확인

---

## 2026-06-27 — 전 차량 재부팅 후 스택 복구 + RPP 파라미터 보정

### 완료 작업

#### 1. 속도 클램핑 2-레이어 구현 (dashboard_server.py + serial_bridge)

**문제**: 수동 제어 시 0.22 m/s 초과 명령 발생 시 ESP32 펌웨어가 구동을 완전 거부(0 출력).
**원인 추정**: ESP32 firmware 내부에서 max_vel 초과 명령을 0으로 처리.
**해결책**: 소프트웨어 계층 두 곳에서 클램핑 적용.

- `dashboard_server.py`: `_VEHICLE_VEL_LIMITS` 딕셔너리 + `cmd_override()` 클램핑 추가
  ```python
  max_lin, max_ang = _VEHICLE_VEL_LIMITS.get(vehicle_id, _DEFAULT_VEL_LIMIT)
  twist.linear.x  = max(-max_lin, min(max_lin, lx))
  twist.angular.z = max(-max_ang, min(max_ang, az))
  ```
- `aip1 serial_bridge` (`base.launch.py`): `max_linear: 0.30, max_angular: 1.0` 파라미터 추가.

#### 2. RPP `max_angular_accel` 보정

이전 세션에서 aip1/aip3를 3.2 rad/s²(DWB acc_lim_theta 초과값)로 설정한 오류 수정:
- aip1(대형 자작): `max_angular_accel: 1.0` (DWB acc_lim_theta=1.0 기준)
- aip2(TB3 Burger): `max_angular_accel: 3.2` (Burger spec acc_lim_theta=3.2)
- aip3(소형 자작): `max_angular_accel: 1.0` (DWB acc_lim_theta=1.0 기준)

#### 3. 전 차량 `desired_linear_vel` 0.30 m/s 통일

사용자 결정: aip1/aip2/aip3 모두 0.30으로 통일.
중앙 레퍼런스 파일(main_agv/turtlebot3/custom_vehicle) 및 실차 파일 모두 수정 완료.

#### 4. aip1 fleet_main systemd user 서비스 생성

`~/.config/systemd/user/aip-fleet.service` 작성 및 `systemctl --user enable` 완료.
- 환경변수: ROS_DOMAIN_ID=42, RMW=rmw_fastrtps_cpp, FASTRTPS profile, DS 192.168.0.10:11811
- ExecStart: source humble + aip_ws → `ros2 launch aip_bringup fleet_main.launch.py with_base:=true`
- **linger 비활성**: `sudo loginctl enable-linger jh` 실행 필요 (sudo 패스워드 없어 미완료)

#### 5. aip2/aip3 컨테이너 시작 + RPP 로드 확인

- aip2_robot: `docker start aip2_robot` → Up 확인
- docker-robot-1(aip3): `docker start docker-robot-1` → Up + RPP 로드 로그 확인
  ```
  [aip3.controller_server]: Created controller : FollowPath of type
  nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController
  [aip3.controller_server]: Controller Server has FollowPath controllers available.
  ```

#### 6. aip3 재부팅 후 컨테이너 자동 시작 원인 규명

RestartPolicy=no, rc.local/crontab 없음, docker/robot 관련 systemd 서비스 없음.
**결론**: Docker 데몬 재시작 시 컨테이너 상태 복원(live-restore 기본 동작). 이전 실행 중이던 컨테이너가
시스템 강제 재부팅(SIGKILL) 시 "running" 상태로 기록됨 → 다음 부팅에서 자동 복원.
이후 정상 종료 후 재부팅하면 재발하지 않을 것으로 예상.

### 잔여 (하드웨어 필요)

1. **aip1**: ESP32 USB 물리 재연결 → `systemctl --user start aip-fleet.service`로 스택 기동
   - 또는 수동: `source ~/.bashrc && ros2 launch aip_bringup fleet_main.launch.py with_base:=true`
   - linger 활성화: `sudo loginctl enable-linger jh` (재부팅 자동 기동 위해)
2. **RPP 동작 검증**: NavigateToPose goal 전송 → 경로 추종 확인

---

## 2026-06-27 — aip1 FastDDS 로컬 DS 추가 + Nav2 즉시 활성화 + RPP 검증

### 작업 내용

#### 1. FastDDS 클라이언트 프로파일 배포 완료
- `/home/kde/aip_swarm_ws/config/fastdds_client_profile.xml` → aip1의 `/home/jh/aip_ws/config/fastdds_client_profile.xml` scp 복사
- 서비스 파일에 `FASTRTPS_DEFAULT_PROFILES_FILE=/home/jh/aip_ws/config/fastdds_client_profile.xml` 추가 + daemon-reload

#### 2. 로컬 Discovery Server 추가 (핵심 수정)
**문제**: lifecycle_manager가 `controller_server/get_state` 서비스를 수십 분간 발견 못 함.
**원인**: FastDDS SUPER_CLIENT 모드에서 DS(192.168.0.10)를 경유하는 EDP 패킷이 60% 패킷 손실 환경에서 best-effort 전달로 누락됨 → DS는 재전송 안 함.
**해결**: aip1 내 로컬 DS 추가.

| 구성 | 내용 |
|---|---|
| 로컬 DS | `fast-discovery-server -i 1 -l 127.0.0.1 -p 11812` |
| GUID prefix | `44.53.01.5f.45.50.52.4f.53.49.4d.41` |
| systemd 서비스 | `/home/jh/.config/systemd/user/aip-local-ds.service` (enabled) |
| LD_LIBRARY_PATH | `/opt/ros/humble/lib` 명시 필요 |

`/home/jh/aip_ws/config/fastdds_aip1_profile.xml` 신규 생성:
- discoveryServersList에 로컬 DS(127.0.0.1:11812) + 중앙 DS(192.168.0.10:11811) 모두 포함
- leaseDuration=30s, leaseAnnouncement=5s
- 서비스 파일의 `FASTRTPS_DEFAULT_PROFILES_FILE` 경로를 신규 파일로 업데이트

#### 3. nav2_aip1.launch.py: lifecycle_manager 30초 지연 시작
- `TimerAction(period=30.0)` 추가 — 로컬 DS에 노드들이 등록 완료된 후 lifecycle_manager 시작
- `GroupAction` 밖으로 lifecycle_manager를 분리
- 백업: `nav2_aip1.launch.py.bak` 저장

#### 4. 결과
서비스 재시작 후 **~36초 만에 Nav2 전체 활성화**:
- T=0s: controller_server 등 7개 Nav2 노드 시작
- T=30s: lifecycle_manager 시작 → **1초 내** controller_server/get_state 발견 (로컬 DS 경유)
- T=36s: "Managed nodes are active" + bond timer 시작

#### 5. RPP 동작 검증 완료
```
ros2 action send_goal /aip1/navigate_to_pose nav2_msgs/action/NavigateToPose \
  '{pose: {header: {frame_id: map}, pose: {position: {x: 0.5, y: 0.0}}}}'
→ Goal finished with status: SUCCEEDED
```

### 현재 aip1 상태

| 구성 요소 | 상태 |
|---|---|
| aip-local-ds.service | active (127.0.0.1:11812, server-id=1) |
| aip-fleet.service | active |
| serial_bridge | /dev/aip_esp32 정상, odom 20Hz |
| Nav2 (전체) | ACTIVE (36초 내 활성화) |
| FastDDS 프로파일 | /home/jh/aip_ws/config/fastdds_aip1_profile.xml |
| RPP NavigateToPose | SUCCEEDED ✅ |

### 잔여

1. **aip1 linger**: `sudo loginctl enable-linger jh` — 재부팅 시 aip-local-ds + aip-fleet 자동 기동
2. **aip2 LIDAR 점검**: /scan 발행 여부 미확인
3. **C-AMCL**: aip3 initialpose 자동 발행 실차 검증

---

## 2026-06-27 (계속) — aip2 복구 + aip3 Nav2 TF 프레임 수정

### aip1 재부팅 자동 기동 (linger 대안)
sudo 비밀번호 미확보로 `loginctl enable-linger` 불가 → crontab @reboot 대안:
- `/home/jh/aip_start_on_boot.sh`: `sleep 30 → systemctl --user start aip-local-ds → sleep 3 → aip-fleet`
- `crontab -l`: `@reboot /home/jh/aip_start_on_boot.sh >> /home/jh/aip_boot.log 2>&1`

### aip2 복구
- 컨테이너 50분 전 종료 → `docker start aip2_robot` 후 정상 기동
- `/aip2/scan` `/aip2/map` `/aip2/odom` `/aip2/heartbeat` 발행 확인 ✅
- Docker RestartPolicy `unless-stopped` 적용 → 재부팅 후 자동 복구

### aip3 Nav2 TF 프레임 불일치 수정
**문제**: `local_costmap`이 `aip3/odom → aip3/base_link` TF를 기다리지만 실제 TF는:
- AMCL: `map → odom` (비네임스페이스)
- combined_safety_node: `odom → base_footprint` (비네임스페이스)

**원인**: `robot.yaml`의 `odom_frame_id: aip3/odom` 파라미터가 `combined_safety_node`에 적용되지 않음 (파라미터 키가 매칭 안 됨)

**수정** (`nav2_params.yaml`):
| 항목 | 이전 | 이후 |
|---|---|---|
| `amcl.base_frame_id` | `aip3/base_link` | `base_footprint` |
| `amcl.odom_frame_id` | `aip3/odom` | `odom` |
| `bt_navigator.robot_base_frame` | `aip3/base_link` | `base_footprint` |
| `local_costmap.global_frame` | `aip3/odom` | `odom` |
| `local_costmap.robot_base_frame` | `aip3/base_link` | `base_footprint` |
| `global_costmap.robot_base_frame` | `aip3/base_link` | `base_footprint` |

백업: `nav2_params.yaml.bak_20260627`
컨테이너 재시작 후 검증 중

---

## 2026-06-27 — Fleet Brain 브랜치 분석 + 원격 접속 환경 점검

### 배경
`feat/fleet-brain` 브랜치(별도 세션 작업)를 분석하고 Tailscale 원격 GPU PC 학습 접속을 시도.

### feat/fleet-brain 브랜치 현황 (분석 완료)
- **BRAIN-1~4 완전 구현**: `aip_fleet_brain` 패키지 (정책 4종: anomaly_triage/patrol_scheduler/health_monitor/coverage_allocator), 대시보드 연동, 테스트 25개+
- **RL 파이프라인**: 3개 Gymnasium 환경 (formation/coverage/coverage_grid), PPO(SB3), ONNX export
- **CPU 학습 결과**: formation 56%, coverage 80.5%, coverage_grid ~55% — GPU 학습 필요
- **GPU PC**: WSL2+ROCm 준비 완료, .zip/.onnx 이미 존재 (Tailscale: 100.116.223.0)

### 결정: HealthMonitor 도킹 좌표 동적화 필요
- 현재: `brain.yaml` 정적값(`dock_poses_json`)
- 문제: 대시보드 UI에서 유동 관리하는 `~/aip_maps/dock_positions.json`과 불일치 가능
- 학습(RL)과는 무관 — RL 환경에 도킹 개념 없음
- **수정 방향**: `health_monitor.py`가 `~/aip_maps/dock_positions.json` 동적 읽기, 미존재 시 `brain.yaml` 폴백

### Tailscale/원격 접속 이슈 (2026-06-27)
- **학교망 Fortinet**: SSL 인터셉트로 Tailscale 제어 플레인 차단 → 로그인 불가
- **해결**: 핫스팟으로 1회 로그인 성공 → `tailscale status` 양 기기 확인 (100.125.29.37, 100.116.223.0)
- **학교망 복귀 후**: ping 응답 (터널 부분 유지), 단 status는 offline 표시
- **RDP 실패**: `ERRCONNECT_PASSWORD_CERTAINLY_EXPIRED` — Windows 비밀번호 만료
- **SSH 실패**: OpenSSH 서버 미활성화
- **귀가 후 조치 필요**: ① Windows 비밀번호 변경 ② OpenSSH 서버 활성화

### 다음 세션 진입점
1. `tailscale status` 확인 (학교망이면 핫스팟 로그인 선행)
2. `git checkout -b feat/fleet-brain origin/feat/fleet-brain`
3. Brain 빌드/테스트 → HealthMonitor 동적화 → GPU 학습 → E2E 검증

## 2026-06-27 (오후) — 중앙 ONLINE 미발행 근본원인 규명 및 해결

### 증상
- 차량 ID 카드 ONLINE 상태 미발행. DDS 과변경 의심으로 시작했으나 실제 원인은 별개.

### 근본 원인 (연쇄)
1. 중앙 PC 재부팅 → 시계 미래값 후 NTP 보정 (jounalctl 타임스탬프 스큐로 진단 혼란)
2. **이전 세대 systemd가 띄운 stray `fast-discovery-server`(PID 29666)가 포트 11811 점유**
3. 현재 `fastdds-ds.service`가 11811 바인드 실패 → 크래시 루프 (restart counter 70+)
4. `aip-central.service`의 `Requires=fastdds-ds.service` → flap마다 aip-central에 SIGTERM
5. `central_real_combined.py`의 14초 stabilize sleep 창에 SIGTERM 유입 → rclpy 셧다운 → `WatchdogNode()` NotInitializedException → aip-central도 크래시 루프 → ONLINE 파이프라인 정지

### 진단 결정타
- 포그라운드로 `central_real_combined.py` 직접 실행 시 정상 동작(크래시 없음), systemd에서만 크래시 → 외부 SIGTERM(의존성 flap)이 원인임을 특정.

### 해결
- stray DS(29666) `kill` → `fastdds-ds.service` 11811 정상 바인드 → flap 종료 → **aip-central 안정화(HTTP 200, 5분+ 생존)**, aip2 ONLINE 복구 확인.

### 차량 DDS 변경 원복
- 앞서 시도한 aip2/aip3 local-DS(loopback) 추가는 **전부 원복**:
  - aip2: `start_robot_stack.sh` → `unset FASTRTPS_DEFAULT_PROFILES_FILE` 복원, local DS 코드 제거
  - aip3: `.env` FastDDS 프로파일 `fastdds_client_profile.xml`로 복원, `docker-compose.yml` local DS 제거
- aip3 nav2 TF 수정(`nav2_params.yaml` `aip3/odom`·`aip3/base_link`)은 정당한 수정으로 **유지** (NavigateToPose SUCCEEDED 검증 완료).

### 남은 별개 이슈 (DDS-over-WiFi 신뢰성)
- aip1/aip3 heartbeat가 supervisor 미도달, aip2는 간헐 수신(flapping). 본 건(중앙 크래시)과 별개의 Discovery Server EDP 전달 신뢰성 문제. 추가 변경은 사용자 승인 후 진행.

---

## 2026-06-27 (야간) — aip1 토픽 트리 /main → /aip1 네임스페이스 통일

### 배경 및 결정 이유
- aip1이 `/main` 네임스페이스로 토픽을 발행하던 것은 초기 '메인 차량 + 스카우트' 구성 시절 잔재.
- 현재 플릿 규약(`aip1/aip2/aip3`)과 불일치로 supervisor alias(`aip1=/main/central_cmd_vel`) 등 우회 설정이 누적.
- **결정**: 차량 소스에서 네임스페이스를 `/aip1`로 통일, 중앙 우회 설정 전부 제거.

### 변경 내역 (aip1 차량 — jh@192.168.0.3)
| 파일 | 변경 |
|------|------|
| `~/aip_ws/src/aip_bringup/launch/fleet_main.launch.py` | `namespace="main"` × 2 → `"aip1"`, `PushRosNamespace("main")` → `"aip1"`, remap `/main/cmd_vel` → `/aip1/cmd_vel` |
| `~/aip_ws/src/aip_bringup/config/twist_mux_main.yaml` | 루트키 `/main/twist_mux:` → `/aip1/twist_mux:` |
| `~/aip_ws/src/aip_bringup/config/slam_toolbox_aip1.yaml` | `scan_topic: /main/scan` → `/aip1/scan` |
- 백업: 각 파일 `.bak_20260627_*` 생성 완료.
- aip1에서 `colcon build --symlink-install --packages-select aip_bringup` 성공.

### 변경 내역 (중앙 — kde PC)
| 파일 | 변경 |
|------|------|
| `src/aip_fleet_bringup/config/supervisor.yaml` | `vehicle_cmd_vel_overrides: ["aip1=/main/central_cmd_vel"]` → `"/aip1/central_cmd_vel"` |
| `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py` | `_LEGACY_TOPIC_TO_DISPLAY['main']` 항목 제거, cmd_vel/scan override `/main/*` → `/aip1/*`, 맵 fallback `'main'` 제거 |
- 중앙 `colcon build --symlink-install --packages-select aip_fleet_dashboard aip_fleet_bringup` 성공.

### 검증 결과 (aip1 재부팅 후)
- aip1 로컬 콘솔: `/main` 노드 **0개**, 활성 서비스 `aip-fleet.service`·`aip-local-ds.service`만.
- aip1 PID 확인: ydlidar·serial_bridge·twist_mux·heartbeat·slam·controller 전부 `__ns:=/aip1`.
- 중앙 DDS에서 `/aip1/scan` 발행자 1, `/aip1/heartbeat` 발행자 2(정상).
- 중앙에 잔존하는 `/main/*` 13개는 DS stale 엔드포인트(차량 재부팅 전 등록분) — 로컬 콘솔 직접 확인으로 aip1에 `/main` 발행 주체 없음 확정.

### aip3 부팅 병목 패치 (이전 세션 연속)
- `~/industrial_sub_vehicle/docker/docker-compose.yml` 조건부 빌드 패치 적용 및 검증:
  - `colcon build --symlink-install` → `{ [ -f install/setup.bash ] && echo skip-colcon-build:cache-hit || colcon build --symlink-install; }`
  - `docker logs docker-robot-1 | grep skip-colcon-build` → `skip-colcon-build:cache-hit` 확인.
  - 효과: 부팅 마비(분 단위) → 기동 약 15초로 단축.

### 현재 미해결 (다음 세션 진입점)
1. **aip1 ssh 불안정**: bringup 부하(Nav2+SLAM 동시 로딩 ~15초 I/O 창) 중 ssh 타임아웃. aip3와 동일 패턴. stagger 기동 고려.
2. **aip2/aip3 오프라인**: 본 세션에서 전원 꺼짐. 다음 세션 켜서 supervisor ONLINE 확인 필요.
3. **DS stale ghost `/main/*`**: DS 재시작 후에도 소멸 안 됨 → FastDDS SUPER_CLIENT 환경에서 정상(lease duration 만료 전까지 잔존). 기능적 무해, 방치 가능.
4. **aip2 heartbeat 간헐 flapping**: DDS-over-WiFi UDP 손실 문제, 별도 세션 개선 필요.
5. **Fleet Brain GPU 학습**: Tailscale + Windows SSH 접속 미완. 귀가 후 조치 필요.

---

## 2026-06-27 (야간) — 실차 부하·SSH 완화 + 운영(미션) 모드 bringup (main 브랜치)

**배경/요청**: 오늘 작업으로 전 차량 부하 발생 → SSH 불안정(위 미해결 #1 "stagger 기동 고려").
차량 미연결 상태에서 작업 기록 기반으로 문제 사유 수정 + 관제(수동/미션 제어) 동작 보장 요청.
사용자 정의 "수동 제어" = 운영자 주도 미션 제어(웨이포인트·순찰·금지구역)까지 = **Nav2 상시 필요**,
SLAM 은 AMCL 로 대체 가능. (브랜치: 사용자 지정 — 로컬 `main` 직접 작업, fleet-brain AI 는 차후.)

**진단(저장소 정적 분석)**:
- 부하 근본원인 = **Nav2 라이프사이클 + SLAM 동시 활성화**로 RPi4B 수~십수초 포화 → SSH 타임아웃.
- `turtlebot3.launch.py`(aip2)·`custom_vehicle.launch.py`(aip3) = **staggering 전무**(동시 기동). aip1만 보유.
- 중앙 수동제어 경로(`/aip1/central_cmd_vel` → twist_mux → `/aip1/cmd_vel`)는 main 에서 일관 = 코드 버그 없음.
- `config/main_agv/twist_mux.yaml` 노드키가 `/main/twist_mux:` 잔존(배포 `/aip1` 와 드리프트).
- 금지구역 costmap 미배선(실차) — `keepout_zone_node` 시뮬에만, 실차 nav2.yaml 관측원에 keepout_cloud 없음.

**결정/수정(코드)**:
1. **staggering 추가** — aip2/aip3 launch 에 `TimerAction`(드라이버 t=0 → 위치추정 t≈4 → Nav2 t≈10 → 순찰 t≈12).
2. **localization 모드 도입** — `fleet_main.launch.py` `localization:={slam|amcl|none}` + `map_yaml`.
   - `amcl`: map_server(/map latched) + amcl(map→odom) + lifecycle_manager. 운영 기본(저부하·좌표계 고정).
   - `slam`: 기존 slam_toolbox(매핑 1회용). slam/amcl 는 staggering 동일 슬롯, 상호배타 조건.
3. **실차 AMCL 설정 신규** `config/main_agv/amcl.yaml`(RPi4B 부하용 파티클 400~1500·빔 120, 프레임 odom/base_footprint).
4. **twist_mux.yaml 정합화** `/aip1/twist_mux:` + central 슬롯 `central_cmd_vel`(대시보드/supervisor 타겟), 표준 차이 주석화.
5. **slam/nav2.yaml 헤더 주석** `namespace=main` → `aip1` 정정.
6. **문서** — `REAL_VEHICLE_OPERATION.md §7` 전면 갱신(부하 원인·staggering·localization 모드·미션 제어 활성화
   `AIP_NAV_ALLOWED_IDS`·keepout 갭), `ANALYSIS.md` 부하/keepout/twist_mux 분석 추가.

**검증**: 이 PC ROS2 부재 → 편집 launch 4종 `py_compile` 통과 + 정적 검토. **실차 E2E 미검증**(차량 미연결).
- 남은 검증: RPi 에서 `localization:=amcl map_yaml:=~/aip_maps/latest_fleet_map.yaml` E2E(map_server→amcl 수렴→Nav2 goal),
  중앙 `AIP_NAV_ALLOWED_IDS` 설정 후 대시보드 웨이포인트/순찰, keepout costmap 적용 여부(부하 트레이드오프).

**다음**: ① 실차 연결 시 위 E2E 검증 → ② keepout costmap 배선(선택) → ③ 안정 후 fleet-brain AI 설계/학습 재개 → main 병합.

### 2026-06-27 (야간, 이어서) — 웹 UI 전수 검증 + 안정성 점검

**요청**: 차량 즉시 연결 전, 웹 UI 구현 기능의 백엔드/차량 대응성 + 안정성 철저 검증.
**방법**: UI 송신 cmd 24종·수신 type 26종을 `dashboard_server.py`·patrol_planner·serial_bridge·
supervisor 까지 추적(정적). SSOT: `docs/ANALYSIS.md §웹 UI 전수 검증(D~F)`.

**발견·조치**:
1. **[미션] 패널 고아(무동작)** — `start_mapping`·`deploy_patrol`·`reset_mission` top-level cmd 가
   백엔드 핸들러 없음 + UI 가 기다리는 `mission_phase` 미발행 + `stop` 은 patrol_planner 미지원 명령.
   → **사용자 결정: 일단 비활성화(추후 AI 파이프라인 통합)**. `index.html` 비활성 배너 + 버튼 5종
   `disabled` + JS `MISSION_PANEL_ENABLED=false` 가드 적용. (JS 괄호/버튼 균형 검증 통과)
2. **ESTOP 자율주행 중 래치 안 됨(안전)** — twist_mux `estop_lock` 락 비활성 + serial_bridge `/estop`
   미구독 → Nav2 가동 중 0.5s 후 재개 위험. **사용자 결정: 코드 준비 + 실차 검증 후 적용**.
   → `main_agv`/`turtlebot3` twist_mux.yaml estop_lock 블록을 "검증 후 활성화" 가이드로 정비,
   절차 `REAL_VEHICLE_OPERATION.md §7-5`(estop_lock=False 평상 발행 확인 후 주석 해제). **활성화는 안 함.**
3. **navigate 기본 차단** — `cmd_navigate` 가 `AIP_NAV_ALLOWED_IDS` 미설정 시 전부 거부(안전 게이트).
   중앙에서 설정 필요(§7-3). keepout 은 goal 거부만, costmap 차단 미배선(§B, 선택).

**정상 확인**: 수동 주행(override 80ms 연속·클램핑·deadman), 단일 목표 이동, 순찰 편집, 맵/dock/pose/
lock/esp32_reset/bag, 상태·위치·스캔 표시, QoS 호환, 노드 예외 내성. `set_scenario`는 실차 무효(무해).

**연결 직후 운영 체크리스트**: ① `AIP_NAV_ALLOWED_IDS` 설정 → ② `localization:=amcl`+저장맵 →
③ 부팅 중 SSH 유지 확인 → ④ 수동 주행/목표 이동/순찰 편집 동작 확인 → ⑤ (선택) estop_lock 검증·활성화.

### 2026-06-27 (야간, 이어서) — 금지구역 costmap 차단 구현 (자율 매핑 중 위험구역 회피)

**요청**: 금지구역이 자율 매핑 중 접근금지/위험 구역 진입을 막아야 함. costmap 배선 구현 요청.
**구현(시뮬 `nav2_full.yaml` 검증 패턴 이식)**:
- `central.launch.py` 에 `keepout_zone_node` 기동 추가(`with_keepout:=true` 기본). 대시보드
  `/fleet/keepout_zones` → `/fleet/keepout_cloud`(PointCloud2, map, 1Hz 재발행).
- 실차 `aip_fleet_real/config/{main_agv,turtlebot3,custom_vehicle}/nav2.yaml` local·global
  obstacle_layer 6개에 `keepout_cloud` 관측원 추가. **`clearing:False·marking:True`**(저부하).
- 효과: Nav2 자율 경로(자율 매핑/탐사·순찰·목표 이동)가 위험구역 회피·진입거부. 해제 시 ClearEntireCostmap.
- **한계**: 수동 teleop 은 costmap 게이트 아님(twist_mux central 우회) → 운영자 직접 회피 필요.
**검증**: central.launch.py py_compile + 3개 nav2.yaml YAML 파싱·6 costmap keepout 배선 단언 통과.
실차: 구역 그리기→`/fleet/keepout_cloud` 점 발행→자율 goal 우회/거부 확인. SSOT `ANALYSIS.md §B`.

### 2026-06-27 (야간, 이어서) — 수동 teleop 금지구역 경고(운영자 인지)

**요청**: 수동 teleop 시 금지구역 통과하면 경고 정도 기능. 조작인원 인지가 중요.
**구현(대시보드 프런트엔드 전용 → RPi4B 부하 0)**: `index.html` 에 차량 위치 vs 금지구역
폴리곤 내부 판정(`checkKeepoutWanings`/`_pointInPolygon`), 진입 시 지도 위 빨간 배너 +
토스트(high) + 비프음(알림음 켜짐 시), 3s 간격 재경고, 이탈 시 자동 해제. `onPoses`(~5Hz)에서 호출.
좌표계: 구역·포즈 모두 map 표시 좌표라 일관. 검증: JS BALANCED·`<button>`65/65·`<div>`133/133.
**한계**: 경고만(모션 미차단). 완전 차단은 차량측 cmd_vel 게이트 노드 별도 필요.

### 2026-06-27 (야간, 이어서) — aip3 오판 정정 + 내일 검증 핸드오프 작성

- **aip3 구동계 "미구현" 오판 정정**: 실제 동작함(수동 구동 테스트 완료). 근거 = vehicle 문서
  (콘센트 조건 단거리 이동·web MANUAL), 자체 스택 `industrial_sub_vehicle`(RPP 적용), `docker-robot-1`,
  ESP32+STS3215(사용자 확인). aip2/aip3는 docker 컨테이너 자체 스택이라 저장소·기록만으론 확인 어려움.
  → **문서 드리프트**(ARCHITECTURE·HANDOFF_REAL_WS·SETUP_*·TEAM_ONBOARDING의 "aip3 placeholder 미구현")
  잔존, 정리 대상(미수정, 사용자 지시 대기).
- **핸드오프**: 운용 PC가 달라 다른 세션 에이전트가 이어받음 → 무손실 전달 위해
  **`docs/agent_context/HANDOFF_2026-06-28_VEHICLE_TEST.md` 신규 작성**(세션 전 맥락+결정+정정사실+
  내일 전차량 검증절차+gotcha+체크리스트) + `HANDOFF.md` 상단 포인터 추가.
- **전달 필수**: 이 변경(17개)을 origin 에 **커밋·푸시**해야 다른 PC가 pull 가능. 브랜치 결정 후 진행.
  → `fc97ae6`(본작업) + `87c9588`(핸드오프해시) origin/main 푸시 완료.

### 2026-06-28 — 서보암 ROS→ESP32 연결(servo 모드) + 열상 퓨전 부하 논의

- **서보암(aip1 전용, MG996R×4)**: `arm_scan_node`가 `joint_N_cmd`(rad Float64)만 발행하고
  `serial_bridge`는 `servo_cmd`(UInt8 deg)만 구독 → 변환 어댑터 부재로 ROS에서 팔 미동작이던 갭 해소.
  - 사용자 결정: ESP32 PWM + **기존 servo_cmd 토픽 활용**(ros2_control 불필요).
  - `arm_scan_node`에 **'servo' controller_type 추가**: 자세 rad → MG996R deg(0~180) 변환 후
    `/{vid}/servo_cmd`(UInt8MultiArray) 발행 → serial_bridge → PKT_SERVO → ESP32.
  - `arm_config.yaml`: `controller_type: servo`(실차 기본) + 관절별 servo 캘리브레이션
    (neutral_deg/deg_per_rad/invert/clamp, 명목값 — 실차 보정 필요).
  - 검증: py_compile + 전 자세(stow/forward/left/right/up/low_forward) 0~180° 유효 변환 확인.
  - **잔여(실차)**: 서보혼 방향·기계영점 캘리브레이션, `arm_scan.launch.py vehicle_id:=aip1` 기동,
    실제 팔 동작 검증. URDF arm_joint_2/3 pivot 은 팀원 SolidWorks 대기(R-URDF, 별개).
- **열상 퓨전**: 팀원 담당 → **보류**(미수정). 논의 결론(참고): Pi 부하 주범은 열상(32×24, 49KB/s)이
  아니라 **RGB 캡처/압축**. 권장 = 열상 임계는 Pi 상시(경량)+RGB 이벤트 구동(WARN시만)+YOLO 중앙(기존).
- 진행률 실측: 서보암 로직/펌웨어/설정 완성, 이번에 연결 글루 추가 → SW 경로 완성(HW 검증만 남음).
  열상 퓨전 SW 체인(driver→patrol_monitor→central_fusion YOLOv8→viz) ~80%, 실HW·캘리브·검증 미완.

### 2026-06-28 (이어서) — 웹 관제 서보암 수동 제어 (구동모터처럼)

사용자 요청: 서보암도 구동모터처럼 웹에서 수동 제어. **대시보드가 `/aip1/servo_cmd` 직접 발행**
(serial_bridge 상시 가동 → 구동모터 cmd_vel 과 동일 성격, arm_scan_node 미가동에도 동작).
- 백엔드 `dashboard_server.py`: `_ARM_VEHICLE`(기본 aip1) + arm 퍼블리셔(servo_cmd/scan_request/estop)
  + `cmd_arm(action, degrees)` (servo=deg×4 0~180 클램프 직접 / scan=자동스캔 / stow) + WS `arm` 케이스.
- 프런트 `index.html` 제어탭: **서보암 패널** — 자세버튼 6(전방/좌/우/상방/저자세/접기) +
  4축 슬라이더(0~180°, onchange 발행) + 자동스캔/정지. `ARM_POSES`(arm_config 명목 캘리브 deg) UI 보유.
- 검증: dashboard py_compile, JS BALANCED, `<button>`73/73·`<div>`140/140. **실차 동작은 HW 캘리브 후 검증.**
- 경로: 웹 → WS{cmd:arm} → cmd_arm → /aip1/servo_cmd(UInt8×4) → serial_bridge → PKT_SERVO → ESP32 PWM.
- **UI 피드백 반영(재설계)**: ① 슬라이더 미표시 버그 = JS 동적 생성(`initArmSliders`) 의존 →
  **정적 HTML 슬라이더 4축으로 전환**(항상 렌더, 근본 해결). ② 자세 버튼 6개 → **CCTV PTZ 십자
  방향패드**(◀▶=팬/베이스, ▲▼=틸트/숄더 ±8°, ⌂=홈/전방) + 접기/자동스캔/스캔정지. 검증 재통과
  (JS BALANCED·`<button>`73/73·`<div>`142/142·슬라이더4 onchange 배선).

## 2026-06-28 (장시간 세션) — DDS cross-machine 단절 근본원인 규명 + SIMPLE 통일 복구

### 증상
대시보드에 차량(aip1) 라이다·위치 미표시, cross-machine DDS 데이터 도달 0. 매우 긴 진단(100+ 명령) 끝에 **근본원인 3건이 겹쳐 있음**을 규명. 겹침이 진단을 극도로 어렵게 만든 핵심.

### 근본원인 3건
1. **측정 도구 도메인 오염 — `~/.bashrc:121 export ROS_DOMAIN_ID=45`(시뮬용)**
   진단 CLI(제어 PC)가 시뮬 도메인 45로 떠서 도메인 42(실차) 토픽/데이터를 못 봄 → 진단 내내 "데이터 안 옴" **착시**. 사용자 `ros2 topic list` 에러(`!rclpy.ok()`)도 동일 원인. interactive 셸은 ~/.bashrc 적용(42)이지만 **non-interactive/스크립트(snapshot)는 profile 레벨 45 잔재** → 측정마다 결과가 달라짐. 조치: `~/.bashrc:121` 45→42.
2. **aip1 차량 내부 통신 차단 — client_profile(DS XML) + aip-local-ds disable**
   aip1을 단일 중앙 DS(client_profile) + 로컬 DS(11812) disable → 차량 노드들이 중앙 DS(11811)에만 의존, 그 연결이 안 되니 **차량 내부 discovery까지 깨짐**(차량 로컬 topic 0개). 조치: aip1 **순수 SIMPLE**(DS 설정 완전 제거) → 차량 로컬 topic 53개, scan/odom 발행 정상.
3. **DS/SIMPLE 모드 혼재 → cross-machine 차단**
   도메인42에 DS 서버(11811) + SIMPLE 노드 혼재 시 discovery 충돌. 듀얼 DS(aip1 로컬+중앙)는 cross-machine locator 오염. 단일 DS도 클라이언트 11811 연결 실패. 조치: **전체 SIMPLE 통일**(DS 서버 off).

### 해결 = 전체 SIMPLE 통일 + 도메인42
- **aip1**: `aip-fleet.service` override `UnsetEnvironment=ROS_DISCOVERY_SERVER FASTRTPS_DEFAULT_PROFILES_FILE`. `aip-local-ds` disable.
- **중앙**: `aip-central` override `UnsetEnvironment=...`(순수 SIMPLE). `fastdds-ds` = no-op(`ExecStart=/usr/bin/sleep infinity`, Requires 만족용). DS 서버 미기동(11811=0).
- `~/.bashrc` 도메인 45→42.
- **결과**: 대시보드에 aip1 scan(라이다)·odom·poses 도달 → **라이다 표시 성공(사용자 확인 2026-06-28)**.

### 부수 성과
- aip1 `serial_bridge` busy-poll 수정: `_rx_loop` non-blocking(timeout=0)+2ms `Event().wait` polling → blocking `ser.read(ser.in_waiting or 1)`(timeout=0.1). load 5.3→3.05, SSH 안정.
- aip2 자동실행 원인: 컨테이너 restart policy `unless-stopped` + docker.service enabled (`docker update --restart=no aip2_robot` 필요).

### 남은 작업
- **heartbeat 타입 미스매치**: 차량 `heartbeat_pub`(std_msgs/Bool) vs supervisor(`FleetHeartbeat`) → aip1 ping overlay만(online 카드 cpu/battery 0). 차량 발행을 FleetHeartbeat로 또는 UDP:19051 adapter 경로로.
- **aip2/aip3**: 순수 SIMPLE 통일 필요(컨테이너 `ROS_DISCOVERY_SERVER` 제거). aip2 restart policy=no.
- 임시 override(fastdds-ds no-op 등) 정식 SIMPLE 구성으로 정돈.

### 교훈 (다음 세션 필수)
- **DDS 진단 전 반드시 측정 셸 도메인 확인**: `echo $ROS_DOMAIN_ID`==42. ~/.bashrc/profile/snapshot에 시뮬 45 잔재 주의 — 이번 진단의 절반이 도메인45 측정 착시였음.
- **이 환경의 정답 DDS = SIMPLE 통일**(단일 서브넷, 멀티캐스트 양방향 도달 실측 검증됨). DS(Discovery Server)는 듀얼·단일 모두 실패했으니 쓰지 말 것. 차량 client_profile/ROS_DISCOVERY_SERVER 설정 제거 상태 유지.

## 2026-06-28 (이어서) — 잔여작업 ①online 카드 cpu telemetry 복구, ③override 정리(보류)

### ① online 카드 cpu/battery 0 → 실 telemetry 복구 (완료·검증)
- **근본구조 파악**: `/<ns>/heartbeat` 계약 타입은 `FleetHeartbeat`(SSOT `docs/FLEET_DASHBOARD_CONTRACT.md`)지만 **차량엔 `aip_fleet_msgs`가 없음**(aip1 src: aip_base/bringup/description/navigation2/slam/ydlidar뿐). 그래서 중앙 `udp_status_heartbeat_adapter`(UDP:19051)가 차량 UDP JSON→FleetHeartbeat 재발행하는 설계. 단 **FleetHeartbeat엔 cpu_load 필드가 없어** cpu는 어댑터 경로로 못 옴. cpu는 대시보드 **직접 UDP 오버레이**(`_on_udp_status`, `AIP_UDP_STATUS_PORT`)로만 표시 가능.
- **해결(설계정합·저위험)**: 차량에 **경량 UDP 리포터** 배포(순수 UDP+psutil, ROS 의존성·colcon 빌드 0). aip1 `~/aip_ws/scripts/aip_status_udp.py` + user service `aip-status-udp.service`(enable, 1Hz, →중앙 19052). 리포 버전관리: `deploy/vehicle/`(aip2/3 재사용).
- **중앙**: `aip-central` override(드롭인)에 `Environment=AIP_UDP_STATUS_PORT=19052` 추가 → 대시보드 직접 UDP 리스너 활성. (base 유닛 안 건드림.)
- **ping 경합 해결**: 대시보드 `_ping_status_loop`(line 1246)가 **같은 `_on_udp_status`/같은 키**에 1Hz로 `cpu=0, status=network_ping_only_no_ssh` 를 써서 실 telemetry를 덮는 last-writer-wins 경합 발견. 차량이 실 리포터를 가지면 ping은 중복·유해 → override에 `Environment=AIP_PING_STATUS_TARGETS=`(빈값)로 ping 오버레이 비활성. (코드레벨 우선순위 수정은 팀원 dashboard 작업과 조율 후.)
- **검증**: 재시작 후 `/proc/<pid>/environ`에 ROS_DISCOVERY_SERVER/FASTRTPS 없음(SIMPLE 유지 확인), domain42. 대시보드 `fleet_status` aip1 카드 = `state:MANUAL, cpu:35.7(실시간), status:ok, battery:0.0`(센서 없음, 정직), 안정(ping 플레이스홀더로 안 튐). scan·odom·poses 계속 정상.
- **잔여(후속)**: 실 estop/mode 표시 = ROS-aware 리포터 확장. 배터리 telemetry = 센서 추가 시. ping 경합 코드레벨 우선순위 수정(팀원 조율).

### ③ 임시 override(fastdds-ds no-op) 정식 정리 — 보류(문서화)
- `aip-central` base 유닛의 `Requires=fastdds-ds.service`는 **드롭인 빈 `Requires=` 리셋이 안 먹음**(daemon-reload 후에도 잔존, `.requires/` 심링크도 없음 — systemd 특성). 따라서 fastdds-ds를 disable/remove하면 다음 aip-central 재시작 때 Requires가 **실제 DS를 11811에 띄워 SIMPLE을 깨뜨림**. → **no-op `sleep infinity`는 load-bearing**. 제거하려면 base 유닛(`~/.config/systemd/user/aip-central.service`) 수술(Requires·ROS_DISCOVERY_SERVER 라인 제거)+재시작 필요 → 안정성 위해 **유지보수 창으로 보류**. 현 no-op 구성은 안정·동작.

### ② aip2/aip3 SIMPLE 통일 — 차량 전원 ON 필요(대기)
- 컨테이너 환경 수정(`ROS_DISCOVERY_SERVER` 제거) 작업이라 해당 차량 전원 ON+SSH 필요. 클린 재작업 시 `deploy/vehicle/` 리포터도 함께 배포.

## 2026-06-28 (이어서) — aip1 주행 모터 미동작 진단 + estop 재발 영구 해결

증상: aip1 주행 모터 동작 안 함, **서보암은 정상**.

### 진단 (토픽 추적, domain42/SIMPLE)
- `/aip1/estop`=true → twist_mux가 이걸 lock(`estop_lock`, topic=`estop`, prio90, timeout0)으로 구독 → **모든 cmd_vel 입력 masked** → 바퀴 0. 서보암은 `/aip1/servo_cmd`+별도 `/aip1/arm/estop` 경로라 twist_mux 게이트 미경유 → 정상. (serial_bridge는 cmd_vel·servo_cmd 둘 다 구독.)
- diagnostics 원문 확정: `lock locks.estop_lock: locked ... priority #90`, `current priority: 90`.
- 대시보드 "전체 정지 해제"(release_all)가 안 먹은 이유: `/aip1/estop=false`(Bool)+`/fleet/override` CMD_CLEAR 를 **일회성 VOLATILE**로 발행 → cross-machine/짧은 발행으로 twist_mux·supervisor에 미도달.

### 근본원인 = watchdog 의 offline estop 재단언 (heartbeat 갭의 실제 악영향)
- `watchdog_node._reassert_offline`(line102-104): `_offline` 차량에 **타이머마다 CMD_ESTOP 재발행**. `_on_status`는 복귀 시 `_send_clear`(CMD_CLEAR).
- aip1이 supervisor 인식 **FleetHeartbeat 미송신**(heartbeat_pub은 std_msgs/Bool, 19051 미송신) → 영구 offline → watchdog이 estop 계속 재단언 → 수동 해제해도 estop_lock free↔locked **깜빡임**, 주행 단속.

### 해결 (영구) = 리포터 → 어댑터(19051) FleetHeartbeat 공급
- `deploy/vehicle/aip_status_udp.py` 가 같은 페이로드를 대시보드(19052)+**어댑터(19051)** 양쪽 송신 → `udp_status_heartbeat_adapter`가 FleetHeartbeat 재발행 → supervisor online 인식 → watchdog 복귀감지 **CMD_CLEAR** → estop 해제 + **재단언 중단**.
- 검증: estop_lock 12초 **13/13 free**(깜빡임 소멸). 대시보드 카드 aip1 online/MANUAL/healthy/estop:false. 사용자 대시보드 수동주행 정상 확인.
- 커밋 `485b31f`.

### 트레이드오프·후속
- 카드가 FleetHeartbeat 경로로 전환되며 **cpu=0 회귀**(해당 경로 cpu 필드 없음, UDP 오버레이보다 우선). 복원 = `dashboard_server._merge_udp_status_overlay`가 FleetHeartbeat 카드에도 cpu 오버레이하도록 코드 수정(팀원 조율).
- **estop 해제 신뢰성 코드 결함**: 대시보드 release/CMD_CLEAR가 일회성 VOLATILE → reliable+latched(transient_local) 또는 supervisor 권위적 지속 재발행으로 고쳐야 재발 방지. twist_mux estop 구독은 BEST_EFFORT.
- (참고) ssh로 직접 estop disarm은 안전 가드 차단 → 사용자 명시 허가 후 진행했음.

### 후속 2건 코드레벨 해결 (커밋 93a4e00)
- **cpu 카드 복원**: `dashboard_server._merge_udp_status_overlay` 가 FleetHeartbeat 카드에도 UDP 오버레이 cpu(미지원 배터리 포함)를 병합(기존엔 목록에 없는 차량만 추가). aip2/3 등 모든 차량 공통 적용. 검증: aip1 카드 cpu 37.9 표시 + scan 정상.
- **estop 해제 신뢰성**: `supervisor_node._publish_status` 가 매 주기 `/<vid>/estop`·estop_lock 을 `_estop_locked` 기준으로 전 차량 **권위적 지속 재발행**(estop_lock은 원래 그랬음, estop도 동일하게). 일회성 VOLATILE 발행이 twist_mux(BEST_EFFORT)에 미도달하던 문제 제거 → 대시보드 ESTOP/해제가 신뢰성 있게 반영. 검증: `/aip1/estop` ~8Hz 발행, estop_lock free 유지. (override CMD_CLEAR는 dashboard↔supervisor 동일 프로세스라 본래 신뢰성 있음.)
- 빌드: `aip_fleet_dashboard`·`aip_fleet_supervisor` colcon 빌드(build/는 src 복사본 — symlink 아님) 후 aip-central 재시작. SIMPLE/domain42·scan 유지 확인.

## 2026-06-28 (이어서) — aip2/aip3 클린 재작업 + 텔레메트리(cpu/배터리) + online 안정화

### aip2/aip3 SIMPLE 통일 + cross-machine 데이터 복구
- aip2(TurtleBot, `aip2_robot` docker run): `start_robot_stack.sh` 에서 `unset ROS_DISCOVERY_SERVER` + wifi 프로파일 export. `restart=no`.
- aip3(자작차, `docker-robot-1` compose): `.env`/compose 에서 DS 제거, `config/fastdds_aip3_simple_wifi.xml`(SIMPLE+wifi) 적용, 컨테이너 recreate.
- **근본원인: docker0(172.17.0.1) DDS locator 충돌** — 중앙·docker차량이 동일 172.17 서브넷이라, host-network 컨테이너가 172.17.0.1 locator를 광고하면 중앙이 자기 docker0로 착각해 **cross-machine 데이터 전달 실패**(discovery는 멀티캐스트라 됨). aip1(네이티브, docker0 없음)만 무사했음. → 차량 FastDDS를 **wifi interfaceWhiteList(192.168.0.4/.5 + 127.0.0.1) UDP 전용**으로 제한해 해결.
- **중앙 wifi 전용 프로파일은 철회**: `useBuiltinTransports=false`로 SHM 제거 시 중앙 내부 heartbeat 불안정 유발. 차량 측 whitelist만으로 충분(중앙은 순수 SIMPLE 유지).

### 대시보드 scan override 버그 (DDS 아님)
- aip3 scan 미표시는 `dashboard_server._VEHICLE_SCAN_OVERRIDES['aip3']='/scan'`(옛 root ns 가정) 때문 → `/aip3/scan`으로 수정(커밋 e52a6ad). 전 차량 `/<ns>/scan` 통일.

### 배터리 게이지 (커밋 6c0dee3)
- aip2(TurtleBot `turtlebot3_node` `/battery_state`) BatteryState 구독 → 실 배터리%. 배터리 모듈 없는 차량(aip1/aip3)은 `battery=null` → 프런트 "N/A"(0%와 구별). `_VEHICLE_BATTERY_TOPIC` 맵 + `_cb_battery` + `_battery_for()`. 검증: aip2 28.3%, aip1/aip3 N/A.

### CPU 리포터 + online 안정화 (★ 다중 문제 동시 해결)
- aip2/aip3 호스트에 경량 UDP 리포터 배포(`deploy/vehicle/`, AIP_STATUS_HZ=2.0, →19052 cpu + **19051 어댑터**). SSH가 wifi 혼잡으로 자주 끊겨 **atomic 단일-ssh(base64) 재시도 배포**로 성공.
- **한 번의 배포로 4건 동시 해결**: ① cpu 표시(aip2/aip3) ② (배터리 별개 완료) ③ **online 깜빡임 해소** — 리포터→19051→중앙(same-host) FleetHeartbeat 재발행이 cross-machine native heartbeat 혼잡을 우회 ④ **watchdog estop 자동 해소 → 수동제어 복구**(estop은 online flicker의 증상이었음).
- 검증: 3대 battery/cpu 정상(aip2 28.3%·39.2%, aip1 N/A·30%, aip3 N/A·25%), `/fleet/status` 3샘플 전원 online·offline 없음(깜빡임 소멸).

### 핵심 교훈 / 미해결
- **수동제어 미동작 = heartbeat 불안정의 증상**: offline flicker → watchdog CMD_ESTOP → twist_mux 차단. 리포터의 same-host heartbeat로 근본 완화됨.
- **SSH 느림 = wifi airtime 혼잡**(SIMPLE 멀티캐스트 플러딩 + 3대 데이터 스트림), CPU 무관. 완화책: 5GHz 전환(Pi4B CYW43455 5GHz 지원), 데이터 감축(scan/costmap throttle), DS 재도입(discovery 멀티캐스트 제거 — docker0 원인 규명됐으니 이제 가능). **사용자와 방향 논의 중, DS 미적용**.
- 리포터 영속성(linger) 차량별 확인 필요(enable-linger). 데이터 감축/5GHz/DS는 후속 결정.

## 2026-06-28 (이어서) — Discovery Server 재도입 (SIMPLE → DS)

근본원인 확정: SIMPLE 멀티캐스트 discovery가 **3대 풀스택(70+ participant)에서 wifi airtime 포화** → ① aip1 ydlidar participant 매칭 실패(중앙이 /aip1/scan 발행자 discovery 못함, odom은 됨) ② heartbeat 불안정 ③ SSH 마비. 제 잦은 중앙 재시작이 재발견을 강제해 약점 노출. (단순 대역폭 아니라 discovery 매칭 실패.)

### 해결 = DS 재도입 (중앙=DS 서버, 전원 SUPER_CLIENT)
- **중앙**: `fastdds-ds` no-op 해제 → 실 DS 서버(`fast-discovery-server -i 0 -l 192.168.0.10 -p 11811`). `aip-central` override UnsetEnvironment에서 ROS_DISCOVERY_SERVER 제거 → base의 `ROS_DISCOVERY_SERVER=192.168.0.10:11811` 적용(DS-client). FASTRTPS 미설정(기본 transport=SHM intra-host).
- **aip1**(native): override를 `FASTRTPS_DEFAULT_PROFILES_FILE=fastdds_client_profile.xml`(단일 중앙 DS SUPER_CLIENT)로 교체(듀얼DS aip1_profile 금지), ROS_DISCOVERY_SERVER는 base. aip-fleet 재시작 → **ydlidar 재announce로 /aip1/scan 매칭 회복(0→27)**.
- **aip2/aip3**(docker): wifi 전용 SUPER_CLIENT 프로파일(`fastdds_*_ds_wifi.xml`, interfaceWhiteList=차량IP+127.0.0.1, RemoteServer=192.168.0.10:11811) + ROS_DISCOVERY_SERVER 설정. aip3=compose .env, aip2=start_robot_stack.sh. 컨테이너 recreate.
- 템플릿 `deploy/vehicle/fastdds_ds_wifi.xml.template`.

### 함정(겪음)
- aip2 start_robot_stack.sh의 `if [ -n "$ROS_DISCOVERY_SERVER" ]; then unset FASTRTPS_DEFAULT_PROFILES_FILE; fi` — DS 켜자 wifi 프로파일을 도로 unset → docker0 재오염. unset을 `:`(no-op)로 교체(주석만 하면 then 블록 비어 **bash 문법오류**로 컨테이너 exit — 한 번 겪음).

### 결과 / 남은 것
- **검증**: aip1 scan 매칭 회복, 3대 online, SSH **응답함(6s)** ← 전엔 타임아웃(>25s). discovery 멀티캐스트 제거 효과 확인.
- **남은 = 데이터 대역폭**: scan/odom 윈도우당 부분 도달(BEST_EFFORT 스트림 2.4GHz 포화). DS는 discovery만 고침 → **5GHz 전환(ipTIME AX3000Q, 같은 서브넷+MAC DHCP 예약으로 IP 유지) + aip2 커스텀 스크립트(ros_topic_bridge 33%·scan_normalizer 16%) 최적화**가 다음.
- 네트워크 기록: memory `project_fleet_network`(공유기 AX3000Q).

## 2026-06-29 — 5GHz 밴드 전환 (혼합밴드 확정) + aip2 5GHz 근본원인 진단

DS는 discovery만 고침. 데이터 대역폭(scan/odom 스트림)의 2.4GHz airtime 포화 해소 위해 **5GHz 전환** 진행.

### 라우터/전환 방식
- ipTIME AX3000Q에 **별도 SSID `aip5GHz`**(ch36 고정, 80MHz, WPA2 AES, 비밀번호는 저장소에서 제거). 5GHz 160MHz는 KR에서 DFS 강제 + RPi4는 80MHz 한계라 **80MHz 권장**(사용자 적용). MAC 예약이 밴드무관 → IP 유지(.10/.3/.4/.5).
- 차량 전환: netplan `aip2.4GHz→aip5GHz` 치환 + `netplan apply`. **안전장치**: 백업 후 detached `setsid` watchdog로 **180초 자동 롤백**(ssh 끊겨도 생존) → 확인되면 watchdog kill. 차량엔 `iwgetid` 없음 → **`wpa_cli -i wlan0 status`**(ssid/freq/wpa_state)로 탐지. 스크립트 `$JOB/tmp/netplan_5g.sh`.

### 결과
- **중앙 PC**: 5GHz(wlp4s0, 1134Mbit, −33dBm, DS 11811 무중단). ✅
- **aip1**: 5GHz(ch36, −33dBm, 고정IP .3 유지). ✅ — 첫 시도 때 `iwgetid` 없어 오판→롤백, `wpa_cli` 탐지로 재시도 성공.
- **aip2**: **2.4GHz 확정** ⚠️ — 5GHz가 flap/DORMANT. **전력·거리·배터리 모두 배제**(USB-C 급전 테스트로 전력 배제, 공유기 근처라 거리 배제). **근본원인 = 펌웨어 CLM/regulatory**: brcmfmac은 self-managed인데 phy가 `country 99: DFS-UNSET`에 고정(KR 미적용)→5GHz no-IR(스캔 −28dBm은 되나 association 불가). **여분 Pi에 aip2 SD 이식해도 동일 재현 → 하드웨어 아님.** aip1과 펌웨어 동일(7.45.241, 2021-11-01)인데 aip1만 정상=CLM/regulatory 차이. wpa conf엔 `country=KR` 있으나 self-managed라 런타임 적용 안 됨. 기존 flap과 spare DORMANT는 같은 현상의 다른 포착 시점. **2.4는 −27dBm 0%손실 안정**(GPIO 급전에서도).
- **aip3**: 미전환(2.4 유지). 자작 차량이라 이미지 다를 수 있어 별도 판단.
- **혼합밴드 정상**: 2.4·5GHz 같은 서브넷 브리지 → 교차밴드 통신 검증(중앙5GHz↔차량2.4 ping 0%). DDS 무관.

### 의사결정
- **DDS 마무리는 보류**: 5GHz 전환 전, 단일 중앙 DS가 **aip2 Nav2 내부(intra-vehicle) discovery를 깨뜨림**(노드끼리 중앙 DS 왕복 hang, `ros2 node list`=0) 확인 → 권장은 **SIMPLE 복원**(5GHz airtime이면 멀티캐스트 감당 + 내부 discovery 로컬). 전환 후 진행 예정.
- **aip2 5GHz CLM 수정**은 방대해 보류 → **백그라운드 에이전트로 aip1↔aip2 CLM/regulatory 심층 비교 분석 의뢰**(읽기 전용).
- 차량 sudo 편집: netplan root 600 + 무비번 sudo 불가 → 사용자 비번 필요(평문 저장 금지).

## 2026-06-29 (이어서) — aip2 5GHz 근본원인 **정정**: CLM/HW 아님, **해시 PSK**였음

앞 섹션의 "CLM/regulatory" 및 그 뒤 "HW 결함" 추정은 **둘 다 틀렸음**. 끝까지 추적해 진짜 원인 확정.

**배제(증거)**:
- 백그라운드 에이전트 read-only 비교: clm_blob·regulatory.db·NVRAM·펌웨어(7.45.241)·커널·`iw reg get`(둘 다 phy `country 99`)·ch36 플래그 전부 **aip1과 바이트 동일** → regulatory/CLM/펌웨어 배제. ("country 99"는 self-managed brcmfmac 정상 기본값 — 작동하는 aip1도 99.)
- **aip1 SD를 aip2 본체에 꽂으니 5GHz 정상**(.3 COMPLETED −34dBm 0%손실) → **aip2 HW 정상 확정**, HW 가설 배제.
- netplan/wpasupplicant를 aip1과 동일 버전으로 업그레이드(0.107 / 2.10-…2.4)+클린 리부트해도 실패 → SW 버전 배제.
- AP 무선 접속제한(MAC) 등록 장치 없음 → AP 배제.

**진짜 원인 = netplan YAML의 해시 PSK**: aip2 `50-cloud-init.yaml`의 `password`가 평문이 아니라 **미리 해시된 PSK**(`d9af…`, **SSID `aip2.4GHz` 기준 계산값**). `sed`로 SSID만 aip5GHz로 바꾸니 → (a) **PSK는 SSID마다 다른데 aip2.4GHz용 해시를 aip5GHz에 사용=틀린 키**, (b) **해시본은 SAE 비호환**. 이중으로 association 실패(`ASSOC-REJECT status_code=16`+auth timeout). aip1은 평문 PSK라 SSID 변경 후 정상 연결됨(실제 값은 저장소에서 제거).

**수정(해결)**: netplan password를 **올바른 평문 PSK(값은 저장소에서 제거)** + SSID aip5GHz → **즉시 5GHz 결합**(.4 freq=5180 COMPLETED −31dBm). 영구화 = cloud-init 네트워크 재생성 비활성(`/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg` = `network: {config: disabled}`) → reboot 지속.

**잔여 = 데이터 대역폭(밴드 무관)**: 컨테이너(`aip2_robot`) 가동 시 5GHz도 **287ms 포화**(0%손실=TX 큐 지연, ssh 타임아웃). power_save는 이미 off → **DDS 데이터 트래픽이 업링크 포화**가 원인(사용자 지적). 컨테이너 정지 시 2~8ms. → DDS SIMPLE 복원 + `ros_topic_bridge` throttle + scan/costmap throttle 필요.

**교훈**: 증상(5GHz만 실패·status_code=16)에서 regulatory/HW로 점프 말 것. **생성된 `wpa-wlan0.conf`를 aip1과 직접 diff**했으면 즉시 보였음(psk 평문 vs 해시). netplan은 password를 해시로 저장 가능, **해시 PSK는 SSID 종속 + SAE 비호환**.

## 2026-06-29 (이어서) — 전 차량 5GHz 운영 검증 + **DDS DS 유지 확정**(SIMPLE 복원 불필요)

전 차량 5GHz 전환 후 운영 점검:
- **전 차량 online·저지연**: aip1 .3 / aip2 .4 / aip3 .5 모두 5GHz, ping 1.5~9ms. aip2 컨테이너 재시작 후 **Nav2(controller/planner/SLAM) 실제 가동**(CPU 36%씩 = hang 아님).
- **데이터 end-to-end 도달 확인**: aip2 wlan0 TX **2.5MB/s** ↔ 중앙 wlan0 RX **1.24MB/s** = 차량→중앙 데이터 흐름. 중앙 watchdog 로그가 aip2/aip3 online(recovered, ESTOP clear) 추적. (수동 `ros2 topic list`가 0개로 나온 건 SUPER_CLIENT 프로파일/transport 설정 문제일 뿐 — 실서비스는 정상.)
- **aip2 287ms는 일시적 settling**이었음 — 컨테이너 풀가동(2.5MB/s)에서도 **안정 7ms**(15/15 0%손실). 5GHz가 트래픽 흡수.
- **DDS = 단일 중앙 DS 유지 확정**: 2.4에서 깨졌던 aip2 Nav2 **내부(intra-vehicle) discovery**가 **5GHz에선 정상**(round-trip 빨라서). → **SIMPLE 복원 불필요. DS가 최종.**
- 전환 중 band 끊김으로 watchdog가 일시 ESTOP→recovered(설계대로). 현재 전 차량 ESTOP clear.

**잔여(선택·비긴급)**: aip2 TX 2.5MB/s는 단일 로봇치곤 높음(`ros_topic_bridge` 재발행 추정) → throttle하면 효율·헤드룸↑. 단 5GHz가 감당하므로 긴급 아님.

---

## 2026-06-28 — Vision Pi 직접 RGB/MLX 웹관제 연동 PR 준비

### 배경
메인 차량 CPU 부하를 피하기 위해 Vision Pi의 RGB/MLX 영상을 메인 차량 ROS2 경로로 통과시키지 않고 웹관제가 Pi 스트림 URL을 직접 표시하는 방식으로 정리했다. 접속 비밀번호/시크릿은 문서와 저장소에 남기지 않는다.

### 변경
- `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py`
  - `AIP_VISION_STREAM_URLS`, `AIP_THERMAL_STREAM_URLS` 환경변수 파서를 추가했다.
  - FastAPI startup 시 `vision_streams`, `thermal_streams` 상태를 WebSocket 캐시에 주입한다.
- `src/aip_fleet_dashboard/static/index.html`
  - RGB/thermal 카메라 슬롯이 직접 스트림 URL을 기존 ROS2 base64 프레임보다 우선 표시한다.
  - `?vision_<vehicle_id>=...`, `?thermal_<vehicle_id>=...`, `?no_ws=1` 정적 테스트 모드를 추가했다.
- `scripts/dev_mjpeg_stream.py`
  - PC에서 대시보드 임베드 동작을 확인하는 의존성 없는 테스트 스트림 서버를 추가했다.

### Vision Pi 검증
- Pi 서비스: `aip-vision-preview.service` enabled/active.
- RGB: `http://192.168.0.108:8081/rgb.mjpg`, `400x300`, 2 fps, raw Bayer stream mode.
- MLX thermal: `http://192.168.0.108:8081/thermal.mjpg`, `240x180`, 약 3.8-4 fps.
- `oneshot` 저부하 RGB 모드는 화면 깨짐이 있어 보류하고, RGB만 이전 안정 경로인 stream mode로 복구했다.
- PC 웹관제 정적 테스트에서 RGB/thermal 직접 스트림이 모두 렌더링됨을 확인했다.

### PR 메모
- 이 PR은 중앙 대시보드와 테스트 도구만 변경한다.
- 메인 차량 SW, firmware, docker secret 파일은 수정하지 않았다.
- 운영 환경 변수 예:
  - `AIP_VISION_STREAM_URLS=aip2=http://192.168.0.108:8081/rgb.mjpg`
  - `AIP_THERMAL_STREAM_URLS=aip2=http://192.168.0.108:8081/thermal.mjpg`

---

## 2026-06-28 — Direct Vision Pi stream 위 bbox overlay 추가

### 배경
사용자가 바운딩 박스 같은 인식 기능을 넣으면 Pi CPU 부하가 커지는지 확인했다. 결정은 Pi가 영상 스트리밍만 담당하고, 인식/YOLO는 중앙 PC에서 돌린 뒤 `/fleet/alerts`의 bbox 결과만 웹관제 화면에 얹는 방식이다.

### 변경
- `src/aip_fleet_dashboard/static/index.html`
  - RGB 카메라 슬롯 위에 `.vision-overlay` 레이어를 추가했다.
  - WebSocket `alert` 메시지의 `bbox` 값을 선택 차량 RGB 이미지 위에 표시한다.
  - 이미지 `object-fit: contain` 영역에 맞춰 bbox 픽셀 좌표를 스케일링한다.
  - 로컬 리뷰 테스트용 `?bbox_<vehicle_id>=x,y,w,h` 쿼리를 추가했다.

### 검증
- `python -m py_compile src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py scripts/dev_mjpeg_stream.py` 통과.
- `index.html` 내부 `<script>`를 Node `new Function(...)`으로 파싱해 문법 오류 없음 확인.
- 로컬 테스트:
  - 대시보드 `127.0.0.1:8092`, 더미 MJPEG `127.0.0.1:8093`.
  - URL에 `bbox_aip2=80,60,180,120`을 넣어 `#vision-a-overlay .vision-bbox` 1개 생성 확인.
  - RGB/thermal 모두 `480x270`으로 렌더링, 브라우저 console error/waning 없음.

### 통합 메모
- Pi에는 bbox 그리기/YOLO 연산을 추가하지 않았다.
- 실제 통합 때 중앙 인식 노드가 사용하는 RGB 해상도와 웹에 표시하는 direct stream 해상도가 다르면 bbox 위치 스케일 보정 기준을 맞춰야 한다.

---

## 2026-06-28 — Vision Pi를 차량형 ROS2 실험 환경으로 확장 준비

### 배경
사용자가 `vision@vision` Pi에서 메인 1번 차량과 같은 환경으로 실험하면서, 카메라/열화상 표시 이후 기능적인 부분을 추가하고 싶다고 요청했다. 원칙은 메인 차량 SW를 건드리지 않고 Vision Pi를 별도 실험 노드로 붙이는 것이다.

### 확인
- Vision Pi는 Ubuntu 22.04.5, `aip-vision-preview.service` active.
- RGB/thermal HTTP endpoint는 정상:
  - `/rgb.jpg`: `400x300`, JPEG.
  - `/thermal.jpg`: `240x180`, JPEG.
  - `/status.json`: camera/thermal/monitor 상태 제공.
- Vision Pi에는 현재 `ros2`, `rclpy`, `sensor_msgs`, `std_msgs`가 설치되어 있지 않다.

### 변경
- `src/aip_fleet_perception/aip_fleet_perception/vision_pi_bridge_node.py` 추가.
  - Vision Pi HTTP `/rgb.jpg`를 `/<vehicle_id>/image_raw/compressed`로 발행.
  - Vision Pi HTTP `/thermal.jpg`를 `/<vehicle_id>/thermal_viz`로 발행.
  - Vision Pi `/status.json`을 `/<vehicle_id>/heartbeat`로 발행.
  - thermal max temp가 임계값을 넘으면 `/fleet/alerts` WARN을 발행.
- `vision_pi_bridge.launch.py` 추가.
- `setup.py` console entrypoint 등록.
- `central_fusion_node.py`, `perception_central.launch.py` 기본 vehicle_ids를 `peer_*`에서 `aip1/aip2/aip3`로 갱신.

### 검증
- `python -m py_compile` 통과:
  - `vision_pi_bridge_node.py`
  - `central_fusion_node.py`
  - `vision_pi_bridge.launch.py`
  - `perception_central.launch.py`
- PC에서 Vision Pi HTTP 확인:
  - `/status.json` OK.
  - `/rgb.jpg` JPEG magic `FF D8 FF`, `400x300`.
  - `/thermal.jpg` JPEG magic `FF D8 FF`, `240x180`.

### 다음
- Pi에서 직접 실행하려면 ROS2 Humble runtime/rclpy와 이 저장소의 `aip_fleet_msgs`, `aip_fleet_perception` 빌드가 필요하다.
- 설치 전 빠른 검증은 중앙 PC에서 `vision_pi_bridge_node`를 실행해 Pi HTTP를 ROS2 토픽으로 변환하는 방식이 안전하다.

---

## 2026-06-28 — Vision Pi RGB 6 fps 부하 실측

### 배경
사용자가 10 fps 가능성을 검토한 뒤, 우선 6 fps로 올려 실제 Pi CPU 상태를 분석해 달라고 요청했다.

### 변경
- Vision Pi `/etc/systemd/system/aip-vision-preview.service`를 백업한 뒤 RGB `--fps 2` → `--fps 6`으로 변경했다.
- RGB 해상도/품질은 유지:
  - `400x300`, JPEG quality `65`, raw Bayer stream mode.
- MLX thermal 설정은 유지:
  - `240x180`, JPEG quality `55`.

### 검증
- 웹관제 최신 테스트 URL에서 RGB `400x300`, thermal `240x180` 정상 로드.
- 브라우저 console error/waning 없음.
- 15초 CPU 샘플:
  - 실제 RGB frame delta: `85 / 15s` → 약 `5.67 fps`.
  - thermal frame delta: `59 / 15s` → 약 `3.93 fps`.
  - preview process: Pi 전체 4코어 기준 평균 `20.0%` (`19.2~20.7%`).
  - preview process: 한 코어 기준 평균 `79.9%` (`77.0~82.7%`).
  - Pi 전체 busy 평균 `24.2%` (`22.9~26.7%`).
  - RSS 약 `130~137 MB`.
  - HTTP 8081 socket rows: `4`.
- 추가 상태:
  - 온도 `49.1°C`.
  - throttled `0x0`.

### 판단
- 6 fps는 짧은 테스트 기준으로 안정권이다.
- 2 fps 대비 preview process는 Pi 전체 기준 약 `13~14%` → `20%`로 증가했다.
- 10 fps는 여전히 MJPEG/JPEG 인코딩 때문에 한 코어 포화에 가까워질 수 있으므로, 장시간 운용 전 6 fps 온도/지연/SSH 반응성을 먼저 관찰한다.

---

## 2026-06-28 — Vision Pi RGB 10 fps 부하 실측

### 배경
사용자가 10 fps로 올려 테스트하고 상황을 분석해 달라고 요청했다. ROS2는 실행하지 않고 기존 Vision Pi HTTP preview 서비스의 RGB FPS만 변경했다.

### 변경
- Vision Pi `/etc/systemd/system/aip-vision-preview.service`를 백업한 뒤 RGB `--fps 6` → `--fps 10`으로 변경했다.
- RGB 해상도/품질은 유지:
  - `400x300`, JPEG quality `65`, raw Bayer stream mode.
- MLX thermal 설정은 유지:
  - `240x180`, JPEG quality `55`.

### 검증
- 웹관제 테스트 URL에서 RGB `400x300`, thermal `240x180` 정상 로드.
- 브라우저 console error/waning 없음.
- 15초 CPU 샘플:
  - 실제 RGB frame delta: `118 / 15s` → 약 `7.87 fps`.
  - thermal frame delta: `59 / 15s` → 약 `3.93 fps`.
  - preview process: Pi 전체 4코어 기준 평균 `23.8%` (`23.0~24.5%`).
  - preview process: 한 코어 기준 평균 `95.1%` (`92.2~97.9%`).
  - Pi 전체 busy 평균 `28.4%` (`27.4~30.1%`).
  - RSS 약 `130~138 MB`.
  - HTTP 8081 socket rows: `6`.
- 추가 상태:
  - 온도 `55.0°C`.
  - throttled `0x0`.

### 판단
- 10 fps 설정이어도 실제 RGB는 약 `7.9 fps`로, 현재 MJPEG/raw Bayer stream 경로의 처리 한계가 보인다.
- Pi 전체 기준으로는 아직 여유가 있지만, preview process가 한 코어를 거의 포화시키므로 장시간 운용에서는 온도·지연·SSH 반응성을 더 봐야 한다.
- 운영 안정성이 우선이면 6 fps가 더 균형이 좋고, 10 fps급 부드러움이 필요하면 MJPEG 대신 H.264/WebRTC/RTSP gateway를 검토한다.

---

## 2026-06-28 — Vision Pi thermal 10 fps 시도 및 한계 확인

### 배경
사용자가 RGB뿐 아니라 MLX thermal 실제 프레임도 10 fps까지 올려 달라고 요청했다. 목표는 Pi CPU 부하를 크게 늘리지 않으면서 웹관제에서 RGB/thermal이 모두 부드럽게 보이도록 하는 것이다.

### 변경/시험
- Vision Pi의 `aip_vision/thermal_uart.py`에서 UART read timeout을 `0.2s`에서 `0.03s`로 낮추고 read chunk를 `4096`에서 `512`로 줄여 수신 루프 지연을 줄였다.
- 기존 `115200` baud에서 thermal frame rate를 재측정했다.
- host 쪽 service baud만 `230400`으로 올려 수신 가능 여부를 시험한 뒤, 프레임 수신 실패를 확인하고 즉시 `115200`으로 복구했다.

### 결과
- thermal 실측은 계속 약 `4.00 fps`였다.
- RGB는 10 fps 설정에서 약 `7.87 fps` 수준이었다.
- thermal payload는 frame당 약 `1537 bytes`로 확인됐다.
- `230400` baud host-only 변경은 `frames=0`, UART data 대기 상태로 실패했다.

### 판단
- 현재 병목은 웹관제나 Pi의 JPEG 표시 코드가 아니라 MLX UART 송신 보드/펌웨어 출력률로 보인다.
- 현 상태에서 thermal 실제 10 fps를 만들려면 송신 보드가 10Hz로 프레임을 내보내도록 firmware/baud를 변경하거나, UART를 우회해 MLX를 Pi에서 직접 I2C로 읽는 경로가 필요하다.
- 현재 운영 상태는 RGB 10 fps 설정, thermal 115200 UART 약 4 fps, `aip-vision-preview.service` active이다.

---

## 2026-06-28 — Vision Pi RGB 20 fps 설정 테스트

### 배경
사용자가 fps를 20으로 올려 테스트해 달라고 요청했다. thermal은 UART 송신 보드 출력률 한계가 확인된 상태라, 이번 테스트는 RGB preview service의 `--fps` 값을 20으로 올리는 방식으로 진행했다.

### 변경
- Vision Pi `/etc/systemd/system/aip-vision-preview.service`를 백업한 뒤 RGB `--fps 10` → `--fps 20`으로 변경했다.
- RGB 해상도/품질은 유지:
  - `400x300`, JPEG quality `65`, raw Bayer stream mode.
- MLX thermal 설정은 유지:
  - `240x180`, JPEG quality `55`, UART `115200`.

### 검증
- PC에서 `rgb.mjpg`와 `thermal.mjpg`를 동시에 읽으며 20초 샘플을 측정했다.
- service 상태: `active`, camera/thermal `last_error=None`.
- 20초 CPU 샘플:
  - 실제 RGB frame delta: `157 / 20.2s` → 약 `7.77 fps`.
  - thermal frame delta: `80 / 20.2s` → 약 `3.96 fps`.
  - preview process: Pi 전체 4코어 기준 평균 `23.7%`.
  - preview process: 한 코어 기준 평균 `94.7%`.
  - Pi 전체 busy 평균 `29.3%`.
  - RSS 약 `130 MB`.
  - 온도 약 `51.6°C`.
  - throttled `0x0`.

### 판단
- `--fps 20` 설정은 적용됐지만 실제 RGB frame rate는 10 fps 설정 때와 거의 같거나 낮다.
- 현재 병목은 FPS 파라미터가 아니라 raw Bayer stream 캡처/디베이어/JPEG preview 경로의 한 코어 포화로 보인다.
- 운영 안정성이 우선이면 6 fps 또는 10 fps로 되돌리는 것이 낫고, 10 fps 이상이 필요하면 MJPEG가 아닌 H.264/WebRTC/RTSP 또는 ISP/드라이버 경로를 검토한다.
- 현재 운영 상태는 RGB `--fps 20`, thermal 115200 UART 약 4 fps, `aip-vision-preview.service` active이다.

---

## 2026-06-28 — Vision Pi RGB 6 fps live test 상태로 전환

### 배경
사용자가 직접 화면 안정성을 확인할 수 있도록 fps를 6으로 낮춰 계속 켜 달라고 요청했다.

### 변경
- Vision Pi `/etc/systemd/system/aip-vision-preview.service`를 백업한 뒤 RGB `--fps 20` → `--fps 6`으로 변경했다.
- 서비스는 재시작 후 `active` 상태로 유지했다.
- 로컬 대시보드 정적 서버를 `127.0.0.1:8092`에 실행하고, 브라우저를 Pi 직접 스트림 테스트 URL로 열었다.

### 검증
- 브라우저 이미지 로드:
  - RGB `http://192.168.0.108:8081/rgb.mjpg`, natural size `400x300`.
  - thermal `http://192.168.0.108:8081/thermal.mjpg`, natural size `240x180`.
- 15초 CPU 샘플:
  - 실제 RGB frame delta: `85 / 15.02s` → 약 `5.66 fps`.
  - thermal frame delta: `59 / 15.02s` → 약 `3.93 fps`.
  - preview process: Pi 전체 4코어 기준 평균 `19.9%`.
  - preview process: 한 코어 기준 평균 `79.6%`.
  - Pi 전체 busy 평균 `25.7%`.
  - 온도 약 `50.1°C`.
  - throttled `0x0`.

### 판단
- 6 fps는 현재 MJPEG 경로에서 10/20 fps 설정보다 여유가 있고, 테스트 중 끊김·오류 없이 유지됐다.
- 현재 운영 상태는 RGB `--fps 6`, thermal 115200 UART 약 4 fps, `aip-vision-preview.service` active이다.

---

## 2026-06-28 — Vision Pi RGB 10 fps급 추천 설정 테스트

### 배경
사용자가 추천 방식으로 진행해 달라고 요청했고, 한 코어만 쓰지 말고 다른 코어를 쓰면 되는 것 아닌지 질문했다. 확인 결과 기존 raw Bayer stream 코드에는 `min(self.fps, 8.0)` 안전 상한이 있어 10/20 fps 설정이 실제 약 7.8 fps에서 막혔다.

### 변경
- Vision Pi 로컬 코드(`/home/vision/aip_vision_ws/aip_vision`)에 raw Bayer 처리 상한 옵션을 추가했다.
  - `CameraReader(..., raw_max_fps=8.0)` 추가.
  - `--rgb-raw-max-fps` CLI 인자 추가.
  - 기존 기본값은 8 fps로 유지해 급격한 동작 변화는 피했다.
- 테스트 설정:
  - `--fps 10 --rgb-raw-max-fps 12`, RGB `400x300`, JPEG quality `65`.
  - `--fps 10 --rgb-raw-max-fps 12`, RGB `320x240`, JPEG quality `65`.
  - `--fps 12 --rgb-raw-max-fps 14`, RGB `320x240`, JPEG quality `65`.

### 검증
- `400x300`, `--fps 10`, raw cap 12:
  - RGB 약 `8.93 fps`.
  - thermal 약 `3.90 fps`.
  - preview process 한 코어 기준 약 `100.9%`, Pi 전체 약 `30.0%`, throttled `0x0`.
- `320x240`, `--fps 10`, raw cap 12:
  - RGB 약 `8.99 fps`.
  - preview process 한 코어 기준 약 `93.4%`, Pi 전체 약 `28.7%`, throttled `0x0`.
- `320x240`, `--fps 12`, raw cap 14:
  - RGB 약 `10.46 fps`.
  - thermal 약 `3.93 fps`.
  - preview process 한 코어 기준 약 `102.4%`, Pi 전체 약 `30.9%`, 온도 약 `52.6°C`, throttled `0x0`.
- 브라우저 직접 스트림 로드:
  - RGB natural size `320x240`.
  - thermal natural size `240x180`.

### 판단
- 기존 `7.87 fps`는 하드웨어 절대 최대가 아니라 코드의 raw stream 안전 상한과 직렬 처리 병목이 만든 실측 상한이었다.
- OpenCV는 4 threads 설정이지만, 현재 파이프라인은 프레임 단위로 `capture -> normalize/debayer -> resize -> JPEG`가 이어지는 직렬 구조라 자동으로 4코어 전체를 효율적으로 쓰지 못한다.
- 멀티프로세스 워커로 변환/JPEG를 나눌 수는 있지만 raw frame 복사, 큐 지연, 프레임 순서/드롭 관리가 생겨 즉시 운영용으로 넣기에는 리스크가 더 크다.
- 단기 추천은 현재 적용한 `320x240`, `--fps 12`, `--rgb-raw-max-fps 14` 설정이다. 실제 10 fps급이 가능하고, 현재 짧은 테스트에서 에러/스로틀링은 없었다.
- 장기 추천은 MJPEG Python 변환 경로가 아니라 H.264/WebRTC/RTSP 또는 ISP/드라이버 경로로 이동하는 것이다.
- 현재 운영 상태는 RGB `320x240`, `--fps 12`, `--rgb-raw-max-fps 14`, thermal 115200 UART 약 4 fps, `aip-vision-preview.service` active이다.

---

## 2026-06-28 — Vision Pi 영상 지연 대응: JPEG polling 모드 추가

### 배경
사용자가 현재 화면 딜레이가 너무 심하다고 보고했다. MJPEG 장기 연결은 브라우저나 Python HTTP server 쪽에서 오래된 프레임이 쌓일 수 있으므로, 지연 누적을 줄이는 대안이 필요했다.

### 변경
- 대시보드 직접 영상 URL에 JPEG polling 모드를 추가했다.
  - 공통: `poll_ms=<ms>`
  - RGB 전용: `rgb_poll_ms=<ms>`
  - thermal 전용: `thermal_poll_ms=<ms>`
- polling은 `setInterval`이 아니라 이미지 로드가 끝난 뒤 다음 요청을 예약하는 sequential 방식으로 구현했다.
  - Pi 응답보다 빠르게 `src`를 갈아끼워 첫 프레임을 계속 취소하는 문제를 피한다.
- RGB overlay의 `onload` 처리와 polling 스케줄이 서로 덮어쓰지 않도록 조정했다.
- 테스트 URL 예:
  - `?no_ws=1&rgb_poll_ms=80&thermal_poll_ms=800&vision_aip2=http://192.168.0.108:8081/rgb.jpg&thermal_aip2=http://192.168.0.108:8081/thermal.jpg`

### Pi 측 시도
- raw Bayer stdout drain 방식의 최신 프레임 유지 패치를 시험했다.
- 결과적으로 RGB 캡처가 약 `6 fps`대로 떨어지고 MJPEG 송출도 불안정해져 운영 후보에서 제외했다.
- Pi camera code는 기존 안정 raw stream 방식으로 되돌렸다.
- Pi web preview에는 `TCP_NODELAY`, `Cache-Control: no-store`, `X-Accel-Buffering: no`만 남겼다.
- 서비스는 RGB `320x240`, `--fps 10`, `--rgb-raw-max-fps 12` 균형 설정으로 재시작했다.

### 검증
- 대시보드 JS 문법 검증 통과.
- 로컬 더미 snapshot 서버로 polling 반복 갱신 확인:
  - RGB/thermal image `src`가 시간 파라미터로 반복 갱신됨.
  - natural size가 정상으로 잡힘.
- Pi 실측 중간 결과:
  - RGB 약 `8.89 fps`.
  - thermal 약 `3.89 fps`.
  - preview process 한 코어 기준 약 `92.2%`.
  - Pi 전체 busy 약 `27.8%`.
  - throttled `0x0`.

### 현재 블로커
- 이후 Vision Pi `192.168.0.108`이 ping, SSH `22`, HTTP `8081` 모두 timeout 상태가 됐다.
- 로컬 브라우저 요청과 더미 서버는 중지했다.
- 다음 진행은 Pi 전원/네트워크 확인 또는 재부팅 후 가능하다.

---

## 2026-06-28 — Vision Pi 저부하·저지연 최종 임시 운용값 선정

### 배경
사용자가 부드럽게 나오면서 CPU를 많이 쓰지 않고 웹관제에서 볼 수 있는 추천 방식으로 계속 진행해 달라고 요청했다. Pi가 다시 네트워크에 올라온 뒤 H.264/WebRTC 방향과 더 가벼운 MJPEG 대안을 비교했다.

### 확인
- Pi에는 `/dev/video11` H.264 encoder device가 보이나 `ffmpeg`, `gstreamer`, `libcamera/rpicam`은 기본 설치되어 있지 않았다.
- `ustreamer`를 설치해 RGB를 Python 밖으로 빼는 방식을 테스트했다.
  - `MMAP`에서는 capture start가 `Invalid argument`로 실패.
  - `USERPTR`은 `/dev/video0`가 지원하지 않아 실패.
  - 결과가 `NO SIGNAL` placeholder라 운영 후보에서 제외했다.
- `v4l2-ctl` 직접 stream 테스트는 여러 포맷에서 OK였으나, uStreamer와의 조합은 맞지 않았다.

### 변경
- uStreamer 테스트 프로세스는 종료했다.
- `aip-vision-preview.service`를 안정 균형값으로 재설정했다.
  - RGB `320x240`.
  - `--fps 8`.
  - `--rgb-raw-max-fps 8`.
  - JPEG quality `65`.
  - thermal `240x180`, UART `115200` 유지.
- 웹관제 브라우저는 기본 MJPEG direct URL로 열었다.

### 검증
- 단일 HTTP 응답시간:
  - `/rgb.jpg`: 대부분 `0.008~0.047s`.
  - `/thermal.jpg`: 대부분 `0.008~0.018s`.
  - `/status.json`: 대부분 `0.011~0.026s`.
- 브라우저 MJPEG 직접 연결 상태 15초 샘플:
  - RGB 약 `7.86 fps`.
  - thermal 약 `3.93 fps`.
  - preview process 한 코어 기준 약 `85.7%`.
  - Pi 전체 busy 약 `26.2%`.
  - 온도 약 `49.2°C`.
  - throttled `0x0`.
  - socket state: `ESTAB=2`, `TIME-WAIT=67`.
- 브라우저에서 RGB natural size `320x240`, thermal natural size `240x180` 확인.

### 판단
- 현재 장비에서 가장 안전한 단기 추천은 `320x240`, `8fps`, MJPEG direct다.
- `12fps/raw cap 14`는 실제 10fps급이 가능하지만 한 코어가 100% 안팎이라 지연과 불안정성이 커질 수 있다.
- JPEG polling은 지연 누적 fallback으로 유지하되, 너무 빠른 polling은 TIME_WAIT를 많이 만들 수 있으므로 운영 기본값으로 두지 않는다.
- 장기적으로 진짜 저부하/고프레임이 필요하면 `ffmpeg/gstreamer + H.264 V4L2 M2M + WebRTC/RTSP gateway`를 별도 작업으로 검증한다.

---

## 2026-06-28 — 웹관제 카메라 지연 완화 패치

### 배경
사용자가 웹관제 카메라 화면의 렉/딜레이가 심하다고 보고했다. 기존 MJPEG direct와 과도한 JPEG polling 모두 지연 체감이 생길 수 있어, 현재 Pi 부하와 브라우저 렌더 상태를 다시 점검했다.

### 확인
- Pi preview service는 정상 동작 중이다.
  - RGB 캡처 약 `7.8 fps`.
  - thermal 약 `4.0 fps`.
  - RGB frame age 약 `0.11s`, thermal age 약 `0.05s`.
  - Pi 전체 CPU busy 약 `27%`, 온도 약 `54.0°C`, throttled `0x0`.
- `rgb_poll_ms=125`, `thermal_poll_ms=250`은 너무 공격적이라 `/rgb.jpg` 응답이 순간적으로 `0.4~1.5s`까지 밀렸다.
- `rgb_poll_ms=300`, `thermal_poll_ms=1000`에서는 `/rgb.jpg`, `/thermal.jpg` 응답이 대부분 `10~20ms`대로 안정화됐다.

### 변경
- 대시보드 JPEG polling 표시 로직을 개선했다.
  - 기존: 보이는 `<img>`의 `src`를 직접 교체.
  - 변경: 백그라운드 `Image()`가 새 JPEG를 완전히 로드한 뒤 보이는 `<img>`의 `src`를 교체.
  - poll timer는 `clearTimeout`으로 정리하고, token으로 이전 polling 콜백이 뒤늦게 화면을 덮어쓰지 않게 했다.
- 현재 테스트 브라우저 URL은 저지연 안정값으로 전환했다.
  - `rgb_poll_ms=300`
  - `thermal_poll_ms=1000`
  - `vision_aip2=http://192.168.0.108:8081/rgb.jpg`
  - `thermal_aip2=http://192.168.0.108:8081/thermal.jpg`

### 검증
- 브라우저에서 RGB `320x240`, thermal `240x180` 정상 표시 확인.
- 이미지 `complete=true` 상태 유지 확인.
- 5초 샘플에서 RGB/thermal URL timestamp가 계속 갱신됨을 확인.
- HTML 내 JavaScript를 UTF-8로 추출해 `node --check` 통과.

### 판단
- 지금 체감 지연을 줄이는 단기값은 JPEG polling `RGB 300ms`, `thermal 1000ms`다.
- thermal은 실제 센서 입력이 약 4fps이므로 1초 갱신도 관제 확인에는 충분하고, 연결/CPU 부담을 크게 줄인다.
- 더 부드러운 RGB가 필요하면 `rgb_poll_ms=200`까지는 시험 가능하지만, 125ms 이하로 내리면 Pi HTTP 연결과 브라우저가 다시 밀릴 수 있다.

---

## 2026-06-28 — Vision Pi 설정 변수 분리 및 팀원 조정용 런북 추가

### 배경
사용자가 현재 CPU 부하를 확인하고, 실차 투입 시 팀원이 직접 세팅 변수를 바꿀 수 있게 해달라고 요청했다. 또한 RGB 카메라와 thermal이 묶여 있는지, 따로 바꿀 수 있는지 확인했다.

### 확인
- Vision Pi 서비스는 하나의 `aip-vision-preview.service`에서 RGB와 thermal을 함께 띄운다.
- 웹관제 연결 URL과 표시 주기는 RGB/thermal을 따로 조정할 수 있다.
- Pi 내부 옵션도 RGB와 thermal이 대부분 분리되어 있다. 단, 서비스 프로세스는 하나이며 `--fps`는 MJPEG 송출 루프에도 공통 영향을 준다.
- 현재 실측:
  - RGB 약 `7.8 fps`.
  - thermal 약 `3.9 fps`.
  - RGB age 약 `0.10s`, thermal age 약 `0.18s`.
  - Pi 전체 CPU busy 약 `28%`.
  - Python preview 프로세스 한 코어 기준 약 `84%`, `v4l2-ctl` 약 `19%`.
  - 온도 약 `52.5°C`, throttled `0x0`.

### 변경
- 중앙 대시보드 서버 환경변수를 추가했다.
  - `AIP_VISION_POLL_MS`
  - `AIP_RGB_POLL_MS`
  - `AIP_THERMAL_POLL_MS`
- 대시보드 WebSocket seed에 `vision_config`를 추가했다.
- 프론트엔드는 `vision_config`를 받아 polling 값을 적용한다.
  - URL query가 있으면 query가 우선한다.
  - `0`이면 polling 비활성, 양수면 안전 범위로 clamp한다.
- `docker/central/.env.example`과 `docker/central/docker-compose.yml`에 Vision Pi direct stream/poll 변수를 추가했다.
- 팀원용 런북 `docs/VISION_PI_DIRECT_STREAM_KO.md`를 추가했다.
- `pending_tasks.md`의 추천 fallback 값을 `RGB 300ms`, `thermal 1000ms`로 갱신했다.

### 검증
- `python -m py_compile src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py` 통과.
- `src/aip_fleet_dashboard/static/index.html` 내 JavaScript를 UTF-8로 추출해 `node --check` 통과.

### 판단
- 팀원은 중앙 웹관제에서 RGB/thermal을 별도 변수로 조정하면 된다.
- Pi CPU를 직접 줄이고 싶을 때는 RGB 쪽 `--fps`, `--rgb-raw-max-fps`, preview size, JPEG quality를 먼저 낮춘다.
- thermal 10fps는 웹관제 변수 조정만으로 해결되지 않으며 MLX 송신 보드/baud/I2C 경로 확인이 필요하다.

---

## 2026-06-28 — Thermal UART FPS 최대화 시도

### 배경
사용자가 UART로 열화상 프레임을 최대한 올리는 방향으로 수정해달라고 요청했다. 기존 측정에서 thermal은 약 `3.9~4.0 fps`였고, RGB와 달리 센서/송신 보드 출력률이 의심됐다.

### Pi 수정
- Vision Pi `/home/vision/aip_vision_ws/aip_vision/thermal_uart.py`를 백업 후 수정했다.
  - 백업: `thermal_uart.py.bak_uartmax_20260628_173900`
- systemd unit을 백업 후 수정했다.
  - 백업: `/etc/systemd/system/aip-vision-preview.service.bak_uartmax_20260628_173900`
- `thermal_uart.py`
  - `ZZ 02 06` parser에서 bytes 복사를 줄이고 `memoryview`를 사용.
  - 한 read 후 버퍼에 완성 프레임이 여러 개 있으면 모두 drain하도록 변경.
  - UART 수신 스레드에서 JPEG encode를 하지 않고, HTTP 요청 시 lazy encode하도록 변경.
  - serial timeout을 `0.03s`에서 `0.01s`로 낮추고 `in_waiting` 기반으로 read 크기를 조정.
- `aip-vision-preview.service`
  - `--thermal-protocol mlx_uart_zz`를 추가해 auto protocol 탐색 비용을 줄였다.

### 검증
- `python3 -m py_compile aip_vision/thermal_uart.py aip_vision/web_preview.py` 통과.
- 서비스 재시작 성공.
- 패치 후 115200bps:
  - RGB 약 `7.8 fps`.
  - thermal 약 `3.9 fps`.
  - thermal bytes 약 `6111 B/s`.
  - thermal age 약 `0.20s`.
  - `thermal_protocol=mlx_uart_zz`, `last_error=null`.
- 460800bps 일시 전환 테스트:
  - `ZZ 02 06` 프레임 0건.
  - 안전 복구 후 115200bps에서 약 `3.8 fps` 정상 확인.
- 115200bps rate code `0..7` 스윕:
  - 모두 약 `3.83 fps`.
- 프레임 요청 명령을 `4..30Hz`로 반복:
  - 모두 약 `3.71 fps`.

### 판단
- Pi 수신 코드 병목은 줄였지만 실제 FPS는 오르지 않았다.
- 현재 제한은 Pi 수신부가 아니라 MLX UART 송신 보드/펌웨어의 자동출력 약 `4Hz` 한계로 판단된다.
- UART로 8~10fps가 필요하면 송신 보드가 실제로 고속 baud/update rate를 지원하도록 펌웨어 또는 설정을 바꿔야 한다.
- 고프레임이 필수이면 UART 보드 경유보다 MLX90640 직접 I2C 경로를 별도 검증하는 것이 현실적이다.

### 추가 시도 — 보드 고속 설정 저장
- 매뉴얼 명령표를 확인했다.
  - 460800bps: `A5 15 03 BD`
  - 8Hz: `A5 25 04 CE`
  - automatic output: `A5 35 02 DC`
  - save: `A5 65 01 0B`
- Vision Pi에서 다음을 수행했다.
  - service stop.
  - 115200bps에서 `query -> 8Hz -> 460800 -> auto -> save` 반복 송신.
  - systemd unit을 `--thermal-baud 460800`으로 변경.
  - Vision Pi reboot.
- 결과:
  - service는 460800으로 기동했지만 thermal frame `0건`.
  - 460800에서는 약 `15.5 kB/s`의 깨진 바이트만 수신되고 `ZZ 02 06` header 없음.
  - service stop 후 raw scan에서 115200bps는 정상 header와 약 `3.7 fps` 확인.
- 복구:
  - 115200bps에서 `query -> 4Hz -> 115200 -> auto -> save` 송신.
  - systemd unit을 `--thermal-baud 115200`으로 복구.
  - service 재시작 후 thermal 약 `3.8 fps`, `last_error=null` 확인.
- 판단:
  - 현재 연결된 송신 보드는 매뉴얼 명령만으로 460800/8Hz 저장 운용이 되지 않는다.
  - 실제 8fps UART가 필요하면 송신 보드 펌웨어/제조사 설정툴/전용 MCU 코드 확인이 필요하다.

### 추가 확인 — 직접 I2C 경로
- 8fps 목표를 위해 UART 보드 우회 가능성을 확인했다.
- Vision Pi 상태:
  - `/dev/i2c-0`, `/dev/i2c-1`, `/dev/i2c-10`, `/dev/i2c-22` 존재.
  - `/boot/firmware/config.txt`에 `dtparam=i2c_arm=on`.
  - `vision` 사용자는 `i2c` 그룹 포함.
  - `i2c-tools`, `python3-smbus` 설치 완료.
- `i2cdetect` 결과:
  - `/dev/i2c-1`에 MLX90640 기본 주소 `0x33` 없음.
  - `/dev/i2c-10`, `/dev/i2c-22`의 `0x36`은 `UU`로 잡히며 Pi 카메라/시스템 장치로 판단.
- 판단:
  - 현재 배선/보드 모드에서는 MLX90640 직접 I2C 접근이 불가능하다.
  - GY-MCU90640 보드의 `PS`를 `GND`에 묶고 SDA/SCL을 Pi GPIO2/GPIO3에 연결한 뒤 `i2cdetect -y 1`에서 `0x33`이 보여야 직접 I2C 8Hz reader를 진행할 수 있다.

### 추가 구현 — 직접 I2C rate probe
- `scripts/mlx90640_i2c_rate_probe.py`를 추가했다.
  - 외부 Python 패키지 없이 Linux I2C ioctl을 직접 사용한다.
  - MLX90640 status register `0x8000` data-ready bit를 count한다.
  - control register `0x800D` refresh-rate bits를 `rate-code 4` (`8Hz`)로 설정할 수 있다.
- Vision Pi에도 배포했다.
  - `/home/vision/aip_vision_ws/tools/mlx90640_i2c_rate_probe.py`
- 현재 배선에서 실행 결과:
  - `MLX90640 not detected at /dev/i2c-1 addr=0x33: [Erno 121] Remote I/O error`
- 사용 조건:
  - 보드 `PS -> GND`.
  - SDA/SCL을 Pi GPIO2/GPIO3에 연결.
  - `i2cdetect -y 1`에서 `0x33` 확인 후 probe 실행.

## 2026-06-28 — MLX UART 송신보드 고속 설정 재시도

### 결정
- 사용자가 UART 송신보드를 고속으로 설정해 thermal이 8fps에 가깝게 나와야 한다고 요청했다.
- 이전 460800/8Hz 저장 테스트에서 실패했기 때문에, 이번에는 자동송신 중 명령이 무시되는 가능성을 배제하기 위해 query/single-output 모드로 먼저 전환한 뒤 baud 변경을 다시 시도했다.

### 실행
- Vision Pi service를 중지한 뒤 baseline을 측정했다.
  - 115200bps, `ZZ 02 06`, 약 `3.75~3.8 fps`.
- `A5 35 01 DB` 송신 후 2초 동안 자동 프레임이 멈춘 것을 확인했다.
- 115200bps에서 `8Hz=A5 25 04 CE`, `460800=A5 15 03 BD`를 송신했다.
- 460800bps로 재오픈 후 `query -> 8Hz -> auto`를 송신하고 6초 수신했다.

### 결과
- 460800bps에서는 정상 `ZZ 02 06` 프레임이 0건이었고, quiet-mode 절차에서도 송신보드가 460800으로 전환되지 않았다.
- 115200bps에서 `4Hz -> auto -> save`로 복구했다.
- service 재시작 후 상태:
  - RGB 약 `7.8 fps`.
  - thermal 약 `4.0 fps`.
  - `--thermal-baud 115200 --thermal-protocol mlx_uart_zz`.
  - `last_error=null`.
- Pi UART는 `/dev/serial0 -> /dev/ttyAMA0` PL011 경로이므로 고속 baud 자체가 막힌 상태는 아니다.
- 결론: 현재 송신보드/펌웨어는 A5 명령만으로 460800/8Hz UART 출력을 적용하지 않는다. 8fps가 필수이면 제조사 설정툴/펌웨어 변경 또는 MLX90640 직접 I2C 경로가 필요하다.

## 2026-06-28 — MLX UART 8fps 추가 조사 및 보드 도구 추가

### 질문
- 사용자가 UART로는 아예 불가능한지, 예전에는 가능했던 것 같으니 다른 방법까지 찾아서 MLX thermal frame이 약 8fps가 되도록 해결해 달라고 요청했다.

### 조사/검증
- 공개 GY-MCU90640 ESP8266 스트리머 구현을 확인했다.
  - setup sequence는 `115200 -> 8Hz -> manual -> save`이며, setup 뒤 전원을 껐다 켜야 한다고 안내한다.
- 같은 순서를 Vision Pi에서 시험했다.
  - `A5 55 01 FB` emissivity/sync 응답 확인.
  - `115200 -> 8Hz -> manual -> save`.
  - manual mode에서 자동 frame 0건 확인.
  - `auto` 전환 후에도 115200bps에서는 약 `3.875 fps`.
- `8Hz -> 460800 -> manual/save` 뒤 후보 baud를 스캔했다.
  - 9600/19200/38400/57600/115200/230400/250000/256000/460800/500000/921600/1000000.
  - 정상 `ZZ 02 06` frame은 115200에서만 확인됐고 약 `4.0 fps`.
- 대역폭 계산:
  - `ZZ 02 06` frame은 약 `1544 B/frame`.
  - 8fps는 약 `12.3 kB/s`가 필요하다.
  - 115200 8N1 payload 한계는 약 `11.5 kB/s`라 실제 8fps 전체 프레임 전송에는 부족하다.

### 구현
- `scripts/mlx90640_uart_board_tool.py` 추가.
  - `measure`: 한 baud에서 실제 `ZZ 02 06` fps 측정.
  - `scan`: 여러 baud 후보를 스캔.
  - `stage-high`: `8Hz/460800/auto/save` 저장 후 물리 전원 재인가 준비.
  - `restore-safe`: `115200/4Hz/auto/save` 복구.
- Vision Pi에도 배포했다.
  - `/home/vision/aip_vision_ws/tools/mlx90640_uart_board_tool.py`
- 배포 후 `measure --baud 115200 --duration 5` 검증:
  - 약 `3.8 fps`.
  - service 재시작 후 thermal 약 `4.0 fps`, `last_error=null`.

### 결론/다음 단계
- UART 자체가 불가능하다고 단정할 수는 없다.
- 현재 원격 소프트웨어 명령만으로는 460800/8Hz가 적용되지 않았다.
- 남은 UART 가능성은 `stage-high` 후 GY-MCU90640 보드 MCU 전원을 실제로 완전히 껐다 켠 뒤 `scan --send-auto`로 460800 프레임을 확인하는 것이다.
- Pi reboot만으로는 GPIO 전원이 계속 살아 있어 보드 MCU가 power-cycle되지 않을 수 있다.

## 2026-06-28 — MLX UART autobaud service 적용 및 high-speed stage

### 결정
- GY-MCU90640 매뉴얼을 다시 확인했다.
  - 8Hz 응답 주파수는 `460800bps` 조건으로 명시되어 있다.
  - baud/update/auto 설정 후 save command를 보내고, 모듈 전원을 껐다 켜야 저장 설정대로 동작한다고 되어 있다.
- 따라서 Vision Pi service는 `115200` 고정 대신 `460800 -> 115200` 순서로 자동 감지하도록 바꾼다.

### 구현/적용
- `scripts/vision_preview_autobaud.py`를 추가했다.
  - `--thermal-baud auto`일 때 `mlx90640_uart_board_tool.py scan --send-auto`로 baud를 감지한다.
  - `460800`을 먼저 검사하고 실패하면 `115200`으로 fallback한다.
  - 감지 후 `python3 -m aip_vision.web_preview`를 실제 baud로 exec한다.
- Vision Pi 배포:
  - `/home/vision/aip_vision_ws/tools/vision_preview_autobaud.py`
- systemd 변경:
  - `ExecStart=/usr/bin/python3 /home/vision/aip_vision_ws/tools/vision_preview_autobaud.py ... --thermal-baud auto ...`
- `mlx90640_uart_board_tool.py stage-high` 실행:
  - `manual -> 8Hz -> 460800 -> auto -> save` 송신 완료.

### 검증
- 전원 재인가 전 현재 상태:
  - wrapper가 `115200`을 선택.
  - RGB 약 `7.7~8.0 fps`.
  - thermal 약 `4.0 fps`.
  - `/status.json`: `thermal_baud=115200`, `err=null`.
- 다음 실험은 GY-MCU90640 보드 MCU 전원을 실제로 끊었다 켠 뒤 service를 재시작하고 jounal에서 `selected thermal baud 460800`이 나오는지 확인하는 것이다.

## 2026-06-28 — MLX UART 460800/8Hz 성공 검증

### 결과
- `stage-high` 후 보드/PI 전원이 실제로 재인가되었다.
- `aip-vision-preview.service`가 autobaud wrapper를 통해 `460800`을 선택했다.
  - jounal: `vision_preview_autobaud: selected thermal baud 460800`
  - autobaud scan: `plausible_fps=8.0`, `frames=20` / `2.5s`
- web preview 실제 상태를 10초 계측했다.
  - RGB 약 `7.9 fps`
  - thermal 약 `7.8 fps`
  - `thermal_baud=460800`
  - `thermal_protocol=mlx_uart_zz`
  - `thermal_bytes_per_sec` 약 `12043 B/s`
  - `thermal_error=null`
- HTTP endpoint 확인:
  - `/rgb.jpg` 200 `image/jpeg`
  - `/thermal.jpg` 200 `image/jpeg`
  - `/thermal.mjpg` 200 `multipart/x-mixed-replace`
- 최신 autobaud wrapper 재배포 후 service restart 검증:
  - jounal: `selected thermal baud 460800`
  - autobaud scan: `plausible_fps=8.4`
  - web preview 8초 계측: thermal 약 `7.875 fps`, `thermal_error=null`

### 결론
- UART로 MLX thermal 약 8fps는 가능하다.
- 실패 원인은 UART 방식 자체가 아니라 `8Hz/460800/auto/save` 이후 GY-MCU90640 보드 MCU 전원 완전 재인가가 필요했던 것이다.
- 현재 Vision Pi는 `--thermal-baud auto` 상태라, 보드가 460800이면 460800을 선택하고 실패 시 115200으로 fallback한다.

## 2026-06-28 — Vision Pi jdedu9807 8fps 운영 스냅샷 문서화

### 배경
사용자가 Vision Pi를 `jdedu9807` Wi-Fi에서 주행 중 확인할 수 있게 부드러운 웹관제 스트림 상태와 CPU 정보를 팀원에게 공유할 문서로 정리하고 PR을 요청했다.

### 확인
- Vision Pi는 `jdedu9807`에서 `192.168.0.7`로 연결됐다.
- `aip-vision-preview.service`는 active/enabled 상태다.
- 웹관제는 JPG polling보다 MJPEG direct stream이 주행 확인용으로 더 부드럽다.
- 실측:
  - RGB 약 `7.87 fps`.
  - thermal 약 `7.67 fps`이며 짧은 샘플에서는 약 `8.1 fps`도 확인.
  - `thermal.baud=460800`, `thermal.protocol=mlx_uart_zz`, `last_error=null`.
  - Pi 전체 busy 약 `31~36%`, idle 약 `64~69%`.
  - Vision Python 프로세스는 한 코어 기준 약 `90~94%`.
  - 서비스 메모리 약 `48 MB`, 온도 약 `57.4 C`.

### 변경
- `docs/VISION_PI_STATUS_2026-06-28_KO.md`를 추가해 현재 네트워크, 스트림 URL, 프레임, CPU/메모리/온도, 운영 권장, 장애 확인 순서를 정리했다.
- `docs/VISION_PI_DIRECT_STREAM_KO.md` 상단에 최신 스냅샷 문서 링크를 추가했다.
- `docs/agent_context/pending_tasks.md`의 비전 스트리밍 섹션에 최신 상태 문서와 `jdedu9807` 테스트 결과를 반영했다.

### 결과
- 팀원이 PR에서 현재 Vision Pi 운영 상태와 통합 시 권장 스트림 URL을 바로 확인할 수 있게 됐다.
- Wi-Fi/계정 비밀번호는 저장소 문서에 기록하지 않았다.

## 2026-06-29 — 영상피드 HW-ISP 전환 + 대시보드 영상/열상 통합

### 결정
- 카메라 RGB 캡처를 소프트웨어 디베이어(web_preview, CPU 57~77%)에서 **libcamera 하드웨어 ISP(camera_ros)** 로 전환 — 자율 순찰 CPU 헤드룸 확보.
- 열상은 ROS 경로 유지(이벤트/경보 보존), 정합 오버레이/온도 심부 마커는 대시보드 클라이언트 합성(하이브리드 A-1).

### 구현/적용
- aip1 `aip-vision-cam.service`: camera_ros(libcamera vc4 HW-ISP, OV5647) RGB888 640×480 6fps. image_transport compressed 명시 리맵 + `unset FASTRTPS_DEFAULT_PROFILES_FILE`(SIMPLE discovery).
- 중앙 `aip-central-fusion.service`: central_fusion_node — `/{vid}/arm/image_raw/compressed` 구독 → `/fleet/perception_viz` 6fps 라이브 스트림(연속 타이머) + 180° 회전(`image_rotate`) + 토픽 템플릿(`image_topic`) 정합.
- 대시보드(index.html): 영상 박스 확대(158→260px), 서보암 틸트→리스트(joint3)+반전, 정합 오버레이(cal 슬라이더·localStorage 영속), **온도 심부 마커 모드(기본)**·열상 합성(옵션) 토글, 확대 모달 합성 캔버스 + 열상 스케일업.
- `dashboard_server.py`: `thermal_raw` 구독→최고/최저온 심부(`thermal_spots`) 발행, 알림 캐시 재발사 수정(`_EVENT_TYPES`), 열상 박스 차량 누수(크로스-차량 폴백) 제거.
- web_preview(`aip-vision-rgb`) disabled 폴백 보존, `AIP_VISION_STREAM_URLS` 제거(override.conf).

### 검증
- camera_node CPU 12.5%(이전 57~77%), aip1 load 6.4→2.7.
- 체인 camera_ros→compressed→central_fusion→perception_viz 6fps→대시보드 WS RGB 수신 확인. `thermal_spots`(hot/cold) 라이브 수신 확인.

### 함정/메모
- libcamera 0.1.0에 RPi vc4 파이프라인 포함 → OV5647 HW ISP(/dev/media1) 등록 OK.
- camera_ros 0.6.0 `orientation` 파라미터는 값만 들어가고 실제 회전 **no-op** → central_fusion `cv2.ROTATE_180`로 처리.
- `bash -lc` 로그인셸이 DS 프로파일 주입 → SIMPLE에서 discovery 죽음 → `bash -c` + `unset FASTRTPS_DEFAULT_PROFILES_FILE ROS_DISCOVERY_SERVER` 필수.

## 2026-07-06 — 포트폴리오용 시뮬/웹관제 데모 실행 정비

### 배경
사용자가 현재까지 진행된 상태를 실행해 화면으로 보고, 영상/캡처를 남겨 포트폴리오와 GitHub 업로드 자료로 정리하고 싶다고 요청했다. 실차 완전 군집은 아직 미해결임을 설명해야 했다.

### 조치
- `docker/sim/docker-compose.yml`에 `8080:8080` 포트를 추가해 sim 컨테이너의 FastAPI 웹 대시보드를 호스트 브라우저에서 바로 볼 수 있게 했다.
- `docker/sim/Dockerfile`에서 `entrypoint.sh` CRLF를 빌드 시 LF로 정규화하도록 하고, sim 런타임 의존성(`twist_mux`, `nav2_msgs`, FastAPI/Pillow/uvicon)을 추가했다.
- `docker/sim/entrypoint.sh`는 전체 저장소를 빌드하지 않고 포트폴리오 시연에 필요한 패키지 세트만 빌드하도록 좁혔다. 이로써 `m-explore`/map_merge 등 심화 패키지 의존성 때문에 기본 시연이 막히지 않게 했다.
- `src/aip_fleet_sim/config/vehicles.yaml`의 시뮬 차량 ID를 현재 중앙 계약에 맞춰 `aip1/aip2/aip3`로 정렬했다.
- `sim_vehicle_node.py` heartbeat 발행을 최신 `FleetHeartbeat` 계약(`robot_id`, `mode`, `battery_percentage`, `status` 등)에 맞췄다.
- `sim_world_node.py`가 `/map`, `/map_static`, `/<vid>/map`, `/<vid>/dashboard/map`을 주기 발행하고 `/fleet/map_ready=true`를 발행하도록 해 웹관제 첫 화면에서 `MAP READY`와 맵이 표시되게 했다.
- `PORTFOLIO_KO.md`를 추가해 현재 구현 범위, 데모 실행법, 군집 미완성 이유, 다음 단계를 정리했다.
- 브라우저 캡처 산출물:
  - `docs/portfolio/assets/dashboard_overview.png`
  - `docs/portfolio/assets/dashboard_overview_wide.png`
  - `docs/portfolio/assets/dashboard_demo.gif`
  - `docs/portfolio/assets/demo_frames/`

### 검증
- WSL Docker에서 `docker compose -f docker/sim/docker-compose.yml up -d --build` 경로로 sim 컨테이너 기동.
- 웹 대시보드 `http://localhost:8080` 응답 및 브라우저 표시 확인.
- UI에서 `3 online`, `MAP READY`, `전체맵/저장맵 · 400×400 · 0.05 m/cell`, 차량 pose marker 확인.
- `/fleet/status`에서 `aip1/aip2/aip3` heartbeat online 및 `offline_vehicle_ids: []` 확인.

### 판단
- 현재 포트폴리오로 보여줄 수 있는 범위는 “중앙 관제, 안전 체인, 3대 시뮬레이션, 맵/pose 표시, follower coordination 기반”이다.
- 실차 완전 군집은 아직 미완이다. 핵심 이유는 각 차량의 독립 위치추정/TF/heartbeat 계약 안정화, 중앙 coordinator 의존도, 실차 DDS/네트워크 안정화, 이기종 하드웨어 차이, 3대 동시 자율 순찰 장시간 검증이 남아 있기 때문이다.

## 2026-07-06 — 포트폴리오용 AGENTS 지침 정비

### 배경
사용자가 이 저장소를 클로봇 로봇 응용 SW 개발자 신입 지원용 포트폴리오로 정리하기 위해, Codex가 따라야 할 루트 `AGENTS.md` 작성 규칙을 요청했다.

### 조치
- 저장소 루트 `AGENTS.md`를 포트폴리오 정리 목적에 맞게 갱신했다.
- 확인되지 않은 기능을 구현된 것처럼 쓰지 않는 원칙, 기술 스택 검증 기준, README 필수 구성, 수정 전후 설명 규칙을 명시했다.
- 기존 프로젝트 문맥에 맞춰 작업 시작 시 읽을 문서, SSOT, 보안/시크릿 주의사항, 실행 참고를 함께 보존했다.

### 결과
- 향후 README와 docs 정리 시 과장보다 구조, 역할, 문제 해결, 학습 내용을 중심으로 작성하도록 기준을 세웠다.
- 미완성 기능은 `TODO`, `확인 필요`, `향후 개선`으로 구분해 면접에서 설명 가능한 수준으로 남기도록 했다.

## 2026-07-06 — 포트폴리오용 README 개편

### 배경
사용자가 클로봇 로봇 응용 SW 개발자 신입 지원용 포트폴리오로 보이도록 README를 재작성해 달라고 요청했다. 과장 없이 실제 코드에서 확인된 기능만 쓰고, 확인되지 않은 내용은 `TODO` 또는 `확인 필요`로 표시하는 것이 핵심 조건이었다.

### 조치
- 루트 `README.md`를 14개 섹션(Project Overview, Demo, My Role, Key Features, System Architecture, ROS2 Communication, Web Dashboard, Vision Camera Integration, Sub Vehicle Control, Tech Stack, How to Run, Troubleshooting, What I Learned, Future Improvements)으로 전면 개편했다.
- 웹관제, 비전카메라, 서브차량 제어, ROS2 통신 계약을 코드 근거 중심으로 정리했다.
- 실차 완전 군집 주행, aip3 STS3215 드라이버, YOLOv8 현장 검증처럼 불확실한 항목은 `확인 필요` 또는 향후 개선으로 분리했다.

### 결과
- README만 읽어도 프로젝트 목적, 담당 역할, 시스템 구조, 실행 방법, 현재 한계가 보이도록 정리했다.
- 포트폴리오 표현은 “완료”보다 “확인됨/확인 필요/TODO” 기준으로 정리했다.

## 2026-07-06 — README 보완용 docs 문서 세트 생성

### 배경
사용자가 README를 보완하기 위해 `docs/` 하위에 이미지/영상/아키텍처 폴더와 면접 준비, ROS2 통신, 시스템 아키텍처, 트러블슈팅 문서를 만들어 달라고 요청했다. 소스코드는 수정하지 않고, 확인되지 않은 내용은 `TODO` 또는 `확인 필요`로 표시하는 조건이었다.

### 조치
- `docs/images/`, `docs/videos/`, `docs/architecture/` 폴더를 추가하고 Git 추적용 `.gitkeep`을 배치했다.
- `docs/system-architecture.md`에 전체 시스템 구조, 데이터 흐름, 웹관제/ROS2/비전/서브차량 연결 구조와 Mermaid diagram을 정리했다.
- `docs/ros2-communication.md`에 확인된 ROS2 패키지, Node, Topic, Service, Action, Message Type을 표로 정리했다.
- `docs/troubleshooting.md`에 ROS2 topic, 웹관제, 카메라, 빌드, E-Stop 문제 확인 순서를 정리했다.
- `docs/interview-notes.md`에 프로젝트 소개, 담당 역할, 데이터 흐름, 예상 면접 질문과 답변 방향을 정리했다.

### 결과
- README에서 다 담기 어려운 기술 세부 내용을 docs 문서로 분리했다.
- 실차 완전 군집, aip3 드라이버, YOLOv8 현장 정확도, 카메라 캘리브레이션 등 불확실한 내용은 `확인 필요`로 분리했다.

## 2026-07-06 — ROS2 통신 문서 상세화

### 배경
사용자가 저장소의 ROS2 관련 코드를 직접 검색해 `docs/ros2-communication.md`를 더 구체적으로 정리해 달라고 요청했다. `package.xml`, `setup.py`, `CMakeLists.txt`, launch 파일, `rclpy`/`rclcpp` 코드, publisher/subscriber/service/action/message/parameter/launch argument를 확인하고, 확인된 사실과 TODO를 구분하는 것이 핵심 조건이었다.

### 조치
- `src/` 하위의 `package.xml`, `setup.py`, `CMakeLists.txt`, launch 파일과 주요 Python/C++ ROS2 코드를 검색했다.
- `aip_fleet_msgs`의 custom message/service 목록을 `CMakeLists.txt` 근거로 정리했다.
- `supervisor_node`, `watchdog_node`, `dashboard_server`, `patrol_node`, `keepout_zone_node`, perception node, sim node, real bridge node, `explore`, `map_merge` 등 주요 ROS2 Node의 입력/출력 topic, message type, service/action 사용 여부를 표로 정리했다.
- 코드에서 직접 확인된 항목은 `확인됨`, 세부 검증이 필요한 항목은 `TODO` 또는 `확인 필요`로 표시했다.
- 면접에서 설명해야 할 ROS2 질문 10개를 문서 마지막에 추가했다.

### 결과
- `docs/ros2-communication.md`가 포트폴리오/면접용 ROS2 통신 근거 문서로 보강되었다.
- `AssignMission.srv` 사용처, 일부 coordinator/localizer/map_merge 세부 topic, 실제 런타임 `ros2 topic/service/action list` 결과는 추가 확인 TODO로 남겼다.

## 2026-07-06 — 웹관제 문서 생성

### 배경
사용자가 웹관제 관련 코드를 찾아 `docs/web-dashboard.md` 문서를 만들어 달라고 요청했다. HTML, CSS, JavaScript, React/Vue 사용 여부, WebSocket/REST/rosbridge 사용 여부, 상태 표시, 제어 버튼, 카메라 화면, 에러/로그 표시 코드를 확인하고 실제 확인된 기능만 정리하는 조건이었다.

### 조치
- `src/aip_fleet_dashboard/static/index.html`에서 단일 HTML 기반 UI, inline CSS, vanilla JavaScript, WebSocket 연결, 차량 상태 표시, 지도/비전/알림/제어 버튼 코드를 확인했다.
- `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py`에서 FastAPI 서버, `/ws` WebSocket endpoint, `/` 및 `/static` 제공, ROS2 publish/subscribe/action/service 연동을 확인했다.
- `src/aip_fleet_foxglove_panels`에서 React/TypeScript 기반 Foxglove custom panel이 별도 존재함을 확인했다.
- `rosbridge`, `roslibjs`, Vue 사용은 코드 검색에서 확인되지 않았으므로 문서에 사용 확인 안 됨으로 표시했다.

### 결과
- `docs/web-dashboard.md`를 새로 생성해 목적, 확인된 파일, 데이터 흐름, 주요 기능, 제어 명령 흐름, 한계점, 개선 방향을 정리했다.
- 메인 웹관제와 Foxglove React 패널을 구분하고, REST 제어 API가 아닌 WebSocket 중심 구조임을 명확히 적었다.

## 2026-07-06 — 비전카메라/OpenCV 문서 생성

### 배경
사용자가 비전카메라 또는 OpenCV 관련 코드를 찾아 `docs/vision-camera.md` 문서를 만들어 달라고 요청했다. camera capture, OpenCV, image topic, `sensor_msgs/Image`, `cv_bridge`, frame 처리, 객체/감시 기능, 웹 전달 코드를 확인하고 실제 코드 기반으로만 정리하는 조건이었다.

### 조치
- `src/aip_fleet_perception`의 camera launch, Vision Pi bridge, central fusion, thermal driver, patrol monitor 코드를 확인했다.
- `src/aip_fleet_dashboard`의 image topic 구독과 WebSocket base64 전달 코드를 확인했다.
- OpenCV 사용 지점(`imdecode`, `cvtColor`, `rotate`, `perspectiveTransform`, `applyColorMap`, `rectangle`, `putText`, `resize`, `imencode`)을 정리했다.
- `cv_bridge`, 직접 `cv2.VideoCapture`, 차선 인식 코드는 확인되지 않았으므로 문서에 사용 확인 안 됨으로 표시했다.
- YOLOv8 호출 코드는 확인했지만, fire/smoke 전용 모델과 정확도 검증은 확인 필요로 구분했다.

### 결과
- `docs/vision-camera.md`를 새로 생성해 목적, 확인된 파일, 입력 데이터, 처리 흐름, 출력 데이터, 확인된 기술, 한계점, 개선 방향을 정리했다.
- 마지막에 비전카메라 관련 예상 면접 질문 10개와 답변 방향, 직접 확인해야 할 TODO를 추가했다.

## 2026-07-06 — 서브차량 제어 문서 생성

### 배경
사용자가 서브차량 제어 관련 코드를 찾아 `docs/sub-vehicle-control.md` 문서를 만들어 달라고 요청했다. 모터 제어, `cmd_vel`, `geometry_msgs/Twist`, serial 통신, ESP32/임베디드 보드 연동, start/stop/E-Stop, joystick/keyboard/web command, 제어 명령 수신 ROS2 Node를 확인하고 실제 구현된 내용만 정리하는 조건이었다.

### 조치
- `serial_bridge.py`, `sim_vehicle_node.py`, `supervisor_node.py`, `watchdog_node.py`, dashboard backend/frontend, twist_mux 설정, TurtleBot3/custom vehicle launch, coordinator, Gazebo relay/stuck escape 코드를 확인했다.
- `firmware/main_agv`의 ESP32 serial protocol, motor control, firmware main loop를 확인했다.
- `firmware/scout/src/main.cpp`는 `cmd_vel`/`estop` micro-ROS skeleton이 있으나 motor PWM 매핑이 TODO이고 현재 `FleetHeartbeat.msg`와 필드 정합 확인이 필요하다고 분리했다.
- physical joystick node는 확인되지 않았고, 웹 keyboard drive와 hold-drive는 확인됨으로 정리했다.

### 결과
- `docs/sub-vehicle-control.md`를 새로 생성해 목적, 확인된 파일, 입력 명령, 제어 흐름, 출력/동작 결과, 안전 고려사항, 한계점, 개선 방향을 정리했다.
- 마지막에 서브차량 제어 예상 면접 질문 10개와 답변 방향, 직접 확인해야 할 TODO를 추가했다.

## 2026-07-06 — 포트폴리오용 폴더 구조 정리

### 배경
사용자가 소스코드나 ROS2 package 구조를 건드리지 않고, 포트폴리오 제출 관점에서 문서/이미지/영상 자료의 위치만 보기 좋게 정리해 달라고 요청했다. 작업 전 이동 대상과 위험 대상을 구분하고, 작업 후 README 링크와 직접 확인할 사항을 정리하는 조건이었다.

### 조치
- `docs/` 루트에 있던 포트폴리오 보조 문서를 성격별로 분리했다.
- 시스템/ROS2/웹관제/비전/서브차량 제어 문서는 `docs/architecture/`로 이동했다.
- 면접 노트와 troubleshooting 문서는 `docs/portfolio/`로 이동했다.
- 데모 캡처 PNG는 `docs/images/`, 데모 GIF는 `docs/videos/`로 이동했다.
- GIF 생성용 중간 frame 자료는 포트폴리오 핵심 산출물이 아니므로 `archive/portfolio-demo-frames/`로 이동했다.
- `README.md`, `PORTFOLIO_KO.md`, `docs/architecture/ros2-communication.md`의 이동된 자료 경로를 새 위치에 맞게 갱신했다.
- `.gitignore`에 rosbag/MCAP/DB3 및 raw demo capture 폴더 제외 규칙을 추가했다.

### 결과
- 소스코드, ROS2 package 이름, import 경로, launch 파일 구조는 수정하지 않았다.
- README의 데모 이미지/GIF 경로는 `docs/images/`와 `docs/videos/` 기준으로 정리되었다.
- 기존 메인 문서(`docs/HANDOFF.md`, `docs/ARCHITECTURE.md`, `docs/ANALYSIS.md`, `docs/SECURITY.md`, `docs/agent_context/**`)는 SSOT 성격이 있어 이동하지 않았다.

## 2026-07-06 — 면접 대비 Interview Notes 완성

### 배경
사용자가 클로봇 로봇 응용 SW 개발자 신입 면접에서 프로젝트를 설명할 수 있도록 `docs/interview-notes.md`를 완성해 달라고 요청했다. 과장 없이 확인된 코드 근거와 확인 필요 항목을 구분하고, ROS2/웹관제/비전카메라/서브차량 제어/협업/AI 도구/지원동기 질문을 포함하는 것이 핵심 조건이었다.

### 조치
- `docs/portfolio/interview-notes.md`를 12개 섹션 구조로 다시 작성했다.
- 사용자가 요청한 경로에서도 바로 확인할 수 있도록 동일한 내용을 `docs/interview-notes.md`에도 복사했다.
- 프로젝트 한 줄 소개, 담당 역할, 전체 시스템 구조, ROS2 통신 구조, 웹관제 데이터 흐름, 비전카메라 처리 흐름, 서브차량 제어 흐름을 면접 답변용 문장으로 정리했다.
- 확인되지 않은 기능은 `확인 필요`로 표시하고, YOLO 성능 검증, aip3 custom driver, 실차 군집 자율주행 완성 여부 등은 과장하지 않도록 명시했다.
- 예상 면접 질문 30개와 각 질문별 짧은 답변 방향을 추가했다.

### 결과
- `docs/interview-notes.md`와 `docs/portfolio/interview-notes.md`가 동일한 면접 대비 문서로 정리되었다.
- 소스코드와 실행 방식은 수정하지 않았다.

## 2026-07-06 — 수업용 Docker stack과 AIP sim 포트 충돌 해소

### 배경
사용자가 수업용 MySQL/MLflow/Spark/Jupyter stack에서 `8080`, `5000`, `3306`, `7077`, `8888`, `4040`, `8001` 포트를 사용 중이라 AIP 웹관제 sim 포트를 변경해 달라고 요청했다.

### 조치
- `docker/sim/docker-compose.yml`의 host 포트를 `18080:8080`, `18765:8765`로 변경해 수업용 `8080` Spark Master와 충돌하지 않게 했다.
- sim 재빌드 안전 문제를 함께 수정했다.
  - `docker/sim/Dockerfile`: `python3-uvicon` → `python3-uvicorn`
  - `sim_vehicle_node.py`, `sim_world_node.py`: `retun` → `return`
  - `sim_vehicle_node.py`: `waning` → `warning`
- `fleet_sim.launch.py`에서 `central.launch.py` include 시 `with_foxglove:=true`를 전달해 `ws://localhost:18765`가 실제 Foxglove bridge로 연결되도록 했다.
- README, `PORTFOLIO_KO.md`, `docs/portfolio/troubleshooting.md`의 sim 접속 주소를 `http://localhost:18080`, `ws://localhost:18765` 기준으로 갱신했다.

### 검증
- `docker compose -f docker/sim/docker-compose.yml down && docker compose -f docker/sim/docker-compose.yml up -d --build` 성공.
- 수업용 stack은 유지됨: Spark Master `localhost:8080`, MLflow `5000`, MySQL `3306`, Jupyter `8888` 등 그대로 실행 중.
- AIP sim 컨테이너 포트: `0.0.0.0:18080->8080`, `0.0.0.0:18765->8765`.
- 브라우저 `http://localhost:18080/`에서 `CONNECTED`, `MAP READY`, `3 online` 확인.
- ROS2 `/fleet/status`에서 `aip1/aip2/aip3` 모두 online, `offline_vehicle_ids: []` 확인.
- `/foxglove_bridge` 노드와 `18765` TCP open 확인.

## 2026-07-06 — AIP sim 자동 데모 주행 및 맵 개선

### 배경
사용자가 웹관제는 열리지만 시뮬레이션 차량이 계속 멈춰 보이고, 시뮬레이션 맵도 더 그럴듯하게 바꾸고 싶다고 요청했다. 현재는 실차가 없으므로 시뮬레이션으로만 돌리되, 추후 실제 로봇 3대 구동과 구분되어야 했다.

### 조치
- `aip_fleet_sim`에 `demo_patrol_node`를 추가했다.
  - `aip1`의 `/aip1/autonomy_cmd_vel`에 waypoint 기반 데모 주행 명령을 10Hz로 발행한다.
  - 기존 `twist_mux`와 coordinator 경로를 그대로 사용해 `aip2/aip3`가 follower처럼 따라오게 했다.
  - `fleet_sim.launch.py`의 `with_demo_motion` 인자로 켜고 끌 수 있게 했으며 기본값은 `true`다.
- `src/aip_fleet_sim/config/world.yaml`을 단순 기둥 맵에서 창고/산업 현장형 레이아웃으로 변경했다.
  - 외곽 벽, 랙 열, 검사실/장비 섬, 충전/대기 구역을 직사각형 obstacle로 구성했다.
- README와 `PORTFOLIO_KO.md`에 이 자동 주행이 시뮬레이션 전용이고 실제 차량 bringup에는 포함되지 않는다고 명시했다.

### 검증
- WSL Python 구문 검증 통과.
- `colcon test --packages-select aip_fleet_sim` 결과 `26 passed`.
- waypoint가 obstacle 내부에 들어가지 않는지 확인했다.
- `docker compose -f docker/sim/docker-compose.yml down -v && docker compose -f docker/sim/docker-compose.yml up -d --build`로 AIP sim 클린 재빌드/재기동 성공.
- 로그에서 `demo_patrol_node` 실행, `/foxglove_bridge` 실행, `World published ... 20 obstacles` 확인.
- `/aip1/autonomy_cmd_vel`과 `/aip1/cmd_vel` 발행 확인.
- `/aip1/odom`이 4초 사이 `(4.59, 4.37)` → `(3.14, 4.59)`로 변해 실제 이동 확인.
- `/fleet/status`에서 `aip1/aip2/aip3` 모두 `mode: autonomous`, `healthy: true`, `estop: false`, `status: ok`, `offline_vehicle_ids: []` 확인.
- 인앱 브라우저 `http://localhost:18080/`에서 `CONNECTED`, `MAP READY`, `3 online`, 세 차량 `AUTO`, 속도/이동거리 증가, 새 창고형 맵 렌더링 확인.

## 2026-07-06 — 로봇 응용 SW 면접 복습용 PDF 생성

### 배경
사용자가 클로봇 로봇 응용 SW 개발자 공고와 AIP 프로젝트를 연결해 공부할 수 있는 PDF 자료를 요청했다. 목적은 면접 복습용이며, 개념에서 프로젝트 구조, 데이터 흐름, 시뮬레이션, 실차 확장, 면접 답변까지 이어지는 15~20쪽 분량으로 정했다.

### 조치
- `output/pdf/aip_robot_app_sw_study_guide.pdf`를 생성했다.
- ReportLab와 Windows 한글 폰트(`malgun.ttf`, `malgunbd.ttf`)를 사용해 한글 PDF를 구성했다.
- 목차는 공고 요구사항, ROS2 핵심 개념, 패키지 구조, 상태/제어 데이터 흐름, 웹관제, 시뮬레이션, 실차 확장, ESP32/Pi 없는 상황, 센서/비전, 안전 구조, 실행 체크리스트, 면접 답변, 확인됨/확인 필요/향후 개선으로 구성했다.
- 중간 생성/검증 파일은 `tmp/pdfs/` 아래에 두었다.

### 검증
- `pdfinfo` 기준 A4 17쪽 PDF로 확인했다.
- `pdftoppm`으로 전체 17쪽을 PNG 렌더링했다.
- 표지, 시스템 요약, 상태 흐름, 실차 확장, 면접 답변, 마지막 체크리스트 페이지를 시각 확인했다.
- `pypdf` 텍스트 추출에서 `ROS2`, `웹관제`, `시뮬레이션`, `실차 연동`, `확인 필요`, `/<vid>/heartbeat`가 포함됨을 확인했다.

### 판단
- PDF는 현재 포트폴리오 표현 원칙에 맞춰 확인된 범위와 확인 필요 범위를 분리했다.
- 실차 3대 완전 자율주행은 구현 완료가 아니라 향후 검증 과제로 표시했다.

## 2026-07-06 — 클로봇 합격 대비 AIP 면접 전략 PDF 생성

### 배경
사용자가 기존 개념 복습용 PDF보다 더 면접 중심의 합격 대비 자료를 요청했다. 목표는 클로봇 로봇 응용 SW 개발자 공고에 맞춰 AIP 프로젝트를 왜 만들었고, 각 기술이 왜 필요하며, 면접에서 어떻게 답변할지 공부할 수 있는 20~25쪽 전략서로 정했다.

### 조치
- 기존 `output/pdf/aip_robot_app_sw_study_guide.pdf`는 보존했다.
- 새 산출물 `output/pdf/aip_clobot_interview_success_guide.pdf`를 생성했다.
- 각 챕터에 `왜 필요한가`, `AIP 프로젝트에서 어떻게 쓰였나`, `면접에서 어떻게 말할까`, `반드시 기억`, `면접 한 문장`, `주의`를 포함했다.
- 내용은 공고 분석, 30초/1분/3분 프로젝트 답변, ROS2, 웹관제, 상태/제어 흐름, 시뮬레이션, 실차 확장, ESP32/Pi 없는 상황, LiDAR/odom/TF/map, 카메라/thermal/alert, E-Stop/watchdog, Docker/포트 분리, 문제 해결, 한계와 개선, 예상 질문 40개, 암기 카드, 면접 직전 점검표로 구성했다.
- 구현하지 않은 기능은 `확인 필요`, `검증 예정`, `향후 개선`으로 분리해 과장 표현을 피했다.
- 중간 생성/검증 파일은 `tmp/pdfs/` 아래에 두었다.

### 검증
- `pdfinfo` 기준 A4 22쪽 PDF로 확인했다.
- `pypdf` 텍스트 추출에서 `클로봇`, `ROS2`, `웹관제`, `왜 필요한가`, `반드시 기억`, `확인 필요`, `cmd_vel`, `E-Stop` 포함을 확인했다.
- `pdftoppm`으로 전체 22쪽을 PNG로 렌더링했다.
- contact sheet와 표지, 공고 분석, ROS2 개념, 상태 흐름, 제어 흐름, 실차 확장, 예상 질문, 암기 카드, 면접 직전 점검표 페이지를 시각 확인했다.

### 판단
- 새 PDF는 면접 답변 제작과 암기용으로 쓰기 적합하며, 기존 복습용 PDF보다 공고 대응과 답변 프레임에 초점을 맞췄다.
- 시뮬레이션 검증과 실차 검증 예정 범위를 명확히 구분해 포트폴리오 표현 원칙을 유지했다.

## 2026-07-08 — 로봇 SW 면접용 포트폴리오 브랜치 정리

### 배경
사용자가 기존 `main` 브랜치는 그대로 두고, 클로봇 로봇 응용 SW 신입과 로보티즈 인턴 지원을 위한 GitHub 면접용 브랜치를 새로 만들어 달라고 요청했다. 핵심 방향은 로봇 SW 채용담당자가 3분 안에 프로젝트 목적, 역할, 구현 범위, 한계를 볼 수 있게 정리하는 것이었다.

### 조치
- 새 브랜치 `codex/robot-sw-portfolio`를 생성했다.
- `README.md` 상단을 채용담당자용 Quick Scan, 데모, 보수적 역할 표현 중심으로 재정리했다.
- 신규 문서 `docs/PROJECT_FACTS.md`, `docs/WHAT_I_DID.md`, `docs/TECH_STACK.md`, `docs/TEST_AND_LIMITATIONS.md`, `docs/INTERVIEW_EXPLANATION_NOTES.md`를 추가했다.
- `docs/portfolio/company-fit-clobot-robotis.md`와 `docs/portfolio/application_checklist.md`를 추가해 클로봇/로보티즈 공고별 연결 포인트와 제출 전 체크리스트를 정리했다.
- `PORTFOLIO_KO.md`에 면접관용 상세 문서 링크를 추가했다.
- `.gitignore`에 `firmware/scout_microros/secrets.ini`, `tmp/`, `archive/portfolio-demo-frames/`를 추가해 secret과 중간 산출물이 제출 브랜치에 섞이지 않게 했다.

### 검증
- README의 대표 이미지, GIF, 포트폴리오 문서, 직무 매칭 문서, PDF 경로가 실제 파일로 존재함을 확인했다.
- `tmp/pdfs/*`, `archive/portfolio-demo-frames/*`, `firmware/scout/secrets.ini`, `firmware/scout_microros/secrets.ini`가 ignore 되는 것을 확인했다.
- PowerShell에는 Docker CLI가 없었으므로 WSL에서 `docker compose -f docker/sim/docker-compose.yml config`를 실행했고, `18080:8080`, `18765:8765` 포트 매핑을 확인했다.
- WSL에서 `docker compose -f docker/sim/docker-compose.yml up -d --build`를 실행해 `aip_sim` 컨테이너를 기동했다.
- `curl http://localhost:18080/` HTML 응답과 `/fleet/status`의 `aip1/aip2/aip3` healthy/autonomous, `offline_vehicle_ids: []`를 확인했다.

### 판단
- GitHub 제출본은 README, 핵심 docs, 대표 이미지/GIF, 최종 PDF 위주로 간결하게 정리한다.
- 중간 PDF 렌더링 PNG와 demo frame 원본은 저장소에 남아 있더라도 Git stage 대상에서 제외한다.
- 본인 역할은 "전체 분석, ROS2 통신/웹관제/비전/서브차량 제어 흐름 통합 정리, 문서화, 시연 자료 준비" 중심으로 말하고, 실차 장시간 군집 주행, YOLO 현장 성능, aip3 custom driver 완성도는 계속 확인 필요로 둔다.

## 2026-07-10 — 현재 PC ROS2/웹관제 환경 진단

### 배경
사용자가 현재 PC에서 ROS2를 돌릴 수 있는지, 실제 로봇들을 웹관제에 연결할 수 있는지 확인해 달라고 요청했다.

### 확인 결과
- Windows PowerShell PATH에는 `ros2`, `colcon`, `docker` 명령이 잡히지 않았다.
- WSL Ubuntu는 실행 중이며 Docker CLI/Compose는 설치되어 있었다. 그러나 WSL 내부에 `/opt/ros`가 없고 `ros2`, `colcon` 명령도 없었다.
- `aip_sim` Docker 컨테이너는 실행 중이었다. 웹관제 `http://localhost:18080`과 Foxglove bridge `ws://localhost:18765` 포트가 열려 있었다.
- 컨테이너 내부 ROS2 Humble 환경에서 `/fleet/status`, `/aip1/odom`, `/fleet/override` 등을 확인했고, `/fleet/status`는 `aip1/aip2/aip3` 모두 healthy/autonomous로 보고했다.
- 현재 PC는 외부 네트워크에 연결돼 있었고, WSL은 NAT 대역 `192.168.98.20`이었다. 로봇망으로 문서화된 `192.168.0.3`, `192.168.0.4`, `192.168.0.5`에는 ping이 닿지 않았다. 공인 IP는 포트폴리오 공개를 위해 기록에서 제거했다.
- `docker/central/.env`는 없고 `.env.example`만 있다. 중앙 production compose는 InfluxDB 필수 환경변수 보간 단계에서 실패했다.

### 판단
- 현재 PC는 **Docker 기반 시뮬레이션/포트폴리오 웹관제 데모는 바로 가능**하다.
- 현재 상태만으로는 **실제 로봇용 ROS2 중앙 PC 환경은 준비 완료가 아니다**. 네이티브 ROS2 Humble/colcon 설치, 로봇망 `192.168.0.0/24` 접속, 중앙 IP/Discovery Server 설정 정리, `docker/central/.env` 준비가 필요하다.

## 2026-07-10 — WSL에서 Pi 없는 로봇 구동 가능 여부 추가 진단

### 배경
사용자가 WSL에서 Raspberry Pi가 없는 로봇을 구동하기 위한 설치 환경이 되어 있는지 추가로 확인해 달라고 요청했다.

### 확인 결과
- WSL은 Ubuntu 26.04이며 Docker/Compose는 설치되어 있지만, WSL 네이티브 `ros2`/`colcon`/`/opt/ros`는 없다.
- WSL Python에는 `pyserial`은 있으나 ROS2가 없어 `serial_bridge`를 네이티브 실행할 수 없다.
- 현재 실행 중인 `aip_sim` 컨테이너에는 ROS2 Humble과 웹관제 의존성은 있지만 `aip_fleet_real` 패키지와 `pyserial`, `micro_ros_agent`는 없다.
- `microros/micro-ros-agent:humble` Docker image는 로컬에 없다.
- WSL에는 `/dev/ttyUSB*`, `/dev/ttyACM*`, `/dev/serial/by-id/*` 장치가 보이지 않고, Windows에는 기본 `COM1`, `COM2`만 확인됐다. `usbipd` 명령도 감지되지 않았다.

### 판단
- 현재 WSL은 **시뮬레이션 로봇 구동 환경**으로는 동작하지만, **Pi 없는 실물 로봇을 바로 구동하는 환경은 아니다**.
- ESP32-only/micro-ROS 방식이라면 micro-ROS Agent image 설치, UDP 8888/로봇망 연결, scout firmware의 실제 motor PWM 매핑 검증이 필요하다.
- USB serial로 ESP32를 직접 붙이는 방식이라면 ROS2 실행 환경, `aip_fleet_real` 빌드, `pyserial`, USB/COM 포트 WSL 전달 설정이 필요하다.

## 2026-07-10 — Gazebo/Ignition 실행 환경 확인

### 배경
사용자가 현재 WSL/PC에서 Gazebo에 띄워서 볼 수 있는 환경도 설치되어 있는지 확인해 달라고 요청했다.

### 확인 결과
- WSL 네이티브에는 `gazebo`, `gz`, `ign` 실행 파일이 잡히지 않았다.
- WSL dpkg 목록에서도 Gazebo/Ignition/ROS-GZ 관련 설치 패키지는 확인되지 않았다.
- 실행 중인 `aip_sim` 컨테이너에도 `gazebo`, `gz`, `ign` 실행 파일이 없었다.
- `aip_sim` 컨테이너의 ROS2 install에는 `aip_fleet_gazebo`, `ros_gz_sim`, `gazebo_ros` 패키지가 잡히지 않았다.
- 저장소 소스에는 `src/aip_fleet_gazebo` 패키지가 존재하고, `package.xml` 기준 `ros_gz_sim`, `ros_gz_bridge`, `ign_ros2_control` 의존성을 요구한다.

### 판단
- 현재 열려 있는 `http://localhost:18080`은 Gazebo가 아니라 Docker 기반 2D sim/웹관제이다.
- 현재 PC/WSL 상태로는 **Gazebo/Ignition에 로봇을 띄워서 보는 환경은 아직 설치 완료가 아니다**.
- Gazebo 시뮬을 쓰려면 Ubuntu 22.04 + ROS2 Humble 조합에서 `ros-humble-ros-gz`, `ros-humble-ign-ros2-control`, 필요 시 `ros-humble-turtlebot3-gazebo` 등을 설치하고 `aip_fleet_gazebo`를 빌드해야 한다.

## 2026-07-10 — 실로봇 대비 Ubuntu 22.04 WSL/ROS2 Humble 환경 설치

### 배경
사용자가 나중에 실제 로봇을 가져와 돌릴 예정이므로, 맞는 환경을 알려주고 그 기준에 맞춰 설치 및 확인을 요청했다.

### 조치
- Windows WSL에 `Ubuntu-22.04` 배포판을 새로 설치했다.
- 새 배포판은 `Ubuntu 22.04.5 LTS (Jammy Jellyfish)`로 확인됐다.
- ROS2 Humble apt repository를 추가하고, 다음 주요 패키지를 설치했다.
  - `ros-humble-desktop`
  - `ros-humble-foxglove-bridge`
  - `ros-humble-twist-mux`
  - `ros-humble-nav2-bringup`, `ros-humble-navigation2`
  - `ros-humble-slam-toolbox`
  - `ros-humble-robot-localization`
  - `ros-humble-turtlebot3`, `ros-humble-turtlebot3-bringup`, `ros-humble-turtlebot3-gazebo`
  - `ros-humble-ros-gz`, `ros-humble-ign-ros2-control`
  - `ros-humble-rosbag2-storage-mcap`, `ros-humble-cv-bridge`, `ros-humble-camera-calibration`
  - `python3-colcon-common-extensions`, `python3-rosdep`, `python3-serial`, `python3-fastapi`, `python3-uvicorn`
- `rosdep init/update`를 수행했다.
- `rosdep install`은 `ydlidar_ros2_driver`, `micro_ros_agent`, `micro_ros_platformio`를 skip key로 두고 실행했다. `ydlidar_ros2_driver`와 `micro_ros_agent`는 apt 후보가 없어 실물 장치 확정 후 별도 설치가 필요하다.
- `/opt/aip/fastdds_client_profile.xml`에 FastDDS profile을 배치했다.
- 새 22.04 WSL에서 다음 패키지 범위를 colcon build했다.
  - `aip_fleet_msgs`
  - `aip_main_description`
  - `aip_fleet_supervisor`
  - `aip_fleet_dashboard`
  - `aip_fleet_bringup`
  - `aip_fleet_autonomous`
  - `aip_fleet_gazebo`
  - `aip_fleet_real`

### 검증
- `ros2` 명령 실행 확인.
- `gazebo`, `gz`, `ign` 실행 파일 확인.
- `gazebo --version` 결과: Gazebo 11.10.2.
- `foxglove_bridge`, `nav2_bringup`, `slam_toolbox`, `ros_gz_sim`, `turtlebot3_gazebo` 패키지 prefix 확인.
- `ros2 launch aip_fleet_bringup central.launch.py --show-args` 성공.
- `ros2 launch aip_fleet_gazebo ign_fleet.launch.py --show-args` 성공.
- `ros2 launch aip_fleet_real fleet_main.launch.py --show-args` 성공.
- 현재 실행 중인 Docker sim과 같은 `ROS_DOMAIN_ID=42`에서 새 Ubuntu 22.04 WSL이 `/fleet/status`를 수신하는 것을 확인했다. `aip1/aip2/aip3` 모두 `healthy: true`, `offline_vehicle_ids: []`였다.

### 판단
- 이 PC에는 이제 **실로봇 대비 개발/검증용 Ubuntu 22.04 + ROS2 Humble + Gazebo/ROS-GZ 환경**이 준비됐다.
- 단, 실제 현장 주행용 중앙 PC로는 여전히 네이티브 Ubuntu 22.04가 가장 안정적이다. WSL은 네트워크가 NAT/가상 NIC이고 USB serial 전달도 별도 설정이 필요하기 때문이다.
- 남은 항목:
  - 로봇망 `192.168.0.0/24` 직접 접속 또는 WSL mirrored networking 확인.
  - 실제 LiDAR 모델에 맞는 `ydlidar_ros2_driver` 별도 설치.
  - ESP32-only 차량을 쓸 경우 `micro_ros_agent` Docker/image 또는 소스 빌드.
- USB serial 장치 사용 시 `usbipd-win` 또는 Windows COM/WSL 전달 설정.

## 2026-07-21 — 면접용 포트폴리오 현재 상태 재검증 및 GitHub 게시

### 배경
사용자가 팀프로젝트를 면접 준비용으로 사용할 수 있도록 현재 구현·실행 범위를 다시 확인하고 GitHub에 새로 게시해 달라고 요청했다.

### 확인 및 조치
- 로컬 면접용 브랜치 `codex/robot-sw-portfolio`와 GitHub remote/auth 상태를 확인했다.
- Docker sim을 현재 Compose 설정으로 재빌드·재생성해 `18080:8080`, `18765:8765` 포트 매핑을 복구했다.
- WSL 내부 dashboard HTML 응답과 `/fleet/status`를 확인했다.
  - `aip1`, `aip2`, `aip3`: `mode: autonomous`, `healthy: true`, `estop: false`
  - `offline_vehicle_ids: []`
- Docker ROS2 환경에서 `colcon test --packages-select aip_fleet_sim`을 실행해 26 tests 통과를 확인했다.
- Ubuntu 22.04 WSL에서 ROS2 Humble, Gazebo 11.10.2와 central/Gazebo/real launch의 `--show-args` 통과를 재확인했다.
- 현재 PC에서는 WSL 내부 서비스는 정상이지만 Windows `localhost:18080` 브라우저 접속이 되지 않아 WSL localhost forwarding을 추가 확인 항목으로 남겼다.
- 코드와 문서를 대조해 `cv_bridge`가 `scout_localizer_node.py`에서 사용된다는 사실을 확인하고, 비전/기술 스택/면접 문서의 잘못된 미사용 표현을 정정했다.
- 게시 전 검색에서 과거 Wi-Fi 평문 PSK와 현재 PC 공인 IP가 문서에 남아 있음을 발견해 현재 브랜치 문서에서는 값을 제거했다. 해당 PSK는 기존 `main` 이력에도 존재하므로 별도 회전과 이력 정리를 권장한다.

### 판단
- GitHub 제출 가능 범위는 Docker 2D sim, ROS2 상태/제어 계약, 웹관제 구조, 비전·열화상 연동 코드, 문서와 데모 자료다.
- 실차 3대 장시간 군집 주행, 물리 E-Stop end-to-end, YOLO 현장 성능, 일부 custom driver 완성도는 계속 `확인 필요`로 유지한다.
- Windows 브라우저 데모는 면접 전 별도 사전 점검이 필요하다.
- 초기 대응으로 `codex/robot-sw-portfolio`를 원격에 push하고 `main` 대상 Draft PR #11을 생성했으나, 다음 날 사용자의 신규 저장소 요청을 재확인한 뒤 폐기했다.

## 2026-07-22 — PR 방식 철회 및 신규 포트폴리오 저장소 게시

### 배경
사용자가 기존 팀 저장소의 PR이 아니라, 면접 제출용 코드를 별도의 새 GitHub 저장소에 직접 업로드해 달라는 의도를 명확히 했다.

### 확인 및 조치
- 잘못 생성한 `Mark2AC/aip-swarm-ws`의 Draft PR #11을 닫고 원격 `codex/robot-sw-portfolio` 브랜치를 삭제했다.
- 기존 CI 실패가 운영 코드가 아니라 오래된 supervisor 테스트와 현재 메시지 규약의 불일치에서 발생한 것을 확인했다.
  - `FleetHeartbeat.vehicle_id` 기대값을 실제 필드인 `robot_id`로 수정했다.
  - E-Stop 해제 상태를 주기적으로 `False`로 재발행하는 현재 동작을 검증하도록 테스트를 수정했다.
- 차량 자체 SW는 변경하지 않았다.
- Docker ROS2 Humble 환경에서 CI 대상 6개 패키지를 빌드하고, supervisor 30개와 simulation 26개 등 총 56개 테스트가 모두 통과함을 확인했다.
- 공개 대상 추적 파일 397개(약 5.39 MiB)를 `git archive`로 내보내 기존 `.git` 이력 없이 새 저장소를 구성했다.
- 공개 전 고신뢰도 시크릿 패턴과 secret/env 파일 포함 여부를 다시 검사했으며, 실제 시크릿 파일은 포함되지 않았다.
- 새 공개 저장소 `spongebobDG/aip-swarm-portfolio`를 만들고 단일 초기 커밋을 `main`에 직접 push했다. PR은 생성하지 않았다.
- GitHub Actions `colcon build & test` run 29882072441에서 빌드, 56개 테스트, patrol plan YAML 검증이 모두 성공했다.

### 판단 및 주의
- 면접 제출용 기준 저장소는 `https://github.com/spongebobDG/aip-swarm-portfolio`다.
- 공개 저장소는 새 이력으로 생성했기 때문에 기존 팀 저장소의 과거 커밋 이력을 포함하지 않는다.
- 과거 팀 저장소 이력에 노출됐던 Wi-Fi PSK는 새 저장소에 포함되지 않았지만, 자격 증명 회전과 기존 저장소 이력 정리는 별도 보안 작업으로 남는다.
- 실차 장시간 주행과 Windows 브라우저의 WSL localhost forwarding은 기존과 같이 확인 필요 상태다.

## 2026-07-22 — 면접용 프로젝트 영상 추가

### 배경
사용자가 순찰 영상과 프로젝트 종합 영상을 면접용 GitHub 저장소에 추가해 달라고 요청했다.

### 확인 및 조치
- 사용자 제공 원본 2개의 크기와 재생시간을 확인했다.
  - `aip순찰.mp4`: 약 69.7 MiB, 5분
  - `aip종합영상.mp4`: 약 66.7 MiB, 4분 44초
- 원본 파일은 변경하지 않고 각각 `docs/videos/aip_patrol.mp4`, `docs/videos/aip_project_overview.mp4`로 복사했다.
- 일반 Git 이력의 대용량 증가를 막기 위해 `docs/videos/*.mp4`를 Git LFS 추적 대상으로 지정했다.
- README Demo 표에 두 영상의 용도, 재생시간과 링크를 추가했다.

### 판단
- 두 영상은 면접관이 README에서 바로 찾을 수 있는 시연 자료로 사용한다.
- 영상의 실차·기능 범위는 영상 자체와 기존 문서에서 확인되는 수준으로만 설명하고, 미검증 기능을 구현 완료로 표현하지 않는다.
