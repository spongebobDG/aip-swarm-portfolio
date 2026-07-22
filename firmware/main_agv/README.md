# AIP Main AGV — ESP32 펌웨어

## 하드웨어

| 항목 | 사양 |
|---|---|
| MCU | ESP32 (240 MHz dual-core) |
| 모터 드라이버 | BTS7960 × 2 (좌/우 바퀴) |
| 서보 | MG996R × 4 (4축 서보암) |
| 엔코더 | 증분형 700 PPR × 2 |
| 시리얼 | UART0 115200 8N1 → RPi4B (`/dev/aip_esp32`) |
| 부저 | 패시브 부저 (LEDC PWM, `BUZZER_PIN` 지정) |

## 핀맵 요약

```
// 모터 (BTS7960)
M1 : RPWM=21 LPWM=19 REN=18 LEN=17  ENC_A=23 ENC_B=22  (좌)
M2 : RPWM=25 LPWM=26 REN=27 LEN=14  ENC_A=32 ENC_B=33  (우)

// 서보 (MG996R, LEDC 50Hz)
서보 0-3 : GPIO 16 / 4 / 15 / 13

// 부저 (LEDC 채널 8)
BUZZER_PIN = 2  ← config.h 에서 실제 핀으로 수정
```

## 시리얼 프로토콜

패킷 형식: `AA 55 [type] [payload...] [XOR_cks]`  
XOR 체크섬: `type ⊕ payload[0] ⊕ ... ⊕ payload[N-1]`

| 타입 | 방향 | payload | 설명 |
|---|---|---|---|
| `0x01` CMD_VEL | RPi→ESP32 | `<ff` (8B) linear_m/s · angular_rad/s | 주행 명령 |
| `0x02` MOTOR_FB | ESP32→RPi | `<ll` (8B) enc_L · enc_R | 엔코더 누적 틱 (20 Hz) |
| `0x03` SERVO | RPi→ESP32 | `4×uint8` | 서보 각도 0-180° |
| `0x04` SERVO_FB | ESP32→RPi | `4×uint8` | 현재 서보 각도 (20 Hz) |
| `0x05` STATUS | ESP32→RPi | `<IHHHH` (12B) | 업타임·플래그·bad_pkts·loop_hz·heap_kb (1 Hz) |
| `0x06` SERVO_RELEASE | RPi→ESP32 | `1B` mode | PARK_POSE 후 서보 전체 detach |
| `0x07` RESET | RPi→ESP32 | `1B` mode=0 | ESP32 소프트 리셋 (`esp_restart()`) |
| `0x08` BEEP | RPi→ESP32 | `1B` pattern | 비프음 (0=단음 1=이중 2=부팅 3=오류) |

## 빌드 & 플래시

**Arduino IDE (권장)**
1. Arduino IDE 2.x + ESP32 보드 패키지 (`arduino-esp32 v2.x`) 설치
2. `firmware/main_agv/aip_firmware.ino` 열기
3. 보드: `ESP32 Dev Module` · 포트 선택
4. `config.h` 에서 `BUZZER_PIN` 을 실제 연결 핀으로 수정
5. 업로드

**주의**: `arduino-esp32 v3.x` 는 LEDC API 변경으로 컴파일 에러 발생 (`config.h` 상단 에러 가드 있음). v2.x 고정 사용.

## RPi 연동 (`serial_bridge.py`)

RPi4B 의 `~/aip_ws/src/aip_base/aip_base/serial_bridge.py` 가 이 펌웨어의 시리얼 상대방.

```bash
# 부팅 비프 확인 후 RPi에서 리셋 명령
ros2 topic pub --once /aip1/esp32_reset std_msgs/msg/Empty "{}"

# 비프음 패턴 테스트
ros2 topic pub --once /aip1/esp32_beep std_msgs/msg/UInt8MultiArray "{data: [2]}"
```

serial_bridge.py 수정 시 RPi 에서 재빌드 필요:
```bash
cd ~/aip_ws && colcon build --symlink-install --packages-select aip_base
```

## 소스 파일 구조

| 파일 | 역할 |
|---|---|
| `aip_firmware.ino` | 메인 진입점. setup() / loop() |
| `config.h` | 핀맵·물리 파라미터·패킷 타입 상수 |
| `protocol.h/cpp` | 패킷 파서·핸들러 등록·TX 함수 |
| `motor_control.h/cpp` | 속도 루프 (FF+PI), watchdog, 엔코더 |
| `servo_control.h/cpp` | 서보 모션 프로파일, detach 시퀀스 |
| `status_monitor.h/cpp` | STATUS 패킷 주기 발행, 루프 Hz 계측 |
| `buzzer.h/cpp` | 비블로킹 부저 상태머신 (4패턴) |
| `firmware_test.py` | PC-side 프로토콜 단위 테스트 스크립트 |
