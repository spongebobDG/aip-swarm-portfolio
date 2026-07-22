# What I Did

> 목적: 본인 역할, 팀 전체 구현, 확인 필요 항목을 분리해 면접에서 방어 가능한 표현으로 정리한다.

## 내가 말할 수 있는 핵심 역할

| 영역 | 내가 한 일 | 면접 표현 |
|---|---|---|
| 프로젝트 분석 | 패키지, launch, message, dashboard, perception, firmware 경로를 읽고 구조를 분리했다 | "코드 기준으로 전체 데이터 흐름을 분석했습니다." |
| ROS2 통신 정리 | `heartbeat`, `/fleet/status`, `/fleet/override`, `cmd_vel`, `estop`, Nav2 Action 흐름을 표로 정리했다 | "Topic/Action/Message 계약을 기준으로 설명할 수 있게 만들었습니다." |
| 웹관제 정리 | FastAPI backend, WebSocket, 정적 HTML/JavaScript UI의 역할을 나눠 문서화했다 | "브라우저가 ROS2에 직접 붙지 않고 Python backend가 bridge 역할을 하는 구조입니다." |
| 비전/열화상 정리 | Vision Pi HTTP bridge, ROS2 image topic, thermal alert, dashboard 표시 흐름을 분리했다 | "영상 입력부터 alert와 관제 표시까지의 흐름을 정리했습니다." |
| 서브차량 제어 정리 | `twist_mux`, override, coordinator, autonomy, serial bridge 흐름을 비교했다 | "여러 제어 입력의 우선순위와 최종 `cmd_vel` 흐름을 설명할 수 있습니다." |
| 시연 자료 준비 | Docker sim 기준 캡처/GIF, README, 포트폴리오 docs, 면접 PDF를 정리했다 | "시연 가능한 범위와 확인 필요한 범위를 분리했습니다." |

## 팀 전체 구현으로 구분할 것

- 메인 AGV의 하위 차량 SW와 실차 작업 환경 전체
- Nav2/SLAM 자체 알고리즘 구현
- TurtleBot3 또는 custom vehicle 하위 driver
- 실제 현장 네트워크/DDS 운영 검증
- 카메라 하드웨어 장착과 Vision Pi 현장 운용

## 확인 필요로 남길 것

- 실차 3대가 동시에 장시간 자율 군집 주행을 완료했는지
- `aip3` STS3215 driver가 어느 수준까지 구현/검증됐는지
- YOLOv8이 실제 화재/연기 모델로 검증됐는지
- E-Stop이 모든 실차에서 모터 정지까지 반복 검증됐는지
- 실제 시연 영상에서 사용한 camera source와 FPS/latency

## 안전한 30초 답변

제가 맡은 부분은 로봇 개별 알고리즘을 완성했다고 말하기보다, 팀프로젝트의 ROS2 통신 구조와 웹관제, 비전/열화상 연동, 서브차량 제어 흐름을 코드 근거로 분석하고 문서화한 것입니다. 특히 `/<vehicle>/heartbeat`, `/fleet/status`, `/fleet/override`, `cmd_vel` 같은 계약이 어떻게 dashboard와 차량 제어로 이어지는지 설명할 수 있게 정리했습니다. 실차 군집 주행이나 YOLO 성능처럼 증빙이 부족한 부분은 확인 필요로 분리했습니다.

## 위험한 표현과 수정

| 위험한 표현 | 수정 표현 |
|---|---|
| "완전 자율 군집주행을 구현했습니다" | "군집 관제와 통신 구조를 구성했고, 완전한 실차 군집 검증은 확인 필요입니다." |
| "YOLO 화재 탐지를 완성했습니다" | "YOLOv8 연동 코드는 있으나 모델과 정확도 검증은 확인 필요입니다." |
| "제가 전체 로봇 시스템을 혼자 만들었습니다" | "팀프로젝트에서 통합 구조 분석, 문서화, 시연 자료 준비를 담당했습니다." |
| "상용 FMS 수준입니다" | "포트폴리오용 관제 구조와 시뮬레이션 데모입니다." |
