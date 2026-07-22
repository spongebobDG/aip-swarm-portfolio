# 1번 차량: aip1 / main 차량

## 식별

- 웹 표준 ID: `aip1`
- 역할: main 차량
- 확인된 호스트명: `AIP`
- 확인된 IP: `192.168.0.3`
- 주의: main 차량 내부 SW와 team main 원본 폴더는 팀원 관할이므로 이번 통합 작업에서 직접 수정하지 않았다.

## 현재 확인된 상태

- 웹 카드: online, `MANUAL`
- 상태 경로: `/tmp/status_aip1.py` 임시 helper 기반
- 현재 pose: `pose:--`
- 현재 확인된 ROS 프로세스:
  - `heartbeat_pub`
  - `/tmp/status_aip1.py`
- 현재 확인되지 않은 pose source:
  - `/aip1/odom`
  - `/main/odom`
  - `/aip1/pose`
  - `/main/pose`
  - `/tf`
  - `/map`
  - `/scan`

## helper pose 후보

`aip1`에서는 generic `/odom`, `/pose`를 사용하지 않는다.

이유: main 차량 host가 같은 Discovery Server에서 다른 차량의 전역 `/odom`을 볼 수 있으므로, generic 후보를 허용하면 다른 차량 위치가 `aip1` 위치처럼 표시될 위험이 있다.

현재 허용 후보:

```text
/aip1/odom
/main/odom
/aip1/pose
/main/pose
```

## 팀원 확인 필요

1. main 차량에서 실제 주행/SLAM/odom stack이 실행 중인지 확인한다.
2. main 차량의 정식 pose source 토픽 이름을 확인한다.
3. 웹에서 `aip1` 위치를 띄우려면 위 후보 중 하나로 odom/pose가 들어와야 한다.
4. 팀원 허락 전 `aip1` 주행 명령은 보내지 않는다.
