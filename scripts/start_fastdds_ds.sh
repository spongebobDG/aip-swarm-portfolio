#!/usr/bin/env bash
set -euo pipefail

pkill -f '[f]ast-discovery-server' 2>/dev/null || true
rm -f /tmp/fastdds_ds.log

setsid bash -lc 'source /opt/ros/humble/setup.bash; exec fast-discovery-server -i 0 -l 192.168.0.106 -p 11811' \
  >/tmp/fastdds_ds.log 2>&1 < /dev/null &

sleep 3
ps -ef | grep -E 'fast[-_]?discovery' | grep -v grep || true
ss -lunp 2>/dev/null | grep ':11811' || true
cat /tmp/fastdds_ds.log || true
