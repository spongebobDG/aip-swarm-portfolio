# Main+Sub 통합본 PR 변경 파일 목록

이 문서는 `C:\Projects\aip-swarm-ws-main+sub` 통합본에서 팀원 PR 검토를 위해 확인해야 할 주요 변경 파일 목록이다.

원본 team main 폴더는 수정하지 않았다. 현재 통합본 폴더도 Git 저장소가 아니므로, 실제 PR을 만들 때는 아래 파일들을 Git 브랜치에 반영한 뒤 diff를 다시 확인해야 한다.

## 핵심 코드

- `src/aip_fleet_bringup/scripts/udp_status_heartbeat_adapter.py`
  - 차량별 UDP 상태 helper 입력을 team-main 구형 `FleetHeartbeat`로 변환한다.
  - `/aip1/heartbeat`, `/aip2/heartbeat`, `/aip3/heartbeat`를 발행한다.

- `src/aip_fleet_bringup/scripts/central_real_combined.py`
  - 중앙 프로세스에 UDP heartbeat adapter 노드를 함께 올린다.

- `src/aip_fleet_bringup/CMakeLists.txt`
  - adapter 스크립트 설치와 pytest 등록을 추가한다.

- `src/aip_fleet_bringup/package.xml`
  - `ament_cmake_pytest` test dependency를 추가한다.

- `src/aip_fleet_dashboard/aip_fleet_dashboard/dashboard_server.py`
  - 예전 dashboard direct UDP overlay 기본 포트를 `0`으로 바꿔 기본 비활성화한다.
  - 기본 상태 경로를 `/fleet/status` 기반으로 유지한다.

- `src/aip_fleet_dashboard/static/index.html`
  - 지도 위 도킹 위치 마커 렌더링을 제거한다.
  - 현재 실차 운영에 필요하지 않은 충전/도킹 스테이션 UI를 숨긴다.

## 테스트

- `src/aip_fleet_bringup/test/test_udp_status_heartbeat_adapter.py`
  - UDP payload를 `FleetHeartbeat`로 변환하는 순수 함수 테스트.
  - 확인된 테스트 결과: `6 passed`.

## 운영 스크립트

- `scripts/start_fastdds_ds.sh`
  - WSL에서 FastDDS Discovery Server를 `192.168.0.8:11811`로 시작한다.

- `scripts/manage_status_overlays.py`
  - `aip1`, `aip2`, `aip3` 차량에 임시 `/tmp/status_aipN.py` helper를 시작/중지/상태확인한다.
  - 비밀번호는 파일에 저장하지 않고, 프롬프트 또는 현재 셸 환경변수로만 받는다.
  - 자동 환경용 `--no-prompt` 옵션을 제공한다.

- `scripts/check_web_control_stack.sh`
  - dashboard `8080`, adapter `19051`, Discovery Server `11811`, direct overlay `19050` 비활성화, 저장맵 존재 여부를 점검한다.

## 문서

- `docs/WEB_CONTROL_RUNBOOK_KO.md`
  - 현장 실행 절차.
  - overlay 시작/중지/상태 확인.
  - 자동 헬스체크 명령.

- `docs/PR_REVIEW_NOTES_KO.md`
  - 팀원 리뷰용 요약.
  - 왜 중앙 compatibility layer를 둔 것인지 설명.
  - 남은 리스크와 PR 제안 방향.

- `docs/CHANGESET_FOR_PR_KO.md`
  - 이 파일. 실제 PR에 들어갈 파일 목록.

- `docs/agent_context/conversation_log.md`
  - 통합 과정의 결정과 검증 이력.

- `docs/agent_context/pending_tasks.md`
  - 남은 작업 우선순위.

## PR 전에 다시 확인할 명령

```bash
cd /mnt/c/Projects/aip-swarm-ws-main+sub
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select aip_fleet_dashboard aip_fleet_bringup
source install/setup.bash
colcon test --packages-select aip_fleet_bringup
colcon test-result --verbose --test-result-base build/aip_fleet_bringup
bash scripts/check_web_control_stack.sh
```

## 팀과 결정해야 할 점

- 중앙 compatibility layer를 시연 기간 공식 경로로 둘지 결정한다.
- 이후 차량 side adapter로 옮길지, 중앙 DDS discovery 문제를 해결해 제거할지 결정한다.
- `udp_status_only` 태그는 임시 helper 경로임을 의미하므로, 최종 릴리즈 전 제거 또는 이름 변경 여부를 결정한다.

## 2026-06-23 추가 변경 — pose marker 경로

- `udp_status_heartbeat_adapter.py`
  - UDP payload에 `pose`가 포함되면 `/fleet/peer_poses`를 발행한다.
  - 웹 dashboard의 기존 `poses` 경로를 사용하므로 프론트엔드의 로봇 marker 로직을 새로 만들지 않는다.

- `manage_status_overlays.py`
  - 차량 내부 odom 후보 토픽을 짧게 구독해 성공 시 UDP payload에 `pose`를 포함한다.
  - 후보 토픽:
    - `aip1`: `/aip1/odom`, `/main/odom`
    - `aip2`: `/aip2/odom`, `/scout_1/odom`, `/odom`
    - `aip3`: `/aip3/odom`, `/scout_2/odom`, `/odom`
  - pose가 전송되면 웹 카드 behavior 태그에 `pose_udp`가 추가된다.

- 테스트
  - `test_udp_status_heartbeat_adapter.py`에 `PeerPose` 변환 테스트를 추가했다.
  - 확인된 결과: `9 passed`.
