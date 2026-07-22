# 코드 구조 및 개발 진행 단계 분석

**작성일**: 2026-04-22  
**분석자**: Claude Code (claude-sonnet-4-6)  
**기준 커밋**: T2/T3/T4/T5 완료 시점 (Ubuntu 세션)

---

## 1. 소스 규모 전체 현황

| 카테고리 | 주요 파일 | 라인 수 |
|---|---|---|
| 시뮬레이터 | `world.py`, `sim_vehicle_node.py`, `sim_lidar_node.py`, `sim_world_node.py` | 499 |
| 감독/감시 | `supervisor_node.py`, `watchdog_node.py` | 290 |
| 단위 테스트 | `test_supervisor_node.py` | 204 |
| 펌웨어 | `firmware/scout_microros/src/main.cpp` | 187 |
| Foxglove 패널 | `EStopPanel.tsx`, `OverridePanel.tsx`, `index.ts` | 265 |
| 런치/설정 | `fleet_sim.launch.py`, `central.launch.py` | 168 |
| **합계** | | **≈ 1,613 LoC** |

### ROS2 패키지 (5개)

| 패키지 | 유형 | 역할 |
|---|---|---|
| `aip_fleet_msgs` | ament_cmake | 커스텀 메시지·서비스 정의 |
| `aip_fleet_sim` | ament_python | 소프트웨어 in-the-loop 시뮬레이터 |
| `aip_fleet_supervisor` | ament_python | 감독 + 감시 노드, 단위 테스트 |
| `aip_fleet_bringup` | ament_python | 중앙 PC 런치, 설정 YAML |
| `aip_fleet_foxglove_panels` | npm/TypeScript | Foxglove 커스텀 패널 2종 |

---

## 2. 실제 구현된 토픽 흐름

```
[ESP32 / SimVehicle]
  /<ns>/heartbeat ──────────────────► [SupervisorNode]
  /<ns>/odom, /<ns>/scan                    │
                                            │ /fleet/status (2 Hz, TRANSIENT_LOCAL)
                                            ▼
[Foxglove Panel]                      [WatchdogNode]
  /fleet/override ─────────────────► [SupervisorNode]
                                            │
                      ┌─────────────────────┼─────────────────────┐
                      ▼                     ▼                     ▼
               /<ns>/estop          /<ns>/estop_lock      /<ns>/override_cmd_vel
                      │                     │                     │
               [SimVehicle]          [twist_mux ❌]         [SimVehicle]
                                     (미설정 — B3)
```

### 구현된 twist_mux 우선순위 체인 (설계 기준)

```
HW-EStop     (100) ← 물리 배선, 구현 없음
estop_lock   ( 90) ← supervisor → twist_mux (twist_mux 런치 미설정)
central      ( 80) ← 운영자 teleop
fleet_coord  ( 50) ← aip_fleet_coordinator (T6, 패키지 없음)
autonomy     ( 10) ← 차량 자율주행 스택
```

---

## 3. 컴포넌트별 완성도

| 컴포넌트 | 완성도 | 상태 | 비고 |
|---|---|---|---|
| 메시지 정의 (`aip_fleet_msgs`) | 90% | 🟡 | `AssignMission.srv` 정의만 있고 서버/클라이언트 없음 |
| 시뮬레이터 (`aip_fleet_sim`) | 95% | ✅ | diff-drive 적분·LiDAR 레이캐스트·배터리 드레인 동작 |
| 감독 노드 (`supervisor_node`) | 95% | ✅ | estop_lock(T2) 완료, 23개 테스트 PASS |
| 감시 노드 (`watchdog_node`) | 95% | ✅ | 히스테리시스 1.5 s, E2E 검증 |
| ESP32 펌웨어 | 55% | 🟡 | odom/모터 PWM TODO, `active_behaviors` unbounded(T8) |
| Foxglove 패널 | 70% | 🟡 | 기능 있으나 HOLD-to-drive 버그(B4) |
| **군집 조율** | **0%** | ❌ | `aip_fleet_coordinator` 패키지 자체 없음(T6) |
| **twist_mux 통합** | **0%** | ❌ | 런치 파일 어디에도 설정 없음(B3) |
| 보안 Phase 1 | 0% | ❌ | T9/T10/T11 미적용 |

---

## 4. 발견된 버그 및 갭

### B3. twist_mux 런치 누락 — **신규, 심각**

- **위치**: `central.launch.py`, `fleet_sim.launch.py`
- **현상**: `CLAUDE.md`에 `estop_lock(90) > central(80) > fleet_coord(50)` 우선순위 체인 명시되어 있으나 `twist_mux` 노드가 어느 런치 파일에도 없음
- **영향**: 시뮬에서는 `sim_vehicle_node`가 `override_cmd_vel`을 직접 받아 우회 동작하므로 E2E는 통과. 그러나 실제 차량에서 `estop_lock` 신호가 `twist_mux`를 통해 차단되지 않음
- **우선순위**: 하드웨어 배포 전 필수 해결

### B4. OverridePanel HOLD-to-drive가 한 번만 발행 — **신규, 중간**

- **위치**: `src/aip_fleet_foxglove_panels/OverridePanel/src/OverridePanel.tsx:141`
- **현상**: `onMouseDown={publishManualFrame}` — DOM 이벤트 한 번만 실행. 주석에는 "10 Hz while the button is held"라고 명시되어 있으나 `setInterval` 없음
- **영향**: 버튼을 눌러도 `CMD_MANUAL` 프레임 1회 발행 후 0.5 s 뒤 `sim_vehicle_node`의 cmd_vel stale watchdog이 차량 정지. 수동 조종 실질적으로 불가
- **수정안**: `onMouseDown`에서 `setInterval(publishManualFrame, 100)` 시작, `onMouseUp/onMouseLeave`에서 `clearInterval`

### B2. 와일드카드 차량 목록 시작 시점 고정 — **기존, 낮음**

- **위치**: `supervisor_node.py:117` — `targets = self.vehicle_ids if msg.vehicle_id == '*' else [msg.vehicle_id]`
- **현상**: `self.vehicle_ids`는 파라미터로 시작 시 결정. 런타임에 동적 추가된 차량은 `"*"` 와일드카드에 미포함
- **현재 영향**: 차량 목록이 고정 운용 시 문제 없음. 동적 확장 시 해결 필요

### T8 (기존). `string[] active_behaviors` unbounded

- **위치**: `src/aip_fleet_msgs/msg/FleetHeartbeat.msg:17`
- **현상**: unbounded `string[]` — micro-ROS `rmw_microxrcedds` 기본 설정에서 직렬화 실패 가능
- **수정안**: bounded 선언(`string[<=4] active_behaviors`) 또는 `ScoutHeartbeat.msg` 별도 분리

---

## 5. 미구현 기능 상세

### AssignMission.srv

정의: `src/aip_fleet_msgs/srv/AssignMission.srv`

```
vehicle_id, mission_type, target → accepted, reason
```

서버 구현 없음. `fleet_coord(50)` 레이어에서 mission을 받아 `/<ns>/coord_cmd_vel`을 발행하는 `aip_fleet_coordinator`가 구현되어야 함.

### aip_fleet_coordinator (T6)

패키지 자체 없음. 필요한 토픽:
- 구독: `AssignMission.srv` (서비스 서버), `/<ns>/odom` (각 차량 위치)
- 발행: `/<ns>/coord_cmd_vel` → twist_mux 우선순위 50

### Scout 위치추정 (T7)

`sim_vehicle_node.py`는 `/<ns>/odom` 발행 (odom frame). `map` frame TF 없음.  
`sim_world_node.py`는 정적 `map → <ns>/odom` TF를 브로드캐스트하나 실제 Scout에는 외부 위치추정 수단 없음.

---

## 6. 종합 판단

```
현재 상태: "중앙 PC 측 인프라 완성, 차량-플릿 연동 인프라 미완"

준프로덕션 가능한 것 (시뮬 기준):
  ✅ ESTOP → watchdog → clear 전 E2E 흐름
  ✅ Foxglove 대시보드 (배터리 플롯, 상태 테이블, 패널 2종)
  ✅ 감독/감시 노드 (23개 테스트 검증)
  ✅ Foxglove 패널 빌드 환경 (create-foxglove-extension)

하드웨어 배포 전 필수:
  ❌ twist_mux 런치 통합 (B3) ← 가장 긴급
  ❌ OverridePanel HOLD-to-drive 수정 (B4)
  ❌ SROS2 (T9) / 바인드 제한 (T10) / 공급망 고정 (T11)
  ❌ ESP32 모터 PWM 실구현 / odom 인코더 연동

설계 미확정:
  ❓ Scout 위치추정 전략 (T7) — 하드웨어 조달 결정 선행
  ❓ 군집 조율 노드 (T6) — T7 결정 후
  ❓ AssignMission.srv 서버 구현 위치
```

---

## 7. 권장 다음 작업 순서

| 우선순위 | 작업 ID | 내용 | 예상 규모 |
|---|---|---|---|
| 즉시 | B3 | twist_mux 런치 통합 (`central.launch.py` + `fleet_sim.launch.py`) | ~30줄 |
| 즉시 | B4 | OverridePanel `setInterval` HOLD-to-drive 수정 | ~15줄 |
| 다음 | T11 | 공급망 digest 고정 (platformio hash, docker SHA256) | 파일 3개 |
| 설계 후 | T7 | Scout 위치추정 전략 결정 → 구현 | 하드웨어 의존 |
| T7 후 | T6 | `aip_fleet_coordinator` 스켈레톤 | 신규 패키지 |
| 병행 | T9/T10 | SROS2 + 바인드 제한 | 인프라 변경 |

---

*이 문서는 `docs/agent_context/conversation_log.md`의 2026-04-22 Ubuntu 세션과 연동됩니다.*
