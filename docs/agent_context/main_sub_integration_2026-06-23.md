# Main + Sub Web Integration Log (2026-06-23)

## Scope

- Created local integration copy at `C:\Projects\aip-swarm-ws-main+sub`.
- Source baseline: team main snapshot under `C:\Users\user\Downloads\aip-swarm-ws-main (2)\aip-swarm-ws-main_team1(main)`.
- Remote repository HEAD observed during integration: `Mark2AC/aip-swarm-ws.git` at `07a7722ae1f285ccbd6a3b651ddf24a62e9428a0`.
- The local team snapshot has no `.git` metadata, so exact snapshot-vs-remote commit equivalence was not provable locally.
- The team main source folder was not modified.
- No Git push was performed.

## Decisions

- Web display IDs are standardized as `aip1`, `aip2`, `aip3`.
- Current live topic compatibility is handled through aliases:
  - `aip1 -> aip1`
  - `aip2 -> scout_1`
  - `aip3 -> scout_2`
- Main vehicle internal software remains team-owned. The integration only changes the local copied web/supervisor layer.
- Autonomous navigation remains gated by `AIP_NAV_ALLOWED_IDS`; manual control and pose/map validation should be verified first.

## Implemented

- Ported the improved dashboard server and static dashboard UI into the local integration folder.
- Normalized dashboard defaults to show exactly `aip1`, `aip2`, `aip3`.
- Added dashboard alias routing with `AIP_VEHICLE_TOPIC_ALIASES`.
- Updated supervisor to publish `/fleet/status` using display IDs while subscribing/publishing to aliased live topics.
- Updated `supervisor.yaml` with the default live aliases.
- Updated `run_central.sh` to use `supervisor.yaml` and `leader_ns:=aip1`.
- Preserved pose calibration, yaw display, robot direction arrow, saved map loading, map source control, manual drive safety gate, and control lock stabilization from the previous work.

## Verification

- `python -m py_compile` passed for:
  - `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py`
  - `src/aip_fleet_supervisor/aip_fleet_supervisor/supervisor_node.py`
  - `src/aip_fleet_bringup/launch/central.launch.py`
- Dashboard JavaScript syntax check passed with Node.js.
- WSL Ubuntu build passed:
  - `colcon build --symlink-install --packages-select aip_fleet_msgs aip_fleet_supervisor aip_fleet_dashboard aip_fleet_bringup`

## Remaining Live Checks

1. Start the local integration stack from `C:\Projects\aip-swarm-ws-main+sub`.
2. Confirm dashboard cards show only `aip1`, `aip2`, `aip3`.
3. Confirm `/fleet/status` contains `aip1/aip2/aip3`, not raw `scout_1/scout_2`.
4. Confirm selecting `aip2` or `aip3` does not jump to another vehicle.
5. Confirm control release remains released and does not behave like pause-only.
6. Confirm map source stays on saved/global map unless the operator explicitly selects a vehicle SLAM map.
7. Keep `aip1` motion commands disabled unless the main vehicle owner approves.

## Live Run Update

- Started the local integration dashboard at `http://127.0.0.1:8080`.
- Reintroduced the real-fleet single-process launcher because separate local
  ROS participants did not discover each other through the Discovery Server.
- Updated `FleetHeartbeat.msg` to match the deployed vehicle definition
  (`robot_id`, `mode`, `healthy`, `estop`, `battery_percentage`, `status`, ...).
- Rebuilt `aip_fleet_msgs`, `aip_fleet_supervisor`, `aip_fleet_dashboard`, and
  `aip_fleet_bringup` successfully.
- Restarted the Discovery Server and robot containers.
- Confirmed inside `scout_1` container:
  - `/scout_1/heartbeat` publishes valid `aip_fleet_msgs/msg/FleetHeartbeat`.
- Confirmed inside `scout_2` container:
  - `USE_FLEET_ADAPTER=false`
  - `/scout_2/heartbeat` is not currently published.
- Current blocker:
  - The central PC still cannot receive `/scout_1/heartbeat` over DDS, even with
    matching message definition, fresh Discovery Server, robot container restart,
    and a temporary FastDDS UDP interface whitelist.
  - Dashboard therefore shows `aip1/aip2/aip3` as offline.
