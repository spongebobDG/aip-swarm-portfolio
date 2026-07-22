# Array of peer vehicle poses, published by sim_peer_sensing_node (sim)
# or by the central PC after aggregating individual vehicle pose reports (real).
#
# Topic: /fleet/peer_poses   (10 Hz)
# Bounded for DDS compatibility: max 8 vehicles in one fleet.

builtin_interfaces/Time stamp
PeerPose[<=8] poses
