# AIP Fleet — 실차 하드웨어 세팅 가이드

> **대상**: 차량 담당 팀원. 각 차량의 RPi4B에 소프트웨어를 설치하고 플릿에 합류시키는 절차.  
> **전제**: 개발 PC(중앙 PC)는 Wi-Fi AP `aip2.4GHz`에 연결되어 있고, `./run_central.sh`로 Discovery Server + Dashboard가 실행 중이다.  
> **테스트 환경**: 전용 AP 대신 기존 공유기(`aip2.4GHz`, `192.168.0.0/24`)를 그대로 사용. 전용 AP 구성 시 §2-1 IP 대역만 조정하면 된다.

---

## 1. 플릿 구성 한눈에

```
                    ┌─────────────────────────────┐
                    │     중앙 PC (192.168.0.6)    │
                    │  FastDDS Discovery Server    │  ← run_central.sh
                    │  웹 관제 Dashboard :8080     │
                    └────────────┬────────────────┘
                                 │
            Wi-Fi AP: aip2.4GHz (192.168.0.0/24)  ← 기존 공유기 사용
            ┌────────────────────┼────────────────────┐
            │                    │                    │
   ┌────────┴──────┐   ┌─────────┴──────┐   ┌────────┴──────┐
   │   scout_1     │   │   scout_2      │   │   main AGV    │
   │  (TurtleBot3) │   │ (자작 차량)    │   │ (타 팀원 관할) │
   │  RPi4B        │   │  RPi4B         │   │  RPi4B        │
   │ 192.168.0.21  │   │ 192.168.0.22   │   │ 192.168.0.20  │
   └───────────────┘   └────────────────┘   └───────────────┘
```

### 차량별 하드웨어 스펙

| 항목 | `scout_1` | `scout_2` | `main` |
|---|---|---|---|
| **모델** | TurtleBot3 Burger | 자작 차량 | 메인 AGV |
| **컴퓨팅** | Raspberry Pi 4B | Raspberry Pi 4B | Raspberry Pi 4B |
| **구동부** | DYNAMIXEL XL430-W250 × 2 | Feetech STS3215 서보 (UART half-duplex) | DFRobot FIT0186 DC모터 × 2 + PP-A055 드라이버 |
| **LiDAR** | LDS-03 (360°, USB) | YDLIDAR X4 PRO (360°, 최대 10m) | YDLIDAR |
| **휠 간격** | 160 mm | — | 290 mm |
| **휠 반경** | 33 mm | — | 60 mm |
| **최대 선속도** | 0.22 m/s | — | 1.58 m/s (운용 상한 0.5 m/s) |
| **최대 각속도** | 2.84 rad/s | — | 3.45 rad/s (운용 상한 1.70 rad/s) |
| **차체 크기** | 138×178×192 mm | 미확정 | 230(W)×300(L)×120(H) mm |
| **센서/부가장치** | — | — | 4축 로봇암, OV5647 카메라, MLX90640 열화상 |
| **ROS2 드라이버** | ✅ `turtlebot3_bringup` 내장 | 🔧 미구현 | 타 팀원 관할 (`my_ros_env`) |
| **SW 현황** | ✅ launch 완료 | 🔧 드라이버 필요 | 🔗 인터페이스 협조만 |
| **담당** | 담당자 A | 담당자 B | 타 팀원 |

---

## 2. 네트워크 준비 (공통)

### 2-1. Wi-Fi AP 설정

모든 기기를 `aip2.4GHz` AP에 연결한다.  
*(전용 AP로 전환 시 아래 IP 대역을 원하는 서브넷으로 일괄 변경)*

| 기기 | 고정 IP | 비고 |
|---|---|---|
| 중앙 PC (개발 PC) | `192.168.0.6` | Discovery Server 호스트 — DHCP로 이미 할당됨 |
| main AGV RPi4B | `192.168.0.20` | 타 팀원 관할 |
| scout_1 RPi4B | `192.168.0.21` | |
| scout_2 RPi4B | `192.168.0.22` | |

> 중앙 PC는 현재 DHCP(`192.168.0.6`)를 사용 중. RPi4B들이 Discovery Server에 접속할 수 있으려면 **이 IP가 바뀌지 않아야** 한다. 공유기에서 중앙 PC의 MAC에 IP를 고정 할당(DHCP 예약)해두는 것을 권장한다.

### 2-2. RPi4B IP 고정 (Ubuntu 22.04 netplan)

각 차량 RPi4B에서 실행 (IP를 차량에 맞게 변경):

```bash
sudo tee /etc/netplan/01-aip-fleet.yaml << 'EOF'
network:
  version: 2
  wifis:
    wlan0:
      dhcp4: false
      addresses: [192.168.0.21/24]    # scout_2는 192.168.0.22/24로 변경
      gateway4: 192.168.0.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
      access-points:
        "aip2.4GHz":
          password: "팀장에게 문의"    # Wi-Fi 비밀번호 (레포 미포함)
EOF
sudo netplan apply
```

### 2-3. 연결 확인

```bash
ping 192.168.0.6   # 중앙 PC 도달 확인
```

---

## 3. RPi4B 공통 소프트웨어 설치

**scout_1, scout_2 모두 동일하게 진행한다.**

### 3-1. OS 요구사항

| 항목 | 값 |
|---|---|
| OS | Ubuntu 22.04 Server 64-bit (arm64), headless |
| 저장장치 | 16 GB 이상 (권장: 32 GB USB 3.0 SSD) |
| RAM | 4 GB 이상 |

### 3-2. ROS2 저장소 등록 및 설치

```bash
sudo apt update && sudo apt install -y locales curl gnupg lsb-release
sudo locale-gen en_US en_US.UTF-8
sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8

sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt update

sudo apt install -y ros-humble-ros-base ros-dev-tools python3-colcon-common-extensions
```

### 3-3. 워크스페이스 클론

```bash
cd ~
git clone https://github.com/Mark2AC/aip-swarm-ws.git aip_swarm_ws
cd ~/aip_swarm_ws
git submodule update --init --recursive
```

### 3-4. 의존성 자동 설치 (rosdep)

```bash
source /opt/ros/humble/setup.bash
sudo rosdep init 2>/dev/null; rosdep update
rosdep install --from-paths src --ignore-src -r -y \
  --skip-keys "gazebo_ros ignition-gazebo ros_gz_sim"
```

> **OOM 발생 시**: `sudo fallocate -l 2G /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile`

### 3-5. 빌드 (Gazebo 제외)

```bash
cd ~/aip_swarm_ws
colcon build --symlink-install \
  --packages-skip aip_fleet_gazebo aip_fleet_sim aip_fleet_foxglove_panels \
  --parallel-workers 2
```

> 빌드 중 멈히면: `--parallel-workers 1 --executor sequential`

빌드 확인:

```bash
source install/setup.bash
ros2 pkg list | grep aip_fleet_real   # → aip_fleet_real 출력되면 OK
```

### 3-6. FastDDS Discovery Server 클라이언트 설정

```bash
sudo mkdir -p /opt/aip
sudo cp ~/aip_swarm_ws/config/fastdds_client_profile.xml /opt/aip/
```

### 3-7. 환경변수 영구화 (`~/.bashrc` 끝에 추가)

**scout_1 (TurtleBot3):**

```bash
cat >> ~/.bashrc << 'EOF'

# ── AIP Fleet ──────────────────────────────────────────────────
source /opt/ros/humble/setup.bash
source ~/aip_swarm_ws/install/setup.bash

export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/aip/fastdds_client_profile.xml
export ROS_DISCOVERY_SERVER=192.168.0.6:11811
export TURTLEBOT3_MODEL=burger
EOF
source ~/.bashrc
```

**scout_2 (자작 차량) — `TURTLEBOT3_MODEL` 줄 제외:**

```bash
cat >> ~/.bashrc << 'EOF'

# ── AIP Fleet ──────────────────────────────────────────────────
source /opt/ros/humble/setup.bash
source ~/aip_swarm_ws/install/setup.bash

export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/aip/fastdds_client_profile.xml
export ROS_DISCOVERY_SERVER=192.168.0.6:11811
EOF
source ~/.bashrc
```

> ⚠️ 새 터미널마다 `echo $ROS_DOMAIN_ID` → 42 확인. 0이면 소싱 누락.

---

## 4. scout_1 (TurtleBot3 Burger) 세팅

### 하드웨어 스펙 요약

| 항목 | 값 |
|---|---|
| 제조사 | Robotis |
| 구동부 | DYNAMIXEL XL430-W250 × 2 |
| 제어보드 | OpenCR 1.0 |
| LiDAR | LDS-03 (360°, 최대 8m, USB 연결) |
| 휠 간격 | 160 mm |
| 휠 반경 | 33 mm |
| 최대 선속도 | 0.22 m/s |
| 최대 각속도 | 2.84 rad/s |
| 차체 | 138(W)×178(L)×192(H) mm, 약 1 kg |

### 4-1. 추가 패키지 설치

```bash
sudo apt install -y ros-humble-turtlebot3 ros-humble-turtlebot3-bringup
```

### 4-2. OpenCR 펌웨어 확인

TurtleBot3의 OpenCR 보드가 Burger용 펌웨어로 플래시되어 있어야 한다.  
아직 안 되어 있으면: [TB3 공식 매뉴얼 OpenCR 섹션](https://emanual.robotis.com/docs/en/platform/turtlebot3/opencr_setup/) 참조.

### 4-3. 하드웨어 연결 확인

```bash
ls /dev/ttyACM*    # OpenCR → /dev/ttyACM0
ls /dev/ttyUSB*    # LDS-03 LiDAR → /dev/ttyUSB0 (또는 USB1)
```

USB 권한 추가 (한 번만):

```bash
sudo usermod -aG dialout $USER
# 재로그인 후 적용
```

### 4-4. TF 프레임 prefix 배선 (⚠️ 반드시 처리)

TurtleBot3 기본 bringup은 TF 프레임을 `odom / base_link / base_scan` (prefix 없이) 발행한다. 본 스택은 `scout_1/odom`, `scout_1/base_link`를 기대하므로 **수동 배선이 필요하다.**

**적용 방법 (A — 권장): launch 파라미터로 frame prefix 지정**

`turtlebot3.launch.py`에서 `tb3_bringup` 그룹 아래 아래 파라미터를 추가 적용:

```python
# turtlebot3_bringup robot.launch.py에 frame_prefix 전달
launch_arguments={
    'multi_robot_name': 'scout_1',   # odom→scout_1/odom, base_link→scout_1/base_link
}.items(),
```

> ⚠️ `turtlebot3_bringup`의 `multi_robot_name` 지원 여부를 `ros2 launch turtlebot3_bringup robot.launch.py --show-args`로 먼저 확인할 것.  
> 지원하지 않으면 방법 B 적용.

**적용 방법 (B — 대안): config에서 prefix 없는 기본값 사용**

`src/aip_fleet_real/config/turtlebot3/slam_toolbox.yaml`에서:

```yaml
odom_frame:  odom          # scout_1/odom → odom 으로 변경
base_frame:  base_footprint  # scout_1/base_link → base_footprint 로 변경
scan_topic:  /scout_1/scan   # 유지 (네임스페이스로 토픽은 구분됨)
```

`src/aip_fleet_real/config/turtlebot3/nav2.yaml`에서:

```yaml
bt_navigator:
  ros__parameters:
    robot_base_frame: base_footprint   # scout_1/base_link → base_footprint
```

> 방법 B는 단일 TB3 환경에서 빠르게 검증할 때 사용. 다중 차량이면 방법 A로 prefix를 반드시 부여해야 TF 충돌이 없다.

### 4-5. Nav2 MPPI 파라미터 조정 (RPi4B CPU 대응)

TB3 RPi4B에서 `batch_size=1000`은 10Hz 제어 루프를 초과할 수 있다.  
`src/aip_fleet_real/config/turtlebot3/nav2.yaml`에서 조정:

```yaml
FollowPath:
  batch_size: 600          # 1000 → 600: RPi4B 여유 확보 (지연 지속 시 400까지 하향)
  visualize: false         # MarkerArray 퍼블리싱 비활성 (CPU 절감)
```

### 4-6. 실행

```bash
# 기본 실행 (수동 goal)
ros2 launch aip_fleet_real turtlebot3.launch.py

# 순찰 미션 자동 시작
ros2 launch aip_fleet_real turtlebot3.launch.py with_patrol:=true
```

### 4-7. 동작 확인

```bash
# 토픽 확인
ros2 topic list | grep scout_1
# → /scout_1/cmd_vel  /scout_1/odom  /scout_1/scan  /scout_1/map

# LiDAR 수신 확인
ros2 topic hz /scout_1/scan   # → ~10 Hz

# TF 트리 확인
ros2 run tf2_tools view_frames
# → map → scout_1/odom → scout_1/base_link 체인 있어야 함

# 중앙 PC에서 차량 보임 확인
ros2 topic echo /fleet/status   # scout_1 포함 확인
```

### 4-8. 순찰 웨이포인트 설정

`src/aip_fleet_real/config/turtlebot3/patrol.yaml`의 `waypoints` 값을 실제 맵 좌표로 교체한다.

```yaml
/scout_1/patrol_node:
  ros__parameters:
    waypoints: [
      1.0, 0.0, 0.0,      # WP1: x, y, yaw(도)
      1.0, 1.5, 90.0,     # WP2
      0.0, 1.5, 180.0,    # WP3
      0.0, 0.0, -90.0,    # WP4
    ]
```

좌표 확인 방법:
1. `ros2 launch aip_fleet_real turtlebot3.launch.py`로 SLAM 기동
2. 차량을 수동으로 이동하며 맵 생성
3. `ros2 topic echo /scout_1/odom`으로 원하는 위치의 좌표 기록
4. 또는 RViz2의 `2D Pose Estimate` 툴로 맵 위 좌표 읽기

수정 후 `colcon build` 없이 재기동만으로 반영됨 (`--symlink-install` 적용).

---

## 5. scout_2 (자작 차량) 세팅

> ⚠️ **현재 상태**: STS3215 서보 드라이버가 미구현. LiDAR(YDLIDAR X4 PRO)는 확정됐으며 드라이버 패키지 설치는 가능. 실차 완전 구동은 서보 드라이버 구현 후 가능.

### 하드웨어 스펙 요약

| 항목 | 값 |
|---|---|
| 차체 | 자작 (치수 확정 후 config 반영 필요) |
| 구동부 | Feetech STS3215 서보 (UART half-duplex 버스, 위치·속도·전류 피드백 내장) |
| LiDAR | **YDLIDAR X4 PRO** (360°, 최대 10m, USB 연결) — ✅ 확정 |
| 컴퓨팅 | Raspberry Pi 4B |
| ROS2 드라이버 | LiDAR: `ros-humble-ydlidar-ros2-driver` / 서보: 미구현 |

### 5-1. YDLIDAR X4 PRO 드라이버 설치

```bash
sudo apt install -y ros-humble-ydlidar-ros2-driver

# USB 장치 권한
sudo usermod -aG dialout $USER   # 재로그인 후 적용

# 연결 확인
ls /dev/ttyUSB*    # → /dev/ttyUSB0
```

YDLIDAR udev rule 등록 (1회):

```bash
rosrun ydlidar_ros2_driver ydlidar_ros2_driver_node
# 또는 수동 등록
sudo tee /etc/udev/rules.d/ydlidar.rules << 'EOF'
KERNEL=="ttyUSB*", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", \
  MODE:="0666", GROUP:="dialout", SYMLINK+="ydlidar"
EOF
sudo udevadm control --reload-rules && sudo udevadm trigger
```

YDLIDAR X4 PRO launch 파라미터 (`custom_vehicle.launch.py`에 추가 예정):

```yaml
# X4 PRO 기준값
port: /dev/ydlidar        # udev symlink 사용 권장
baudrate: 128000
lidar_type: 1             # YDLIDAR_TYPE_TRIANGLE
frame_id: scout_2/base_scan
resolution_fixed: true
auto_reconnect: true
reversion: false
clockwise: false
min_angle: -3.14159
max_angle: 3.14159
scan_frequency: 8.0
sample_rate: 5
min_range: 0.10
max_range: 10.0
```

### 5-2. 현재 가능한 것

```bash
# 드라이버 없이 소프트웨어 구조만 기동 (토픽/TF 확인)
ros2 launch aip_fleet_real custom_vehicle.launch.py drivers_ready:=false

# LiDAR만 단독 테스트
ros2 launch ydlidar_ros2_driver ydlidar_launch.py
ros2 topic hz /scan   # → ~8 Hz 확인
```

### 5-3. 서보(STS3215) 드라이버 구현 후 추가할 것 (TODO)

STS3215는 UART half-duplex 직렬 버스 방식으로, 표준 diff_drive_controller와 연동하려면 `ros2_control hardware_interface` 구현이 필요하다.

- [ ] STS3215 ROS2 드라이버 선정 (`feetech_ros2` 또는 자작 hardware_interface)
- [ ] `/scout_2/cmd_vel` → 서보 속도 명령 변환 노드
- [ ] `custom_vehicle.launch.py`에 LiDAR + 서보 드라이버 노드 추가
- [ ] `config/custom_vehicle/slam_toolbox.yaml` frame 값 수정 (`scout_2/odom`, `scout_2/base_link`)
- [ ] `config/custom_vehicle/nav2.yaml` footprint·속도 파라미터를 실차 치수로 수정

---

## 6. main AGV 협조 (타 팀원 담당)

### 하드웨어 스펙 참고

| 항목 | 값 |
|---|---|
| 차체 | 230(W)×300(L)×120(H) mm |
| 구동부 | DFRobot FIT0186 DC모터 × 2 (12V, 43.8:1, 최대 1.58m/s) |
| 모터 드라이버 | PP-A055 (BTS7960 43A H브리지) |
| LiDAR | YDLIDAR |
| 부가장치 | 4축 로봇암 + OV5647 RGB카메라 + MLX90640 열화상 + 가스/유해물질 센서 |
| ROS2 | `my_ros_env` 컨테이너 — **이 스택 설치 불가, 수정 금지** |

main AGV는 이 스택을 설치하지 않는다. `my_ros_env` 컨테이너(타 팀원 관할)가 구동 중이며, 아래 환경변수 설정만 요청하면 된다.

**타 팀원에게 요청할 내용:**

```bash
# my_ros_env 컨테이너 내부 또는 RPi4B ~/.bashrc에 추가
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/aip/fastdds_client_profile.xml
export ROS_DISCOVERY_SERVER=192.168.0.6:11811
```

FastDDS 클라이언트 프로필 파일 전달:
```bash
# 중앙 PC에서 main AGV RPi4B로 복사
scp ~/aip_swarm_ws/config/fastdds_client_profile.xml ubuntu@192.168.0.20:/opt/aip/
```

**main AGV가 발행해야 하는 표준 인터페이스:**

| 토픽/TF | 타입 | 비고 |
|---|---|---|
| `/main/cmd_vel` | `geometry_msgs/Twist` | 입력 (우리가 발행) |
| `/main/odom` | `nav_msgs/Odometry` | 출력 (AGV가 발행) |
| `/main/scan` | `sensor_msgs/LaserScan` | 출력 (AGV가 발행) |
| TF `main/odom → main/base_link` | — | AGV 발행 |
| TF `map → main/odom` | — | SLAM 발행 |
| `/main/estop` | `std_msgs/Bool` | 비상정지 수신 |

---

## 7. 중앙 PC (개발 PC) 역할 확인

차량 세팅 전에 중앙 PC에서 아래가 실행 중이어야 한다.

```bash
# 중앙 PC에서 실행
./run_central.sh
```

내부적으로 기동되는 것:
- **FastDDS Discovery Server** — 모든 차량의 DDS 피어 발견 중계 (`:11811`)
- **웹 관제 Dashboard** — `http://localhost:8080` (차량 상태, E-Stop, 이동 명령)
- **Foxglove Bridge** — `ws://localhost:8765` (실시간 맵/센서 시각화)

중앙 PC 환경변수 확인:
```bash
echo $ROS_DOMAIN_ID         # → 42
echo $RMW_IMPLEMENTATION    # → rmw_fastrtps_cpp
```

---

## 8. 플릿 전체 연결 검증

모든 차량 기동 후 중앙 PC에서 확인:

```bash
# 1. DDS 피어 발견 확인
ros2 node list
# → /scout_1/slam_toolbox  /scout_1/controller_server 등 차량 노드 보여야 함

# 2. 핵심 토픽 확인
ros2 topic list | grep -E "scout_1|scout_2|main"

# 3. LiDAR 수신 확인
ros2 topic hz /scout_1/scan   # → ~10 Hz

# 4. 웹 관제 UI
# 브라우저 → http://localhost:8080
# 차량 카드에 scout_1이 ONLINE으로 표시되어야 함
# 지도 툴바 "🗺 전체맵" / "🔍 SLAM맵" 전환 확인

# 5. E-Stop 테스트 (차량 정지 상태에서)
ros2 topic pub -1 /scout_1/estop std_msgs/Bool "data: true"
# → cmd_vel 멈춤 확인 후 해제
ros2 topic pub -1 /scout_1/estop std_msgs/Bool "data: false"
```

---

## 9. 알려진 이슈 및 주의사항

| 이슈 | 현황 | 대응 |
|---|---|---|
| TF frame prefix | TB3 기본 bringup이 prefix 없는 프레임 발행 | 섹션 4-4 방법 A 또는 B 적용 필수 |
| MPPI CPU 부하 | RPi4B에서 batch_size=1000 시 10Hz 루프 누락 가능 | nav2.yaml `batch_size: 600`으로 하향 |
| scout_2 LiDAR | YDLIDAR X4 PRO 드라이버 설치 필요 | 섹션 5-1 절차대로 설치 |
| scout_2 서보 드라이버 | STS3215 ROS2 드라이버 미구현 | 섹션 5-3 TODO 완료 후 활성화 |
| 순찰 좌표 | patrol.yaml가 0.5m 사각형 placeholder | 섹션 4-7대로 실환경 좌표로 교체 |
| main AGV TF | SLAM이 `map→main/odom`을 static으로 발행 중 | AGV SLAM 완성 후 static TF 제거 |

### use_sim_time 주의

실차 launch에서 `use_sim_time: true`를 절대 사용하지 않는다. 항상 `false`.

### 시크릿 파일

`docker/central/.env`, `firmware/scout_microros/secrets.ini`는 커밋 금지 (`.gitignore` 등재).

---

## 10. 코드 업데이트 방법

```bash
cd ~/aip_swarm_ws
git pull
colcon build --symlink-install \
  --packages-skip aip_fleet_gazebo aip_fleet_sim aip_fleet_foxglove_panels

source install/setup.bash
```

파라미터 yaml만 수정한 경우 (`--symlink-install` 환경): 재빌드 없이 재기동만으로 반영.

---

## 11. 참고 문서

| 문서 | 내용 |
|---|---|
| `docs/SETUP_RPI4.md` | RPi4B 의존성 설치 상세 절차 |
| `docs/REAL_WS.md` | 실차 패키지 구조 및 설계 의도 |
| `docs/ARCHITECTURE.md` | 토픽·TF·QoS 전체 아키텍처 |
| `docs/SECURITY.md` | 보안 감사 결과 |
| `src/aip_fleet_real/launch/turtlebot3.launch.py` | launch 상단 CAVEAT — TF 배선 상세 |
| `src/aip_fleet_real/config/turtlebot3/` | 차량별 SLAM·Nav2·twist_mux·patrol 파라미터 |
