# 차량 상태 리포터 배포 (aip_status_udp)

대시보드 상태 카드에 차량의 **실 cpu telemetry**를 표시하기 위한 경량 UDP 리포터.
순수 UDP+psutil 이라 차량에 ROS 메시지(`aip_fleet_msgs`)나 colcon 빌드가 필요 없다.

## 데이터 경로

```
차량 aip_status_udp.py ──UDP JSON(1Hz)──▶ 중앙 19052
                                            └▶ dashboard_server._on_udp_status
                                                 → 카드 cpu/battery/mode 오버레이 병합
```

- 중앙 전제: `aip-central` 에 `AIP_UDP_STATUS_PORT=19052` 설정(없으면 리스너 비활성).
- 배터리 센서 없는 차량은 `battery=0.0`(unsupported)로 정직하게 표시.
- `mode` 는 정적값(기본 manual). 실제 estop/모드 표시는 ROS-aware 리포터 확장 과제.

## 배포 (차량별)

```bash
VID=aip1                      # aip2 / aip3 로 변경
HOST=jh@192.168.0.3           # 차량 ssh (계정/IP 는 memory project_vehicle_ssh_accounts 참조)

ssh "$HOST" 'mkdir -p ~/aip_ws/scripts ~/.config/systemd/user'
scp deploy/vehicle/aip_status_udp.py    "$HOST":~/aip_ws/scripts/
scp deploy/vehicle/aip-status-udp.service "$HOST":~/.config/systemd/user/
# 차량 ID 치환 (aip1 외)
ssh "$HOST" "sed -i 's/AIP_VEHICLE_ID=aip1/AIP_VEHICLE_ID=$VID/' ~/.config/systemd/user/aip-status-udp.service"
ssh "$HOST" 'systemctl --user daemon-reload && systemctl --user enable --now aip-status-udp.service && systemctl --user is-active aip-status-udp.service'
```

## 검증

대시보드 WebSocket(`ws://<central>:8080/ws`) `fleet_status` 의 해당 차량 카드가
`cpu`>0, `status:"ok"` 로 표시되면 정상. ping 플레이스홀더(`network_ping_only_no_ssh`)
로 튀면 중앙 `AIP_PING_STATUS_TARGETS` 에 해당 차량이 남아있는지 확인(경합).

## 주의 — ping 오버레이 경합

대시보드 `_ping_status_loop` 도 `_on_udp_status` 로 같은 키에 쓰므로, 리포터가 있는
차량은 중앙 `AIP_PING_STATUS_TARGETS` 에서 제외해야 cpu=0 으로 덮이지 않는다.
(코드레벨 우선순위 수정은 팀원 dashboard 작업과 조율 후 — 그 전까지는 config 로 분리.)
