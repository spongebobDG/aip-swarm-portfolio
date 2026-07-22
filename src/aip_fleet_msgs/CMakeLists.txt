cmake_minimum_required(VERSION 3.8)
project(aip_fleet_msgs)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  msg/FleetHeartbeat.msg
  msg/FleetStatus.msg
  msg/OverrideCommand.msg
  msg/PeerPose.msg
  msg/PeerPoseArray.msg
  msg/PeerRange.msg
  msg/PeerRangeArray.msg
  msg/PerceptionAlert.msg
  srv/AssignMission.srv
  DEPENDENCIES builtin_interfaces geometry_msgs std_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
