# Agent Handoff — AIP Swarm Workspace

> **이 문서는 다른 환경(특히 Ubuntu 중앙 PC)에서 Claude Code 에이전트가 이 워크스페이스의 작업을 이어받을 때 가장 먼저 읽어야 하는 문서.**

> 🚨 **최신 (2026-06-29): 5GHz 밴드 전환 — 중앙·aip1·aip2·aip3 전 차량 5GHz 완료.** aip2 5GHz 실패 원인은 **netplan password가 해시 PSK**였던 것(평문 수정으로 해결; regulatory/CLM/HW 전부 배제 — `conversation_log.md` 2026-06-29 정정). **DDS = 단일 중앙 DS 확정**(5GHz에서 aip2 Nav2 내부 discovery 정상 → SIMPLE 복원 불필요). 전 차량 online, 중앙 RX 1.24MB/s로 데이터 도달 확인. 잔여 = (선택·비긴급) aip2 트래픽 최적화. 상세 §5 + memory `project_fleet_network`.
>
> 🚨 **그 직전 재개 지점 (2026-06-28 전 차량 검증/투입):**
> **[`docs/agent_context/HANDOFF_2026-06-28_VEHICLE_TEST.md`](agent_context/HANDOFF_2026-06-28_VEHICLE_TEST.md)** 를 읽을 것.
> 2026-06-27 야간 세션(RPi4B 부하/SSH 안정화 + 운영 AMCL 모드 + 금지구역 차단/경고 + 웹 UI 전수
> 검증, 로컬 main)의 전 맥락과 **내일 aip1/aip2/aip3 직접 검증 절차·gotcha·배포 체크리스트**가 거기 있다.

## 한 줄 요약

AIP 팀의 **분산 자율 군집 이동체 시스템**. 목표는 각 차량이 독립적으로 자율 주행하면서 서로 협력하는 동등 피어(peer) 군집이다. 현재는 예산 제약으로 완전 사양 차량(main)과 최소 사양 차량(scout)이 혼재하는 임시 계층 구조를 갖는다. `docs/VISION.md` 참조.

워크스페이스는 ROS2 Humble 기반, Ubuntu 22.04 중앙 PC 에서 구동. 중앙 PC의 supervisor/coordinator는 **임시 스캐폴딩**이며 장기적으로 각 차량에 분산된다.

## 1. 반드시 먼저 읽을 파일 (순서대로)

1. `README.md` — 전체 스코프 요약, 배포·실행 방법
2. **`docs/VISION.md`** — **설계 철학 및 세대별 목표. 가장 먼저 읽어야 할 맥락.**
3. `docs/agent_context/approved_plan.md` — 이 프로젝트의 **승인된 상위 계획**. 모든 작업은 이 계획 안에서 이뤄져야 함
4. `docs/agent_context/memory/` — Claude 메모리 스냅샷. 사용자 선호·프로젝트 맥락·피드백·레퍼런스 모두 이 안에
5. `docs/agent_context/conversation_log.md` — 지금까지의 주요 대화·의사결정 누적 로그
6. `docs/agent_context/pending_tasks.md` — 아직 남은 작업의 우선순위 로드맵
7. `docs/ARCHITECTURE.md` — 패키지·토픽·QoS·런타임 그래프 (현재 구현 기준)
8. `docs/ANALYSIS.md` — 발견된 버그·구조 문제와 개선 방향
9. `docs/SECURITY.md` — 보안 감사 결과 (36 건, mitigated/deferred 플래그 포함)
10. `docs/SWARM_LOCALIZATION.md` — 군집 차량 위치 추정 하드웨어 전략
11. `docs/CENTRAL_AI.md` — **중앙 제어 AI(Fleet Brain) 설계 기본 틀** (로컬 룰/경량 ML · 제안만 · 미구현)

## 2. 실행 가능한 진입점

| 목적 | 명령 |
|---|---|
| 시뮬 E2E (Ubuntu·Windows 공통) | `docker compose -f docker/sim/docker-compose.yml up --build` → Foxglove `ws://localhost:8765` |
| 중앙 프로덕션 스택 (Ubuntu) | `cd docker/central && docker compose up -d` |
| Ubuntu 초기 세팅 전체 절차 | `docs/SETUP_UBUNTU.md` |
| Windows 개발 루프 | `docs/SETUP_WINDOWS.md` |

## 3. 중요한 "암묵적" 규칙

아래 규칙은 코드에서 유추되지 않으므로 새 에이전트가 반드시 알아야 함:

1. **설계 목표는 동등 피어 군집**. `aip1`/`aip2`/`aip3` 구분은 역할이 아닌 정체성(identity). 코드는 항상 차량 사양이 올라가도 인터페이스가 그대로 유지되도록 작성한다. `docs/VISION.md` 참조.
2. **차량 자체 SW 는 건드리지 않는다.** 메인 AGV 의 `my_ros_env` 컨테이너 와 `/root/colcon_ws` 는 다른 팀원 관할. 본 워크스페이스는 협조 요청 만 문서화할 권한.
3. **네임스페이스 규약**: `aip1`, `aip2`, `aip3`. 전역은 `/fleet/*`. 새 차량 추가 시 반드시 `/<ns>/heartbeat`, `/<ns>/cmd_vel`, `/<ns>/override_cmd_vel`, `/<ns>/estop` 규약 준수.
4. **ROS_DOMAIN_ID = 42** — `.env` 환경변수로 관리 (H9 mitigated). 다중 플릿 배포 시 변경.
5. **DDS = 전환 중** (2026-06-28 DS 재도입 → 2026-06-29 5GHz 후 **SIMPLE 복원 예정**). 동일 서브넷(192.168.0.0/24). 최신 상태는 memory `project_fleet_network`/`project_dds_simple_unified` 단일 진실. ⚠️ 단일 중앙 DS는 차량 Nav2 **내부(intra-vehicle) discovery를 깨뜨림** → SIMPLE 권장.
6. **우선순위 체인** (twist_mux): estop_lock(90) > central override(80) > fleet_coord(50) > stuck_escape(15) > autonomy(10).
7. **UWB 배제** (2026-06-15 결정). 실차 위치 추정은 LiDAR SLAM 전용. UWB 관련 노드 실차 launch에 포함 금지.
8. **보안 finding 은 `docs/SECURITY.md` 에서 단일 진실**. 이미 mitigated 된 항목(C6/H2/H3/H10) 은 되돌리지 말 것.
9. **시크릿 파일은 절대 커밋 금지**: `firmware/scout_microros/secrets.ini`, `docker/central/.env`. `.gitignore` 에 이미 등재.
10. **한국어로 대화**. 사용자가 한국어 선호.

## 4. 파일 경로 매핑 (Windows → Ubuntu)

원본 메모리는 Windows 경로를 기준으로 작성됐음. Ubuntu 로 이주하는 경우:

| Windows | Ubuntu |
|---|---|
| `C:\Users\user\aip_swarm_ws\` | `~/aip_swarm_ws/` |
| `C:\Users\user\.claude\plans\wobbly-gathering-tome.md` | `~/aip_swarm_ws/docs/agent_context/approved_plan.md` (복사본) |
| `C:\Users\user\.claude\projects\C--Users-user\memory\` | `~/aip_swarm_ws/docs/agent_context/memory/` (복사본) |
| 메인 차량 워크스페이스 (Pi4 Docker `my_ros_env:/root/colcon_ws`) | 동일 — 이 프로젝트는 직접 접근하지 않음 |

## 5. 현재 상태 스냅샷 (2026-06-29 기준)

**네트워크 밴드 (2026-06-29 5GHz 전환):**
- 중앙 PC=**5GHz**(1134Mbit), aip1=**5GHz**(ch36 −33dBm), **aip2=5GHz**(2026-06-29; 원인=netplan **해시 PSK**→평문 수정으로 해결, regulatory/CLM/HW 전부 배제), **aip3=5GHz**(−38dBm 1.7ms). **전 차량 5GHz 완료.**
- **혼합밴드 정상**(2.4·5GHz 같은 서브넷 브리지, 교차밴드 검증). 라우터 ipTIME AX3000Q, SSID `aip5GHz` ch36 80MHz.
- **DDS=단일 중앙 DS 확정**: 2.4에서 깨졌던 aip2 Nav2 내부 discovery가 5GHz에선 정상 → **SIMPLE 복원 불필요**. 전 차량 online, aip2 Nav2 가동, 중앙 wlan0 RX 1.24MB/s 데이터 도달 확인. (memory `project_fleet_network`, `project_dds_simple_unified`.)
- 진행(선택·비긴급): **aip2 트래픽 최적화**(TX 2.5MB/s → ros_topic_bridge throttle). **5GHz 전환·DDS DS·전 차량 운영 검증 = 완료.**

완료(이전):
- **aip1 네임스페이스 통일** — `/main/*` → `/aip1/*` 완전 치환. 소스(fleet_main/twist_mux/slam config) + 중앙(supervisor.yaml/dashboard_server.py) 모두 완료, 재부팅 검증됨.
- **aip3 부팅 병목 해소** — `docker-compose.yml` 조건부 빌드 패치. cache-hit 시 colcon build 생략, 기동 마비 → 15초로 단축.
- **중앙 ONLINE 파이프라인 복구** — stray DS(포트 11811 점유) kill → fastdds-ds stable → aip-central HTTP 200.
- **aip1 Nav2 RPP 검증** — NavigateToPose x=0.5m SUCCEEDED (2026-06-27).
- **전 차량 토픽 네임스페이스**: aip1→`/aip1/*`, aip2→`/aip2/*`, aip3→`/aip3/*` 규약 준수 완료.
- Foxglove 완전 비사용 확정, 웹 대시보드(http://localhost:8080) 단일 관제 UI.

진행 중/미완:
- **aip1 ssh 불안정**: Nav2+SLAM 동시 로딩 15초 I/O 창에서 ssh 타임아웃. stagger 기동 미적용.
- **aip2 heartbeat flapping**: DDS-over-WiFi UDP 손실. supervisor timeout 완화 또는 발행 주기 상향 필요.
- **aip3 combined_safety_node** 58~70% CPU (ESP32 busy-poll 의심).
- **Fleet Brain GPU 학습**: Tailscale 구성 완료, Windows SSH/RDP 자격증명 문제로 미완. 귀가 후 조치 필요.
- **C-AMCL**: 코드 완료, 실차 검증 필요 (`AIP_AMCL_INIT_VEHICLES=aip3`).
- `docs/agent_context/pending_tasks.md` 참조.

다음 세션 시작 시 확인 순서:
1. `systemctl --user status fastdds-ds aip-central` — 중앙 스택 상태
2. `ping 192.168.0.3 192.168.0.4 192.168.0.5` — 전 차량 응답 확인
3. 대시보드 http://localhost:8080 — 차량 ONLINE 카드 확인
4. aip2/aip3 켜져 있으면 `ros2 topic hz /aip2/heartbeat /aip3/heartbeat` — heartbeat 수신 확인

## 6. 다음 에이전트가 흔히 실수하는 지점

- **시뮬 이미지(docker/sim) 와 프로덕션 중앙 스택(docker/central) 을 섞지 말 것.** 전자는 단일 컨테이너 + bridge net, 후자는 분리된 서비스 + host net.
- **Python 노드를 추가/수정해도 rebuild 불필요** (`--symlink-install`). 하지만 **msg/srv 수정 시에는 반드시 `colcon build` 재실행**.
- **`ros2 launch` 는 컨테이너 안에서 실행.** 호스트 Windows/Ubuntu 에 ROS2 를 별도 설치하지 않고도 개발 가능하게 설계됨.
- **Foxglove 는 8765 포트**, 그 외 DDS/micro-ROS 포트(11811/8888)는 host-net 기반 production 스택에서만 사용.
- **Ubuntu 에서 `.env` 미설정 시 InfluxDB 서비스가 의도적으로 실패** (H3 mitigation). `.env.example` 참고.

## 7. 에이전트가 반드시 유지해야 할 단일 진실 (SSOT)

| 대상 | 단일 진실 파일 |
|---|---|
| 승인된 계획 범위 | `docs/agent_context/approved_plan.md` |
| 아키텍처 (토픽/QoS/TF) | `docs/ARCHITECTURE.md` |
| 발견된 버그/개선 | `docs/ANALYSIS.md` |
| 보안 findings + Status | `docs/SECURITY.md` |
| 사용자 선호/암묵 규칙 | `docs/agent_context/memory/` |
| 남은 작업 우선순위 | `docs/agent_context/pending_tasks.md` |
| 대화·의사결정 누적 로그 | `docs/agent_context/conversation_log.md` |

새 작업/결정을 했다면 위 파일들을 **즉시 업데이트**. 다음 에이전트가 빠르게 따라붙을 수 있게.
