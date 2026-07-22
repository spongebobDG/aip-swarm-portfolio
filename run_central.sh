#!/bin/bash
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
# 실차 환경: scout_1/scout_2 컨테이너가 DS CLIENT(192.168.0.106:11811)로 설정돼 있으므로
# DS SERVER 모드가 기본이다. Simple Discovery로 바꾸려면 AIP_DISCOVERY_MODE=simple 지정.
if [[ "${AIP_DISCOVERY_MODE:-server}" == "server" ]]; then
  export ROS_DISCOVERY_SERVER="${ROS_DISCOVERY_SERVER:-192.168.0.106:11811}"
else
  unset ROS_DISCOVERY_SERVER
fi
export LIBGL_ALWAYS_SOFTWARE=1
unset FASTRTPS_DEFAULT_PROFILES_FILE
unset FASTDDS_BUILTIN_TRANSPORTS
# ⚠ FASTRTPS_DEFAULT_PROFILES_FILE(UDP-only)는 사용하지 않는다.
#   robot_description 등 큰 latched 메시지 전달 방해 가능성. 기본 transport 사용.

# 이전 대시보드 서버가 8080 을 점유한 채 남아있으면 새 서버가 즉시 죽는다
# (Errno 98: address already in use) → 시작 전에 반드시 정리.
pkill -9 -f dashboard_server 2>/dev/null || true
fuser -k 8080/tcp 2>/dev/null || true
sleep 1

COLCON_WS="${COLCON_WS:-$(cd "$(dirname "$0")" && pwd)}"

source /opt/ros/humble/setup.bash
source "$COLCON_WS/install/setup.bash"

exec ros2 launch aip_fleet_bringup central_real_single_process.launch.py
