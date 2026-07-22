# 2번 차량: aip2 / scout_1

## 식별

- 웹 표준 ID: `aip2`
- 현재 실차 namespace: `scout_1`
- 확인된 IP: `192.168.0.4`
- SSH 접속: `aip2@192.168.0.4`
- 주요 컨테이너: `turtlebot3_humble`

## 현재 확인된 상태

- 웹 카드: online, `MANUAL`
- 현재 pose 표시: `(0.26, -0.30)`
- pose source 표시: `pose:fleet+cal+poseflip`
- helper 태그: `pose_udp`
- 저장맵 표시 상태: `전체맵/저장맵 · 201x167 0.05 m/cell`

## 확인된 pose source

컨테이너 내부에서 다음 odom 토픽이 실제 수신됨을 확인했다.

```text
/odom
/scout_1/odom
/scout_1/dashboard/odom
```

Discovery Server 환경에서는 `ros2 topic list`가 `/parameter_events`, `/rosout`만 보여도 exact topic echo는 몇 초 기다리면 odom을 받을 수 있었다. 그래서 helper pose probe 대기시간을 늘렸다.

## helper pose 후보

```text
/aip2/odom
/scout_1/odom
/scout_1/dashboard/odom
/odom
/aip2/pose
/scout_1/pose
/scout_1/dashboard/pose
/pose
```

## 안전 상태

- 현재 자율 goal/patrol은 보류.
- 수동 주행/상태/pose 표시 검증까지만 허용.
- `poseflip`은 웹 표시 보정이며 Nav2 localization 보정은 아니다.
