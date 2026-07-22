cmake_minimum_required(VERSION 3.8)
project(aip_fleet_nav)

find_package(ament_cmake REQUIRED)

install(DIRECTORY params launch rviz
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
