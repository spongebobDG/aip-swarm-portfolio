# AGENTS.md - Agent Instructions for AIP Swarm Workspace

> 이 저장소는 클로봇 로봇 응용 SW 개발자 신입 지원용 포트폴리오로 정리하는 프로젝트이다.
> Codex는 이 파일을 우선 지침으로 보고, README와 docs를 면접관이 이해하기 쉬운 형태로 정리한다.

## 프로젝트 목적

- ROS2 기반 로봇 소프트웨어 경험을 보여준다.
- 산업감시로봇 팀프로젝트에서 사용자가 맡은 역할을 명확히 보여준다.
- 서브차량 제어, 웹관제, 비전카메라 연동 경험을 정리한다.
- 면접관이 README와 docs만 읽어도 프로젝트 구조를 이해할 수 있게 만든다.
- 구현하지 않은 기능을 구현한 것처럼 과장하지 않는다.

## 작업 시작 시 읽을 문서

1. `docs/HANDOFF.md` - 프로젝트 요약과 다음에 읽을 파일 순서.
2. `docs/agent_context/approved_plan.md` - 승인된 상위 계획.
3. `docs/agent_context/memory/MEMORY.md` - 사용자 선호, 프로젝트 맥락, 피드백 인덱스.
4. `docs/agent_context/pending_tasks.md` - 남은 작업 우선순위.
5. `docs/agent_context/conversation_log.md` - 지금까지의 의사결정 이력.

## 핵심 작성 원칙

1. 실제 코드나 자료에서 확인되지 않은 기능은 절대 구현된 것처럼 쓰지 않는다.
2. ROS2, rosbridge, WebSocket, React, Vue, SLAM, Nav2, Docker, MLOps 등은 코드나 자료에서 확인될 때만 사용했다고 작성한다.
3. 확인되지 않은 내용은 `TODO` 또는 `확인 필요`라고 표시한다.
4. 소스코드 동작을 임의로 크게 바꾸지 않는다.
5. 파일 삭제는 금지한다. 불필요한 파일은 필요 시 `archive/` 폴더로 이동만 한다.
6. README와 문서는 한글 중심으로 작성하되, ROS2, Topic, Service, Node, WebSocket, OpenCV 같은 기술 용어는 영어 그대로 사용한다.
7. 면접에서 설명 가능한 수준의 솔직한 표현을 사용한다.
8. 신입 개발자 포트폴리오답게 과장보다 구조, 역할, 문제 해결, 학습 내용을 강조한다.
9. 코드나 문서 수정 전에는 어떤 파일을 왜 수정할지 먼저 설명한다.
10. 수정 후에는 변경 요약, 위험 요소, 사용자가 확인해야 할 사항을 정리한다.

## README 필수 구성

README를 작성하거나 개편할 때는 최소한 아래 항목을 포함한다.

- Project Overview
- Demo
- My Role
- Key Features
- System Architecture
- ROS2 Communication
- Web Dashboard
- Vision Camera Integration
- Sub Vehicle Control
- Tech Stack
- How to Run
- Troubleshooting
- What I Learned
- Future Improvements

## 표현 기준

- "구현 완료", "실차 검증", "자율주행 가능", "군집 주행 완료" 같은 표현은 코드, 실행 로그, 문서, 캡처 등 근거가 있을 때만 사용한다.
- 현재 데모 수준이 시뮬레이션, 웹관제, 일부 통신 구조 확인에 머무른다면 그 범위를 명확히 쓴다.
- 미완성 기능은 "진행 중", "검증 필요", "향후 개선"으로 구분한다.
- 팀프로젝트 내용은 사용자가 맡은 역할과 팀 전체 구현을 구분해서 쓴다.
- 지원용 문서에서는 성과뿐 아니라 문제 원인, 해결 과정, 배운 점을 함께 정리한다.

## 코드 수정 원칙

- 차량 자체 SW는 수정하지 않는다. 메인 AGV의 `my_ros_env:/root/colcon_ws`는 다른 팀원 관할이다.
- 네임스페이스 규약을 유지한다. 기존 문서 기준은 `main`, `scout_N`이며, 플릿 전역 Topic은 `/fleet/*`를 사용한다. 단, 현재 코드에서 `aip1`, `aip2`, `aip3` 등 다른 명칭이 확인되면 문서에 그 차이를 설명한다.
- 새 차량 또는 서브차량을 설명할 때는 `/<ns>/heartbeat`, `/<ns>/cmd_vel`, `/<ns>/override_cmd_vel`, `/<ns>/estop` 같은 통신 계약을 확인한 뒤 작성한다.
- 통신 스택을 추천하거나 설명할 때는 현재 ESP32 기반 구성과 향후 Pi4/Jetson 전환 가능성을 함께 고려한다.
- 보안 finding은 `docs/SECURITY.md`를 단일 진실로 본다. mitigated 항목을 되돌리지 않는다.
- 시크릿 파일은 커밋하지 않는다. 특히 `firmware/scout_microros/secrets.ini`, `docker/central/.env`는 주의한다.

## 파일별 단일 진실

| 대상 | 파일 |
|---|---|
| 승인된 계획 | `docs/agent_context/approved_plan.md` |
| 아키텍처 | `docs/ARCHITECTURE.md` |
| 버그·개선 | `docs/ANALYSIS.md` |
| 보안 findings | `docs/SECURITY.md` |
| 사용자 암묵 규칙 | `docs/agent_context/memory/` |
| 남은 작업 | `docs/agent_context/pending_tasks.md` |
| 의사결정 이력 | `docs/agent_context/conversation_log.md` |

## 빠른 실행 참고

```bash
# 시뮬레이션 E2E
docker compose -f docker/sim/docker-compose.yml up --build

# Foxglove Studio
ws://localhost:8765

# 중앙 프로덕션 스택, Ubuntu 전용
cd docker/central && docker compose up -d
```

세팅 가이드는 `docs/SETUP_UBUNTU.md`, `docs/SETUP_WINDOWS.md`를 우선 확인한다.

## 작업 완료 기록

- 작업 완료 시 `docs/agent_context/conversation_log.md` 하단에 날짜, 결정, 결과를 추가한다.
- 필요하면 `docs/agent_context/pending_tasks.md`도 함께 갱신한다.
- 포트폴리오용 변경은 README, docs, 데모 캡처, 실행 방법이 서로 일치하는지 마지막에 확인한다.