# Absolute pose of one vehicle in the map frame.
#
# In simulation: derived from TF (map → <vehicle_id>/base_link) which reflects
#   slam_toolbox / AMCL localization with its natural odometry noise.
# On real hardware: each vehicle publishes its SLAM-estimated pose here;
#   the central PC aggregates and republishes as PeerPoseArray.
#
# covariance_xy_m: rough 1-σ position uncertainty radius.
#   Set 0.0 in sim (TF is the best estimate available).
#   On real hardware fill from SLAM covariance diagonal.

string<=32 vehicle_id
geometry_msgs/Pose pose      # map frame
float64 covariance_xy_m      # 1-σ position uncertainty (m), 0 = unknown/sim
