# 핸드오프 — 2026-06-28 전 차량 검증 & 프로젝트 테스트

> **다른 PC(중앙 Ubuntu)의 새 에이전트가 이 작업을 이어받을 때 `docs/HANDOFF.md` 다음으로
> 가장 먼저 읽는 문서.** 2026-06-27 야간 세션(Windows 개발 PC, 로컬 main 작업)의 전 맥락 +
> 내일 실차 검증 계획을 무손실로 전달한다. 여기 적힌 결정·사실·절차를 그대로 따른다.

## 0. 한 줄 요약 + 읽는 순서

2026-06-27~28: **① RPi4B 부하/SSH 안정화 + 운영(AMCL) 모드 ② 금지구역 차단/경고 ③ 웹 UI 전수
검증 ④ 서보암(aip1) ROS→ESP32 연결 + 웹 수동 제어(PTZ 패드)** 를 `main`에 구현·**origin 푸시 완료**.
목표 = **aip1/aip2/aip3 연결해 수동·미션 제어 + 서보암 동작 확정 후 투입**. AI(fleet-brain)는 그 다음 단계.

읽는 순서:
1. `docs/HANDOFF.md` (프로젝트 진입점)
2. **이 문서** (현재 구조 전체 + 즉시 테스트 가이드)
3. `docs/agent_context/conversation_log.md` **하단 2026-06-27~28 섹션 8개** (상세 결정 이력·서보암 포함)
4. `docs/agent_context/pending_tasks.md` **N-LOAD 항목**
5. `docs/ANALYSIS.md` **"웹 UI 전수 검증(A~F)"·"실차 부하 분석"** (SSOT)
6. `docs/REAL_VEHICLE_OPERATION.md §7` (운영 절차 SSOT)

## 1. 코드 가져오기 (중요 — 다른 PC라 반드시 pull)

2026-06-27~28 변경 전부 **origin/main 에 푸시 완료**. 다른 PC(중앙 Ubuntu)에서:
```bash
git fetch origin && git checkout main && git pull --ff-only
```
> **최신 origin/main = `85181c3`** (여기까지 pull). 직전 기준 = `53ba18b`. 커밋 체인:
> - `fc97ae6` feat(real): RPi4B 부하/SSH 안정화 + 운영 AMCL 모드 + 금지구역 차단/경고
> - `87c9588` docs(handoff): 핸드오프 커밋 해시 기록
> - `85181c3` feat(arm/dashboard): 서보암 ROS→ESP32 연결 + 웹 수동 제어(PTZ 패드)
>
> 상세 `git log 53ba18b..85181c3 --stat`.
> ⚠️ **aip1 차량 `~/aip_swarm_ws` 도 `git pull` 로 `85181c3` 까지 받아야** staggering·AMCL·
>    keepout·서보암 servo 모드가 실제 반영됨(R6). (aip2/aip3 는 컨테이너 자체 스택 — §4 참조)

## 2. 이번 세션(2026-06-27 야간) 변경 전체 — 무엇을·왜

### A. RPi4B 부하/SSH 안정화 + 운영 모드
- **기동 staggering** — `turtlebot3.launch.py`(aip2)·`custom_vehicle.launch.py`(aip3)에
  `TimerAction` 추가(기존 전무). 드라이버 t=0 → 위치추정 t≈4 → Nav2 t≈10 → 순찰 t≈12.
  `fleet_main.launch.py`(aip1)는 기존 staggering + amcl 슬롯. **이유**: Nav2 라이프사이클 8노드 +
  SLAM 동시 기동이 SD카드 IO 포화 → SSH 타임아웃(부하 근본원인).
- **위치추정 모드** — `fleet_main.launch.py`에 `localization:={slam|amcl|none}` + `map_yaml` 도입.
  - `amcl`(운영 기본, 저부하): map_server(/map latched)+amcl(map→odom)+lifecycle_manager.
  - `slam`(매핑 1회용): 기존 slam_toolbox. **이유**: 운영 시 SLAM은 부하 크고 재기동마다 맵
    원점이 흔들려 저장 웨이포인트/금지구역 좌표가 깨짐. AMCL=저부하+좌표계 고정.
  - 신규 `config/main_agv/amcl.yaml` (RPi4B용: 파티클 400~1500, 빔 120, odom/base_footprint).

### B. 네임스페이스·estop 정합
- `config/main_agv/twist_mux.yaml`: `/main/twist_mux:` → `/aip1/twist_mux:`, central 슬롯
  `central_cmd_vel`(대시보드 `_VEHICLE_CMD_VEL_OVERRIDES`·supervisor.yaml 타겟). slam/nav2 헤더 주석 정정.
- **ESTOP 래치 코드 준비(미활성)** — `main_agv`/`turtlebot3` twist_mux.yaml의 `estop_lock` 락 블록을
  "검증 후 활성화" 가이드로 정비. **현재 비활성** = estop이 자율주행 중 0.5s 후 풀릴 수 있음(위험).
  활성화 절차 `REAL_VEHICLE_OPERATION.md §7-5` (실차에서 `/aipN/estop_lock` 평상 False 확인 후 주석 해제).

### C. 금지구역(위험구역) 차단 + 수동 경고
- **자율 경로 차단(costmap)**: `central.launch.py`에 `keepout_zone_node` 기동 추가
  (`with_keepout:=true` 기본). 실차 `nav2.yaml` 6개 costmap(3차량×local/global)에 `keepout_cloud`
  관측원 추가(`clearing:False·marking:True`=저부하). 대시보드 폴리곤→`/fleet/keepout_zones`→
  `/fleet/keepout_cloud`(PointCloud2,map)→Nav2 obstacle_layer. **자율 매핑/탐사·순찰·이동 경로가 회피**.
- **수동 teleop 경고**: `index.html`에 차량 위치 vs 금지구역 폴리곤 내부 판정
  (`checkKeepoutWarnings`/`_pointInPolygon`, `onPoses`에서 호출). 진입 시 지도 위 빨간 배너+토스트+비프.
  **브라우저 계산이라 RPi4B 부하 0.** 경고만(모션 미차단). **이유**: 수동은 twist_mux central이 costmap
  우회 → 운영자 인지 필요(사용자 요청).

### D. 웹 UI 정리
- **[미션] 패널 비활성화** — `start_mapping`/`deploy_patrol`/`reset_mission`이 백엔드 미연결(고아)이라
  배너+버튼 disabled+JS 가드(`MISSION_PANEL_ENABLED=false`). **추후 AI 파이프라인 통합 예정**(사용자 결정).

### E. 서보암(aip1 4축 MG996R) ROS→ESP32 연결 + 웹 수동 제어 (커밋 `85181c3`)
- **갭 해소**: `arm_scan_node`가 `joint_N_cmd`(rad)만 발행하고 `serial_bridge`는 `servo_cmd`(deg)만
  구독 → 변환 부재로 ROS에서 팔 미동작이던 것을, `arm_scan_node`에 **'servo' controller_type 추가**
  (자세 rad → deg 0~180 변환 후 `/{vid}/servo_cmd`(UInt8MultiArray) 발행)로 연결.
- `arm_config.yaml`: `controller_type: servo`(실차 기본) + 관절별 servo 캘리브레이션(**명목값 — 실차 보정 필요**).
- `dashboard_server.py`: arm 퍼블리셔(servo_cmd/scan_request/estop) + `cmd_arm(servo/scan/stow)` +
  WS `arm` 케이스. `_ARM_VEHICLE`(기본 aip1, env override).
- `index.html` [제어] 탭 **서보암 패널**: CCTV PTZ **십자 방향패드**(◀▶=팬/베이스, ▲▼=틸트/숄더 ±8°,
  ⌂=홈/전방) + **정적 4축 슬라이더**(0~180°, 항상 렌더) + 접기/자동스캔/스캔정지.
- **경로**: 웹 → /aip1/servo_cmd → serial_bridge → PKT_SERVO → ESP32 PWM. serial_bridge 상시 가동이라
  arm_scan_node 없이도 동작(자동 스캔만 arm_scan_node 필요) = 구동모터 cmd_vel 과 동일 성격.

### 변경 파일
- `fc97ae6`(부하/AMCL/keepout/UI, 18): docs(ANALYSIS·REAL_VEHICLE_OPERATION·conversation_log·
  pending_tasks·HANDOFF·이 문서) + `central.launch.py` + `dashboard/static/index.html` +
  `config/{main_agv,turtlebot3,custom_vehicle}/nav2.yaml` + `config/main_agv/{slam_toolbox,twist_mux,amcl(신규)}.yaml` +
  `config/turtlebot3/twist_mux.yaml` + `launch/{fleet_main,turtlebot3,custom_vehicle}.launch.py`.
- `85181c3`(서보암, 5): `aip_fleet_perception/{arm_scan_node.py, config/arm_config.yaml}` +
  `dashboard/{dashboard_server.py, static/index.html}` + conversation_log.
검증: launch·dashboard py_compile, YAML 파싱·keepout 6 costmap·서보암 전 자세 0~180° 변환,
대시보드 JS BALANCED. **실차 E2E 미검증**(개발 PC에 ROS2 부재).

## 시스템 구조 현황 (한눈에)

| 구성 | 위치 / 스택 | 상태 |
|---|---|---|
| **aip1** 메인 AGV | 이 저장소 `aip_fleet_real` **온보드**(RPi4B `~/aip_swarm_ws`) | 구동·LiDAR·SLAM/AMCL·Nav2 ✅ |
| **aip2** TurtleBot3 | 컨테이너 `turtlebot3_humble` (자체 스택) | 구동(수동) ✅ — 실차 검증 |
| **aip3** 커스텀 STS3215 | 컨테이너 `docker-robot-1` `industrial_sub_vehicle` | 구동(수동·단거리) ✅ — 실차 검증 |
| 위치추정 | `localization:=slam`(매핑1회) / `amcl`(운영·저부하) | ✅ |
| 수동 제어 — 구동 | 웹→`override_cmd_vel`/`central_cmd_vel`→twist_mux→모터 | ✅ (12.5Hz·deadman) |
| 수동 제어 — **서보암(aip1)** | 웹 PTZ패드·슬라이더→`/aip1/servo_cmd`→ESP32 | ✅ SW (HW 캘리브 남음, R8) |
| 미션 — 목표이동/순찰 | 웹→Nav2 (`AIP_NAV_ALLOWED_IDS` 필요·R3) | ✅ |
| 금지구역 | 자율=costmap 차단 / 수동=경고 배너 | ✅ |
| ESTOP | 수동 정지 ✅ / 자율 래치=코드준비(미활성·R1) | ⚠️ 검증 후 활성화 |
| 퍼셉션 — 열상 퓨전(aip1) | `aip_fleet_perception` SW~80%, **팀원 담당** | ⏳ 미수정 |
| 중앙 AI — fleet-brain | 별 브랜치(머지·재학습 대기) | ⏳ |

> aip1 = 이 저장소 stack(`git pull` 로 코드 반영). **aip2/aip3 = 컨테이너 자체 스택**(저장소와 별개,
> 실차에서 직접 검증). 서보암·열상은 **aip1 전용**.

## 3. 확정된 설계 결정 + 근거 (틀리면 안 됨)

1. **Nav2는 부팅부터 상시 가동** — "수동 제어" = 운영자 미션 제어(웨이포인트·순찰·금지구역)까지 포함
   = 완전 자율 이전. AI는 부차 목표.
2. **운영=AMCL, 매핑=SLAM** — 부하 + 좌표계 고정 정합성.
3. **ESTOP 래치는 코드 준비만, 활성화는 실차 검증 후** (사용자 결정).
4. **미션 패널 비활성 → 추후 AI 파이프라인 통합** (사용자 결정).
5. **금지구역: 자율=costmap 차단, 수동=경고만** (사용자 결정 — 인지가 핵심).
6. **작업 브랜치 = 로컬 main 직접** (사용자 지정).

## 4. 정정된 사실 (이전 오판 교정)

- **aip3 구동계는 동작한다(수동 구동 테스트 완료)**. 이전에 "미구현"으로 오판했으나 오류였음.
  - 근거: `docs/vehicles/3_aip3_scout_2/README.md`("콘센트 조건에서 조금씩 움직임", web MANUAL),
    aip3 자체 스택 `/home/aip3/industrial_sub_vehicle/ros2_ws/src/sub_vehicle_bringup/`(RPP 적용),
    컨테이너 `docker-robot-1`, ESP32 펌웨어로 STS3215 구동(사용자 확인).
- **aip2/aip3는 docker 컨테이너 자체 스택** (aip1만 이 저장소 stack). 저장소의
  `custom_vehicle.launch.py`/`turtlebot3.launch.py`는 **레퍼런스**이며 실차가 그대로 쓰지 않음.
  → 저장소·기록만으로 aip2/aip3 구동 확인 어려움. **실차 직접 검증 필요**.
- **문서 드리프트(정리 대상, 미수정)**: 다수 SSOT가 "aip3 미구현 placeholder"로 잔존 →
  `ARCHITECTURE.md:186-188,382`, `HANDOFF_REAL_WS.md:25,267`, `SETUP_HARDWARE.md:355,535`,
  `SETUP_RPI4.md:214`, `TEAM_ONBOARDING.md:198,267`, `custom_vehicle.launch.py` docstring.
- **네임스페이스 미확정**: aip3가 `/aip3/*`인지 `/scout_2/*`인지 실차 확인 필요(vehicle 문서엔 scout_2 잔존).
  대시보드 alias(`AIP_VEHICLE_TOPIC_ALIASES`)로 흡수 가능.
- **퍼셉션(aip1 전용) 진행 상태**:
  - **서보암(4축 MG996R)**: SW 경로 **완성**(servo 모드 연결 + 웹 PTZ 수동제어). 실차 남은 것 = 서보혼/영점
    **캘리브레이션**(arm_config `servo:` + UI `ARM_POSES`), `arm_scan.launch.py vehicle_id:=aip1` 기동, 실제 동작 검증.
    URDF arm_joint_2/3 pivot 은 팀원 SolidWorks 대기(별개).
  - **열상 퓨전**: SW 체인(thermal_driver→patrol_monitor→central_fusion **YOLOv8**→viz) ~80% 구현이나
    **팀원 담당 → 미수정**. 실HW·캘리브(열상↔RGB 호모그래피)·YOLO 가중치·검증 미완. Pi 부하 주범은
    RGB 캡처/압축(열상 32×24는 경량) → 권장: 열상 임계 Pi 상시 + RGB 이벤트 구동 + YOLO 중앙(기존).

## 5. 즉시 테스트 가이드 (전 차량 + 서보암)

> 순서대로 진행. 웹 관제는 `http://localhost:8080` [제어] 탭에서 **구동(수동 주행) + 서보암**을 모두 제어.

### 5-0. 중앙 PC 선행 (필수)
```bash
export AIP_NAV_ALLOWED_IDS=aip1,aip2,aip3     # 미설정 시 navigate(목표이동/순찰) 전부 조용히 거부됨
# (선택) 서보암 차량 변경 시: export AIP_ARM_VEHICLE=aip1  (기본 aip1)
cd ~/aip_swarm_ws && ros2 launch aip_fleet_bringup central.launch.py    # keepout_zone_node·supervisor·dashboard 포함
# → http://localhost:8080 접속, 차량 카드/지도 표시 확인
```

### 5-1. aip1 (이 저장소 stack, RPi4B 온보드)
1. 맵 1회 제작: `fleet_main.launch.py localization:=slam` → 수동 주행(teleop 경고 동작 확인) →
   `ros2 service call /aip1/slam_toolbox/save_map ...` `~/aip_maps/latest_fleet_map`.
2. 운영: `fleet_main.launch.py localization:=amcl map_yaml:=~/aip_maps/latest_fleet_map.yaml`.
   - **부팅 후 ~15s SSH 자제**(Nav2 IO 스파이크 통과 대기) → AMCL 수렴 확인.
3. 수동 주행/단일 목표 이동/금지구역(자율 우회 + 수동 경고) 동작 확인.
4. **ESTOP 검증·활성화**: `ros2 topic echo /aip1/estop_lock` 평상 False → estop_lock 주석 해제 →
   주행 중 ESTOP 즉시·지속 정지 → CLEAR 재개.

### 5-2. aip2/aip3 (컨테이너 — 직접 검증)
```bash
# 토픽 실재 (aip3는 /aip3 또는 /scout_2 둘 다 점검)
ros2 topic list | grep -E "aip2|aip3|scout_2"
ros2 topic hz /aip2/scan ; ros2 topic hz /aip2/odom   # 센서·휠 구동 피드백
ros2 topic echo --once /aip2/heartbeat
ssh aip2@192.168.0.4   # docker ps(turtlebot3_humble), uptime/top 부하
ssh aip3@192.168.0.5   # docker ps(docker-robot-1), ESP32/micro-ROS·STS3215 브리지 살아있나, 부하
# ⭐ 수동 제어 E2E: 웹 제어권 획득 → 전진 짧게 → 차량 이동 + /aipN/odom 변화 → 정지
#    (경로: 웹 → /aipN/override_cmd_vel + UDP 19051/19052 → twist_mux → /aipN/cmd_vel → 모터)
ros2 topic echo /aip2/cmd_vel   # 조작 시 값 들어오는지 모니터
```
합격: scan·odom 발행 + heartbeat + web online/MANUAL + 웹조작→cmd_vel→**차량 이동**→정지 + SSH 안정.

### 5-3. 서보암 웹 수동 제어 (aip1)
전제: aip1 에서 `fleet_main.launch.py` 가동(serial_bridge 포함 → /aip1/servo_cmd→ESP32). 자동 스캔만
쓸 땐 `ros2 launch aip_fleet_perception arm_scan.launch.py vehicle_id:=aip1` 추가.
```bash
ros2 topic echo /aip1/servo_cmd     # 웹 조작 시 deg×4(UInt8) 들어오는지 모니터
```
웹 [제어] 탭 → **서보암 패널**:
1. **십자 방향패드** ◀▶(팬=베이스)·▲▼(틸트=숄더) → 한 번에 ±8° → 실제 팔 움직임 확인.
2. **4축 슬라이더**(베이스/숄더/엘보/리스트, 0~180°) 직접 이동 확인. **⌂=홈, 접기=stow.**
3. **방향이 반대면** `arm_config.yaml` `servo:` 의 `invert`(또는 UI 방향패드 delta 부호) 보정.
4. **자동 스캔**(arm_config 시퀀스) ↔ **수동 제어**는 번갈아 사용(동시 사용 시 servo_cmd 충돌).
합격: 방향패드/슬라이더 조작 → `/aip1/servo_cmd` 발행 → **팔이 해당 축으로 이동** → 접기 복귀.

## 6. 핵심 gotcha / 위험 등록부

| # | 위험 | 영향 | 조치 |
|---|---|---|---|
| R1 | ESTOP 자율 중 미래치(estop_lock 비활성) | 안전 | 5-1 ④ 검증·활성화 |
| R2 | 부팅 Nav2 t≈7s IO 스파이크 → SSH 렉 | 운영 | 부팅 후 15s SSH 자제 / (개선) SSD 부팅·로그 verbosity↓ |
| R3 | `AIP_NAV_ALLOWED_IDS` 미설정 | 미션 불가 | 5-0 설정 |
| R4 | AMCL 초기 포즈 미수렴 | 좌표 오류 | 대시보드 재로컬라이즈 / `AIP_AMCL_INIT_VEHICLES`·`_POSE_*` |
| R5 | WiFi DDS 손실(heartbeat flap) | 모니터링 | AP 품질·채널 점검 |
| R6 | 차량 파일 vs 저장소 드리프트 | 재현성 | aip1 `~/aip_swarm_ws`가 push된 main과 일치하는지 1회 대조 |
| R7 | aip3 네임스페이스(/aip3 vs /scout_2) | 토픽 | 실차 `topic list`로 확정, alias 조정 |
| R8 | 서보암 방향/영점 미보정(명목 캘리브) | 팔 오동작 | `arm_config.yaml servo: invert/neutral_deg` 실측 보정(5-3 ③) |

## 7. 오픈 결정 / 미완

- ✅ **커밋·푸시**: 전부 origin/main `85181c3` 까지 푸시 완료(사용자 지정 = main 직접).
- **서보암 실차 캘리브레이션**(R8) + 동작 검증 — 실차 연결 후.
- **열상 퓨전**: 팀원 담당(미수정). Pi 부하 위해 RGB 이벤트 구동 권고(§4).
- **문서 드리프트 정리**(§4): aip3 현실 반영 여부 — 사용자 지시 대기(미수정).
- **수동 금지구역 완전 차단**(경고→차단): 필요 시 차량측 cmd_vel 게이트 safety 노드 별도 구현.
- **AI(fleet-brain)**: `feat/fleet-brain`(merge-base `6e50883`, main보다 5커밋 뒤) — 재개 전 **main 머지 권장**
  (충돌 6파일: dashboard_server·index.html·central.launch 등). 기존 커버리지 모델은 10m·균일·keepout없음
  가정 → keepout 주입·이질차량·arena 스케일 조정 또는 재학습 필요(`ANALYSIS.md`·conversation_log 참조).
