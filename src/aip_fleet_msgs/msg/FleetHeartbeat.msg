# AIP fleet per-vehicle heartbeat.
# Published at /<ns>/heartbeat, 1 Hz minimum.
#
# Type hash MUST be identical across all vehicles (aip1, aip2, aip3)
# and the central supervisor. Any field change breaks DDS endpoint matching.
# SSOT: docs/FLEET_DASHBOARD_CONTRACT.md §1.

std_msgs/Header header
string  robot_id            # "aip1" | "aip2" | "aip3"
string  mode               # "manual" | "autonomous"
bool    healthy
bool    estop
bool    heartbeat_stale
bool    obstacle_stop
bool    cmd_stale
float32 battery_voltage     # unsupported vehicles: 0.0
float32 battery_percentage  # unsupported vehicles: 0.0
string  status              # "ok" | "blocked" | "heartbeat_stale" ...
