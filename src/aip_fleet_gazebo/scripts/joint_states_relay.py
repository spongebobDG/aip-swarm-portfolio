#!/usr/bin/env python3
"""joint_states_relay.py — JSB→RSP QoS 불일치 해결 릴레이.

JSB(publisher): RELIABLE + TRANSIENT_LOCAL  → RSP(subscriber): BEST_EFFORT + VOLATILE
QoS 불일치로 RSP가 30Hz 발행 중 1.25Hz만 수신 → 바퀴/암 TF 시각화 지연.

이 노드가 RELIABLE로 JSB를 구독(드롭 없음) → 10Hz RELIABLE로 재발행
→ RSP가 BEST_EFFORT로 구독해도 10Hz에서는 드롭율 극히 낮음.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy,
)
from sensor_msgs.msg import JointState

_SUB_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)
_PUB_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


class JointStatesRelay(Node):
    def __init__(self) -> None:
        super().__init__('joint_states_relay')
        self._latest: JointState | None = None
        self._pub = self.create_publisher(JointState, 'joint_states_rsp', _PUB_QOS)
        self._sub = self.create_subscription(
            JointState, 'joint_states', self._cb, _SUB_QOS,
        )
        self.create_timer(0.05, self._timer_cb)  # 20 Hz (EKF odom->base_link 와 동기)

    def _cb(self, msg: JointState) -> None:
        self._latest = msg

    def _timer_cb(self) -> None:
        if self._latest is not None:
            # 타임스탬프를 현재 sim_time으로 갱신:
            # RSP는 이 stamp로 TF를 발행하므로 EKF(body) TF와 동일 시점이 되어
            # RViz에서 바퀴 프레임이 본체와 동기화됨.
            self._latest.header.stamp = self.get_clock().now().to_msg()
            self._pub.publish(self._latest)


def main() -> None:
    rclpy.init()
    node = JointStatesRelay()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
