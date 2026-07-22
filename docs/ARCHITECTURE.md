# ARCHITECTURE.md — AIP Swarm 시스템 아키텍처

> **이 문서는 현재 구현된 코드와 실차 검증 결과를 기준**으로 한다.
> 최종 갱신: 2026-06-23 (세션 11 — aip1 실차 완전 가동 확인)

---

## 0. 전체 구성 한눈에

```
                        Wi-Fi AP: AIP_FLEET (192.168.0.0/24)
                        ROS_DOMAIN_ID=42 / FastDDS Simple Discovery

  dev PC (Ubuntu, 192.168.0.9)
  ┌──────────────────────────────────────────────────────────────┐
  │  aip_swarm_ws (모노레포)                                      │
  │                                                              │
  │  ┌─────────────────────┐   ┌──────────────────────────────┐  │
  │  │  Docker Central      │   │  ros2 launch (직접 실행)     │  │
  │  │  ├─ dashboard_server │   │  ├─ main_agv.launch.py      │  │
  │  │  │  (FastAPI+WS:8080)│   │  │  (SLAM+Nav2+patrol)      │  │
  │  │  ├─ supervisor_node  │   │  │  for aip1                │  │
  │  │  ├─ watchdog_node    │   │  └─ turtlebot3.launch.py    │  │
  │  │  └─ keepout_zone_node│   │     (SLAM+Nav2+patrol)      │  │
  │  └─────────────────────┘   │     for aip2                │  │
  │                             └──────────────────────────────┘  │
  └──────────────────────────────────────────────────────────────┘
            │           DDS UDP (FastDDS Simple Discovery)
            │
   ─────────┼──────────────────────────────────────────────────
            │
  RPi4B — aip1 (192.168.0.3)     RPi4B — aip2 (192.168.0.4)
  ┌──────────────────────────┐    ┌─────────────────────────────┐
  │  fleet_main.launch.py    │    │  turtlebot3.launch.py        │
  │  ├─ ydlidar_ros2_driver  │    │  ├─ turtlebot3_bringup       │
  │  ├─ serial_bridge (ESP32)│    │  │  (OpenCR + LDS-03)        │
  │  ├─ static_tf_publisher  │    │  ├─ slam_toolbox             │
  │  ├─ twist_mux            │    │  ├─ nav2_bringup             │
  │  └─ heartbeat_pub        │    │  ├─ twist_mux                │
  │                          │    │  └─ heartbeat_pub            │
  │  /dev/ydlidar  (ttyUSB0) │    │                              │
  │  /dev/aip_esp32(ttyUSB1) │    │  ⚠️ TF frame_prefix 확인 필요│
  └──────────────────────────┘    └─────────────────────────────┘

  RPi4B — aip3 (192.168.0.5)
  ┌──────────────────────────┐
  │  custom_vehicle.launch.py│
  │  (placeholder — STS3215  │
  │   드라이버 미구현)        │
  └──────────────────────────┘
```

---

## 1. 패키지 구조

```
aip_swarm_ws/src/
├── aip_fleet_msgs          — ROS2 인터페이스 정의 (ament_cmake, rosidl)
├── aip_fleet_supervisor    — 중앙 supervisor + watchdog (Python)
├── aip_fleet_coordinator   — 편대 제어 coordinator (Python)
├── aip_fleet_autonomous    — patrol_node + keepout_zone_node (Python)
├── aip_fleet_dashboard     — FastAPI 대시보드 서버 (Python)
├── aip_fleet_bringup       — 중앙 launch 파일들
├── aip_fleet_real          — 실차 bringup/config ← 이 문서의 핵심
├── aip_fleet_nav           — Nav2/SLAM 설정 (시뮬용)
├── aip_fleet_gazebo        — Gazebo 시뮬 (RPi4B에서는 빌드 제외)
├── aip_fleet_sim           — 2D numpy 시뮬 (RPi4B에서는 빌드 제외)
└── aip_fleet_foxglove_panels — Foxglove TypeScript 패널

firmware/
└── main_agv/               — aip1 ESP32-S3 Arduino 펌웨어
```

---

## 2. 네임스페이스 규약

| 차량 | 네임스페이스 | 플랫폼 | IP | 상태 |
|---|---|---|---|---|
| 메인 AGV | **`aip1`** | RPi4B + ESP32-S3 | 192.168.0.3 | ✅ 운용 중 |
| TurtleBot3 Burger | **`aip2`** | RPi4B | 192.168.0.4 | 🔧 세팅 중 |
| 자작 차량 | **`aip3`** | RPi4B | 192.168.0.5 | 🔧 세팅 중 |
| 중앙 PC (dev PC) | — | Ubuntu | 192.168.0.9 | ✅ 운용 중 |

> ⚠️ 구형 문서의 `main`/`scout_1`/`scout_2` 네임스페이스는 **폐기됨**.
> 모든 코드·설정은 `aip1`/`aip2`/`aip3`를 사용한다.

**플릿 전역**: `/fleet/*` 토픽은 어느 차량에도 속하지 않는 전역 상태/명령.

---

## 3. 완전한 ROS2 토픽 그래프

### 3-1. aip1 (메인 AGV) — 검증 완료

#### RPi4B에서 발행 (fleet_main.launch.py)

| 토픽 | 타입 | 발행 노드 | 주기 | QoS |
|---|---|---|---|---|
| `/aip1/scan` | `sensor_msgs/LaserScan` | ydlidar_ros2_driver_node | 10 Hz | RELIABLE / VOLATILE |
| `/aip1/odom` | `nav_msgs/Odometry` | aip_serial_bridge | 20 Hz | RELIABLE / VOLATILE |
| `/aip1/enc_ticks` | `std_msgs/Int32MultiArray` | aip_serial_bridge | 20 Hz | RELIABLE / VOLATILE |
| `/aip1/cmd_vel` | `geometry_msgs/Twist` | twist_mux (출력) | 20 Hz | RELIABLE / VOLATILE |
| `/aip1/heartbeat` | `aip_fleet_msgs/FleetHeartbeat` | heartbeat_pub | 2 Hz | RELIABLE / VOLATILE |
| `/aip1/servo_cmd` | `std_msgs/UInt8MultiArray` | (dashboard) | 수동 | RELIABLE |
| `/aip1/esp32_reset` | `std_msgs/Empty` | (dashboard) | 수동 | RELIABLE |
| `/aip1/esp32_beep` | `std_msgs/UInt8MultiArray` | (dashboard) | 수동 | RELIABLE |

#### RPi4B에서 수신 (fleet_main.launch.py twist_mux 입력)

| 토픽 | 타입 | 발행원 | 우선순위 |
|---|---|---|---|
| `/aip1/override_cmd_vel` | `geometry_msgs/Twist` | dashboard / supervisor | 80 (central) |
| `/aip1/coord_cmd_vel` | `geometry_msgs/Twist` | fleet_coordinator | 50 |
| `/aip1/stuck_escape_cmd_vel` | `geometry_msgs/Twist` | stuck_escape_node | 15 |
| `/aip1/autonomy_cmd_vel` | `geometry_msgs/Twist` | Nav2 (dev PC) | 10 |
| `/aip1/estop` | `std_msgs/Bool` | supervisor / dashboard | lock(90) |

#### dev PC에서 발행 (main_agv.launch.py)

| 토픽 | 타입 | 발행 노드 | 설명 |
|---|---|---|---|
| `/map` | `nav_msgs/OccupancyGrid` | slam_toolbox | SLAM 맵 (TRANSIENT_LOCAL) |
| `/aip1/plan` | `nav_msgs/Path` | Nav2 planner | 경로 계획 |
| `/aip1/trajectories` | `visualization_msgs/MarkerArray` | Nav2 MPPI | MPPI 궤적 시각화 |
| `/aip1/patrol_path_viz` | `visualization_msgs/MarkerArray` | patrol_node | 순찰 경로 시각화 |
| `/aip1/patrol_status` | `std_msgs/String` (JSON) | patrol_node | 순찰 상태 |
| `/aip1/global_costmap/costmap` | `nav_msgs/OccupancyGrid` | Nav2 | 전역 비용맵 |
| `/aip1/local_costmap/costmap` | `nav_msgs/OccupancyGrid` | Nav2 | 지역 비용맵 |

#### aip1 TF 체인

```
map
 └── odom                    ← slam_toolbox 동적 (dev PC, main_agv.launch.py)
      └── base_footprint     ← serial_bridge 동적 (RPi4B)
           └── base_link     ← static_transform_publisher (fleet_main: z=0.060m)
                └── laser_link ← static_transform_publisher (fleet_main: z=0.160m)
```

> ⚠️ **FastDDS TRANSIENT_LOCAL 다중 호스트 이슈**: `/tf_static` 이 RPi→dev PC 로 전달되지 않는 알려진 문제.
> 해결책: `main_agv.launch.py`에서 dev PC가 동일한 static TF를 재발행.

---

### 3-2. aip2 (TurtleBot3 Burger) — 세팅 중

#### RPi4B에서 발행 (turtlebot3.launch.py)

| 토픽 | 타입 | 발행 노드 | 주기 |
|---|---|---|---|
| `/aip2/scan` | `sensor_msgs/LaserScan` | turtlebot3_bringup (LDS-03) | 5 Hz |
| `/aip2/odom` | `nav_msgs/Odometry` | turtlebot3_bringup (OpenCR) | 20 Hz |
| `/aip2/imu` | `sensor_msgs/Imu` | turtlebot3_bringup | 40 Hz |
| `/aip2/heartbeat` | `aip_fleet_msgs/FleetHeartbeat` | heartbeat_pub | 2 Hz |
| `/aip2/plan` | `nav_msgs/Path` | Nav2 planner | — |
| `/aip2/trajectories` | `visualization_msgs/MarkerArray` | Nav2 MPPI | — |

#### aip2 twist_mux 입력 (동일 우선순위 체인)

| 토픽 | 우선순위 |
|---|---|
| `/aip2/override_cmd_vel` | 80 (central) |
| `/aip2/coord_cmd_vel` | 50 |
| `/aip2/autonomy_cmd_vel` | 10 (Nav2) |
| `/aip2/estop` | lock(90) |

#### aip2 TF 체인

```
map
 └── aip2/odom              ← slam_toolbox 동적
      └── aip2/base_footprint ← turtlebot3_bringup (OpenCR)
           └── aip2/base_link
                └── aip2/base_scan ← LDS-03 드라이버
```

> ⚠️ **CAVEAT**: TurtleBot3 기본 bringup은 TF 프레임을 prefix 없이 (`odom`/`base_link`/`base_scan`) 발행한다.
> `turtlebot3.launch.py` 상단 CAVEAT 참조. `frame_prefix:=aip2/` 를 TB3 bringup에 전달하거나
> slam_toolbox/nav2 config에서 prefix 없는 프레임명을 사용하도록 맞춰야 한다.
> **aip2 담당 팀원이 실차 테스트 후 결정할 항목.**

---

### 3-3. aip3 (자작 차량) — Placeholder

현재 `custom_vehicle.launch.py`는 placeholder. STS3215 서보 드라이버 미구현.
실차 연결 시 아래를 참고하여 config/custom_vehicle/ 파일 작성.

예상 토픽 (드라이버 구현 후):

| 토픽 | 타입 |
|---|---|
| `/aip3/scan` | `sensor_msgs/LaserScan` |
| `/aip3/odom` | `nav_msgs/Odometry` |
| `/aip3/cmd_vel` | `geometry_msgs/Twist` |
| `/aip3/heartbeat` | `aip_fleet_msgs/FleetHeartbeat` |

---

### 3-4. 플릿 전역 토픽 (`/fleet/*`)

| 토픽 | 타입 | 발행 | 구독 | QoS |
|---|---|---|---|---|
| `/fleet/status` | `aip_fleet_msgs/FleetStatus` | supervisor_node | watchdog, dashboard | RELIABLE / TRANSIENT_LOCAL(1) |
| `/fleet/override` | `aip_fleet_msgs/OverrideCommand` | dashboard, watchdog | supervisor_node | RELIABLE / VOLATILE(10) |
| `/fleet/alerts` | `aip_fleet_msgs/PerceptionAlert` | patrol_monitor | dashboard | RELIABLE / VOLATILE |
| `/fleet/peer_poses` | `aip_fleet_msgs/PeerPoseArray` | (시뮬: sim_pose_relay) | dashboard, coordinator | RELIABLE / TRANSIENT_LOCAL(1) |
| `/fleet/coverage_pct` | `std_msgs/String` (JSON) | keepout_zone_node | dashboard | RELIABLE / VOLATILE |
| `/fleet/keepout_zones` | `std_msgs/String` (JSON) | dashboard | keepout_zone_node | RELIABLE / VOLATILE |
| `/fleet/control_lock` | `std_msgs/String` (JSON) | dashboard | supervisor | RELIABLE / TRANSIENT_LOCAL(1) |
| `/fleet/map_ready` | `std_msgs/Bool` | dashboard | coordinator | RELIABLE / TRANSIENT_LOCAL(1) |

---

### 3-5. 맵 토픽

| 토픽 | 발행 | 설명 |
|---|---|---|
| `/map` | slam_toolbox (aip1, dev PC) | 실차 SLAM 맵 — dashboard 기본 소스 |
| `/map_static` | map_server (시뮬) | 시뮬 전용 공유 맵 — 실차에서는 없음 |
| `/aip1/map` | (relay, 옵션) | aip1 전용 맵 relay |
| `/fleet/keepout_cloud` | keepout_zone_node | Nav2 costmap 장애물 레이어 |

---

## 4. cmd_vel 우선순위 체인 (모든 차량 공통)

```
입력 (우선순위 높은 순)                      twist_mux 출력
                                                    │
  /{vid}/estop_lock     (lock, priority 90) ─ 🔒 lock
  /{vid}/override_cmd_vel  (priority 80)  ─────┐
  /{vid}/coord_cmd_vel     (priority 50)  ─────┤
  /{vid}/stuck_escape_cmd_vel (priority 15) ───┤──► /{vid}/cmd_vel ──► 모터
  /{vid}/autonomy_cmd_vel  (priority 10)  ─────┘
```

| 슬롯 | 우선순위 | 발행원 | 용도 |
|---|---|---|---|
| `estop_lock` | 90 (lock) | supervisor_node | E-Stop 잠금 (활성화 시 전체 모션 차단) |
| `central` | 80 | dashboard / 원격 조작 | 원격 수동 조종 (`override_cmd_vel`) |
| `fleet_coord` | 50 | coordinator_node | 편대 주행 명령 (`coord_cmd_vel`) |
| `stuck_escape` | 15 | stuck_escape_node | 고착 탈출 (`stuck_escape_cmd_vel`) |
| `autonomy` | 10 | Nav2 | 자율주행 (`autonomy_cmd_vel`) |

> ⚠️ `estop_lock`은 발행자(supervisor_node)가 없으면 **항상 locked** 상태가 된다.
> `twist_mux.yaml` 의 locks 섹션은 supervisor_node 연동 전까지 주석 처리.

---

## 5. 데이터 파이프라인

### 5-A. aip1 정상 자율주행

```
[YDLidar TG15]         [ESP32-S3]
     │ /aip1/scan           │ /aip1/odom, /aip1/enc_ticks
     │                      │ TF: odom→base_footprint
     └──────────┬───────────┘
                │
         (DDS over Wi-Fi)
                │
         [dev PC — main_agv.launch.py]
                │
         [slam_toolbox]                    [Nav2 navigation_launch]
         /aip1/scan → /map                 /map + /aip1/scan
         TF: map→odom                      → /aip1/autonomy_cmd_vel (autonomy:10)
                │                                   │
                └───────────────────────────────────┘
                                                     │
                                              (DDS over Wi-Fi)
                                                     │
                                          [RPi4B — twist_mux]
                                                     │
                                            /{aip1}/cmd_vel
                                                     │
                                             [ESP32-S3 모터]
```

### 5-B. 웹 대시보드 ↔ 차량

```
[브라우저: http://localhost:8080]
        │ WebSocket (/ws)
        ▼
[dashboard_server.py (FastAPI)]
        │ rclpy 구독/발행
        ▼
  ┌─────────────────────────────────────────────────────────┐
  │  구독: /map, /aip1~3/odom, /aip1~3/heartbeat            │
  │        /fleet/status, /fleet/peer_poses, /fleet/alerts  │
  │        TF buffer (map→base_link 위치 조회)               │
  │                                                          │
  │  발행: /{vid}/override_cmd_vel  (WASD 드라이브)          │
  │        /{vid}/estop             (E-Stop)                 │
  │        /{vid}/goal_pose         (이동 목표)               │
  │        /fleet/keepout_zones     (금지구역)               │
  │        /patrol_planner/cmd      (순찰 제어)              │
  └─────────────────────────────────────────────────────────┘
```

### 5-C. 비상정지 (E-Stop) 루프

```
[dashboard/감시자]
    │
    ▼
/fleet/override  →  [supervisor_node]
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        /aip1/estop  /aip2/estop  /aip3/estop
        (Bool True)
              │
              ▼
        [twist_mux locks: estop_lock]
              │
       모든 모션 차단 (/cmd_vel = 0)
```

---

## 6. QoS 매트릭스

| 카테고리 | 토픽 예 | Reliability | Durability | Depth |
|---|---|---|---|---|
| 고주파 센서 | `odom`, `scan` | RELIABLE | VOLATILE | 5~10 |
| 제어 명령 | `cmd_vel`, `override_cmd_vel`, `estop` | RELIABLE | VOLATILE | 10 |
| 플릿 상태 (latched) | `/fleet/status`, `/map`, `peer_poses` | RELIABLE | TRANSIENT_LOCAL | 1 |
| 하트비트 | `/{vid}/heartbeat` | RELIABLE | VOLATILE | 10 |
| 맵 (SLAM) | `/map`, `global_costmap/costmap` | RELIABLE | TRANSIENT_LOCAL | 1 |
| TF | `/tf` | RELIABLE | VOLATILE | 100 |
| TF static | `/tf_static` | RELIABLE | TRANSIENT_LOCAL | — |

> `/aip1/odom`은 serial_bridge가 RELIABLE로 발행. `ros2 topic echo`의 기본 BEST_EFFORT와
> QoS 불일치로 수신 안 될 수 있음. `--qos-reliability reliable` 옵션 사용.

---

## 7. TF 구조 비교

| 차량 | `odom` 프레임 | `base` 프레임 | `laser` 프레임 | 발행 노드 |
|---|---|---|---|---|
| aip1 | `odom` | `base_footprint` → `base_link` | `laser_link` | serial_bridge, fleet_main static_tf |
| aip2 | `aip2/odom` | `aip2/base_footprint` → `aip2/base_link` | `aip2/base_scan` | TB3 bringup (CAVEAT 확인) |
| aip3 | `aip3/odom` | `aip3/base_link` | `aip3/laser_link` | 드라이버 구현 후 결정 |

> **aip1 특이사항**: fleet_main.launch.py의 RSP가 `frame_prefix=''`로 실행되므로
> TF 프레임에 네임스페이스가 없다. dashboard_server.py의 TF 조회 분기 처리 참조.

---

## 8. DDS 통신 구성

```
dev PC (192.168.0.9)                RPi4B(s)
ROS_DOMAIN_ID=42                    ROS_DOMAIN_ID=42
rmw_fastrtps_cpp                    rmw_fastrtps_cpp
FastDDS Simple Discovery            FastDDS Simple Discovery
        │                                   │
        └─────────────── UDP ───────────────┘
                    (동일 서브넷 자동 탐색)
```

**검증 결과 (2026-06-23)**: FastDDS Simple Discovery만으로 동일 서브넷(192.168.0.0/24) 내 통신 정상.
Discovery Server(DS)는 이기종 네트워크/VPN 연결 시에만 필요.

`.env` 에서 `ROS_DOMAIN_ID=42` 설정 필요. Discovery Server 주소는 `192.168.0.9:11811`.

---

## 9. launch 파일 진입점 정리

### 실차 운용

| 실행 위치 | 명령 | 역할 |
|---|---|---|
| RPi4B (aip1) | `ros2 launch aip_fleet_real fleet_main.launch.py` | aip1 HW 드라이버 |
| RPi4B (aip2) | `ros2 launch aip_fleet_real turtlebot3.launch.py` | aip2 TB3 bringup+SLAM+Nav2 |
| RPi4B (aip3) | `ros2 launch aip_fleet_real custom_vehicle.launch.py` | aip3 (placeholder) |
| dev PC (aip1) | `ros2 launch aip_fleet_real main_agv.launch.py` | SLAM+Nav2+patrol for aip1 |
| dev PC (통합) | `ros2 launch aip_fleet_real fleet_real.launch.py` | 여러 차량 선택 기동 |

### 중앙 관제

```bash
# Docker Central 스택 (dashboard + supervisor + keepout_zone)
cd ~/aip_swarm_ws/docker/central && docker compose up -d
# 대시보드: http://localhost:8080
```

### 시뮬 (개발 PC)

```bash
source ~/.bash_aliases && aip sim
aip_auto_patrol   # SLAM + Nav2 + 3대 자율 순찰
```

---

## 10. 표준 차량 인터페이스 (계약)

모든 차량은 다음 인터페이스를 **동일하게** 노출해야 한다.
상위 스택(coordinator, autonomous, dashboard)은 이 인터페이스만 바라본다.

```
출력  /{vid}/scan             sensor_msgs/LaserScan      — LiDAR
출력  /{vid}/odom             nav_msgs/Odometry          — 오도메트리
출력  /{vid}/heartbeat        aip_fleet_msgs/FleetHeartbeat — 생존 신호 (2Hz)
입력  /{vid}/cmd_vel          geometry_msgs/Twist        — twist_mux 최종 출력
입력  /{vid}/override_cmd_vel geometry_msgs/Twist        — 원격 수동 조종 (priority 80)
입력  /{vid}/autonomy_cmd_vel geometry_msgs/Twist        — Nav2 입력 (priority 10)
입력  /{vid}/estop            std_msgs/Bool              — 비상정지
TF    map → {odom} → {base}  → {laser}                  — 위치 추정 체인
```

`{vid}` ∈ {`aip1`, `aip2`, `aip3`}

---

## 11. 알려진 이슈 및 주의사항

| 이슈 | 증상 | 원인 | 해결책 |
|---|---|---|---|
| FastDDS TRANSIENT_LOCAL 다중 호스트 | `/tf_static` RPi→dev PC 미수신 | FastDDS Simple Discovery의 알려진 동작 | dev PC에서 static TF 재발행 (main_agv.launch.py에 구현됨) |
| serial_bridge QoS | `ros2 topic echo /aip1/odom` 수신 안 됨 | RELIABLE 발행 + BEST_EFFORT 구독 불일치 | `--qos-reliability reliable` 옵션 사용 |
| nohup 비대화형 쉘 | `ros2: command not found` | `.bashrc` guard (`[ -z "$PS1" ] && return`) | explicit source 경로 사용 (REAL_VEHICLE_OPERATION.md §3-3 참조) |
| aip2 TF frame_prefix | SLAM `map↔base` 변환 실패 | TB3 bringup이 prefix 없이 TF 발행 | turtlebot3.launch.py CAVEAT 참조 — 담당 팀원 결정 필요 |
| estop_lock twist_mux | 발행자 없이 활성화 시 항상 locked | twist_mux lock: 구독자 없으면 타임아웃=locked | supervisor_node 연동 전까지 주석 처리 |
