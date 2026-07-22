#!/bin/bash
export TERM=dumb
L=$(grep -l "ign gazebo" ~/.ros/log/*/launch.log 2>/dev/null | xargs ls -t 2>/dev/null | head -1)
D=$(dirname "$L")
echo "LOG: $L"
echo "=== 노드별 로그 파일 존재? ==="
ls "$D" 2>/dev/null | grep -iE "controller_server|bt_navigator|planner_server|lifecycle|behavior_server" | head
echo "=== Nav2 노드 메시지 (process started 제외, 멈춤 지점) ==="
grep -anE "\[controller_server-27\]|\[bt_navigator-26\]|\[planner_server-25\]|\[lifecycle_manager-29\]|\[behavior_server-28\]" "$L" 2>/dev/null | grep -avE "process started|process has" | tail -18
echo "=== controller_server stderr ==="
cat "$D"/controller_server-27*.log 2>/dev/null | tail -12
echo "=== lifecycle_manager stderr ==="
cat "$D"/lifecycle_manager-29*.log 2>/dev/null | tail -8
