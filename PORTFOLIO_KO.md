# AIP Swarm Workspace 포트폴리오 정리

> 기준일: 2026-07-06  
> 상태: 중앙 웹 관제 + 3대 경량 시뮬레이션 + 안전/수동제어/맵 표시 데모 가능. 실차 완전 군집 자율주행은 아직 미완성.

## 한 줄 소개

ROS2 Humble 기반의 다중 이동로봇 관제/협조 주행 워크스페이스입니다. 저예산 차량 구성에서 시작했지만, 차량별 네임스페이스와 공통 토픽 계약을 유지해 향후 Pi4/Jetson급 피어 차량으로 확장할 수 있게 설계했습니다.

![AIP dashboard overview](docs/images/dashboard_overview_wide.png)

## 현재 데모

![AIP dashboard demo](docs/videos/dashboard_demo.gif)

로컬 실행:

```bash
docker compose -f docker/sim/docker-compose.yml up -d --build
```

브라우저:

- 웹 관제: http://localhost:18080
- Foxglove bridge: ws://localhost:18765

현재 데모에서 확인 가능한 것:

- `aip1`, `aip2`, `aip3` 3대 상태 집계와 heartbeat 기반 online 표시
- `/map_static`, `/aipN/map` 기반 맵 표시와 차량 pose marker
- `demo_patrol_node` 기반 시뮬레이션 전용 자동 주행 표시
- `twist_mux` 우선순위 체인: central override, fleet coordination, autonomy 입력 분리
- watchdog 기반 offline/estop 안전 경로
- 웹 대시보드의 수동 조작, 비상정지, 금지구역, 순찰/커버리지 UI 골격
- 시뮬레이션에서 coordinator가 follower 차량에 `/aipN/coord_cmd_vel`을 발행하는 구조

## 면접관용 상세 문서

| 문서 | 용도 |
|---|---|
| `docs/PROJECT_FACTS.md` | 코드와 자료에서 확인된 사실, 추정, 확인 필요 항목 |
| `docs/WHAT_I_DID.md` | 본인 역할과 팀 전체 구현 분리 |
| `docs/TECH_STACK.md` | 실제 코드에서 확인되는 기술 스택 |
| `docs/TEST_AND_LIMITATIONS.md` | 검증 범위와 한계 |
| `docs/INTERVIEW_EXPLANATION_NOTES.md` | 30초/1분/3분 면접 답변 |
| `docs/portfolio/company-fit-clobot-robotis.md` | 클로봇/로보티즈 공고별 연결 포인트 |

## 구현한 주요 축

### 1. ROS2 통신 계약

- 차량 네임스페이스: `aip1`, `aip2`, `aip3`
- 차량별 기본 토픽: `/<ns>/heartbeat`, `/<ns>/cmd_vel`, `/<ns>/override_cmd_vel`, `/<ns>/estop`, `/<ns>/odom`
- 플릿 전역 토픽: `/fleet/status`, `/fleet/override`, `/fleet/peer_poses`, `/fleet/alerts`, `/fleet/map_ready`
- `FleetHeartbeat`, `FleetStatus`, `OverrideCommand`, `PeerPoseArray` 등 공통 메시지 패키지 구성

### 2. 중앙 관제 대시보드

- FastAPI + WebSocket 기반 단일 웹 관제
- 지도, 차량 상태, 수동 주행, E-Stop, 순찰 경로, 금지구역, 커버리지 UI
- 실차/시뮬 양쪽에서 같은 `/fleet/*` 계약을 보도록 구성

### 3. 안전 체인

우선순위 개념:

```text
HW-EStop > estop_lock > central override > fleet_coord > stuck_escape > autonomy
```

중앙 supervisor/watchdog가 heartbeat lapse를 감지하면 `/<ns>/estop`과 `/<ns>/estop_lock`을 발행해 차량을 정지시키는 구조입니다.

### 4. 확장 가능한 통신 전략

- 현재 ESP32/micro-ROS scout를 염두에 두었지만, 동일 토픽 계약을 유지하면 Pi4/Jetson 차량으로 비파괴 전환 가능
- Wi-Fi multicast 불안정성에 대비해 FastDDS Discovery Server, SIMPLE discovery 전환 기록, 향후 Zenoh/SROS2 전환 여지를 문서화

### 5. 비전/열화상 파이프라인

- RGB/thermal 스트림을 웹 관제에 연결하는 구조 구현
- MLX90640 UART 460800bps/약 8fps 검증 기록
- HW-ISP(camera_ros) 기반 RGB 경로로 CPU 사용률 개선 기록

## 아직 군집이 완성되지 않은 이유

현재 데모는 “군집 시스템의 관제·통신·안전·시뮬 기반”까지입니다. 실차 완전 군집 자율주행이 아직 해결되지 않은 이유는 다음입니다.

1. **각 차량의 독립 위치추정이 아직 완전하지 않음**
   - 목표는 모든 차량이 자기 위치를 독립적으로 알고 협력하는 구조입니다.
   - 현재 저예산 scout는 센서/연산 자원이 제한되어 있고, 실차에서 `/aipN/odom`, TF, 맵 좌표계가 항상 안정적으로 들어오는 상태가 아닙니다.

2. **중앙 coordinator 의존도가 아직 큼**
   - 현재 구조는 중앙 PC가 follower 목표 속도를 계산하는 과도기 구조입니다.
   - 장기 목표인 “각 차량이 동등한 피어로 판단하고 협력”하는 완전 분산 구조는 아직 아닙니다.

3. **실차 네트워크/DDS 안정화가 먼저 필요했음**
   - 5GHz 전환, Discovery Server/SIMPLE discovery, heartbeat flapping, 컨테이너 트래픽 포화 같은 문제를 먼저 해결해야 했습니다.
   - 특히 차량별 Nav2 내부 discovery와 중앙 관제 discovery가 동시에 안정적이어야 군집 실험이 가능합니다.

4. **하드웨어 구성 차이가 큼**
   - `aip1`은 LiDAR/SLAM/Nav2가 가능한 메인 AGV이고, `aip2/aip3`는 예산 제약 scout 성격입니다.
   - 동일 성능 피어 군집을 바로 구성하기보다, 공통 인터페이스를 먼저 맞춘 뒤 하드웨어 업그레이드에 열어둔 상태입니다.

5. **멀티 로봇 자율 순찰 E2E 장시간 검증이 남음**
   - 시뮬/부분 실차 검증은 진행했지만, 3대 동시 자율 순찰을 실차에서 장시간 안정 운용하는 검증은 아직 완료되지 않았습니다.

## 다음 단계

- 실차 기준 `/aip1`, `/aip2`, `/aip3` heartbeat/odom/TF 계약 완전 통일
- 저장맵 + AMCL 운영 모드 실차 검증
- follower 위치추정: 자체 odom/SLAM 또는 카메라/마커 기반 보조 위치추정 안정화
- 3대 동시 순찰/커버리지 E2E 테스트
- 중앙 coordinator 의존도 축소: 차량별 로컬 판단과 충돌 회피 강화
- 시연용 rosbag/MCAP 로그와 장애 복구 시나리오 추가

## 이번 포트폴리오 캡처 산출물

- `docs/images/dashboard_overview_wide.png`
- `docs/images/dashboard_overview.png`
- `docs/videos/dashboard_demo.gif`
- `archive/portfolio-demo-frames/`
