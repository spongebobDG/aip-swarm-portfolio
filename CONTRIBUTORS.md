# Contributors

AIP Swarm 프로젝트에 기여해 주신 분들입니다.

## Core Team

| 이름 | GitHub | 역할 |
|---|---|---|
| Mark2AC | [@Mark2AC](https://github.com/Mark2AC) | 프로젝트 리드, 전체 아키텍처, 실차 통합 |

## Contributors

| 이름 | GitHub | 기여 내용 |
|---|---|---|
| spongebobDG | [@spongebobDG](https://github.com/spongebobDG) | 웹 관제 대시보드 기능 구현 |

### spongebobDG 기여 상세 (PR #2 → 6f3ccf9)

- **`dashboard_server.py`**: asyncio 스레딩 버그 수정, `_state_cache` 도입(신규 클라이언트 접속 시 상태 복원), `ExternalShutdownException` 처리, TF fallback 타이머 추가
- **`static/index.html`**: 다크모드 토글, 지도 전체화면, 웨이포인트 편집 UI
- **`sim_heartbeat_node.py`**: 시뮬 환경용 FleetHeartbeat 더미 퍼블리셔 노드 (신규)
- **`sim_pose_relay_node.py`**: TF → `/fleet/peer_poses` 릴레이 노드 (신규)
- **`supervisor_node.py`**: ControlLock 기반 다중 오퍼레이터 충돌 방지 메커니즘
- **`EStopPanel` / `OverridePanel` / `FleetDashboard`**: 세션 락, 키보드 제어 추가
- **`central.launch.py`**: Foxglove 조건부 시작, 대시보드 `use_sim_time` 수정
- **`follower_trigger_node.py`**: live map fallback 개선
- **`run_sim.sh` / `run_central.sh`**: 시뮬·중앙 실행 편의 스크립트
