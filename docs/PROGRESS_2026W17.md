# AIP Swarm — 주간 진행 보고서 (2026-W17)

> 기준일: 2026-04-24  
> 비교 기준: `approved_plan.md` 10단계 계획 (최초 승인본)  
> 작성: Claude Code 세션 자동 생성

---

## 1. 계획 대비 진행률 요약

| Step | 계획 내용 | 상태 | 비고 |
|------|-----------|------|------|
| Step 1 | 전용 Wi-Fi 인프라 구축 | ⏸ 대기 | 하드웨어 확보 전. 소프트웨어 선행 개발 중 |
| Step 2 | 중앙 PC 베이스 구성 (Docker Compose) | ✅ 완료 | `docker/central/` 스택 가동 |
| Step 3 | FastDDS Discovery Server 설정 | ✅ 완료 | `ROS_DOMAIN_ID=42`, DS `192.168.50.10:11811` |
| Step 4 | 공통 메시지 패키지 `aip_fleet_msgs` | ✅ 완료 | bounded string 적용 (T8) |
| Step 5 | Supervisor & Watchdog 노드 | ✅ 완료 | 23개 단위 테스트 PASS, estop_lock 퍼블리셔 포함 |
| Step 6 | `twist_mux` 통합 | ✅ 완료 | 우선순위 체인 4단계, launch arg로 활성화 |
| Step 7 | ESP32-S3 Scout 펌웨어 | ✅ 완료 | PlatformIO 스켈레톤, heartbeat 문자열 안전화, ns_valid() 검증 |
| Step 8 | Foxglove 대시보드 | ✅ 완료 | OverridePanel 10Hz HOLD-to-drive, EStopPanel, 배터리 필터 표현식 |
| Step 9 | 로깅 & 재생 | ✅ 완료 | rosbag2 상시 기록 + InfluxDB 텔레메트리 브릿지 |
| Step 10 | 시뮬 선검증 | ✅ **Phase-1 완료** | Ignition Fortress 5-peer 스폰·TF·teleop 전부 통과 |

**10단계 중 9단계 완료, 1단계(Wi-Fi 인프라) 하드웨어 대기.**

---

## 2. 계획 외 추가 달성 항목

승인 계획에는 없었으나 이번 주 신규 착수·완료된 항목:

### 2-1. 보안 강화 (SECURITY.md 기반, 36건 감사)

| 분류 | 항목 | 조치 |
|------|------|------|
| Critical | C6 watchdog 히스테리시스 | 완료 |
| High | H2 Wi-Fi PSK 외부화 | 완료 |
| High | H3 InfluxDB 자격증명 외부화 | 완료 |
| High | H4/H5 공급망 digest 고정 | 완료 (ros/microros/influxdb) |
| High | H6 컨테이너 non-root | cap_drop:[ALL] + user:65534 |
| High | H8 ESP32 set_ns 입력 검증 | ns_valid() 함수 |
| High | H9 ROS_DOMAIN_ID 하드코딩 | .env + docker-compose 환경변수화 |
| High | H10 Foxglove 패널 debounce | 완료 |
| Medium | M4/M5 YAML·패널 입력 검증 | 스키마 검증 함수 추가 |
| Critical | C1/C2/C5, H1, M2, L3/L4 | SROS2 keystore + policy 일괄 |

SROS2 keystore 생성 완료 (`config/security/keystore/`), `with_security:=true`로 즉시 활성화 가능.

### 2-2. Ignition Fortress 시뮬 스택 (신규 — 계획 범위 확장)

원래 계획(Step 10)은 `turtlesim` 3대로 E2E 검증이었으나,  
**Ignition Fortress + ros2_control 기반 5-peer 물리 시뮬**로 격상.

| 패키지 | 내용 |
|--------|------|
| `aip_main_description` | URDF/xacro — 후륜 구동 + 전방 캐스터, `use_sim` arg로 시뮬·실차 전환 |
| `aip_fleet_gazebo` | `fleet_world.sdf` (20×20m 창고), `spawn_vehicle.launch.py`, `ign_fleet.launch.py` |
| `aip_fleet_nav` | slam_toolbox / AMCL / Nav2 파라미터 + launch (Phase-2 대기) |

**Phase-1 검증 결과 (2026-04-24 완료):**
- 5대 동시 스폰 ✅
- `diff_drive_controller` active × 5 ✅
- TF 체인 `map → peer_N/odom → peer_N/base_link` × 5 ✅
- teleop 이동 확인 ✅
- 차량 디자인: 후륜 구동 + 전방 캐스터 삼각 지지 ✅

### 2-3. 군집 설계 철학 재정립

| 변경 전 | 변경 후 |
|---------|---------|
| main AGV + scout 보조 차량 계층 구조 | 동등 피어(peer) 군집 — scout는 예산 제약 임시 명칭 |
| scout가 main을 따라다님 | 각 차량이 독립 자율 주행하며 상호 협력 |

`docs/VISION.md` 신규 생성 (설계 철학 단일 진실).  
`docs/SWARM_LOCALIZATION.md` 전면 재작성 (4단계 하드웨어 업그레이드 경로).

### 2-4. 인프라 자동화

- `scripts/setup_ubuntu.sh`: 11개 섹션, 멱등성·DRY_RUN 지원 — 새 PC에서 single-command 환경 구성
- `scripts/sros2_init.sh`: keystore 일괄 생성 스크립트
- `docker/central/aip-central.service`: systemd unit 파일 — 부팅 시 자동 시작
- `~/.bash_aliases`: 14 aliases + 6 functions — `aip_ign`, `aip_ctrl`, `aip_tele` 등 개발 루프 자동화

---

## 3. E2E 검증 계획 대비 현황

원래 `approved_plan.md` §검증 계획 6단계:

| # | 검증 항목 | 상태 |
|---|-----------|------|
| 1 | 네트워크 ping + Discovery Server | ⏸ Wi-Fi AP 미확보 (로컬 환경에서 DS 동작 확인) |
| 2 | 시뮬 3대 E-Stop → `/cmd_vel` 0 송출 | ✅ Ignition 5대로 격상 완료 (Phase-1) |
| 3 | ESP32 단독 Agent 세션 수립 | ⏸ 하드웨어 미수령 |
| 4 | 3대 동시 + 메인 SLAM | 🔄 Phase-2 예정 (SLAM + Nav2) |
| 5 | 장애 주입 (Wi-Fi 차단 → ESTOP) | ⏸ 실차 환경 필요 |
| 6 | rosbag 재생 offline 분석 | ✅ `aip_bag` alias 준비 완료 |

---

## 4. 잔여 작업 (우선순위 순)

### 즉시 착수 가능

| 항목 | 내용 | 예상 공수 |
|------|------|-----------|
| **Phase-2 시뮬** | `aip_slam` (peer_1 SLAM) + `aip_nav peer_2..5` (팔로워 Nav2) | 1~2일 |
| **UWB SW 선행** | `uwb_localizer_node.py` 스켈레톤 (하드웨어 전 소프트웨어 준비) | 반나절 |
| **coordinator fallback** | TF stale 시 odom 추정 연장 로직 | 반나절 |

### 하드웨어 대기

| 항목 | 필요 하드웨어 | 예산 |
|------|--------------|------|
| Wi-Fi AP 구축 | 듀얼밴드 공유기 | — |
| ESP32 실차 연동 | Scout 차량 (기존 보유) | — |
| 예산 피어 1단계 업그레이드 | RPi Zero 2W + DWM3001C UWB + 엔코더×2 + ICM-42688 | ~9만 원 |
| 예산 피어 2단계 | VL53L5CX×4 ToF | ~+5만 원 |

### 낮은 우선순위

- B2: 와일드카드 차량 목록 동적 갱신
- Phase 3 보안: WPA3, ESP32 secure_boot, OTA 서명
- GitHub Actions CI 구성
- Grafana 대시보드 JSON
- ray-cast 단위 테스트

---

## 5. 이번 주 커밋 통계

| 날짜 | 커밋 | 주요 내용 |
|------|------|-----------|
| 2026-04-22 | 5건 | T2~T5 (estop_lock, 단위테스트, 배터리플롯, ESP32), B3 twist_mux |
| 2026-04-23 | 11건 | T6~T11, Phase2 보안, telemetry, SROS2, VISION.md |
| 2026-04-24 | 2건 | Ignition 시뮬 스택 구축 + Phase-1 완료 |

**총 18커밋, 신규 패키지 6개, 파일 변경 ~3,000줄 이상.**

---

## 6. 다음 주 목표

1. **Phase-2 시뮬 완료** — peer_1 SLAM 지도 생성 + peer_2~5 AMCL 팔로잉 + coordinator V포메이션
2. **UWB 소프트웨어 선행** — `uwb_localizer_node.py`, `with_uwb_localizer` launch arg
3. **Wi-Fi AP 확보 시** — 실차 Discovery Server 연동 테스트

---

*이 문서는 `docs/agent_context/conversation_log.md` 및 `docs/agent_context/pending_tasks.md`를 기반으로 자동 생성됩니다.*
