> ⚠️ **2026-06-23 갱신**: 이 문서는 구 별도 워크스페이스(`aip_real_ws`) 설계를 담고 있으며 **이미 폐기됨**.
> - 별도 워크스페이스 구조는 2026-06-15 모노레포 통합으로 폐기됨
> - `aip_fleet_real`은 이제 `aip_swarm_ws/src/` 에 있음
> - 네임스페이스 `main`/`scout_1`/`scout_2` → **`aip1`/`aip2`/`aip3`** 로 변경됨
>
> **최신 문서**: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — 현재 토픽·TF·파이프라인 전체
> **팀원 온보딩**: [`docs/TEAM_ONBOARDING.md`](TEAM_ONBOARDING.md) — aip2/aip3 세팅 절차
> **설치 절차**: [`docs/SETUP_RPI4.md`](SETUP_RPI4.md) — RPi4B 설치 순서

---

# [DEPRECATED] 실차량 워크스페이스 전환 핸드오프 문서

> 아래 내용은 **역사적 참고용**으로만 보존. 차량 스펙 수치와 인터페이스 규약은 여전히 유효하지만
> 네임스페이스/경로/워크스페이스 구조는 현재 상태와 다르다.

---

## [CURRENT] 현재 실차 시스템 현황 (2026-06-23)

| 차량 | 네임스페이스 | IP | 상태 | launch |
|---|---|---|---|---|
| 메인 AGV | `aip1` | 192.168.0.3 | ✅ SLAM+Nav2 운용 중 | `fleet_main.launch.py` (RPi) + `main_agv.launch.py` (dev PC) |
| TurtleBot3 | `aip2` | 192.168.0.4 | 🔧 세팅 중 | `turtlebot3.launch.py` (RPi) |
| 자작 차량 | `aip3` | 192.168.0.5 | 🔧 STS3215 미구현 | `custom_vehicle.launch.py` (placeholder) |

중앙 PC(dev PC): `192.168.0.9` — Docker Central 스택 (대시보드 + supervisor)

---

## 1. [LEGACY] 프로젝트 배경

### 당시 상태 (2026-06-15)
- `~/aip_swarm_ws` — **시뮬레이션 전용** 워크스페이스 (Gazebo Ignition Fortress + ROS2 Humble)
- GitHub: `https://github.com/Mark2AC/aip-swarm-ws` (private)
- 3대 가상 차량(`peer_1/2/3`)으로 SLAM + Nav2 + 순찰 자율주행 시뮬 구현 완료

### 당시 작업 목표 (이미 완료/폐기됨)
실차량 3대를 위한 **별도 워크스페이스 `~/aip_real_ws`** 생성.
→ **폐기**: 이 구조는 모노레포 통합으로 대체됨. `aip_fleet_real` 패키지가 `aip_swarm_ws/src/`에 통합.

---

## 2. 실차량 구성 (확정 사항)

### 공통 사항
| 항목 | 값 |
|------|-----|
| 컴퓨팅 | **Raspberry Pi 4B** (전 차량 동일) |
| OS | Ubuntu 22.04 Server + ROS2 Humble |
| 측위 | **LiDAR + slam_toolbox** 독립 실행 (차량별 독립 SLAM, 공유 맵 없음) |
| UWB | **없음** (전면 배제 결정) |
| ROS_DOMAIN_ID | **42** |
| RMW | **rmw_fastrtps_cpp** + FastDDS Discovery Server (192.168.0.9:11811) |
| 네트워크 | Wi-Fi AP `AIP_FLEET` (192.168.0.0/24) |

### 차량 1 — 메인 AGV (`main`)
| 항목 | 값 |
|------|-----|
| 컴퓨팅 | RPi4B (Docker `my_ros_env`) |
| LiDAR | YDLIDAR (모델 확인 필요) |
| 구동 | DC모터 + 인코더 (FIT0186), diff-drive |
| 휠 간격 | 290mm / 휠 반경 60mm |
| 추가 센서 | 3~4 DOF 로봇암 + 열화상 + 가스 센서 |
| 기존 ROS2 WS | `my_ros_env:/root/colcon_ws` |

> ⚠️ **메인 AGV의 `my_ros_env:/root/colcon_ws`는 다른 팀원 관할이다. 절대 수정하지 않는다.**  
> 이 차량의 ROS2 인터페이스(토픽/TF)만 확인하여 연동한다.

### 차량 2 — TurtleBot3 Burger (`aip2`)
| 항목 | 값 |
|------|-----|
| 제조사 | 로보티즈(Robotis) |
| 모델 | **TurtleBot3 Burger** |
| LiDAR | **LDS-03** (turtlebot3_bringup 내장 드라이버 사용) |
| 구동 | DYNAMIXEL XL430-W250 × 2 |
| 휠 간격 | 160mm (axle_y = 0.080m) |
| 휠 반경 | 33mm (wheel_r = 0.033m) |
| 최대 선속도 | 0.22 m/s |
| 최대 각속도 | 2.84 rad/s |
| footprint 반경 | ~0.105m |
| 환경변수 | `TURTLEBOT3_MODEL=burger` |
| ROS2 패키지 | `ros-humble-turtlebot3*` (공식 패키지, 드라이버 포함) |

### 차량 3 — 자작 SLAM 차량 (`aip3`)
| 항목 | 값 |
|------|-----|
| 구동 | **Feetech STS3215 서보** (UART half-duplex 직렬 버스) |
| LiDAR | **미확정** (추후 확정 시 config에 추가) |
| ROS2 드라이버 | **미구현** — 이번 작업에서 placeholder만 생성 |

> STS3215 드라이버는 별도 세션에서 구현 예정. 이번 작업에서는 패키지 구조와 placeholder launch 파일만 만든다.

---

## 3. 워크스페이스 아키텍처

### 오버레이 구조
```
~/aip_swarm_ws/          ← 시뮬 워크스페이스 (건드리지 않음)
  install/setup.bash       ← aip_real_ws의 underlay

~/aip_real_ws/           ← 실차 워크스페이스 (이번 작업에서 생성)
  src/
    aip_fleet_real/        ← 실차 전용 패키지 (유일한 신규 패키지)
  install/
  build/
  log/
```

### 빌드 방법

**개발 PC에서:**
```bash
# underlay (시뮬 워크스페이스) 먼저 빌드
cd ~/aip_swarm_ws
colcon build --symlink-install

# overlay (실차 워크스페이스) 빌드
source ~/aip_swarm_ws/install/setup.bash
cd ~/aip_real_ws
colcon build --symlink-install
```

**RPi4B에서 (Gazebo 없이):**
```bash
# 공용 패키지만 선택 빌드 (시뮬 패키지 제외)
cd ~/aip_swarm_ws
colcon build --symlink-install \
  --packages-skip aip_fleet_gazebo aip_fleet_sim aip_fleet_foxglove_panels

# 실차 워크스페이스 빌드
source ~/aip_swarm_ws/install/setup.bash
cd ~/aip_real_ws
colcon build --symlink-install
```

### 시뮬 로직 변경 시 반영 방법
```bash
# 시뮬 워크스페이스에서 수정 후
cd ~/aip_swarm_ws && colcon build --symlink-install
# aip_real_ws는 underlay를 통해 자동 반영됨 (재빌드 불필요)
# RPi4B는 git pull + colcon build만 하면 됨
```

---

## 4. 표준 차량 인터페이스 (상위 로직과의 계약)

모든 차량은 아래 인터페이스를 **동일하게** 노출해야 한다.  
`aip_fleet_coordinator`, `aip_fleet_autonomous` 등 공용 패키지는 이 인터페이스만 본다.

```
입력  /<ns>/cmd_vel          geometry_msgs/Twist       — Nav2 속도 명령
출력  /<ns>/odom             nav_msgs/Odometry         — 주행 거리계
출력  /<ns>/scan             sensor_msgs/LaserScan     — LiDAR
출력  TF: <ns>/odom → <ns>/base_link                  — 오도메트리 TF
출력  TF: map → <ns>/odom                             — SLAM TF (slam_toolbox)

추가 (AIP 플릿 규약)
출력  /<ns>/heartbeat        aip_fleet_msgs/FleetHeartbeat
입력  /<ns>/estop            std_msgs/Bool
입력  /<ns>/override_cmd_vel geometry_msgs/Twist
```

네임스페이스 규약: `aip1`, `aip2`, `aip3` (구형 `main`/`scout_1`/`scout_2`는 폐기됨)

---

## 5. `aip_fleet_real` 패키지 목표 구조

```
src/aip_fleet_real/
├── package.xml
├── setup.py
├── launch/
│   ├── main_agv.launch.py        — 메인 AGV 연동 (인터페이스 확인 후 리매핑)
│   ├── turtlebot3.launch.py      — TB3 Burger bringup + 네임스페이스 리매핑
│   ├── custom_vehicle.launch.py  — 자작 차량 (placeholder, 드라이버 미구현)
│   └── fleet_real.launch.py      — 3대 통합 launch (각 차량 launch include)
├── config/
│   ├── turtlebot3/
│   │   ├── nav2_override.yaml    — 실차 전용 차이만 (footprint, 속도, use_sim_time)
│   │   └── slam_override.yaml    — scan_topic, frame_id 등 LDS-03 전용 설정
│   ├── main_agv/
│   │   ├── nav2_override.yaml
│   │   └── slam_override.yaml
│   └── custom_vehicle/
│       ├── nav2_override.yaml    — placeholder (LiDAR 미확정)
│       └── slam_override.yaml    — placeholder
└── resource/
    └── aip_fleet_real
```

> **핵심 원칙**: `config/` 파일들은 시뮬 파라미터의 복사본이 아니다.  
> 베이스(`aip_swarm_ws/params/`)는 그대로 유지하고, 실차에서 **달라지는 값만** override 파일에 기재한다.  
> 시뮬에서 알고리즘이 개선되면 베이스가 바뀌고, override는 그대로이므로 자동 반영된다.

---

## 6. 각 launch 파일 구현 지침

### 6-1. 파라미터 로드 패턴 (전 차량 공통)

ROS2는 Node에 `parameters=[file1, file2]` 형식으로 파라미터 파일을 순서대로 전달하면 **뒤 파일이 앞 파일을 덮어쓴다.** 이 동작을 이용해 base + override를 구현한다.

```python
import os, yaml, tempfile, string
from ament_index_python.packages import get_package_share_directory

def _load_nav2_params(vehicle_id: str, override_path: str) -> str:
    """베이스 nav2_full.yaml에 vehicle_id 치환 후 override를 deep-merge.
    결과를 임시 파일에 쓰고 경로를 반환한다."""
    auto_share  = get_package_share_directory('aip_fleet_autonomous')
    base_path   = os.path.join(auto_share, 'params', 'nav2_full.yaml')

    # 베이스: ${vehicle_id} 치환
    with open(base_path) as f:
        base_str = string.Template(f.read()).substitute(vehicle_id=vehicle_id)
    params = yaml.safe_load(base_str)

    # override: 실차 전용 차이 적용
    if os.path.exists(override_path):
        with open(override_path) as f:
            override = yaml.safe_load(f) or {}
        _deep_merge(params, override)

    # 임시 파일로 저장 (Nav2 params_file 인수 요구)
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
    yaml.dump(params, tmp)
    tmp.flush()
    return tmp.name

def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
```

이 헬퍼 함수를 `turtlebot3.launch.py`, `main_agv.launch.py`, `custom_vehicle.launch.py` 모두에서 재사용한다.

### 6-2. `turtlebot3.launch.py`

TurtleBot3 공식 bringup을 실행하되, 모든 토픽을 AIP 네임스페이스로 리매핑한다.

```python
# 환경변수 필수
os.environ['TURTLEBOT3_MODEL'] = 'burger'

# 실행할 것
# 1. turtlebot3_bringup robot.launch.py  (LDS-03 드라이버 포함)
# 2. slam_toolbox (online_async) — slam_override.yaml 적용
# 3. Nav2 — _load_nav2_params('scout_1', nav2_override_path) 결과 파일 사용
# 4. twist_mux — aip_swarm_ws의 twist_mux_vehicle.yaml 그대로 사용

# 토픽 리매핑 (PushRosNamespace 또는 remappings 파라미터)
# /cmd_vel  → /scout_1/cmd_vel
# /odom     → /scout_1/odom
# /scan     → /scout_1/scan
# /imu      → /scout_1/imu
```

### 6-3. `custom_vehicle.launch.py`

STS3215 드라이버 미구현 → placeholder 경고 출력 후 slam_toolbox/Nav2만 실행.

```python
# TODO: STS3215 ros2_control hardware_interface 구현 후 활성화
# 현재는 /scout_2/cmd_vel 수신만 되고 실제 모터 제어 없음
```

### 6-4. `fleet_real.launch.py`

세 차량 launch를 include하는 통합 런치. 인수로 어떤 차량을 기동할지 선택 가능하게:
```
with_main:=true/false
with_tb3:=true/false
with_custom:=true/false
```

---

## 7. 파라미터 override 파일 작성 기준

### 원칙

| 구분 | 위치 | 관리 주체 |
|------|------|---------|
| 베이스 (알고리즘·비용함수·플래너 설정) | `aip_swarm_ws/params/nav2_full.yaml` | 시뮬 팀 (수정 금지) |
| override (실차 전용 차이) | `aip_fleet_real/config/<vehicle>/nav2_override.yaml` | 실차 팀 |

시뮬에서 알고리즘이 개선되면 베이스가 업데이트되고, override 파일은 그대로이므로 **자동 반영**된다. override 파일에는 실차 하드웨어에 종속된 값만 기재한다.

### `config/turtlebot3/nav2_override.yaml`

```yaml
# ── 실차 전용 차이만 기재 ───────────────────────────────────────────────────
# Base: aip_swarm_ws/src/aip_fleet_autonomous/params/nav2_full.yaml
# 여기 없는 값은 모두 베이스에서 그대로 사용된다.

# 1. 시뮬 시간 해제 (전 노드 공통 — 베이스의 use_sim_time: true를 덮어씀)
/${vehicle_id}/amcl:
  ros__parameters:
    use_sim_time: false
/${vehicle_id}/controller_server:
  ros__parameters:
    use_sim_time: false
/${vehicle_id}/bt_navigator:
  ros__parameters:
    use_sim_time: false
/${vehicle_id}/planner_server:
  ros__parameters:
    use_sim_time: false
/${vehicle_id}/global_costmap/global_costmap:
  ros__parameters:
    use_sim_time: false
/${vehicle_id}/local_costmap/local_costmap:
  ros__parameters:
    use_sim_time: false

# 2. TB3 Burger 물리 스펙 (베이스의 메인 AGV 수치를 덮어씀)
/${vehicle_id}/controller_server:
  ros__parameters:
    FollowPath:
      max_vel_x: 0.20        # Burger 최대 0.22m/s, 안전 마진 적용
      min_vel_x: -0.10
      max_vel_theta: 2.50

/${vehicle_id}/local_costmap/local_costmap:
  ros__parameters:
    robot_radius: 0.105      # Burger footprint (외접원 ~105mm)

/${vehicle_id}/global_costmap/global_costmap:
  ros__parameters:
    robot_radius: 0.105
```

> `${vehicle_id}`는 launch 파일의 `_load_nav2_params()` 가 호출 시 실제 네임스페이스(`scout_1` 등)로 치환한다.

### `config/turtlebot3/slam_override.yaml`

```yaml
# Base: aip_swarm_ws/src/aip_fleet_nav/params/slam_toolbox_online.yaml
slam_toolbox:
  ros__parameters:
    use_sim_time: false
    odom_frame:  scout_1/odom       # 실제 네임스페이스로 변경
    base_frame:  scout_1/base_link
    scan_topic:  /scout_1/scan      # turtlebot3_bringup 리매핑 결과 토픽
```

### `config/custom_vehicle/nav2_override.yaml` (placeholder)

```yaml
# PLACEHOLDER — LiDAR 모델 및 STS3215 드라이버 확정 후 작성
# 현재 비어 있음: 베이스 파라미터만 적용됨
```

---

## 8. RPi4B 환경 설정

### 필수 apt 패키지
```bash
sudo apt install -y \
  ros-humble-navigation2 \
  ros-humble-nav2-bringup \
  ros-humble-slam-toolbox \
  ros-humble-turtlebot3 \
  ros-humble-turtlebot3-bringup \
  ros-humble-twist-mux \
  ros-humble-robot-localization \
  ros-humble-rmw-fastrtps-cpp
```

### 환경변수 설정 (`~/.bashrc` 또는 `~/.bash_aliases`)
```bash
source ~/aip_swarm_ws/install/setup.bash
source ~/aip_real_ws/install/setup.bash

export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export TURTLEBOT3_MODEL=burger   # TB3 차량에서만

# FastDDS Discovery Server 클라이언트 모드
export FASTRTPS_DEFAULT_PROFILES_FILE=~/aip_swarm_ws/config/fastdds_client_profile.xml
```

---

## 9. 금지 사항 (반드시 준수)

| 금지 | 이유 |
|------|------|
| `~/aip_swarm_ws/src/` 내 기존 파일 수정 | 시뮬 워크스페이스 오염 방지 |
| `my_ros_env:/root/colcon_ws` 수정 | 메인 AGV 담당 팀원 관할 |
| `config/security/keystore/` 커밋 | 보안 (`.gitignore` 등재됨) |
| `docker/central/.env` 커밋 | 시크릿 포함 |
| `use_sim_time: true` 실차 launch에 사용 | 실차에서 시뮬 시간 사용 시 Nav2 동작 불가 |
| UWB 관련 노드 실차 launch에 포함 | UWB 전면 배제 결정 (2026-06-15) |

---

## 10. 작업 체크리스트

### Phase 1 — 워크스페이스 스캐폴딩 (이번 세션)
- [ ] `~/aip_real_ws/` 디렉터리 생성
- [ ] `src/aip_fleet_real/` 패키지 생성 (package.xml, setup.py)
- [ ] 디렉터리 구조 생성 (launch/, config/ 서브디렉터리)
- [ ] `colcon build` 통과 확인 (빈 패키지)
- [ ] `docs/SETUP_RPI4.md` 작성 (RPi4B 환경 구성 가이드)

### Phase 2 — TurtleBot3 Burger 연동
- [ ] `_load_nav2_params()` / `_deep_merge()` 헬퍼 함수 작성 (6-1절 참고)
- [ ] `turtlebot3.launch.py` 작성
  - turtlebot3_bringup 포함 (LDS-03 드라이버 내장)
  - 네임스페이스 리매핑 (`/scout_1/`)
  - slam_toolbox — `slam_override.yaml` 적용
  - Nav2 — `_load_nav2_params('scout_1', nav2_override_path)` 사용
  - twist_mux — `aip_swarm_ws`의 `twist_mux_vehicle.yaml` 재사용
- [ ] `config/turtlebot3/nav2_override.yaml` 작성 (7절 내용 그대로)
- [ ] `config/turtlebot3/slam_override.yaml` 작성 (7절 내용 그대로)
- [ ] RPi4B에서 빌드 및 단독 주행 테스트

### Phase 3 — 자작 차량 placeholder
- [ ] `custom_vehicle.launch.py` 작성 (placeholder + 경고 메시지)
- [ ] `config/custom_vehicle/nav2_override.yaml` — placeholder (빈 파일)
- [ ] `config/custom_vehicle/slam_override.yaml` — placeholder (빈 파일)
- [ ] STS3215 드라이버 선정 결정 (별도 세션)

### Phase 4 — 통합
- [ ] `fleet_real.launch.py` 작성 (3대 통합)
- [ ] 메인 AGV 인터페이스 확인 후 `main_agv.launch.py` 작성
- [ ] 멀티 SLAM 맵 공유 전략 결정 (map_merge vs 독립 내비게이션)

---

## 11. 참고 파일 경로 (`aip_swarm_ws` 기준)

| 목적 | 경로 |
|------|------|
| Nav2 파라미터 (시뮬 원본) | `src/aip_fleet_autonomous/params/nav2_full.yaml` |
| EKF 파라미터 | `src/aip_fleet_nav/params/ekf_vehicle.yaml` |
| slam_toolbox 파라미터 | `src/aip_fleet_nav/params/slam_toolbox_online.yaml` |
| twist_mux 설정 | `src/aip_fleet_bringup/config/twist_mux_vehicle.yaml` |
| 환경 설정 스크립트 | `aip_env.sh` |
| FastDDS 클라이언트 프로파일 | `config/fastdds_sim_profile.xml` (실차용은 별도 확인) |
| 네임스페이스 규약 전체 | `docs/ARCHITECTURE.md` |
| 보안 규칙 | `docs/SECURITY.md` |
| 의사결정 이력 | `docs/agent_context/conversation_log.md` |
| 차량 스펙 메모리 | `docs/agent_context/memory/project_fleet_vehicle_specs.md` |

---

## 12. 완료 기준

이번 세션이 끝났을 때 다음이 모두 충족돼야 한다.

1. `~/aip_real_ws/` 가 존재하고 `colcon build` 가 통과한다.
2. `aip_fleet_real` 패키지가 `ros2 pkg list` 에 나타난다.
3. `turtlebot3.launch.py` 가 TB3 네임스페이스 리매핑을 포함하고, Nav2 파라미터가 `_load_nav2_params()` 를 통해 base + override 병합으로 로드된다.
4. `config/turtlebot3/nav2_override.yaml` 에 `use_sim_time: false` 와 Burger 물리 스펙만 기재돼 있다 (베이스 파일의 복사본이 아님).
5. `docs/SETUP_RPI4.md` 가 존재하고 RPi4B에서 처음 세팅하는 팀원이 따라할 수 있는 수준이다.
6. `aip_swarm_ws` 의 어떤 파일도 수정되지 않았다.
