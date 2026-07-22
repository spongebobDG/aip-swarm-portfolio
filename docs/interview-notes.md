# Interview Notes

> 목적: 클로봇 로봇 응용 SW 개발자 신입 면접에서 이 프로젝트를 솔직하고 구조적으로 설명하기 위한 정리 문서입니다.  
> 원칙: 코드와 문서에서 확인된 내용은 `확인됨`, 추가 증빙이 필요한 내용은 `확인 필요`로 표시합니다.

## 1. 프로젝트 한 줄 소개

ROS2 기반 다중 산업감시로봇 환경에서 차량 상태, 제어 명령, 비전/열화상 데이터를 중앙 웹관제 화면으로 통합해 확인하고 제어할 수 있도록 구성한 포트폴리오 프로젝트입니다.

## 2. 내가 맡은 역할

| 역할 | 설명 | 확인 상태 |
|---|---|---|
| 서브차량 제어 구조 정리 | `cmd_vel`, `override_cmd_vel`, `coord_cmd_vel`, `estop`, `heartbeat` 중심의 차량 제어 흐름을 분석하고 문서화 | 확인됨 |
| 웹관제 연동 | FastAPI backend, WebSocket, 정적 HTML/JavaScript UI를 통해 ROS2 상태와 제어 명령을 연결하는 구조 정리 | 확인됨 |
| 비전카메라 연동 | Vision Pi HTTP bridge, ROS2 image topic, thermal alert, dashboard 표시 흐름을 정리 | 확인됨 |
| 팀 통합/시연 지원 | README, docs, demo 이미지/GIF, troubleshooting, 면접 노트 등 포트폴리오 제출 자료 정리 | 확인됨 |
| 실차 다중 군집 자율주행 완성 | 모든 차량이 동시에 안정적으로 군집 자율주행을 완료했는지 여부 | 확인 필요 |
| aip3 custom vehicle/STS3215 driver 완성 | custom vehicle launch와 TODO 문서가 확인되므로 실제 driver 완성 여부 | 확인 필요 |
| YOLO 기반 화재/연기 인식 성능 검증 | YOLOv8 호출 코드는 있으나 전용 모델, 데이터셋, 정확도 검증 근거 | 확인 필요 |

면접에서 이렇게 말하면 안전합니다.

> 제가 맡은 핵심은 로봇 개별 알고리즘을 완성했다고 주장하기보다, 여러 차량과 센서 데이터를 ROS2 Topic 계약으로 묶고 웹관제, 비전카메라, 서브차량 제어 흐름을 통합·문서화한 부분입니다. 구현된 코드와 아직 검증이 필요한 부분을 구분해서 포트폴리오로 정리했습니다.

## 3. 전체 시스템 구조 설명

이 프로젝트는 크게 네 영역으로 나눠 설명할 수 있습니다.

1. 차량 또는 시뮬레이션 노드가 `heartbeat`, `odom`, `scan`, `cmd_vel` 같은 ROS2 Topic을 주고받습니다.
2. 중앙 PC의 supervisor/watchdog/dashboard/perception node가 차량 상태를 모으고, offline 상태나 E-Stop 같은 안전 이벤트를 처리합니다.
3. 웹관제 backend인 `dashboard_server.py`가 ROS2 Topic을 구독하고 WebSocket으로 브라우저에 전달합니다.
4. 브라우저 UI는 차량 카드, 지도, 위치, alert, camera frame을 표시하고, 사용자의 E-Stop/manual override/goal 명령을 다시 backend로 보냅니다.

말로 설명할 때는 다음 순서가 좋습니다.

> 차량은 ROS2 Topic으로 상태를 내보내고, 중앙 PC는 그 상태를 `/fleet/status`로 모읍니다. 웹관제 서버는 이 ROS2 데이터를 WebSocket JSON으로 바꿔 브라우저에 보여줍니다. 반대로 사용자가 웹에서 E-Stop이나 수동 주행 명령을 누르면 WebSocket으로 backend에 들어오고, backend가 ROS2 Topic이나 Action으로 차량에 전달합니다.

## 4. ROS2 통신 구조 설명

| ROS2 개념 | 이 프로젝트에서의 예시 | 설명 |
|---|---|---|
| Node | `supervisor_node`, `watchdog_node`, `dashboard_server`, `vision_pi_bridge_node`, `serial_bridge`, `coordinator_node` | 독립적으로 실행되는 기능 단위 |
| Topic | `/<vehicle>/heartbeat`, `/fleet/status`, `/fleet/override`, `/fleet/alerts`, `/<vehicle>/cmd_vel` | 상태와 명령을 비동기로 주고받는 통신 경로 |
| Message | `FleetHeartbeat`, `FleetStatus`, `OverrideCommand`, `PerceptionAlert`, `geometry_msgs/Twist` | Topic으로 오가는 데이터 형식 |
| Service | `/save_map_now`, Nav2 costmap clear service | 요청-응답이 필요한 작업에 사용 |
| Action | `/<vehicle>/navigate_to_pose`, `FollowJointTrajectory` | 시간이 걸리는 목표 수행에 사용 |
| Parameter | `vehicle_id`, `base_url`, `heartbeat_timeout_sec`, `warn_temp_c` 등 | launch나 runtime에서 node 동작을 조정 |
| Namespace | `aip1`, `aip2`, `aip3`, `/fleet/*` | 차량별 Topic과 fleet 공통 Topic을 구분 |

핵심 설명:

> ROS2에서는 단순히 Topic 이름만 맞추는 것이 아니라 Message Type, namespace, QoS, publish/subscribe 방향이 맞아야 통합이 됩니다. 이 프로젝트에서는 차량별 상태는 `/<vehicle>/heartbeat`로 받고, 중앙에서 `/fleet/status`로 모아 웹관제에 전달합니다. 제어는 웹관제에서 `/fleet/override` 또는 차량별 `override_cmd_vel`로 전달되며, E-Stop은 supervisor/watchdog과 연결됩니다.

주의해서 말할 점:

- `AssignMission.srv` 파일은 확인되지만 실제 server/client 사용처는 확인 필요입니다.
- custom Action Server는 코드 검색 기준 확인되지 않았습니다.
- Nav2는 직접 구현했다기보다 `NavigateToPose` Action Client로 goal을 전달하는 구조입니다.

## 5. 웹관제 데이터 흐름

확인된 웹관제 구조는 `FastAPI + WebSocket + 정적 HTML/JavaScript`입니다. React/Vue 기반 메인 dashboard는 확인되지 않았고, Foxglove custom panel에는 React/TypeScript 코드가 별도로 존재합니다.

데이터 흐름:

1. 차량 또는 simulation node가 `/<vehicle>/heartbeat`, `/<vehicle>/odom`, `/<vehicle>/scan`, image topic, alert topic을 발행합니다.
2. `supervisor_node`가 heartbeat를 모아 `/fleet/status`를 발행합니다.
3. `dashboard_server.py`가 `/fleet/status`, `/fleet/alerts`, `/map`, `/map_static`, `/fleet/peer_poses`, image topic 등을 구독합니다.
4. backend가 ROS2 Message를 브라우저에서 쓰기 쉬운 JSON 또는 base64 image로 변환합니다.
5. WebSocket `/ws`를 통해 `fleet_status`, `alert`, `slam_map`, `vision`, `thermal_spots`, `scan`, `odom` 같은 메시지를 전송합니다.
6. `index.html`의 JavaScript가 차량 카드, 지도, alert feed, vision panel을 갱신합니다.

제어 명령 흐름:

1. 사용자가 웹에서 E-Stop, 수동 주행, goal 이동, patrol, keepout zone 명령을 누릅니다.
2. frontend가 WebSocket command를 backend로 보냅니다.
3. `dashboard_server.py`가 command를 분기 처리합니다.
4. backend가 ROS2 Topic publish, Service call, Action goal 형태로 차량 또는 중앙 node에 전달합니다.

면접 표현:

> 브라우저가 ROS2에 직접 붙는 구조가 아니라, Python backend가 ROS2와 WebSocket 사이의 bridge 역할을 합니다. 그래서 ROS2 의존성은 backend에 두고, 브라우저는 JSON과 image base64만 처리합니다.

## 6. 비전카메라 처리 흐름

확인된 비전 흐름은 세 갈래입니다.

### 6.1 ROS2 camera driver 기반 RGB 흐름

1. `camera_driver.launch.py`가 `camera_ros` 또는 `v4l2_camera_node` 실행을 구성합니다.
2. RGB image가 `/<vehicle>/arm/image_raw/compressed` 형태로 발행되도록 구성되어 있습니다.
3. `central_fusion_node.py`가 compressed image를 구독합니다.
4. OpenCV로 decode, rotate, resize, bbox/text overlay, JPEG encode를 수행합니다.
5. `/fleet/perception_viz/<vehicle>`로 dashboard 표시용 image를 발행합니다.

### 6.2 Vision Pi HTTP bridge 흐름

1. `vision_pi_bridge_node.py`가 Vision Pi의 `/rgb.jpg`, `/thermal.jpg`, `/status.json` endpoint를 읽습니다.
2. RGB JPEG는 `/<vehicle>/image_raw/compressed`로 발행합니다.
3. thermal JPEG는 `sensor_msgs/Image` `rgb8` 형태의 `/<vehicle>/thermal_viz`로 발행합니다.
4. status에서 온도 threshold를 넘으면 `/fleet/alerts`로 `PerceptionAlert`를 발행합니다.

### 6.3 Thermal monitoring 흐름

1. `thermal_driver_node.py` 또는 `thermal_uart_driver_node.py`가 32x24 thermal frame을 `/<vehicle>/thermal_raw`로 발행합니다.
2. `patrol_monitor_node.py`가 최고 온도와 hotspot을 계산합니다.
3. threshold 조건을 만족하면 `/fleet/alerts`를 발행합니다.
4. dashboard backend가 alert와 image topic을 WebSocket으로 브라우저에 전달합니다.

면접에서 조심할 점:

- OpenCV 사용은 확인됨입니다.
- `cv_bridge`는 Scout ArUco localizer에서 사용되고, perception/dashboard 일부 경로는 NumPy 직접 변환을 사용합니다.
- 직접 `cv2.VideoCapture()`로 camera capture하는 코드는 확인되지 않았습니다.
- YOLOv8 호출 코드는 있으나 fire/smoke 전용 모델 검증은 확인 필요입니다.
- “AI 화재 감지 완성”보다 “비전/열화상 데이터를 ROS2와 웹관제로 연결하고, optional YOLO fusion 경로를 구성했다”가 안전합니다.

## 7. 서브차량 제어 흐름

확인된 제어 흐름은 다음과 같습니다.

### 7.1 웹 수동 제어

1. 사용자가 웹 UI에서 제어권을 잡고 버튼 또는 keyboard로 명령을 입력합니다.
2. `index.html`이 WebSocket으로 `override` command를 보냅니다.
3. `dashboard_server.py`가 `linear_x`, `angular_z`를 `geometry_msgs/Twist`로 변환합니다.
4. backend가 `/fleet/override`와 차량별 override topic에 명령을 보냅니다.
5. `supervisor_node.py`가 `/fleet/override`를 받아 차량별 `override_cmd_vel`, `estop`, `estop_lock`으로 route합니다.
6. `twist_mux`가 central override, coordinator, stuck escape, autonomy 입력의 우선순위를 적용해 최종 `cmd_vel`을 만듭니다.
7. 차량 driver 또는 simulation node가 `cmd_vel`을 받아 동작합니다.

### 7.2 aip1 serial bridge 흐름

1. `serial_bridge.py`가 ROS2 `cmd_vel`을 구독합니다.
2. `Twist.linear.x`, `Twist.angular.z`를 UART packet `CMD_VEL`로 변환합니다.
3. ESP32 firmware가 packet을 받아 좌우 wheel velocity로 변환합니다.
4. motor control 코드가 PWM을 계산하고 encoder feedback을 받습니다.
5. ESP32가 encoder tick을 다시 RPi로 보내면 `serial_bridge.py`가 `odom`, `enc_ticks`, TF를 발행합니다.

### 7.3 안전 제어

- `watchdog_node.py`는 `/fleet/status`에서 offline 차량을 감지하면 `/fleet/override`로 `CMD_ESTOP`을 발행합니다.
- `supervisor_node.py`는 E-Stop 명령을 차량별 `estop`, `estop_lock`, zero `Twist`로 변환합니다.
- ESP32 main AGV firmware에는 command watchdog이 있어 명령이 끊기면 PWM을 0으로 만드는 흐름이 확인됩니다.

확인 필요:

- 모든 차량에서 `estop_lock`이 실제 `twist_mux` lock으로 활성화되어 motion을 막는지 실차 검증이 필요합니다.
- aip3 custom vehicle driver 완성 여부는 확인 필요입니다.
- physical joystick node는 확인되지 않았고, 웹 keyboard/manual drive는 확인됩니다.

## 8. 가장 어려웠던 문제

코드와 문서 구조를 기준으로 예상되는 문제 해결 사례입니다. 실제 면접에서는 본인이 직접 겪은 사례만 선택해서 말하는 것이 좋습니다.

### 사례 1. ROS2 Topic 계약과 문서가 섞여 있던 문제

- 문제: 문서에는 `main/scout_*` 표현이 남아 있고, 최신 코드에서는 `aip1/aip2/aip3` namespace가 사용되는 부분이 있었습니다.
- 원인: 프로젝트가 진행되면서 차량 ID 체계가 바뀌었지만 문서가 모두 최신화되지 않았을 가능성이 있습니다.
- 대응: README와 docs에서 확인된 코드 기준으로 namespace와 Topic을 다시 정리했습니다.
- 말할 때: “문서와 코드가 다를 때는 코드, launch, setup.py, topic 이름을 기준으로 다시 확인했습니다.”

### 사례 2. 웹관제와 ROS2 사이의 데이터 형식 변환

- 문제: ROS2 Message를 브라우저가 바로 이해할 수 없기 때문에 JSON/base64 image로 바꿔야 했습니다.
- 대응: `dashboard_server.py`가 ROS2 subscribe/publish를 담당하고, WebSocket `/ws`가 UI와의 실시간 통신을 담당하도록 역할을 나눴습니다.
- 배운 점: 로봇 관제에서는 backend가 통신 계약과 상태 변환의 중심이 되며, message schema를 문서화하는 것이 중요합니다.

### 사례 3. 비전카메라 경로가 여러 개인 문제

- 문제: camera driver 기반 RGB topic, Vision Pi HTTP bridge, thermal driver 경로가 함께 존재해 어떤 입력이 실제 사용되는지 혼동될 수 있었습니다.
- 대응: `vision-camera.md`와 interview notes에서 입력 경로를 분리해서 설명하고, 확인되지 않은 model/accuracy는 확인 필요로 남겼습니다.
- 직접 채울 질문: 실제 시연 영상에서 사용한 camera source는 `camera_ros`, `v4l2_camera`, Vision Pi HTTP 중 무엇이었나요?

### 사례 4. E-Stop이 UI 버튼에서 실제 차량 정지까지 이어지는지 검증 필요

- 문제: 코드상 E-Stop command, supervisor routing, watchdog은 확인되지만 모든 실차에서 motion 차단까지 end-to-end 검증했는지는 별도 증빙이 필요합니다.
- 대응: 문서에는 확인된 ROS2 command 흐름과 확인 필요 항목을 분리했습니다.
- 직접 채울 질문: E-Stop 버튼 클릭 후 `/fleet/override`, `/<vehicle>/estop`, `/<vehicle>/cmd_vel=0`, 실제 정지까지 녹화한 자료가 있나요?

## 9. 현재 한계점

- 전체 다중 로봇 군집 자율주행이 완전히 해결됐다고 말하기에는 검증 근거가 부족합니다.
- `sim_vehicle_node.py`에는 문서상 수정 필요로 보이는 오타가 언급되어 fresh run 검증이 필요합니다.
- Vision/YOLO 경로는 코드가 있지만 전용 모델, 정확도, 현장 검증은 확인 필요입니다.
- `aip3` custom vehicle driver는 TODO 성격이 남아 있어 완성 기능처럼 말하면 위험합니다.
- 웹관제는 기능이 많지만 `index.html` 단일 파일 규모가 커서 유지보수성이 낮아 보일 수 있습니다.
- WebSocket command schema, E-Stop 감사 로그, reconnect 세부 정책, latency/FPS 측정이 더 보강되면 좋습니다.
- physical E-Stop input node와 physical joystick node는 코드 기준 확인되지 않았습니다.
- `AssignMission.srv`는 파일은 있으나 실제 사용처 확인이 필요합니다.

## 10. 개선 계획

클로봇 로봇 응용 SW 개발 직무와 연결해서 다음 순서로 개선하면 좋습니다.

| 개선 계획 | 이유 | 우선순위 |
|---|---|---|
| ROS2 Topic/Message 계약 표준화 | 다중 로봇 통합에서는 namespace, topic, message type이 흔들리면 전체가 불안정해짐 | 높음 |
| E-Stop end-to-end 검증 로그 | 안전 기능은 UI 버튼보다 실제 차량 정지 증빙이 중요함 | 높음 |
| WebSocket command schema 문서화 | frontend/backend 사이 계약을 명확히 해야 유지보수와 협업이 쉬움 | 높음 |
| reconnect/stale 상태 표시 강화 | 로봇 관제에서는 네트워크 끊김과 데이터 지연을 사용자가 알아야 함 | 높음 |
| 비전 FPS/latency 측정 | camera 입력부터 dashboard 표시까지 병목을 수치로 설명 가능 | 높음 |
| Docker 실행 환경 정리 | 면접관이나 팀원이 README만 보고 재현 가능해야 함 | 높음 |
| rosbridge 검토 | 브라우저가 ROS2 topic과 직접 통신해야 하는 요구가 생기면 검토 가능. 현재 코드 기준 사용은 확인되지 않음 | 중간 |
| 로그 저장/감사 기록 | E-Stop, override, goal command의 누가/언제/무엇을 기록하면 운영 관점 설명 가능 | 중간 |
| dashboard frontend 모듈 분리 | 단일 HTML/JS가 커져 유지보수 위험이 있으므로 기능별 파일 분리 | 중간 |
| `aip3` driver 검증 | custom vehicle 제어를 포트폴리오에서 더 명확히 설명하려면 실제 topic/driver 검증 필요 | 중간 |

## 11. 예상 면접 질문 30개

### ROS2

1. 이 프로젝트에서 ROS2 Node는 어떤 기준으로 나눴나요?
2. `/fleet/status`와 `/<vehicle>/heartbeat`의 차이는 무엇인가요?
3. `supervisor_node`와 `watchdog_node`의 역할 차이는 무엇인가요?
4. Topic, Service, Action을 각각 어디에 사용했나요?
5. `geometry_msgs/Twist`는 어떤 값으로 차량을 제어하나요?
6. custom message를 만든 이유는 무엇인가요?
7. namespace를 `aip1/aip2/aip3`로 나누는 이유는 무엇인가요?
8. QoS는 왜 중요하다고 생각하나요?

### 웹관제

9. 웹관제는 ROS2와 어떻게 연결되어 있나요?
10. rosbridge를 사용했나요?
11. WebSocket을 사용한 이유는 무엇인가요?
12. 웹에서 E-Stop 버튼을 누르면 어떤 흐름으로 전달되나요?
13. dashboard에서 표시하는 데이터는 어떤 것들이 있나요?
14. 현재 웹관제 코드의 가장 큰 한계는 무엇인가요?

### 비전카메라

15. 비전카메라 데이터는 어떤 경로로 들어오나요?
16. OpenCV는 어디에 사용했나요?
17. `sensor_msgs/Image`와 `CompressedImage`를 어떻게 구분했나요?
18. YOLOv8 기능은 완성된 기능인가요?
19. thermal alert는 어떻게 만들어지나요?
20. 카메라 latency나 FPS는 측정했나요?

### 서브차량 제어

21. 서브차량은 어떤 명령으로 움직이나요?
22. `twist_mux`를 왜 사용하나요?
23. `serial_bridge.py`는 어떤 역할을 하나요?
24. E-Stop은 어떻게 처리되나요?
25. 통신이 끊기면 차량은 어떻게 되나요?

### 협업

26. 팀 프로젝트에서 본인의 기여를 어떻게 구분해서 설명할 수 있나요?
27. 문서와 코드가 다를 때 어떻게 확인했나요?
28. 구현한 기능과 구현하지 않은 기능을 어떻게 구분했나요?

### AI 도구 사용

29. AI 도구를 사용했다면 어떤 방식으로 활용했고, 검증은 어떻게 했나요?

### 클로봇 지원동기

30. 이 프로젝트 경험이 클로봇 로봇 응용 SW 개발 직무와 어떻게 연결되나요?

## 12. 답변 방향

| 번호 | 답변 방향 |
|---|---|
| 1 | 기능 단위와 통신 책임 기준으로 나눴다고 답합니다. 예: supervisor는 상태 집계, watchdog은 offline 안전 처리, dashboard는 ROS2-WebSocket bridge, perception은 vision/thermal 처리입니다. |
| 2 | `heartbeat`는 차량별 생존/상태 신호이고, `/fleet/status`는 중앙 supervisor가 이를 모아 만든 fleet 전체 요약이라고 설명합니다. |
| 3 | supervisor는 정상 상태 집계와 override routing, watchdog은 offline 상태를 감지해 E-Stop을 발행하는 안전 감시 역할이라고 설명합니다. |
| 4 | Topic은 상태/명령 stream, Service는 `/save_map_now`처럼 요청-응답, Action은 `NavigateToPose`처럼 시간이 걸리는 goal 수행에 사용한다고 말합니다. |
| 5 | 주행에는 주로 `linear.x`와 `angular.z`를 사용한다고 말하고, serial bridge가 이 값을 ESP32 packet으로 변환한다고 연결합니다. |
| 6 | `FleetHeartbeat`, `FleetStatus`, `OverrideCommand`, `PerceptionAlert`처럼 fleet 관제에 필요한 정보를 표준 ROS2 메시지보다 명확히 담기 위해 만들었다고 설명합니다. |
| 7 | 차량별 topic 충돌을 막고 동일한 인터페이스를 여러 차량에 적용하기 위해 namespace를 나눴다고 답합니다. |
| 8 | map/status처럼 늦게 붙는 subscriber가 필요한 데이터와 sensor처럼 최신성이 중요한 데이터는 QoS 요구가 다르다고 설명합니다. |
| 9 | `dashboard_server.py`가 ROS2 node로 topic을 구독/발행하고, FastAPI/WebSocket으로 브라우저와 통신한다고 답합니다. |
| 10 | 현재 메인 dashboard 코드에서는 rosbridge/roslibjs 사용이 확인되지 않았다고 솔직히 답합니다. 대신 Python backend가 bridge 역할을 한다고 설명합니다. |
| 11 | 차량 상태, alert, image frame처럼 실시간성이 필요한 데이터를 브라우저에 계속 push하기 위해 WebSocket을 사용한다고 설명합니다. |
| 12 | UI -> WebSocket command -> `dashboard_server.py` -> `/fleet/override`/vehicle estop topic -> supervisor/vehicle 순서로 설명합니다. |
| 13 | 차량 online/offline, battery/cpu 일부, map, pose, scan, alert, RGB/thermal image, E-Stop/override 상태를 표시한다고 말합니다. |
| 14 | 기능이 단일 `index.html`에 많이 들어 있어 유지보수성이 낮고, command schema와 감사 로그 문서화가 필요하다고 솔직히 말합니다. |
| 15 | ROS2 camera driver topic 경로와 Vision Pi HTTP bridge 경로가 확인된다고 설명하고, 실제 시연에 사용한 경로는 자료로 증빙해야 한다고 답합니다. |
| 16 | JPEG decode, color conversion, rotate, heatmap, bbox/text drawing, resize, JPEG encode에 사용했다고 설명합니다. |
| 17 | RGB JPEG/visualization은 `CompressedImage`, thermal raw/viz는 `Image` 중심이라고 설명합니다. |
| 18 | YOLOv8 호출 코드는 있지만 전용 모델과 정확도 검증은 확인 필요라고 말합니다. 과장하지 않는 것이 중요합니다. |
| 19 | thermal frame 또는 Vision Pi status에서 최고 온도와 hotspot을 보고 threshold를 넘으면 `PerceptionAlert`를 발행한다고 설명합니다. |
| 20 | 문서상 일부 FPS 기록은 있지만 통합 end-to-end latency/FPS는 추가 측정 계획으로 답하는 것이 안전합니다. |
| 21 | 최종적으로 `geometry_msgs/Twist` 기반 `cmd_vel`을 사용하고, override/coordinator/autonomy 입력이 `twist_mux`를 거쳐 합쳐진다고 설명합니다. |
| 22 | 수동 override, coordinator, autonomy, E-Stop 등 여러 제어 입력의 우선순위를 명확히 하기 위해 사용한다고 답합니다. |
| 23 | ROS2 `cmd_vel`을 ESP32 UART packet으로 변환하고, encoder feedback을 `odom`/TF로 다시 발행하는 bridge라고 설명합니다. |
| 24 | watchdog과 dashboard가 `/fleet/override` 또는 차량별 estop topic을 발행하고, supervisor가 차량별 E-Stop과 zero Twist로 route한다고 설명합니다. |
| 25 | watchdog은 heartbeat offline을 감지해 E-Stop을 발행하고, ESP32 main firmware에는 command watchdog으로 PWM을 0으로 만드는 흐름이 확인된다고 말합니다. 단, 차량별 end-to-end 검증은 확인 필요입니다. |
| 26 | 본인은 서브차량 제어 흐름, 웹관제 연동, 비전카메라 연동, 문서화/시연 자료 정리에 집중했다고 말합니다. 다른 팀원이 맡은 차량 자체 SW는 과장하지 않습니다. |
| 27 | README보다 코드의 `package.xml`, `setup.py`, launch, topic publish/subscribe를 우선 근거로 삼고, 불확실한 부분은 TODO로 남겼다고 답합니다. |
| 28 | 코드에서 확인된 것은 확인됨, 문서에만 있는 것은 문서상 확인, 실행 검증이 필요한 것은 확인 필요로 분리했다고 말합니다. |
| 29 | AI 도구는 코드 검색, 문서 구조화, 면접 질문 정리에 활용하되, 실제 코드 근거와 실행 결과를 직접 확인하는 방식으로 검증했다고 답합니다. |
| 30 | 클로봇 직무에서 중요한 ROS2 통신, 다중 로봇 상태 관리, 관제 UI, 안전 제어, 센서 연동을 작게나마 직접 다뤄본 경험이라고 연결합니다. 다만 신입으로서 부족한 부분을 배우고 개선하겠다는 태도로 마무리합니다. |
