#!/usr/bin/env python3
"""scenario_manager_node.py — 시뮬 시나리오 상태 관리 노드.

시나리오 전환 → sim_thermal_node 에 현재 활성 열원 목록 발행.

시나리오 전환 방법 (CLI):
  ros2 topic pub --once /sim/set_scenario std_msgs/String '{data: FIRE}'
  ros2 topic pub --once /sim/set_scenario std_msgs/String '{data: NORMAL}'

지원 시나리오:
  NORMAL      — 배경 온도만 (25°C)
  OVERHEATING — 전기 패널 과열 (65°C)
  PREFIRE     — 화재 전조 (90+95°C)
  FIRE        — 화재 발생 (200+160°C)
  PROGRESSIVE — 점진 온도 상승 (30→200°C)
  MULTI_HAZARD — 다중 열원

발행:
  /sim/active_scenario   std_msgs/String       (현재 시나리오명)
  /sim/heat_sources      std_msgs/Float32MultiArray
                         [x, y, z, temp_c, radius_m] × N (flat list)
"""
from __future__ import annotations

import math
import os

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray, String

FIELDS = 5  # x, y, z, temp_c, radius_m per heat source


class ScenarioManagerNode(Node):
    def __init__(self) -> None:
        super().__init__('scenario_manager')

        self.declare_parameter('config_file', '')
        self.declare_parameter('initial_scenario', 'NORMAL')
        self.declare_parameter('publish_hz', 2.0)

        cfg_file = self.get_parameter('config_file').value
        if not cfg_file:
            share = get_package_share_directory('aip_fleet_gazebo')
            cfg_file = os.path.join(share, 'config', 'heat_sources.yaml')

        with open(cfg_file) as f:
            self._cfg = yaml.safe_load(f)

        self._sources  = self._cfg['heat_sources']
        self._physics  = self._cfg['physics']
        self._scenario = self.get_parameter('initial_scenario').value
        self._prog_temp: dict[str, float] = {}   # PROGRESSIVE 현재 온도
        self._prog_start: dict[str, float] = {}  # PROGRESSIVE 시작 시각

        self.create_subscription(String, '/sim/set_scenario', self._cb_set, 10)
        self._pub_scenario = self.create_publisher(String, '/sim/active_scenario', 10)
        self._pub_sources  = self.create_publisher(
            Float32MultiArray, '/sim/heat_sources', 10)

        hz = self.get_parameter('publish_hz').value
        self.create_timer(1.0 / hz, self._publish)
        self.get_logger().info(
            f'scenario_manager ready — initial={self._scenario}')
        self.get_logger().info(
            '전환: ros2 topic pub --once /sim/set_scenario std_msgs/String \'{data: FIRE}\'')

    # ── 시나리오 전환 ──────────────────────────────────────────────────────
    def _cb_set(self, msg: String) -> None:
        name = msg.data.strip().upper()
        valid = list(self._cfg['scenarios'].keys())
        if name not in valid:
            self.get_logger().warn(f'알 수 없는 시나리오: {name}  (유효: {valid})')
            return
        self._scenario = name
        self._prog_temp.clear()
        self._prog_start.clear()
        self.get_logger().info(
            f'시나리오 전환 → {name}: '
            f'{self._cfg["scenarios"][name]["description"]}')

    # ── 현재 활성 열원 온도 계산 ───────────────────────────────────────────
    def _active_sources(self) -> list[dict]:
        now = self.get_clock().now().nanoseconds * 1e-9
        result = []
        for sid, src in self._sources.items():
            scen_temps = src.get('scenarios', {})
            if self._scenario not in scen_temps:
                continue

            base_temp = float(scen_temps[self._scenario])

            if self._scenario == 'PROGRESSIVE':
                if sid not in self._prog_start:
                    self._prog_start[sid] = now
                    self._prog_temp[sid]  = base_temp
                elapsed  = now - self._prog_start[sid]
                rate     = self._physics.get('progressive_rate_c_per_s', 1.0)
                cur_temp = min(200.0, base_temp + elapsed * rate)
                self._prog_temp[sid] = cur_temp
                temp = cur_temp
            else:
                temp = base_temp

            result.append({
                'position': src['position'],
                'temp_c':   temp,
                'radius_m': src['radius_m'],
            })
        return result

    # ── 발행 ───────────────────────────────────────────────────────────────
    def _publish(self) -> None:
        self._pub_scenario.publish(String(data=self._scenario))

        sources = self._active_sources()
        flat: list[float] = []
        for s in sources:
            flat.extend(s['position'])   # x, y, z
            flat.append(s['temp_c'])
            flat.append(s['radius_m'])

        msg = Float32MultiArray()
        msg.data = flat
        self._pub_sources.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ScenarioManagerNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
