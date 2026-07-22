# CLAUDE.md — Agent Instructions for AIP Swarm Workspace

> 이 파일은 Claude Code 가 이 워크스페이스에서 세션을 시작할 때 자동으로 읽는 지침.
> 가장 먼저 `docs/HANDOFF.md` 를 읽고 작업을 이어갈 것.

## 최우선 순서

1. **`docs/HANDOFF.md`** — 진입점. 프로젝트 요약 + 다음 읽을 파일 순서.
2. **`docs/agent_context/approved_plan.md`** — 승인된 상위 계획. 작업은 이 범위 안에서.
3. **`docs/agent_context/memory/MEMORY.md`** — 사용자 선호·프로젝트 맥락·피드백 인덱스.
4. **`docs/agent_context/pending_tasks.md`** — 남은 작업 우선순위.
5. **`docs/agent_context/conversation_log.md`** — 지금까지의 의사결정 이력.

## 필수 규칙

- **한국어로 응답**. 사용자가 한국어 선호.
- **차량 자체 SW 는 수정하지 않는다**. 메인 AGV 의 `my_ros_env:/root/colcon_ws` 는 다른 팀원 관할 (`memory/reference_main_agv_ws.md`).
- **네임스페이스 규약 준수**: `aip1`, `scout_N`. 플릿 전역은 `/fleet/*`. 새 차량 추가 시 `/<ns>/heartbeat`, `/<ns>/cmd_vel`, `/<ns>/override_cmd_vel`, `/<ns>/estop` 필수.
- **통신 스택 추천 시 확장성 반영 필수**. 현재 ESP32 를 쓰지만 Pi4/Jetson 업그레이드 시 비파괴 전환 가능해야 함 (`memory/feedback_future_proof_comm.md`).
- **보안 finding 은 `docs/SECURITY.md` 가 단일 진실**. mitigated 항목(C6/H2/H3/H10)을 되돌리지 말 것.
- **시크릿 커밋 금지**: `firmware/scout_microros/secrets.ini`, `docker/central/.env`. `.gitignore` 에 이미 등재.
- **작업 완료 시** `docs/agent_context/conversation_log.md` 하단에 날짜·결정·결과 섹션 추가. 필요 시 `pending_tasks.md` 도 갱신.

## 파일별 단일 진실 (SSOT)

| 대상 | 파일 |
|---|---|
| 승인된 계획 | `docs/agent_context/approved_plan.md` |
| 아키텍처 | `docs/ARCHITECTURE.md` |
| 버그·개선 | `docs/ANALYSIS.md` |
| 보안 findings | `docs/SECURITY.md` |
| 사용자 암묵 규칙 | `docs/agent_context/memory/` |
| 남은 작업 | `docs/agent_context/pending_tasks.md` |
| 의사결정 이력 | `docs/agent_context/conversation_log.md` |

## 빠른 개발 루프

```bash
# 시뮬 E2E (Ubuntu·Windows 공통)
docker compose -f docker/sim/docker-compose.yml up --build
# 웹 대시보드 → http://localhost:8080

# 중앙 프로덕션 스택 (Ubuntu 전용)
cd docker/central && docker compose up -d
```

세팅 가이드: `docs/SETUP_UBUNTU.md`, `docs/SETUP_WINDOWS.md`.

## alias 환경 (압축 대비 — ~/.bash_aliases 참고)

> 새 터미널 / 세션 시작 시 반드시: `source ~/.bash_aliases && aip`
> 전체 목록: `aip_help`

| alias | 설명 |
|---|---|
| `aip [sim\|real\|central]` | 워크스페이스 소싱 (ROS_DOMAIN_ID=42, RMW=fastrtps) |
| `aip_stop` | 시뮬 프로세스 전체 종료 + shm/socket 정리 (재시작 전 필수) |
| `aip_build` | 전체 colcon 빌드 + 재소스 |
| `aip_build_pkg PKG…` | 지정 패키지만 빌드 |
| `aip_ign` | Phase-1: Ignition 5대 스폰 (NVIDIA GPU) |
| `aip_ign_headless` | Phase-1 headless |
| `aip_phase2` | Phase-2: V-포메이션 (SLAM+Nav2+coordinator) |
| `aip_auto` | Autonomous: 자율주행 대기 (수동 goal) |
| `aip_auto_headless` | Autonomous headless |
| `aip_auto_patrol` | Autonomous + 순찰 자동 시작 |
| `aip_auto_thermal` | Autonomous + 순찰 + 열화상 파이프라인 |
| `aip_auto_full` | Autonomous + 순찰 + 열화상 + 충돌방지 + 커버리지 |
| `aip_ready` | 전체 초기화 헬스체크 (t=200s 이후) |
| `aip_check_auto [PEER]` | Nav2+MPPI 체인 진단 |
| `aip_check_follow [PEER]` | V포메이션 체인 진단 |
| `aip_goal [PEER] [x] [y]` | NavigateToPose 목표 전송 |
| `aip_ctrl [PEER]` | ros2_control 컨트롤러 상태 |
| `aip_tele [PEER]` | teleop → cmd_vel |
| `aip_override [PEER]` | teleop → override_cmd_vel (twist_mux 통과) |
| `aip_topics` | 핵심 토픽 목록 |
| `aip_coverage` | /fleet/coverage_pct 1회 |
| `aip_alerts` | /fleet/alerts 스트림 |
| `aip_tf` | TF 트리 PDF 생성 |
| `aip_uwb_compare` | UWB vs AMCL 오차 비교 |

## 기본 기술 스택

- ROS2 Humble, FastDDS + Discovery Server (192.168.0.10:11811), ROS_DOMAIN_ID=42
- micro-ROS Agent (UDP4:8888) for ESP32-S3 scouts
- 웹 대시보드 (FastAPI+WebSocket, http://localhost:8080) — 메인 관제 UI
- Foxglove Studio: **비사용 확정 (2026-06-25)**. `central.launch.py with_foxglove:=false` 기본값 유지.
- twist_mux 우선순위: HW-EStop(100) > estop_lock(90) > central(80) > fleet_coord(50) > autonomy(10)
- Docker Compose 중심, 전용 Wi-Fi AP (`AIP_FLEET`, 192.168.0.0/24)

## 경로 매핑 (호스트 이동 시)

| Windows | Ubuntu |
|---|---|
| `C:\Users\user\aip_swarm_ws\` | `~/aip_swarm_ws/` |
| Windows `~/.claude/plans/wobbly-gathering-tome.md` | `docs/agent_context/approved_plan.md` (워크스페이스 내 복사본) |
| Windows `~/.claude/projects/.../memory/` | `docs/agent_context/memory/` (워크스페이스 내 복사본) |
