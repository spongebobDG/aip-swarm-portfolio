# AIP Swarm 개발 타임라인

이 문서는 AIP Swarm 프로젝트의 전체 개발 이력을 시간 순으로 정리한 기록입니다.
발생한 문제, 근본 원인 분석, 적용된 수정 방법을 포함합니다.

---

## 목차

1. [2026-04-20 — 초기 스캐폴딩 (Windows)](#2026-04-20--초기-스캐폴딩-windows)
2. [2026-04-22 — Ubuntu 환경 이전 및 코드 리뷰](#2026-04-22--ubuntu-환경-이전-및-코드-리뷰)
3. [2026-04-22 — 보안 감사 및 즉시 완화 조치](#2026-04-22--보안-감사-및-즉시-완화-조치)
4. [2026-04-23 — 기능 완성 및 설계 확정](#2026-04-23--기능-완성-및-설계-확정)
5. [2026-04-24 — Ignition Fortress Phase-1 구축](#2026-04-24--ignition-fortress-phase-1-구축)
6. [2026-04-27 — Phase-2 통합 런치 + 버그 수정](#2026-04-27--phase-2-통합-런치--버그-수정)
7. [2026-05-07 — AMCL 파라미터 네임스페이스 버그 + CI](#2026-05-07--amcl-파라미터-네임스페이스-버그--ci)
8. [2026-05-12 — odom TF 프레임 수정 (odom_frame_fixer)](#2026-05-12--odom-tf-프레임-수정-odom_frame_fixer)
9. [2026-05-13 — UWB shadow 모드 + 분산 군집 전환 경로](#2026-05-13--uwb-shadow-모드--분산-군집-전환-경로)
10. [2026-05-14 — UWB 검증 실행 + 근본 원인 분석](#2026-05-14--uwb-검증-실행--근본-원인-분석)
11. [2026-05-18 — odom TF 분리 현상 진단 및 수정](#2026-05-18--odom-tf-분리-현상-진단-및-수정)
12. [2026-05-20 — 자율 순찰 아키텍처 개선](#2026-05-20--자율-순찰-아키텍처-개선)
13. [2026-05-21 — 열화상 파이프라인 + MPPI + FleetDashboard](#2026-05-21--열화상-파이프라인--mppi--fleetdashboard)
14. [2026-05-22 — gz_ros2_control 첫 번째 엔티티 버그 수정](#2026-05-22--gz_ros2_control-첫-번째-엔티티-버그-수정)
15. [2026-05-22 — AMCL 맵 토픽 불일치 수정](#2026-05-22--amcl-맵-토픽-불일치-수정)
16. [2026-06-15 — 실차 bringup 모노레포 통합 (feat/real-monorepo)](#2026-06-15--실차-bringup-모노레포-통합-featreal-monorepo)
17. [2026-06-17~18 — 시뮬 최종 안정화 + 실차 버그 수정 + 대시보드 확장](#2026-06-1718--시뮬-최종-안정화--실차-버그-수정--대시보드-확장)
18. [2026-06-19 — 시뮬 검증 완료 + 실차 fleet_main 완전 구동](#2026-06-19--시뮬-검증-완료--실차-fleet_main-완전-구동)
19. [2026-06-22 — 실차 메인 AGV 통합 launch + ESP32 펌웨어 + PR 머지](#2026-06-22--실차-메인-agv-통합-launch--esp32-펌웨어--pr-머지)
20. [2026-06-22 — 차량 네임스페이스 전면 변경 (aip1/aip2/aip3)](#2026-06-22--차량-네임스페이스-전면-변경-aip1aip2aip3)
21. [2026-06-22 — 관제 웹 UI 네임스페이스 반영 + 미구현 버그 수정](#2026-06-22--관제-웹-ui-네임스페이스-반영--미구현-버그-수정)

---

## 2026-04-20 — 초기 스캐폴딩 (Windows)

### 핵심 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| RMW | `rmw_fastrtps_cpp` + Discovery Server | Wi-Fi 환경에서 multicast 불안정. Zenoh는 향후 전환 옵션으로 유보 |
| ESP32 브릿지 | micro-ROS Agent (UDP4) | ROS2 토픽 계약 유지 → Pi/Jetson 업그레이드 시 동일 네임스페이스 |
| ROS_DOMAIN_ID | 42 (전 스택 통일) | 환경변수화는 H9 finding으로 Phase-2 보안 시 적용 |
| 대시보드 | Foxglove Studio + 커스텀 TS 패널 | 3D·이미지·다차량 동시 뷰 + TypeScript API 유연성 |
| 안전 우선순위 | HW-EStop(100) > estop_lock(90) > central(80) > fleet_coord(50) > autonomy(10) | estop_lock이 central보다 높은 이유: supervisor assert 후 운영자 실수로 풀리지 않아야 함 |

### 생성된 패키지
- `aip_fleet_msgs` — 메시지 정의
- `aip_fleet_supervisor` — 차량 감시 + estop 제어
- `aip_fleet_sim` — numpy 레이캐스팅 2D 시뮬
- `aip_fleet_bringup` — 런치 진입점
- `aip_fleet_foxglove_panels` — Foxglove TS 패널

---

## 2026-04-22 — Ubuntu 환경 이전 및 코드 리뷰

### 발견된 이슈

| 이슈 | 상태 | 조치 |
|---|---|---|
| git 미초기화 → `.gitignore` 무효 | ❌ | `git init` + `main` 브랜치 + 초기 커밋 |
| `.bashrc`에 install/ source 미등록 | ❌ | `source ~/aip_swarm_ws/install/setup.bash` 추가 |
| Node.js 미설치 → Foxglove 패널 빌드 불가 | ⚠️ | 사용자 sudo 필요 (`curl nodesource | sudo bash`) |
| T1 LiDAR 루프 버그 | 코드 리뷰 결과 이미 정상 | 버그 없음 확인, `pending_tasks.md` 완료 처리 |

### 주요 완료 (B3)

**B3 — twist_mux 런치 통합**

- **문제**: `estop_lock`이 twist_mux 없이는 차량 모션을 실제로 차단하지 못함
- **수정**:
  - `config/twist_mux_vehicle.yaml` 신규 (상대 토픽, PushRosNamespace 자동 적용)
  - `central.launch.py`: OpaqueFunction으로 scout별 twist_mux 추가
  - `fleet_sim.launch.py`: 차량 루프에 PushRosNamespace + twist_mux 추가

---

## 2026-04-22 — 보안 감사 및 즉시 완화 조치

### 보안 감사 결과

총 **36건** (Critical 6, High 10, Medium 9, Low 9). 근본 문제: 신뢰 경계 없음 — "Wi-Fi 침투 = 전 토픽 권한".

### 즉시 적용 (운영 영향 최소화 원칙)

| Finding | 조치 | 파일 |
|---|---|---|
| C6 watchdog 히스테리시스 | `OFFLINE_CONFIRM_COUNT=3` 추가 (단발 지터로 인한 오 ESTOP 방지) | `watchdog_node.py` |
| H2 Wi-Fi PSK 노출 | `secrets.ini` (gitignored)로 분리 + `.example` 제공 | `platformio.ini` |
| H3 InfluxDB 자격증명 | `.env` 외부화, `${VAR:?msg}` 미설정 시 compose 기동 실패 | `docker/central/.env` |
| H10 Foxglove wildcard | 비상 외 모든 명령 confirm, Clear E-Stop confirm 필수 | `OverridePanel.tsx`, `EStopPanel.tsx` |

### 이후 단계별 보안 분류

- **Phase 2**: 컨테이너 non-root, ESP32 set_ns 검증, ROS_DOMAIN_ID 환경변수화, YAML 스키마 검증
- **Phase 3**: WPA2-Enterprise, ESP32 secure_boot, 서명된 OTA

---

## 2026-04-23 — 기능 완성 및 설계 확정

### 완료된 기능

| 기능 | 내용 |
|---|---|
| B4 — OverridePanel HOLD-to-drive | `setInterval(100ms)` 10 Hz 스트리밍, `onMouseLeave` 정지 처리 |
| T8 — FleetHeartbeat.msg bounded | micro-ROS 정적 메모리 모델 호환: `string<=32`, `string<=64[<=8]` |
| T10 — 바인드 주소 제한 | foxglove-bridge `0.0.0.0` → `192.168.50.10` |
| T11 — 공급망 digest 고정 | docker-compose 이미지에 `@sha256:...` 추가 |
| T6 — coordinator 스켈레톤 | TF2 map-frame P-controller, V 포메이션 오프셋 계산 |
| T9 — SROS2 도입 | `sros2_policy.xml` + `sros2_init.sh` + `central.launch.py with_security` |

### 군집 설계 철학 확정

사용자 명시: "fleet(함대)이 아니라 각 차량이 독립·유기적으로 활동하는 swarm(군집)이 목표."

- `docs/VISION.md` 신규: 동등 피어 군집 목표, 세대별 로드맵
- `docs/SWARM_LOCALIZATION.md` 전면 재작성: scout=예산 제약 피어, 4단계 업그레이드 경로

---

## 2026-04-24 — Ignition Fortress Phase-1 구축

### 채택 이유

**Gazebo Ignition Fortress** (Gazebo Classic 대신): `ros2_control` 하드웨어 인터페이스 추상화 — 시뮬(`gz_ros2_control/GazeboSimSystem`) ↔ 실차(`aip_hardware/MainAGVHardware`) 플러그인만 교체, 나머지 스택 동일 유지.

### 실행 중 발견된 버그 (8건)

| # | 파일 | 문제 | 수정 |
|---|---|---|---|
| 1 | `fleet_world.sdf` | 존재하지 않는 `gpu-lidar-sensor-system` 플러그인 | 제거 (sensors-system이 처리) |
| 2 | `main_agv.urdf.xacro` | `type="gpu_lidar"` — GPU 없는 환경에서 실패 | `type="lidar"` (CPU ray-cast)로 변경 |
| 3 | `main_agv.urdf.xacro` | `ign_ros2_control::IgnROS2ControlPlugin` 클래스명 불일치 | `gz_ros2_control::GazeboSimROS2ControlPlugin`으로 수정 |
| 4 | `spawn_vehicle.launch.py` | controller YAML 최상위 키 네임스페이스 없어 타입 미인식 | `/**:` 와일드카드로 변경 |
| 5 | `spawn_vehicle.launch.py` | spawner가 controller type 미인식 | `--controller-type` 플래그 추가 |
| 6 | `spawn_vehicle.launch.py` | `odom_frame_id`에 네임스페이스 중복 (`peer_1/peer_1/odom`) | `odom` (비네임스페이스, 컨트롤러가 자동 prefix) |
| 7 | `cmd_relay.py` | `diff_drive_controller/cmd_vel` 발행 → subscriber 없음 | `cmd_vel_unstamped`로 변경 |
| 8 | `spawn_vehicle.launch.py` | `/peer_N/odom` 토픽 없음 | `topic_tools relay` 노드 추가 |

### Phase-1 최종 결과

| 항목 | 결과 |
|---|---|
| 3대 스폰 (peer_1/2/3) | ✅ |
| `diff_drive_controller` active | ✅ |
| `map → peer_N/odom → peer_N/base_link` TF 체인 | ✅ (static TF로) |
| teleop 이동 (peer_1) | ✅ |

---

## 2026-04-27 — Phase-2 통합 런치 + 버그 수정

### 주요 추가 사항

- `fleet_phase2.launch.py` 신규: 타이밍 조율 통합 런치
- `sim_peer_sensing_node.py`: TF 기반 차량 간 거리 시뮬 + Gaussian 노이즈(σ=0.05m)
- `uwb_localizer_node.py`: 가중 Gauss-Newton 협력 측위 (SLAM w=1.0, 앵커 w=1.0, 협력 추정 w=0.5)

### 발생된 버그 (3건)

**버그 1 — twist_mux 미설치**

- **증상**: `"package 'twist_mux' not found"` → launch 전체 cascade 종료
- **수정**: `sudo apt install ros-humble-twist-mux` (사용자 수동 설치)

**버그 2 — peer_1 diff_drive_controller FATAL 로드 실패**

- **증상**: `[FATAL] peer_1.ddc_spawner: Failed loading controller diff_drive_controller`
- **근본 원인**: gz_ros2_control이 state interface 생성 후 command interface 생성 순서로 동작. 3s 타이밍에서 command interface 미준비 → DDC 로드 실패. peer_2/3는 0.8/1.6s 늦게 실행되어 성공
- **수정** (`spawn_vehicle.launch.py`): spawner 딜레이 `3.0s → 6.0s`, `--controller-manager-timeout 30` 추가

**버그 3 — coordinator setup.cfg 누락**

- **증상**: `ros2 run aip_fleet_coordinator coordinator_node` → `No executable found`
- **근본 원인**: ament_python 패키지에서 `setup.cfg` 미존재 시 console_scripts가 `install/bin/`(ros2 run 미탐색 경로)에 설치됨
- **수정**: `setup.cfg` 신규 생성 (`script_dir=$base/lib/aip_fleet_coordinator`)

---

## 2026-05-07 — AMCL 파라미터 네임스페이스 버그 + CI

### 버그 — AMCL 파라미터 미적용

- **증상**: AMCL 노드가 active 상태이지만 파라미터가 전혀 적용되지 않음
- **근본 원인**: `PushRosNamespace("peer_2")` 안에 배치된 노드는 `/peer_2/amcl` 경로에 위치하는데, 파라미터 YAML의 최상위 키가 bare `amcl:`이면 `/amcl`(루트 ns)에만 매칭됨
- **수정**:

  | 파일 | 변경 |
  |---|---|
  | `amcl.yaml` | `amcl:` → `/${vehicle_id}/amcl:` |
  | `slam_toolbox_online.yaml` | `slam_toolbox:` → `/${vehicle_id}/slam_toolbox:` |
  | `nav2_params.yaml` | 모든 노드 FQDN, `voxel_layer` → `obstacle_layer` (Humble 호환) |

### GitHub Actions CI 구성

`.github/workflows/colcon.yml`:
- 트리거: main push / PR
- 선행 빌드: `aip_fleet_msgs` → 의존 패키지 순차 빌드
- 테스트: `aip_fleet_supervisor` 23개 pytest 단위 테스트
- 제외: Ignition 의존 패키지 (CI 환경 미지원)

---

## 2026-05-12 — odom TF 프레임 수정 (odom_frame_fixer)

### 문제

`diff_drive_controller`가 `enable_odom_tf: True`여도 TF를 `odom → base_link`(비네임스페이스)로 발행. slam_toolbox와 AMCL은 `peer_N/odom → peer_N/base_link` TF를 요구 → TF 없음 → SLAM 드리프트, AMCL 실패.

### 해결책 — odom_frame_fixer.py

```
diff_drive_controller/odom (frame_id='odom')
    ↓ odom_frame_fixer.py
diff_drive_controller/odom_corrected (frame_id='peer_N/odom')
    ↓
EKF (publish_tf: true)
    ↓
peer_N/odom → peer_N/base_link TF 발행
```

### 변경 파일

| 파일 | 변경 |
|---|---|
| `scripts/odom_frame_fixer.py` | 신규: frame_id 교정 relay 노드 |
| `ekf_vehicle.yaml` | `odom0` → `odom_corrected`, `publish_tf: true` |
| `spawn_vehicle.launch.py` | `enable_odom_tf: False`, fixer t=7s에 추가 |
| `CMakeLists.txt` | `odom_frame_fixer.py` install 등록 |

### AMCL 관련 동시 수정 (2026-05-12)

**버그 1 — AMCL이 `/peer_N/map` 구독**

- **근본 원인**: `PushRosNamespace("peer_2")` 안에서 상대 토픽 `map` → `/peer_2/map`으로 해석. slam_toolbox는 `/map`(절대)으로 발행 → 구독자 불일치 → 맵 미수신
- **수정** (`nav_follower.launch.py`): `remappings=[('map', '/map')]` 명시

**버그 2 — AMCL set_initial_pose 누락**

- **근본 원인**: `initial_pose_x/y/a`는 `set_initial_pose: true`일 때만 적용. 없으면 `initial_pose_is_known_ = false` → `laserReceived()` 즉시 리턴 → TF 영구 미발행
- **수정** (`nav_follower.launch.py` + `amcl.yaml`): `set_initial_pose: true` 추가

**버그 3 — 코디네이터 정지 (추종 도달 불가)**

- **근본 원인**: `v = kp_lin * dist * cos(alpha)` 수식에서 alpha가 크면 cos(alpha)→0 → 선속도 소멸 → 리더 이동 시 새 타겟 → 반복 → 도달 불가
- **수정** (`coordinator_node.py`): 두-단계(two-phase) 제어기
  - `|alpha| > 1.05 rad`: 제자리 회전만, 선속도=0
  - `|alpha| ≤ 1.05 rad`: 전진 `v = kp_lin * dist` (cos 감쇠 없음)
  - `goal_tolerance`: 0.05 → 0.15 m (dead-band 확장, 진동 방지)

---

## 2026-05-13 — UWB shadow 모드 + 분산 군집 전환 경로

### UWB shadow 모드

**문제**: AMCL과 UWB localizer가 동일 TF(`map → peer_N/base_link`)를 경쟁 발행

**해결**: UWB localizer가 `peer_N/base_link_uwb_est` 프레임으로 발행 → AMCL과 공존, 오차 비교 가능

### 독자 제어 전환 경로 (설계)

| 단계 | 핵심 변경 |
|---|---|
| 1 | coordinator가 Twist 대신 Nav2 `NavigateToPose` action 호출 |
| 2 | `task_allocator_node`: 웨이포인트 목록 → 최근접 차량 배분 |
| 3 | 중앙 코디네이터 제거, 경매 기반 `/fleet/bid_msg` 토픽 |
| 4 | BehaviorTree.CPP + Patrol/Search/Rendezvous 행동 모듈 |

---

## 2026-05-14 — UWB 검증 실행 + 근본 원인 분석

### 검증 결과

```
peer_2: AMCL TF missing (uwb_est at (-1.5, 1.0))  ← AMCL 기동 실패
peer_3: AMCL(-0.007,-1.002)  UWB(-0.24~-0.36, -0.25~-0.47)  err=0.6~0.87m → 0.242m
```

### 발견 및 수정 (4건)

| 파일 | 수정 내용 |
|---|---|
| `uwb_accuracy_check.py`, `odom_frame_fixer.py` | 실행 권한 누락 (`chmod +x`) |
| `uwb_localizer_node.py` | `initial_x/y/yaw` 파라미터 추가 — odom(0,0) 초기화 시 d=0 특이점 방지 |
| `fleet_phase2.launch.py` | `_SPAWN_POS` 딕셔너리로 스폰 좌표 → `initial_x/y` 주입 |
| `sim_peer_sensing_node.py` | `_lookup()` UWB TF fallback 추가 |

### 오차 원인 및 대책

- **원인**: 앵커 1개만 유효(peer_2 AMCL 불능) + 단거리 이동(odom drift ≈ 0 < UWB σ=5cm)
- **대책**: `uwb_trigger_dist_m` 파라미터 추가 — odom 누적 이동거리 초과 후에만 UWB 보정 실행 (실차 권장값 0.5m)

---

## 2026-05-18 — odom TF 분리 현상 진단 및 수정

### 증상

RViz 관찰 결과: **각 peer의 odom TF 프레임이 차량 모델과 공간적으로 분리됨.** odom 프레임 원점이 차량 스폰 위치가 아닌 맵 (0,0)에 고정.

### 근본 원인 분석

```
Ignition diff_drive_controller → 절대 월드 좌표 odom 출력
    (스폰 위치 (-1.5,+1.0)이 t=0 pose값)
        ↓
odom_frame_fixer → frame_id만 교정, pose는 그대로 통과
        ↓
EKF: odom0_relative: false → 절대 좌표로 해석
        ↓
peer_N/odom → base_link = (-1.5,+1.0) at spawn
        ↓
AMCL: map → peer_N/odom = (0,0)으로 세팅
        ↓
odom 프레임이 맵 원점에 고정됨 (차량 위치와 분리)
```

### 수정

| 파일 | 변경 | 이유 |
|---|---|---|
| `ekf_vehicle.yaml` | `odom0_relative: false` → `true` | EKF가 첫 메시지를 기준점으로 해석, 이후 상대 델타만 적분 |
| `scripts/odom_frame_fixer.py` | 초기 pose 영점화 추가 (T_rel = T0_inv · T1) | 절대 좌표 → 상대 좌표 변환, EKF 수정과 이중 안전장치 |

### SLAM 맵 피어 바디 오염 문제 (분석)

```
t= 2.8s  peer_2 스폰 (Ignition에 물리적 존재)
t= 3.6s  peer_3 스폰
t=16.0s  SLAM 시작 → peer_1 LiDAR가 peer_2/3 바디 스캔 시작
t=55.0s  AMCL 시작 (39초간 peer_2/3 바디가 맵에 정적 장애물로 기록됨)
```

AMCL 파티클이 불일치를 설명하는 오프셋된 위치로 수렴 → 계통적 위치 오차 발생.

**파라미터로 내성 향상** (`amcl.yaml`): `z_hit: 0.7→0.6`, `z_rand: 0.2→0.3`, `sigma_hit: 0.1→0.15m`

**장기 근본 해결책 (미적용)**:
- peer_2/3를 SLAM 완료(t≈52s) 후 스폰
- `laser_filters`로 근거리(<0.8m) 레이 제거
- Ignition visibility_flags로 차량 충돌 geometry를 LiDAR 비감지 그룹으로 설정

---

## 2026-05-20 — 자율 순찰 아키텍처 개선

### 주요 변경

| 항목 | 변경 내용 |
|---|---|
| 순찰 시퀀스 | peer_1 전체 맵 탐색 완료 후 peer_2/3 시작 (t=155s/163s) |
| `leader_nav.launch.py` 신규 | peer_1 전용 Nav2 (AMCL 없음, slam_toolbox TF 사용) |
| AMCL 시작 시간 | peer_2: 55→155s, peer_3: 63→163s (peer_1 탐색 완주 대기) |
| patrol start_delay | peer_2/3: 15→40s (AMCL 수렴 대기) |
| base_footprint TF 추가 | identity TF 발행 (RViz 경고 해결) |
| `docs/PROJECT_OVERVIEW.md` 신규 | 전체 설계·구현·한계 종합 문서 |

---

## 2026-05-21 — 열화상 파이프라인 + MPPI + FleetDashboard

### 열화상 파이프라인 전체 흐름

```
scenario_manager_node.py  — /sim/set_scenario → /sim/heat_sources (2 Hz)
        ↓
sim_thermal_node.py       — TF + 열원 목록 → /<vid>/thermal_raw (8 Hz)
        ↓
patrol_monitor_node.py    — 임계값 필터 + TF map_position → /fleet/alerts
        ↓
alert_visualizer_node.py  — /fleet/alerts → /fleet/alert_markers (RViz MarkerArray)
```

### MPPI 통합 검증 결과

| 검사 항목 | 결과 |
|---|---|
| MPPI 설정 10항목 (plugin, batch_size, time_steps, critics 등) | ALL PASS |
| patrol_monitor `_estimate_map_position` 단위 테스트 11개 | ALL PASS |
| alert_visualizer_node 마커 로직 10항목 | PASS (DELETEALL 추가 후) |
| 전체 사전 비행 검사 14항목 | ALL PASS |
| `aip_fleet_perception`, `aip_fleet_autonomous` 재빌드 | SUCCESS |

**MPPI 총 샘플**: 2,000 × 56 = 112,000 (DWB 대비 280×), 예측 지평선 2.8초

### FleetDashboard Foxglove 패널

신규 패널 (`FleetDashboard/src/FleetDashboard.tsx`):
- 차량 상태 카드: `/fleet/status` → peer_1/2/3 상태배지·배터리·CPU·행동태그
- 차량별 제어: PAUSE/RESUME/CLEAR/ESTOP 버튼
- 시나리오 제어: 6종 시나리오 버튼
- 탐색 커버리지: `/fleet/coverage_pct` 바
- 열화상 경보: `/peer_N/perception_alert` 목록

---

## 2026-05-22 — gz_ros2_control 첫 번째 엔티티 버그 수정

### 증상

`aip_auto_patrol` 실행 시 peer_1 Controller Manager(CM)가 시작되지 않음. peer_2/3 CM은 정상.

### 근본 원인 분석

**gz_ros2_control-system 0.7.19 싱글톤 특성**: 플러그인이 Ignition 내에서 엔티티를 **순차 처리**. 첫 번째 엔티티의 `Configure()` 완료 전까지 이후 엔티티의 `Configure()` 실행 불가.

```
[시뮬 시작]
    ↓
peer_1이 첫 번째 엔티티로 처리됨
    ↓
rclcpp 초기화 경쟁 조건 → peer_1 CM 노드 생성 실패
    ↓
Configure() fast fail → 큐 해제 → peer_2, peer_3 처리 (성공)
    ↓
결과: peer_1 CM 없음, peer_2/3 CM 있음
```

### 1차 수정 시도 — RSP 네임스페이스 오류 (실패)

- 워밍업 RSP를 `name='robot_state_publisher'`에 namespace 없이 생성 → 노드가 `/robot_state_publisher`에 위치
- 워밍업 플러그인은 `/gz_warmup/robot_state_publisher`를 탐색 → RSP 발견 불가 → 무한 대기 루프
- **결과**: 워밍업 Configure()가 영구 블록 → peer_1/2/3 전혀 처리 안 됨

### 최종 수정 — 워밍업 모델 + 올바른 RSP 네임스페이스

**`ign_fleet.launch.py` 변경**:

```python
# 워밍업 RSP: namespace='gz_warmup' 필수
warmup_rsp = Node(
    package='robot_state_publisher',
    namespace='gz_warmup',              # → /gz_warmup/robot_state_publisher
    ...
)
# 워밍업 스폰: /gz_warmup/robot_description 토픽 참조
warmup_spawn = Node(
    arguments=[
        '-topic', '/gz_warmup/robot_description',
        '-x', '-45', '-y', '-45',       # 맵 외곽 스폰
    ]
)
actions.append(TimerAction(period=1.0, actions=[warmup_rsp, warmup_spawn]))

# 차량 스폰 딜레이 조정
delay = 3.5 + idx * 0.8  # peer_1=3.5s (기존 2.0s), peer_2=4.3s, peer_3=5.1s
```

### 검증 결과

```
/gz_warmup/controller_manager   ← 워밍업 첫 번째 엔티티 처리 완료
/peer_1/controller_manager      ← 두 번째 엔티티, 정상 처리
/peer_2/controller_manager      ← 정상
/peer_3/controller_manager      ← 정상
joint_state_broadcaster: active (peer_1/2/3)  ✅
diff_drive_controller:   active (peer_1/2/3)  ✅
```

---

## 2026-05-22 — AMCL 맵 토픽 불일치 수정

### 증상

`aip_auto_patrol` 실행 후 peer_2/3의 `map → peer_N/odom` TF가 발행되지 않음.
TF 트리에서 `peer_2/odom`, `peer_3/odom`의 parent가 없음 → RViz에서 odom 프레임이 맵과 단절, 위치 오차 큼.

### 근본 원인 분석

```
slam_toolbox (namespace=peer_1)
    → map 토픽을 /peer_1/map으로 발행 (네임스페이스 안에서 상대 발행)

nav_follower.launch.py AMCL
    → remappings=[('map', '/map')]  # 전역 /map 구독
    → /map 토픽이 존재하지 않음
    → AMCL이 맵 수신 불가 → 수렴 불가 → TF 미발행
```

`slam_leader.launch.py` 주석: "The leader builds the shared /map" — 의도는 전역 발행이었으나 리맵 누락.

### 수정

**`src/aip_fleet_nav/launch/slam_leader.launch.py`**:

```python
remappings=[
    ('scan', f'/{vid}/scan'),
    ('map', '/map'),           # 추가: 전역 /map으로 발행
    ('map_metadata', '/map_metadata'),  # 추가
],
```

### 수정 전후 비교

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| slam_toolbox map 발행 토픽 | `/peer_1/map` | `/map` |
| AMCL map 구독 토픽 | `/map` (수신 없음) | `/map` (수신 성공) |
| peer_2/3 AMCL 수렴 | ❌ | ✅ (예상) |
| `map → peer_N/odom` TF | ❌ | ✅ (예상) |

---

---

## 2026-05-22 — SLAM 오염 방지 + AMCL 수렴 타이밍 수정

### 문제 1: TF 루프 (`base_link ↔ base_footprint`)

**증상**: peer_3 스폰 후 Nav2 시작 시 `tf tree is invalid because it contains a loop` 오류 발생 → peer_3 플래너 작동 불가.

**근본 원인**: `spawn_vehicle.launch.py`에 있던 `static_transform_publisher`가 `base_link → base_footprint` TF를 발행. 동시에 URDF의 `base_joint`(parent=`base_footprint`, child=`base_link`)를 `robot_state_publisher`가 `base_footprint → base_link`로 발행. 두 TF가 서로 역방향 루프를 형성.

**수정**: `spawn_vehicle.launch.py`의 `base_footprint_tf` 노드 완전 제거. URDF RSP가 이미 올바른 방향으로 발행하고 있었으므로 추가 TF 불필요.

---

### 문제 2: peer_2/3 차체가 peer_1 맵에 영구 장애물로 기록

**증상**: peer_2 Nav2 시작 시 `Starting point is in lethal space` 오류. peer_2가 자신이 스폰된 좌표를 lethal로 인식.

**근본 원인**: peer_2/3가 t≈4s에 스폰되어 peer_1 SLAM이 진행되는 t=4~155s 동안 150초간 같은 위치에 정지. peer_1 LiDAR가 차체를 수백 번 스캔해 해당 셀 `P(occupied)`가 최대치 수렴 → 맵에 영구 벽으로 기록.

**수정**: `ign_fleet.launch.py`에 `follower_spawn_delay` LaunchArgument 추가. `fleet_autonomous.launch.py`에서 `follower_spawn_delay:='181'` 전달 → peer_2/3 스폰 시각: t≈185s (peer_1 순찰 완료 후).

```python
# ign_fleet.launch.py
def _spawn_vehicles(context, *args, **kwargs):
    extra = float(LaunchConfiguration('follower_spawn_delay').perform(context))
    for idx, (vid, sx, sy, syaw) in enumerate(_FLEET):
        delay = 3.5 if idx == 0 else 3.5 + idx * 0.8 + extra
```

---

### 문제 3: AMCL `createLaserObject` 5Hz 반복 → 파티클 수렴 불가

**증상**: peer_2 Nav2 로그에 `Received a 369 X 271 map / createLaserObject` 가 초당 5회 반복. peer_2 위치 추정이 발산하며 원점과 동떨어진 위치로 수렴.

**근본 원인**: `map_update_interval: 0.2` → slam_toolbox가 5Hz로 OccupancyGrid 발행. AMCL은 새 맵 메시지 수신마다 `createLaserObject()` 호출 → likelihood field 재초기화 → 파티클이 수렴하기 전에 리셋 반복.

**수정**: `slam_toolbox_online.yaml`에서 `map_update_interval: 0.2 → 5.0 → 30.0`으로 단계적 상향.

```yaml
map_update_interval: 30.0   # AMCL createLaserObject 재호출 억제
```

**결과**: peer_2 AMCL 수렴 성공. peer_3는 타이밍 추가 조정으로 해결.

---

### 타이밍 파라미터 최종값

| 파라미터 | 수정 전 | 수정 후 | 파일 |
|---|---|---|---|
| `follower_spawn_delay` | `0.0` | `181` | `fleet_autonomous.launch.py` |
| `_NAV_START['peer_2']` | `155.0` | `200.0` | `fleet_autonomous.launch.py` |
| `_NAV_START['peer_3']` | `163.0` | `210.0` | `fleet_autonomous.launch.py` |
| `map_update_interval` | `0.2` | `30.0` | `slam_toolbox_online.yaml` |

---

## 2026-05-22 — 이벤트 기반 자율 탐색 아키텍처 도입

### 배경

타이머 기반(`_NAV_START`) 팔로워 시작은 맵 크기나 순찰 경로가 바뀔 때마다 수동 조정이 필요한 구조적 한계를 가짐. 맵 완성도를 실시간 감시하고 완성 시 팔로워를 자동 기동하는 이벤트 기반 아키텍처로 전환.

### 설계 원칙

```
기존: 고정 타이머(t=200/210s) → 팔로워 Nav2 시작
신규: explore_lite 프론티어 소진 + 커버리지 ≥ 70% → /fleet/map_ready → 팔로워 Nav2 시작
```

### 추가된 컴포넌트

#### `map_readiness_node.py` (신규)

`/map` OccupancyGrid를 구독해 `known 셀 / 전체 셀` 비율을 계산. `coverage_threshold(70%)` + `min_known_cells(3000)` 조건 충족 시 `/fleet/map_ready(Bool, TRANSIENT_LOCAL)` 발행.

#### `follower_trigger_node.py` (신규)

`/fleet/map_ready` 수신 → 각 팔로워의 `controller_manager` 서비스 등록 확인 → `ros2 launch autonomous_nav.launch.py` + `ros2 run patrol_node` 순차 실행. peer_3는 10s 스태거.

```
파라미터:
  with_patrol:       순찰 노드 동반 기동 여부
  waypoints_peer_2/3: 순찰 웨이포인트 flat list
  patrol_start_delay: Nav2 기동 후 patrol_node 시작 대기(s)
```

#### `explore_lite` (외부, m-explore-ros2)

프론티어 탐색 알고리즘으로 peer_1의 `navigate_to_pose` 액션에 목표를 순차 전달. 접근 가능한 전 구역의 프론티어를 소진하면 자동 종료.

```
프론티어 정의: Free 셀 + 인접 Unknown 셀 존재
소진 조건:    모든 접근 가능한 Unknown 셀이 Free/Occupied로 전환됨
```

설치:
```bash
cd ~/aip_swarm_ws/src && git clone https://github.com/robo-friends/m-explore-ros2.git
colcon build --packages-select explore_lite_msgs
colcon build --packages-select explore_lite
```

#### `patrol_node.py` (수정)

`/map` 구독 추가. 웨이포인트 전송 전 `_is_waypoint_known()` 체크 — 해당 셀이 Unknown(-1)이면 건너뜀.

```python
def _is_waypoint_known(self, x, y) -> bool:
    idx = my * m.info.width + mx
    return m.data[idx] >= 0   # -1 = unknown
```

### 브링업 타임라인 (신규)

| 시각 | 이벤트 |
|---|---|
| t=0s | Ignition 기동, peer_1 스폰 |
| t=14s | twist_mux × 3 |
| t=16s | SLAM (slam_toolbox) + sim_peer_sensing + **map_readiness_node** 시작 |
| t=22s | peer_1 Nav2 (leader_nav) + **explore_lite** + **follower_trigger_node** 시작 |
| t=70s | coverage_tracker_node (선택) |
| t≈185s | peer_2/3 스폰 (CM + EKF 준비 시작) |
| t=맵완성 | `/fleet/map_ready` 발행 |
| 즉시 | follower_trigger_node → CM 확인 → peer_2 Nav2 기동 |
| +10s | peer_3 Nav2 기동 |

### 변경 파일 목록

| 파일 | 변경 내용 |
|---|---|
| `aip_fleet_autonomous/map_readiness_node.py` | 신규 |
| `aip_fleet_autonomous/follower_trigger_node.py` | 신규 |
| `aip_fleet_autonomous/patrol_node.py` | 맵 필터링 추가 |
| `fleet_autonomous.launch.py` | explore_lite 추가, 팔로워 TimerAction 제거 |
| `setup.py` | 신규 노드 2개 entry_points 등록 |
| `package.xml` | `std_msgs`, `nav_msgs` 의존성 추가 |

---

---

## 2026-06-15 — 실차 bringup 모노레포 통합 (feat/real-monorepo)

### 배경

시뮬 스택(`aip_fleet_gazebo`, `aip_fleet_autonomous`)의 구조를 그대로 유지하면서, 실차 전용 bringup 레이어를 동일 모노레포에 추가하는 `feat/real-monorepo` 브랜치 개시. CI(`fix(ci): pin pytest<9`) 수정과 함께 시작.

### 추가 패키지: `aip_fleet_real`

```
src/aip_fleet_real/
├── launch/
│   ├── fleet_real.launch.py      — 전 차량 통합 런치 진입점
│   ├── main_agv.launch.py        — aip1 (FIT0186): SLAM + Nav2 + patrol
│   ├── turtlebot3.launch.py      — aip2 (TB3 Burger): SLAM + Nav2 + patrol
│   ├── turtlebot3_sim.launch.py  — aip2 Gazebo Classic 단독 시뮬
│   └── custom_vehicle.launch.py  — aip3 (STS3215): SLAM + Nav2
├── config/
│   ├── main_agv/{nav2, slam_toolbox, patrol}.yaml   — YDLidar TG15, DWB, RPi4B 최적화
│   ├── turtlebot3/{nav2, slam_toolbox, patrol, twist_mux, nav2_sim, …}.yaml
│   └── custom_vehicle/{nav2, slam_toolbox}.yaml
└── package.xml
```

### 설계 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 시뮬/실차 분리 원칙 | 실차 config는 `aip_fleet_real/`, 시뮬은 기존 `aip_fleet_gazebo/` 유지 | 실차 `use_sim_time: false` 혼입 방지 |
| UWB 완전 배제 | 실차 launch에서 UWB 노드 포함 금지 | 2026-06-15 하드웨어 확정 시 전 차량 RPi4B LiDAR SLAM으로 결정 |
| TB3 nav2 네임스페이스 | `PushRosNamespace(ns)` + `SetRemap('/tf', '/tf')` 필수 | navigation_launch.py가 namespace를 YAML root_key로만 사용, TF 경로 불일치 방지 |
| map_topic 명시 | `global_costmap.static_layer.map_topic: /map` | slam_toolbox가 절대 `/map`으로 발행, namespaced costmap 미수신 방지 |

---

## 2026-06-17~18 — 시뮬 최종 안정화 + 실차 버그 수정 + 대시보드 확장

### 실차 nav2 버그 수정 (2026-06-17, 00eaea5 / 3c936d4)

| 파일 | 수정 내용 |
|---|---|
| `turtlebot3.launch.py` | nav2 GroupAction에 `PushRosNamespace` + `/tf`, `/tf_static` `SetRemap` 추가 |
| `nav2.yaml` | `static_layer.map_topic: /map` 추가 (절대경로 발행 대응) |
| `turtlebot3.launch.py` | `patrol_node` 실차 launch에 통합 (`/aip2/navigate_to_pose` 액션 연결) |
| `SETUP_RPI4.md` | 차량별 의존성 설치 순서 재구성 |

### 시뮬 안정화 (2026-06-18, efba200·c3b51b9·db45fe0)

| 수정 | 내용 |
|---|---|
| `behavior_server` lifecycle 포함 | peer_2/3 Nav2에서 behavior_server가 lifecycle manager에서 빠져 있어 BackUp/Spin 동작 불가 → 추가 |
| spawner 타이밍 최적화 | RTF=1.0 안정 환경에서 불필요한 대기 제거 |
| MPPI visualize 비활성 | `/trajectories` 퍼블리시를 `visualize: false`로 설정해 "10Hz 제어 루프 누락" 경고 제거 |

### 대시보드 확장 (2026-06-18, db45fe0)

- `map_static` 기본 맵 로드: 시작 시 `~/aip_maps/map_static.pgm` 자동 로드 → 실차에서 SLAM 없이도 맵 표시
- 맵 소스 실시간 전환 UI: `/map`(SLAM) ↔ `/map_static`(사전 저장) 버튼 전환, `_active_map_source` 상태 유지

### 실차 하드웨어 문서화 (2026-06-18)

- `SETUP_HARDWARE.md` 신규: 차량별 H/W 스펙, 전장 연결, 전원 체계
- `docs/hardware/`: 차량별 실제 스펙 확정 (RPi4B 전 차량, YDLidar TG15 전 차량, STS3215 서보)
- `config/network/dhcp_reservations.md`: 서브넷 192.168.0.x 최종 배정

---

## 2026-06-19 — 시뮬 검증 완료 + 실차 fleet_main 완전 구동

### 시뮬 최종 수정 (e6a8a70·83f96a9·f3ecef5)

#### peer_1 TF 단절 해결

**근본 원인**: `slam_toolbox(t=16s)`가 `EKF(t=20.5s)` 보다 4.5초 먼저 시작 → `peer_1/odom→base_link` TF 없는 상태에서 SLAM 실행 → transform_timeout 반복.

**수정**: `fleet_autonomous.launch.py`에서 slam_toolbox 시작 시각 `t=16s → t=21s` (EKF 이후 0.5s).

#### lethal space 루프 해결

**증상**: peer_1이 코너 frontier에서 LETHAL 고착 → BackUp 143회 반복 실패.

**수정 3종**:
1. `navigate_w_collision_recovery.xml`: ClearAll + Spin(1.57 rad) + BackUp 단계 추가 (코너 탈출 회전)
2. `explore_lite`: `min_frontier_size 0.5→0.75m`, `progress_timeout 60→30s`
3. `nav2_full.yaml` local_costmap: `footprint_padding 0.05 제거` (LETHAL 반경 0.155m→0.105m)

**검증 결과 (2026-06-19 headless)**:
- TF 에러 0건, 제어 루프 누락 0건
- 33회 Navigation Goal 전송, 커버리지 87.0㎡ → 135㎡ 달성

### 실차 기능 구현 (87faf57·fe28832·f9c8ed8·60639dc)

#### keepout zone 실제 동작 (87faf57)

이전까지 대시보드에서 폴리곤을 그려도 Nav2 costmap에 반영되지 않음.

**구현**:
- `keepout_zone_node.py` 신규: `/fleet/keepout_zones` JSON → 폴리곤 내부 0.05m 격자 채우기 → `/fleet/keepout_cloud` (PointCloud2, TRANSIENT_LOCAL) 1Hz 발행
- `nav2_full.yaml`: observation_sources에 `keepout_cloud` 추가 (`marking:True, clearing:False, obstacle_max_range:200m`)
- `dashboard_server.py cmd_navigate()`: ray-casting으로 목표 좌표가 금지구역 내부이면 `navigate_rejected` WS 메시지 후 Nav2 발행 차단
- `index.html`: `navigate_rejected` 수신 시 적색 toast 표시

#### 순찰 시작/정지 버튼 (fe28832)

- `patrol_node.py`: `start/stop/mode:loop` 명령 처리 + `/aip2/patrol_status` 발행
- `dashboard_server.py`: `/fleet/patrol_status` relay + `_patrol_running` 상태 캐시
- `index.html`: 버튼 색상 피드백, 차량 선택 시 캐시된 상태로 즉시 동기화

#### 도킹 위치 영속화 (f9c8ed8)

- `~/aip_maps/dock_positions.json` 저장 → WS 재접속 시 `dock_positions` 메시지로 자동 복원
- `_state_cache['dock_positions']` 등록

#### 금지구역 영속화 (60639dc)

- `~/aip_maps/keepout_zones.json` 저장 → 서버 재시작 시 자동 로드 + 신규 클라이언트 접속 시 `keepout_zones_restore` 메시지 전송

### fleet_main 완전 구동 검증 (5904e96)

RPi4B(`192.168.0.3`)에서 `fleet_main.launch.py` 구동 결과 문서화 (`docs/REAL_VEHICLE_OPERATION.md`):

| 검증 항목 | 결과 |
|---|---|
| YDLidar TG15 스캔 `/aip1/scan` | ✅ |
| serial_bridge `/dev/aip_esp32` 연결 | ✅ |
| `/aip1/autonomy_cmd_vel` → twist_mux → `/aip1/cmd_vel` → ESP32 | ✅ |
| 엔코더 피드백 L+99K/R+99K (직진 틱 차 <30) | ✅ |
| FastDDS 양방향 (Simple Discovery, 192.168.0.9:11811) | ✅ |

---

## 2026-06-22 — 실차 메인 AGV 통합 launch + ESP32 펌웨어 + PR 머지

### main_agv.launch.py 완전 구현 (66d654a·47142f4·ef9bc34)

이전까지 placeholder였던 `main_agv.launch.py`에 SLAM + Nav2(DWB) + patrol 전체 파이프라인 통합.

| 파일 | 내용 |
|---|---|
| `main_agv.launch.py` | SLAM + Nav2 + patrol + 배포 스크립트 (`scripts/deploy_main_agv.sh`) |
| `config/main_agv/nav2.yaml` | DWB 컨트롤러 (MPPI → DWB 전환, RPi4B CPU 예산), bond_timeout=0.0, batch_size=500 |
| `config/main_agv/slam_toolbox.yaml` | YDLidar TG15 파라미터, throttle_scans=2 |
| `config/main_agv/patrol.yaml` | 실좌표 교체 가능한 template |

**TF 프레임 수정** (47142f4): `aip1/odom`, `aip1/base_link` 등 네임스페이스 prefix 정합.

**RPi4B 주파수 최적화** (ef9bc34): local costmap 5→2Hz, AMCL max_beams 180→60, controller_frequency 20→10Hz.

### ESP32 펌웨어 추가 (cbc1308)

`firmware/` 디렉토리를 차량별로 분리 재구성:

```
firmware/
├── main_agv/     — FIT0186 메인 AGV (BTS7960+MG996R), Arduino IDE
│   ├── buzzer.h/cpp         — 비-블로킹 부저 상태머신 (BOOT/SINGLE/DOUBLE/ERROR)
│   ├── config.h             — BUZZER_PIN=2, BUZZER_CH=8, PKT_RESET=0x07, PKT_BEEP=0x08
│   ├── aip_firmware.ino     — setup() Buzzer::play(BOOT), loop() Buzzer::tick()
│   └── README.md            — 핀맵, 프로토콜 표, 빌드 가이드
└── scout/        — aip2/aip3 (micro-ROS over UDP), PlatformIO  ← 구 scout_microros/ rename
    └── README.md            — aip2/aip3 네임스페이스 NVS 설정 방법
```

**부저 상태머신 설계**: `Note{freq_hz, ms}` 배열 + sentinel `{0,0}`, `millis()` 기반 비블로킹 tick. `delay()` 미사용 → 모터 피드백 루프 블로킹 없음.

**serial_bridge.py 수정** (RPi, SCP 배포):
- `/aip1/esp32_reset` (Empty) 구독 → `PKT_RESET(0x07)` 전송 → `esp_restart()`
- `/aip1/esp32_beep` (UInt8MultiArray) 구독 → `PKT_BEEP(0x08)` + pattern byte 전송

**`.gitignore` 업데이트**: `firmware/scout_microros/secrets.ini` → `firmware/scout/secrets.ini`

### spongebobDG 기여 등록 (40e82ec)

팀원 PR #2("웹 관제 대시보드 기능 추가")의 48개 파일 중 38개가 이미 메인 코드에 통합된 것으로 확인. PR은 별도 머지 없이 닫고, `CONTRIBUTORS.md` 신규 생성으로 기여 내역 명시:

- `dashboard_server.py`: asyncio 스레딩 버그 수정, `_state_cache` 도입, ExternalShutdownException 처리
- `static/index.html`: 다크모드 토글, 지도 전체화면, 웨이포인트 편집 UI
- `sim_heartbeat_node.py`, `sim_pose_relay_node.py`: 시뮬 전용 더미 노드 2종 신규
- Foxglove 패널 3종: 세션 락, 키보드 제어 추가

### PR #1 머지 (bcc1656 on main)

`feat/real-monorepo` → `main` 머지 완료 (2026-06-22T06:16 UTC). 42개 커밋, 약 120개 파일 변경.

---

## 2026-06-22 — 차량 네임스페이스 전면 변경 (aip1/aip2/aip3)

### 결정

| 이전 | 이후 | 차량 |
|---|---|---|
| `main` | `aip1` | FIT0186 메인 AGV |
| `scout_1` | `aip2` | TurtleBot3 Burger |
| `scout_2` | `aip3` | STS3215 커스텀 차량 |

**이유**: 역할 기반 이름은 차량 추가·역할 변경 시 혼란 발생. 프로젝트 전용 ID로 고정해 모든 노드·토픽·문서가 동일 기준 사용.

### 변경 범위 (488eb21, 42개 파일)

| 분류 | 파일 수 | 대표 파일 |
|---|---|---|
| Python 노드 | 7 | supervisor_node, coordinator_node, dashboard_server, scout_localizer |
| Launch 파일 | 6 | main_agv, turtlebot3, custom_vehicle, fleet_real, turtlebot3_sim |
| YAML config | 11 | nav2×3, slam_toolbox×3, patrol×3, twist_mux |
| TypeScript 패널 | 3 | EStopPanel, FleetDashboard, OverridePanel |
| 보안·설정 | 4 | sros2_policy.xml, sros2_init.sh, dhcp_reservations.md, vehicles.yaml |
| 문서·규약 | 5 | CLAUDE.md, FleetHeartbeat.msg, fleet_overview.json, package.xml, 메모리 |

**신중하게 교체하지 않은 것**: `def main()`, `if __name__ == '__main__'`, `main_agv`(디렉토리명), `peer_1/2/3`(시뮬 전용), `node_modules/` 내 `"main"` 키.

---

## 2026-06-22 — 관제 웹 UI 네임스페이스 반영 + 미구현 버그 수정

### 수정 내용 (f7a4ecc)

#### `index.html`

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| `VEHICLES` 상수 | `"main","scout_1","scout_2"` | `"aip1","aip2","aip3"` |
| `COLORS` 맵 키 | `main:`, `scout_1:`, `scout_2:` | `aip1:`, `aip2:`, `aip3:` |
| 초기 선택 차량 | `peer_1` | `aip1` |
| `wpDeleteIdx` | 서버 미동기화 (로컬 splice만) | 삭제 후 `wpSend()` / `clear` 호출 추가 |

#### `dashboard_server.py`

| 항목 | 문제 | 수정 |
|---|---|---|
| `_tf_vehicle_ids` | `aip1~3` 누락 → 실차 TF fallback 포즈 불표시 | `aip1`, `aip2`, `aip3` 추가 |
| 맵 구독 | `/peer_1/map`만 있고 실차 `/aip1/map` 없음 | `/aip1/map`, `/aip1/map_relay` 구독 추가 |
| bag 토픽 | `aip1~3` odom/scan 누락 | 추가 |
| 맵 소스 캐시 | 재접속 시 맵 소스 버튼 상태 미복원 | `_state_cache['map_source_changed']` 초기 등록 |
| `navigate_to`/`set_dock` 기본값 | `peer_1` | `aip1` |

---

## 현재 상태 요약 (2026-06-22)

### 완료된 항목 (전체)

| 항목 | 날짜 |
|---|---|
| 초기 스캐폴딩 (5개 패키지, Docker, Foxglove 패널) | 2026-04-20 |
| Ubuntu 환경 이전 + git init | 2026-04-22 |
| 보안 감사 36건 (즉시 4건, 단계별 분류) | 2026-04-22 |
| twist_mux + 코디네이터 + SROS2 + setup_ubuntu.sh | 2026-04-22~23 |
| Ignition Fortress Phase-1 (3대 스폰, TF, teleop) | 2026-04-24 |
| Phase-2 통합 런치 버그 수정 3건 | 2026-04-27 |
| UWB 협력 측위 (shadow 모드, 검증 인프라) | 2026-04-27~05-14 |
| AMCL 파라미터 버그 + CI 구성 | 2026-05-07 |
| odom_frame_fixer (프레임 교정 relay) | 2026-05-12 |
| odom TF 분리 현상 수정 (EKF relative + 영점화) | 2026-05-18 |
| 자율 순찰 아키텍처 (peer_1 선행 탐색 + explore_lite) | 2026-05-20~22 |
| 열화상 파이프라인 + MPPI 통합 | 2026-05-21 |
| FleetDashboard Foxglove 패널 | 2026-05-21 |
| gz_ros2_control 첫 번째 엔티티 버그 (워밍업 모델) | 2026-05-22 |
| AMCL 맵 토픽 불일치 + TF 루프 + SLAM 오염 방지 | 2026-05-22 |
| 이벤트 기반 탐색 (map_readiness + follower_trigger) | 2026-05-22 |
| 웹 대시보드 2.0 (60fps, 팬/줌, 5탭, keepout, dock) | 2026-06-15 |
| `aip_fleet_real` 실차 bringup 모노레포 통합 | 2026-06-15 |
| 시뮬 안정화 완료 (TF 에러 0건, 커버리지 135㎡) | 2026-06-19 |
| keepout zone 실제 동작 + 영속화 | 2026-06-19 |
| 순찰 시작/정지 버튼 + 도킹 위치 영속화 | 2026-06-19 |
| fleet_main 실차 완전 구동 검증 (RPi4B) | 2026-06-19 |
| main_agv.launch.py 통합 (SLAM+Nav2+patrol) | 2026-06-22 |
| ESP32 펌웨어 차량별 분리 + 부저 상태머신 | 2026-06-22 |
| feat/real-monorepo → main PR 머지 | 2026-06-22 |
| 차량 네임스페이스 전면 변경 (aip1/aip2/aip3, 42파일) | 2026-06-22 |
| 웹 UI 네임스페이스 반영 + 미구현 버그 4건 수정 | 2026-06-22 |

### 잔여 작업

| 항목 | 우선순위 |
|---|---|
| ESP32 BUZZER_PIN 확정 후 firmware/main_agv 플래시 | 높음 |
| RPi colcon build + fleet_main 재시작 (serial_bridge.py 교체 반영) | 높음 |
| Scout ESP32 펌웨어 소스 확보 (팀원 확인) | 높음 |
| aip2(TB3) / aip3(STS3215) 실차 배포 및 검증 | 중간 |
| SROS2 키스토어 재생성 (sros2_init.sh — aip1/aip2/aip3 enclave 이름 반영) | 중간 |
| turtlebot3_sim.launch.py 실제 Gazebo 실행 검증 (GUI 필요) | 낮음 |
| Foxglove 레이아웃 aip1~3 토픽 경로 최종 확인 | 낮음 |
| OverrideCommand.command=4 (수동주행) 메시지 정의 확인 | 낮음 |
| control_lock_state 토픽 JSON 포맷 `{"locks": {...}}` 실검증 | 낮음 |

---

*이 문서는 `docs/agent_context/conversation_log.md`와 `pending_tasks.md`를 기반으로 작성됨.*
*마지막 업데이트: 2026-06-22*
