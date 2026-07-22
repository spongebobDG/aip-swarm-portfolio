#!/bin/bash
# 단일 차량(peer_1) 전용 시뮬 — WSL2 CPU 병목 회피용.
# solo_mapping:=true → peer_2/3 스폰 안 함(follower_trigger 비활성).
# peer_1 의 SLAM + Nav2(leader_nav)는 그대로 떠서, 웹에서 수동 이동 명령으로
# 조종을 확실히 검증할 수 있다. 검증 후 run_sim.sh(3대)로 확장한다.
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export LIBGL_ALWAYS_SOFTWARE=1

# ── 이전 시뮬 잔재(orphan) 완전 정리 ──
pkill -9 -f "ign gazebo"             2>/dev/null
pkill -9 -f "gz sim"                 2>/dev/null
pkill -9 -f "ruby /usr/bin/ign"      2>/dev/null
pkill -9 -f "ros_gz"                 2>/dev/null
pkill -9 -f "parameter_bridge"       2>/dev/null
pkill -9 -f "robot_state_publisher"  2>/dev/null
pkill -9 -f "slam_toolbox"           2>/dev/null
pkill -9 -f "fleet_autonomous"       2>/dev/null
rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_* /tmp/fastrtps_* 2>/dev/null
sleep 2

source /opt/ros/humble/setup.bash
COLCON_WS="${COLCON_WS:-$(cd "$(dirname "$0")" && pwd)}"
source "$COLCON_WS/install/setup.bash"
ros2 daemon stop 2>/dev/null
sleep 1

exec ros2 launch aip_fleet_autonomous fleet_autonomous.launch.py \
  gui:=false \
  solo_mapping:=true \
  skip_explore:=true \
  with_patrol:=true \
  rtf:=0.5
