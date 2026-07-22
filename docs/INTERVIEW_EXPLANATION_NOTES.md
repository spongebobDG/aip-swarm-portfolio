# Interview Explanation Notes

> 목적: 로봇 SW 신입 면접에서 바로 말할 수 있는 프로젝트 설명을 정리한다.

## 30초 소개

산업감시로봇 팀프로젝트에서 ROS2 기반 다중 차량 관제 구조를 정리한 포트폴리오입니다. 차량별 heartbeat와 `cmd_vel`, 중앙 `/fleet/status`, `/fleet/override`, 웹관제 WebSocket, RGB/열화상 alert 흐름을 코드 기준으로 분석하고 문서화했습니다. 실차 완전 군집 주행처럼 증빙이 부족한 내용은 확인 필요로 분리했고, 현재는 시뮬레이션 데모와 구조 설명에 초점을 맞췄습니다.

## 1분 자기소개 초안

저는 ROS2 기반 산업감시로봇 팀프로젝트를 통해 로봇 상태와 제어 명령, 센서 데이터를 하나의 관제 흐름으로 묶는 경험을 했습니다. 프로젝트에서 제가 강조할 수 있는 부분은 개별 알고리즘을 모두 직접 만들었다는 것이 아니라, 여러 패키지와 Topic, WebSocket dashboard, 비전/열화상 연동, 서브차량 제어 흐름을 분석하고 면접에서 설명 가능한 형태로 정리한 점입니다. 로봇 응용 SW 직무에서 중요한 것은 실제 로봇과 사용자 인터페이스 사이의 데이터 흐름을 안정적으로 이해하는 것이라고 생각해서, 확인된 기능과 한계를 분리해 포트폴리오를 준비했습니다.

## 3분 프로젝트 설명 구조

1. 문제: 여러 로봇의 상태, 지도, 제어, 비전 데이터를 중앙에서 확인해야 했다.
2. 구조: 차량은 ROS2 Topic으로 heartbeat/odom/scan/image를 발행하고, 중앙 node가 `/fleet/status`, `/fleet/alerts`, `/fleet/override`로 묶는다.
3. 웹관제: `dashboard_server.py`가 ROS2와 WebSocket 사이를 중계하고, browser는 JSON/base64 image를 표시한다.
4. 제어: 사용자 override, coordinator, autonomy 명령은 `twist_mux`를 거쳐 최종 `cmd_vel`로 이어진다.
5. 안전: watchdog이 offline을 감지하면 E-Stop 명령을 발행한다.
6. 한계: 실차 장시간 군집, YOLO 성능, 일부 custom driver는 추가 검증이 필요하다.

## 자주 나올 질문

| 질문 | 짧은 답변 방향 |
|---|---|
| ROS2 Topic과 Action 차이는? | Topic은 지속적인 상태/명령 stream, Action은 Nav2 goal처럼 시간이 걸리는 작업의 목표/피드백/결과에 적합하다. |
| 웹관제에서 WebSocket을 쓴 이유는? | 로봇 상태와 alert가 계속 바뀌므로 서버가 브라우저에 상태를 push하기 좋다. |
| rosbridge를 사용했나? | 메인 dashboard에서는 확인되지 않는다. 이 프로젝트는 Python FastAPI backend가 ROS2 bridge 역할을 한다. |
| 직접 구현한 부분은? | 전체 구조 분석, ROS2 통신/웹관제/비전/서브차량 제어 흐름 정리, 데모/문서화 준비를 직접 수행했다. |
| 가장 큰 한계는? | 실차 3대 장시간 군집 주행과 YOLO 현장 성능은 증빙이 부족해 확인 필요로 남겼다. |
| 개선한다면? | E-Stop end-to-end 로그, WebSocket command schema, camera FPS/latency, 차량별 heartbeat/odom 계약을 먼저 정리하겠다. |

## 클로봇 답변 포인트

- 이기종 로봇 관제와 연결: 차량별 namespace와 `/fleet/*` 공통 Topic 계약
- 로봇 응용 SW와 연결: ROS2 node와 dashboard/backend 사이 bridge
- 센서 연동과 연결: RGB/thermal image, alert, dashboard 표시 흐름
- 테스트/검증과 연결: Docker sim, demo GIF, 확인 필요 항목 분리

## 로보티즈 답변 포인트

- ROS2 사용 경험: Node, Topic, Action, namespace, launch 설명
- Nav2/Localization 이해: `NavigateToPose` Action Client, SLAM/AMCL 설정, TF/odom 중요성
- Linux/Docker 경험: sim compose, ROS2 workspace, package 구조
- 모바일로봇 프로젝트 경험: TurtleBot3 계열 launch와 다중 차량 관제 구조

## 모르면 이렇게 답하기

"제가 이 부분을 상용 수준으로 완성했다고 말하기는 어렵습니다. 다만 코드 기준으로는 여기까지 확인했고, 실행 검증이 필요한 항목은 확인 필요로 분리했습니다. 면접 이후에는 이 항목부터 로그와 영상으로 보강하겠습니다."
