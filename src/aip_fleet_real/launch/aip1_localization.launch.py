"""aip1 중앙 로컬라이제이션 런치 — 저장맵 + AMCL (SLAM 대체).

aip1 은 차량에 nav2 미설치 → 중앙에서 map_server+amcl 실행(매핑이 중앙 SLAM 이듯).
전제: aip1 base-only 가동(/aip1/scan, aip1/odom→aip1/base_footprint TF) + 저장된 맵.
초기 위치추정: 대시보드 '지도 위치 보정'이 /aip1/initialpose 발행 → AMCL 그 위치로 수렴.

프레임(amcl.yaml): global=map, odom=aip1/odom, base=aip1/base_footprint (frame_prefix 정합).
맵 토픽: /map (공유 분배자 — 다차량 공통). 대시보드 'map'(공용 SLAM맵) 소스. 차량별 포즈는 map→aipN/odom TF.

실행(중앙, 도메인 42 SIMPLE):
    ros2 launch aip_fleet_real aip1_localization.launch.py map:=/home/kde/aip_maps/<맵>.yaml
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import GroupAction, DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, PushRosNamespace


def generate_launch_description():
    pkg_real = get_package_share_directory('aip_fleet_real')
    amcl_yaml = os.path.join(pkg_real, 'config', 'main_agv', 'amcl.yaml')
    namespace = 'aip1'

    map_arg = DeclareLaunchArgument(
        'map', default_value=os.path.expanduser('~/aip_maps/latest_fleet_map.yaml'),
        description='저장된 맵 yaml 경로')
    map_yaml = LaunchConfiguration('map')

    # frame_prefix=aip1/ 정합 static TF 재발행(다중호스트 /tf_static 우회) — 매핑 런치와 동일.
    static_tf_footprint_to_base = Node(
        package='tf2_ros', executable='static_transform_publisher',
        name='tf_base_footprint_to_base_link_devpc',
        arguments=['0', '0', '0.06', '0', '0', '0', 'aip1/base_footprint', 'aip1/base_link'])
    static_tf_base_to_laser = Node(
        package='tf2_ros', executable='static_transform_publisher',
        name='tf_base_link_to_laser_link_devpc',
        arguments=['0', '0', '0.16', '0', '0', '0', 'aip1/base_link', 'aip1/laser_link'])

    # ── 공유 맵 분배자(map_server→/map) + 차량별 amcl(/map 구독) + lifecycle ──
    # map_server 는 fleet-공유 맵 분배자: 절대토픽 /map 발행(네임스페이스 무관).
    # amcl 은 aip1 네임스페이스이나 공유 /map 을 구독 → map→aip1/odom 발행.
    # (다차량 순찰 시 map_server 1개를 공유, 각 차량 amcl 만 추가 — 동일 /map 구독)
    localization = GroupAction([
        PushRosNamespace(namespace),
        Node(
            package='nav2_map_server', executable='map_server', name='map_server',
            output='screen',
            parameters=[{'use_sim_time': False, 'yaml_filename': map_yaml,
                         'frame_id': 'map', 'topic_name': '/map'}]),   # 공유 /map 발행
        Node(
            package='nav2_amcl', executable='amcl', name='amcl',
            output='screen',
            parameters=[amcl_yaml, {'use_sim_time': False}],
            remappings=[('map', '/map')]),                              # 공유 /map 구독
        Node(
            package='nav2_lifecycle_manager', executable='lifecycle_manager',
            name='lifecycle_manager_localization', output='screen',
            parameters=[{'use_sim_time': False, 'autostart': True,
                         'node_names': ['map_server', 'amcl']}]),
    ])

    return LaunchDescription([
        map_arg,
        static_tf_footprint_to_base,
        static_tf_base_to_laser,
        localization,
    ])
