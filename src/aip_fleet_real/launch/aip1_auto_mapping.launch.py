"""aip1 자율 매핑 런치 — 중앙 SLAM + Nav2 + explore_lite(프론티어 자율 탐색).

수동 teleop 대신 차량이 스스로 미탐색 경계로 주행하며 지도화한다.
구성:
  main_agv.launch.py  → static TF 재발행 + slam_toolbox(mapping) + Nav2(RPP)
                        (with_patrol:=false → 순찰 노드 제외)
  explore_lite        → /aip1/map 의 프론티어 탐지 → /aip1/navigate_to_pose 로 목표 전송

안전(후방 라이다 마스킹 사각 대응 — config/main_agv/nav2.yaml):
  - RPP allow_reversing:false + behavior 'backup' 제거 + velocity min vx 0 → 후진 금지
  - use_collision_detection:true, max_time_to_collision:1.0, desired_linear_vel 0.30(곡선 0.15)
  - footprint 0.30×0.23 + padding 0.05 + inflation 0.30
  ※ 독립 로컬 장애물정지는 없음 → 감독 하 운용 + central(80) estop 대기 필수.

전제: aip1 base-only 가동(/aip1/scan, odom→base_footprint TF). 중앙 도메인 42 SIMPLE.
맵 저장: ros2 service call /aip1/slam_toolbox/save_map slam_toolbox/srv/SaveMap \
           "{name: {data: '/home/kde/aip_maps/aip1_map'}}"
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import GroupAction, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node, PushRosNamespace, SetRemap


def generate_launch_description():
    real_share = get_package_share_directory('aip_fleet_real')
    explore_share = get_package_share_directory('explore_lite')

    main_agv = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(real_share, 'launch', 'main_agv.launch.py')),
        launch_arguments={'with_patrol': 'false', 'use_sim_time': 'false'}.items(),
    )

    # explore_lite — namespace aip1, frame_prefix 정합(robot_base_frame=aip1/base_link).
    # costmap_topic 'map'(params 기본)은 namespace 로 /aip1/map(SLAM 맵)에 매핑돼 프론티어 탐지.
    explore = GroupAction([
        PushRosNamespace('aip1'),
        SetRemap('/tf', '/tf'),
        SetRemap('/tf_static', '/tf_static'),
        Node(
            package='explore_lite',
            executable='explore',
            name='explore_node',
            output='screen',
            parameters=[
                os.path.join(explore_share, 'config', 'params.yaml'),
                {'use_sim_time': False, 'robot_base_frame': 'aip1/base_link'},
            ],
        ),
    ])

    return LaunchDescription([
        main_agv,
        # SLAM(t≈0) + Nav2(t=5s, 라이프사이클 활성 ~15s) 안정 후 탐색 시작.
        TimerAction(period=20.0, actions=[explore]),
    ])
