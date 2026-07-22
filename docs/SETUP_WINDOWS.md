# Windows 개발환경 설정 (시뮬 E2E)

Windows 11 + Docker Desktop만으로 AIP 스웜 시뮬 스택을 전부 돌리는 절차.
ROS2 네이티브 설치 불필요. 모든 ROS2 노드·Foxglove Bridge는 컨테이너 안에서 실행.

목표: 1회 빌드 후 `docker compose up` → Foxglove Studio에서 `ws://localhost:8765`
접속 → 차량 3대 + 맵 + LaserScan + `/fleet/status` 확인 → E-Stop / Override 동작 검증.

---

## 0. 전제

- Windows 11 Pro
- Docker Desktop (WSL2 backend) 설치·실행 중 — `docker version` 으로 확인
- 작업 경로: `C:\Users\user\aip_swarm_ws`

Docker Desktop 미설치 시: <https://www.docker.com/products/docker-desktop/>.
설치 후 반드시 **Settings → Resources → WSL Integration** 토글 확인.

---

## 1. Foxglove Studio 설치

택1:

- **데스크톱 앱** (권장, Windows 네이티브): <https://foxglove.dev/download> → Windows x64 인스톨러
- **웹**: <https://app.foxglove.dev> — 브라우저만으로 접속 가능 (로그인 계정 필요)

두 버전 모두 동일한 확장 API를 지원하므로 패널 로드 방식은 같음.

---

## 2. 시뮬 스택 빌드·기동

PowerShell 또는 Git Bash 에서:

```powershell
cd C:\Users\user\aip_swarm_ws
docker compose -f docker/sim/docker-compose.yml up --build
```

첫 빌드는 `ros:humble-ros-base` pull + `colcon build` 로 5–10 분 소요.
이후 `--build` 없이 `up` 만 하면 바로 뜸.

정상 기동 로그 예시 (축약):

```
[INFO] [sim_world_node]: Loaded world: 20x20m, 7 obstacles
[INFO] [sim_vehicle_node-main]: Vehicle 'main' spawned at (0.00, 0.00, 0.00)
[INFO] [sim_vehicle_node-scout_1]: Vehicle 'scout_1' spawned at (1.50, -1.00, 0.00)
[INFO] [sim_vehicle_node-scout_2]: Vehicle 'scout_2' spawned at (-1.50, -1.00, 0.00)
[INFO] [aip_fleet_supervisor]: Supervisor watching vehicles: ['main', 'scout_1', 'scout_2'] (heartbeat timeout 2.0s)
[INFO] [aip_fleet_watchdog]: Watchdog armed (offline_confirm_count=3).
[INFO] [foxglove_bridge]: WebSocket server listening on 0.0.0.0:8765
```

에러 발생 시: `docker compose -f docker/sim/docker-compose.yml logs sim`

---

## 3. Foxglove 접속

1. Foxglove Studio 실행
2. **Open Connection** → **Foxglove WebSocket** → URL `ws://localhost:8765` → **Open**
3. 좌측 **Topics** 패널에 `/main/odom`, `/map`, `/fleet/status` 등이 뜨면 성공

### 레이아웃 로드

`config/foxglove_layouts/fleet_overview.json` 을 import:

- Foxglove: **Layouts** (좌측 상단) → **Import from file…** → 해당 JSON 선택

3D 뷰에 `OccupancyGrid` + 차량 3대 TF + `/main/scan` 이 보이면 완료.

---

## 4. 스모크 테스트

### 4.1 CLI 로 메인 차량 직진

컨테이너 안에서 토픽 publish. Windows PowerShell:

```powershell
docker exec -it aip_sim bash
# 컨테이너 안에서:
source /opt/ros/humble/setup.bash && source /ws/install/setup.bash
ros2 topic pub -r 10 /main/cmd_vel geometry_msgs/Twist '{linear: {x: 0.3}, angular: {z: 0.2}}'
```

Foxglove 3D 뷰에서 `main` 차량이 움직이는지 확인. `Ctrl+C` 로 중지.

### 4.2 전체 E-Stop (CLI)

```bash
ros2 topic pub -1 /fleet/override aip_fleet_msgs/OverrideCommand \
  '{vehicle_id: "*", command: 3}'
```

`/fleet/status` 의 각 `state` 가 3 (ESTOP) 로 변하는지 확인.

### 4.3 Watchdog 동작 (히스테리시스)

한 차량의 sim_vehicle_node 를 죽여 2초 이상 오프라인 만들기:

```bash
# 컨테이너 안에서 sim_vehicle_node 프로세스 찾아 kill
pgrep -a -f "sim_vehicle_node.*scout_1" | awk '{print $1}' | xargs kill
```

기대 동작: ~1.5–2.0 s 후 watchdog 로그에
`Vehicle scout_1 offline for 3 cycles — forcing ESTOP` 출현.
`/fleet/status.offline_vehicle_ids` 에 `scout_1` 포함.

---

## 5. Foxglove 커스텀 패널 (E-Stop / Override)

패널은 TypeScript 소스 상태로 들어 있음. Foxglove extension 으로 로컬 설치:

### 준비

Node.js 18+ 가 Windows 에 설치되어 있어야 함 (<https://nodejs.org>).

```powershell
cd C:\Users\user\aip_swarm_ws\src\aip_fleet_foxglove_panels
npm install
npm run local-install
```

`local-install` 스크립트는 `.foxe` 를 만들어 Foxglove 의 로컬 확장 디렉터리에 복사.
Foxglove Studio 재시작 후 **Add Panel** 목록에 `AIP E-Stop`, `AIP Override` 등장.

---

## 6. 반복 개발 루프

- **Python 노드 수정**: `src/aip_fleet_*/` 아래 `.py` 수정 → 컨테이너 재시작 불필요.
  `docker exec -it aip_sim bash` 에서 `ros2 launch` 만 재실행하거나
  `docker compose restart sim` 한 번.
- **메시지/CMake 수정** (`aip_fleet_msgs` 등): 컨테이너 안에서
  `cd /ws && colcon build --symlink-install` 재실행.
- **Dockerfile 수정**: `docker compose -f docker/sim/docker-compose.yml up --build`.
- **TS 패널 수정**: `npm run local-install` 재실행 후 Foxglove 재시작.

---

## 7. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `port 8765 already in use` | 다른 프로세스가 8765 점유 | `netstat -ano \| findstr 8765` 로 PID 찾아 종료 |
| Foxglove 가 topic 을 못 봄 | 컨테이너 안 launch 실패 | `docker compose logs sim` 확인 |
| `colcon build` 메시지 에러 | msg/srv 수정 후 cache 오염 | `docker compose down && docker compose up --build` |
| 3D 뷰 맵이 안 뜸 | `/map` 이 TRANSIENT_LOCAL 인데 Foxglove 가 late-subscribe 처리 못함 | Foxglove 재접속 또는 sim 재시작 |
| Docker Desktop 이 WSL2 에러 | kernel 미업데이트 | PowerShell 관리자: `wsl --update` |

---

## 8. 정리

```powershell
# 스택 중지
docker compose -f docker/sim/docker-compose.yml down

# 이미지까지 삭제 (재빌드 강제)
docker compose -f docker/sim/docker-compose.yml down --rmi local

# 볼륨까지 초기화 (중앙 스택의 rosbag/influx 용)
docker compose -f docker/central/docker-compose.yml down -v
```

---

## 9. 다음 단계

- Ubuntu 중앙 PC 로 넘어가려면 `docs/SETUP_UBUNTU.md` 참조
- 실제 차량 하드웨어 연동 전 체크리스트: `README.md` § "Interfaces the vehicle-SW teammate must honor"
- 보안 하드닝 로드맵: `docs/SECURITY.md` Phase 1
