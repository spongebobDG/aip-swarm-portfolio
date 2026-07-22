#!/usr/bin/env python3
"""TurtleBot3 Burger 시뮬 (Gazebo Classic) — 실차 aip2 파이프라인 검증용.

실차 turtlebot3.launch.py 의 하드웨어 bringup 부분만 Gazebo 스폰으로 교체하고,
그 위의 SLAM→Nav2→twist_mux→patrol 스택은 실차와 동일하게 돌린다(use_sim_time:=true).
sim↔real drift 를 최소화하기 위해 twist_mux/patrol 은 재사용하고, slam/nav2 는
frame(odom/base_footprint) + use_sim_time 만 바꾼 시뮬 사본 config 를 쓴다.

⚠️ TB3 gazebo plugin(diff_drive/lidar/imu)은 turtlebot3_burger.urdf 가 아니라
   models/turtlebot3_burger/model.sdf 에 있다. 따라서:
   - robot_state_publisher 는 urdf 로 TF(base_footprint→base_link→base_scan) 발행
   - gazebo 스폰은 plugin 포함 model.sdf(-file)로 → /aip2/scan, /aip2/odom, odom TF
⚠️ Nav2 네임스페이스: navigation_launch.py 는 namespace 를 RewriteYaml root_key 로만
   쓰므로 PushRosNamespace 로 직접 감싸야 노드가 /aip2/* 에 뜨고 params 가 매칭된다.
⚠️ TF 는 글로벌 /tf 로 통일한다(SetRemap('/tf','/tf')). gazebo plugin 은 odom→base_footprint
   TF 를 글로벌 /tf 에 발행하는데, navigation_launch 는 ('/tf','tf') remap + PushRosNamespace
   로 /aip2/tf 를 보게 되어 불일치 → 단독 로봇이므로 nav2/slam 의 tf 를 /tf 로 고정.

전제: ros-humble-turtlebot3-gazebo 설치, TURTLEBOT3_MODEL=burger.
환경: `source aip_env.sh sim` (Simple Discovery, Discovery Server 미사용).

사용:
  export TURTLEBOT3_MODEL=burger
  ros2 launch aip_fleet_real turtlebot3_sim.launch.py with_patrol:=true
  ros2 launch aip_fleet_real turtlebot3_sim.launch.py gui:=false   # headless
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, GroupAction,
                            IncludeLaunchDescription, TimerAction)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node, PushRosNamespace, SetRemap
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_real = get_package_share_directory('aip_fleet_real')
    cfg_dir = os.path.join(pkg_real, 'config', 'turtlebot3')
    slam_yaml = os.path.join(cfg_dir, 'slam_toolbox_sim.yaml')
    nav2_yaml = os.path.join(cfg_dir, 'nav2_sim.yaml')
    twist_mux_yaml = os.path.join(cfg_dir, 'twist_mux.yaml')   # 실차와 동일
    patrol_yaml = os.path.join(cfg_dir, 'patrol_sim.yaml')

    namespace = 'aip2'
    with_patrol = LaunchConfiguration('with_patrol')
    gui = LaunchConfiguration('gui')
    spawn_x = LaunchConfiguration('spawn_x')
    spawn_y = LaunchConfiguration('spawn_y')

    declare_patrol = DeclareLaunchArgument(
        'with_patrol', default_value='false',
        description='순찰 미션 자동 시작(patrol_node). 좌표는 config/turtlebot3/patrol_sim.yaml')
    declare_gui = DeclareLaunchArgument(
        'gui', default_value='true', description='gzclient GUI 실행(headless 면 false)')
    declare_x = DeclareLaunchArgument('spawn_x', default_value='0.0')
    declare_y = DeclareLaunchArgument('spawn_y', default_value='0.0')

    tb3_gazebo = get_package_share_directory('turtlebot3_gazebo')

    # ── Gazebo Classic + turtlebot3_world ───────────────────────────────────
    world = os.path.join(tb3_gazebo, 'worlds', 'turtlebot3_world.world')
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('gazebo_ros'), 'launch', 'gazebo.launch.py')),
        launch_arguments={'world': world, 'gui': gui, 'verbose': 'false'}.items(),
    )

    # ── robot_state_publisher (urdf → TF) + spawn (model.sdf → plugin) ──────
    urdf = os.path.join(tb3_gazebo, 'urdf', 'turtlebot3_burger.urdf')
    with open(urdf) as f:
        robot_desc = f.read()
    model_sdf = os.path.join(
        tb3_gazebo, 'models', 'turtlebot3_burger', 'model.sdf')

    rsp = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        namespace=namespace,
        output='screen',
        parameters=[{'robot_description': robot_desc, 'use_sim_time': True}],
    )
    # plugin 포함 model.sdf 를 -file 로 스폰. -robot_namespace 로 plugin 토픽을
    # /aip2/* 에 매핑(scan/odom/cmd_vel). odom→base_footprint TF 는 글로벌 /tf.
    spawn = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        output='screen',
        arguments=[
            '-entity', namespace,
            '-file', model_sdf,
            '-robot_namespace', namespace,
            '-x', spawn_x, '-y', spawn_y, '-z', '0.01',
        ],
    )

    # ── slam_toolbox (sim) — TF 는 글로벌 /tf ───────────────────────────────
    slam = GroupAction([
        PushRosNamespace(namespace),
        SetRemap('/tf', '/tf'),
        SetRemap('/tf_static', '/tf_static'),
        Node(
            package='slam_toolbox',
            executable='async_slam_toolbox_node',
            name='slam_toolbox',
            output='screen',
            parameters=[slam_yaml, {'use_sim_time': True}],
        ),
    ])

    # ── Nav2 navigation (sim) ───────────────────────────────────────────────
    # PushRosNamespace 로 노드를 /aip2/* 에 배치(navigation_launch 는 namespace 를
    # 노드에 적용하지 않음). namespace 인자는 RewriteYaml root_key 로 params nest.
    # SetRemap('/tf','/tf'): navigation_launch 의 ('/tf','tf') 를 눌러 글로벌 /tf 유지.
    # SetRemap(cmd_vel→autonomy_cmd_vel): 최종 nav2 속도 출력 → twist_mux 입력.
    nav2 = GroupAction([
        PushRosNamespace(namespace),
        SetRemap('/tf', '/tf'),
        SetRemap('/tf_static', '/tf_static'),
        SetRemap('cmd_vel', 'autonomy_cmd_vel'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(PathJoinSubstitution([
                FindPackageShare('nav2_bringup'),
                'launch', 'navigation_launch.py'])),
            launch_arguments={
                'namespace': namespace,
                'use_sim_time': 'true',
                'autostart': 'true',
                'params_file': nav2_yaml,
            }.items(),
        ),
    ])

    # ── twist_mux (실차 config 재사용) ──────────────────────────────────────
    twist_mux = GroupAction([
        PushRosNamespace(namespace),
        Node(
            package='twist_mux',
            executable='twist_mux',
            name='twist_mux',
            output='screen',
            parameters=[twist_mux_yaml, {'use_sim_time': True}],
            remappings=[('cmd_vel_out', 'cmd_vel')],
        ),
    ])

    # ── (옵션) 순찰 미션 ─────────────────────────────────────────────────────
    patrol = Node(
        condition=IfCondition(with_patrol),
        package='aip_fleet_autonomous',
        executable='patrol_node',
        name='patrol_node',
        namespace=namespace,
        output='screen',
        parameters=[patrol_yaml, {'use_sim_time': True}],
        remappings=[('/map_static', '/map')],   # slam_toolbox → absolute /map
    )

    return LaunchDescription([
        declare_patrol,
        declare_gui,
        declare_x,
        declare_y,
        gazebo,
        rsp,
        TimerAction(period=5.0, actions=[spawn]),
        TimerAction(period=8.0, actions=[slam, twist_mux]),
        TimerAction(period=10.0, actions=[nav2]),
        TimerAction(period=11.0, actions=[patrol]),
    ])
