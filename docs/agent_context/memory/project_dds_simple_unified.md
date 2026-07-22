---
name: project_dds_simple_unified
description: "DDS 변천 기록 — 한때 SIMPLE 통일(DS 금지)이었으나, docker0 원인 규명 후 DS 재도입이 최종. 현재는 DS — project_fleet_network 참조"
metadata: 
  node_type: memory
  type: project
  originSessionId: 731ef982-9656-4ae1-b294-0960d1f0b260
---

⚠️ **갱신(2026-06-28 후반): 이 'DS 금지' 결론은 폐기됨.** 당시 DS 실패의 진짜 원인은 **docker0(172.17.0.1) locator 충돌**이었고, 차량 wifi interfaceWhiteList 프로파일로 해결한 뒤 **DS(Discovery Server)를 재도입한 것이 최종 구성**입니다(SIMPLE은 70+ participant에서 멀티캐스트 discovery가 wifi airtime 포화 → 매칭 실패·SSH 마비). **현재 구성은 [[project_fleet_network]]**. 아래는 그 이전 단계(docker0 미규명 시) 기록.

---

(이전 기록) 이 플릿(단일 서브넷 192.168.0.0/24, WiFi)의 정답 DDS = **전체 SIMPLE discovery 통일**. 멀티캐스트 양방향 도달 실측 검증됨(2026-06-28). 이 구성으로 대시보드 aip1 라이다(scan)·odom·poses cross-machine 도달, 라이다 표시 성공.

**Discovery Server(DS) 사용 금지**: 듀얼 DS(차량 로컬11812 + 중앙11811)는 cross-machine locator 오염, 단일 DS도 클라이언트가 11811 연결 실패 — 둘 다 cross-machine 차단. DS 서버 + SIMPLE 노드 혼재 시 discovery 충돌. (기존 [[project_central_ds_port_conflict]] 의 DS 전제는 폐기됨.)

**현재 구성(유지할 것)**:
- 차량 aip1: `aip-fleet.service` override `UnsetEnvironment=ROS_DISCOVERY_SERVER FASTRTPS_DEFAULT_PROFILES_FILE`(순수 SIMPLE), `aip-local-ds` disable.
- 중앙: `aip-central` override `UnsetEnvironment=...`(순수 SIMPLE), `fastdds-ds` = no-op(`ExecStart=/usr/bin/sleep infinity`, Requires 만족용 — 정식 정리 대상). DS 서버 미기동(11811=0).

**되살리지 말 것**: 차량 `client_profile.xml` / `ROS_DISCOVERY_SERVER` 설정. aip2/aip3 컨테이너도 `ROS_DISCOVERY_SERVER` 제거(순수 SIMPLE) 필요(aip2 docker restart policy=no).

**online 카드 cpu telemetry(해결, 2026-06-28)**: 차량엔 `aip_fleet_msgs` 없어 native FleetHeartbeat 불가 → 경량 UDP 리포터(`deploy/vehicle/aip_status_udp.py`, 순수 UDP+psutil) → 중앙 대시보드 직접 UDP(`AIP_UDP_STATUS_PORT=19052`) 오버레이로 cpu 실값 표시. 주의: 대시보드 `_ping_status_loop`가 같은 `_on_udp_status` 키를 cpu=0으로 덮는 경합 → 리포터 있는 차량은 `AIP_PING_STATUS_TARGETS`에서 제외. **남은 작업**: aip2/aip3 SIMPLE 통일+리포터 배포(전원 ON 필요), 실 estop/mode = ROS-aware 리포터 확장. 측정 함정은 [[feedback_dds_domain_check]]. 상세는 conversation_log 2026-06-28 섹션.
