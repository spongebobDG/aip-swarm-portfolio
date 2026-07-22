#!/bin/bash
# Source ROS2, build the workspace if needed, then exec the launch command.
#
# `src/` is bind-mounted by docker-compose so it always reflects the host.
# We build into /ws/build + /ws/install which live inside the container's
# writable layer (or in a named volume if compose provides one). Using
# `exec` at the end preserves PID 1 so SIGTERM from `docker stop`
# propagates to ros2 launch and its child nodes.
#
# Incremental rebuilds: if /ws/install already exists we skip the build.
# To force a rebuild (e.g. after msg/srv changes), either:
#   docker compose restart sim   # no effect — install/ persists
#   docker compose down && up    # install/ is in container layer, lost → rebuild
#   OR touch a sentinel file:    ros2 daemon stop; rm -rf /ws/install /ws/build
set -e

source /opt/ros/humble/setup.bash

NEEDED_PACKAGES=(
    aip_fleet_msgs
    aip_fleet_supervisor
    aip_fleet_dashboard
    aip_fleet_autonomous
    aip_fleet_coordinator
    aip_fleet_bringup
    aip_fleet_sim
)

needs_build=false
if [ ! -f /ws/install/setup.bash ]; then
    needs_build=true
else
    source /ws/install/setup.bash
    for pkg in "${NEEDED_PACKAGES[@]}"; do
        if ! ros2 pkg prefix "$pkg" >/dev/null 2>&1; then
            needs_build=true
            break
        fi
    done
fi

if [ "$needs_build" = true ]; then
    echo "[entrypoint] building sim dashboard package set"
    cd /ws
    colcon build --symlink-install \
        --packages-up-to "${NEEDED_PACKAGES[@]}" \
        --event-handlers console_direct+
    echo "[entrypoint] build finished"
fi

source /ws/install/setup.bash
exec "$@"
