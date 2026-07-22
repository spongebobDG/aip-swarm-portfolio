cmake_minimum_required(VERSION 3.8)
project(aip_fleet_gazebo)

find_package(ament_cmake REQUIRED)

install(DIRECTORY worlds launch scripts config
  DESTINATION share/${PROJECT_NAME}
)

# Install Python scripts as ROS2 executables (ros2 run aip_fleet_gazebo <name>)
install(PROGRAMS
  scripts/cmd_relay.py
  scripts/sim_peer_sensing_node.py
  scripts/odom_frame_fixer.py
  scripts/uwb_accuracy_check.py  # DEPRECATED (2026-06-15): 전 차량 LiDAR+SLAM 채택으로 불필요
  scripts/sim_thermal_node.py
  scripts/scenario_manager_node.py
  scripts/peer_obstacle_node.py
  scripts/coverage_tracker_node.py
  scripts/arm_scan_node.py
  scripts/stuck_escape_node.py
  scripts/joint_states_relay.py
  scripts/sim_heartbeat_node.py
  scripts/sim_pose_relay_node.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
