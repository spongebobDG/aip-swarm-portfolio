#!/bin/bash
# ros_preclean.sh — 차량 스택 (재)기동 직전 "동일 노드 중복/orphan" 정리.
#
# 왜 (DS 다차량 baseline):
#   수동 `ros2 launch` 잔재·비정상 종료로 같은 노드가 두 벌 돌면 —
#     • /dev(라이다 ydlidar, ESP32 serial_bridge) 점유 충돌 → 드라이버 기동 실패
#     • 동일 TF(map→odom 등) 이중 발행 → TF_OLD_DATA 오염, 위치 점프
#     • map/costmap 이중 발행 → wifi 대역폭 낭비 + DDS discovery 혼선
#   → DS로 여러 대를 동시에 돌릴 때 중복 노드 방지는 기본 위생.
#
# 가정: 단일 차량 호스트(이 호스트의 ROS 노드는 모두 이 차량 소속).
# 사용:
#   systemd:   [Service] ExecStartPre=-/path/ros_preclean.sh
#   container: entrypoint 선두에서 `bash ros_preclean.sh` 호출
# ExecStartPre 는 ExecStart 보다 먼저 1회 실행되므로, 새로 뜰 스택은 안 건드리고
# "이전에 남아있던" 동일 노드/런치 잔재만 정리한다(systemd가 자기 cgroup은 이미 stop).

# 중복 시 문제를 일으키는 핵심 노드/런치 패턴 (pgrep -f 정규식)
PATTERNS=(
  'ros2 launch .*fleet_main'              # orphan 런치 자체
  'ydlidar_ros2_driver_node'              # 라이다(device 점유)
  'rplidar_node|sllidar_node'             # 타 라이다 드라이버
  'serial_bridge'                         # ESP32 시리얼(device 점유)
  'async_slam_toolbox_node'               # SLAM(TF·map 이중발행)
  '/opt/ros/humble/lib/nav2_'             # Nav2 전체(costmap·TF 이중발행)
)

cleaned=0
for pat in "${PATTERNS[@]}"; do
  pids=$(pgrep -f "$pat" 2>/dev/null)
  [ -z "$pids" ] && continue
  kill -TERM $pids 2>/dev/null
  cleaned=$((cleaned + 1))
done
if [ "$cleaned" -gt 0 ]; then
  sleep 1
  # SIGTERM 무시하는 잔재는 SIGKILL (Nav2/ydlidar 가 느리거나 무시하는 사례 있음)
  for pat in "${PATTERNS[@]}"; do
    pids=$(pgrep -f "$pat" 2>/dev/null)
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null
  done
  echo "ros_preclean: 잔재 노드 정리 완료(${cleaned} 패턴)"
fi
exit 0
