---
name: Main AGV ROS2 workspace location
description: Where the main vehicle's ROS2 colcon workspace lives and who owns it
type: reference
---

- 메인 AGV 워크스페이스: Raspberry Pi 4B 내부 Docker 컨테이너 `my_ros_env`의 `/root/colcon_ws`.
- 백업 tar.gz 위치: `C:\Users\user\Desktop\agv_backup_20260409_1300\` (`agv_workspace_20260409_1300.tar.gz`, `my_ros_agv_backup_20260409_1300.tar.gz`).
- 진행 중 작업: rf2o_laser_odometry 통합 (`compressed-wiggling-spindle.md` 계획).
- 담당: 다른 팀원. AIP 군집주행 계획에서는 환경변수 3줄(ROS_DISCOVERY_SERVER, FASTRTPS_DEFAULT_PROFILES_FILE, ROS_DOMAIN_ID=42)과 cmd_vel 앞단 twist_mux 삽입만 협조 요청.

**Why:** 메인 차량 SW는 별도 팀원 관할이라 본 계획(군집 통신·중앙 PC)이 직접 수정하지 않음.
**How to apply:** 메인 차량 측 파일 수정이 필요해지면 변경 지점을 최소 diff로 문서화해서 협조 요청하는 방식으로 진행. 직접 수정하지 말 것.
