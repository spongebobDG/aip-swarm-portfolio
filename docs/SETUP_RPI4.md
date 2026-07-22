# SETUP_RPI4.md — 실차량 RPi4B 의존성 설치 순서 & 환경 구성

> 대상: AIP 플릿 실차량(`aip2` TurtleBot3 Burger, `aip3` 자작 차량)의
> Raspberry Pi 4B 온보드 컴퓨터. `aip1`(메인 AGV) RPi4B도 이 가이드를 따른다.
> 메인 AGV 차량 자체 SW(`my_ros_env` 컨테이너 `/root/colcon_ws`)는 타 팀원 관할이므로 수정 금지.
>
> 구조: 2026-06-15 모노레포 통합 — 시뮬/실차가 `aip_swarm_ws` 한 레포에 공존하며
> sim/real 은 colcon 빌드 타겟으로 분리한다(별도 워크스페이스 없음). 상세: `docs/REAL_WS.md`.

**설치는 §1 → §8 순서대로** 진행한다. 각 단계는 앞 단계 결과에 의존하므로 건너뛰지 말 것.

---

## 0. 전제 (하드웨어/저장장치)

| 항목 | 값 |
|---|---|
| 보드 | Raspberry Pi 4B **RAM 4GB 이상** (MPPI+SLAM 동시 구동) |
| OS | **Ubuntu 22.04 Server (64-bit / arm64)**, headless |
| 저장장치 | **최소 16 GB, 권장 32 GB**, USB 3.0 SSD 권장(SD카드 수명/IO) |
| 네트워크 | Wi-Fi AP `AIP_FLEET` (192.168.0.0/24) 접속 가능 |

> 설치 후 점유량은 약 8 GB(toolchain 포함). 개발 PC 빌드본을 복사 배포하면 ~6.5 GB.

---

## 설치 순서 한눈에 (의존 관계)

```
1. 시스템 준비 + ROS2 apt 저장소 등록     ← 이게 없으면 ros-humble-* 설치 불가
2. ROS2 코어(ros-base) + 빌드 도구        ← rosdep/colcon 이 여기서 들어옴
3. 워크스페이스 클론 + 서브모듈            ← package.xml 들이 있어야 다음 단계 가능
4. rosdep 으로 패키지 의존성 자동 설치     ← nav2/slam/twist_mux/tb3 대부분 자동
5. 차량별 추가 의존성                       ← scout_1=tb3, scout_2=드라이버(추후), main=없음
6. colcon 빌드(시뮬 패키지 제외)
7. 환경변수 영구화
8. 기동 & 점검
```

---

## 1. 시스템 준비 + ROS2 apt 저장소 등록

ROS2 패키지를 apt 로 받으려면 **저장소 키 등록이 가장 먼저** 돼야 한다.

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
```

---

## 2. ROS2 코어 + 빌드 도구

```bash
sudo apt install -y ros-humble-ros-base ros-dev-tools python3-colcon-common-extensions
```

- `ros-humble-ros-base`: rclcpp/rclpy/fastrtps 등 코어 (headless, desktop 불필요).
- `ros-dev-tools`: **rosdep·colcon·vcstool** 포함 → 다음 단계(§4 자동 의존성 해결)의 전제.

> 이후 모든 ROS 명령 전에 `source /opt/ros/humble/setup.bash` 필요(§7에서 영구화).

---

## 3. 워크스페이스 클론 + 서브모듈

`package.xml`(의존 선언)이 있어야 §4 rosdep 이 동작하므로 소스를 먼저 받는다.

```bash
cd ~
git clone https://github.com/Mark2AC/aip-swarm-ws.git aip_swarm_ws
cd ~/aip_swarm_ws
git submodule update --init --recursive    # rf2o 등
```

---

## 4. rosdep 으로 패키지 의존성 자동 설치 (핵심 단계)

`aip_fleet_real/package.xml` 에 실차 런타임 의존(`navigation2`, `nav2_bringup`,
`slam_toolbox`, `twist_mux`, `turtlebot3_bringup`, `aip_fleet_msgs` …)이 선언돼 있어
**rosdep 이 이들을 자동으로 apt 설치**한다. 수동 나열보다 이 경로를 신뢰한다.

```bash
source /opt/ros/humble/setup.bash
sudo rosdep init 2>/dev/null; rosdep update
rosdep install --from-paths src --ignore-src -r -y \
  --skip-keys "gazebo_ros ignition-gazebo ros_gz_sim"   # RPi4B 에는 Gazebo 없음
```

> 자동 해결되는 주요 패키지: `ros-humble-navigation2`, `ros-humble-nav2-bringup`,
> `ros-humble-slam-toolbox`, `ros-humble-twist-mux`, `ros-humble-robot-localization`,
> `ros-humble-rmw-fastrtps-cpp`.
>
> **수동 설치 대안**(rosdep 이 일부를 못 잡을 때만):
> ```bash
> sudo apt install -y ros-humble-navigation2 ros-humble-nav2-bringup \
>   ros-humble-slam-toolbox ros-humble-twist-mux ros-humble-robot-localization \
>   ros-humble-rmw-fastrtps-cpp
> ```

---

## 5. 차량별 추가 의존성

| 단계 | `aip1` (메인 AGV) | `aip2` (TB3 Burger) | `aip3` (자작 차량) |
|---|---|---|---|
| §1~§4 | ✅ 동일 | ✅ 동일 | ✅ 동일 |
| 추가 패키지 | `ros-humble-ydlidar-ros2-driver`, `pyserial` | `ros-humble-turtlebot3` `ros-humble-turtlebot3-bringup` | (현재 없음) STS3215·LiDAR 드라이버는 **추후** |
| 환경변수 | (없음) | `TURTLEBOT3_MODEL=burger` | (없음) |

### aip2 (TurtleBot3 Burger)
```bash
sudo apt install -y ros-humble-turtlebot3 ros-humble-turtlebot3-bringup
# (§4 rosdep 에서 이미 설치됐을 수 있음 — 멱등)
```

### aip3 (자작 차량)
- 현재 추가 apt 의존 없음. Feetech STS3215 모터 + LiDAR 드라이버는 별도 세션에서
  구현·문서화 예정(미구현). 구현 후 본 표에 패키지를 추가한다.

### aip1 (메인 AGV)
추가 apt 패키지:
```bash
sudo apt install -y ros-humble-ydlidar-ros2-driver
```
> YDLidar TG15 드라이버: `ydlidar_ros2_driver` (rosdep 이 package.xml 에서 자동 설치).
> serial_bridge / heartbeat_pub 는 `aip_fleet_real` Python 패키지 내 포함(별도 설치 불필요).
> pyserial 필요: `pip3 install pyserial`

---

## 6. colcon 빌드 (시뮬 패키지 제외)

```bash
cd ~/aip_swarm_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install \
  --packages-skip aip_fleet_gazebo aip_fleet_sim aip_fleet_foxglove_panels
```

> 빌드 검증: `source install/setup.bash && ros2 pkg list | grep aip_fleet_real`
> → `aip_fleet_real` 출력되면 성공.
>
> 실차 패키지+의존만 빠르게: `colcon build --symlink-install --packages-up-to aip_fleet_real`
>
> **RPi4B 4GB OOM 주의**: nav2/msgs 빌드가 메모리를 많이 먹는다 →
> `colcon build --parallel-workers 1 --executor sequential` + 2GB swap 권장.
> 또는 개발 PC 에서 빌드한 `install/` 을 복사 배포(차량에서 toolchain 생략 가능).

코드 갱신 시: `git pull && colcon build --symlink-install --packages-skip ...`.

---

## 7. 환경변수 영구화

`~/.bashrc` 끝에 추가:

```bash
source /opt/ros/humble/setup.bash
source ~/aip_swarm_ws/install/setup.bash

export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export TURTLEBOT3_MODEL=burger   # aip2(TB3) 에서만. aip1/aip3 는 이 줄 제외.

# FastDDS Discovery Server (동일 서브넷에서는 불필요. 이기종 네트워크 시에만 활성화)
# export FASTRTPS_DEFAULT_PROFILES_FILE=~/aip_swarm_ws/config/fastdds_client_profile.xml
```

`aip3` 에서는 `TURTLEBOT3_MODEL` 줄을 뺀다.

> ⚠️ 미소싱 시 `ROS_DOMAIN_ID=0` 기본값으로 떠 플릿과 통신되지 않는다.
> 새 터미널마다 `echo $ROS_DOMAIN_ID`(=42) 확인.

---

## 8. 기동 & 점검

### aip1 — 메인 AGV (RPi4B 에서 실행)
```bash
# 하드웨어 드라이버 기동 (YDLidar + serial_bridge + twist_mux + heartbeat)
ros2 launch aip_fleet_real fleet_main.launch.py

# 확인
ros2 topic hz /aip1/scan     # ~10Hz
ros2 topic hz /aip1/odom     # ~20Hz
ros2 topic echo /aip1/heartbeat --field vehicle_id
```

### aip2 — TurtleBot3 Burger
```bash
ros2 launch aip_fleet_real turtlebot3.launch.py
# 통합: ros2 launch aip_fleet_real fleet_real.launch.py with_tb3:=true with_main:=false with_custom:=false
```
```bash
ros2 topic list | grep /aip2/      # /aip2/scan /odom /cmd_vel
ros2 topic hz /aip2/scan
ros2 run tf2_tools view_frames     # map→odom→base_footprint
```
> ⚠️ TB3 기본 bringup 은 TF 프레임을 prefix 없이(odom/base_link/base_scan) 발행한다.
> config 의 aip2/* 와 맞추려면 robot_state_publisher `frame_prefix:=aip2/` 등
> 추가 배선 필요. 상세: `turtlebot3.launch.py` 상단 CAVEAT.

### aip3 — 자작 차량 (placeholder)
```bash
ros2 launch aip_fleet_real custom_vehicle.launch.py drivers_ready:=false
```

### 표준 차량 인터페이스 (자가 점검)
| 방향 | 토픽/TF | 타입 |
|---|---|---|
| 입력 | `/<ns>/cmd_vel` | geometry_msgs/Twist |
| 출력 | `/<ns>/odom` | nav_msgs/Odometry |
| 출력 | `/<ns>/scan` | sensor_msgs/LaserScan |
| TF | `odom → base_footprint` | serial_bridge / odom (aip1) |
| TF | `map → odom` | slam_toolbox |
| 출력 | `/<ns>/heartbeat` | aip_fleet_msgs/FleetHeartbeat |
| 입력 | `/<ns>/override_cmd_vel` | geometry_msgs/Twist |

`<ns>` ∈ {`aip1`, `aip2`, `aip3`}.

---

## 9. 트러블슈팅

| 증상 | 점검 |
|---|---|
| `ros-humble-*` apt 못 찾음 | §1 저장소 키/`ros2.list` 등록, `sudo apt update` 재실행 |
| rosdep 이 의존 못 잡음 | `rosdep update` 재실행, §4 수동 apt 대안 사용 |
| 플릿과 통신 안 됨 | `echo $ROS_DOMAIN_ID`(=42), RMW=fastrtps, AP 접속, DS(11811) 도달 |
| `/aip1/scan` 없음 | `/dev/ydlidar` 존재 여부, udev 규칙, fleet_main 로그 |
| `/aip1/odom` 없음 | `/dev/aip_esp32` 존재, 115200 baud, serial_bridge 로그 |
| `/aip2/scan` 없음 | LDS-03 USB, OpenCR 전원, `turtlebot3_bringup` 로그 |
| Nav2 가 안 움직임 | `/<ns>/cmd_vel` 에 twist_mux 출력 실리는지 `ros2 topic echo` |
| map→odom TF 없음 | slam_toolbox 생존, scan 수신, frame_prefix(§8 CAVEAT) |
| pyserial 없음 | `pip3 install pyserial` (serial_bridge 의존) |
| 빌드 중 멈춤/OOM | `--parallel-workers 1 --executor sequential` + swap |
| Gazebo 의존 오류 | 빌드에 `--packages-skip aip_fleet_gazebo aip_fleet_sim aip_fleet_foxglove_panels` |
