# AIP 군집 순찰 로봇 프로젝트 — 종합 개요

> 작성일: 2026-05-20  
> 버전: Phase-2 (자율 내비게이션 + 군집 제어)  
> 피드백 요청용 문서 — 설계·구현·한계를 솔직하게 기술함

---

## 1. 프로젝트 개요

### 1.1 목표 및 컨셉

다수의 소형 AGV(Automated Guided Vehicle)를 자율적으로 군집 운용하여 **실내 창고/공장 환경의 자율 순찰 및 감시**를 수행하는 ROS2 기반 멀티로봇 시스템.

- **운용 개념**: 3대의 차량이 역할을 분담하여 광역 공간을 순찰
  - `peer_1` (리더): SLAM 수행, 지도 생성, 북쪽 구역 탐색
  - `peer_2`: 동쪽·북쪽 열원 구역 순찰 (문 통과 포함)
  - `peer_3`: 남쪽·서쪽 구역 순찰
- **속도**: 0.2–0.5 m/s (저속 운용 — 감지 품질 우선)
- **순찰 주기**: 각 차량 독립적으로 waypoint 루프 반복
- **열원 감지 시나리오**: MLX90640 열화상 카메라로 비정상 열원 감지 (실하드웨어)

### 1.2 시뮬레이션 시나리오 (fleet_world)

- **환경**: 20m×20m 창고 (Ignition Fortress SDF)
- **주요 지형 요소**:
  - 외벽: 4방향 (±10m)
  - 내부 격리 벽: y=4.0m 위치, 0.70m 개구부(doorway) 구비
  - `shelf_center`: x=[-3,3], y=6.0m — 선반 장애물
  - `heat_source_fire`: (2.0, 7.5) — 화재 열원 시뮬레이션 대상
  - `heat_source_shelf`: (-2.0, 6.0) — 선반 내 열원

### 1.3 개발 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| Phase-1 | V-포메이션 추종 (coordinator_node) + slam_toolbox | ✅ 완료 |
| Phase-2 | 독립 자율 항법 (Nav2 per vehicle) + 커버리지 순찰 | 🔄 진행 중 |
| Phase-3 | 실하드웨어 통합 (메인 AGV + ESP32 Scout) | 📋 예정 |

---

## 2. 차량 하드웨어 스펙

### 2.1 주행 시스템

| 항목 | 사양 |
|---|---|
| 구동 방식 | 차동 구동 (Differential Drive) |
| 모터 | FIT0186 12V DC, 감속비 43.8:1 |
| 바퀴 지름 | 120mm (반경 60mm) |
| 바퀴 간격(wheel_separation) | 290mm |
| 차체 크기 (L×W×H) | 300mm × 230mm × (미정) |
| 최대 이론 속도 | 1.58 m/s |
| 운용 속도 상한 | 0.5 m/s (이론치의 32%) |
| robot_radius (Nav2) | 0.19m = √((0.230/2)²+(0.300/2)²) |

### 2.2 센서 구성 (실 하드웨어 기준)

| 센서 | 모델 | 인터페이스 | 용도 |
|---|---|---|---|
| RGB 카메라 | OV5647 | CSI-2 | 시각 정보 |
| 열화상 카메라 | MLX90640 | I2C → ESP32 → micro-ROS | 열원 감지 |
| LiDAR | (사양 미정) | USB/UART | SLAM, 장애물 회피 |
| IMU | (내장 or 외부) | SPI/I2C | EKF 자이로 융합 |
| 서보 암 | 4축 | PWM | 물체 조작 (옵션) |

### 2.3 시뮬레이션 센서 (Ignition Fortress)

| 센서 | 타입 | 특성 |
|---|---|---|
| LiDAR (GPU) | `ignition::gazebo::systems::Sensors` | 최대 범위 7.5m, `inf_is_valid=true` 필수 |
| IMU | `ignition::gazebo::systems::Imu` | 자이로만 EKF에 사용 (절대 orientation 미사용) |

---

## 3. 시스템 환경

### 3.1 네트워크 구성

| 항목 | 값 |
|---|---|
| Wi-Fi AP | AIP_FLEET (전용 AP) |
| 서브넷 | 192.168.0.0/24 |
| Discovery Server | 192.168.0.9:11811 |
| ROS_DOMAIN_ID | 42 |
| DDS | FastDDS + Discovery Server 모드 |

### 3.2 소프트웨어 환경

| 항목 | 버전/설명 |
|---|---|
| OS | Ubuntu 22.04 (호스트) / Windows 11 (개발 겸용) |
| ROS2 | Humble Hawksbill |
| Gazebo | Ignition Fortress |
| micro-ROS Agent | UDP4:8888 (ESP32-S3 스카우트용) |
| Foxglove Bridge | WebSocket:8765 |
| 배포 방식 | Docker Compose 중심 |

### 3.3 ROS2 패키지 구성

```
aip_swarm_ws/src/
├── aip_fleet_bringup/       # 브링업 설정 (twist_mux YAML 등)
├── aip_fleet_coordinator/   # 군집 제어 노드 (coordinator, uwb_localizer)
├── aip_fleet_gazebo/        # Ignition 시뮬레이션 (world, launch, scripts)
├── aip_fleet_msgs/          # 커스텀 메시지 (PeerRange, PeerPose, PerceptionAlert)
├── aip_fleet_nav/           # Nav2 파라미터 (AMCL, EKF, slam_toolbox)
├── aip_fleet_autonomous/    # 독립 자율 내비게이션 (patrol_node, launch)
├── aip_fleet_perception/    # 인식 파이프라인 (예정)
└── aip_main_description/    # 차량 URDF (main_agv.urdf.xacro)
```

---

## 4. 소프트웨어 스택 상세

### 4.1 차량 스폰 파이프라인 (spawn_vehicle.launch.py)

각 차량 스폰 시 아래 노드들이 순차적으로 시작된다:

```
t=0s   robot_state_publisher  — URDF→ロボット記述 발행 (/<vid>/robot_description)
       Ignition create        — 월드에 URDF 엔티티 생성
       ros_gz_bridge          — Ignition 토픽 → ROS2 토픽 변환
       static_transform_publisher — base_link → base_footprint (identity TF)

t=6s   joint_state_broadcaster — 관절 상태 발행 (ros2_control)
       diff_drive_controller   — 차동 구동 제어기 (ros2_control)

t=7s   cmd_relay.py           — /<vid>/cmd_vel → diff_drive input
       odom_frame_fixer.py    — 오도메트리 프레임 ID 교정
       odom_relay             — diff_drive/odom → /<vid>/odom

t=8s   ekf_node               — 센서 융합: 바퀴 인코더 + IMU → 필터링 odom
```

**핵심 설계 결정사항:**

- `enable_odom_tf: false` (diff_drive_controller): EKF가 TF를 발행하므로 충돌 방지
- `odom_frame_fixer.py`: `diff_drive_controller`가 발행하는 프레임 ID `'odom'`을 `'peer_N/odom'`으로 교정. SLAM/AMCL은 네임스페이스가 포함된 프레임 ID를 요구.
- `base_footprint` 정적 TF: RViz 기본 설정이 `base_footprint`를 참조하지만 URDF 루트는 `base_link`이므로 identity TF로 연결.

### 4.2 EKF 센서 융합 파이프라인

**파일**: `src/aip_fleet_nav/params/ekf_vehicle.yaml`

```
diff_drive_controller/odom (50 Hz) ──→ odom_frame_fixer.py ──→ /<vid>/diff_drive_controller/odom_corrected
                                                                         │
/<vid>/imu (100 Hz) ──────────────────────────────────────────────────── ┤
                                                                         ▼
                                                               ekf_node (robot_localization)
                                                                         │
                                          ┌──────────────────────────────┤
                                          ▼                              ▼
                               /<vid>/odometry/filtered      TF: <vid>/odom → <vid>/base_link
```

**EKF 파라미터:**

| 항목 | 값 | 비고 |
|---|---|---|
| frequency | 50 Hz | 바퀴 인코더와 동기 |
| two_d_mode | true | 3D 상태 억제, 2D diff-drive에 필수 |
| publish_tf | true | EKF가 odom→base_link TF 권위 발행 |
| Sensor 0 (wheel odom) | x, y, yaw, vx, vyaw 융합 | odom0_relative=true |
| Sensor 1 (IMU) | 각속도 z만 사용 (gyro) | 절대 orientation 미사용 |

**IMU에서 각속도만 사용하는 이유**: 시뮬레이터(및 실하드웨어)에서 자력계가 없으므로 절대 헤딩 기준이 없다. IMU 자이로는 단기 yaw rate 정밀도에서 바퀴 미끄럼보다 우수하다.

**process_noise_covariance**: 2D 모드 유효 상태 5개 (x, y, yaw, vx, vyaw)에 대해 Q 대각 원소 설정 (0.05, 0.05, 0.06, 0.025, 0.02).

### 4.3 SLAM (slam_toolbox, peer_1 전용)

**파일**: `src/aip_fleet_nav/launch/slam_leader.launch.py`  
**파라미터**: `src/aip_fleet_nav/params/slam_toolbox_online.yaml`

- `peer_1`만 SLAM을 수행하여 전역 `/map` 토픽 생성
- `slam_toolbox`는 `map → peer_1/odom` TF를 발행 (AMCL 불필요)
- 다른 차량(peer_2/3)은 AMCL로 이 지도에서 자기 위치만 추정

**단일 SLAM 리더 한계**:
- `peer_1`이 스캔하지 못한 영역(doorway 북쪽)은 지도에 포함되지 않음
- 해결책: `peer_1`이 탐색 경로를 먼저 완주하여 전체 지도 구축 후 peer_2/3 시작

### 4.4 Nav2 전체 스택

**파일**: `src/aip_fleet_autonomous/params/nav2_full.yaml`

#### 4.4.1 AMCL (peer_2/3 위치 추정)

| 파라미터 | 값 | 설명 |
|---|---|---|
| min_particles | 1000 | 최소 파티클 수 |
| max_particles | 3000 | 최대 파티클 수 |
| laser_model_type | likelihood_field | 레이저 모델 |
| laser_max_range | 7.5 m | LiDAR 최대 유효 거리 |
| update_min_d | 0.05 m | 최소 이동 거리 (업데이트 트리거) |
| update_min_a | 0.10 rad | 최소 회전량 |
| transform_tolerance | 1.0 s | sim_time 점프 대응 (기본 0.3s) |
| robot_model_type | DifferentialMotionModel | 차동 구동 운동 모델 |

**AMCL 수렴 조건**: 지도 특징이 존재하는 위치에서 시작해야 파티클이 수렴. 지도에 없는 구역에서 시작 시 발산.

#### 4.4.2 Global Planner (SmacPlannerHybrid, Hybrid-A*)

Hybrid-A*를 선택한 이유: 좁은 통로(doorway 0.70m)에서 차량 최소 회전 반경을 경로에 강제하여 실행 불가능한 경로를 원천 차단.

| 파라미터 | 값 | 설명 |
|---|---|---|
| motion_model_for_search | REEDS_SHEPP | 후진 허용 (diff-drive 최적) |
| minimum_turning_radius | 0.145 m | wheel_sep/2 = 0.290/2 |
| angle_quantization_bins | 72 | 헤딩 이산화: 5° 간격 |
| tolerance | 0.25 m | 목표 도달 허용 반경 |
| reverse_penalty | 2.1 | 후진 비용 배율 |
| max_planning_time | 5.0 s | 계획 최대 허용 시간 |
| allow_unknown | true | 미탐색 영역 통과 허용 |

#### 4.4.3 Controller Server (DWB Local Planner)

| 파라미터 | 값 | 설명 |
|---|---|---|
| controller_frequency | 10.0 Hz | 제어 주파수 |
| max_vel_x | 0.5 m/s | 최대 전진 속도 |
| max_vel_theta | 2.0 rad/s | 최대 회전 속도 |
| sim_time | 1.5 s | 궤적 시뮬레이션 시간 |
| transform_tolerance | 1.0 s | **sim_time 점프 대응** (기본 0.5s) |
| xy_goal_tolerance | 0.10 m | 목표 위치 허용 오차 |
| yaw_goal_tolerance | 0.15 rad | 목표 헤딩 허용 오차 |

**DWB Critics (비용 함수)**:
- `PathAlign (32.0)`, `PathDist (32.0)`: 경로 추종 강제
- `GoalAlign (24.0)`, `GoalDist (24.0)`: 목표 지향
- `RotateToGoal (32.0)`: 목표 도달 전 헤딩 정렬
- `BaseObstacle (0.02)`: 장애물 회피 (낮은 가중치 — 로컬 코스트맵 의존)

#### 4.4.4 Progress Checker

| 파라미터 | 값 | 설명 |
|---|---|---|
| required_movement_radius | 0.3 m | 최소 진행 반경 (기존 0.5m) |
| movement_time_allowance | 20.0 s | 최대 대기 시간 (기존 10s) |

**"Failed to make progress" ABORT 문제 해결**: LiDAR 드롭(sim_time 점프) → 로컬 코스트맵 데이터 손실 → DWB 진동 → progress_checker 타임아웃. 반경 완화(0.5→0.3m) + 시간 연장(10→20s)으로 해결.

#### 4.4.5 Local Costmap (다중 로봇 충돌 방지)

```yaml
observation_sources: scan peer_obstacles

peer_obstacles:          # peer_obstacle_node.py 가 발행하는 가상 PointCloud2
  topic:     /<vid>/peer_obstacles
  data_type: PointCloud2
  marking:   True
  clearing:  False       # 소거는 rolling window에 위임
```

#### 4.4.6 BT (Behavior Tree) 선택

`navigate_w_replanning_only_if_path_becomes_invalid.xml`:
- 기본 `navigate_to_pose_w_replanning_and_recovery.xml` 대비 복구 행동 최소화
- 실패 시 즉각 ABORT → patrol_node가 다음 waypoint로 진행
- 시뮬에서 복구 행동(spin, back-up)이 추가 TF 문제 유발하는 것을 방지

#### 4.4.7 peer_1 전용 Nav2 (leader_nav.launch.py)

`peer_1`은 slam_toolbox가 이미 `map → peer_1/odom` TF를 발행하므로 AMCL이 불필요:

```
autonomous_nav.launch.py  →  AMCL + planner + BT + DWB + lifecycle (4 nodes)
leader_nav.launch.py      →          planner + BT + DWB + lifecycle (3 nodes, AMCL 없음)
```

### 4.5 V-포메이션 군집 제어 (coordinator_node.py)

**파일**: `src/aip_fleet_coordinator/aip_fleet_coordinator/coordinator_node.py`

Phase-1에서 사용한 V-포메이션 추종 제어기. TF 기반 P-제어 구조.

#### 제어 알고리즘

```
leader pose (lx, ly, lθ) 와 follower pose (fx, fy, fθ) 를 TF map frame 에서 취득

목표점 (tx, ty) = 리더 body frame의 오프셋을 map frame으로 변환:
  tx = lx + offset_x·cos(lθ) - offset_y·sin(lθ)
  ty = ly + offset_x·sin(lθ) + offset_y·cos(lθ)

dist = √((tx-fx)² + (ty-fy)²)
alpha = atan2(ty-fy, tx-fx) - fθ  (목표 방위각, follower body frame)

Two-phase control:
  Phase 1 (|alpha| > 1.05 rad ≈ 60°): 제자리 회전, 전진 없음
  Phase 2 (|alpha| ≤ 1.05 rad):       v = kp_linear * dist 로 전진

cmd.linear.x  = clip(v, ±v_max)
cmd.angular.z = clip(kp_angular * alpha, ±w_max)
```

#### 제어 파라미터

| 파라미터 | 값 | 설명 |
|---|---|---|
| kp_linear | 0.8 | 선속도 게인 |
| kp_angular | 1.5 | 각속도 게인 |
| max_linear_vel | 0.5 m/s | 선속도 상한 |
| max_angular_vel | 1.5 rad/s | 각속도 상한 |
| goal_tolerance | 0.15 m | dead-band 반경 |
| alpha_turn_threshold | 1.05 rad | Phase 전환 임계 |
| tf_stale_holdout_sec | 1.0 s | TF 누락 시 캐시 유지 |
| CONTROL_HZ | 10 Hz | 제어 주기 |

#### V-포메이션 오프셋

```python
'peer_2': offset_x=-1.5, offset_y=+1.0   # 리더 기준 좌-후방 1.5m×1.0m
'peer_3': offset_x=-1.5, offset_y=-1.0   # 리더 기준 우-후방 1.5m×1.0m
```

**TF stale holdout**: UWB 신호 순단 등으로 TF lookup 실패 시 1.0초 동안 마지막 알려진 위치 사용. 순간적인 속도 스파이크 방지.

### 4.6 UWB 측위 시뮬레이션 (sim_peer_sensing_node.py)

**파일**: `src/aip_fleet_gazebo/scripts/sim_peer_sensing_node.py`

TF map frame에서 각 차량의 실제 위치를 읽어 UWB 센서 데이터를 시뮬레이션.

#### 발행 토픽

| 토픽 | 타입 | 내용 |
|---|---|---|
| `/fleet/peer_poses` | `PeerPoseArray` | SLAM 기반 절대 위치 (10Hz) |
| `/fleet/peer_ranges` | `PeerRangeArray` | 차량쌍 거리 + AoA + 노이즈 (10Hz) |

#### 노이즈 모델

- **거리 노이즈**: `range = true_dist + N(0, σ_r)`, σ_r = 0.05m (5cm)
- **AoA 노이즈**: `aoa = true_bearing_body_frame + N(0, σ_aoa)`, σ_aoa = 0.087 rad (5°)
- `max_range_m = 10.0m` 초과 시 측정값 드롭

#### PDoA AoA 계산

```python
# 수신기(receiver) A에서 송신기(transmitter) B의 AoA
bearing_map = atan2(B_y - A_y, B_x - A_x)   # 맵 프레임에서 방위각
aoa_body    = wrap(bearing_map - θ_A)         # A body 프레임으로 변환
aoa_a       = wrap(aoa_body + N(0, σ_aoa))    # 노이즈 추가

# B에서 A를 보는 AoA 도 대칭 계산 (bilateral AoA)
```

#### 고정 앵커 지원

UWB 비콘(고정 인프라)도 시뮬레이션 가능. 앵커는 heading이 없으므로 AoA = NaN.

```python
anchor_ids = ['anchor_nw', 'anchor_ne']
anchor_x   = [-4.0, 4.0]
anchor_y   = [9.0,  9.0]
```

#### 실물 전환 경로

```
시뮬: TF + anchor parameters → sim_peer_sensing_node
실물: DWM3001C UWB 드라이버 → /fleet/peer_poses, /fleet/peer_ranges (동일 토픽)
```

**설계 의도**: 시뮬과 실물이 동일 토픽을 사용하여 uwb_localizer_node를 교체 없이 재사용.

### 4.7 UWB 협력 측위 (uwb_localizer_node.py)

**파일**: `src/aip_fleet_coordinator/aip_fleet_coordinator/uwb_localizer_node.py`

`/fleet/peer_poses` + `/fleet/peer_ranges`를 수신하여 가중 Gauss-Newton 반복으로 위치 추정.

- **Shadow mode**: `child_frame_suffix='_uwb_est'` → `map → peer_N/base_link_uwb_est` TF 발행
- AMCL과 TF 충돌 없이 동시 실행 가능 → RViz에서 AMCL vs UWB 비교 가능
- `publish_hz = 20 Hz`

### 4.8 twist_mux 우선순위 체계

**파일**: `src/aip_fleet_bringup/config/twist_mux_vehicle.yaml`

```
우선순위 (높을수록 먼저 적용):
  HW-EStop      (100) — 하드웨어 비상정지 (실물 전용)
  estop_lock    ( 90) — supervisor ESTOP 래치 (실물 전용; 시뮬에서는 비활성)
  central       ( 80) — 운용자 override_cmd_vel (수동 원격 조작)
  fleet_coord   ( 50) — coordinator_node → coord_cmd_vel (V-포메이션 추종)
  autonomy      ( 10) — Nav2 → autonomy_cmd_vel (자율 항법)
```

**cmd_vel 경로 (자율 모드)**:
```
Nav2 controller_server → /<vid>/autonomy_cmd_vel
                                     ↓
                             twist_mux (priority 10)
                                     ↓
                           diff_drive_controller ← /<vid>/cmd_vel
```

**Phase-2 시뮬 주의사항**: `estop_lock`이 주석 처리됨. 발행자가 없을 경우 항상 locked 상태가 되어 전체 정지. 실하드웨어 통합 시 supervisor_node와 함께 활성화 필요.

---

## 5. 브링업 타임라인 (fleet_autonomous.launch.py)

자율 순찰 모드의 전체 시작 순서:

```
t=  0 s  Ignition Fortress 시작 + 3대 차량 스폰 (V 형 배치)
          peer_1: (0.0, 0.0)   peer_2: (-1.5, +1.0)   peer_3: (-1.5, -1.0)

t=  6 s  각 차량의 ros2_control 스포너 시작 (EKF 이전)
t=  7 s  odom_frame_fixer, cmd_relay, odom_relay 시작
t=  8 s  EKF 시작 (바퀴 + IMU 융합)

t= 14 s  twist_mux × 3 시작

t= 16 s  slam_toolbox (peer_1) + sim_peer_sensing_node 시작
         → peer_1이 /map 토픽 생성 시작

t= 18 s  peer_obstacle_node 시작 (--with_peer_obstacles:=true 시)

t= 22 s  peer_1 Nav2 스택 (AMCL 없음, leader_nav.launch.py)
         + peer_1 patrol_node (탐색 경로, loop=False)
         → 전 구역 탐색 시작 (약 120초 소요)

t= 70 s  coverage_tracker_node 시작 (--with_coverage:=true 시)

t=155 s  peer_2 자율 Nav2 풀스택 (AMCL + SmacHybrid + BT + DWB)
         + peer_2 patrol_node (loop=True, start_delay=40s)
         → peer_2 실제 이동: t=195s

t=163 s  peer_3 자율 Nav2 풀스택
         + peer_3 patrol_node (loop=True, start_delay=40s)
         → peer_3 실제 이동: t=203s
```

**peer_2/3 시작 지연(155s/163s)의 이유**:
- peer_1 탐색 경로 완주 필요 (~120s): doorway 북쪽 열원 구역까지 지도 완성
- AMCL은 지도가 있는 구역에서만 수렴 가능
- 8초 스태거: 병렬 파티클 초기화 부하 충돌 방지

---

## 6. 순찰 경로 설계

### peer_1 탐색 경로 (1회 실행, 지도 구축 목적)

```
(3.5,  0.0) → (3.5, -3.5) → (-3.5, -3.5) → (-3.5, 0.0)  # 남부 동서 sweep
→ (0.0, 2.0) → (2.5, 3.5) → (2.5, 5.5)   # doorway 접근 및 통과
→ (4.0, 6.0) → (2.0, 8.0) → (-2.0, 7.5) → (-4.0, 5.5)  # 북부 열원 구역
→ (2.5, 4.5) → (0.0, 0.0)  # 복귀
```

### peer_2 순찰 경로 (루프 반복, 동/북쪽 담당)

```
(2.0, 1.5) → (2.5, 3.5) → (2.5, 4.7)  # doorway 통과
→ (4.0, 5.5) → (2.0, 8.5) → (-2.5, 8.0) → (-4.0, 5.5)  # 열원 구역
→ (2.5, 4.7) → (2.5, 3.5) → (2.0, 1.5)  # 복귀
```

### peer_3 순찰 경로 (루프 반복, 남/서쪽 담당)

```
(0.0, -0.5) → (-3.5, -0.5) → (-3.5, -5.0) → (3.0, -5.0) → (3.0, -0.5) → (0.0, -2.5)
```

---

## 7. 다중 로봇 충돌 방지

### 7.1 peer_obstacle_node.py

- 각 차량의 TF 위치를 읽어 다른 차량의 위치를 `PointCloud2` 형태로 발행
- Nav2 로컬 코스트맵의 `peer_obstacles` 소스로 등록
- 동료 차량 위치를 가상 장애물로 마킹 (반경 0.30m의 링 포인트 12개)
- `clearing=False`: 동료가 이동했을 때 소거는 rolling window에 위임

### 7.2 한계

- 실시간 TF 기반이므로 TF 지연 시 충돌 방지 효과 저하
- 큰 회피 반경(0.30m)으로 좁은 통로에서 경로 계획 실패 가능성

---

## 8. 앞으로의 진행 과정 및 예상 결과

### 8.1 단기 (Phase-2 완성)

| 과제 | 내용 | 예상 결과 |
|---|---|---|
| Stage-5 검증 | 탐색→순찰 전체 시퀀스 시뮬 완주 | peer_2/3 doorway 통과 확인 |
| UWB 정확도 검증 | AMCL vs UWB 오차 비교 (`with_uwb:=true`) | 기대: AMCL < 0.2m RMS |
| 커버리지 추적 | `with_coverage:=true` + `/fleet/coverage_pct` 확인 | 전 구역 커버리지 % |
| 열화상 연동 | `PerceptionAlert` 메시지 발행 테스트 | 열원 위치 → RViz 시각화 |

### 8.2 중기 (Phase-3: 실하드웨어 통합)

| 과제 | 내용 |
|---|---|
| 메인 AGV 통합 | `my_ros_env:/root/colcon_ws` (타팀 관할) |
| ESP32-S3 Scout | micro-ROS Agent (UDP4:8888) 통신 |
| UWB 실물 | DWM3001C 드라이버 연결, 동일 토픽 사용 |
| 열화상 실물 | MLX90640 → ESP32 → micro-ROS → `/peer_N/thermal` |
| 실외/실내 전환 | `use_sim_time: false` 전환 |

### 8.3 장기

- **자율 탐색**: SLAM + Frontier Exploration (미지 구역 자동 탐색)
- **동적 임무 배분**: 열원 감지 시 해당 구역으로 차량 동적 재배치
- **실물 플릿 운용**: Wi-Fi AP 기반 5대 이상 차량 동시 운용

---

## 9. 피드백 요청 사항

### F-01 단일 SLAM 리더 아키텍처의 확장성

**현황**: `peer_1`만 SLAM, `peer_2/3`는 AMCL 의존.  
**문제**: peer_1 고장 시 전체 위치 추정 불가.  
**질문**: `multirobot_map_merge` 또는 `slam_toolbox`의 lifelong map 공유가 실용적인가?

### F-02 peer_1 탐색 완료 대기 (155초)

**현황**: peer_2/3는 peer_1 탐색 완료 후 155초에 시작.  
**문제**: 하드코딩된 타이밍 — 환경 크기에 따라 부족/과도할 수 있음.  
**개선 방향**: `/map` 커버리지 메트릭 기반 조건부 시작? slam_toolbox 완료 이벤트 구독?

### F-03 DWB vs TEB vs MPPI 선택

**현황**: DWB (Dynamic Window Approach) 사용.  
**문제**: 좁은 통로(doorway 0.70m)에서 DWB의 동적 윈도우 샘플링이 최적 경로를 찾지 못할 수 있음.  
**질문**: Nav2 Humble에서 TEB(Timed Elastic Band)나 MPPI가 좁은 통로 통과성에서 유리한가?

### F-04 AMCL 수렴 시간 (40초 start_delay)

**현황**: patrol_node가 AMCL 수렴을 40초 고정 대기.  
**문제**: 파티클 발산 시 차량이 잘못된 위치에서 이동 시작.  
**개선 방향**: AMCL covariance 임계값 기반 수렴 감지 후 순찰 시작?

### F-05 EKF IMU 보정 부재

**현황**: IMU gyro만 사용, absolute orientation 미사용.  
**문제**: 장시간 운용 시 yaw drift 누적.  
**질문**: 시뮬에서 drift 심화 전에 AMCL이 충분히 교정하는가? 실물에서는?

### F-06 peer_obstacle_node와 Nav2 코스트맵 통합 효과

**현황**: 동료 차량 위치를 PointCloud2로 로컬 코스트맵에 주입.  
**문제**: 동료가 빠르게 이동하면 마킹이 공간에 남아 경로 방해 가능.  
**질문**: 더 나은 다중 로봇 충돌 방지 방법론이 있는가? (e.g., 분산 RVO)

### F-07 실물 UWB와 AMCL 융합 전략

**현황**: Shadow mode로 비교만 수행, 실제 융합 미구현.  
**개선 방향**: UWB 측위를 AMCL initial pose로 주입? EKF에 제3 센서로 추가?  
**질문**: 실내 UWB(σ≈5cm)가 LiDAR AMCL보다 정확한 조건은?

### F-08 twist_mux estop_lock 운용 안전성

**현황**: 시뮬에서 `estop_lock` 비활성화.  
**문제**: 실물 통합 시 supervisor_node 없이 활성화하면 항상 잠김.  
**개선 방향**: estop_lock 발행 없을 때 기본 열림(unlocked) 처리 방식?

### F-09 Hybrid-A* 성능 (doorway 통과)

**현황**: SmacPlannerHybrid + `minimum_turning_radius=0.145m`.  
**문제**: doorway 폭 0.70m, 차체 폭 0.23m → 여유 0.47m지만 인플레이션(0.30m) 포함 시 실제 여유 0.17m.  
**질문**: 인플레이션 반경과 doorway 크기의 최소 허용 비율은 경험적으로 얼마인가?

### F-10 Coverage Tracker 실효성

**현황**: 격자 기반 방문 여부로 커버리지 계산 (`visit_radius_m=0.30m`).  
**문제**: 단순 위치 방문 기록 — 실제 감지 범위(LiDAR 7.5m) 미반영.  
**개선 방향**: LiDAR 스캔 FOV 기반 커버리지 계산이 더 정확하지 않을까?

---

## 부록: 주요 ROS 토픽 맵

```
/map                              ← slam_toolbox (peer_1)
/fleet/peer_poses                 ← sim_peer_sensing_node
/fleet/peer_ranges                ← sim_peer_sensing_node
/fleet/coverage_pct               ← coverage_tracker_node
/fleet/coverage_grid              ← coverage_tracker_node

/<vid>/scan                       ← ros_gz_bridge (LiDAR)
/<vid>/imu                        ← ros_gz_bridge (IMU)
/<vid>/odom                       ← odom_relay
/<vid>/odometry/filtered          ← ekf_node
/<vid>/diff_drive_controller/odom_corrected ← odom_frame_fixer
/<vid>/cmd_vel                    ← twist_mux output → diff_drive_controller
/<vid>/autonomy_cmd_vel           ← Nav2 controller_server (priority 10)
/<vid>/coord_cmd_vel              ← coordinator_node (priority 50)
/<vid>/override_cmd_vel           ← 운용자 수동 입력 (priority 80)
/<vid>/peer_obstacles             ← peer_obstacle_node
/<vid>/navigate_to_pose           ← BT Navigator action server

TF tree:
  map → <vid>/odom → <vid>/base_link → <vid>/base_footprint
       ↑ slam_toolbox(peer_1) / AMCL(peer_2,3)
                   ↑ ekf_node
```

---

*이 문서는 AIP 군집 로봇 프로젝트의 현재 상태를 기반으로 작성되었으며, 피드백 및 설계 리뷰를 위한 용도입니다.*
