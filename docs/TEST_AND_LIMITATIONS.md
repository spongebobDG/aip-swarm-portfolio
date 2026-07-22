# Test And Limitations

> 목적: 시연/검증된 범위와 아직 말하면 위험한 범위를 분리한다.

## 검증 또는 산출물 기준으로 확인된 것

| 항목 | 상태 | 근거 |
|---|---|---|
| Docker sim 데모 | 2026-07-06 작업 로그상 실행, 대시보드 캡처/GIF 산출 | `docs/agent_context/conversation_log.md`, `docs/images/`, `docs/videos/` |
| 웹관제 접속 포트 | sim 기준 `http://localhost:18080`, Foxglove bridge `ws://localhost:18765` | `docker/sim/docker-compose.yml`, README |
| 3대 sim 상태 표시 | GIF/캡처와 작업 로그 기준 확인 | `docs/videos/dashboard_demo.gif` |
| ROS2 custom message 생성 | CMakeLists 기준 확인 | `src/aip_fleet_msgs/CMakeLists.txt` |
| supervisor/watchdog 코드 | source 기준 확인 | `src/aip_fleet_supervisor/` |
| dashboard WebSocket bridge | source 기준 확인 | `src/aip_fleet_dashboard/` |
| perception bridge/fusion | source 기준 확인 | `src/aip_fleet_perception/` |
| final PDF | 파일 존재 확인 | `output/pdf/` |

## 추가로 다시 확인할 것

- `http://localhost:18080`에서 `CONNECTED`, map, 3대 상태 표시 확인
- E-Stop 버튼 클릭 후 `/fleet/override`, `/<vid>/estop`, `/<vid>/cmd_vel` 변화 확인
- image/thermal topic과 dashboard 표시 FPS/latency 확인
- 실제 차량 네트워크에서 3대 장시간 운용과 물리 정지 확인

## 현재 브랜치 검증 기록

2026-07-21, `codex/robot-sw-portfolio` 브랜치에서 다시 확인한 결과:

| 검증 | 결과 |
|---|---|
| `docker compose -f docker/sim/docker-compose.yml config` | 통과. `18080:8080`, `18765:8765` 포트 매핑 확인 |
| `docker compose -f docker/sim/docker-compose.yml up -d --build --force-recreate` | 통과. 오래된 컨테이너를 현재 Compose 설정으로 재생성하고 포트 매핑 복구 |
| WSL 내부 `curl http://localhost:18080/` | HTML 응답 확인 |
| `docker logs aip_sim` | `demo_patrol_node`, supervisor, watchdog, dashboard, coordinator, Foxglove bridge, 20개 obstacle world 기동 확인 |
| `/fleet/status` | `aip1`, `aip2`, `aip3` 모두 `healthy: true`, `estop: false`, `offline_vehicle_ids: []` 확인 |
| 컨테이너 `colcon test --packages-select aip_fleet_sim` | 26 tests, 0 errors, 0 failures |
| Ubuntu 22.04 WSL ROS2 환경 | ROS2 Humble, Gazebo 11.10.2, central/Gazebo/real launch `--show-args` 통과 |
| Windows 브라우저 `localhost:18080` | 현재 세션에서는 연결되지 않음. WSL 내부 서비스와 포트는 정상이며 Windows↔WSL localhost forwarding은 추가 확인 필요 |

남은 검증:

- Windows 브라우저에서 실제 지도/차량 이동/버튼 동작을 눈으로 확인
- E-Stop 버튼 클릭 후 ROS2 topic 변화 캡처
- 비전/열화상 frame source와 FPS/latency 확인

## 한계

| 한계 | 이유 | 면접 답변 방향 |
|---|---|---|
| 실차 3대 장시간 군집 주행 미확정 | 증빙 영상/로그가 부족하다 | "시뮬과 통신/관제 구조 중심으로 검증했습니다." |
| `aip3` custom driver 상태 불명확 | launch와 TODO가 함께 존재한다 | "custom vehicle driver는 확인 필요로 분리했습니다." |
| YOLO 성능 검증 부족 | 모델 파일, 데이터셋, 정확도 자료가 없다 | "연동 코드와 thermal alert 흐름 중심으로 설명합니다." |
| E-Stop 물리 정지 검증 부족 | ROS2 명령 경로와 실제 모터 정지는 별도 증빙 필요 | "E-Stop 경로는 코드로 확인했고, 차량별 end-to-end 검증이 필요합니다." |
| dashboard 유지보수성 | 단일 `index.html`에 기능이 많다 | "향후 module 분리와 command schema 문서화를 개선하겠습니다." |
| 문서 드리프트 | `main/scout_*`와 `aip1/aip2/aip3` 표현이 혼재한다 | "최신 기준을 `aip1/aip2/aip3`로 정리했습니다." |
| 현재 PC WSL 브라우저 접속 | WSL 내부 서비스는 정상이나 Windows localhost forwarding을 재확인해야 한다 | "데모 전 Docker 포트와 Windows 브라우저 접속을 사전 점검합니다." |

## 제출 전 체크

- README 링크가 모두 열리는지 확인
- secret 파일이 `git status`에 뜨지 않는지 확인
- `tmp/`, raw frame, local cache가 stage 되지 않는지 확인
- 위험 표현 검색 후 문맥 확인
- 본인이 실제로 한 일과 팀 전체 구현이 섞이지 않았는지 확인
