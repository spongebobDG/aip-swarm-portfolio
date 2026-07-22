"""Publishes the shared /map occupancy grid and the static TFs from `map`
to each vehicle's `<ns>/odom` frame (so every vehicle spawns at its
configured pose in the world)."""
from __future__ import annotations

import math
import os
from typing import Dict

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from std_msgs.msg import Bool
from tf2_ros import StaticTransformBroadcaster

from aip_fleet_sim.world import World

_WORLD_REQUIRED = ('size_x', 'size_y', 'origin_x', 'origin_y', 'resolution', 'obstacles')
_VEHICLE_REQUIRED = ('initial_x', 'initial_y', 'initial_theta')


def _validate_world_yaml(path: str, data: dict) -> None:
    """M4: Raise ValueError for malformed world YAML so bad paths fail cleanly."""
    if not isinstance(data, dict) or 'world' not in data:
        raise ValueError(f"{path}: expected top-level 'world' mapping")
    w = data['world']
    missing = [k for k in _WORLD_REQUIRED if k not in w]
    if missing:
        raise ValueError(f"{path}: missing keys in 'world': {missing}")
    for key in ('size_x', 'size_y', 'resolution'):
        if float(w[key]) <= 0:
            raise ValueError(f"{path}: 'world.{key}' must be positive, got {w[key]}")
    if not isinstance(w['obstacles'], list):
        raise ValueError(f"{path}: 'world.obstacles' must be a list")
    for i, obs in enumerate(w['obstacles']):
        if not isinstance(obs, (list, tuple)) or len(obs) != 4:
            raise ValueError(f"{path}: obstacles[{i}] must be [x_min, y_min, x_max, y_max]")


def _validate_vehicles_yaml(path: str, data: dict) -> None:
    """M4: Raise ValueError for malformed vehicles YAML."""
    if not isinstance(data, dict) or 'vehicles' not in data:
        raise ValueError(f"{path}: expected top-level 'vehicles' mapping")
    vehicles = data['vehicles']
    if not isinstance(vehicles, dict) or not vehicles:
        raise ValueError(f"{path}: 'vehicles' must be a non-empty mapping")
    for vid, cfg in vehicles.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"{path}: vehicle '{vid}' must be a mapping")
        missing = [k for k in _VEHICLE_REQUIRED if k not in cfg]
        if missing:
            raise ValueError(f"{path}: vehicle '{vid}' missing keys: {missing}")


def _yaw_to_quat(theta: float):
    return (0.0, 0.0, math.sin(theta / 2.0), math.cos(theta / 2.0))


class SimWorldNode(Node):
    def __init__(self) -> None:
        super().__init__('sim_world_node')

        pkg_share = get_package_share_directory('aip_fleet_sim')
        self.declare_parameter(
            'world_yaml', os.path.join(pkg_share, 'config', 'world.yaml')
        )
        self.declare_parameter(
            'vehicles_yaml', os.path.join(pkg_share, 'config', 'vehicles.yaml')
        )
        world_path = self.get_parameter('world_yaml').get_parameter_value().string_value
        vehicles_path = self.get_parameter('vehicles_yaml').get_parameter_value().string_value

        with open(world_path) as f:
            world_data = yaml.safe_load(f)
        _validate_world_yaml(world_path, world_data)
        w = world_data['world']

        with open(vehicles_path) as f:
            vehicles_data = yaml.safe_load(f)
        _validate_vehicles_yaml(vehicles_path, vehicles_data)
        vehicles: Dict = vehicles_data['vehicles']

        self.world = World(**{k: w[k] for k in
            ('size_x', 'size_y', 'origin_x', 'origin_y', 'resolution', 'obstacles')})

        # Publish the shared map on both the canonical /map topic and the
        # dashboard's current per-vehicle map aliases used by the web UI.
        latched_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        map_topics = ['/map', '/map_static']
        for vid in vehicles:
            map_topics.extend([f'/{vid}/map', f'/{vid}/dashboard/map'])
        self._map_pubs = [
            self.create_publisher(OccupancyGrid, topic, latched_qos)
            for topic in map_topics
        ]
        self._map_ready_pub = self.create_publisher(Bool, '/fleet/map_ready', latched_qos)

        self._static_tf = StaticTransformBroadcaster(self)
        self._publish_map()
        self._publish_map_ready()
        self.create_timer(2.0, self._publish_map)
        self.create_timer(2.0, self._publish_map_ready)
        self._publish_static_tfs(vehicles)

        self.get_logger().info(
            f'World published ({self.world.size_x:.1f}×{self.world.size_y:.1f} m, '
            f'{len(self.world.obstacles)} obstacles). {len(vehicles)} vehicles spawned.'
        )

    def _publish_map(self) -> None:
        grid = self.world.to_occupancy_grid()
        msg = OccupancyGrid()
        msg.header.frame_id = 'map'
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.info.resolution = self.world.resolution
        msg.info.width = grid.shape[1]
        msg.info.height = grid.shape[0]
        msg.info.origin.position.x = self.world.origin_x
        msg.info.origin.position.y = self.world.origin_y
        msg.info.origin.orientation.w = 1.0
        msg.data = grid.flatten().tolist()
        for pub in self._map_pubs:
            pub.publish(msg)

    def _publish_map_ready(self) -> None:
        self._map_ready_pub.publish(Bool(data=True))

    def _publish_static_tfs(self, vehicles: Dict) -> None:
        tfs = []
        for vid, cfg in vehicles.items():
            t = TransformStamped()
            t.header.stamp = self.get_clock().now().to_msg()
            t.header.frame_id = 'map'
            t.child_frame_id = f'{vid}/odom'
            t.transform.translation.x = float(cfg.get('initial_x', 0.0))
            t.transform.translation.y = float(cfg.get('initial_y', 0.0))
            qx, qy, qz, qw = _yaw_to_quat(float(cfg.get('initial_theta', 0.0)))
            t.transform.rotation.x = qx
            t.transform.rotation.y = qy
            t.transform.rotation.z = qz
            t.transform.rotation.w = qw
            tfs.append(t)
        self._static_tf.sendTransform(tfs)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SimWorldNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
