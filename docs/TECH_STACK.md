# Tech Stack

> 원칙: 코드나 설정 파일에서 확인되는 기술만 정리한다. 이름만 등장하거나 실행 검증이 부족한 항목은 확인 필요로 표시한다.

## 확인된 기술

| 분류 | 기술 | 근거 | 설명 수준 |
|---|---|---|---|
| Robot Middleware | ROS2 Humble, `rclpy`, `rclcpp` | `src/*/package.xml`, Python/C++ node | Topic, Service, Action 흐름 설명 가능 |
| Navigation | Nav2, SLAM Toolbox, AMCL 설정, `twist_mux` | launch/config, docs | 직접 알고리즘 구현이 아니라 연동/설정 중심 |
| ROS2 Interfaces | custom msg/srv, `geometry_msgs`, `nav_msgs`, `sensor_msgs`, `std_msgs`, `nav2_msgs` | `src/aip_fleet_msgs`, package deps | message 계약 설명 가능 |
| Dashboard Backend | FastAPI, Uvicorn, WebSocket | `aip_fleet_dashboard` | ROS2와 browser 사이 bridge 역할 |
| Dashboard Frontend | HTML, CSS, JavaScript | `src/aip_fleet_dashboard/static/index.html` | 정적 UI, Canvas, WebSocket client |
| Foxglove 보조 패널 | React, TypeScript, Foxglove extension | `src/aip_fleet_foxglove_panels` | 메인 dashboard와 별도 보조 UI |
| Vision | OpenCV, NumPy, `cv_bridge`, ROS2 Image/CompressedImage | `aip_fleet_perception`, `scout_localizer_node.py`, dashboard backend | localizer는 `cv_bridge`, 일부 perception/dashboard 경로는 직접 buffer 변환 |
| AI/Detection | Ultralytics YOLOv8 optional import | `central_fusion_node.py` | 모델/정확도는 확인 필요 |
| Simulation | Python 2D kinematic sim, Docker sim | `src/aip_fleet_sim`, `docker/sim` | 포트폴리오 데모 중심 |
| Firmware/Embedded | ESP32, PlatformIO, Arduino-style C++ | `firmware/main_agv`, `firmware/scout` | main AGV serial/motor path 확인, scout는 TODO 존재 |
| Transport/Network | FastDDS, Discovery Server config, micro-ROS Agent | `config/`, `docker/central`, docs | 운영 이력은 문서 기준 |
| Deployment | Docker, Docker Compose | `docker/sim`, `docker/central` | sim 실행과 central stack 구성 |
| Logging/Telemetry | rosbag2, InfluxDB optional | docs, telemetry package | 운영 보조 기능 |

## 코드에서 확인되지 않거나 주의할 기술

| 기술/표현 | 상태 | 면접에서의 안전한 말 |
|---|---|---|
| rosbridge/roslibjs | 메인 dashboard 코드에서는 사용 확인 안 됨 | "현재는 FastAPI backend가 bridge 역할을 합니다." |
| Vue | 사용 확인 안 됨 | "Vue는 사용했다고 말하지 않습니다." |
| React | Foxglove extension에서 확인됨 | "메인 dashboard가 아니라 보조 Foxglove panel에 사용됐습니다." |
| YOLO fire/smoke 성능 | 모델/검증 확인 필요 | "연동 코드가 있고 성능 검증은 추가 확인이 필요합니다." |
| MLOps | 이 저장소의 핵심 구현으로 보기 어려움 | "면접에서는 Docker/테스트/문서화 중심으로 말합니다." |

## 직무 연결 요약

- 클로봇 관점: ROS2, 센서 연동, 제어 명령, 웹관제, 테스트/배포 설명에 강점이 있다.
- 로보티즈 관점: ROS2, Nav2/Localization 이해, Linux/Docker, 모바일로봇 테스트와 문서화 경험으로 연결한다.
- 신입 관점: "능숙"보다 "코드를 읽고 구조를 설명하며 부족한 부분을 확인 필요로 분리할 수 있음"을 강조한다.
