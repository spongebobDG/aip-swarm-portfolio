# REAL_VEHICLE_OPERATION.md — 메인 차량 실차 운용 가이드

> **대상**: RPi4B(IP: 192.168.0.3)에 탑재된 메인 차량(`aip1`)
> **상태 기준**: 2026-06-22 — `fleet_main.launch.py` 를 `aip_swarm_ws/aip_fleet_real` 로 통합
> _(이전: `~/aip_ws` 의 `aip_bringup` 패키지 — **더 이상 사용하지 않음**)_
>
> 설치/환경 구성은 `docs/SETUP_RPI4.md` 참고. 이 문서는 **이미 설치된 환경에서 실행·테스트** 순서를 다룬다.

---

## 1. 시스템 구성 한눈에

```
dev PC (Ubuntu, 192.168.0.9)            RPi4B — AIP (192.168.0.3)
┌────────────────────────────┐           ┌───────────────────────────────┐
│  aip_swarm_ws/             │   WiFi    │  ~/aip_swarm_ws/              │
│  ROS_DOMAIN_ID=42          │◄─────────►│  ROS_DOMAIN_ID=42             │
│  FastDDS Simple Discovery  │           │  FastDDS Simple Discovery     │
└────────────────────────────┘           │  (~/aip_ws 폴더 존재하지만     │
                                         │   더 이상 실행하지 않음)       │
                                         │  /dev/ydlidar  → ttyUSB0      │
                                         │  /dev/aip_esp32→ ttyUSB1      │
                                         │                               │
                                         │  ┌─────────────────────────┐  │
                                         │  │ fleet_main.launch.py    │  │
                                         │  │  (aip_fleet_real 패키지) │  │
                                         │  │  ├─ ydlidar_driver      │  │
                                         │  │  ├─ tf static×2         │  │
                                         │  │  ├─ aip_serial_bridge   │  │
                                         │  │  ├─ twist_mux           │  │
                                         │  │  └─ heartbeat_pub       │  │
                                         │  └─────────────────────────┘  │
                                         └───────────────────────────────┘
```

### USB 장치 매핑

| 심링크 | 물리 장치 | 칩 | 역할 |
|--------|-----------|-----|------|
| `/dev/ydlidar` | `ttyUSB0` | CP210x | YDLidar TG15 (512000 baud) |
| `/dev/aip_esp32` | `ttyUSB1` | CP210x | ESP32-S3 serial_bridge (115200 baud) |

udev 규칙: `/etc/udev/rules.d/99-aip.rules` (USB 포트 위치 고정, 재플러그 후 자동 재적용)

---

## 2. SSH 접속

```bash
# dev PC에서
ssh jh@192.168.0.3
# SSH 키: ~/.ssh/id_ed25519 (dev PC에 등록됨, 비밀번호 불필요)
```

RPi가 안 보이면:
```bash
ping 192.168.0.3                     # 응답 없으면 전원/네트워크 확인
sudo nmap -sn 192.168.0.0/24        # 전체 스캔으로 IP 재확인
```

---

## 3. 실차 기동 순서

### 3-1. 환경 소싱 (RPi 터미널마다 필수)

```bash
source /opt/ros/humble/setup.bash
source ~/aip_swarm_ws/install/setup.bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DOMAIN_ID=42
```

> `~/.bashrc` 에 추가해 두면 매번 입력 불필요 (SETUP_RPI4.md §7 참고).

### 3-2. 프로세스 정리 (재기동 전 필수)

```bash
pkill -9 -f "ros2 launch|ydlidar_ros2|twist_mux|heartbeat_pub|serial_bridge|static_transform"
sleep 2
```

### 3-3. fleet_main 기동

```bash
# 전체 기동 (드라이버 + 위치추정 + Nav2 + 순찰). 기본 localization:=slam(매핑).
# ⚠️ 평상 운영은 저부하 AMCL 모드 권장 → 7장 참조:
#    ros2 launch aip_fleet_real fleet_main.launch.py localization:=amcl \
#        map_yaml:=/home/jh/aip_maps/latest_fleet_map.yaml
ros2 launch aip_fleet_real fleet_main.launch.py

# ESP32 없이 YDLidar + TF만 (LiDAR 단독 테스트):
ros2 launch aip_fleet_real fleet_main.launch.py with_base:=false
```

> 부팅 중 SSH·heartbeat 가 끊겼다면 **위치추정+Nav2 동시 기동 부하** 때문이다.
> launch 에 staggering 이 반영돼 있고, 운영 모드(AMCL)·부하 완화 상세는 **7장**을 볼 것.

> **nohup 백그라운드 실행 (비대화형 쉘 — SSH 원격 실행 등):**
> ```bash
> nohup bash -c "
>   export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
>   export ROS_DOMAIN_ID=42
>   source /opt/ros/humble/setup.bash
>   source /home/jh/aip_swarm_ws/install/setup.bash
>   ros2 launch aip_fleet_real fleet_main.launch.py
> " > /tmp/fleet_main.log 2>&1 </dev/null &
> tail -f /tmp/fleet_main.log
> ```
> *주의: `source ~/.bashrc`는 비대화형 쉘에서 guard(`[ -z "$PS1" ] && return`)로 인해 early return됨. 반드시 위처럼 경로를 직접 지정.*

### 3-4. 정상 기동 확인

약 3초 후:

```bash
ros2 node list
# 기대 출력:
# /aip1/aip_serial_bridge
# /aip1/heartbeat_pub
# /aip1/tf_base_footprint_to_base_link  (static_transform_publisher)
# /aip1/tf_base_link_to_laser_link      (static_transform_publisher)
# /aip1/twist_mux
# /aip1/ydlidar_ros2_driver_node

ros2 topic list | grep aip1
# 기대 토픽:
# /aip1/cmd_vel          ← twist_mux 출력 (ESP32 모터 입력)
# /aip1/enc_ticks        ← ESP32 엔코더 누적 틱 (Int32MultiArray)
# /aip1/heartbeat        ← 2Hz FleetHeartbeat
# /aip1/odom             ← serial_bridge 계산 Odometry
# /aip1/scan             ← YDLidar 10Hz LaserScan
```

---

## 4. 발행 채널 구조 (cmd_vel 우선순위)

```
/aip1/override_cmd_vel  (priority 80) ─┐
/aip1/coord_cmd_vel     (priority 50) ─┼─► twist_mux ─► /aip1/cmd_vel ─► ESP32 모터
/aip1/autonomy_cmd_vel  (priority 10) ─┘
                   (estop_lock lock priority 90 — supervisor 발행 시 활성화)
```

| 채널 | 발행원 | 용도 |
|------|--------|------|
| `/aip1/override_cmd_vel` | dev PC dashboard/supervisor | 원격 수동 제어 |
| `/aip1/coord_cmd_vel` | fleet coordinator | 편대 제어 |
| `/aip1/autonomy_cmd_vel` | Nav2 (dev PC main_agv.launch) | 자율주행 |

---

## 5. 수동 구동 테스트

```bash
# dev PC 또는 RPi에서 (환경변수 설정 후)

# 직진 테스트 (0.1 m/s, 5초)
ros2 topic pub /aip1/autonomy_cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.1, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}" \
  --rate 10 --times 50

# 엔코더 틱 실시간 확인
ros2 topic echo /aip1/enc_ticks

# Odom 확인
ros2 topic echo /aip1/odom --field pose.pose.position
```

> 바퀴가 회전하면서 `/aip1/enc_ticks`의 data[0](L), data[1](R)이 변화해야 한다.
> 직진 시 둘 다 양수 증가, 좌회전 시 L 감소/R 증가.

---

## 6. 서보암 테스트

```bash
# fleet_main 실행 중 ROS 토픽으로 제어
ros2 topic pub /aip1/servo_cmd std_msgs/msg/UInt8MultiArray \
  "{data: [90, 90, 90, 90]}" --once

# ESP32 리셋
ros2 topic pub --once /aip1/esp32_reset std_msgs/msg/Empty "{}"

# 비프음 패턴 테스트 (0=단음 1=이중 2=부팅 3=오류)
ros2 topic pub --once /aip1/esp32_beep std_msgs/msg/UInt8MultiArray "{data: [1]}"
```

서보 각도 기준:
- BOOT 자세: `(90, 60, 90, 125)` — 기동 시 자동 이동
- PARK 자세: `(90, 0, 0, 90)` — 정렬/종료 자세

---

## 7. 위치추정 + Nav2 기동 (운영 모드 / 매핑 모드)

> **2026-06-27 갱신** — 부하·SSH 안정화 + 위치추정 모드 도입.
> `fleet_main.launch.py` 가 위치추정(slam/amcl)·Nav2·순찰까지 **온보드 통합**한다.

### 7-0. 왜 부팅 중 SSH 가 끊겼는가 (부하 원인)

Nav2 라이프사이클(8+ 노드)과 SLAM 을 **동시에** 활성화하면 RPi4B(Cortex-A72 4코어)가
수~십수 초간 CPU/IO 포화 상태가 되어 SSH·heartbeat 가 타임아웃된다(2026-06-27 전 차량 증상).

**완화책(이미 launch 에 반영):**
- **기동 staggering** — 드라이버·twist_mux(t=0) → 위치추정(t≈2) → Nav2(t≈7) → 순찰(t≈8)
  로 시차 기동해 스파이크를 분산. (`fleet_main`·`turtlebot3`·`custom_vehicle` launch 공통)
- **운영 시 SLAM→AMCL** — 아래 7-1. SLAM 매핑은 CPU 부하가 크므로 맵 제작 시에만 사용하고,
  평상 운영은 저장맵+AMCL(저부하)로 한다.

### 7-1. 위치추정 모드 (localization 인자)

| 모드 | 용도 | 부하 | 명령 |
|---|---|---|---|
| `slam` | 맵 **제작** (1회) | 높음 | `fleet_main.launch.py localization:=slam` |
| `amcl` | **운영**(미션) 기본 | 낮음 | `fleet_main.launch.py localization:=amcl map_yaml:=<경로>` |
| `none` | 외부/오프보드 compute | 없음 | `fleet_main.launch.py localization:=none with_nav2:=false` |

두 모드 모두 `/map` 과 `map→odom` TF 를 제공하므로 **Nav2 설정·다운스트림은 동일**하다.

> **AMCL 운영이 미션 정합성에도 유리**: 라이브 SLAM 은 재기동마다 맵 원점이 흔들려
> 저장된 웨이포인트/금지구역 좌표가 깨질 수 있다. 저장맵+AMCL 은 좌표계가 고정되어
> 운영자 미션(웨이포인트·순찰·금지구역)이 재부팅 후에도 유효하다.

### 7-2. 표준 운영 플로우

```bash
# (A) 최초 1회 — 맵 제작 (SLAM):
ros2 launch aip_fleet_real fleet_main.launch.py localization:=slam
#   환경을 한 바퀴 주행시켜 맵을 채운 뒤 저장:
ros2 service call /aip1/slam_toolbox/save_map slam_toolbox/srv/SaveMap \
  "{name: {data: '/home/jh/aip_maps/latest_fleet_map'}}"
#   (대시보드 '맵 저장' 버튼도 동일 경로 ~/aip_maps/latest_fleet_map.* 로 저장)

# (B) 평상 운영 — 저장맵 + AMCL + Nav2 (저부하, 권장 기본):
ros2 launch aip_fleet_real fleet_main.launch.py localization:=amcl \
  map_yaml:=/home/jh/aip_maps/latest_fleet_map.yaml with_patrol:=false

# (C) 순찰 자동 시작:
ros2 launch aip_fleet_real fleet_main.launch.py localization:=amcl \
  map_yaml:=/home/jh/aip_maps/latest_fleet_map.yaml with_patrol:=true
```

> `use_sim_time` 은 반드시 `false` (실차). 실수로 `true` 설정 시 모든 노드가 frozen 됨.

### 7-3. 미션 제어(수동 운영) 활성화 — 중앙 PC

운영자 주도 미션(웨이포인트·순찰)이 대시보드에서 동작하려면 **위치추정 검증 후**
중앙 대시보드의 자율주행 게이트를 열어야 한다(안전 장치, 기본 비활성):

```bash
# 중앙 PC — 대시보드 기동 환경에 설정 (localization 수렴 확인 후):
export AIP_NAV_ALLOWED_IDS=aip1,aip2,aip3   # 또는 '*'
```

- 금지구역(keepout) — ✅ **자율주행 경로 차단 구현됨**(2026-06-27): 대시보드 폴리곤이
  ① 목표점 거부 + ② **costmap 장애물 주입**(`keepout_zone_node`→`/fleet/keepout_cloud`→
  각 차량 nav2 obstacle_layer)으로 **Nav2 자율 경로(자율 매핑/탐사·순찰·이동)가 위험구역을 회피**한다.
  - 중앙 스택에 `keepout_zone_node` 자동 기동(`central.launch.py with_keepout:=true` 기본).
  - 구역 그리기→`ros2 topic echo /fleet/keepout_cloud`(점 발행) 확인→자율 goal 이 우회/진입거부되는지 확인.
  - ⚠️ **수동 teleop 은 costmap 게이트 아님**(twist_mux central 우회) → 수동 주행 시엔 운영자가 직접 회피.
  - 부하: `clearing:False`(마킹만)이라 RPi4B 영향 적고, 구역 없으면 무부하. 상세 `docs/ANALYSIS.md §B`.

### 7-4. (대안) 오프보드 compute — RPi 부하 최소화

RPi 부하를 더 줄이려면 위치추정·Nav2 를 dev PC 에서 돌리는 분리 모델도 가능하다
(`localization:=none with_nav2:=false` 로 RPi 는 드라이버만, dev PC 에서 `main_agv.launch.py`).
단 WiFi 너머 costmap/scan 스트리밍·TRANSIENT_LOCAL 전달 신뢰성 이슈가 있어
**온보드 AMCL(7-2 B) 를 우선 권장**한다.

### 7-5. ⚠️ ESTOP 안전 — 자율주행 중 래치 활성화 (실차 검증 후)

**현재 한계**: 대시보드 ESTOP 은 supervisor 를 통해 0속도 1회 + `estop_lock=True` 를
발행하지만, 차량 `twist_mux.yaml` 의 `estop_lock` **락이 비활성(주석)** 이라 priority-90
래치가 걸리지 않는다. 따라서:
- **수동 모드**: 정지함(0속도 + 경쟁 autonomy 없음).
- **Nav2 상시 가동(운영 모드)**: ESTOP 후 0.5s 만에 Nav2 가 재개될 수 있다 → **위험**.

**활성화 절차(차량 연결 후 1회):**
```bash
# ① 중앙 스택 기동 후 supervisor 가 estop_lock 을 정상 발행하는지 확인 (평상시 False):
ros2 topic echo /aip1/estop_lock      # 평상 data: false 가 주기적으로 와야 함
#   ⚠️ False 가 안 오면 활성화 금지 — 항상 locked 되어 차량이 전혀 안 움직인다.
# ② 각 차량 twist_mux.yaml 의 'locks: estop_lock:' 블록 주석 해제 후 twist_mux 재기동.
# ③ 검증: 평상 주행 OK → 대시보드 ESTOP → 즉시·지속 정지 확인 →
#         해제(CLEAR/release) 후 정상 재개 확인.
```
관련 파일: `config/main_agv/twist_mux.yaml`, `config/turtlebot3/twist_mux.yaml`
(aip3 는 차량 컨테이너 내 twist_mux 설정에 동일 적용). SSOT 분석: `docs/ANALYSIS.md §D`.

---

## 8. dev PC ↔ RPi DDS 통신 검증

```bash
# dev PC에서 RPi 토픽 수신 확인
source ~/aip_swarm_ws/install/setup.bash   # 또는: source ~/.bash_aliases && aip
ros2 topic echo /aip1/heartbeat            # 2Hz FleetHeartbeat 출력되면 통신 정상
ros2 topic hz /aip1/scan                  # ~10Hz면 YDLidar 정상
```

---

## 9. 자주 발생하는 문제

### 증상: 노드가 여러 개 중복 뜸 (duplicate node 경고)

**원인**: 이전 launch 프로세스가 완전히 종료되기 전에 재실행.

**해결**:
```bash
pkill -9 -f "ros2 launch|ydlidar_ros2|twist_mux|heartbeat_pub|robot_state_pub|serial_bridge"
sleep 3   # 충분히 대기
# 이후 재실행
```

### 증상: serial_bridge "serial open failed"

**원인**: `/dev/aip_esp32` 심링크가 없거나 포트가 다른 프로세스에 점유됨.

**확인 및 해결**:
```bash
ls -la /dev/aip_esp32 /dev/ttyUSB*   # 심링크 존재 확인
fuser /dev/aip_esp32                   # 점유 프로세스 확인
# servo_test.py 등이 열고 있으면 종료
```

### 증상: YDLidar "Checksum error" 다수 출력

**원인**: 시작 직후 intensity 모드 자동 조정 과정에서 정상 발생. "Lidar has started!" 이후 자동 해소. **무해함.**

### 증상: `ros2 topic list`에 /main/ 토픽이 안 보임 (dev PC)

**원인**: `RMW_IMPLEMENTATION` 또는 `ROS_DOMAIN_ID` 불일치.

**해결**:
```bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DOMAIN_ID=42
ros2 topic list   # 재확인
```

---

## 10. RPi 워크스페이스 파일 구조

```
~/aip_ws/src/
├── aip_bringup/
│   ├── config/
│   │   ├── twist_mux_main.yaml    ← twist_mux 우선순위 설정
│   │   └── ydlidar_tg15.yaml      ← YDLidar TG15 파라미터 (/**  키로 namespace 무관 적용)
│   ├── launch/
│   │   ├── fleet_main.launch.py   ← 메인 진입점 (namespace='main' 래핑)
│   │   ├── robot.launch.py        ← RSP + YDLidar + serial_bridge (with_base 옵션)
│   │   └── ydlidar.launch.py      ← YDLidar 단독 런치
│   └── scripts/
│       └── heartbeat_pub.py       ← 1Hz /main/heartbeat 발행
├── aip_base/
│   ├── aip_base/
│   │   └── serial_bridge.py       ← ESP32 UART 브릿지 (0xAA/0x55 프로토콜)
│   └── launch/
│       └── base.launch.py         ← serial_bridge 단독 런치
├── aip_description/
│   ├── launch/rsp.launch.py
│   └── urdf/aip.urdf.xacro        ← 차량 URDF
├── aip_navigation2/
│   ├── config/nav2_params.yaml    ← Nav2 파라미터 (use_sim_time 확인!)
│   └── launch/
│       ├── localization.launch.py
│       └── navigation.launch.py
├── aip_slam/
│   ├── config/slam_toolbox.yaml
│   └── launch/slam.launch.py
├── servo_test.py                   ← 서보암 단독 테스트 스크립트
└── yaw_accum.py                    ← IMU yaw 누적 테스트 유틸
```

---

## 11. ESP32 serial_bridge 프로토콜 요약

`aip_base/aip_base/serial_bridge.py` ↔ ESP32 펌웨어 (115200 baud, 8N1)

```
프레임: [0xAA][0x55][type][payload...][XOR 체크섬 (type+payload XOR)]

방향          type  payload            주기    내용
RPi→ESP32     0x01  2×float32 LE      20Hz   linear.x [m/s], angular.z [rad/s]
ESP32→RPi     0x02  2×int32 LE        20Hz   enc_L, enc_R 누적 틱
RPi→ESP32     0x03  4×uint8           변화시  서보 각도 0-180 (J1~J4)
ESP32→RPi     0x04  4×uint8           20Hz   현재 서보 각도
ESP32→RPi     0x05  uint32+4×uint16   1Hz    uptime_ms, flags, bad_pkts, loop_hz, heap_kb
RPi→ESP32     0x06  1×uint8           수동    SERVO_RELEASE (0=park+detach)
```

엔코더 부호 규약: 전진→L(+)R(+), 좌회전→L(-)R(+)
wheel_radius=0.056m, wheel_separation=0.3015m, CPR=2800

---

*마지막 업데이트: 2026-06-19 세션 7*
