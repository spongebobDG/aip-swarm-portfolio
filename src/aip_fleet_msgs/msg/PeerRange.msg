# Single ranging measurement between two vehicles.
#
# In simulation: Euclidean distance from TF + Gaussian noise (noise_stddev_m).
# On real hardware: UWB two-way ranging result (e.g. DWM3001C with PDoA).
#
# vehicle_a / vehicle_b are unordered — (a,b) and (b,a) are the same pair.
# range_m is always >= 0.
# Pairs beyond the sensor's max_range_m are omitted from PeerRangeArray.
#
# PDoA angle-of-arrival (AoA) fields
# ─────────────────────────────────────────────────────────────────────────────
# aoa_a_rad: angle at which the signal from vehicle_b arrives at vehicle_a's
#            antenna array, expressed in vehicle_a's body frame.
#            Convention: 0 = directly ahead of vehicle_a,
#                        +π/2 = arrives from vehicle_a's left (ROS CCW+).
# aoa_b_rad: same, but measured at vehicle_b's antenna.
# aoa_noise_stddev_rad: 1-σ AoA measurement noise (typ. 0.087 rad = 5 deg).
#
# Set to IEEE 754 NaN (float('nan')) when PDoA is unsupported or unavailable.
# Both AoA fields may be NaN simultaneously (e.g. non-PDoA hardware).

string<=32 vehicle_a
string<=32 vehicle_b
float64 range_m               # measured range (m)
float64 noise_stddev_m        # range noise sigma (m); 0.0 on real hardware
float64 aoa_a_rad             # AoA at vehicle_a antenna, body frame (NaN = N/A)
float64 aoa_b_rad             # AoA at vehicle_b antenna, body frame (NaN = N/A)
float64 aoa_noise_stddev_rad  # AoA noise sigma (rad); NaN when AoA fields NaN
