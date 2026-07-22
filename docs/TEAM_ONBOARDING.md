# AIP Fleet — 팀원 온보딩 가이드

> **대상**: aip2(TurtleBot3) 또는 aip3(자작 차량) 담당 팀원.
> aip1(메인 AGV)는 별도 팀원 관할 — `docs/SETUP_RPI4.md §1` 참조.
>
> 최종 갱신: 2026-06-23

---

## 0. 먼저 알아야 할 것 (1분 요약)

| 항목 | 값 |
|---|---|
| Wi-Fi | `aip2.4GHz` (비밀번호는 팀장에게) |
| ROS_DOMAIN_ID | **42** |
| RMW | **rmw_fastrtps_cpp** (FastDDS) |
| DDS 탐색 | Simple Discovery — 동일 Wi-Fi 내 자동 탐색 (DS 불필요) |
| 중앙 PC IP | `192.168.0.9` (dev PC — 대시보드 + 빌드 서버) |

**네트워크 IP 배정 현황**

| 차량 | 네임스페이스 | IP | 상태 |
|---|---|---|---|
| 메인 AGV | `aip1` | `192.168.0.3` | ✅ 운용 중 |
| TurtleBot3 Burger | `aip2` | `192.168.0.4` | 🔧 세팅 중 |
| 자작 차량 | `aip3` | `192.168.0.5` | 🔧 세팅 중 |
| 중앙 PC (dev PC) | — | `192.168.0.9` | ✅ 운용 중 |

> ⚠️ 구형 문서의 `main`/`scout_1`/`scout_2` 네임스페이스 및 IP `192.168.0.20~22`는 **폐기됨**.
> 이 문서의 내용이 최신 기준.

---

## 1. 공통 설치 절차 (모든 RPi4B 공통)

**자세한 절차**: `docs/SETUP_RPI4.md`

요약:

```bash
# 1. Ubuntu 22.04 Server arm64 설치 후 SSH 접속
# 2. ROS2 Humble 설치
sudo apt install ros-humble-desktop python3-colcon-common-extensions

# 3. 레포 클론
git clone https://github.com/Mark2AC/aip-swarm-ws.git ~/aip_swarm_ws
cd ~/aip_swarm_ws

# 4. 의존성 설치
sudo rosdep init && rosdep update
rosdep install --from-paths src --ignore-src -r -y

# 5. 빌드 (시뮬/Gazebo 패키지 제외)
colcon build --packages-skip aip_fleet_gazebo aip_fleet_sim \
             --symlink-install

# 6. 환경 변수 (항상 source 후 사용)
echo "source ~/aip_swarm_ws/install/setup.bash" >> ~/.bashrc
echo "export ROS_DOMAIN_ID=42" >> ~/.bashrc
echo "export RMW_IMPLEMENTATION=rmw_fastrtps_cpp" >> ~/.bashrc
source ~/.bashrc
```

---

## 2. aip2 담당 팀원 — TurtleBot3 Burger

### 2-1. 하드웨어 스펙

| 항목 | 값 |
|---|---|
| 모델 | TurtleBot3 Burger (Robotis) |
| 구동부 | DYNAMIXEL XL430-W250 × 2 (OpenCR 보드) |
| LiDAR | LDS-03 (USB) |
| 최대 속도 | 0.22 m/s |
| RPi4B 포트 | OpenCR: `ttyACM0`, LDS-03: `ttyUSB0` |

### 2-2. 추가 의존성 설치

```bash
# TurtleBot3 패키지
sudo apt install ros-humble-turtlebot3 \
                 ros-humble-turtlebot3-msgs \
                 ros-humble-turtlebot3-navigation2

# SLAM Toolbox
sudo apt install ros-humble-slam-toolbox

# Nav2
sudo apt install ros-humble-nav2-bringup
```

### 2-3. 차량 bringup

RPi4B에서 실행:

```bash
source ~/aip_swarm_ws/install/setup.bash
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

ros2 launch aip_fleet_real turtlebot3.launch.py
```

**launch 인수 옵션:**

```bash
# 순찰 미션 포함
ros2 launch aip_fleet_real turtlebot3.launch.py with_patrol:=true

# 커스텀 namespace (기본값 aip2)
ros2 launch aip_fleet_real turtlebot3.launch.py namespace:=aip2
```

### 2-4. 제공 토픽 (bringup 완료 후)

| 토픽 | 타입 | 주기 |
|---|---|---|
| `/aip2/scan` | `sensor_msgs/LaserScan` | 5 Hz |
| `/aip2/odom` | `nav_msgs/Odometry` | 20 Hz |
| `/aip2/imu` | `sensor_msgs/Imu` | 40 Hz |
| `/aip2/heartbeat` | `aip_fleet_msgs/FleetHeartbeat` | 2 Hz |

**수신하는 토픽** (중앙 PC → RPi4B):

| 토픽 | 용도 |
|---|---|
| `/aip2/override_cmd_vel` | 원격 수동 조종 (우선순위 80) |
| `/aip2/autonomy_cmd_vel` | Nav2 자율주행 (우선순위 10) |
| `/aip2/estop` | 비상정지 |

### 2-5. ⚠️ TF frame_prefix 주의사항

TurtleBot3 기본 bringup은 TF 프레임을 **prefix 없이** 발행한다:
- 기본: `odom` → `base_footprint` → `base_link` → `base_scan`
- 필요: `aip2/odom` → `aip2/base_footprint` → `aip2/base_link` → `aip2/base_scan`

현재 `turtlebot3.launch.py`에 `CAVEAT` 주석으로 표시되어 있음.

**처리 방법 (택1):**

**방법 A** — TB3 bringup launch argument 활용:
```bash
# TB3 Burger의 경우 robot_description namespace 처리가 필요
# turtlebot3.launch.py 상단 CAVEAT 참조
ros2 launch aip_fleet_real turtlebot3.launch.py namespace:=aip2
```

**방법 B** — SLAM/Nav2 config에서 prefix 없는 프레임명 직접 사용:
```yaml
# config/turtlebot3/slam_toolbox.yaml
odom_frame: odom          # aip2/ 없이
base_frame: base_footprint
```

> 실차 테스트 후 어떤 방법이 동작하는지 확인하고 `turtlebot3.launch.py` CAVEAT 섹션에 결과를 기록해줄 것.
> aip1은 `base_link`(prefix 없음)를 사용하므로 일관성 문제가 있을 수 있음 → `docs/ARCHITECTURE.md §7` 참조.

### 2-6. 동작 검증

```bash
# RPi4B에서 bringup 실행 후 중앙 PC에서 확인:

# 1. 토픽 확인
ros2 topic list | grep aip2
ros2 topic hz /aip2/scan         # ~5 Hz
ros2 topic hz /aip2/odom         # ~20 Hz

# 2. 하트비트 확인
ros2 topic echo /aip2/heartbeat --once

# 3. 대시보드 확인
# http://localhost:8080 → aip2 차량 온라인 표시 확인

# 4. 수동 이동 테스트 (중앙 PC)
ros2 topic pub --once /aip2/override_cmd_vel geometry_msgs/Twist \
  '{linear: {x: 0.1}, angular: {z: 0.0}}'
```

---

## 3. aip3 담당 팀원 — 자작 차량

### 3-1. 하드웨어 스펙

| 항목 | 값 |
|---|---|
| 구동부 | Feetech STS3215 서보 (UART half-duplex) |
| LiDAR | YDLIDAR X4 PRO (360°, 최대 10m) |
| LiDAR 포트 | `ttyUSB0` (udev rule로 고정 권장) |
| 서보 포트 | `ttyUSB1` 또는 `ttyS0` (반이중 UART) |

### 3-2. 드라이버 현황

| 드라이버 | 상태 |
|---|---|
| YDLIDAR X4 PRO | ✅ `ros-humble-ydlidar-ros2-driver` 패키지 사용 가능 |
| Feetech STS3215 | ❌ 미구현 — 직접 구현 필요 |

**STS3215 드라이버 구현 참고:**
```
- 커뮤니티 패키지: feetech_ros2 (GitHub 검색)
- 또는 ros2_control HardwareInterface 자작
- UART half-duplex: 115200 baud, 데이터 비트 8, 정지 비트 1, 패리티 없음
```

### 3-3. 현재 launch 파일 상태

```bash
# 현재 placeholder 상태 — STS3215 드라이버 구현 후 수정 필요
ros2 launch aip_fleet_real custom_vehicle.launch.py
```

`src/aip_fleet_real/launch/custom_vehicle.launch.py` 및
`src/aip_fleet_real/config/custom_vehicle/` 파일을 참고하여 드라이버 통합 진행.

### 3-4. 구현해야 할 표준 인터페이스

플릿 시스템과 연동하려면 다음을 발행해야 한다:

```
발행: /aip3/scan            sensor_msgs/LaserScan    (LiDAR)
발행: /aip3/odom            nav_msgs/Odometry        (서보 엔코더 기반)
발행: /aip3/heartbeat       aip_fleet_msgs/FleetHeartbeat  (2Hz)
수신: /aip3/cmd_vel         geometry_msgs/Twist      (twist_mux 출력)
TF:  odom → base_link → laser_link  (또는 aip3/ prefix — aip2와 통일)
```

### 3-5. 차체 치수 설정

구현 완료 후 다음 파일에 실측 치수 입력:

```yaml
# src/aip_fleet_real/config/custom_vehicle/nav2.yaml
# robot_radius 또는 footprint 섹션 수정
footprint: [[0.15, 0.12], [0.15, -0.12], [-0.15, -0.12], [-0.15, 0.12]]

# src/aip_fleet_real/config/custom_vehicle/slam_toolbox.yaml
# base_frame, odom_frame 등 확인
```

---

## 4. 공통 검증 체크리스트 (차량 연결 후)

```
[ ] ros2 topic list | grep aip{2|3}  → scan, odom, heartbeat 확인
[ ] ros2 topic hz /aip{2|3}/scan     → 5~10 Hz
[ ] ros2 topic hz /aip{2|3}/odom     → 20 Hz
[ ] ros2 topic echo /aip{2|3}/heartbeat --once
[ ] 대시보드 http://localhost:8080 에서 차량 온라인 표시
[ ] 원격 Twist 명령 → 실제 바퀴 회전 확인
[ ] E-Stop 테스트: 대시보드 → 선택 차량 정지 → 바퀴 멈춤 확인
[ ] E-Stop 해제: 선택 차량 해제 → 바퀴 재구동 확인
```

---

## 5. 참조 문서

| 문서 | 내용 |
|---|---|
| `docs/ARCHITECTURE.md` | **전체 아키텍처** — 토픽 그래프, TF 구조, 파이프라인 |
| `docs/SETUP_RPI4.md` | RPi4B 상세 설치 절차 |
| `docs/SECURITY.md` | 보안 설정 (기본 비밀번호 변경 등) |
| `src/aip_fleet_real/launch/turtlebot3.launch.py` | aip2 launch 파일 (CAVEAT 섹션 필독) |
| `src/aip_fleet_real/launch/custom_vehicle.launch.py` | aip3 launch 파일 (placeholder) |
| `src/aip_fleet_real/config/turtlebot3/` | aip2 SLAM/Nav2/patrol 설정 |
| `src/aip_fleet_real/config/custom_vehicle/` | aip3 설정 디렉터리 |

---

## 6. 팀장 전달 체크리스트

### aip2 팀원에게 전달

- [ ] GitHub 레포 초대
- [ ] Wi-Fi 비밀번호 (구두/메신저)
- [ ] RPi4B 보드 + TurtleBot3 Burger 본체 (OpenCR 펌웨어 Burger용 확인)
- [x] RPi4B IP 주소 배정 — `192.168.0.4` (수동 고정)
- [ ] TF frame_prefix 방법 결정 통보 (실차 테스트 후)

### aip3 팀원에게 전달

- [ ] GitHub 레포 초대
- [ ] Wi-Fi 비밀번호 (구두/메신저)
- [ ] RPi4B 보드 + 자작 차체 일체 (STS3215, YDLIDAR X4 PRO 포함)
- [x] RPi4B IP 주소 배정 — `192.168.0.5` (수동 고정)
- [ ] STS3215 드라이버 구현 방향 결정 (ros2_control vs 직접 발행)

### 레포에 포함 안 된 항목

| 항목 | 전달 방법 |
|---|---|
| Wi-Fi 비밀번호 (`aip2.4GHz`) | 구두/메신저 |
| RPi4B IP 배정 (aip2/aip3) | ✅ 확정 — aip2: 192.168.0.4, aip3: 192.168.0.5 (수동 고정) |
| patrol.yaml 웨이포인트 | 각 담당자가 운용 환경에서 SLAM 맵 생성 후 직접 입력 |
