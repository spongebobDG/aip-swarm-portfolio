#!/usr/bin/env python3
"""Run the real central services in one rclpy process.

This avoids the WSL2/FastDDS Discovery Server local-local discovery gap where
freshly launched local participants sometimes fail to discover each other even
though remote vehicle traffic is still visible.
"""
from __future__ import annotations

import math
import os
import threading
import time

from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.executors import MultiThreadedExecutor
import uvicorn

import aip_fleet_dashboard.dashboard_server as dashboard_module
from aip_fleet_dashboard.dashboard_server import DashboardNode, app
from aip_fleet_supervisor.supervisor_node import SupervisorNode
from aip_fleet_supervisor.watchdog_node import WatchdogNode
from udp_status_heartbeat_adapter import UdpStatusHeartbeatAdapter


def _amcl_init_thread(supervisor: SupervisorNode) -> None:
    """AMCL 재초기화: docker restart 후 AMCL이 initialpose를 잃어버리는 문제 자동 복구.

    환경 변수:
      AIP_AMCL_INIT_VEHICLES   쉼표 구분 차량 ID 목록 (기본: 비활성)
                                예) AIP_AMCL_INIT_VEHICLES=aip3
      AIP_AMCL_INIT_DELAY_SEC  중앙 안정화 후 추가 대기 시간 (기본: 8.0)
      AIP_AMCL_INIT_POSE_AIP3  x,y,yaw_deg (기본: 0.0,0.0,0.0)
    """
    vehicles_str = os.environ.get('AIP_AMCL_INIT_VEHICLES', '').strip()
    if not vehicles_str or vehicles_str.lower() in ('0', 'none', 'false'):
        return

    from geometry_msgs.msg import PoseWithCovarianceStamped  # noqa: PLC0415

    vehicles = [v.strip() for v in vehicles_str.split(',') if v.strip()]
    delay = float(os.environ.get('AIP_AMCL_INIT_DELAY_SEC', '8.0'))
    supervisor.get_logger().info(
        f'[AMCL init] {delay:.1f}s 후 initialpose 발행 대상: {vehicles}'
    )
    time.sleep(delay)

    for vid in vehicles:
        pose_str = os.environ.get(f'AIP_AMCL_INIT_POSE_{vid.upper()}', '0.0,0.0,0.0')
        try:
            parts = pose_str.split(',')
            x, y = float(parts[0]), float(parts[1])
            yaw = math.radians(float(parts[2])) if len(parts) > 2 else 0.0
        except (ValueError, IndexError):
            x, y, yaw = 0.0, 0.0, 0.0

        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp = supervisor.get_clock().now().to_msg()
        msg.pose.pose.position.x = x
        msg.pose.pose.position.y = y
        msg.pose.pose.orientation.z = math.sin(yaw / 2.0)
        msg.pose.pose.orientation.w = math.cos(yaw / 2.0)
        # 넓은 초기 공분산: AMCL이 LiDAR 스캔으로 자체 수렴하도록 허용
        msg.pose.covariance[0]  = 0.5           # x 분산 (0.7m)
        msg.pose.covariance[7]  = 0.5           # y 분산 (0.7m)
        msg.pose.covariance[35] = (math.pi / 6.0) ** 2  # yaw 분산 (±30°)

        pub = supervisor.create_publisher(PoseWithCovarianceStamped, f'/{vid}/initialpose', 10)
        time.sleep(0.5)  # publisher discovery 대기
        pub.publish(msg)
        supervisor.get_logger().info(
            f'[AMCL init] /{vid}/initialpose 발행 완료  '
            f'x={x:.2f} y={y:.2f} yaw={math.degrees(yaw):.1f}°'
        )


def main() -> None:
    supervisor_params = (
        f'{get_package_share_directory("aip_fleet_bringup")}/config/supervisor.yaml'
    )
    rclpy.init(args=['--ros-args', '--params-file', supervisor_params])

    supervisor = SupervisorNode()
    heartbeat_adapter = None
    watchdog = None
    dashboard_node = None

    executor = MultiThreadedExecutor()
    executor.add_node(supervisor)
    if os.environ.get('AIP_UDP_HEARTBEAT_ADAPTER_ENABLE', '1').strip().lower() not in (
        '0', 'false', 'no', 'off',
    ):
        heartbeat_adapter = UdpStatusHeartbeatAdapter()
        executor.add_node(heartbeat_adapter)

    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()
    threading.Thread(target=_amcl_init_thread, args=(supervisor,), daemon=True).start()

    try:
        stabilize_sec = float(os.environ.get('AIP_CENTRAL_STABILIZE_SEC', '14.0'))
        supervisor.get_logger().info(
            f'Waiting {stabilize_sec:.1f}s before starting watchdog/dashboard endpoints'
        )
        time.sleep(stabilize_sec)

        watchdog = WatchdogNode()
        dashboard_node = DashboardNode()
        dashboard_module._ros_node = dashboard_node
        executor.add_node(watchdog)
        executor.add_node(dashboard_node)

        uvicorn.run(app, host='0.0.0.0', port=8080, log_level='warning')
    finally:
        executor.shutdown()
        supervisor.destroy_node()
        if heartbeat_adapter is not None:
            heartbeat_adapter.destroy_node()
        if watchdog is not None:
            watchdog.destroy_node()
        if dashboard_node is not None:
            dashboard_node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
