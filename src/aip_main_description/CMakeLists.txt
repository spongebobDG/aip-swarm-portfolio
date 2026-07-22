cmake_minimum_required(VERSION 3.8)
project(aip_main_description)

find_package(ament_cmake REQUIRED)

install(DIRECTORY urdf config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
