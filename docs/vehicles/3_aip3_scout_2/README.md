# 3번 차량: aip3 / scout_2

## 식별

- 웹 표준 ID: `aip3`
- 현재 실차 namespace: `scout_2`
- 확인된 IP: `192.168.0.5`
- 주요 컨테이너: `docker-robot-1`

## 현재 확인된 상태

- 웹 카드: online, `MANUAL`
- 현재 pose 표시: `(-0.22, -0.39)`
- pose source 표시: `pose:fleet+cal`
- helper 태그: `pose_udp`
- 저장맵 표시 상태: `전체맵/저장맵 · 201x167 0.05 m/cell`

## helper pose 후보

```text
/aip3/odom
/scout_2/odom
/scout_2/dashboard/odom
/odom
/aip3/pose
/scout_2/pose
/scout_2/dashboard/pose
/pose
```

## 운영 메모

- 현재 콘센트 연결 조건에서 조금씩만 움직일 수 있는 차량으로 운용 중이었다.
- 상태/pose 표시 검증은 가능하다.
- 장거리 주행, patrol loop, autonomous goal은 별도 안전공간과 배터리 조건을 다시 확인한 뒤 진행한다.
