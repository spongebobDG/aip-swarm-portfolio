#!/usr/bin/env bash
# deploy_main_agv.sh — aip_swarm_ws 메인 AGV 파이프라인을 RPi4B 에 배포하고 동작 확인.
#
# 사용:
#   bash scripts/deploy_main_agv.sh [RPI_HOST]
#   # 예: bash scripts/deploy_main_agv.sh jh@192.168.0.3
#
# 전제:
#   - dev PC 에서 RPi 에 SSH 키 인증 완료 (비밀번호 없이 접속 가능)
#   - RPi 에 ROS2 Humble + 필수 패키지 설치 완료 (docs/SETUP_RPI4.md §1~§5)
#   - dev PC 에서 이 스크립트를 ~/aip_swarm_ws 루트에서 실행
#
# 수행 순서:
#   1. RPi 에 aip_swarm_ws 클론 (없으면) 또는 pull + submodule sync
#   2. RPi 에서 실차 패키지 빌드 (시뮬 패키지 제외)
#   3. 배포 완료 확인 메시지 출력 + 기동 명령 안내

set -euo pipefail

RPI_HOST="${1:-jh@192.168.0.3}"
RPI_WS="~/aip_swarm_ws"
REPO_URL="https://github.com/Mark2AC/aip-swarm-ws.git"
BRANCH="${2:-main}"

log() { echo -e "\033[1;34m[deploy]\033[0m $*"; }
ok()  { echo -e "\033[1;32m[  OK  ]\033[0m $*"; }
err() { echo -e "\033[1;31m[ ERR  ]\033[0m $*" >&2; exit 1; }

# ── 0. SSH 연결 확인 ─────────────────────────────────────────────────────
log "RPi SSH 연결 확인: $RPI_HOST"
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$RPI_HOST" "echo ok" &>/dev/null; then
  err "SSH 실패. RPi 전원/네트워크 확인 후 재시도: ssh $RPI_HOST"
fi
ok "SSH 연결 성공"

# ── 1. 워크스페이스 클론 또는 업데이트 ─────────────────────────────────
log "RPi 워크스페이스 동기화 중..."
ssh "$RPI_HOST" bash <<REMOTE
set -e
if [ ! -d "$RPI_WS/.git" ]; then
  echo "[RPi] 워크스페이스 신규 클론..."
  git clone "$REPO_URL" "$RPI_WS"
  cd "$RPI_WS"
  git checkout "$BRANCH"
  git submodule update --init --recursive
else
  echo "[RPi] 기존 워크스페이스 업데이트..."
  cd "$RPI_WS"
  git fetch origin
  git checkout "$BRANCH" 2>/dev/null || true
  git pull --rebase origin "$BRANCH"
  git submodule update --init --recursive
fi
REMOTE
ok "워크스페이스 동기화 완료"

# ── 2. rosdep 의존성 설치 (첫 배포 또는 package.xml 변경 시) ────────────
log "RPi rosdep 의존성 확인..."
ssh "$RPI_HOST" bash <<REMOTE
set -e
source /opt/ros/humble/setup.bash
cd "$RPI_WS"
sudo rosdep init 2>/dev/null || true
rosdep update --quiet
rosdep install --from-paths src --ignore-src -r -y \
  --skip-keys "gazebo_ros ignition-gazebo ros_gz_sim turtlebot3_gazebo" \
  2>&1 | grep -v "^#" | grep -v "^$" | tail -5
REMOTE
ok "의존성 확인 완료"

# ── 3. 빌드 (시뮬 패키지 제외) ──────────────────────────────────────────
log "RPi colcon 빌드 시작... (OOM 방지: parallel-workers=1)"
ssh "$RPI_HOST" bash <<REMOTE
set -e
source /opt/ros/humble/setup.bash
cd "$RPI_WS"
colcon build --symlink-install \
  --parallel-workers 1 --executor sequential \
  --packages-skip aip_fleet_gazebo aip_fleet_sim aip_fleet_foxglove_panels \
  --cmake-args -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -15
REMOTE
ok "빌드 완료"

# ── 4. 배포 확인 ──────────────────────────────────────────────────────────
log "배포 확인 중..."
ssh "$RPI_HOST" bash <<REMOTE
source /opt/ros/humble/setup.bash
source "$RPI_WS/install/setup.bash"
echo "[패키지 확인]"
ros2 pkg list | grep -E "aip_fleet_real|aip_fleet_autonomous" || true
echo "[launch 파일 확인]"
find "$RPI_WS/install/aip_fleet_real" -name "main_agv.launch.py" 2>/dev/null || true
REMOTE

# ── 5. 기동 안내 ─────────────────────────────────────────────────────────
cat << 'EOF'

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  배포 완료. 아래 순서로 실행하세요:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [RPi — aip1] 하드웨어 bringup (YDLidar + serial_bridge + TF)
    bash ~/aip_swarm_ws/scripts/rpi_bringup.sh aip1

  [dev PC] 중앙 스택 기동 (Docker)
    cd ~/aip_swarm_ws/docker/central && docker compose up -d
    ros2 launch aip_fleet_bringup central.launch.py   # foxglove_bridge + SLAM + Nav2

  [dev PC] 정상 기동 확인
    ros2 topic hz /aip1/scan              # ~10 Hz (YDLidar TG15)
    ros2 topic hz /aip1/odom             # ~20 Hz (serial_bridge)
    ros2 topic list | grep /aip1/        # Nav2 + SLAM 토픽 확인
    ros2 run tf2_tools view_frames       # map→odom→base_footprint→laser_link TF

  [SLAM 맵 충분히 생성 후] Nav2 목표 테스트
    ros2 action send_goal /aip1/navigate_to_pose nav2_msgs/action/NavigateToPose \
      '{"pose":{"header":{"frame_id":"map"},"pose":{"position":{"x":1.0,"y":0.0}}}}'

  [patrol.yaml 좌표 확정 후] 순찰 시작
    bash ~/aip_swarm_ws/scripts/rpi_bringup.sh aip1 --patrol

  [맵 저장]
    ros2 service call /slam_toolbox/save_map slam_toolbox/srv/SaveMap \
      "{name: {data: '/home/$(whoami)/maps/aip1_map'}}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
