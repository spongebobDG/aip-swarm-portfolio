#!/usr/bin/env bash
# rpi_bringup.sh — AIP 플릿 실차량 공용 기동 스크립트 (RPi4B 온보드에서 직접 실행)
#
# 사용:
#   bash ~/aip_swarm_ws/scripts/rpi_bringup.sh [vehicle_id] [옵션]
#
#   vehicle_id: aip1 | aip2 | aip3  (생략 시 호스트명으로 자동 감지)
#
# 옵션:
#   --patrol     순찰 미션 자동 시작 (aip1/aip2 지원)
#   --no-nav2    SLAM 전용, Nav2 없이 기동 (aip1)
#   --dry-run    실제 launch 없이 환경변수·launch 명령만 출력
#
# 예시:
#   bash ~/aip_swarm_ws/scripts/rpi_bringup.sh            # 호스트명 자동 감지
#   bash ~/aip_swarm_ws/scripts/rpi_bringup.sh aip1
#   bash ~/aip_swarm_ws/scripts/rpi_bringup.sh aip2 --patrol
#   bash ~/aip_swarm_ws/scripts/rpi_bringup.sh aip1 --dry-run

set -euo pipefail

# ── 색상 출력 ──────────────────────────────────────────────────────────────
log()  { echo -e "\033[1;34m[bringup]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[  OK  ]\033[0m $*"; }
warn() { echo -e "\033[1;33m[ WARN ]\033[0m $*"; }
err()  { echo -e "\033[1;31m[ ERR  ]\033[0m $*" >&2; exit 1; }

# ── 인수 파싱 ──────────────────────────────────────────────────────────────
VEHICLE_ID=""
WITH_PATROL=false
NO_NAV2=false
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    aip1|aip2|aip3) VEHICLE_ID="$arg" ;;
    --patrol)   WITH_PATROL=true ;;
    --no-nav2)  NO_NAV2=true ;;
    --dry-run)  DRY_RUN=true ;;
    *) err "알 수 없는 인수: $arg\n사용법: $0 [aip1|aip2|aip3] [--patrol] [--no-nav2] [--dry-run]" ;;
  esac
done

# ── 차량 ID 자동 감지 (호스트명 기반) ─────────────────────────────────────
if [ -z "$VEHICLE_ID" ]; then
  HOSTNAME=$(hostname)
  case "$HOSTNAME" in
    *aip1*) VEHICLE_ID="aip1" ;;
    *aip2*) VEHICLE_ID="aip2" ;;
    *aip3*) VEHICLE_ID="aip3" ;;
    *)
      warn "호스트명 '$HOSTNAME'으로 차량 ID 감지 실패."
      warn "직접 지정: $0 aip1|aip2|aip3"
      read -rp "차량 ID 입력 (aip1/aip2/aip3): " VEHICLE_ID
      [[ "$VEHICLE_ID" =~ ^aip[123]$ ]] || err "유효하지 않은 차량 ID: $VEHICLE_ID"
      ;;
  esac
  log "자동 감지된 차량 ID: $VEHICLE_ID"
fi

# ── 워크스페이스 경로 ──────────────────────────────────────────────────────
WS_DIR="$HOME/aip_swarm_ws"
[ -d "$WS_DIR" ] || err "워크스페이스 없음: $WS_DIR\n'git clone' 후 재실행하세요."

SETUP_BASH="$WS_DIR/install/setup.bash"
[ -f "$SETUP_BASH" ] || err "빌드 결과 없음: $SETUP_BASH\n'colcon build' 먼저 실행하세요."

# ── 기존 ROS 프로세스 정리 ────────────────────────────────────────────────
log "기존 ROS 프로세스 정리 중..."
_ROS_PROCS=(
  "ros2 launch"
  "ydlidar_ros2_driver_node"
  "static_transform_publisher"
  "twist_mux"
  "serial_bridge"
  "heartbeat_pub"
  "slam_toolbox"
  "nav2"
  "bt_navigator"
  "ros2-daemon"
)
_killed=0
for _proc in "${_ROS_PROCS[@]}"; do
  if pgrep -f "$_proc" > /dev/null 2>&1; then
    pkill -TERM -f "$_proc" 2>/dev/null || true
    _killed=$((_killed + 1))
  fi
done
if [ "$_killed" -gt 0 ]; then
  sleep 2
  # SIGKILL for stubborn processes
  for _proc in "${_ROS_PROCS[@]}"; do
    pkill -KILL -f "$_proc" 2>/dev/null || true
  done
  sleep 1
  warn "$_killed 종류의 기존 프로세스를 정리했습니다."
else
  ok "정리할 기존 프로세스 없음"
fi

# ── 공통 환경 소싱 ─────────────────────────────────────────────────────────
# ROS2 setup.bash 내부에서 미정의 변수를 참조하므로 소싱 중에만 -u 해제
log "ROS2 환경 소싱..."
set +u
# shellcheck source=/dev/null
source /opt/ros/humble/setup.bash
# shellcheck source=/dev/null
source "$SETUP_BASH"
set -u

export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

# ── 차량별 추가 환경변수 ───────────────────────────────────────────────────
case "$VEHICLE_ID" in
  aip1)
    LAUNCH_PKG="aip_fleet_real"
    LAUNCH_FILE="fleet_main.launch.py"
    LAUNCH_ARGS=""
    ;;
  aip2)
    export TURTLEBOT3_MODEL=burger
    LAUNCH_PKG="aip_fleet_real"
    LAUNCH_FILE="turtlebot3.launch.py"
    LAUNCH_ARGS="namespace:=aip2"
    if $WITH_PATROL; then
      LAUNCH_ARGS="$LAUNCH_ARGS with_patrol:=true"
    fi
    ;;
  aip3)
    LAUNCH_PKG="aip_fleet_real"
    LAUNCH_FILE="custom_vehicle.launch.py"
    LAUNCH_ARGS="namespace:=aip3"
    ;;
esac

# aip1 patrol / no-nav2 옵션
if [ "$VEHICLE_ID" = "aip1" ]; then
  # fleet_main.launch.py 는 HW 드라이버 전용 — Nav2/SLAM/patrol 은 dev PC에서 실행
  # (main_agv.launch.py 는 dev PC 전용)
  if $WITH_PATROL || $NO_NAV2; then
    warn "aip1 RPi는 HW 드라이버만 기동합니다."
    warn "SLAM+Nav2+patrol은 dev PC에서 main_agv.launch.py로 실행하세요."
  fi
fi

# ── 실행 정보 출력 ─────────────────────────────────────────────────────────
echo ""
echo "┌─────────────────────────────────────────────┐"
echo "│  AIP Fleet — RPi Bringup                    │"
echo "├─────────────────────────────────────────────┤"
printf "│  차량 ID       : %-27s│\n" "$VEHICLE_ID"
printf "│  ROS_DOMAIN_ID : %-27s│\n" "$ROS_DOMAIN_ID"
printf "│  RMW           : %-27s│\n" "$RMW_IMPLEMENTATION"
printf "│  패키지        : %-27s│\n" "$LAUNCH_PKG"
printf "│  launch 파일   : %-27s│\n" "$LAUNCH_FILE"
if [ -n "$LAUNCH_ARGS" ]; then
  printf "│  인수          : %-27s│\n" "$LAUNCH_ARGS"
fi
echo "└─────────────────────────────────────────────┘"
echo ""

if $DRY_RUN; then
  ok "dry-run 완료. 실제 launch 명령:"
  echo "  ros2 launch $LAUNCH_PKG $LAUNCH_FILE $LAUNCH_ARGS"
  exit 0
fi

# ── launch 실행 ────────────────────────────────────────────────────────────
log "$VEHICLE_ID 기동 중..."
# shellcheck disable=SC2086
exec ros2 launch "$LAUNCH_PKG" "$LAUNCH_FILE" $LAUNCH_ARGS
