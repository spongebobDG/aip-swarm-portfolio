# 현 파이프라인 분석 & 개선 추천

작성 시점: 2026-04-20. 최종 갱신: 2026-05-11. 대상: `aip_swarm_ws/` 전체 스캐폴딩.

---

## 이번 턴에 이미 수정한 실제 버그

| # | 위치 | 증상 | 수정 |
|---|---|---|---|
| B1 | `src/aip_fleet_bringup/launch/fleet_sim.launch.py` (구버전) | `executable='python3'` + 인라인 스크립트로 Node 실행 — ROS2 Node 액션은 패키지 `lib/` 아래에서만 실행 파일을 찾으므로 실제로는 "executable not found"로 실패 | `aip_fleet_sim` 패키지의 정식 entry point를 사용하는 새 launch 로 교체 |
| B2 | 같은 파일 | turtlesim은 `/odom`·`/scan`·TF를 내놓지 않아서 supervisor/watchdog/Foxglove 파이프라인을 온전히 검증 불가 | 경량 kinematic 시뮬(`sim_world_node`, `sim_vehicle_node`, `sim_lidar_node`)로 대체 |
| B3 | `src/aip_fleet_bringup/launch/central.launch.py` | `vehicle_ids` 를 `LaunchConfiguration` 로 string_array 파라미터에 전달 → 실제로는 리터럴 문자열로 직렬화되어 `string_array_value` 가 빈 리스트 | `supervisor_params` YAML 파일(`config/supervisor.yaml`) 경로를 전달하도록 변경 |
| B4 | `docker/central/docker-compose.yml` · rosbag-recorder | `>` 폴딩 블록 안에서 `$(date ...)` 가 YAML 파싱 시 엉키고 `--storage-config-file /dev/null` 는 유효 옵션 아님 | `entrypoint: ["/bin/bash", "-lc"]` + 리스트 커맨드로 재작성, date 확장은 컨테이너 안에서 정상 수행 |
| B5 | 같은 파일 · foxglove-bridge | 매 재시작마다 `apt-get install` — 느리고 인터넷 의존적 | 공식 이미지 `ghcr.io/foxglove/ros-foxglove-bridge:humble` 로 교체 |
| B6 | 같은 파일 · fastdds-ds | `eprosima/fast-dds:2.14.2` 태그는 ROS2 Humble 과의 wire-format 일치가 보장되지 않음 | `ros:humble-ros-base` 이미지에서 humble 번들 `fastdds` 바이너리 사용 |
| B7 | `src/aip_fleet_supervisor/.../supervisor_node.py` | `/fleet/status` 가 VOLATILE QoS — Foxglove 가 늦게 붙으면 첫 프레임까지 대기 | TRANSIENT_LOCAL 로 변경, watchdog 구독 QoS도 동일하게 맞춤 |
| B8 | `src/aip_fleet_bringup/package.xml` | 삭제한 `turtlesim` 의존성이 남아있어 `rosdep install` 이 잘못된 패키지 설치 시도 | 제거 |
| B9 | `src/aip_fleet_bringup/CMakeLists.txt` | `launch/` 만 설치 — `config/supervisor.yaml` 은 런타임에 존재하지 않음 | `config/` 까지 install |

---

## 구조·설계상 아직 유효한 약점 / 향후 의사결정 필요

### 1. Multi-robot TF 통일 전략이 모호

> **✅ 결정 완료 (2026-04-23)**: ArUco 카메라 기반 앵커(선택지 1) 채택.
> `src/aip_fleet_coordinator/aip_fleet_coordinator/scout_localizer_node.py` 구현 완료.
> 하드웨어 연동은 카메라 구매·캘리브레이션 후 `with_localizer:=true`로 활성화.

현재 시뮬은 `map → <ns>/odom → <ns>/base_link` 트리를 세 개 만들고, `map→<ns>/odom` 은 **static**으로 초기 포즈만 심어둔 상태.
실제 차량에서는:
- 메인 차량은 SLAM으로 `map → main/odom` 을 동적으로 보정.
- 스카우트는 LiDAR 없음 → 메인의 `map` 안에서 자기 위치를 알 수단이 현재 정의되지 않음.

**선택지:**
1. **UWB/ArUco 마커 기반 앵커**: 메인이 스카우트 위치를 관측(카메라/UWB)해 `/scout_N/pose_in_map` 퍼블리시. ← **채택**
2. **DWM/ESP-NOW 상대 위치**: ESP32 간 RSSI/ToF로 상대 거리 → 메인 기준 좌표 산출.
3. **"군집=근접 추종"으로 단순화**: 스카우트는 `map` 에 들어가지 않고, 메인 기준 상대 좌표(`/main/base_link` 하위의 `/scout_N/base_link`)로만 관리.

→ **추천**: MVP는 (3) 상대 좌표로 시작. 차량 하드웨어가 준비되면 (1)을 단계적으로 도입. 이 결정을 하기 전에는 Foxglove 3D에서 스카우트 pose가 올바르게 렌더되지 않을 수 있음.

### 2. 군집 협조 로직 (`coord_cmd_vel`) 이 없음

> **✅ 결정 완료 (2026-04-23)**: 중앙 PC 배치 채택.
> `src/aip_fleet_coordinator/aip_fleet_coordinator/coordinator_node.py` — TF2 P-controller, 10Hz.
> `central.launch.py with_coordinator:=true`로 활성화.

`twist_mux` 설정에는 있지만 **publisher가 존재하지 않음**. 리더-팔로워·포메이션 유지 같은 군집 행동을 어떤 노드가 계산할지 빠져있다. 후보:
- 메인 차량 안에 `fleet_coordinator_node` 를 두고 각 스카우트에게 목표 twist 을 송신 (중앙집중형, 구현 쉬움, 메인 장애 시 전체 멈춤)
- 중앙 PC 에 두고 ROS2 로 각 차량에 송신 (네트워크 지연 1 홉 추가, 디버깅·대시보드 편함 ← **채택**)
- 분산 (각 스카우트가 이웃 관측 기반 자율) — ESP32 연산·센서 한계로 비현실적

**다음 스텝**: `aip_fleet_coordinator` 패키지를 중앙 PC에 둘지 확정 후 스켈레톤 추가.

### 3. 오버라이드 우선순위 재검토

> **✅ 결정 완료 (2026-04-22)**: estop_lock 발행 구현 완료.
> `supervisor_node.py`: CMD_ESTOP → `estop_lock=True`, CMD_CLEAR/RESUME → `estop_lock=False`.
> `config/twist_mux_vehicle.yaml`: estop_lock(90) > central(80) > fleet_coord(50) > autonomy(10).

현재 `twist_mux` 는 각 차량 측에서 구동. HW e-stop > central override > coord > autonomy 순위인데:
- **coord_cmd_vel 이 central override 보다 낮다** → 오퍼레이터가 한 대를 pause 시켜도 `fleet_coordinator` 가 계속 목표 twist 를 생성해 "타임아웃 전까지" 잔여 관성이 남을 수 있음.
- **해결**: override 가 활성화된 경우 supervisor 가 해당 차량 `estop_lock` 토픽을 True 로 잠가(twist_mux locks 스펙 활용) coord 까지 통째로 무시되게 만들기.
- **다음 스텝**: supervisor 에 `estop_lock` 발행 로직 추가(ESTOP 시 True, CLEAR 시 False).

### 4. ESP32 micro-ROS 빌드 체인 불완전

> **✅ 완료 (2026-04-23 T8)**: FleetHeartbeat.msg bounded 선언.
> `string<=32 vehicle_id`, `string<=64[<=8] active_behaviors`.
> FleetStatus.msg: `FleetHeartbeat[<=4] vehicles`, `string<=32[<=4] offline_vehicle_ids`.
> 별도 ScoutHeartbeat.msg 불필요 — FleetHeartbeat 자체가 micro-ROS 호환됨.

`firmware/scout_microros/README.md` 에서 `aip_fleet_msgs` 의 C 헤더를 수동 생성해 넣으라 했지만, 실 운영 시:
- `micro_ros_platformio` 의 `extra_packages` 디렉터리를 사용해 PlatformIO 빌드가 자동으로 humble agent_ws 를 체크아웃 → `aip_fleet_msgs` 를 포함 → 헤더 생성 → 링크. 수동 복사 지양.
- `aip_fleet_msgs/FleetHeartbeat.msg` 의 `string[] active_behaviors` 는 가변길이 unbounded array — micro-ROS rmw_microxrcedds 는 기본 설정에서 지원 제한.
- **다음 스텝**: bounded FleetHeartbeat로 펌웨어 빌드 검증.

### 5. 대시보드 메시지 인덱싱 취약

> **✅ 완료 (2026-04-22 T4)**: 해결 B 적용.
> `fleet_overview.json`: `vehicles[0]` → `vehicles[:]{vehicle_id=="main"}` 필터 표현식.

`config/foxglove_layouts/fleet_overview.json` 의 배터리 플롯이 `/fleet/status.vehicles[0].battery_pct` 같이 **인덱스 기반**. 차량 하나가 offline 으로 빠지면 배열 순서가 밀려서 시각화가 틀어질 수 있다.
- **해결 A**: `FleetStatus.msg` 구조를 `map<string, FleetHeartbeat>` 유사 패턴으로 재구성.
- **해결 B**: Foxglove `filter` expression 으로 `vehicle_id == "main"` 인 원소만 뽑기. ← **채택**

### 6. Foxglove 커스텀 패널 빌드 체인 미검증

> **✅ 완료 (2026-04-23)**: `npm run build` + `npm run package` 모두 PASS.
> `.foxe` 파일 정상 생성 확인: `aip.fleet-foxglove-panels-0.1.0.foxe`.
> B4 수정(HOLD-to-drive 10Hz)도 반영됨.

`src/aip_fleet_foxglove_panels/package.json` 은 `@foxglove/extension` + `create-foxglove-extension` CLI 기반으로 구성. `npm run build` 시 `.foxe` 패키지 정상 생성.
- **설치**: Foxglove Studio → Extensions → Install from .foxe 파일 선택.

### 7. 보안

| 계층 | 현황 | 위험 |
|---|---|---|
| Wi-Fi | WPA2-PSK | 시연용 OK, 외부 노출 시 약함 |
| DDS | 평문 UDP | 같은 SSID 안에서는 누구나 토픽 스니핑 가능 |
| Foxglove Bridge | 익명 WebSocket | LAN 내 누구나 오버라이드/E-Stop 패널 사용 가능 |
| rosbag 레코더 | 로컬 볼륨 | 장기 보관 시 디스크 암호화 필요 |

**MVP 단계**: 그대로 진행. **실증/시연 직전**: Foxglove Bridge 에 `--certfile`/`--keyfile` + 기본 인증, SROS2 키스토어 생성(향후 훅으로 예약됨).

### 8. 텔레메트리 파이프라인 미완

> **✅ 브릿지 완료 (2026-04-23)**: `aip_fleet_telemetry` 패키지 신설.
> `telemetry_node.py`: `/fleet/status` → InfluxDB `fleet_vehicle` measurement (per vehicle),
> `/fleet/override` → `fleet_override` measurement.
> `influxdb-client` 미설치 시 dry-run 모드(DEBUG 로그)로 동작.
> 활성화: `central.launch.py with_telemetry:=true`.
> **잔여**: Grafana 대시보드 JSON (Influx 실 데이터 수집 후 작성).

docker-compose 에 InfluxDB 는 올라가지만, **ROS2 → InfluxDB 브릿지가 없음**. 후보:
- `ros2 topic echo` 파이프 + Telegraf tail 입력 — 비추, 구조적으로 취약.
- 전용 브릿지 노드(파이썬, `influxdb_client` 사용) — **채택**. `/fleet/status`, `/fleet/override` 저장.

**설치 및 실행**:
```bash
pip3 install influxdb-client
ros2 launch aip_fleet_bringup central.launch.py with_telemetry:=true
```
환경변수 `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET` 로 설정.

### 9. 테스트·CI 부재

> **✅ 부분 완료 (2026-04-22 T3)**: supervisor 단위 테스트 23개 추가. PASS 확인.
> `src/aip_fleet_supervisor/test/test_supervisor_node.py`: CMD_ESTOP/CLEAR/RESUME/PAUSE/MANUAL, 와일드카드, estop_lock 재발행 등.

- ~~`aip_fleet_supervisor` 에 pytest 가 없음~~
- launch 테스트(`launch_testing`) 없음 → `ros2 launch ... fleet_sim.launch.py` 가 실행되는지 자동 확인 불가.
- GitHub Actions/GitLab CI 구성 없음.

**잔여 스텝**:
1. `aip_fleet_sim/test/test_world.py` — ray cast 결과 수학 검증.
2. 간단한 `.github/workflows/colcon.yml` 또는 `industrial_ci` 연결.

### 10. 설정 중복

IP `192.168.0.9` 과 포트 `11811`, `8888`, `8765` 가 docker-compose, Dockerfile, XML, README, firmware `platformio.ini` 에 산재.
- **해결**: 단일 `.env` 파일(`docker/central/.env`) + docker compose env_file + 생성 스크립트로 XML 치환. 펌웨어는 PlatformIO 의 `build_flags` 를 CI 변수로 받기.
- **우선순위**: Medium. 지금 바꾸면 오버엔지니어링, 현장 3개 이상으로 늘어나는 시점에 리팩터.

---

## 우선순위 제안 (다음에 내가 손댄다면 이 순서)

1. **§5 배터리 플롯 필터식 수정** (1분, 대시보드 신뢰도 직결).
2. **§3 supervisor 의 `estop_lock` 발행** (오버라이드/E-Stop 의미상 필수, 30분).
3. **§9.1 supervisor 단위 테스트** (회귀 방지, 1시간).
4. **§2 `aip_fleet_coordinator` 스켈레톤** (군집주행 핵심, 차량 팀과 인터페이스 조율 후 진행).
5. **§4 ScoutHeartbeat bounded msg + 펌웨어 전환** (하드웨어 단계 진입 시점에 필수).
6. **§1 스카우트 위치 추정 전략 결정** (하드웨어 센서 선택과 직결 — UWB/마커 구매 결정 포함).
7. **§6 Foxglove 패널 공식 템플릿 마이그레이션** (배포 직전).

---

## Phase-2 디버깅 기록 (2026-05-11)

### 공통 버그: ROS2 YAML 파라미터 네임스페이스 불일치

#### 현상

`PushRosNamespace` 또는 `Node(namespace=...)` 로 배포한 노드에 YAML 파라미터가 적용되지 않아 모든 값이 기본값으로 동작.

#### 원인

ROS2는 YAML 파라미터 파일의 최상위 키를 노드의 **완전 경로(fully qualified name)** 와 매칭한다.

```
노드 실제 경로:  /peer_1/slam_toolbox
YAML 키:         slam_toolbox:          ← /slam_toolbox 에만 매칭 → 미로드
                 /peer_1/slam_toolbox:  ← 정확히 매칭 → 로드됨
```

`PushRosNamespace('peer_1')` 하에서 실행된 노드는 `/peer_1/<node_name>` 경로를 가지므로, YAML 최상위 키도 반드시 `/<namespace>/<node_name>:` 또는 `/**:` 형식이어야 한다.

#### 발견된 파일 및 수정 내역

| 파일 | 수정 전 키 | 수정 후 키 | 증상 |
|---|---|---|---|
| `aip_fleet_nav/params/slam_toolbox_online.yaml` | `slam_toolbox:` | `/${vehicle_id}/slam_toolbox:` | `scan_topic` 기본값 `/scan` 사용 → `/peer_1/scan` 미구독 → 맵 미생성 |
| `aip_fleet_nav/params/amcl.yaml` | `amcl:` | `/${vehicle_id}/amcl:` | `odom_frame_id: odom`, `base_frame_id: base_footprint` 기본값 → TF 조회 실패 → 위치추정 불가 |
| `aip_fleet_nav/params/nav2_params.yaml` | `controller_server:` | `/${vehicle_id}/controller_server:` | DWB critics 파라미터 미로드 → `FATAL: No critics defined for FollowPath` |
| `aip_fleet_nav/params/nav2_params.yaml` | `local_costmap/local_costmap:` | `/${vehicle_id}/local_costmap/local_costmap:` | costmap이 기본 `static_layer` 사용 → 장애물 인식 불가 |
| `aip_fleet_bringup/config/twist_mux_vehicle.yaml` | `twist_mux:` | `/**:` | topics/locks 파라미터 미로드 → 토픽 구독 없음 → cmd_vel 출력 없음 |

#### 진단 방법

```bash
# 파라미터가 실제로 로드됐는지 확인
ros2 param list /peer_1/slam_toolbox | grep scan_topic
ros2 param get  /peer_1/amcl odom_frame_id

# 토픽 구독 여부 확인
ros2 topic info /peer_1/override_cmd_vel  # Subscription count 확인
ros2 node info  /peer_1/twist_mux | grep -A 15 "Subscribers"
```

#### 규칙

- `Node(namespace=vid)` 또는 `PushRosNamespace(vid)` 로 배포되는 노드의 YAML은 반드시 `/<ns>/<node>:` 키 사용.
- 차량 수에 무관하게 공유하는 YAML은 `/**:` 또는 `${vehicle_id}` 치환 방식 사용.
- `slam_toolbox`는 ROS2 표준 remapping을 우회하고 `scan_topic` 파라미터 값으로 직접 subscriber 생성 → YAML 로드가 필수.

---

### Ignition Gazebo sim clock "jump back in time" 분석

#### 현상

```
[tf2_buffer]: Detected jump back in time. Clearing TF buffer.
[robot_state_publisher]: Moved backwards in time, re-publishing joint transforms!
```

SLAM, AMCL, controller_server, robot_state_publisher 등 `use_sim_time: true` 노드에서 반복 발생.

#### 원인: 독립 DDS 채널 간 전송 순서 역전

Ignition이 물리 스텝을 완료하면 `/clock`과 나머지 데이터(TF, 센서)를 **완전히 독립된 DDS 채널**로 발행한다. 채널 간 도달 순서가 보장되지 않아 아래 상황이 발생한다.

```
물리 스텝 완료 (sim_time = 100ms)
        │
        ├─ 채널 A: /clock  (t=100ms) ──► 노드 도달: 2ms 후   → "현재 = 100ms"
        └─ 채널 B: /tf     (t=100ms) ──► 노드 도달: 5ms 후
                   /scan   (t=100ms)
```

노드 입장:
```
t=2ms: /clock 수신 → 현재 시간 = 100ms
t=4ms: /clock 수신 → 현재 시간 = 101ms   (다음 스텝)
t=5ms: /tf   수신 → stamp = 100ms        → 101ms보다 과거 → "jump back in time"
```

#### 3가지 발생 경로

| 경로 | 설명 |
|---|---|
| ros_gz_bridge 변환 레이턴시 | `/clock`은 단순 변환으로 빠르게 전달, `/scan`은 360 ray 변환으로 느림 → 클록이 먼저 앞서감 |
| Ignition 내부 멀티스레드 | 물리/센서/렌더링 스레드 간 컨텍스트 스위치로 같은 스텝 데이터의 타임스탬프가 미세하게 다름 |
| DDS QoS 차이 | `/clock`(BEST_EFFORT)과 `/tf`(RELIABLE)의 큐 우선순위가 달라 처리 순서가 역전됨 |

#### CPU 성능이 좋아도 발생하는 이유

성능이 좋을수록 각 채널이 즉시 처리되어 **채널 간 타이밍 차이가 그대로 노출**된다. 느린 CPU는 큐에 메시지가 쌓이면서 순서가 평준화되는 효과가 있다.

#### 적용된 완화 조치

| 조치 | 파일 | 효과 |
|---|---|---|
| `max_step_size` 0.001 → 0.004 | `worlds/fleet_world.sdf` | 물리 업데이트 주기를 1000Hz → 250Hz로 낮춰 채널 간 타이밍 여유 확보 |
| `transform_tolerance` 0.5 → 1.0 | `params/amcl.yaml` | AMCL이 ±1초 오차의 TF를 허용 |
| `tf_buffer_duration: 30.0` | `params/slam_toolbox_online.yaml` | 버퍼 클리어 후 빠른 재수집 |
| `twist_mux use_sim_time: false` | `launch/fleet_phase2.launch.py` | 불안정한 sim clock 의존 제거 (twist_mux는 TF 미사용이므로 시스템 클록으로 충분) |

#### 차량 추가 시 주의사항

차량이 늘수록 ros_gz_bridge 변환 부하가 선형 증가하여 채널 간 레이턴시 차이가 커진다. 5대 이상에서는 아래 추가 조치 권장:

```yaml
# LiDAR 샘플 수 절감 (창고 환경에서 180도 해상도 충분)
<samples>180</samples>   # 360 → 180

# AMCL 파티클 수 절감
max_particles: 1000      # 2000 → 1000
```
8. 나머지(보안 강화, 텔레메트리 브릿지, 설정 중앙화)는 실증 직전 라운드.

---

## Phase-2 디버깅 기록 (2026-05-18) — odom TF 분리 현상 및 수정

### 증상

RViz에서 `peer_2/odom`, `peer_3/odom` 프레임이 차량 모델과 공간적으로 분리되어 표시됨.
peer_1 teleop 주행 후에도 peer_2/3의 위치 추정값이 실제 이동 거리보다 짧게 나타남.

### 근본 원인 분석

**Ignition Fortress diff_drive_controller**는 오도메트리 메시지의 pose 필드에 **월드 프레임 절대 좌표**를 출력한다. 차량이 스폰 위치 (−1.5, +1.0)에서 시작하면 첫 메시지의 pose도 (−1.5, +1.0, 0)이다.

```
diff_drive/odom → pose.position = (−1.5, +1.0) at spawn
      ↓  odom_frame_fixer (frame_id 교정만, pose 미수정)
odom_corrected  → pose.position = (−1.5, +1.0) at spawn
      ↓  EKF (odom0_relative: false → 절대 좌표로 해석)
peer_2/odom → peer_2/base_link TF = (−1.5, +1.0) at t=0
      ↓  AMCL (initial_pose = (−1.5, +1.0))
map → peer_2/odom = (0, 0, 0)   ← odom 프레임이 월드 (0,0)에 고정됨
```

결과: odom 프레임 원점이 맵의 (0,0)에 있고 차량은 (−1.5, +1.0)에 있어 시각적으로 분리.
차량이 이동하면서 오도메트리가 잘못된 원점에서 적분되어 위치 추정 오류 누적.

### 수정 내용

#### 1. `ekf_vehicle.yaml` — odom0_relative: false → true

`odom0_relative: true`로 변경하면 EKF가 첫 메시지를 기준점으로 설정하고 이후 메시지를 상대 델타로 해석한다. 절대 좌표 (−1.5, +1.0)이 들어와도 EKF 상태는 (0, 0, 0)에서 시작하여 적분한다.

```
map → peer_2/odom (AMCL, initial_pose=(−1.5,+1.0))
              → peer_2/base_link (EKF, 시작=(0,0,0))
```

#### 2. `odom_frame_fixer.py` — 초기 pose 영점화 추가

odom_frame_fixer가 첫 메시지 pose를 기준으로 저장하고, 모든 후속 메시지에서 해당 값을 빼서 (0,0,0) 기준 상대 pose로 변환한다. EKF의 `odom0_relative:true`와 이중 안전장치.

```python
# 일반 2D 강체 변환: T_rel = T0_inv * T1
c, s = cos(yaw0), sin(yaw0)
rel_x =  (x1 - x0) * c + (y1 - y0) * s
rel_y = -(x1 - x0) * s + (y1 - y0) * c
```

### TF 체인 정상 상태 (수정 후)

```
map → peer_N/odom        : AMCL 발행 (initial_pose = spawn 좌표)
peer_N/odom → peer_N/base_link : EKF 발행 (spawn시 (0,0,0), 이후 적분)
peer_N/base_link → peer_N/laser_frame : URDF 고정 조인트 (RSP 발행)
```

### 관련 파일

| 파일 | 변경 |
|---|---|
| `ekf_vehicle.yaml` | `odom0_relative: false` → `odom0_relative: true` |
| `scripts/odom_frame_fixer.py` | 초기 pose 영점화 + 일반 2D rigid transform 추가 |

---

## 실차 부하·SSH + 미션 제어 분석 (2026-06-27)

### A. 부팅 중 부하 → SSH·heartbeat 끊김 (근본 원인 + 완화)

**증상**: 2026-06-27 작업(네임스페이스 통일 재빌드/재부팅 포함) 중 전 차량에서 SSH 불안정.
**근본 원인**: 차량 bringup 이 **Nav2 라이프사이클(8+ 노드) + SLAM 을 동시에 활성화** →
RPi4B(Cortex-A72 4코어)가 수~십수 초 CPU/IO 포화 → SSH·heartbeat 타임아웃.
(conversation_log 2026-06-27 "bringup 부하 ~15초 I/O 창" 항목과 일치.)

**완화(적용)**:
1. **기동 staggering** — `turtlebot3.launch.py`(aip2)·`custom_vehicle.launch.py`(aip3) 에
   `TimerAction` 추가(기존엔 전무, 동시 기동이 스파이크 주범). `fleet_main.launch.py`(aip1)
   는 기존 staggering 유지 + amcl 슬롯 추가. 드라이버(t=0)→위치추정(t≈2~4)→Nav2(t≈7~10)→순찰.
2. **운영 시 SLAM→AMCL** — `fleet_main.launch.py` 에 `localization:={slam|amcl|none}` 도입 +
   실차 AMCL 설정 신규(`config/main_agv/amcl.yaml`, RPi4B 부하용 파티클 400~1500·빔 120).
   SLAM(매핑) 은 1회 맵 제작에만, 평상 운영은 저장맵+AMCL(저부하·좌표계 고정).

**남은 작업(실차 검증)**: 이 PC 에 ROS2 부재로 정적 검토·py_compile 만 수행. 중앙/RPi 에서
`localization:=amcl` E2E(map_server /map latched → amcl map→odom 수렴 → Nav2 goal) 검증 필요.

### B. 금지구역(keepout) costmap 배선 — ✅ 구현 완료 (2026-06-27 야간)

대시보드 금지구역이 두 경로로 작동: ① 목표점 거부(`cmd_navigate`→`_keepout_zone_name`),
② **경로 통과 차단(costmap obstacle 주입)** — 사용자 요청(자율 매핑 중 위험구역 접근 차단)으로 ②를 실차에 구현.

- 중앙 `central.launch.py` 에 `keepout_zone_node` 기동 추가(`with_keepout:=true` 기본).
  `/fleet/keepout_zones`(대시보드)→`/fleet/keepout_cloud`(PointCloud2, map프레임, 1Hz 재발행).
- 실차 `aip_fleet_real/config/{main_agv,turtlebot3,custom_vehicle}/nav2.yaml` 의 local·global
  `obstacle_layer.observation_sources` 에 `keepout_cloud` 추가(전 6개 costmap).
  **`clearing:False, marking:True`** = 레이캐스트 소거 없이 마킹만 → **RPi4B 저부하**(구역 없으면 빈 클라우드=무부하).
  구역 해제 시 `keepout_zone_node` 가 `ClearEntireCostmap` 서비스 호출로 정리.

**적용 범위·한계**: Nav2 가 계획·추종하는 **자율 주행(자율 매핑/탐사·순찰·목표 이동)** 경로가 금지구역을
회피·차단한다. **수동 teleop 은 costmap 게이트가 아님**(twist_mux central 이 우회).
→ **수동 teleop 운영자 인지용 경고 구현(2026-06-27)**: 대시보드(브라우저)가 차량 위치를 금지구역
폴리곤과 대조해 내부 진입 시 배너+토스트+청각 경고(`index.html` `checkKeepoutWarnings`). **브라우저
계산이라 RPi4B 부하 0.** 경고만 하고 모션은 막지 않음(운영자가 회피). 완전 차단이 필요하면 차량측
safety 노드(수동 cmd_vel 게이트) 별도 필요.
**검증(실차)**: 구역 설정→`/fleet/keepout_cloud` 발행 확인→자율 goal 이 구역 우회/진입거부 + 수동 진입 시 경고 표시 확인.

### C. twist_mux 레퍼런스 드리프트 정정

`config/main_agv/twist_mux.yaml` 노드키가 `/main/twist_mux:`(구 네임스페이스)로 남아 있어
2026-06-27 `/aip1` 통일 배포와 어긋남. `/aip1/twist_mux:` + central 슬롯 토픽을
`central_cmd_vel`(대시보드 `_VEHICLE_CMD_VEL_OVERRIDES`·supervisor.yaml 타겟)로 정합화.
표준(`override_cmd_vel`) 과의 차이 및 수렴 시 동시변경 대상은 파일 주석에 명시.

---

## 웹 UI 전수 검증 결과 (2026-06-27 야간)

UI 명령 24종·수신 메시지 26종을 백엔드(`dashboard_server.py`)·차량까지 추적.

### D. ESTOP 이 자율주행 중 래치 안 됨 (안전, 우선순위 높음)

estop 체인: 대시보드 `cmd_estop` → supervisor `/fleet/override`(CMD_ESTOP=3) → supervisor 가
`estop_lock=True`(지속)·`estop=True`·0속도 발행. **그러나 전 차량 `twist_mux.yaml` 의
`estop_lock` 락이 주석(비활성)** + `serial_bridge` 는 `/estop` 미구독.
→ estop 은 central(80) 슬롯의 0속도 1회(0.5s)뿐 → **Nav2 가동 중엔 autonomy(10)가 재개**.
- 수동 모드는 정지(경쟁 autonomy 없음). 운영(Nav2 상시) 모드에서 위험.
- **수정(준비됨)**: supervisor 가 estop_lock 을 발행하므로 twist_mux `estop_lock` 락 주석 해제 시
  래치 동작. "발행자 없으면 항상 locked" 리스크 때문에 실차에서 `estop_lock=False` 평상 발행
  확인 후 활성화. 절차: `REAL_VEHICLE_OPERATION.md §7-5`. (사용자 결정: 코드 준비+검증 후 적용)

### E. "미션" 패널 백엔드 미연결(고아) → 비활성화

대시보드 [미션] 탭의 `start_mapping`·`deploy_patrol`·`reset_mission` 은 top-level WS cmd 인데
`dashboard_server.py _ws_endpoint` 에 핸들러가 **전무**(if/elif 통과 = 무동작). 수신측도 UI 가
`mission_phase` 를 기다리나 백엔드는 미발행. `stopAllMissionPatrol` 의 `patrol_cmd:'stop'` 도
patrol_planner_node 가 모르는 명령. → 패널 전체가 무동작.
- **조치(사용자 결정: 일단 비활성, 추후 AI 파이프라인 통합)**: `index.html` 미션 탭에 비활성 배너 +
  동작 버튼 5종 `disabled` + JS `MISSION_PANEL_ENABLED=false` 가드. 동일 작업은 [제어]·[순찰] 탭 사용.

### F. 정상 확인된 경로(요약)

수동 주행(override CMD_MANUAL 80ms 연속·클램핑·deadman), 단일 목표 이동(navigate_to,
`AIP_NAV_ALLOWED_IDS` 필요), 순찰 경로 편집(patrol_planner), 맵 저장/로드/소스, dock/pose 보정,
제어권 lock, ESP32 리셋(aip1 SSH), bag, 상태/위치/스캔/썸네일 표시 — 백엔드·QoS 호환 확인.
대시보드 `rclpy.spin` 별도 스레드 + 콜백 try/except + WS 광역 except 로 단일 악성 메시지 내성.
`set_scenario` 는 `/sim/set_scenario`(실차 무효·무해).

## 자율 매핑(explore+Nav2) 데드락 검토 (2026-06-30) — 기록만, 수정 미적용

> 대시보드 `auto` 매핑(`aip1_auto_mapping.launch.py` = main_agv[SLAM+Nav2] + explore_lite)
> 실행 시 차량이 끝내 한 번도 움직이지 못하는 시작 데드락. 사용자 요청으로 **검토·기록만** 하고
> 수정은 보류. 수동 매핑/순찰 검증 후 별도 턴에서 수정 예정.

### 현상 (실측 로그)
- `controller_server` **active**, `planner_server` **lifecycle 응답없음**, `bt_navigator` **inactive[2]** 로 고착.
- `global_costmap`: `Lookup would require extrapolation into the past. Requested time 1782755243.107(런치 시각) but earliest data 302→432…` — **요청 시각이 런치 직후 한 시점(≈243)에 고정**된 채 갱신 안 됨. TF 버퍼 최신은 계속 전진(302→432).
- `local_costmap`/`slam_toolbox`: `Message Filter dropping message ... timestamp earlier than transform cache` + `queue is full` 반복.
- `/aip1/map`은 정지 상태라 첫 스캔 이후 stamp 정지. TF `map→aip1/odom`·`map→aip1/base_footprint` 자체는 최근 시각에서 정상 resolve(시계 동기 sub-second 확인, 스큐 아님).

### 핵심 원인 A — global_costmap static_layer 맵 토픽 불일치 (확정·구조적)
`config/main_agv/nav2.yaml:138`
```yaml
static_layer:
  map_topic: /map    # 주석: "slam_toolbox 는 절대경로 /map 발행" ← 사실과 다름
```
- slam_toolbox 는 `PushRosNamespace('aip1')` 아래라 **`/aip1/map`** 을 발행한다(절대 `/map` 아님; 별도 remap 없음).
- 따라서 자율 매핑(SLAM 가동) 시 global_costmap static_layer 가 구독하는 `/map` 에는 **퍼블리셔가 없어** 전역 정적 맵을 영영 못 받는다.
- localization(순찰) 모드는 `aip1_localization.launch.py` 의 map_server 가 `topic_name:=/map` 으로 발행 → static_layer 정상. **그래서 patrol 은 되고 자율 매핑만 깨진다.**
- 주석이 localization 케이스(map_server=/map)를 매핑 케이스(slam=/aip1/map)에 잘못 일반화한 것이 근본.

### 핵심 원인 B — getRobotPose 가 고정 과거 시각(≈243)을 영구 재요청 (즉시 증상)
- 로그의 즉시 실패 지점. 요청 시각이 한 시점에 고정 → TF 버퍼가 그 시각을 지나치면 영구 "extrapolation into the past".
- 정확한 Nav2 내부 트리거는 **소스 확인 필요**(미확정). 유력 가설 2:
  1) explore_lite 가 t≈20s 타이머(`aip1_auto_mapping.launch.py:59`)에 SLAM TF 안정 전 첫 goal 을 stamp≈243 으로 전송 → planner/bt 가 그 stamp 로 변환 시도 → 그 시각 TF 부재(최신은 302+).
  2) static_layer 가 맵을 못 받아(원인 A) costmap 사이즈/원점 미확정 → 업데이트 루프가 초기 시각에 고착.
- 원인 A 가 선행 차단이면 B 는 그 하류 증상일 수 있음 — A 수정 후 재현 여부로 분리 검증 요망.

### 기여 요인 (데드락을 자기강화)
- **C. explore 시작이 준비상태 무관 고정 타이머**: `aip1_auto_mapping.launch.py:59` `TimerAction(period=20.0)`. Nav2 lifecycle active + 유효 `map→base_footprint` TF 게이팅 없음.
- **D. 정지-맵정지 닭달걀**: `slam_toolbox.yaml:27` `minimum_travel_distance: 0.15` → 정지 중 키프레임/맵 stamp 미갱신. costmap 실패 → 목표 미실행 → 무이동 → slam 미갱신 으로 순환.
- **E. slam queue-full 잔존**: `transform_timeout: 1.0`/`tf_buffer_duration: 30.0` 로 이미 상향(주석 line15-16)했음에도 auto 모드서 드롭 지속. wifi 너머 `aip1/odom→base_footprint` 도착 지연/레이트 의심. Nav2 costmap 의 동일 scan/TF 동시 구독으로 경합 가중 가능.

### 수정 방향 (미적용 — 다음 턴 결정·검증 대상)
1. **(원인 A) 맵 토픽 정합** — 택1, 공유 `/map` 아키텍처와 일관되게 결정:
   - (a) `nav2.yaml` global_costmap static_layer `map_topic: /aip1/map` 로 변경(매핑 출력에 직접 정합), 또는
   - (b) 매핑 slam 의 map 토픽을 `/map` 으로 remap(localization·대시보드 실시간맵과 통일). 단 대시보드는 차량별 `/aip1/map` 도 구독 중 → 영향 범위 점검 필요.
   - 권장 검토: localization 이 이미 `/map` 을 쓰므로 (b)가 SSOT 일관성↑. 다만 다차량 동시 매핑 시 토픽 충돌 검토.
2. **(원인 B·C) explore 게이팅** — 고정 20s 타이머 제거, Nav2 lifecycle active + `map→aip1/base_footprint` 유효 TF 확인 후 explore 기동. goal stamp 는 최신 TF 시각 사용.
3. **(기여 D) 시작 데드락 차단** — 매핑 시작 시 제자리 소각 회전(또는 소폭 전진) 시드로 첫 키프레임 강제, 혹은 첫 키프레임에 한해 `minimum_travel` 완화. (속도는 보정된 0.2/0.5 floor 적용됨.)
4. **(기여 E) TF 지연** — `aip1/odom→base_footprint` 발행 레이트/지연 실측, 필요 시 `/tf` 릴레이 또는 transform_timeout 추가 상향. (과거 "unconnected trees" 기록과 동일 계열일 가능성 — 본 검토로 그 원인이 'TF 트리 미연결'이 아니라 'map 토픽 불일치 + 시작 타이밍'임이 드러남.)

### 분리 검증 절차(다음 턴)
- A 단독 수정 → auto 재현 → "Requested 243 고정"·costmap 미활성 해소 여부 관찰(누가 진짜 1차 블로커인지 확정).
- 잔존 시 B/C 게이팅 적용 → explore goal 전송 시각·planner 변환 성공 확인.
- 정지 데드락은 D 시드로 확인. 부하(E)는 thermal 무관(중앙 16코어 유휴, aip1 부하 별개) — 별도 추적.

## 수동 매핑 맵 오염 — 원격 SLAM 스캔 지연/지터 (2026-06-30) — 기록

> 대시보드 수동 매핑 중 aip1 주행 시 "TF가 뒷걸음질하며 제자리처럼" 보이고 맵 오염.

### 측정 (실측, 주행 후 정지 상태)
- odom→base 누적 **6.5m, 방향·크기 정상** → **odom/엔코더 정상**(역방향·정지 아님). map→base≈6.1m 로 최종 전진 추적은 됨(영구 정지 아님 = 주행 중 점프성 오염).
- `ros2 topic delay`: **/aip1/scan 0.155s** vs **/aip1/odom 0.034s** → 스캔이 odom보다 **~120ms 더 지연**.
- wifi RTT(중앙→aip1) **25~92ms, mdev ±24ms**(지터 큼). 편도 ~31ms.
- 분해: scan 155ms = wifi ~31ms + **ydlidar 드라이버 스탬프/시리얼라이즈 ~120ms** + 지터.
- slam 로그 `Message Filter dropping ... 'queue is full'` 반복(이전 런 캡처).

### 메커니즘 (확정에 가까움)
중앙 SLAM(원격)이 *신선한 odom(34ms)* 과 *지연·지터 스캔(155ms)* 을 융합:
1. 체계적 ~120ms 스캔 지연 → 주행속도 × 0.12s 만큼 스캔이 과거 위치에 매칭(0.2~0.3m/s 면 2.4~3.6cm 뒤).
2. wifi 지터(±24ms~92ms) → tf2 message-filter 큐 오버플로 → 스캔 드롭 → 추적 공백 → 재동기 시 map→odom 역방향 점프.
→ 합쳐져 "뒷걸음질하며 제자리" + 맵 스미어. **원격 SLAM(scan over wifi) 설계의 근본 비용** — slam.yaml line15-16 주석이 이미 인지한 지연. [[자율 매핑 데드락]] 기여요인 E 와 동일 환경.

### 완화/수정 방향
- **즉효(워크어라운드)**: ① 주행 ≤0.10~0.15m/s(120ms→1.2~1.8cm, slam 해상도 0.05m 이내로 무해화 — 체계적 오차 핵심 완화) ② slam 조밀 처리 `throttle_scans 3→1`·`minimum_time_interval 0.5→0.2`(중앙 16코어 유휴) ③ 코너 pause-and-go.
- **근본**: 차량(aip1)에서 직접 SLAM 구동(scan→slam wifi 제거) 또는 5GHz wifi 전환(지터↓). 비용은 본 턴 별도 분석(아래 대화 로그/후속 기록 참조).
- **미확인**: 120ms 중 ydlidar 드라이버 스탬프 vs 시리얼 전송 비중 정밀 분해, 주행 중 map→odom 역점프 직접 캡처(재현 시 측정 권장).

### 단독화 격리 측정 (2026-06-30) — 경합 vs 라이다 스탬프 분리 확정
aip2/aip3 전원 off(물리 오프라인, ping 무응답 확인) 후 aip1 단독 재측정:

| 지표 | 3대 동시 | aip1 단독 | 분리 결론 |
|---|---|---|---|
| RTT avg/max | 62/92 ms | **16/28 ms** | 경합이 지연 ~46ms 기여 |
| RTT 지터(mdev) | ±24 ms | **±6 ms** | **경합이 지터 4배 주범** → 큐 드롭 유발 |
| scan delay | 155 ms | **106 ms** | 경합분 ~49ms |
| odom delay | 34 ms | **4 ms** | 단독 시 네트워크 거의 무지연 |

- **결론1 (경합)**: 3대가 단일 5GHz AP 공유 → airtime 경합 + DDS 멀티캐스트로 RTT 지터 4배. 단독화로 해소. TurtleBot 튜토리얼(단일 차량)과의 결정적 차이.
- **결론2 (라이다 스탬프, 본체)**: 단독에서도 **scan 106ms 잔존**(odom 4ms 대비). 같은 wifi라 차이 ~100ms = **ydlidar 드라이버 스탬프 지연**. 10Hz 1회전(100ms)과 일치 → 회전 시작 시각 스탬프 추정. 주행 시 ~100ms-전 위치에 스캔 배치 → 체계적 뒤처짐. **단독화만으론 미해결, 느린 주행 또는 드라이버 stamp 보정 필요.**
- 5GHz·신호 -53dBm·power_save off 는 정상(메모리 "2.4GHz" 기록은 갱신 필요 — 현재 SSID `aip5GHz` ch36).

### ydlidar 타임스탬프 검토 (2026-06-30) — "버그 아님", 고유 sweep 지연
"근본 원인 의심" 받던 ydlidar stamp를 드라이버 소스로 확인한 결과:
- `aip_ws/src/ydlidar_ros2_driver/src/ydlidar_ros2_driver_node.cpp:221` — `scan_msg->header.stamp = scan.stamp`(SDK 제공값). **`now()`(발행시각) 아님.** YDLidar SDK는 scan.stamp를 **sweep 시작 시각**(첫 포인트, ≈현재−sweep시간)으로 설정 → **ROS LaserScan 규약 그대로 정상**.
- ydlidar.yaml: `frequency: 10.0` → 1회전 100ms. 측정 scan delay 106ms = sweep 100ms + 전송 6ms 와 정확 일치 → **stamp 정확, 잘못 찍힌 게 아님**.
- 즉 ~100ms는 **10Hz 스피닝 라이다의 고유 sweep 시간**. 진짜 문제는 ① 주행 중 단일-stamp 처리로 인한 **모션 왜곡**(slam_toolbox 기본 deskew 없음) ② 경합 점프(단독화로 제거됨).

**해결책(타임스탬프 수정 아님)**:
1. **최저 안정속 ~0.2m/s 정속 주행 (1차·정공법)** — ⚠️ 정지마찰 하한이 0.2라 그 이하(0.15)는 stall(주행 불가). 0.2에서 sweep(106ms)당 이동 ~2.1cm < slam 해상도 5cm → 왜곡 무해화. 0.25 초과 금지(3cm 초과). 코너는 정지 후 회전(0.5rad/s×0.1s=2.9°/sweep 스미어). 스피닝 라이다 매핑의 정석. (앞 "수동 매핑 맵 오염"의 ≤0.15 기재는 본 항으로 정정.)
2. sweep **중간 시각 re-stamp(+scan_time/2≈50ms) 릴레이** — 평균 왜곡 절반, 저비용 다음 카드.
3. **스캔 deskew 노드**(드라이버가 per-point stamp 발행: node.cpp:260 `i*time_increment`, + odom) — 근본책이나 구현 복잡 + aip1 CPU.
4. 회전수 10→12Hz는 미미(sweep 100→83ms)하고 각해상도↓ → 비권장.
→ 결론: 단독화 + 느린 주행으로 거의 해결 예상. 부족 시 re-stamp→deskew 순.

### ✅ 매핑 안정화 해결 (2026-06-30) — 근본원인 4종 + deskew로 종결
"선회 시 TF 후진/맵 비틀림" 문제가 **매우 안정적**으로 해결됨(실주행 확인). 누적 원인과 처방:

1. **파라미터 오타** `minimum_laser_range`(미인식)→ **`min_laser_range:0.1`** 정정. 0.0 무효점(26%)이 slam에 원점 가짜점으로 섭취되던 것 차단. (이전 자체검증 `aip_ws/aip_slam` 설정에서 발견)
2. **매칭 파라미터 미튜닝** → aip_slam 검증 설정 도입(**Ceres solver** + correlation/penalty/barycenter/response_expansion + 튜닝된 loop closure). 기본 솔버 대비 매칭 견고.
3. **회전 중 스캔 모션 왜곡**(10Hz sweep 100ms간 선회 시 각도 스미어) → **`scan_deskew_node` 신규**(per-point time + odom twist로 sweep-시작 프레임 역보정, numpy 벡터화, 중앙 실행). **이게 선회 안정화의 결정타.**
4. **대시보드 표시 버그** — `_cb_scan`이 raw odom 포즈로 포인트를 그려 map→odom 보정량만큼 어긋남(선회 시 최대) → **slam 보정 map→base TF 사용**으로 수정. SLAM 자체는 정상이었음(표시만 틀어짐).

부수: scan_range_filter_node는 #1 정정으로 불필요해져 제거. 잔존 queue-full 드롭은 wifi-TF 지연(비차단).
**교훈**: "네트워크가 원흉" 가설은 빗나갔고, 실제는 **설정(파라미터명·매칭튜닝) + 센서 타이밍(deskew) + 표시버그**였음. 원격 SLAM(중앙) 파이프라인은 TurtleBot 표준대로 유지 가능 — on-vehicle SLAM 이전 불필요.
파일: config/main_agv/slam_toolbox.yaml, aip_fleet_real/scan_deskew_node.py, launch(aip1_mapping·main_agv), dashboard_server._cb_scan, aip1:aip_bringup/config/ydlidar_tg15.yaml(invalid_range_is_inf, 무해).
