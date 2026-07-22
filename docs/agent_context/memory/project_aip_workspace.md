---
name: AIP workspace path convention
description: Where the aip_swarm_ws scaffold lives and where it ultimately deploys
type: project
---

- **현재 위치**: Ubuntu 22.04 중앙 PC `~/aip_swarm_ws/` (2026-04-22 이전 완료)
- Windows 스캐폴딩(`C:\Users\user\aip_swarm_ws\`)에서 Ubuntu로 이전 완료. git init + 초기 커밋됨.
- 메인 차량은 별도 환경(`my_ros_env` Docker의 `/root/colcon_ws`) — 건드리지 않음. 네임스페이스/QoS 협조만.

**Why:** Ubuntu 이전 완료로 실제 배포 환경이 개발 환경과 동일해짐.
**How to apply:** 경로는 Ubuntu 기준 `~/aip_swarm_ws/...`로 표기. Windows 경로는 더 이상 사용 안 함.
