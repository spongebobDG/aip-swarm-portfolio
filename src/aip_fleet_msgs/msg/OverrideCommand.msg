# Override command issued from the central PC (operator via Foxglove panel
# or an automated policy). Consumed by aip_fleet_supervisor which routes it
# into the per-vehicle override_cmd_vel / estop topics.

string vehicle_id          # "*" targets every vehicle
builtin_interfaces/Time stamp

uint8 CMD_CLEAR   = 0      # release override, return to autonomy
uint8 CMD_PAUSE   = 1      # hold position, keep autonomy loaded
uint8 CMD_RESUME  = 2      # resume autonomy after PAUSE
uint8 CMD_ESTOP   = 3      # hard stop, requires CLEAR to recover
uint8 CMD_MANUAL  = 4      # operator drives via manual_cmd_vel below
uint8 command

geometry_msgs/Twist manual_cmd_vel   # only honored when command == CMD_MANUAL
