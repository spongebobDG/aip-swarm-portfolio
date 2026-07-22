# Array of pairwise inter-vehicle range measurements.
# Published by sim_peer_sensing_node (sim) or a UWB aggregator node (real).
#
# Topic: /fleet/peer_ranges  (10 Hz)
# Bounded: 8 vehicles → max 8×7/2 = 28 unique pairs.

builtin_interfaces/Time stamp
PeerRange[<=28] ranges
