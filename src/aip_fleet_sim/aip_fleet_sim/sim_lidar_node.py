"""Fake 2D LiDAR for the main vehicle. Ray-casts against the world model
and publishes sensor_msgs/LaserScan on `<ns>/scan`.

Listens to TF for the vehicle's current pose in `map` — no direct
subscription to odom — so it naturally matches whatever the sim_vehicle
integrates.
"""
from __future__ import annotations

import math
import os

import numpy as np
import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from rclpy.duration import Duration
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformListener

from aip_fleet_sim.world import World

_WORLD_REQUIRED = ('size_x', 'size_y', 'origin_x', 'origin_y', 'resolution', 'obstacles')


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


class SimLidarNode(Node):
    def __init__(self) -> None:
        super().__init__('sim_lidar_node')

        pkg_share = get_package_share_directory('aip_fleet_sim')
        self.declare_parameter('vehicle_id', 'aip1')
        self.declare_parameter(
            'world_yaml', os.path.join(pkg_share, 'config', 'world.yaml')
        )
        self.declare_parameter('rate_hz', 10.0)
        self.declare_parameter('range_max', 8.0)
        self.declare_parameter('num_rays', 360)

        self.vid = self.get_parameter('vehicle_id').get_parameter_value().string_value
        world_path = self.get_parameter('world_yaml').get_parameter_value().string_value
        rate = float(self.get_parameter('rate_hz').value)
        self.range_max = float(self.get_parameter('range_max').value)
        self.num_rays = int(self.get_parameter('num_rays').value)

        with open(world_path) as f:
            world_data = yaml.safe_load(f)
        _validate_world_yaml(world_path, world_data)
        w = world_data['world']
        self.world = World(**{k: w[k] for k in
            ('size_x', 'size_y', 'origin_x', 'origin_y', 'resolution', 'obstacles')})

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._pub = self.create_publisher(LaserScan, f'/{self.vid}/scan', 10)

        self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(
            f'[{self.vid}/lidar] {self.num_rays} rays, {self.range_max:.1f} m'
        )

    def _tick(self) -> None:
        try:
            tf = self._tf_buffer.lookup_transform(
                'map', f'{self.vid}/base_link', rclpy.time.Time(),
                timeout=Duration(seconds=0.1),
            )
        except Exception:
            return

        tx = tf.transform.translation.x
        ty = tf.transform.translation.y
        qz = tf.transform.rotation.z
        qw = tf.transform.rotation.w
        yaw = 2.0 * math.atan2(qz, qw)

        angle_min = -math.pi
        angle_increment = (2.0 * math.pi) / self.num_rays
        ranges = np.empty(self.num_rays, dtype=np.float32)
        for i in range(self.num_rays):
            a = yaw + angle_min + i * angle_increment
            d = self.world.raycast(tx, ty, a, self.range_max)
            ranges[i] = d if math.isfinite(d) else self.range_max

        msg = LaserScan()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = f'{self.vid}/base_link'
        msg.angle_min = angle_min
        msg.angle_max = angle_min + angle_increment * (self.num_rays - 1)
        msg.angle_increment = angle_increment
        msg.range_min = 0.05
        msg.range_max = self.range_max
        msg.ranges = ranges.tolist()
        self._pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SimLidarNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
