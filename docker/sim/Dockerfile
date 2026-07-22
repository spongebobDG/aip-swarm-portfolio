# Dev-only image: runs the full AIP sim stack in ONE container.
#
# Unlike docker/central/* (which is split per-service and assumes host
# networking on the Ubuntu central PC), this image is intended for
# Docker Desktop / bridged networking where host networking is
# unreliable. Putting supervisor + watchdog + foxglove_bridge +
# sim_world + sim_vehicles + sim_lidar in a single container keeps all
# DDS traffic on the container's localhost.
#
# Build strategy: this image installs dependencies ONLY. The workspace
# itself (src/) is bind-mounted at runtime by docker-compose, and the
# entrypoint runs `colcon build` on first start so the install tree
# always matches whatever the host's src/ currently contains. This
# avoids symlink breakage from --symlink-install when the image is
# baked with stale paths, and makes the image reusable across edits.
#
# Build context is the workspace root:
#   docker build -t aip/sim:humble -f docker/sim/Dockerfile .

FROM ros:humble-ros-base

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions \
    python3-rosdep \
    python3-numpy \
    python3-yaml \
    python3-fastapi \
    python3-pil \
    python3-uvicorn \
    ros-humble-foxglove-bridge \
    ros-humble-nav2-msgs \
    ros-humble-twist-mux \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /ws

# Single-container sim: keep DDS on lo, no Discovery Server needed.
ENV ROS_DOMAIN_ID=42
ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp

COPY docker/sim/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["ros2", "launch", "aip_fleet_sim", "fleet_sim.launch.py"]
