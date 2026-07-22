# AIP Scout — ESP32-S3 micro-ROS firmware

## Build & flash

```bash
cd firmware/scout
pio run                           # build
pio run -t upload                 # flash
pio device monitor                # watch logs
```

## Namespace switch

The binary is identical for aip2 and aip3. On power-up the
firmware listens on Serial for 3 s; send:

```
set_ns aip3
```

to persist the new namespace in NVS. The ESP resets and re-registers
as `/aip3/*` on the next boot.

## micro-ROS agent_ws

Because the firmware references `aip_fleet_msgs/msg/FleetHeartbeat`, the
micro-ROS build-time package set must include our message package:

```bash
# on the central PC (one-time, to generate C headers for the ESP build)
mkdir -p ~/uros_ws/src
cp -r src/aip_fleet_msgs ~/uros_ws/src/
cd ~/uros_ws
colcon build
# then copy the generated headers into the PlatformIO lib path, or
# configure micro_ros_platformio's extra_packages.colcon.meta to include
# aip_fleet_msgs from ~/uros_ws.
```

See `micro_ros_platformio`'s `extra_packages` documentation for the
per-framework custom-message workflow.

## Runtime prerequisites

- Wi-Fi `AIP_FLEET` must be reachable at power-up (firmware currently
  loops forever waiting for association — TODO: offline fallback).
- micro-ROS Agent must be listening on `udp4://192.168.0.9:8888`
  (`docker/central/docker-compose.yml` service `uros-agent`).
