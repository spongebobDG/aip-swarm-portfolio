#!/usr/bin/env python3
"""sim_pose_relay_node — TF에서 차량 위치를 읽어 /fleet/peer_poses로 발행.

시뮬 세션 내에서 실행되어 TF를 직접 조회하고, 중앙 세션의 대시보드가
구독할 수 있도록 TRANSIENT_LOCAL QoS로 PeerPoseArray를 발행한다.

coordinator_node 없이 autonomous 모드에서도 대시보드가 차량 위치를
표시할 수 있게 하기 위해 추가됨.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile, DurabilityPolicy, ReliabilityPolicy, HistoryPolicy,
)
import tf2_ros

from aip_fleet_msgs.msg import PeerPoseArray, PeerPose


class SimPoseRelayNode(Node):
    def __init__(self):
        super().__init__('sim_pose_relay')

        self.declare_parameter('vehicle_ids', ['peer_1', 'peer_2', 'peer_3'])
        self.declare_parameter('publish_hz', 2.0)

        self._vehicle_ids = list(self.get_parameter('vehicle_ids').value)
        hz = float(self.get_parameter('publish_hz').value)

        # TRANSIENT_LOCAL so late-joining central dashboard picks up the latest pose
        _pose_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self._pub = self.create_publisher(PeerPoseArray, '/fleet/peer_poses', _pose_qos)

        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)

        self.create_timer(1.0 / hz, self._publish_poses)
        self.get_logger().info(
            f'sim_pose_relay: publishing {self._vehicle_ids} at {hz:.1f} Hz'
        )

    def _publish_poses(self):
        msg = PeerPoseArray()
        msg.stamp = self.get_clock().now().to_msg()
        for vid in self._vehicle_ids:
            try:
                t = self._tf_buffer.lookup_transform(
                    'map', f'{vid}/base_link', rclpy.time.Time())
                p = PeerPose()
                p.vehicle_id = vid
                p.pose.position.x = t.transform.translation.x
                p.pose.position.y = t.transform.translation.y
                p.pose.position.z = 0.0
                p.pose.orientation = t.transform.rotation
                p.covariance_xy_m = 0.0
                msg.poses.append(p)
            except Exception:
                pass
        if msg.poses:
            self._pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = SimPoseRelayNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
