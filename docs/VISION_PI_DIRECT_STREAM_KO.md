# Vision Pi 직접 웹관제 스트리밍 런북

최신 실측 스냅샷은 [`docs/VISION_PI_STATUS_2026-06-28_KO.md`](VISION_PI_STATUS_2026-06-28_KO.md)를 먼저 본다.

대상 Vision Pi는 메인 차량 CPU를 거치지 않고 웹관제가 직접 HTTP로 영상을 가져온다.
RGB 카메라와 MLX thermal은 같은 Pi 서비스에서 뜨지만, 웹관제 URL과 표시 주기는 서로 독립적으로 조정한다.

## 현재 실측값

측정 기준: Vision Pi `192.168.0.108`, RGB `320x240`, thermal `240x180`, 웹관제 JPEG polling `RGB 300ms`, `thermal 1000ms`.

| 항목 | 값 |
|---|---:|
| RGB 실제 캡처 | 약 `7.8 fps` |
| thermal 실제 수신 | 약 `3.9 fps` |
| RGB frame age | 약 `0.10 s` |
| thermal frame age | 약 `0.18 s` |
| Pi 전체 CPU busy | 약 `28%` |
| preview Python 프로세스 | 한 코어 기준 약 `84%` |
| `v4l2-ctl` 캡처 프로세스 | 한 코어 기준 약 `19%` |
| 온도 | 약 `52.5°C` |
| throttled | `0x0` |

해석: 한 코어 하나를 거의 쓰는 구조지만 Pi 전체 4코어 기준으로는 대략 `25~30%` 수준이다. 현재 부하는 RGB raw Bayer 변환이 대부분이며, thermal은 UART 입력 한계로 약 `4 fps`가 상한이다.

## 중앙 웹관제 변수

중앙 대시보드가 시작될 때 아래 환경변수를 읽는다. 실차에서 팀원이 가장 안전하게 바꿀 수 있는 값이다.

| 변수 | 의미 | 예시 |
|---|---|---|
| `AIP_VISION_STREAM_URLS` | RGB direct stream URL 목록 | `aip2=http://192.168.0.108:8081/rgb.jpg` |
| `AIP_THERMAL_STREAM_URLS` | thermal direct stream URL 목록 | `aip2=http://192.168.0.108:8081/thermal.jpg` |
| `AIP_RGB_POLL_MS` | RGB JPEG polling 간격. `0`이면 polling 비활성 | `300` |
| `AIP_THERMAL_POLL_MS` | thermal JPEG polling 간격. `0`이면 polling 비활성 | `1000` |
| `AIP_VISION_POLL_MS` | RGB/thermal 공통 fallback 값 | `0` |

추천 저지연 fallback:

```bash
export AIP_VISION_STREAM_URLS='aip2=http://192.168.0.108:8081/rgb.jpg'
export AIP_THERMAL_STREAM_URLS='aip2=http://192.168.0.108:8081/thermal.jpg'
export AIP_RGB_POLL_MS=300
export AIP_THERMAL_POLL_MS=1000
ros2 launch aip_fleet_bringup central.launch.py
```

MJPEG 직접 연결을 쓰려면 polling을 `0`으로 두고 URL만 `.mjpg`로 바꾼다.

```bash
export AIP_VISION_STREAM_URLS='aip2=http://192.168.0.108:8081/rgb.mjpg'
export AIP_THERMAL_STREAM_URLS='aip2=http://192.168.0.108:8081/thermal.mjpg'
export AIP_RGB_POLL_MS=0
export AIP_THERMAL_POLL_MS=0
```

## Docker dashboard 사용 시

`docker/central/.env.example`을 `docker/central/.env`로 복사한 뒤 아래처럼 바꾼다.

```dotenv
AIP_VISION_STREAM_URLS=aip2=http://192.168.0.108:8081/rgb.jpg
AIP_THERMAL_STREAM_URLS=aip2=http://192.168.0.108:8081/thermal.jpg
AIP_RGB_POLL_MS=300
AIP_THERMAL_POLL_MS=1000
```

이후:

```bash
cd ~/aip_swarm_ws/docker/central
docker compose --profile docker-dashboard up -d dashboard
```

## URL query 임시 override

로컬 테스트에서는 환경변수 없이 브라우저 주소로도 바꿀 수 있다. query 값이 있으면 환경변수보다 우선한다.

```text
http://127.0.0.1:8092/?no_ws=1&rgb_poll_ms=300&thermal_poll_ms=1000&vision_aip2=http%3A%2F%2F192.168.0.108%3A8081%2Frgb.jpg&thermal_aip2=http%3A%2F%2F192.168.0.108%3A8081%2Fthermal.jpg
```

## Vision Pi 서비스 조정 기준

Pi에서는 하나의 `aip-vision-preview.service`가 RGB와 thermal을 함께 띄운다. 하지만 옵션은 분리되어 있다.

RGB 영향이 큰 옵션:

- `--fps`
- `--rgb-raw-max-fps`
- `--rgb-preview-width`
- `--rgb-preview-height`
- `--rgb-jpeg-quality`
- `--rgb-percentile-stride`

thermal 영향 옵션:

- `--thermal-preview-width`
- `--thermal-preview-height`
- `--thermal-jpeg-quality`
- `--thermal-baud`
- `--thermal-flip-y`

현재 추천 Pi 값:

```text
RGB 320x240, --fps 8, --rgb-raw-max-fps 8, --rgb-jpeg-quality 65
thermal 240x180, --thermal-baud 115200, --thermal-jpeg-quality 55
```

주의:

- `AIP_RGB_POLL_MS=125`처럼 너무 빠르게 당기면 HTTP 요청이 밀려 오히려 `0.4~1.5s` 지연이 생길 수 있다.
- RGB를 `10 fps` 이상으로 올리면 한 코어가 100%에 가까워질 수 있다.
- thermal 10fps는 웹관제 값만으로는 불가능하다. 현재 MLX UART 115200 출력이 약 `4 fps`로 제한된다.

## Thermal UART 최대화 테스트 결과

2026-06-28 Vision Pi에서 UART 수신 병목을 줄이는 패치를 적용했다.

적용 내용:

- `thermal_uart.py`에서 GY-MCU90640 계열 `ZZ 02 06` 프레임 파싱 시 불필요한 bytes 복사를 줄였다.
- 한 번의 read 후 버퍼에 완성된 프레임이 여러 개 있으면 모두 drain하도록 바꿨다.
- UART 수신 스레드에서 매 프레임 JPEG를 만들지 않고, HTTP 클라이언트가 요청할 때 최신 프레임을 lazy encode하도록 변경했다.
- systemd unit에 `--thermal-protocol mlx_uart_zz`를 추가해 `auto` 탐색 비용을 줄였다.

결과:

| 테스트 | 결과 |
|---|---:|
| 패치 후 115200 자동출력 | 약 `3.9 fps`, 약 `6111 B/s` |
| 460800bps 일시 전환 시도 | `ZZ 02 06` 프레임 0건 |
| 115200에서 rate code `0..7` 스윕 | 모두 약 `3.83 fps` |
| 프레임 요청 명령 반복 `4..30Hz` | 모두 약 `3.71 fps` |
| 8Hz/460800 설정 저장 후 Pi 재부팅 | 460800 프레임 `0건`, 115200에서 약 `3.7 fps` |
| 자동송신 중지 후 8Hz/460800 재시도 | 460800 프레임 `0건`, 115200 복구 후 약 `4.0 fps` |

판단:

- 현재 병목은 Pi 수신 코드가 아니라 thermal 송신 보드 펌웨어/출력 모드 쪽이다.
- 115200bps에서 들어오는 실제 바이트량이 약 `6.1 kB/s`이고, `ZZ 02 06` 한 프레임이 약 `1544 B`라서 실제 송신은 약 `4 fps`다.
- 매뉴얼상 명령은 `8Hz=A5 25 04 CE`, `460800=A5 15 03 BD`, `save=A5 65 01 0B`이지만 현재 보드는 이 조합을 저장/재부팅 후에도 460800 프레임으로 출력하지 않았다.
- UART로 `8~10 fps`가 필요하면 현재 송신 보드 펌웨어가 고속 baud/update rate를 실제 지원하는지 제조사 GUI/펌웨어로 먼저 확인해야 한다.
- 더 확실한 고프레임은 UART 보드 경유 대신 MLX90640 직접 I2C 경로를 별도로 검증하는 방향이 안전하다.

복구 정보:

- Pi 백업 파일:
  - `/home/vision/aip_vision_ws/aip_vision/thermal_uart.py.bak_uartmax_20260628_173900`
  - `/etc/systemd/system/aip-vision-preview.service.bak_uartmax_20260628_173900`
- 현재 서비스는 정상 동작 중이며 `--thermal-baud 115200 --thermal-protocol mlx_uart_zz` 상태다.
- 8Hz/460800 저장 테스트 후 안전 복구 완료:
  - `A5 35 01 DB`, `A5 25 03 CD`, `A5 15 02 BC`, `A5 35 02 DC`, `A5 65 01 0B`
  - systemd unit도 `--thermal-baud 115200`으로 복구했다.

추가 고속 설정 재시도:

- 자동 출력 중 명령이 흘려질 가능성을 배제하기 위해 먼저 `A5 35 01 DB`로 query/single-output 모드로 전환했다.
- 115200bps에서 2초간 추가 자동 프레임이 없음을 확인한 뒤 `8Hz=A5 25 04 CE`, `460800=A5 15 03 BD`를 송신했다.
- 직후 460800bps로 다시 열어서 `query -> 8Hz -> auto`를 송신했지만 수신 바이트와 `ZZ 02 06` 프레임 모두 0건이었다.
- 115200bps에서 `4Hz -> auto -> save`로 복구했고, service 재시작 후 RGB 약 `7.8 fps`, thermal 약 `4.0 fps`, `last_error=null`을 확인했다.
- Pi UART 경로는 `/dev/serial0 -> /dev/ttyAMA0`이고 `disable-bt`가 적용된 PL011 UART라서, 이번 실패는 Pi UART 성능 문제가 아니라 송신 보드가 460800 설정을 적용하지 않는 문제로 판단한다.

### UART 8fps 판단

UART가 원천적으로 불가능한 것은 아니다. 다만 현재 조건에서 `115200bps` 자동 출력만으로는 전체 `32x24` thermal frame `8fps`를 안정적으로 보낼 수 없다.

- `ZZ 02 06` binary frame은 header 4B + 768개 uint16 = 약 `1540~1544 B/frame`.
- `8fps`이면 약 `12.3 kB/s`가 필요하다.
- `115200 8N1`의 이론상 payload 한계는 약 `11.5 kB/s`라 여유가 없고, 실제 오버헤드/간격을 고려하면 부족하다.
- 현재 실측도 약 `6.1 kB/s`, 즉 `3.8~4.0 fps`로 일관된다.

따라서 UART로 8fps에 접근하려면 보드가 실제로 `460800bps` 이상에서 `ZZ 02 06` 프레임을 출력해야 한다.

추가 검증:

- 공개 ESP8266 GY-MCU90640 구현과 같은 순서도 시험했다.
  - `A5 55 01 FB`로 emissivity/sync 응답 확인.
  - `115200 -> 8Hz -> manual -> save` 저장.
  - manual 모드에서 자동 프레임 0건 확인.
  - `auto` 전환 후에도 `115200bps`에서는 약 `3.875 fps`.
- `8Hz -> 460800 -> manual/save` 뒤 후보 baud를 스캔했다.
  - `9600`, `19200`, `38400`, `57600`, `115200`, `230400`, `250000`, `256000`, `460800`, `500000`, `921600`, `1000000`.
  - 정상 `ZZ 02 06` 프레임은 `115200`에서만 확인됐다.
- 이 결과는 `460800` 설정이 즉시 적용되지 않거나, 저장 후 보드 MCU 전원 완전 재인가가 필요하다는 쪽에 가깝다.

준비한 UART 보드 도구:

```bash
python3 scripts/mlx90640_uart_board_tool.py measure --baud 115200 --duration 5
python3 scripts/mlx90640_uart_board_tool.py stage-high
python3 scripts/mlx90640_uart_board_tool.py scan --send-auto --duration 5
python3 scripts/mlx90640_uart_board_tool.py restore-safe
```

Vision Pi 배포 경로:

```bash
python3 /home/vision/aip_vision_ws/tools/mlx90640_uart_board_tool.py measure --baud 115200 --duration 5
```

`stage-high`는 보드에 `8Hz/460800/auto/save`를 저장한다. 이 명령 뒤에는 Pi Linux 재부팅이 아니라 GY-MCU90640 보드 MCU 전원이 실제로 꺼졌다 켜져야 한다. Pi GPIO 5V/3.3V로 전원을 공급 중이면 `sudo reboot`만으로는 보드 전원이 끊기지 않을 수 있다.

현재 Vision Pi 준비 상태:

- `aip-vision-preview.service`는 autobaud wrapper 경유로 실행한다.
  - `/home/vision/aip_vision_ws/tools/vision_preview_autobaud.py`
  - systemd argument: `--thermal-baud auto`
- wrapper는 service 시작 시 `460800`을 먼저 짧게 검사하고, 안 잡히면 `115200`으로 fallback한다.
- 전원 재인가 전 현재 상태에서는 wrapper가 `115200`을 선택했고 thermal 약 `4.0 fps`로 정상 동작한다.
- `mlx90640_uart_board_tool.py stage-high`로 `8Hz/460800/auto/save` 저장 명령은 넣어둔 상태다.

물리 전원 재인가 후 검증:

```bash
sudo systemctl restart aip-vision-preview.service
journalctl -u aip-vision-preview.service -n 30 --no-pager
curl -s http://127.0.0.1:8081/status.json
```

성공이면 journal에 `selected thermal baud 460800`이 찍히고 `/status.json`의 `thermal.baud`가 `460800`, `thermal.frames` 증가율이 대략 `7~8 fps` 근처여야 한다. 실패하면 wrapper가 다시 `115200`을 선택하며 약 `4 fps`로 계속 동작한다.

검증 결과:

- `stage-high` 후 GY-MCU90640 보드/PI 전원이 실제로 재인가되자 autobaud가 `460800`을 선택했다.
- journal:
  - `vision_preview_autobaud: selected thermal baud 460800`
  - autobaud scan 기준 `plausible_fps=8.0`
- web preview `/status.json` 10초 계측:
  - RGB 약 `7.9 fps`
  - thermal 약 `7.8 fps`
  - `thermal.baud=460800`
  - `thermal.protocol=mlx_uart_zz`
  - `thermal_bytes_per_sec` 약 `12043 B/s`
  - `last_error=null`
- `/rgb.jpg`, `/thermal.jpg`, `/thermal.mjpg` 모두 HTTP 200 정상 응답.
- 최신 autobaud wrapper 재배포 후 service restart 검증:
  - journal `selected thermal baud 460800`
  - autobaud scan `plausible_fps=8.4`
  - web preview 8초 계측 thermal 약 `7.875 fps`

결론:

- UART로 `8fps`에 가까운 thermal stream은 가능하다.
- 필수 조건은 `8Hz/460800/auto/save` 설정 후 GY-MCU90640 보드 MCU 전원을 완전히 껐다 켜는 것이다.
- Pi reboot 또는 service restart만으로는 보드 MCU 전원 재인가가 보장되지 않아 `115200/4fps` 상태가 유지될 수 있다.

## MLX90640 직접 I2C 8fps 경로

UART 송신 보드가 4Hz로 고정되어 보일 때 8fps에 가장 가까운 현실적인 경로는 GY-MCU90640 보드의 MCU를 우회하고 MLX90640을 Pi I2C에서 직접 읽는 것이다.

현재 확인:

- Vision Pi에는 I2C가 켜져 있다.
  - `/boot/firmware/config.txt`: `dtparam=i2c_arm=on`
  - `/dev/i2c-0`, `/dev/i2c-1`, `/dev/i2c-10`, `/dev/i2c-22` 존재
  - `vision` 사용자는 `i2c` 그룹에 포함
- `i2c-tools`, `python3-smbus` 설치 완료.
- `i2cdetect` 결과 MLX90640 기본 주소 `0x33`은 보이지 않는다.
  - `/dev/i2c-1`: 장치 없음
  - `/dev/i2c-10`, `/dev/i2c-22`: `0x36`은 `UU`로 표시되나, 이는 Pi 카메라/시스템 장치로 보이며 MLX90640 직접 연결로 쓰지 않는다.

직접 I2C로 전환하려면 물리 변경이 필요하다.

1. GY-MCU90640 보드의 `PS` 핀을 `GND`에 연결해 MCU UART 모드가 아니라 I2C pass-through 모드로 전환한다.
2. MLX/GY 보드의 `SDA`를 Pi GPIO2/SDA1, `SCL`을 Pi GPIO3/SCL1에 연결한다.
3. 전원은 보드 사양에 맞춰 3.3V 또는 5V를 사용하되, Pi I2C 라인에 5V가 직접 걸리지 않게 확인한다.
4. 재전원 후 다음 명령으로 `0x33`이 보이는지 확인한다.

```bash
i2cdetect -y 1
```

`0x33`이 보이면 그 다음 단계에서 직접 I2C reader를 붙여 `8Hz` 설정과 실제 frame rate를 측정한다. `0x33`이 보이지 않으면 소프트웨어에서 8fps를 만들 수 없다.

준비된 검증 스크립트:

```bash
python3 scripts/mlx90640_i2c_rate_probe.py --bus 1 --addr 0x33 --rate-code 4 --duration 15
```

Vision Pi에는 같은 스크립트를 아래 경로에도 배포했다.

```bash
python3 /home/vision/aip_vision_ws/tools/mlx90640_i2c_rate_probe.py --bus 1 --addr 0x33 --rate-code 4 --duration 15
```

성공 기준:

- `i2cdetect -y 1`에서 `0x33` 표시.
- probe 출력의 `control_after` rate가 `4(8Hz)`.
- probe 출력의 `fps`가 대략 `7~8` 근처.

현재 배선에서의 probe 결과:

```text
MLX90640 not detected at /dev/i2c-1 addr=0x33: [Errno 121] Remote I/O error
Check that the GY-MCU90640 board is in I2C pass-through mode, PS is tied to GND, and SDA/SCL are wired to the Pi.
```
