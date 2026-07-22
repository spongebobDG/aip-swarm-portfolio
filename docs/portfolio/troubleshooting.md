# Troubleshooting

> 목적: 실행 중 자주 만날 수 있는 문제와 확인 순서를 정리한다.  
> 기준: 실제 코드와 문서에서 확인된 실행 경로를 중심으로 작성하며, 불확실한 항목은 `확인 필요`로 표시한다.

## 1. 빠른 상태 확인

```bash
# Docker sim 상태
docker ps
docker logs aip_sim

# 웹관제 HTTP 확인
curl http://localhost:18080

# ROS2 topic 확인
ros2 topic list
ros2 topic echo /fleet/status --once
```

Windows PowerShell에서 `docker` 또는 `git`이 안 잡히는 경우 WSL에서 실행해야 할 수 있다.

```bash
wsl.exe --cd /mnt/c/project/aip-swarm-ws docker ps
```

## 2. ROS2 Topic이 안 보일 때

### 증상

- `ros2 topic list`에 `/fleet/status` 또는 `/<vid>/heartbeat`가 보이지 않는다.
- 웹관제에서 차량이 offline으로 표시된다.
- `/fleet/status`가 비어 있다.

### 확인 순서

1. ROS2 환경이 source 되었는지 확인

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
```

2. Domain ID 확인

```bash
echo $ROS_DOMAIN_ID
```

기본 기준은 `42`다.

3. heartbeat topic 확인

```bash
ros2 topic list | grep heartbeat
ros2 topic echo /aip1/heartbeat --once
ros2 topic echo /aip2/heartbeat --once
ros2 topic echo /aip3/heartbeat --once
```

4. `/fleet/status` 확인

```bash
ros2 topic echo /fleet/status --once
```

5. Message Type 계약 확인

```bash
ros2 interface show aip_fleet_msgs/msg/FleetHeartbeat
```

### 가능한 원인

| 원인 | 설명 | 조치 |
|---|---|---|
| ROS_DOMAIN_ID 불일치 | 차량과 중앙 PC가 다른 domain이면 discovery되지 않음 | `ROS_DOMAIN_ID=42` 확인 |
| DDS discovery 문제 | FastDDS/Discovery Server/SIMPLE 설정 불일치 | 최신 `docs/HANDOFF.md`와 network memory 확인 |
| Message Type 불일치 | `FleetHeartbeat.msg` 필드가 서로 다르면 DDS endpoint가 매칭되지 않음 | 차량/중앙 빌드의 msg 계약 확인 |
| 네임스페이스 불일치 | 구형 `main/scout_*`와 최신 `aip1/aip2/aip3` 혼재 | 최신 기준으로 topic 확인 |

## 3. 웹관제 화면이 데이터 수신을 못 할 때

### 증상

- `http://localhost:18080`은 열리지만 차량 카드가 갱신되지 않는다.
- `MAP READY`가 뜨지 않는다.
- 비전/열화상 화면이 비어 있다.

### 확인 순서

1. 웹관제 서버 실행 확인

```bash
curl http://localhost:18080
```

2. WebSocket 서버 로그 확인

```bash
docker logs aip_sim
```

또는 중앙 PC 실행 시 해당 systemd/docker 로그를 확인한다.

3. 대시보드가 구독하는 주요 topic 확인

```bash
ros2 topic echo /fleet/status --once
ros2 topic echo /fleet/map_ready --once
ros2 topic echo /fleet/peer_poses --once
ros2 topic echo /fleet/alerts --once
```

4. 맵 topic 확인

```bash
ros2 topic list | grep map
ros2 topic echo /map --once
ros2 topic echo /map_static --once
```

### 가능한 원인

| 원인 | 확인 방법 |
|---|---|
| `/fleet/status` 미수신 | supervisor/heartbeat 확인 |
| `/map` 또는 `/map_static` 미발행 | map publisher 또는 sim_world_node 확인 |
| `/fleet/map_ready` 미발행 | map_readiness_node 또는 sim_world_node 확인 |
| WebSocket 연결 실패 | 브라우저 개발자 도구 또는 서버 로그 확인 |
| 18080 포트 충돌 | `netstat` 또는 Docker container 상태 확인 |

## 4. 카메라가 안 잡힐 때

### 증상

- 비전 화면이 `NO SIGNAL` 또는 빈 화면이다.
- `/fleet/perception_viz/<vid>`가 발행되지 않는다.
- Vision Pi bridge가 HTTP fetch 실패를 출력한다.

### 확인 순서

1. ROS2 image topic 확인

```bash
ros2 topic list | grep image
ros2 topic list | grep thermal
```

2. Vision Pi HTTP endpoint 확인

```bash
curl http://<vision-pi-ip>:8081/status.json
curl -I http://<vision-pi-ip>:8081/rgb.jpg
curl -I http://<vision-pi-ip>:8081/thermal.jpg
```

3. bridge launch 확인

```bash
ros2 launch aip_fleet_perception vision_pi_bridge.launch.py vehicle_id:=aip2 base_url:=http://<vision-pi-ip>:8081
```

4. RGB/thermal ROS2 발행 확인

```bash
ros2 topic echo /aip2/image_raw/compressed --once
ros2 topic echo /aip2/thermal_viz --once
```

### 가능한 원인

| 원인 | 조치 |
|---|---|
| Vision Pi IP 변경 | 공유기 DHCP 또는 고정 IP 확인 |
| HTTP endpoint 경로 불일치 | `/rgb.jpg`, `/thermal.jpg`, `/status.json` 확인 |
| camera/thermal service 미실행 | Vision Pi systemd service 확인 |
| `central_fusion_node` 모델/의존성 문제 | `ultralytics`, OpenCV 설치 및 로그 확인 |
| 캘리브레이션 미완료 | camera_info yaml, homography 설정 확인 필요 |

## 5. 빌드 에러 발생 시

### 확인 순서

1. ROS2 기본 환경 source

```bash
source /opt/ros/humble/setup.bash
```

2. rosdep 설치

```bash
rosdep install --from-paths src --ignore-src -r -y
```

3. 특정 패키지만 빌드

```bash
colcon build --symlink-install --packages-select aip_fleet_msgs
colcon build --symlink-install --packages-select aip_fleet_dashboard
```

4. 전체 빌드가 실패하면 의존성 큰 패키지 분리

```bash
colcon build --symlink-install --packages-up-to aip_fleet_dashboard
```

### 알려진 주의점

| 항목 | 설명 |
|---|---|
| `sim_vehicle_node.py` | `return`, `warning` 오타 수정 여부 확인 |
| `docker/sim/Dockerfile` | `python3-uvicorn` 의존성 이름 확인 |
| `m-explore-ros2` | `image_geometry` 등 추가 의존성 필요 가능 |
| Foxglove panels | Node/npm 환경 필요 |
| Windows/WSL line ending | CRLF/LF 차이로 git diff가 커질 수 있음 |

## 6. E-Stop / 제어가 이상할 때

### 확인 Topic

```bash
ros2 topic echo /fleet/override --once
ros2 topic echo /aip1/estop --once
ros2 topic echo /aip1/override_cmd_vel --once
ros2 topic echo /aip1/cmd_vel --once
```

### 확인할 것

- `dashboard_server`가 `/<vid>/estop`과 `/fleet/override`를 발행하는지
- `supervisor_node`가 E-Stop 상태를 재발행하는지
- `twist_mux` 설정에서 lock 우선순위가 의도대로 동작하는지
- Nav2가 E-Stop 후 곧바로 다시 `autonomy_cmd_vel`을 내보내는지

## 7. 문서와 실제 동작이 다를 때

이 저장소는 개발 과정이 길고 문서가 많아 구형 정보가 남아 있다.

우선순위:

1. 실제 코드와 launch 파일
2. `README.md`
3. `docs/ARCHITECTURE.md`
4. `docs/HANDOFF.md`
5. `docs/agent_context/conversation_log.md`

정리 필요:

- 구형 `main/scout_1/scout_2` 표현
- 최신 `aip1/aip2/aip3` 기준
- `aip3` placeholder 문서와 수동 구동 확인 기록 간 불일치
- FleetHeartbeat 구형/신형 계약 이력
