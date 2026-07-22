---
name: AIP swarm driving project overview
description: High-level architecture of AIP team's SLAM + swarm-driving + thermal-monitoring vehicle system
type: project
---

목표 시스템:
- **메인 AGV** (1대): Raspberry Pi 4B + ROS2 Humble (Docker `my_ros_env`) + YDLIDAR TG15 + 엔코더 달린 DC/서보 모터 → Full SLAM. **IMU 미설치** (2026-06-24 확인). 하단 ToF/범퍼로 충돌 방지. 3~4 DOF 로봇암 + 열상+이미지 센서퓨전(이상고온 탐지). 차체에 가스/유해물질 센서.
- **TurtleBot** (1대): 로보티즈 TurtleBot (모델 미확정 — TurtleBot3 또는 TurtleBot4). Raspberry Pi 4B 탑재. LiDAR 내장, 기성품 그대로 유용. ros2 공식 패키지 사용.
- **자작 SLAM 차량** (1대): Raspberry Pi 4B + LiDAR(모델 미확정) + **STS3215 Feetech 서보 기반 구동부**. 자체 제작 차체. Feetech STS3215 = 직렬 버스 서보 (UART half-duplex), 전용 ROS2 드라이버 필요.
- **중앙 PC**: Ubuntu 22.04 + ROS2 Humble. FastDDS Discovery Server, micro-ROS Agent, Foxglove Bridge, rosbag2, 오버라이드 게이트웨이 담당.
- **네트워크**: 전용 Wi-Fi 공유기 `AIP_FLEET` (192.168.0.0/24), 외부망과 분리, DHCP 예약 고정 IP.

**2026-06-15 하드웨어 구조 변경 결정:**
- UWB 모듈 **전면 배제**: 전 차량에 LiDAR 장착으로 UWB 협력 측위 불필요
- 전 차량 Raspberry Pi 4B 통일: ESP32-S3 Scout 계획 폐기
- 전 차량 독립 SLAM: 기존 peer_1 SLAM + peer_2/3 AMCL 구조 → 실차에서는 전 차량 slam_toolbox
- LiDAR 모델은 차량별로 다름 → 각 차량 세팅 시 개별 설정 필요

설계 결정:
- RMW = FastDDS + Discovery Server (Wi-Fi multicast 회피, Zenoh 스왑 대비).
- 대시보드 = Foxglove Studio + 커스텀 Override/EStop 패널.
- 우선순위 = HW-EStop > 중앙 override > 군집 협조 > 로컬 자율 (twist_mux).
- 확장 훅 = Zenoh RMW 스왑, SROS2, 추가 차량 네임스페이스 비파괴 확장 가능.

**Why:** 전 차량 LiDAR+SLAM으로 UWB 의존성 제거 → 측위 정확도 향상 + 인프라 단순화.
STS3215 서보: 일반 DC 모터 대비 위치·속도·전류 피드백 제공, 네트워크 버스 방식으로 배선 간소화.
**How to apply:** 새 차량 추가 시 `/<vehicle_ns>/heartbeat`, `/<vehicle_ns>/cmd_vel`, `/<vehicle_ns>/override_cmd_vel`, `/<vehicle_ns>/estop` 규약 준수. 네임스페이스: `main`, `scout_N`. Domain ID=42.
차량별 LiDAR 파라미터(scan topic name, frame_id, range 등)는 개별 설정 파일에서 오버라이드.

[[reference_main_agv_ws]] [[project_fleet_vehicle_specs]]
