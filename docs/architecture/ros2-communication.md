# ROS2 Communication 분석

> 목적: 이 문서는 코드에서 확인되는 ROS2 패키지, Node, Topic, Service, Action, Message Type, Parameter, Launch Argument를 포트폴리오와 면접 설명에 사용할 수 있도록 정리한다.

## 1. 확인 기준

| 확인 여부 | 의미 |
|---|---|
| 확인됨 | `package.xml`, `setup.py`, `CMakeLists.txt`, launch 파일, `rclpy`/`rclcpp` 코드에서 직접 확인됨 |
| 문서상 확인 | README 또는 문서에는 있으나 이번 코드 검색에서 직접 동작 지점을 확인하지 못함 |
| 추정 | 코드 구조상 가능성이 높지만 정확한 런타임 연결은 추가 실행 검증 필요 |
| TODO | 아직 확인하지 못했거나 실제 실행으로 보완해야 함 |

## 2. ROS2 패키지 및 인터페이스 요약

### 2.1 확인된 ROS2 패키지

코드에서 `package.xml`이 확인된 패키지는 다음과 같다.

| 패키지 | 성격 | 확인 여부 |
|---|---|---|
| `aip_fleet_autonomous` | 자율주행, patrol, map readiness, keepout 관련 Python Node | 확인됨 |
| `aip_fleet_bringup` | launch 중심 bringup 패키지 | 확인됨 |
| `aip_fleet_coordinator` | fleet coordinator, localizer 관련 Python Node | 확인됨 |
| `aip_fleet_dashboard` | 웹 Dashboard 서버 및 ROS2 연동 Node | 확인됨 |
| `aip_fleet_gazebo` | Gazebo/Ignition 관련 리소스 패키지 | 확인됨 |
| `aip_fleet_msgs` | Custom Message/Service 인터페이스 패키지 | 확인됨 |
| `aip_fleet_nav` | Navigation 관련 launch/config 패키지 | 확인됨 |
| `aip_fleet_perception` | thermal, vision, perception fusion, arm scan 관련 Python Node | 확인됨 |
| `aip_fleet_real` | 실차 serial bridge, heartbeat, scan deskew 관련 Python Node | 확인됨 |
| `aip_fleet_sim` | 시뮬레이션 world, vehicle, lidar 관련 Python Node | 확인됨 |
| `aip_fleet_supervisor` | fleet supervisor, watchdog 관련 Python Node | 확인됨 |
| `aip_fleet_telemetry` | telemetry bridge Node | 확인됨 |
| `aip_main_description` | 메인 AGV description 리소스 패키지 | 확인됨 |
| `explore_lite` | C++ exploration Node | 확인됨 |
| `explore_lite_msgs` | explore 관련 인터페이스 패키지 | 확인됨 |
| `multirobot_map_merge` | C++ map merge Node | 확인됨 |

### 2.2 확인된 Custom Message/Service

`src/aip_fleet_msgs/CMakeLists.txt`에서 아래 인터페이스 생성이 확인된다.

| 구분 | 이름 | 파일 위치 | 역할 | 입력 | 출력 | 메시지 타입 | 확인 여부 |
|---|---|---|---|---|---|---|---|
| Message | `FleetHeartbeat` | `src/aip_fleet_msgs/msg/FleetHeartbeat.msg` | 차량 heartbeat 상태 전달 | 차량 상태 값 | heartbeat topic | `aip_fleet_msgs/msg/FleetHeartbeat` | 확인됨 |
| Message | `FleetStatus` | `src/aip_fleet_msgs/msg/FleetStatus.msg` | fleet 전체 상태 요약 | supervisor 내부 상태 | `/fleet/status` | `aip_fleet_msgs/msg/FleetStatus` | 확인됨 |
| Message | `OverrideCommand` | `src/aip_fleet_msgs/msg/OverrideCommand.msg` | fleet override/E-stop 명령 | Dashboard 또는 watchdog 명령 | `/fleet/override` | `aip_fleet_msgs/msg/OverrideCommand` | 확인됨 |
| Message | `PeerPose` | `src/aip_fleet_msgs/msg/PeerPose.msg` | peer 차량 pose 단위 데이터 | localizer/coordinator 추정값 | peer pose array 구성 | `aip_fleet_msgs/msg/PeerPose` | 확인됨 |
| Message | `PeerPoseArray` | `src/aip_fleet_msgs/msg/PeerPoseArray.msg` | 여러 peer pose 전달 | peer pose 목록 | `/fleet/peer_poses` | `aip_fleet_msgs/msg/PeerPoseArray` | 확인됨 |
| Message | `PeerRange` | `src/aip_fleet_msgs/msg/PeerRange.msg` | peer 간 거리 단위 데이터 | range 측정값 | peer range array 구성 | `aip_fleet_msgs/msg/PeerRange` | 확인됨 |
| Message | `PeerRangeArray` | `src/aip_fleet_msgs/msg/PeerRangeArray.msg` | 여러 peer range 전달 | range 목록 | localizer 입력 후보 | `aip_fleet_msgs/msg/PeerRangeArray` | 확인됨 |
| Message | `PerceptionAlert` | `src/aip_fleet_msgs/msg/PerceptionAlert.msg` | perception 경고 이벤트 전달 | thermal/vision 감지 결과 | `/fleet/alerts` | `aip_fleet_msgs/msg/PerceptionAlert` | 확인됨 |
| Service | `AssignMission` | `src/aip_fleet_msgs/srv/AssignMission.srv` | mission 할당용 custom service | TODO | TODO | `aip_fleet_msgs/srv/AssignMission` | 파일 확인됨, 사용처 TODO |

## 3. ROS2 통신 상세 표

| 구분 | 이름 | 파일 위치 | 역할 | 입력 | 출력 | 메시지 타입 | 확인 여부 |
|---|---|---|---|---|---|---|---|
| setup.py entry point | `coordinator_node` | `src/aip_fleet_coordinator/setup.py` | fleet coordinator 실행 엔트리 | ROS2 runtime | `aip_fleet_coordinator.coordinator_node:main` | Python console script | 확인됨 |
| setup.py entry point | `scout_localizer_node` | `src/aip_fleet_coordinator/setup.py` | scout localizer 실행 엔트리 | ROS2 runtime | `aip_fleet_coordinator.scout_localizer_node:main` | Python console script | 확인됨 |
| setup.py entry point | `uwb_localizer_node` | `src/aip_fleet_coordinator/setup.py` | UWB localizer 실행 엔트리 | ROS2 runtime | `aip_fleet_coordinator.uwb_localizer_node:main` | Python console script | 확인됨 |
| setup.py entry point | `dashboard_server` | `src/aip_fleet_dashboard/setup.py` | 웹 Dashboard 서버 실행 엔트리 | ROS2 runtime, HTTP/WebSocket client | `aip_fleet_dashboard.dashboard_server:main` | Python console script | 확인됨 |
| setup.py entry point | `patrol_node` | `src/aip_fleet_autonomous/setup.py` | patrol action client 실행 엔트리 | ROS2 runtime | `aip_fleet_autonomous.patrol_node:main` | Python console script | 확인됨 |
| setup.py entry point | `map_readiness_node` | `src/aip_fleet_autonomous/setup.py` | map readiness 실행 엔트리 | ROS2 runtime | `aip_fleet_autonomous.map_readiness_node:main` | Python console script | 확인됨 |
| setup.py entry point | `follower_trigger_node` | `src/aip_fleet_autonomous/setup.py` | follower trigger 실행 엔트리 | ROS2 runtime | `aip_fleet_autonomous.follower_trigger_node:main` | Python console script | 확인됨 |
| setup.py entry point | `patrol_planner_node` | `src/aip_fleet_autonomous/setup.py` | patrol planner 실행 엔트리 | ROS2 runtime | `aip_fleet_autonomous.patrol_planner_node:main` | Python console script | 확인됨 |
| setup.py entry point | `keepout_zone_node` | `src/aip_fleet_autonomous/setup.py` | keepout zone 실행 엔트리 | ROS2 runtime | `aip_fleet_autonomous.keepout_zone_node:main` | Python console script | 확인됨 |
| setup.py entry point | `thermal_driver_node` | `src/aip_fleet_perception/setup.py` | thermal driver 실행 엔트리 | ROS2 runtime | `aip_fleet_perception.thermal_driver_node:main` | Python console script | 확인됨 |
| setup.py entry point | `thermal_uart_driver_node` | `src/aip_fleet_perception/setup.py` | UART thermal driver 실행 엔트리 | ROS2 runtime | `aip_fleet_perception.thermal_uart_driver_node:main` | Python console script | 확인됨 |
| setup.py entry point | `patrol_monitor_node` | `src/aip_fleet_perception/setup.py` | thermal monitoring 실행 엔트리 | ROS2 runtime | `aip_fleet_perception.patrol_monitor_node:main` | Python console script | 확인됨 |
| setup.py entry point | `central_fusion_node` | `src/aip_fleet_perception/setup.py` | central perception fusion 실행 엔트리 | ROS2 runtime | `aip_fleet_perception.central_fusion_node:main` | Python console script | 확인됨 |
| setup.py entry point | `arm_scan_node` | `src/aip_fleet_perception/setup.py` | arm scan 실행 엔트리 | ROS2 runtime | `aip_fleet_perception.arm_scan_node:main` | Python console script | 확인됨 |
| setup.py entry point | `alert_visualizer_node` | `src/aip_fleet_perception/setup.py` | alert visualization 실행 엔트리 | ROS2 runtime | `aip_fleet_perception.alert_visualizer_node:main` | Python console script | 확인됨 |
| setup.py entry point | `vision_pi_bridge_node` | `src/aip_fleet_perception/setup.py` | Vision Pi bridge 실행 엔트리 | ROS2 runtime, Pi HTTP endpoint | `aip_fleet_perception.vision_pi_bridge_node:main` | Python console script | 확인됨 |
| setup.py entry point | `sim_world_node` | `src/aip_fleet_sim/setup.py` | simulation world 실행 엔트리 | ROS2 runtime | `aip_fleet_sim.sim_world_node:main` | Python console script | 확인됨 |
| setup.py entry point | `sim_vehicle_node` | `src/aip_fleet_sim/setup.py` | simulation vehicle 실행 엔트리 | ROS2 runtime | `aip_fleet_sim.sim_vehicle_node:main` | Python console script | 확인됨 |
| setup.py entry point | `sim_lidar_node` | `src/aip_fleet_sim/setup.py` | simulation lidar 실행 엔트리 | ROS2 runtime | `aip_fleet_sim.sim_lidar_node:main` | Python console script | 확인됨 |
| setup.py entry point | `serial_bridge` | `src/aip_fleet_real/setup.py` | ESP32/serial bridge 실행 엔트리 | ROS2 runtime, serial port | `aip_fleet_real.serial_bridge:main` | Python console script | 확인됨 |
| setup.py entry point | `heartbeat_pub` | `src/aip_fleet_real/setup.py` | heartbeat publisher 실행 엔트리 | ROS2 runtime | `aip_fleet_real.heartbeat_pub:main` | Python console script | 확인됨 |
| setup.py entry point | `scan_deskew_node` | `src/aip_fleet_real/setup.py` | LaserScan deskew 실행 엔트리 | ROS2 runtime | `aip_fleet_real.scan_deskew_node:main` | Python console script | 확인됨 |
| setup.py entry point | `supervisor_node` | `src/aip_fleet_supervisor/setup.py` | supervisor 실행 엔트리 | ROS2 runtime | `aip_fleet_supervisor.supervisor_node:main` | Python console script | 확인됨 |
| setup.py entry point | `watchdog_node` | `src/aip_fleet_supervisor/setup.py` | watchdog 실행 엔트리 | ROS2 runtime | `aip_fleet_supervisor.watchdog_node:main` | Python console script | 확인됨 |
| setup.py entry point | `telemetry_node` | `src/aip_fleet_telemetry/setup.py` | telemetry 실행 엔트리 | ROS2 runtime | `aip_fleet_telemetry.telemetry_node:main` | Python console script | 확인됨 |
| CMake executable | `explore` | `src/explore_lite/CMakeLists.txt` | C++ exploration Node 빌드 대상 | C++ source | `explore` executable | `rclcpp` executable | 확인됨 |
| CMake executable | `map_merge` | `src/multirobot_map_merge/CMakeLists.txt` | C++ map merge Node 빌드 대상 | C++ source | `map_merge` executable | `rclcpp` executable | 확인됨 |
| Launch | `central.launch.py` | `src/aip_fleet_bringup/launch/central.launch.py` | 중앙 supervisor/dashboard/perception/coordinator bringup | `supervisor_params`, `leader_ns`, `with_twist_mux`, `with_coordinator`, `with_security`, `with_localizer`, `camera_mode`, `camera_frame`, `camera_offset_*`, `with_keepout`, `with_foxglove`, `foxglove_address`, `with_dashboard`, `with_telemetry`, `with_perception`, `vision_pi_url` | supervisor, watchdog, dashboard, foxglove, coordinator, localizer, telemetry, perception, keepout 등 | Launch Argument | 확인됨 |
| Launch | `fleet_sim.launch.py` | `src/aip_fleet_bringup/launch/fleet_sim.launch.py` | 시뮬레이션 fleet bringup | `world_yaml`, `vehicles_yaml`, `use_sim_time` 등 TODO 세부 검증 | sim world, sim vehicle, sim lidar, central include | Launch Argument | 확인됨 |
| Launch | `fleet_main.launch.py` | `src/aip_fleet_bringup/launch/fleet_main.launch.py` | 실차/메인 AGV bringup | `with_base`, `localization`, `map_yaml`, `with_nav2`, `with_patrol`, `use_sim_time` | serial bridge, heartbeat, slam_toolbox, nav2, patrol 등 | Launch Argument | 확인됨 |
| Launch | `main_agv.launch.py` | `src/aip_fleet_bringup/launch/main_agv.launch.py` | main AGV launch | `namespace`, `with_patrol`, `use_sim_time` | scan deskew, slam_toolbox, nav2, patrol 등 | Launch Argument | 확인됨 |
| Launch | `turtlebot3.launch.py` | `src/aip_fleet_bringup/launch/turtlebot3.launch.py` | TurtleBot3 기반 차량 launch | `namespace`, `use_sim_time`, `with_patrol` | TB3 bringup, slam_toolbox, nav2, twist_mux, patrol | Launch Argument | 확인됨 |
| Launch | `custom_vehicle.launch.py` | `src/aip_fleet_bringup/launch/custom_vehicle.launch.py` | custom vehicle placeholder launch | `namespace`, `use_sim_time`, `drivers_ready` | driver 준비 시 slam_toolbox/nav2 | Launch Argument | 확인됨 |
| Launch | `vision_pi_bridge.launch.py` | `src/aip_fleet_perception/launch/vision_pi_bridge.launch.py` | Vision Pi bridge 단독 launch | `vehicle_id`, `base_url` | `vision_pi_bridge_node` | Launch Argument | 확인됨 |
| Launch | `perception_vehicle.launch.py` | `src/aip_fleet_perception/launch/perception_vehicle.launch.py` | 차량 perception bringup | `vehicle_id`, `sim`, `camera_type`, `video_device`, `thermal_iface`, `thermal_port` | camera driver, thermal driver, patrol monitor | Launch Argument | 확인됨 |
| Launch | `perception_central.launch.py` | `src/aip_fleet_perception/launch/perception_central.launch.py` | 중앙 perception fusion launch | `model_path` | `central_fusion_node` | Launch Argument | 확인됨 |
| Launch | `thermal_only.launch.py` | `src/aip_fleet_perception/launch/thermal_only.launch.py` | thermal pipeline 단독 launch | `vehicle_id` | thermal UART driver, patrol monitor | Launch Argument | 확인됨 |
| Launch | `camera_driver.launch.py` | `src/aip_fleet_perception/launch/camera_driver.launch.py` | USB/V4L2 camera driver launch | `vehicle_id`, `camera_type`, `video_device` | `camera_ros/camera_node` 또는 `v4l2_camera_node` | Launch Argument | 확인됨 |
| Launch | `arm_scan.launch.py` | `src/aip_fleet_perception/launch/arm_scan.launch.py` | arm scan Node launch | `vehicle_id`, `arm_config` | `arm_scan_node` | Launch Argument | 확인됨 |
| Node | `aip_fleet_supervisor` | `src/aip_fleet_supervisor/aip_fleet_supervisor/supervisor_node.py` | 차량 heartbeat 수집, fleet status 발행, override/E-stop 전달 | `/<vehicle>/heartbeat`, `/fleet/override`, `/fleet/control_lock` | `/fleet/status`, `/fleet/control_lock_state`, `/<vehicle>/override_cmd_vel`, `/<vehicle>/estop`, `/<vehicle>/estop_lock` | `FleetHeartbeat`, `OverrideCommand`, `String`, `FleetStatus`, `Twist`, `Bool` | 확인됨 |
| Parameter | `supervisor_node` parameters | `src/aip_fleet_supervisor/aip_fleet_supervisor/supervisor_node.py` | supervisor 동작 설정 | `vehicle_ids`, `vehicle_topic_aliases`, `vehicle_cmd_vel_overrides`, `heartbeat_timeout_sec`, `control_lock_ttl_sec`, `require_control_lock` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `aip_fleet_watchdog` | `src/aip_fleet_supervisor/aip_fleet_supervisor/watchdog_node.py` | offline 차량 감지 후 E-stop/clear override 발행 | `/fleet/status` | `/fleet/override` | `FleetStatus`, `OverrideCommand` | 확인됨 |
| Parameter | `watchdog_node` parameters | `src/aip_fleet_supervisor/aip_fleet_supervisor/watchdog_node.py` | watchdog 판단 설정 | `offline_confirm_count` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `dashboard_server` | `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py` | 웹관제와 ROS2 사이 bridge/server | `/fleet/status`, `/fleet/alerts`, `/fleet/coverage_pct`, `/fleet/vehicle_coverage_pct`, `/fleet/map_ready`, `/map`, `/map_static`, `/<vehicle>/map`, `/fleet/peer_poses`, `/fleet/control_lock_state`, `/patrol_planner/plan_state`, `/<vehicle>/patrol_status`, `/<vehicle>/thermal_temp`, `/fleet/perception_viz/<vehicle>`, `/<vehicle>/thermal_viz`, `/<vehicle>/thermal_raw`, `/<vehicle>/odom`, `/<vehicle>/scan`, battery topic | `/<vehicle>/estop`, `/<vehicle>/initialpose`, `/<vehicle>/override_cmd_vel`, `/<vehicle>/goal_pose`, `/<vehicle>/mode`, `/fleet/override`, `/fleet/control_lock`, `/sim/set_scenario`, `/fleet/map_ready`, `/patrol_planner/cmd`, `/fleet/keepout_zones`, arm control topics | `FleetStatus`, `PerceptionAlert`, `String`, `Bool`, `OccupancyGrid`, `PeerPoseArray`, `Float32`, `CompressedImage`, `Image`, `Odometry`, `LaserScan`, `BatteryState`, `Twist`, `PoseStamped`, `PoseWithCovarianceStamped`, `OverrideCommand`, `UInt8MultiArray` | 확인됨 |
| Action Client | `/<vehicle>/navigate_to_pose` | `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py` | Dashboard에서 Nav2 goal 전송 | 웹 goal 요청 | Nav2 action goal | `nav2_msgs/action/NavigateToPose` | 확인됨 |
| Service Client | `/save_map_now` | `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py` | 웹에서 map 저장 요청 전달 | 웹 요청 | Trigger service request | `std_srvs/srv/Trigger` | 확인됨 |
| Node | `patrol_node` | `src/aip_fleet_autonomous/aip_fleet_autonomous/patrol_node.py` | patrol waypoint를 Nav2 goal로 전송하고 상태 발행 | `/map_static`, `/patrol_planner/plan_state`, `/patrol_planner/cmd` | `/<vehicle>/patrol_status`, `/<vehicle>/patrol_path_viz`, Nav2 action goal | `OccupancyGrid`, `String`, `MarkerArray`, `NavigateToPose` | 확인됨 |
| Parameter | `patrol_node` parameters | `src/aip_fleet_autonomous/aip_fleet_autonomous/patrol_node.py` | patrol 동작 설정 | `vehicle_id`, `waypoints`, `loop_patrol`, `start_delay_sec` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Action Client | `/<vehicle>/navigate_to_pose` | `src/aip_fleet_autonomous/aip_fleet_autonomous/patrol_node.py` | patrol waypoint를 Nav2 Action으로 전달 | waypoint list | Nav2 action goal | `nav2_msgs/action/NavigateToPose` | 확인됨 |
| Node | `keepout_zone_node` | `src/aip_fleet_autonomous/aip_fleet_autonomous/keepout_zone_node.py` | keepout zone 문자열을 costmap cloud로 변환하고 costmap clear 요청 | `/fleet/keepout_zones` | `/fleet/keepout_cloud`, costmap clear service request | `String`, `PointCloud2`, `nav2_msgs/srv/ClearEntireCostmap` | 확인됨 |
| Parameter | `keepout_zone_node` parameters | `src/aip_fleet_autonomous/aip_fleet_autonomous/keepout_zone_node.py` | 적용 차량 목록 설정 | `vehicle_ids` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Service Client | `/{vehicle}/global_costmap/clear_entirely_global_costmap` | `src/aip_fleet_autonomous/aip_fleet_autonomous/keepout_zone_node.py` | keepout 변경 후 global costmap clear | keepout 변경 이벤트 | ClearEntireCostmap request | `nav2_msgs/srv/ClearEntireCostmap` | 확인됨 |
| Service Client | `/{vehicle}/local_costmap/clear_entirely_local_costmap` | `src/aip_fleet_autonomous/aip_fleet_autonomous/keepout_zone_node.py` | keepout 변경 후 local costmap clear | keepout 변경 이벤트 | ClearEntireCostmap request | `nav2_msgs/srv/ClearEntireCostmap` | 확인됨 |
| Node | `map_readiness_node` | `src/aip_fleet_autonomous/aip_fleet_autonomous/map_readiness_node.py` | map 사용 가능 상태 판단 | `/map`, `explore/status` TODO 세부 검증 | `/fleet/map_ready` | `OccupancyGrid`, `String`, `Bool` | 확인됨 |
| Node | `follower_trigger_node` | `src/aip_fleet_autonomous/aip_fleet_autonomous/follower_trigger_node.py` | map 저장/정적 map 발행 트리거 | live map topic TODO 세부 검증 | `/map_static`, `/save_map_now` service | `OccupancyGrid`, `std_srvs/srv/Trigger` | 확인됨 |
| Service Server | `/save_map_now` | `src/aip_fleet_autonomous/aip_fleet_autonomous/follower_trigger_node.py` | 현재 map 저장 트리거 제공 | Trigger request | Trigger response | `std_srvs/srv/Trigger` | 확인됨 |
| Node | `patrol_planner_node` | `src/aip_fleet_autonomous/aip_fleet_autonomous/patrol_planner_node.py` | map 기반 patrol plan 생성/명령 처리 | `/map`, `/map_static`, `/goal_pose`, `/clicked_point`, `/patrol_planner/cmd` | `/patrol_planner/plan_state`, preview/visualization topic TODO | `OccupancyGrid`, `PoseStamped`, `PointStamped`, `String` | 확인됨 |
| Node | `coordinator_node` | `src/aip_fleet_coordinator/aip_fleet_coordinator/coordinator_node.py` | fleet coordination 및 follower command 생성 | `/fleet/status`, peer/localization 관련 topic TODO 세부 검증 | vehicle command/coordination topic TODO | `FleetStatus`, `Twist` 등 TODO | 확인됨, 세부 TODO |
| Node | `scout_localizer_node` | `src/aip_fleet_coordinator/aip_fleet_coordinator/scout_localizer_node.py` | scout 위치 추정 및 peer pose 발행 | range/odom/pose 관련 topic TODO 세부 검증 | `/fleet/peer_poses` | `PeerPoseArray` 등 TODO | 확인됨, 세부 TODO |
| Node | `uwb_localizer_node` | `src/aip_fleet_coordinator/aip_fleet_coordinator/uwb_localizer_node.py` | UWB 기반 localizer 코드 | TODO | TODO | `PeerRangeArray`, `PeerPoseArray` 등 TODO | 코드 확인됨, 실제 사용 여부 확인 필요 |
| Node | `thermal_driver_node` | `src/aip_fleet_perception/aip_fleet_perception/thermal_driver_node.py` | thermal sensor frame/temp 발행 | thermal sensor 또는 sim data | `/<vehicle>/thermal_raw`, `/<vehicle>/thermal_temp` | `sensor_msgs/msg/Image`, `std_msgs/msg/Float32` | 확인됨 |
| Parameter | `thermal_driver_node` parameters | `src/aip_fleet_perception/aip_fleet_perception/thermal_driver_node.py` | thermal driver 설정 | `vehicle_id`, `publish_hz`, `sim`, `i2c_bus` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `thermal_uart_driver_node` | `src/aip_fleet_perception/aip_fleet_perception/thermal_uart_driver_node.py` | UART thermal sensor frame/temp 발행 | UART thermal sensor 또는 sim data | `/<vehicle>/thermal_raw`, `/<vehicle>/thermal_temp` | `sensor_msgs/msg/Image`, `std_msgs/msg/Float32` | 확인됨 |
| Parameter | `thermal_uart_driver_node` parameters | `src/aip_fleet_perception/aip_fleet_perception/thermal_uart_driver_node.py` | UART thermal driver 설정 | `vehicle_id`, `port`, `baud`, `send_auto`, `sim` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `patrol_monitor_node` | `src/aip_fleet_perception/aip_fleet_perception/patrol_monitor_node.py` | thermal frame 기반 온도 경고 생성 | `/<vehicle>/thermal_raw` | `/fleet/alerts`, `/<vehicle>/thermal_viz` | `Image`, `PerceptionAlert` | 확인됨 |
| Parameter | `patrol_monitor_node` parameters | `src/aip_fleet_perception/aip_fleet_perception/patrol_monitor_node.py` | 온도 경고 기준 설정 | `vehicle_id`, `warn_temp_c`, `high_temp_c`, `fire_temp_c`, `consecutive_frames`, `calibration_file`, `estimated_hotspot_distance_m` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `central_fusion_node` | `src/aip_fleet_perception/aip_fleet_perception/central_fusion_node.py` | image/alert fusion 및 perception visualization | `/fleet/alerts`, image topic 기본 `/<vehicle>/arm/image_raw/compressed` | `/fleet/alerts`, `/fleet/perception_viz/<vehicle>` | `PerceptionAlert`, `CompressedImage` | 확인됨 |
| Parameter | `central_fusion_node` parameters | `src/aip_fleet_perception/aip_fleet_perception/central_fusion_node.py` | fusion/model/viz 설정 | `vehicle_ids`, `model_path`, `fire_confidence`, `smoke_confidence`, `high_temp_c`, `image_topic`, `viz_stream_hz`, `viz_max_width`, `image_rotate` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `vision_pi_bridge_node` | `src/aip_fleet_perception/aip_fleet_perception/vision_pi_bridge_node.py` | Raspberry Pi 등 외부 vision endpoint를 ROS2 topic으로 변환 | HTTP status/RGB/Thermal endpoint | `/<vehicle>/heartbeat`, `/<vehicle>/image_raw/compressed`, `/<vehicle>/thermal_viz`, `/fleet/alerts` | `FleetHeartbeat`, `CompressedImage`, `Image`, `PerceptionAlert` | 확인됨 |
| Parameter | `vision_pi_bridge_node` parameters | `src/aip_fleet_perception/aip_fleet_perception/vision_pi_bridge_node.py` | 외부 vision endpoint와 publish rate 설정 | `vehicle_id`, `base_url`, `status_path`, `rgb_jpeg_path`, `thermal_jpeg_path`, `request_timeout_sec`, `heartbeat_hz`, `rgb_publish_hz`, `thermal_viz_hz`, `alert_check_hz`, `warn_temp_c`, `alert_cooldown_sec`, `publish_hotspot_bbox`, `hotspot_bbox_px` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `arm_scan_node` | `src/aip_fleet_perception/aip_fleet_perception/arm_scan_node.py` | arm scan sequence 및 servo/trajectory 제어 | `/<vehicle>/arm/scan_request`, `/<vehicle>/arm/estop` | `/<vehicle>/servo_cmd` 또는 joint command topics, `/<vehicle>/arm/state`, `/<vehicle>/arm/scan_complete`, trajectory action goal | `Bool`, `UInt8MultiArray`, `Float64`, `String`, `FollowJointTrajectory` | 확인됨 |
| Parameter | `arm_scan_node` parameters | `src/aip_fleet_perception/aip_fleet_perception/arm_scan_node.py` | arm scan 설정 파일/차량 설정 | `vehicle_id`, `config_file` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Action Client | `FollowJointTrajectory` | `src/aip_fleet_perception/aip_fleet_perception/arm_scan_node.py` | arm trajectory controller action 호출 | scan sequence | trajectory action goal | `control_msgs/action/FollowJointTrajectory` | 확인됨 |
| Node | `alert_visualizer_node` | `src/aip_fleet_perception/aip_fleet_perception/alert_visualizer_node.py` | perception alert marker 시각화 | `/fleet/alerts` | `/fleet/alert_markers` | `PerceptionAlert`, `MarkerArray` | 확인됨 |
| Parameter | `alert_visualizer_node` parameters | `src/aip_fleet_perception/aip_fleet_perception/alert_visualizer_node.py` | alert 시각화 대상 설정 | `vehicle_ids` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `sim_world_node` | `src/aip_fleet_sim/aip_fleet_sim/sim_world_node.py` | 시뮬레이션 map 및 static TF 발행 | world/vehicle YAML | `/map`, `/map_static`, `/<vehicle>/map`, `/<vehicle>/dashboard/map`, `/fleet/map_ready`, static TF | `OccupancyGrid`, `Bool`, TF | 확인됨 |
| Parameter | `sim_world_node` parameters | `src/aip_fleet_sim/aip_fleet_sim/sim_world_node.py` | 시뮬레이션 환경 파일 설정 | `world_yaml`, `vehicles_yaml` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `sim_vehicle_node` | `src/aip_fleet_sim/aip_fleet_sim/sim_vehicle_node.py` | 시뮬레이션 차량 odom/heartbeat 및 cmd 처리 | `/<vehicle>/cmd_vel`, `/<vehicle>/estop`, `/<vehicle>/override_cmd_vel` | `/<vehicle>/odom`, `/<vehicle>/heartbeat`, TF | `Twist`, `Bool`, `Odometry`, `FleetHeartbeat`, TF | 확인됨, 현재 오타 수정 필요 |
| Parameter | `sim_vehicle_node` parameters | `src/aip_fleet_sim/aip_fleet_sim/sim_vehicle_node.py` | 차량 초기 pose/속도/배터리 설정 | `vehicle_id`, `initial_x`, `initial_y`, `initial_theta`, `max_linear_vel`, `max_angular_vel`, `battery_drain_per_sec` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `sim_lidar_node` | `src/aip_fleet_sim/aip_fleet_sim/sim_lidar_node.py` | 시뮬레이션 LaserScan 발행 | world YAML, vehicle pose TODO 세부 검증 | `/<vehicle>/scan` | `sensor_msgs/msg/LaserScan` | 확인됨 |
| Parameter | `sim_lidar_node` parameters | `src/aip_fleet_sim/aip_fleet_sim/sim_lidar_node.py` | lidar 시뮬레이션 설정 | `vehicle_id`, `world_yaml`, `rate_hz`, `range_max`, `num_rays` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `serial_bridge` | `src/aip_fleet_real/aip_fleet_real/serial_bridge.py` | ESP32/하위제어기 serial bridge | relative `cmd_vel`, `servo_cmd`, `esp32_reset`, `esp32_beep`, serial data | relative `odom`, `enc_ticks`, TF, serial command | `Twist`, `UInt8MultiArray`, `Empty`, `Odometry`, `Int32MultiArray`, TF | 확인됨 |
| Parameter | `serial_bridge` parameters | `src/aip_fleet_real/aip_fleet_real/serial_bridge.py` | serial/차량 kinematics 설정 | `port`, `baud`, `vehicle_id`, `wheel_base`, `wheel_radius`, `ticks_per_rev`, `odom_frame`, `base_frame` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `heartbeat_pub` | `src/aip_fleet_real/aip_fleet_real/heartbeat_pub.py` | 실차 heartbeat 단독 publisher | `vehicle_id` parameter | relative `heartbeat` | `FleetHeartbeat` | 확인됨 |
| Parameter | `heartbeat_pub` parameters | `src/aip_fleet_real/aip_fleet_real/heartbeat_pub.py` | heartbeat vehicle id 설정 | `vehicle_id` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `scan_deskew_node` | `src/aip_fleet_real/aip_fleet_real/scan_deskew_node.py` | LaserScan deskew 처리 | `scan_in`, `odom_topic` | `scan_out` | `LaserScan`, `Odometry` | 확인됨 |
| Parameter | `scan_deskew_node` parameters | `src/aip_fleet_real/aip_fleet_real/scan_deskew_node.py` | deskew input/output/topic 설정 | `scan_in`, `scan_out`, `odom_topic`, `time_reverse`, `motion_eps` | Node 내부 설정 | ROS2 Parameter | 확인됨 |
| Node | `explore` | `src/explore_lite/src/explore.cpp` | frontier exploration 및 Nav2 goal 전송 | map/costmap/action feedback, `explore/resume` | `explore/frontiers`, `explore/status`, Nav2 action goal | `MarkerArray`, `String`, `Bool`, `nav2_msgs/action/NavigateToPose` | 확인됨 |
| Action Client | `navigate_to_pose` | `src/explore_lite/src/explore.cpp` | exploration 목표를 Nav2로 전송 | frontier target | Nav2 action goal | `nav2_msgs/action/NavigateToPose` | 확인됨 |
| Node | `map_merge` | `src/multirobot_map_merge/src/map_merge.cpp` | multi-robot map merge | robot map topics TODO 세부 검증 | merged map topic TODO 세부 검증 | `OccupancyGrid` 등 TODO | 확인됨, 세부 TODO |
| Action Server | Custom action server | `src/` 전체 검색 | 프로젝트 내부 custom action server 구현 여부 | TODO | TODO | TODO | 찾지 못함 |
| Service Server | Custom `AssignMission` server | `src/` 전체 검색 | `AssignMission.srv` 사용 server 여부 | TODO | TODO | `aip_fleet_msgs/srv/AssignMission` | 찾지 못함 |

## 4. 면접에서 설명할 때 주의할 점

- `ROS2를 사용했다`는 표현은 가능하지만, 어떤 Node가 어떤 Topic/Service/Action으로 통신하는지 위 표 기준으로 설명해야 한다.
- `Nav2를 직접 구현했다`가 아니라, 코드상으로는 `NavigateToPose` Action Client를 통해 Nav2에 goal을 전달하는 구조라고 설명하는 것이 안전하다.
- `웹관제`는 React/Vue 코드가 확인된 구조라기보다, 현재 코드 기준으로는 Python `dashboard_server`가 ROS2와 웹 UI 사이를 연결하는 역할로 확인된다.
- `Vision Camera Integration`은 `vision_pi_bridge_node`, `central_fusion_node`, camera launch, image topic이 확인된다. 실제 카메라 모델/실행 영상은 TODO로 남기는 것이 안전하다.
- `서브차량 제어`는 `serial_bridge`, `sim_vehicle_node`, `supervisor_node`, `watchdog_node`, `twist_mux` launch 구성이 핵심 근거다.
- `sim_vehicle_node.py`에는 현재 오타로 보이는 `retun`, `waning`이 있어 fresh 실행 전 수정/검증이 필요하다.
- `AssignMission.srv`는 인터페이스 파일은 있으나 server/client 사용처를 찾지 못했으므로 구현 기능처럼 말하지 않는다.
- `Action Server`는 프로젝트 내부 구현을 찾지 못했고, 주요 Action 사용은 Nav2/trajectory controller에 대한 Action Client로 설명하는 것이 안전하다.

## 5. 면접에서 설명해야 할 ROS2 질문 10개

1. 이 프로젝트에서 ROS2 Node는 어떤 기준으로 나뉘어 있나요?
2. `/fleet/status`와 `/<vehicle>/heartbeat`는 각각 어떤 역할을 하나요?
3. `supervisor_node`와 `watchdog_node`의 차이는 무엇인가요?
4. 웹 Dashboard에서 차량 제어 명령이 들어오면 ROS2 Topic으로 어떻게 전달되나요?
5. `NavigateToPose` Action Client를 사용한 이유와 Topic 제어와의 차이는 무엇인가요?
6. `OverrideCommand`, `FleetHeartbeat`, `FleetStatus` 같은 Custom Message를 만든 이유는 무엇인가요?
7. `Service`는 이 프로젝트에서 어디에 사용되며 Topic과 어떤 차이가 있나요?
8. `launch argument`와 `ROS2 parameter`는 각각 어떤 용도로 사용되나요?
9. 실차 `serial_bridge`와 시뮬레이션 `sim_vehicle_node`의 공통점과 차이는 무엇인가요?
10. 현재 ROS2 통신 구조에서 아직 검증이 필요한 부분과 개선하고 싶은 부분은 무엇인가요?

## 6. 내가 직접 보완해야 할 TODO

- 실제 실행 후 `ros2 node list`, `ros2 topic list -t`, `ros2 service list -t`, `ros2 action list -t` 결과를 이 문서에 캡처 또는 로그로 추가한다.
- `coordinator_node`, `scout_localizer_node`, `patrol_planner_node`, `map_readiness_node`, `map_merge`의 세부 input/output topic을 실행 결과와 함께 한 번 더 확인한다.
- `AssignMission.srv`가 실제로 사용되지 않는다면 README/면접에서는 "인터페이스 파일은 있으나 연결 구현은 확인 필요"로 설명한다.
- Dashboard 실행 화면, ROS2 graph, Topic echo 결과를 `docs/images/` 또는 `docs/videos/`에 추가한다.
- `sim_vehicle_node.py` 오타 수정 후 fresh build/run 검증 결과를 `docs/portfolio/troubleshooting.md`와 README에 반영한다.
