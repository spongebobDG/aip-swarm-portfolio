# Project Facts

> 목적: 로봇 SW 채용 포트폴리오에서 사용할 수 있는 확인된 사실, 추정, 확인 필요 항목을 분리한다.  
> 기준: 저장소 코드, README/docs, 데모 이미지/GIF, 작업 로그. 실행 환경별 결과는 달라질 수 있으므로 실차 검증은 별도 표시한다.

## 확인된 사실

| 항목 | 내용 | 근거 |
|---|---|---|
| 프로젝트 성격 | ROS2 기반 다중 이동로봇 관제, 상태 집계, 제어 명령, 비전/열화상 연동을 다루는 워크스페이스 | `src/`, `README.md`, `docs/ARCHITECTURE.md` |
| 차량 ID | 최신 문서와 코드의 기준 차량 ID는 `aip1`, `aip2`, `aip3`이며, 구형 문서에는 `main`, `scout_1`, `scout_2` 표현이 남아 있다 | `README.md`, `docs/HANDOFF.md` |
| ROS2 메시지 | `FleetHeartbeat`, `FleetStatus`, `OverrideCommand`, `PerceptionAlert`, `PeerPoseArray` 등 custom msg/srv가 있다 | `src/aip_fleet_msgs/CMakeLists.txt` |
| 상태 집계 | 차량별 heartbeat를 모아 `/fleet/status`로 발행하는 supervisor 코드가 있다 | `src/aip_fleet_supervisor/.../supervisor_node.py` |
| 안전 감시 | `/fleet/status`의 offline 상태를 보고 `/fleet/override` E-Stop을 발행하는 watchdog 코드가 있다 | `src/aip_fleet_supervisor/.../watchdog_node.py` |
| 웹관제 | FastAPI backend와 WebSocket `/ws`, 정적 HTML/JavaScript UI가 있다 | `src/aip_fleet_dashboard/.../dashboard_server.py`, `src/aip_fleet_dashboard/static/index.html` |
| 시뮬레이션 | 2D sim world/vehicle/lidar와 Docker compose 기반 데모 경로가 있다 | `src/aip_fleet_sim/`, `docker/sim/docker-compose.yml` |
| 비전 연동 | Vision Pi HTTP bridge, RGB/thermal topic, thermal alert, central fusion 코드가 있다 | `src/aip_fleet_perception/` |
| 실차 bridge | `aip1` 쪽 ESP32 serial bridge, odom/TF 발행, motor firmware 코드가 있다 | `src/aip_fleet_real/.../serial_bridge.py`, `firmware/main_agv/` |
| 데모 자료 | 웹관제 캡처와 GIF, 면접 복습 PDF가 저장소 산출물로 있다 | `docs/images/`, `docs/videos/`, `output/pdf/` |

## 추정

| 항목 | 추정 내용 | 확인 방법 |
|---|---|---|
| 최신 데모 실행 상태 | Docker sim은 2026-07-06 작업 로그상 실행 검증 기록이 있으나, 현재 PC 상태에서는 재확인이 필요하다 | `docker compose -f docker/sim/docker-compose.yml up -d --build` |
| 실차 bringup | launch/config는 있으나 하드웨어 연결, DDS, 네트워크 상태에 따라 결과가 달라질 수 있다 | 차량 전원/네트워크 연결 후 `ros2 topic list -t` |
| 비전 모델 | YOLOv8 호출 코드는 있으나 fire/smoke 전용 모델과 정확도는 별도 자료가 필요하다 | model path, dataset, validation result 확인 |
| E-Stop end-to-end | dashboard, supervisor, watchdog 경로는 코드로 확인되지만 실제 모터 정지까지는 차량별 검증이 필요하다 | `/fleet/override`, `/<vid>/estop`, `/<vid>/cmd_vel`, 실제 정지 녹화 |

## 확인 필요

- 사용자가 실제로 맡은 범위와 팀원이 맡은 범위의 최종 구분
- 실차 3대 장시간 군집 주행 성공 여부와 증빙 영상
- `aip3` STS3215/custom vehicle driver의 구현 및 실차 검증 상태
- Vision Pi 또는 onboard camera 중 실제 시연에 사용한 camera source
- YOLOv8 모델 파일, 학습 데이터, 현장 정확도
- E-Stop 버튼 클릭부터 실제 차량 정지까지의 녹화 또는 로그
- 제출용 GitHub에 공개해도 되는 내부 IP, 장비명, 팀원 정보 포함 여부

## 면접에서 이렇게 설명

이 프로젝트는 여러 로봇을 ROS2 Topic 계약으로 묶고, 중앙 웹관제에서 상태와 제어 명령, 비전/열화상 데이터를 확인하는 구조를 다룬 팀프로젝트입니다. 저는 전체 코드를 분석해 ROS2 통신, 웹관제, 비전 연동, 서브차량 제어 흐름을 정리하고, 시뮬레이션 기반 데모와 면접용 문서로 설명 가능한 형태로 다듬었습니다. 실차 완전 군집 주행이나 YOLO 성능처럼 증빙이 부족한 부분은 확인 필요로 분리했습니다.

## 근거 파일

- `README.md`
- `PORTFOLIO_KO.md`
- `docs/architecture/ros2-communication.md`
- `docs/architecture/web-dashboard.md`
- `docs/architecture/vision-camera.md`
- `docs/architecture/sub-vehicle-control.md`
- `docs/agent_context/conversation_log.md`
