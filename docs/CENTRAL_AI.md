# 중앙 제어 AI — Fleet Brain (설계 기본 틀)

> **상태: 설계 골격만 확정 (2026-06-26). 코드 미구현.**
> 이 문서는 "순찰 관리 + 상황 판단을 직접 진행하는 중앙 제어 AI"의 청사진이다.
> 실제 구현은 별도 세션에서 착수한다 (`docs/agent_context/pending_tasks.md` 의
> "🧠 중앙 제어 AI (Fleet Brain)" 섹션 로드맵 참조).

---

## 0. 확정된 설계 결정 (질답 기반)

| 항목 | 결정 | 함의 |
|---|---|---|
| AI 유형 | **로컬 규칙 / 경량 ML** | 클라우드 LLM 배제. 결정론적·오프라인·저지연 |
| 자율성 | **제안만 (human-in-the-loop)** | AI는 명령을 직접 내리지 않음. 운영자 승인 후 실행 |
| 책임 범위 | ① 이상징후 트리아지 + 출동 ② 순찰 스케줄링/최적화 ③ 차량 상태·장애 대응 | 운영자 자연어 챗은 범위 제외 |
| 인터넷 | **플릿망만, 외부 차단** | 외부 API 호출 불가 — 전부 중앙 PC 로컬 실행 |

> 외부망 차단은 승인된 계획(`docs/agent_context/approved_plan.md` Step 1)과 일치한다.
> 본 AI는 어떤 외부 추론 서비스에도 의존하지 않는다.

---

## 1. 설계 철학 / 비범위

- **제안만(advisory)**: Brain은 차량 토픽에 직접 발행하지 않는다. `/fleet/suggestions`만
  발행하고, 모든 액션은 운영자 승인 게이트를 통과해 **기존 명령 경로**로만 실행된다.
- **반사적 안전과 역할 분리**: 기존 `watchdog_node`
  (`src/aip_fleet_supervisor/aip_fleet_supervisor/watchdog_node.py`)는 `/fleet/status`를
  구독해 하트비트가 끊긴 차량에 `OFFLINE_CONFIRM_COUNT` 회 확인 후 자동 ESTOP을 건다
  (복구 시 자동 해제). 이 **반사적 안전 정지는 Brain을 거치지 않는다.** Brain은 그 위의
  **느린 전략적 판단** 레이어다.
- **외부 의존 제로**: 결정론적 룰을 1차로 두고, 경량 ML은 *교체 가능한 점수 함수 훅*으로만
  둔다. 학습 모델이 없어도 룰만으로 완전 동작한다.

---

## 2. 데이터 흐름 (아키텍처)

```
[입력 — 이미 존재하는 토픽]
  /fleet/status            (aip_fleet_msgs/FleetStatus)    ← supervisor 2Hz
  /fleet/alerts            (aip_fleet_msgs/PerceptionAlert)← patrol_monitor / central_fusion
  /fleet/peer_poses        (aip_fleet_msgs/PeerPoseArray)
  /fleet/coverage_pct      (std_msgs/String)               ← 전역 커버리지
  /fleet/vehicle_coverage_pct (std_msgs/String)            ← 차량별 커버리지
        │
        ▼
  ┌──────────────────────────────────────────────┐
  │  aip_fleet_brain  (신규 rclpy 노드, 중앙 PC)    │
  │  WorldModel  ← 최신 상태/알림/포즈/커버리지 캐시 │
  │  정책 평가기 (모듈식):                          │
  │    ① AnomalyTriage   ② PatrolScheduler        │
  │    ③ HealthMonitor                            │
  │  → Suggestion 객체 생성 · 중복제거 · 만료관리    │
  └──────────────────────────────────────────────┘
        │  publish
        ▼
  /fleet/suggestions  (std_msgs/String = JSON)   ← 신규 토픽 (MVP)
        │
        ▼
  dashboard_server.py  (구독 → WS {"type":"suggestion"} 로 브라우저 전달)
        │
   [운영자가 대시보드에서 승인 / 기각]
        │  승인 시
        ▼
  기존 명령 경로 재사용 (신규 차량-제어 코드 불필요):
    cmd_navigate  → NavigateToPose          (출동)
    cmd_patrol    → /patrol_planner/cmd      (순찰 start/stop/loop)
    cmd_override  → OverrideCommand          (PAUSE/RESUME/CLEAR)
```

**핵심: 입력 토픽도 출력 액션 경로도 이미 전부 존재한다.**
(`dashboard_server.py` 의 `cmd_navigate`/`cmd_patrol`/`cmd_override`/`cmd_estop` 메서드와
`/patrol_planner/cmd` 소비자 `patrol_planner_node.py` 가 그 증거.)
Brain은 그 사이에서 "무엇을 하면 좋을지"를 계산해 **제안만 추가**한다.

---

## 3. 신규 패키지 골격 — `src/aip_fleet_brain/`

```
aip_fleet_brain/
├── package.xml / setup.py / setup.cfg
├── aip_fleet_brain/
│   ├── brain_node.py        # rclpy 노드: 구독·타이머·정책 호출·/fleet/suggestions 발행
│   ├── world_model.py       # 최신 fleet 상태/알림/포즈/커버리지 캐시 (스레드 안전)
│   ├── suggestion.py        # Suggestion 데이터클래스 + JSON 직렬화 + dedup 키
│   └── policies/
│       ├── base.py          # Policy 인터페이스: evaluate(world) -> list[Suggestion]
│       ├── anomaly_triage.py
│       ├── patrol_scheduler.py
│       └── health_monitor.py
├── config/brain.yaml        # 임계값·쿨다운·가중치 파라미터 (룰 튜닝 지점)
└── test/                    # 정책별 단위 테스트 (입력 상태 → 기대 제안)
```

각 정책은 `base.Policy` 인터페이스(`evaluate(world) -> list[Suggestion]`)를 구현하고,
`brain_node`가 이를 순회 호출한다. **새 정책 추가 = 파일 하나 추가**(개방-폐쇄 원칙).

---

## 4. 정책 평가기 3종 (룰 기반 초안 + ML 훅)

### ① AnomalyTriage — 이상징후 트리아지 + 출동
- 트리거: `/fleet/alerts` (PerceptionAlert) 수신.
- 심각도 점수 = f(`alert_level`, `max_temp_c`, `confidence`).
  - `alert_level`: 0=NONE / 1=WARN(열 임계만) / 2=HIGH(열+YOLOv8 시각 확정).
- 대상 차량 선정 = `peer_poses`(map frame 위치) 거리 + `status` 가용성
  (`mode == autonomous` & `healthy` & `!estop` & 배터리 여유) → **가장 가깝고 가용한 차량**.
- 제안: "aipN 을 (x,y)=`map_position` 으로 출동시켜 열원 조사" → `action.cmd = navigate`.
- **경량 ML 훅**: 심각도 분류기(예: 작은 scikit-learn 모델)로 점수 함수를 교체 가능.
  학습 모델 부재 시 룰 점수로 폴백.

### ② PatrolScheduler — 순찰 스케줄링 / 최적화
- 주기 평가(타이머).
- `/fleet/coverage_pct` 정체 + 차량 가용성 변화 → 순찰 시작/정지/구역 재배분 제안.
- ①의 출동으로 순찰에서 이탈한 차량의 공백을 다른 가용 차량으로 메우는 제안.
- 제안: `action.cmd = patrol` (start/stop/loop), 또는 출동 빈자리 보강용 navigate.

### ③ HealthMonitor — 차량 상태·장애 대응
- `/fleet/status`(FleetHeartbeat) 기반.
- 배터리 저하(`battery_percentage`) / `cmd_stale` / 반복 `obstacle_stop` /
  `heartbeat_stale` → 도킹 복귀 · 임무 재배분 · 일시정지(PAUSE) 제안.
- 제안: `action.cmd = patrol`(정지) 또는 `override`(PAUSE/RESUME) 또는 navigate(도킹).
- **주의: 자동 ESTOP은 제안하지 않는다.** 안전 정지는 `watchdog_node`의 반사 영역으로 남긴다.

---

## 5. 인터페이스 계약 (MVP: String / JSON)

`/fleet/suggestions` (`std_msgs/String`, JSON payload) 스키마 초안:

```json
{
  "id": "triage-aip2-1719400000",   // dedup / 승인 추적용 고유키
  "ts": 1719400000.0,
  "kind": "dispatch | patrol | health",
  "severity": "info | warn | high",
  "vehicle_id": "aip2",
  "title": "aip2 출동 권고 — 열원 감지 (62°C)",
  "rationale": "HIGH alert, conf 0.81, 최근접 가용 차량",
  "action": {                        // 승인 시 대시보드가 그대로 실행
    "cmd": "navigate",              // navigate | patrol | override
    "args": { "x": 3.2, "y": -1.4, "yaw": 0.0 }
  },
  "expires_s": 30
}
```

- **MVP는 String/JSON**: 신규 `.msg`/빌드 불필요. 대시보드가 이미 JSON-over-WS 를
  쓰므로 재사용이 최대화된다. 안정화 후 `aip_fleet_msgs/FleetSuggestion.msg` 타입화로
  승급한다(확장점).
- **대시보드 측 변경(추후 구현)**:
  - `dashboard_server.py`: `_cb_suggestion` 구독 추가 → WS `{"type":"suggestion"}` 브로드캐스트.
    인바운드 `approve_suggestion` / `dismiss_suggestion` 핸들러가 `action.cmd`를 기존
    `cmd_navigate` / `cmd_patrol` / `cmd_override` 로 디스패치.
  - `index.html`: 제안 카드 UI(승인/기각 버튼) + 만료 처리.

---

## 6. 안전 가드레일

- **제안만**: Brain은 차량 토픽에 직접 발행하지 않는다. `/fleet/suggestions`만 발행.
- **승인 게이트**: 모든 액션은 운영자 승인 후 기존 명령 경로로만 실행.
- **쿨다운 / dedup**: 동일 상황 반복 제안 억제(`config/brain.yaml` 쿨다운 파라미터).
- **만료**: 제안에 `expires_s` — 오래된 권고 자동 소멸.
- **ESTOP 비간섭**: 안전 정지는 `watchdog_node` 단독 책임으로 남긴다.

---

## 7. 향후 구현 로드맵 (이번 세션 미착수)

1. `aip_fleet_brain` 패키지 + `brain_node` 골격 + `WorldModel`.
2. 정책 3종 룰 기반 구현 + 정책별 단위 테스트.
3. `dashboard_server.py` 제안 구독/승인 핸들러 + `index.html` 제안 카드 UI.
4. `central.launch.py` 에 `with_brain:=true` 인자로 노드 추가.
5. (확장) 경량 ML 심각도 분류기 학습·교체, `FleetSuggestion.msg` 타입화.

---

## 8. 참조 (실제 코드 위치)

| 대상 | 위치 |
|---|---|
| 입력 토픽 구독 패턴 | `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py` (`/fleet/status`·`/fleet/alerts`·`/fleet/peer_poses`·`/fleet/coverage_pct`) |
| 출력 명령 메서드 | 동 파일 `cmd_navigate` / `cmd_patrol` / `cmd_override` / `cmd_estop` |
| 순찰 명령 소비자 | `src/aip_fleet_autonomous/aip_fleet_autonomous/patrol_planner_node.py` (`/patrol_planner/cmd`) |
| 반사적 안전 정지 | `src/aip_fleet_supervisor/aip_fleet_supervisor/watchdog_node.py` |
| 메시지 정의 | `src/aip_fleet_msgs/msg/` (`FleetStatus`·`FleetHeartbeat`·`PerceptionAlert`·`PeerPose`·`OverrideCommand`) |
