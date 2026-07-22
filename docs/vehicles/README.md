# 차량별 웹 관제 통합 리뷰 안내

이 폴더는 `main+sub` 웹 관제 통합 내용을 팀원이 차량별로 빠르게 검토할 수 있도록 정리한 문서 묶음이다.

원본 team main 폴더와 main 차량 내부 소프트웨어는 직접 수정하지 않았다. 이번 PR 범위는 중앙 웹 관제/상태 집계/임시 호환 adapter와 문서 정리다.

## 차량 표준 ID

| 번호 | 웹 표준 ID | 현재 실차/역할 | 현재 pose 상태 |
|---|---|---|---|
| 1 | `aip1` | main 차량 | `pose:--`, main odom/pose source 확인 필요 |
| 2 | `aip2` | 기존 `scout_1` | 표시됨, `pose:fleet+cal+poseflip`, `pose_udp` |
| 3 | `aip3` | 기존 `scout_2` | 표시됨, `pose:fleet+cal`, `pose_udp` |

## 현재 중앙 경로

```text
차량 /tmp/status_aipN.py
  -> UDP 192.168.0.8:19051
  -> central udp_status_heartbeat_adapter
  -> /aipN/heartbeat
  -> supervisor /fleet/status
  -> dashboard http://127.0.0.1:8080/
```

## 리뷰 포인트

- `aip1/aip2/aip3` ID 표준화 방향이 팀 main 구조와 맞는지.
- 임시 UDP status helper를 시연용 compatibility layer로 둘지, 차량 side 정식 adapter로 옮길지.
- `/map`은 기본적으로 저장맵/전체맵을 고정하고, 차량별 SLAM map은 명시 선택만 허용하는 방향이 맞는지.
- 자율 goal/patrol은 현재 보류 상태가 맞는지. 위치/맵/토픽 정합성이 확인되기 전에는 수동 주행 검증만 한다.
