# 실차량 — `aip_fleet_real` (모노레포 내 실차 bringup)

실차량 3대(`main`, `scout_1`, `scout_2`)를 위한 ROS2 Humble 실차 bringup.
**2026-06-15 모노레포로 통합**됨 — 별도 워크스페이스(`aip_real_ws`)를 폐기하고
`aip-swarm-ws` 레포 **한 곳**에서 시뮬과 실차 패키지를 함께 관리한다.
sim/real 분리는 브랜치가 아니라 **colcon 빌드 타겟**(`--packages-select/skip`)으로 한다.

> 이 문서가 실차 부분의 최신 진입점이다. 초기 스캐폴딩 지침서
> `docs/HANDOFF_REAL_WS.md` 의 "별도 워크스페이스 / aip_swarm_ws 무수정" 전제는 본 통합으로
> **무효**다(나머지 인터페이스 규약·차량 스펙·금지사항은 유효).

## 구조

```
aip_swarm_ws/                         # 단일 모노레포 (github.com/Mark2AC/aip-swarm-ws)
├── docs/
│   ├── REAL_WS.md                    # (이 문서) 실차 진입점
│   └── SETUP_RPI4.md                 # RPi4B 의존성 설치 순서 + 환경 구성
└── src/
    ├── aip_fleet_msgs                # 공용 인터페이스 (sim·real 공유)
    ├── aip_fleet_autonomous          # 공용 노드 — patrol_node(순찰) 등
    ├── aip_fleet_coordinator         # 공용 노드 (협력 측위/convoy, 실차 통합 예정)
    ├── aip_fleet_gazebo / _sim / _foxglove_panels   # 기존 Ignition 시뮬 (별개)
    └── aip_fleet_real/               # ◀ 실차 bringup + scout_1 TB3 시뮬
        ├── launch/
        │   ├── turtlebot3.launch.py     # scout_1 실차: TB3 + SLAM + Nav2 + twist_mux + (옵션)순찰
        │   ├── turtlebot3_sim.launch.py # scout_1 시뮬: Gazebo Classic + 위 스택(use_sim_time)
        │   ├── custom_vehicle.launch.py # scout_2: 자작 차량 (placeholder)
        │   ├── main_agv.launch.py       # main: 인터페이스 확인 전용
        │   └── fleet_real.launch.py     # 통합 (with_main/with_tb3/with_custom/with_patrol)
        └── config/
            ├── turtlebot3/{slam_toolbox,nav2,twist_mux,patrol}.yaml          # 실차
            ├── turtlebot3/{slam_toolbox_sim,nav2_sim,patrol_sim}.yaml        # 시뮬
            ├── custom_vehicle/{slam_toolbox,nav2}.yaml   # placeholder
            └── main_agv/{slam_toolbox,nav2}.yaml         # reference only
```

## 차량 구성

| ns | 차량 | 컴퓨팅 | 구동 | LiDAR | 상태 |
|---|---|---|---|---|---|
| `main` | 메인 AGV | RPi4B (`my_ros_env` 컨테이너, 타 팀원 관할) | DC모터+인코더, 휠간격 290mm | YDLIDAR | 인터페이스 확인만 |
| `scout_1` | TurtleBot3 Burger | RPi4B | DYNAMIXEL XL430×2, 휠간격 160mm | LDS-03 | bringup + 순찰 + 시뮬 |
| `scout_2` | 자작 차량 | RPi4B | Feetech STS3215 서보 | 미확정 | placeholder |

공통: ROS2 Humble, ROS_DOMAIN_ID=42, rmw_fastrtps_cpp + FastDDS Discovery Server
(192.168.0.9:11811), Wi-Fi AP `AIP_FLEET`. **UWB 미사용**(2026-06-15 전면 배제).
측위는 차량별 독립 LiDAR + slam_toolbox(공유 맵 없음).

## 빌드 (단일 워크스페이스)

```bash
cd ~/aip_swarm_ws

# 개발 PC (시뮬 포함 전체)
colcon build --symlink-install

# RPi4B (Gazebo 없음 → 시뮬 전용 패키지 제외)
colcon build --symlink-install \
  --packages-skip aip_fleet_gazebo aip_fleet_sim aip_fleet_foxglove_panels

# 실차 패키지만 빠르게 (의존 포함)
colcon build --symlink-install --packages-up-to aip_fleet_real

source install/setup.bash
ros2 pkg list | grep aip_fleet_real   # → aip_fleet_real
```

상세 환경 구성: [`SETUP_RPI4.md`](SETUP_RPI4.md).

## 실차 실행

```bash
ros2 launch aip_fleet_real turtlebot3.launch.py                     # scout_1 단독(수동 goal)
ros2 launch aip_fleet_real turtlebot3.launch.py with_patrol:=true   # scout_1 + 순찰 자동 시작
ros2 launch aip_fleet_real fleet_real.launch.py with_tb3:=true with_patrol:=true
```

## 시뮬 검증 (Gazebo Classic, 개발 PC)

실차 제작 전에 scout_1 파이프라인(SLAM→Nav2→twist_mux→patrol)을 시뮬로 검증한다.
실차 `turtlebot3.launch.py`의 하드웨어 bringup만 Gazebo 스폰으로 교체하고, 그 위 스택은
동일하다(`twist_mux.yaml`·`patrol_node` 재사용, slam/nav2는 frame+use_sim_time만 바꾼 `*_sim.yaml`).

```bash
# 1) 시뮬 의존 설치 (시뮬 PC에서만 — RPi4B 에는 불필요)
sudo apt install -y ros-humble-turtlebot3-gazebo ros-humble-turtlebot3-simulations

# 2) 빌드 + 실행
cd ~/aip_swarm_ws && colcon build --packages-up-to aip_fleet_real && source install/setup.bash
export TURTLEBOT3_MODEL=burger
ros2 launch aip_fleet_real turtlebot3_sim.launch.py with_patrol:=true
```

확인 항목:
- Gazebo GUI 에 TB3 Burger 스폰, `ros2 topic hz /scout_1/scan`
- TF `map → odom → base_footprint`(slam_toolbox)
- RViz2: SLAM 맵 생성 + `/scout_1/patrol_path_viz` 마커 + 로봇이 waypoint 순환 주행
- `ros2 topic echo /scout_1/cmd_vel` 에 twist_mux 출력(순찰 시 autonomy 슬롯)

> ⚠️ `turtlebot3_gazebo`/`turtlebot3_description`은 **`package.xml` 의존이 아니다**
> (RPi4B rosdep 이 무거운 Gazebo 를 깔지 않도록). 시뮬 PC 에서만 위 apt 로 설치한다.
> 순찰 좌표(`patrol_sim.yaml`)는 turtlebot3_world 기준 placeholder — RViz 로 보며 조정.

## 순찰 미션 (patrol_node)

`with_patrol:=true` 시 `aip_fleet_autonomous`의 `patrol_node`가 기동되어,
`patrol(.yaml|_sim.yaml)`의 웨이포인트를 `/scout_1/navigate_to_pose` 액션으로 순환 전송한다.
Nav2 `bt_navigator`가 이를 실행 → 독립 자율 순찰.

- **웨이포인트는 SLAM map 프레임 좌표**(`waypoints: [x,y,yaw_deg, …]`).
- `loop_patrol: true`면 무한 순환. `start_delay_sec`로 첫 goal 지연(Nav2 활성화 대기).
- 미매핑 웨이포인트 skip 판정을 위해 `/map_static`을 `/map`으로 remap
  (slam_toolbox는 네임스페이스 무관 절대경로 `/map` 발행).

## cmd_vel 우선순위 체인 (twist_mux)

```
Nav2 controller/behavior --(cmd_vel→autonomy_cmd_vel)--> /<ns>/autonomy_cmd_vel (prio 10)
operator override        --------------------------------> /<ns>/override_cmd_vel (prio 80)
coordinator convoy       --------------------------------> /<ns>/coord_cmd_vel    (prio 50)
                                          twist_mux ──> /<ns>/cmd_vel ──> 모터/플러그인
```

## 주의 (HANDOFF_REAL_WS.md §9 중 유효 항목)

- `my_ros_env:/root/colcon_ws`(메인 AGV 차량 SW) 수정 금지 — 타 팀원 관할
- 실차 launch 에 `use_sim_time: true` 사용 금지 (항상 false) — 시뮬 launch 는 true
- UWB 관련 노드 포함 금지
- 시크릿 커밋 금지 (`docker/central/.env`, `firmware/scout_microros/secrets.ini`)
