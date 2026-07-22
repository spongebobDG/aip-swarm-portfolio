# Aggregated fleet status published by the supervisor at 2 Hz.
# The dashboard subscribes to a single topic instead of fanning out per vehicle.

builtin_interfaces/Time stamp
FleetHeartbeat[<=4] vehicles
string<=32[<=4] offline_vehicle_ids   # IDs whose heartbeat has lapsed
