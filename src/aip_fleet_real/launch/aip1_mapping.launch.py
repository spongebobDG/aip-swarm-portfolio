"""aip1 중앙 SLAM 매핑 전용 런치 (Nav2 없이).

aip1 은 차량에 slam_toolbox/nav2 미설치 → 자율연산은 중앙에서 실행하는 설계.
main_agv.launch.py 에서 'static TF 재발행 + slam_toolbox(mapping)' 만 추출했다.
순찰용 Nav2 는 제외 — 매핑 단계엔 teleop 으로 주행하므로 불필요(중앙 부하 절감).

전제: aip1 base-only 가동 중(/aip1/scan, odom→base_footprint TF 발행).
실행(중앙, 도메인 42 SIMPLE):
    ros2 launch src/aip_fleet_real/launch/aip1_mapping.launch.py
맵 저장:
    ros2 service call /aip1/slam_toolbox/save_map slam_toolbox/srv/SaveMap \
        "{name: {data: '/home/kde/aip_maps/aip1_map'}}"
    # serialized(재개용): /aip1/slam_toolbox/serialize_map
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import GroupAction
from launch_ros.actions import Node, PushRosNamespace, SetRemap


def generate_launch_description():
    pkg_real = get_package_share_directory('aip_fleet_real')
    slam_yaml = os.path.join(pkg_real, 'config', 'main_agv', 'slam_toolbox.yaml')
    namespace = 'aip1'

    # ── Static TF 재발행 (dev PC) — FastDDS TRANSIENT_LOCAL /tf_static 다중호스트 미전달 우회.
    # frame_prefix=aip1/ 와 정합. (RSP 가 /tf_static 으로도 발행하나 다중호스트 미전달 우회용 재발행.)
    static_tf_footprint_to_base = Node(
        package='tf2_ros', executable='static_transform_publisher',
        name='tf_base_footprint_to_base_link_devpc',
        arguments=['0', '0', '0.06', '0', '0', '0', 'aip1/base_footprint', 'aip1/base_link'])
    static_tf_base_to_laser = Node(
        package='tf2_ros', executable='static_transform_publisher',
        name='tf_base_link_to_laser_link_devpc',
        arguments=['0', '0', '0.16', '0', '0', '0', 'aip1/base_link', 'aip1/laser_link'])

    # ── scan_deskew — 회전/주행 중 스캔 모션 왜곡 보정 (+무효점 정리).
    # /aip1/scan(+odom) → /aip1/scan_deskewed. slam scan_topic 이 이 토픽 구독.
    scan_deskew = Node(
        package='aip_fleet_real',
        executable='scan_deskew_node',
        name='scan_deskew',
        output='screen',
        parameters=[{'scan_in': '/aip1/scan', 'scan_out': '/aip1/scan_deskewed',
                     'odom_topic': '/aip1/odom'}],
    )

    # ── slam_toolbox (online async mapping) — /aip1/scan_deskewed → /aip1/map + map→odom TF.
    slam = GroupAction([
        PushRosNamespace(namespace),
        SetRemap('/tf', '/tf'),
        SetRemap('/tf_static', '/tf_static'),
        Node(
            package='slam_toolbox',
            executable='async_slam_toolbox_node',
            name='slam_toolbox',
            output='screen',
            parameters=[slam_yaml, {'use_sim_time': False}],
        ),
    ])

    return LaunchDescription([
        static_tf_footprint_to_base,
        static_tf_base_to_laser,
        scan_deskew,
        slam,
    ])
