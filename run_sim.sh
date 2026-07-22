#!/bin/bash
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export LIBGL_ALWAYS_SOFTWARE=1
# ⚠ FASTRTPS profile(UDP-only) 미사용 — robot_description 등 큰 latched 메시지
#   전달 방해 가능성. 기본 transport(SHM+UDP) 사용. SHM 경고는 무해(UDP 폴백).

# ── 이전 시뮬 잔재(orphan) 완전 정리 ─────────────────────────────────────────
# ign gazebo ruby 래퍼가 죽어도 fork 된 gz 서버가 orphan 으로 남아 CPU 점유 +
# 다음 실행과 충돌(빈 창/스폰 실패). 시작 전 강제 정리.
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
ros2 daemon stop 2>/dev/null   # 꼬인 ros2 daemon 정리
sleep 1

# gui:=false       → headless + --headless-rendering (WSL2 검증 모드, GPU 라이다 동작)
# skip_explore:=true → ★필수★ explore_lite 패키지 미설치 회피.
#   explore_lite 가 없어 skip_explore=false 면 launch 가 "package 'explore_lite'
#   not found" 예외로 전체 자동 종료된다(t≈60s). true 로 두면 explore 없이
#   with_patrol 로 peer_1 이 순찰하며 slam_toolbox 가 맵을 생성한다.
#   (explore 모드를 쓰려면: sudo apt install ros-humble-explore-lite)
# rtf:=0.5         → ★중요★ rtf=1.0 은 CPU 를 과점유해 gz_ros2_control 이
#   robot_description(get_parameters 서비스) 응답을 못 받아 controller_manager
#   가 안 뜨고 → diff_drive/JSB spawner 가 180s timeout 으로 실패(peer_1 정지).
#   0.5(6/15 검증값)는 CPU 여유를 확보해 controller_manager 초기화를 보장한다.
exec ros2 launch aip_fleet_autonomous fleet_autonomous.launch.py \
  gui:=false \
  skip_explore:=true \
  with_patrol:=true \
  rtf:=0.5
