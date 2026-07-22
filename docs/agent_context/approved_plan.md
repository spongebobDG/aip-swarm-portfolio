# AIP 팀 프로젝트 — 군집주행 통신망 & 중앙 제어/모니터링 환경 구축 계획

## Context

SLAM 기반 자율주행차량 1대(메인, Raspberry Pi 4B + ROS2 Humble + YDLIDAR + STS3215 + IMU)와 소형 군집 차량 2대(ESP32-S3 기반, 비용 제약으로 저성능)를 **유기적으로 묶어 운용**하기 위한 기반 환경을 먼저 구축한다. 차량 각각의 SW는 별도 팀원이 담당하므로, 본 계획의 범위는:

1. **차량 간 통신 계층** — 이기종(Pi 4B ROS2 ↔ ESP32-S3 micro-ROS) 군집을 하나의 ROS2 그래프로 묶기
2. **중앙 제어/모니터링 PC 환경** — 텔레메트리 수집, 상위 권한 오버라이드, 대시보드, 로깅
3. **전용 Wi-Fi 인프라** — 외부망과 분리된 군집 전용 네트워크

확장성 고려사항: 현재 ESP32-S3를 쓰지만 향후 Pi 4B급 이상 SBC로 대체될 가능성이 있으므로 **ROS2 네이티브 계약(토픽·서비스·TF·QoS)을 유지**하도록 설계한다. 추후 Zenoh RMW(`rmw_zenoh_cpp`)로의 스왑 또는 SROS2(보안) 도입을 비파괴적으로 얹을 수 있도록 네임스페이스·QoS·discovery 설정을 표준화한다.

메인 차량은 현재 ROS2 Docker(`my_ros_env`) + `/root/colcon_ws` 워크스페이스에서 rf2o odometry 통합 중 — 이 환경은 건드리지 않고 **neighbor** 관계로 연동한다.

---

## 목표 시스템 구성

```
                  [전용 공유기 Wi-Fi AP — SSID: AIP_FLEET]
                 192.168.0.0/24  (외부망 분리)
                           |
   ┌─────────────┬─────────────┬──────────────┬──────────────┐
   │             │             │              │              │
 .50.10       .50.20         .50.21        .50.22         .50.30
[Central PC]  [Main AGV]    [Scout-1]     [Scout-2]     [Operator Laptop]
 Ubuntu 22.04 RPi4/Humble   ESP32-S3       ESP32-S3       (옵션 원격 Foxglove)
 • FastDDS DS • SLAM/Nav    micro-ROS      micro-ROS
 • µROS Agent • rf2o/lidar  (UDP/Wi-Fi)    (UDP/Wi-Fi)
 • Foxglove Br• IMU/arm
 • rosbag2
 • Override
```

**단일 ROS_DOMAIN_ID = 42**, 네임스페이스로 차량 구분: `/main`, `/scout_1`, `/scout_2`, 그리고 플릿 전역 `/fleet/*`.

---

## 설계 결정 요약

| 항목 | 선택 | 이유 |
|---|---|---|
| RMW | `rmw_fastrtps_cpp` + Discovery Server | Wi-Fi 환경에서 multicast 불안정 회피, RMW 스왑으로 Zenoh 이전 용이 |
| 브리지(ESP32) | micro-ROS Agent (UDP4) on Central PC | ROS2 토픽/서비스 그대로 사용, 유지보수 단일 창구 |
| 대시보드 | Foxglove Studio + Foxglove Bridge(WS 8765) + 커스텀 패널 | 3D·이미지·열상·다차량 뷰를 즉시 확보, 오버라이드/E-Stop 패널만 자체 제작 |
| 네트워크 | 전용 Wi-Fi 공유기(2.4+5GHz 듀얼, ESP32는 2.4GHz) | 외부망/캠퍼스망 discovery 혼선 배제, DHCP 예약으로 IP 고정 |
| 오버라이드 | `twist_mux` 우선순위 기반 + 워치독 | HW e-stop > 중앙 override > 군집 협조 > 로컬 자율 순위 |
| 로깅 | `rosbag2` 상시 기록 + InfluxDB(경량 텔레메트리) | rosbag은 Foxglove 재생 호환, InfluxDB는 장기 추세·알람용 |

---

## 디렉터리/레포 구조 (신규)

중앙 PC에 다음 워크스페이스 신설. 메인 차량 기존 `/root/colcon_ws`는 건드리지 않음.

```
~/aip_swarm_ws/
├── docker/
│   └── central/
│       ├── docker-compose.yml         # µROS Agent, Foxglove Br, InfluxDB, Grafana(옵션)
│       └── Dockerfile.central
├── config/
│   ├── fastdds_discovery_server.xml   # DS 서버 IP/포트
│   ├── fastdds_client_profile.xml     # 각 차량에 배포할 클라이언트 프로파일
│   ├── twist_mux.yaml                 # 우선순위 mux 설정
│   ├── foxglove_layouts/
│   │   ├── fleet_overview.json
│   │   └── scout_debug.json
│   └── network/
│       └── dhcp_reservations.md       # MAC ↔ IP 문서
├── src/
│   ├── aip_fleet_msgs/                # 공통 msg/srv 패키지
│   │   ├── msg/FleetHeartbeat.msg
│   │   ├── msg/FleetStatus.msg
│   │   ├── msg/OverrideCommand.msg
│   │   └── srv/AssignMission.srv
│   ├── aip_fleet_bringup/             # 통합 launch
│   │   └── launch/
│   │       ├── central.launch.py      # 중앙 PC 서비스 전부
│   │       └── fleet_sim.launch.py    # Gazebo/turtlesim 시뮬 검증용
│   ├── aip_fleet_supervisor/          # 파이썬 노드
│   │   ├── supervisor_node.py         # 하트비트 집계 + 오버라이드 게이트웨이
│   │   └── watchdog_node.py           # 차량별 워치독(타임아웃 시 safe-stop)
│   └── aip_fleet_foxglove_panels/     # TS 기반 Foxglove 커스텀 패널
│       ├── OverridePanel/
│       └── EStopPanel/
└── firmware/
    └── scout_microros/                # PlatformIO 프로젝트(ESP32-S3)
        ├── platformio.ini
        └── src/main.cpp               # cmd_vel 구독 / odom·status·battery 발행
```

---

## 단계별 작업

### Step 1. 전용 Wi-Fi 인프라 구축

1. 공유기 1대 확보(듀얼밴드 권장). SSID `AIP_FLEET`, WPA2-PSK.
2. 외부망 업링크는 차단 또는 guest VLAN으로 격리(필수는 아니지만 discovery 혼선 방지).
3. DHCP 예약 고정 (`config/network/dhcp_reservations.md` 문서화):
   - `192.168.0.9` Central PC
   - `192.168.0.3` Main AGV (Pi4)
   - `192.168.0.11` Scout-1
   - `192.168.0.12` Scout-2
   - `192.168.0.20~` Operator laptops
4. 각 노드에 `/etc/hosts` 엔트리 공통 배포(`central`, `main_agv`, `scout_1`, `scout_2`).

### Step 2. 중앙 PC 베이스 구성

1. Ubuntu 22.04 + ROS2 Humble desktop 설치.
2. Docker + Docker Compose 설치.
3. `~/aip_swarm_ws/docker/central/docker-compose.yml`에 다음 서비스 정의:
   - **fastdds-ds**: `fastdds discovery -i 0 -l 192.168.0.9 -p 11811`
   - **uros-agent**: `microros/micro-ros-agent:humble udp4 --port 8888`
   - **foxglove-bridge**: `ros2 run foxglove_bridge foxglove_bridge --port 8765`
   - **rosbag-recorder**: 상시 토픽 기록 (rolling, 24h 리텐션)
   - **influxdb** (선택): 경량 텔레메트리 저장
4. 호스트 네트워크 모드(`network_mode: host`)로 DDS 포트 제약 회피.

### Step 3. FastDDS Discovery Server 설정

Wi-Fi에서 multicast가 불안정한 문제를 해결하고 향후 RMW 스왑도 쉽게 하기 위해 **Unicast Discovery Server 방식**을 전 차량에 강제.

`config/fastdds_discovery_server.xml` 를 `/scout`·`/main`·`/central` 모두에 배포하고 환경변수로 주입:

```bash
export ROS_DISCOVERY_SERVER=192.168.0.9:11811
export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/aip/fastdds_client_profile.xml
export ROS_DOMAIN_ID=42
```

메인 차량(Pi4)의 Docker 컨테이너 `my_ros_env` 실행 시 위 환경변수 추가만 요청(기존 SW 변경 없음).

### Step 4. 공통 메시지 패키지 `aip_fleet_msgs`

```
# FleetHeartbeat.msg
string vehicle_id          # "main" | "scout_1" | "scout_2"
builtin_interfaces/Time stamp
uint8 state                # 0=IDLE 1=AUTO 2=MANUAL 3=ESTOP 4=FAULT
float32 battery_pct
float32 cpu_load
string[] active_behaviors

# OverrideCommand.msg
string vehicle_id          # "*" = 전체
uint8 command              # 0=CLEAR 1=PAUSE 2=RESUME 3=ESTOP 4=MANUAL
geometry_msgs/Twist manual_cmd_vel   # MANUAL일 때만 유효

# AssignMission.srv
string vehicle_id
string mission_type        # "follow" | "patrol" | "goto"
geometry_msgs/PoseStamped target
---
bool accepted
string reason
```

### Step 5. Supervisor & Watchdog 노드 (`aip_fleet_supervisor`)

- **supervisor_node**: 각 차량 `/<ns>/heartbeat`를 2Hz로 수집 → `/fleet/status` (집계) 발행. Foxglove/대시보드가 구독.
- **watchdog_node**: 하트비트가 N초(기본 2.0s) 끊기면 해당 차량에 `OverrideCommand(ESTOP)` 강제 송출.
- **오버라이드 게이트웨이**: `/fleet/override` 토픽 수신 → 해당 차량 네임스페이스의 `/<ns>/override_cmd_vel` 및 `/<ns>/estop`으로 번역.

### Step 6. 차량 측 `twist_mux` 통합(각 차량에서 구동)

모든 차량에 `twist_mux`(또는 파이썬 경량 구현) 배치. 우선순위:

```yaml
topics:
  hw_estop:    { topic: /<ns>/hw_estop_cmd,   priority: 100, timeout: 0.5 }
  central:     { topic: /<ns>/override_cmd_vel, priority: 80, timeout: 1.0 }
  fleet_coord: { topic: /<ns>/coord_cmd_vel,   priority: 50, timeout: 1.0 }
  autonomy:    { topic: /<ns>/auto_cmd_vel,    priority: 10, timeout: 0.5 }
output: /<ns>/cmd_vel
```

메인 차량은 이 mux를 기존 `/cmd_vel` 앞단에 배치하는 것만 요청(차량 SW 담당 팀원과 조율 포인트).

### Step 7. ESP32-S3 Scout 펌웨어 (`firmware/scout_microros`)

- PlatformIO + `micro_ros_platformio` 라이브러리 사용(Humble 호환).
- Transport: `udp4` → Agent `192.168.0.9:8888`.
- 발행: `/<ns>/odom`(경량), `/<ns>/heartbeat`, `/<ns>/battery`, `/<ns>/sensor_raw`.
- 구독: `/<ns>/cmd_vel`, `/<ns>/estop`.
- 네임스페이스는 NVS에 저장해 동일 펌웨어 바이너리를 두 대에 재사용.

### Step 8. Foxglove 대시보드

1. Foxglove Studio(데스크톱 또는 웹) → `ws://192.168.0.9:8765` 접속.
2. 기본 레이아웃 2종 커밋:
   - `fleet_overview.json`: 3D(맵 + 차량 3대 pose) · 배터리 3채널 · `/fleet/status` 테이블 · 열상/카메라 이미지(메인) · E-Stop 버튼.
   - `scout_debug.json`: 단일 scout의 odom/cmd_vel 그래프, 배터리, 센서 raw.
3. **커스텀 패널 2종** (TS):
   - `OverridePanel` → `/fleet/override` 퍼블리시(차량 선택 + 수동 Twist 조이스틱).
   - `EStopPanel` → 큰 빨간 버튼, `OverrideCommand(ESTOP, "*")` 즉시 전송.

### Step 9. 로깅 & 재생

- `rosbag2 record -a --compression-mode file --compression-format zstd` 롤링 버퍼.
- 중요 이벤트(override/estop 발생)는 별도 JSON 로그로 InfluxDB에 동시 기록 → Grafana 추세.

### Step 10. 시뮬 선검증 (하드웨어 도착 전/병행)

`aip_fleet_bringup/launch/fleet_sim.launch.py` 에서 `turtlesim` 3개 인스턴스를 각각 `/main`·`/scout_1`·`/scout_2` 네임스페이스로 구동 → Supervisor/Watchdog/Foxglove 패널이 E2E로 동작함을 먼저 확인 후 하드웨어로 이전.

---

## 수정·신규 대상 파일 요약

| 경로 | 상태 | 담당 경계 |
|---|---|---|
| `~/aip_swarm_ws/` (전체) | 신규 | 본 계획 |
| `~/aip_swarm_ws/docker/central/docker-compose.yml` | 신규 | 본 계획 |
| `~/aip_swarm_ws/config/fastdds_discovery_server.xml` | 신규 | 본 계획 |
| `~/aip_swarm_ws/src/aip_fleet_msgs/**` | 신규 | 본 계획 |
| `~/aip_swarm_ws/src/aip_fleet_supervisor/**` | 신규 | 본 계획 |
| `~/aip_swarm_ws/src/aip_fleet_foxglove_panels/**` | 신규 | 본 계획 |
| `~/aip_swarm_ws/firmware/scout_microros/**` | 신규 | 본 계획 |
| 메인 차량 `my_ros_env` 실행 스크립트에 env 3줄 추가 | 협조 요청 | 차량 SW 담당 |
| 메인 차량 `cmd_vel` 앞단 `twist_mux` 삽입 | 협조 요청 | 차량 SW 담당 |

기존 파일 중 재사용할 항목:
- `/root/colcon_ws/src/rf2o_laser_odometry/launch/rf2o_with_ydlidar.launch.py` (메인 차량측, 이미 compressed-wiggling-spindle.md 계획으로 작성 예정) — `/map`·`/odom`·`/scan` 토픽을 그대로 플릿 그래프에 노출.

---

## 검증 계획 (E2E)

1. **네트워크**: 각 노드에서 `ping central`, `ros2 daemon stop && ros2 topic list` 로 Discovery Server 정상 등록 확인.
2. **시뮬**: `ros2 launch aip_fleet_bringup fleet_sim.launch.py` → Foxglove에서 3대 pose가 뜨고, E-Stop 패널 클릭 시 3대 모두 `/cmd_vel` 0 송출 + `state=ESTOP`.
3. **ESP32 단독**: Scout-1만 전원 켜고 Agent 로그에서 세션 수립, `ros2 topic echo /scout_1/heartbeat` 수신.
4. **3대 동시 + 메인 SLAM**: 메인 차량의 `/map` + `/tf`를 Foxglove 3D에 띄우고 Scout 2대 pose 시각화.
5. **장애 주입**: Scout-1 Wi-Fi 차단 → 2초 내 watchdog이 ESTOP 발령, `/fleet/status` 에 FAULT 반영, 복구 시 자동 재참여.
6. **rosbag 재생**: 기록된 bag를 Foxglove로 offline 재생해 사후 분석 가능성 확인.

---

## 확장성 훅 (미래 작업 예약)

- **RMW 스왑**: `RMW_IMPLEMENTATION=rmw_zenoh_cpp` 전환 시 Discovery Server 구성은 제거되고 zenoh router가 중앙 PC에 올라가는 구조로 대체 — 네임스페이스·QoS는 그대로 유지.
- **SROS2**: `sros2` 키스토어를 `config/security/` 아래에 추가하고 launch에서 `SROS2_SECURITY_ROOT_DIRECTORY` 주입으로 활성화.
- **Scout 업그레이드(RPi급)**: 동일 네임스페이스(`/scout_1`)에서 ROS2 네이티브 노드로 교체만 하면 Supervisor/대시보드 변경 불필요.
- **다중 현장(WAN)**: Zenoh로 전환 후 현장별 router 페어링으로 원격 fleet 운용 가능.
