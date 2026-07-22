# Main+Sub 웹 관제 통합 PR 검토 메모

이 문서는 `C:\Projects\aip-swarm-ws-main+sub` 통합본을 팀원에게 설명하기 위한 요약이다. 원본 team main 폴더는 수정하지 않았다.

실제 PR에 포함할 파일 목록은 `docs/CHANGESET_FOR_PR_KO.md`를 함께 확인한다.

## 목적

- 웹 관제에서 `aip1`, `aip2`, `aip3` 3대가 같은 표준 ID로 보이게 한다.
- 팀 main 설계의 표준 경로인 `/aipN/heartbeat -> /fleet/status -> dashboard`를 유지한다.
- 현재 차량별 heartbeat 스키마와 DDS discovery 문제가 남아 있어 중앙 compatibility layer로 흡수한다.

## 건드리지 않은 것

- 팀원이 만든 원본 main 폴더.
- aip1/aip2/aip3 차량 소스 코드.
- 차량 주행 제어 토픽 계약.
- main 차량 내부 launch/config.
- GitHub push.

## 주요 변경

- 중앙에 `udp_status_heartbeat_adapter.py` 추가.
  - 차량별 `/tmp/status_aipN.py` helper가 보내는 UDP JSON을 받는다.
  - team-main 구형 `FleetHeartbeat` 스키마로 변환한다.
  - `/aip1/heartbeat`, `/aip2/heartbeat`, `/aip3/heartbeat`를 발행한다.
- `central_real_combined.py`에 adapter를 같은 rclpy process로 포함했다.
- dashboard direct UDP overlay는 기본 비활성화했다.
  - 기본 사용 포트: `19051` adapter.
  - fallback direct overlay 포트: `19050`, 명시적으로 켤 때만 사용.
- `manage_status_overlays.py`로 차량별 임시 상태 helper를 시작/중지/확인할 수 있게 했다.
- `WEB_CONTROL_RUNBOOK_KO.md`에 운영 절차를 정리했다.

## 현재 기본 경로

```text
차량 /tmp/status_aipN.py
  -> UDP 192.168.0.8:19051
  -> central udp_status_heartbeat_adapter
  -> /aipN/heartbeat
  -> supervisor /fleet/status
  -> dashboard http://127.0.0.1:8080/
```

## 왜 이렇게 했는가

- aip1은 내부에서 `/aip1/heartbeat`를 정상 발행하지만, 중앙 WSL에서는 DDS discovery가 되지 않았다.
- aip2/aip3는 현재 scout 계열 신형 heartbeat 스키마라 team-main 구형 `FleetHeartbeat`와 직접 호환되지 않는다.
- 따라서 차량 코드를 바로 바꾸는 대신 중앙 compatibility layer로 표준 경로에 맞췄다.

## 검증 방법

빌드:

```bash
cd /mnt/c/Projects/aip-swarm-ws-main+sub
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select aip_fleet_dashboard aip_fleet_bringup
```

테스트:

```bash
cd /mnt/c/Projects/aip-swarm-ws-main+sub
source /opt/ros/humble/setup.bash
source install/setup.bash
colcon test --packages-select aip_fleet_bringup
colcon test-result --verbose --test-result-base build/aip_fleet_bringup
```

운영 헬스체크:

```bash
cd /mnt/c/Projects/aip-swarm-ws-main+sub
bash scripts/check_web_control_stack.sh
```

기대 결과:

- `8080/tcp` 열림.
- `19051/udp` 열림.
- `11811/udp` 열림.
- `19050/udp` 닫힘.
- 웹 `3 online`.

## 남은 리스크

- 현재 차량 helper는 `/tmp/status_aipN.py`라 재부팅 후 사라질 수 있다.
- 완전 정식화하려면 차량이 직접 `/aipN/heartbeat`를 발행하거나, 중앙 WSL DDS discovery 문제가 해결되어야 한다.
- 현재 `udp_status_only` 태그는 “차량 원본 heartbeat가 아니라 adapter 경로”임을 표시한다.

## PR 제안 방향

1. 우선 중앙 compatibility layer로 합의한다.
2. 시연 기간에는 `manage_status_overlays.py` helper를 사용한다.
3. 이후 팀과 합의해 차량 side adapter 또는 네이티브 Linux 중앙 실행으로 완전 정식화한다.

## 2026-06-23 추가 메모 — 로봇 위치 marker

- 기존 `3 online` 표시는 상태만 복구했고, 실제 로봇 위치는 `pose:--`로 남아 있었다.
- 중앙 adapter가 UDP payload의 `pose`를 `/fleet/peer_poses`로 변환하도록 확장했다.
- helper도 차량 내부 odom 후보 토픽을 짧게 구독해 pose를 UDP payload에 붙이도록 확장했다.
- 차량 helper를 재시작하면 odom이 있는 차량은 웹 카드에 `pose_udp` 태그가 붙고 지도에 로봇 화살표가 표시된다.
- 이것도 정식 localization이 아니라 “현재 odom 기반 표시 경로”다. 자율 이동 전에는 map/odom/실물 위치 정합성 검증이 필요하다.
