# 웹 관제 통합본 운영 절차

이 문서는 `C:\Projects\aip-swarm-ws-main+sub` 통합본 기준이다. 팀원이 만든 원본 main 폴더는 수정하지 않는다.

## 현재 상태 요약

- 웹 주소: `http://127.0.0.1:8080/`
- 표준 차량 ID: `aip1`, `aip2`, `aip3`
- 현재 3대 online 표시는 중앙의 UDP heartbeat adapter가 `/aipN/heartbeat`로 변환한 뒤, supervisor의 `/fleet/status`를 통해 웹에 표시된다.
- `udp_status_only` 태그가 보이면 차량 원본 heartbeat가 아니라 중앙 adapter 경로라는 뜻이다.
- 저장맵은 웹에서 `저장맵` 버튼을 눌러 다시 불러올 수 있다.

## 중앙 PC에서 시작

WSL Ubuntu에서 Discovery Server를 먼저 켠다.

```bash
wsl -d Ubuntu-22.04 -- bash /mnt/c/Projects/aip-swarm-ws-main+sub/scripts/start_fastdds_ds.sh
```

중앙 웹 스택은 통합본 폴더에서 실행한다.

```bash
cd /mnt/c/Projects/aip-swarm-ws-main+sub
AIP_DISCOVERY_MODE=server ROS_DISCOVERY_SERVER=192.168.0.8:11811 AIP_PING_STATUS_TARGETS= ./run_central.sh
```

브라우저에서 `http://127.0.0.1:8080/`을 연다.

## 3대 상태 overlay 시작

비밀번호는 파일에 저장하지 않는다. 실행 시 프롬프트에 입력하거나, 현재 터미널에만 환경변수로 넣는다.

프롬프트 입력 방식:

```bash
cd /mnt/c/Projects/aip-swarm-ws-main+sub
python3 scripts/manage_status_overlays.py start
```

환경변수 방식:

```bash
cd /mnt/c/Projects/aip-swarm-ws-main+sub
export AIP1_SSH_PASSWORD='<aip1 비밀번호>'
export AIP2_SSH_PASSWORD='<aip2 비밀번호>'
export AIP3_SSH_PASSWORD='<aip3 비밀번호>'
python3 scripts/manage_status_overlays.py start
```

이 스크립트는 각 차량에 `/tmp/status_aipN.py`를 만들고 1Hz로 `192.168.0.8:19051`에 상태를 보낸다. 중앙의 `udp_status_heartbeat_adapter`가 이를 표준 `/aipN/heartbeat`로 변환한다. 차량 소스 코드나 team main 원본 폴더는 수정하지 않는다.

현재 helper는 차량에서 odom을 찾을 수 있으면 pose도 함께 보낸다. 중앙 adapter는 이 pose를 `/fleet/peer_poses`로 변환하고, 웹은 이를 로봇 화살표 marker로 표시한다.

후보 odom 토픽:

- `aip1`: `/aip1/odom`, `/main/odom`
- `aip2`: `/aip2/odom`, `/scout_1/odom`, `/odom`
- `aip3`: `/aip3/odom`, `/scout_2/odom`, `/odom`

helper를 갱신한 뒤 웹 카드에 `pose_udp` 태그가 보이면 pose 전송이 된 것이다. 계속 `pose:--`라면 해당 차량 내부에서 위 odom 토픽이 안 나오거나 helper가 아직 구버전으로 실행 중인 상태다.

## 상태 확인

```bash
cd /mnt/c/Projects/aip-swarm-ws-main+sub
python3 scripts/manage_status_overlays.py status
```

Codex 자동 실행이나 CI처럼 비밀번호를 입력할 수 없는 환경에서는 빠르게 안내만 받고 끝내려면 다음처럼 실행한다.

```bash
python3 scripts/manage_status_overlays.py status --no-prompt
```

중앙 포트 확인:

```bash
ss -ltnup | grep -E ':8080|:19051|:11811'
```

참고: dashboard의 예전 direct UDP overlay는 기본 비활성화되어 있다. 긴급 fallback으로만 `AIP_UDP_STATUS_PORT=19050`을 명시해 켠다.

자동 점검:

```bash
cd /mnt/c/Projects/aip-swarm-ws-main+sub
bash scripts/check_web_control_stack.sh
```

웹에서 기대 상태:

- `3 online`
- `aip1 MANUAL`
- `aip2 MANUAL`
- `aip3 MANUAL`
- 맵: `전체맵/저장맵`

## overlay 중지

```bash
cd /mnt/c/Projects/aip-swarm-ws-main+sub
python3 scripts/manage_status_overlays.py stop
```

특정 차량만 중지:

```bash
python3 scripts/manage_status_overlays.py stop --targets aip2
```

## aip3 AMCL 초기화 자동화 (C-AMCL)

aip3 docker restart 후 AMCL이 초기 포즈를 잃어 수동 발행이 필요했던 문제를 중앙에서 자동화했다.

**활성화 방법** — 중앙 기동 전 환경변수 설정:

```bash
export AIP_AMCL_INIT_VEHICLES=aip3          # 자동 initialpose 발행 대상
export AIP_AMCL_INIT_DELAY_SEC=8.0          # 중앙 기동 후 대기 시간 (기본 8s)
export AIP_AMCL_INIT_POSE_AIP3=0.0,0.0,0.0 # x,y,yaw_deg (기본 원점)
./run_central.sh
```

**동작**: 중앙 안정화(14s) + 추가 대기(8s) 후 `/aip3/initialpose` 를 DDS로 발행.
공분산 x/y ±0.7m, yaw ±30° 로 설정해 AMCL이 LiDAR 스캔으로 자체 수렴하도록 허용.

포즈가 맞지 않으면 `AIP_AMCL_INIT_POSE_AIP3=x,y,yaw_deg` 값을 실측 좌표로 조정한다.

## 정식화할 때 남은 일

현재 adapter는 정식 토픽 경로(`/aipN/heartbeat` -> `/fleet/status`)를 쓰지만, 입력은 여전히 차량별 UDP helper다. 완전 정식 통합은 다음 중 하나로 가야 한다.

- 중앙을 팀 main과 같은 네이티브 Linux/DDS discovery 조건으로 실행한다.
- WSL mirrored networking + FastDDS Discovery Server locator 문제를 tcpdump로 분석한다.
- 차량 쪽 adapter가 team main 구형 `FleetHeartbeat` 스키마로 `/aipN/heartbeat`를 발행하게 한다.

`aip1`은 이미 `/aip1/heartbeat`를 정상 발행한다. 문제는 중앙 WSL에서 discovery가 안 되는 점이다. `aip2/aip3`는 현재 scout 계열 신형 heartbeat 스키마라서 나중에 adapter가 필요할 가능성이 더 크다.
## 2026-06-23 pose 표시 상태 메모

현재 통합본의 웹 위치 표시는 임시 status helper가 차량 내부 odom/pose를 읽어 UDP payload에 `pose`를 넣고, 중앙 `udp_status_heartbeat_adapter`가 이를 `/fleet/peer_poses`로 변환하는 방식이다.

현재 확인된 상태:

- `aip2`: 표시됨. `(0.26, -0.30)`, `pose:fleet+cal+poseflip`, `pose_udp`.
- `aip3`: 표시됨. `(-0.22, -0.39)`, `pose:fleet+cal`.
- `aip1`: 아직 `pose:--`. main 차량에서 `/aip1/odom`, `/main/odom` 또는 명시적인 pose source가 확인되지 않았다.

Discovery Server 환경에서는 `ros2 topic list`가 `/parameter_events`, `/rosout`만 보일 수 있어도, exact topic echo는 몇 초 기다리면 odom을 받을 수 있다. 그래서 helper는 pose probe를 5초까지 기다리고, subprocess timeout은 8초로 둔다.

현재 helper가 확인하는 주요 후보:

- `aip1`: `/aip1/odom`, `/main/odom`, `/aip1/pose`, `/main/pose`
- `aip2`: `/aip2/odom`, `/scout_1/odom`, `/scout_1/dashboard/odom`, `/odom`, `/aip2/pose`, `/scout_1/pose`, `/scout_1/dashboard/pose`, `/pose`
- `aip3`: `/aip3/odom`, `/scout_2/odom`, `/scout_2/dashboard/odom`, `/odom`, `/aip3/pose`, `/scout_2/pose`, `/scout_2/dashboard/pose`, `/pose`

`aip1` 위치가 필요하면 먼저 team main 차량에서 실제 odom/pose/map stack이 실행 중인지 확인한다. 원본 main 폴더와 main 차량 SW는 이 통합본 작업에서 직접 수정하지 않는다.

주의: `aip1`에는 generic `/odom`, `/pose` 후보를 넣지 않는다. main 차량 host는 같은 Discovery Server에서 다른 차량의 전역 `/odom`을 볼 수 있으므로, 잘못하면 다른 차량 위치가 `aip1` 위치처럼 표시된다.
