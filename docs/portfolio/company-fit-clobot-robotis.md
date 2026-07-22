# Company Fit: Clobot And Robotis

> 기준일: 2026-07-08  
> 목적: AIP 프로젝트를 클로봇 로봇 응용 SW 신입, 로보티즈 인턴 공고와 연결해 설명한다.

## 공고 요약

| 회사 | 공고에서 강하게 보이는 키워드 | AIP 프로젝트 연결 |
|---|---|---|
| 클로봇 | 로봇 응용 SW, 제어/센서 연동, 로봇 관제 대시보드, 웹/앱 UI, 테스트/검증/배포 | ROS2 Topic 계약, dashboard WebSocket, E-Stop/override, RGB/thermal alert, Docker sim |
| 로보티즈 | ROS2, Python/C++, Linux, Nav2/Localization, 모바일로봇 테스트, 문서화 | ROS2 package 구조, Nav2 Action Client, TurtleBot3 launch, sim/실차 bringup 문서 |

## 클로봇 지원 포인트

| 어필 포인트 | 프로젝트 근거 | 말할 때 주의 |
|---|---|---|
| 관제 대시보드 이해 | FastAPI + WebSocket + HTML/JavaScript dashboard | React/Vue 메인 dashboard라고 말하지 않기 |
| 센서 연동 경험 | Vision Pi bridge, thermal driver, `PerceptionAlert` | YOLO 성능 검증을 과장하지 않기 |
| 로봇 제어 흐름 | `/fleet/override`, `twist_mux`, `cmd_vel`, E-Stop | 하드웨어급 안전 인증처럼 말하지 않기 |
| 테스트/검증 태도 | Docker sim, demo GIF, limitations 문서 | 실차 완전 검증과 구분하기 |
| 협업/문서화 | `docs/architecture/*`, `README.md`, `PORTFOLIO_KO.md` | 팀 전체 구현을 개인 단독 성과로 말하지 않기 |

## 로보티즈 지원 포인트

| 어필 포인트 | 프로젝트 근거 | 말할 때 주의 |
|---|---|---|
| ROS2 기본기 | Node, Topic, Service, Action, namespace 정리 | 모르는 QoS 세부를 아는 척하지 않기 |
| Nav2/Localization 이해 | `NavigateToPose` Action Client, SLAM/AMCL config | Nav2 planner/controller를 직접 구현했다고 말하지 않기 |
| 모바일로봇 통합 경험 | TurtleBot3 launch, `cmd_vel`, odom/TF 구조 | 실제 Robotis hardware 검증 범위 확인하기 |
| Linux/Docker | Docker sim, ROS2 workspace, compose | 환경별 미검증 명령은 미검증으로 말하기 |
| 문서와 테스트 | troubleshooting, facts, limitations | 완성도보다 학습과 정리 역량 강조 |

## 지원 서류 한 줄 방향

ROS2 기반 산업감시로봇 팀프로젝트에서 로봇 상태/제어/센서 데이터를 중앙 웹관제로 연결하는 구조를 분석하고, 시뮬레이션 데모와 문서로 검증 범위와 한계를 정리한 신입 지원자입니다.

## 면접에서 강조할 순서

1. ROS2 Topic 계약과 namespace를 먼저 설명한다.
2. 웹관제 backend가 ROS2와 browser 사이를 어떻게 연결하는지 말한다.
3. E-Stop/override/control flow로 로봇 응용 SW 관점을 보여준다.
4. RGB/thermal/perception alert 흐름으로 센서 연동 경험을 말한다.
5. 마지막에 한계와 다음 개선 계획을 솔직하게 말한다.
