---
name: project_fleet_vehicle_specs
description: 실 차량 3대 하드웨어 스펙 및 소프트웨어 통합 요구사항 (2026-06-15 확정)
metadata:
  type: project
---

# 플릿 차량 스펙 (2026-06-15 확정)

## 공통 사항
- 컴퓨팅: **Raspberry Pi 4B** (전 차량 동일)
- OS: Ubuntu 22.04 + ROS2 Humble
- 측위: **LiDAR + slam_toolbox** 독립 실행 (차량별 LiDAR 모델 상이 → 개별 파라미터 설정)
- **UWB 모듈 없음** — 전면 배제 결정 (2026-06-15)

## 차량 1 — 메인 AGV (`main`)
- Pi4B + YDLIDAR TG15 + 인코더 DC/서보모터 (휠베이스 290mm, 차체 300×230mm)
- **IMU 미설치** (2026-06-24 확인 — 초기 계획과 다름)
- 3~4 DOF 로봇암 + 열상 + 가스/유해물질 센서
- Nav2: footprint 300×230mm, inflation_radius 0.30m (실차) / 0.35m (시뮬)
- ROS2 워크스페이스: `my_ros_env:/root/colcon_ws` (다른 팀원 관할 — 수정 금지)

## 차량 2 — TurtleBot3 (`aip2` 또는 미정)
- 제조사: **로보티즈(Robotis)**
- 모델: **TurtleBot3 (TB3)** ← 확정 (2026-06-15)
- 컴퓨팅: Raspberry Pi 4B
- **LiDAR: LDS-03** ← 확정 (2026-06-15)
  - 360° 레이저 거리 센서
  - ROS2 드라이버: `turtlebot3_bringup` 내장 (ld08_driver 또는 hls_lfcd_lds_driver)
  - scan topic: `/scan` (네임스페이스 리매핑 필요)
- 구동부: 기성품 그대로 유용 (DYNAMIXEL 서보 내장)
- ROS2 지원: `ros-humble-turtlebot3*` 공식 패키지
- 세부 모델: **Burger** ← 확정 (2026-06-15)
  - 환경변수: `TURTLEBOT3_MODEL=burger`
  - 차체: 138×178×192mm, 무게 1kg
  - 구동: DYNAMIXEL XL430-W250 × 2
  - 휠 간격(wheel separation): 160mm → axle_y = 0.080m
  - 휠 반경: 33mm → wheel_r = 0.033m
  - 최대 선속도: 0.22 m/s / 최대 각속도: 2.84 rad/s
  - footprint 반경(근사): ~0.105m (외접원 sqrt(69²+89²)mm)
- **통합 주의사항**: 기본 토픽(`/cmd_vel`, `/odom`, `/scan`)을 AIP 네임스페이스(`/<ns>/cmd_vel` 등)로 리매핑 필요

## 차량 3 — 자작 SLAM 차량 (`aip3` 또는 미정)
- 자작 차체
- 컴퓨팅: Raspberry Pi 4B
- LiDAR: **YDLIDAR X4 PRO** ← 확정 (2026-06-18)
  - 360°, 최대 10m, USB 연결
  - ROS2 드라이버: `ros-humble-ydlidar-ros2-driver`
  - scan frequency: ~8 Hz, baudrate: 128000
- 구동부: **Feetech STS3215 서보** (UART half-duplex 직렬 버스)
  - 위치/속도/전류 피드백 내장
  - 네트워크 버스 방식 배선 (멀티 서보 데이지체인)
  - ROS2 드라이버 옵션:
    - `feetech_ros2` (커뮤니티)
    - Waveshare 드라이버 보드 + 커스텀 노드
    - ros2_control + hardware_interface 구현 (권장)
  - **통합 미완료** — 드라이버 선정 및 ros2_control 연동 필요

## 실차 전환 시 공통 작업 목록
1. `use_sim_time: true` → `false` 일괄 변경 (nav2_full.yaml 등 16곳)
2. 차량별 LiDAR launch 파라미터 (scan topic, frame_id, range 등) 개별 설정
3. TurtleBot3 네임스페이스 리매핑 설정 (`/cmd_vel` → `/<ns>/cmd_vel` 등)
4. STS3215 ROS2 드라이버 선정 + ros2_control 연동
5. 하드웨어 bringup launch 파일 작성 (per 차량)
6. 전 차량 독립 slam_toolbox 실행 → 멀티 SLAM 맵 공유 전략 결정
7. UWB 관련 노드/파라미터 실차 launch에서 미포함 확인

**Why:** UWB 배제로 인프라 단순화, 전 차량 LiDAR 장착으로 측위 자체 해결.
STS3215 선택은 피드백 내장 + 버스 배선 단순화 장점.
TurtleBot3 + LDS-03 조합은 공식 ROS2 패키지 지원으로 드라이버 작업 불필요.
**How to apply:** 실차 전환 세션에서 이 목록을 체크리스트로 활용.
자작 차량 LiDAR 모델 확정 시 이 파일 차량 3 섹션에 추가.

[[project_aip_swarm]]
