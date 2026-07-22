#!/bin/bash
# solo 모드(run_sim_solo.sh)에서 peer_1 순찰을 직접 기동한다.
# follower_trigger 가 비활성이므로 patrol_node 를 단독 실행 — leader_nav 의
# /peer_1/navigate_to_pose 액션으로 waypoint 를 순회한다.
#
# 시뮬(run_sim_solo.sh)이 떠 있고 peer_1 Nav2 가 active 인 상태에서 실행.
# waypoints: 맵 중앙의 안전한 사각형(pillar 안쪽 자유공간). [x,y,yaw_deg, ...]
# 막히면 웹 맵에서 자유공간을 보고 좌표를 조정하라.
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
source /opt/ros/humble/setup.bash
COLCON_WS="${COLCON_WS:-$(cd "$(dirname "$0")" && pwd)}"
source "$COLCON_WS/install/setup.bash"

exec ros2 run aip_fleet_autonomous patrol_node --ros-args \
  -p vehicle_id:=peer_1 \
  -p waypoints:="[0.0,1.5,90.0, 1.5,1.5,0.0, 1.5,-1.5,-90.0, -1.5,-1.5,180.0, -1.5,1.5,90.0]" \
  -p loop_patrol:=true \
  -p start_delay_sec:=5.0
