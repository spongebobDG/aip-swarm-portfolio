# AIP Swarm — ESP32 펌웨어

차량 종류별 ESP32 펌웨어 소스.

| 디렉토리 | 차량 | 통신 방식 | 빌드 도구 |
|---|---|---|---|
| [`main_agv/`](main_agv/) | 메인 AGV (자작 BTS7960 구동계 + MG996R 서보암) | UART 시리얼 브리지 (`/dev/aip_esp32` ↔ RPi4B) | Arduino IDE |
| [`scout/`](scout/) | Scout 1 · Scout 2 (TurtleBot3 Burger + STS3215 서보) | micro-ROS over UDP (Wi-Fi → 중앙 PC) | PlatformIO |

## 차량별 통신 아키텍처

```
[main_agv ESP32] ──UART 115200──► [RPi4B serial_bridge.py] ──ROS2──► fleet
[scout_N ESP32]  ──Wi-Fi UDP────► [중앙PC micro-ROS Agent]  ──ROS2──► fleet
```

## 주의사항

- `firmware/scout/secrets.ini` 는 `.gitignore` 에 등재 — 절대 커밋하지 않음.
- `main_agv/config.h` 의 `BUZZER_PIN` 을 보드 실제 핀으로 수정 후 플래시할 것 (기본값 GPIO 2).
- 실차 launch 에서 `use_sim_time: false` 필수 (시뮬 파라미터 사용 금지).
