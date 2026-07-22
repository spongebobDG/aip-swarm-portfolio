# Vision Pi 8fps 직접 스트리밍 현재 상태

작성 기준: 2026-06-28 21:59 KST

이 문서는 Vision Pi를 메인 차량 CPU 경유 없이 웹관제에서 직접 보는 현재 검증 상태를 팀원에게 공유하기 위한 스냅샷이다. Wi-Fi 비밀번호와 계정 비밀번호는 저장소에 기록하지 않는다.

## 요약

- Vision Pi는 독립 SBC로 RGB 카메라와 MLX thermal을 직접 HTTP로 제공한다.
- 메인 차량 ROS/CPU를 경유하지 않으므로 주행 제어 CPU 부하와 영상 부하를 분리할 수 있다.
- 현재 주행 확인용 권장 방식은 `.mjpg` 직접 스트림이다.
- JPG polling도 지원하지만, 8fps 주행 확인에는 MJPEG가 더 부드럽고 요청 수가 적다.

## 현재 네트워크

| 항목 | 값 |
|---|---|
| Wi-Fi SSID | `jdedu9807` |
| Vision Pi IP | `192.168.0.7` |
| Vision Pi MAC | `d8:3a:dd:eb:46:f9` |
| 서비스 포트 | `8081` |
| 서비스 | `aip-vision-preview.service` |
| 서비스 상태 | `active`, `enabled` |

권장: 공유기 DHCP 예약에서 MAC `d8:3a:dd:eb:46:f9`를 고정 IP로 묶어둔다. 현재 `192.168.0.7`은 DHCP 주소라 네트워크 재접속 후 바뀔 수 있다.

## 웹관제 연결값

주행 중 확인용 권장 URL:

```text
RGB:     http://192.168.0.7:8081/rgb.mjpg
Thermal: http://192.168.0.7:8081/thermal.mjpg
Status:  http://192.168.0.7:8081/status.json
```

로컬 정적 웹관제 테스트 URL:

```text
http://127.0.0.1:8092/?no_ws=1&vision_aip2=http%3A%2F%2F192.168.0.7%3A8081%2Frgb.mjpg&thermal_aip2=http%3A%2F%2F192.168.0.7%3A8081%2Fthermal.mjpg
```

중앙 웹관제 환경변수 예시:

```bash
export AIP_VISION_STREAM_URLS='aip2=http://192.168.0.7:8081/rgb.mjpg'
export AIP_THERMAL_STREAM_URLS='aip2=http://192.168.0.7:8081/thermal.mjpg'
export AIP_RGB_POLL_MS=0
export AIP_THERMAL_POLL_MS=0
```

## 실측 프레임

`/status.json` 6초 샘플 기준:

| 항목 | 실측 |
|---|---:|
| RGB fps | 약 `7.87 fps` |
| Thermal fps | 약 `7.67 fps` |
| RGB frame age | 약 `0.058 s` |
| Thermal frame age | 약 `0.112 s` |
| Thermal baud | `460800` |
| Thermal protocol | `mlx_uart_zz` |

이전 짧은 샘플에서는 RGB 약 `7.8 fps`, thermal 약 `8.1 fps`도 확인했다. thermal은 순간 샘플 구간에 따라 `7.6~8.1 fps` 정도로 보면 된다.

## 영상 설정

| 항목 | 값 |
|---|---|
| RGB raw capture | `v4l2-gb10-stream` |
| RGB raw input | `640x480`, `GB10` |
| RGB target fps | `8` |
| RGB raw max fps | `8` |
| RGB web preview | `320x240` |
| RGB JPEG quality | `65` |
| Thermal web preview | `240x180` |
| Thermal JPEG quality | `55` |
| Thermal UART | `/dev/serial0`, `460800 baud` |

현재 systemd 실행 인자 핵심:

```text
--fps 8
--rgb-raw-max-fps 8
--raw-capture-mode stream
--rgb-preview-width 320
--rgb-preview-height 240
--rgb-jpeg-quality 65
--thermal-baud auto
--thermal-protocol mlx_uart_zz
--thermal-preview-width 240
--thermal-preview-height 180
--thermal-jpeg-quality 55
```

## CPU, 메모리, 온도

측정 기준: MJPEG direct stream을 브라우저에서 열어둔 상태.

| 항목 | 측정값 |
|---|---:|
| Pi load average | `1.77 / 1.80 / 1.16` |
| Pi 전체 idle | 약 `64~69%` |
| Pi 전체 busy | 약 `31~36%` |
| Vision Python 프로세스 | 한 코어 기준 약 `90~94%` |
| 서비스 메모리 | 약 `48 MB` |
| 전체 메모리 available | 약 `3.3 GiB` |
| 온도 | 약 `57.4 C` |

해석:

- 8fps RGB + 8fps thermal은 현재 Python 구현에서 실사용 가능한 상한에 가깝다.
- Pi 전체로는 아직 여유가 있지만, Vision Python 프로세스는 한 코어를 꽤 강하게 사용한다.
- 장시간 주행 테스트에서는 온도, 전원, Wi-Fi 품질을 같이 관찰해야 한다.

## 운영 권장

1. 주행 확인 기본값은 MJPEG direct stream을 사용한다.
2. 브라우저/네트워크에서 MJPEG 버퍼 지연이 생길 때만 JPG polling fallback을 사용한다.
3. JPG polling fallback 예시는 아래 정도를 먼저 쓴다.

```text
rgb_poll_ms=300
thermal_poll_ms=300
```

4. `rgb_poll_ms=125`, `thermal_poll_ms=125`는 8fps에 가깝지만 HTTP 요청이 많아져 Pi와 브라우저가 밀릴 수 있다.
5. 더 안정성이 필요하면 fps를 올리기보다 RGB 품질을 `65 -> 55`로 낮추거나 해상도는 `320x240`으로 유지한다.
6. 여러 명이 동시에 스트림을 열면 Pi HTTP/JPEG 부하와 Wi-Fi 부하가 늘어 딜레이가 커질 수 있다.

## 장애 확인 순서

Pi에서:

```bash
systemctl status aip-vision-preview.service --no-pager -l
journalctl -u aip-vision-preview.service -n 30 --no-pager
curl -s http://127.0.0.1:8081/status.json
```

PC에서:

```bash
curl http://192.168.0.7:8081/status.json
curl http://192.168.0.7:8081/rgb.jpg
curl http://192.168.0.7:8081/thermal.jpg
```

`status.json`에서 확인할 핵심:

- `camera.frames`가 증가하는지
- `thermal.frames`가 증가하는지
- `thermal.baud`가 `460800`인지
- `last_error`가 `null`인지

## 통합 시 주의

- 이 변경은 메인 차량 소프트웨어를 수정하지 않는다.
- 영상은 Pi HTTP stream으로 웹관제가 직접 받는다.
- ROS2로는 필요 시 저율 상태, 이벤트 프레임, bbox 결과, alert만 연결하는 구성이 안전하다.
- bbox/YOLO는 Pi에서 돌리지 않고 중앙 PC 또는 웹관제 쪽에서 처리하는 방향이 메인 차량 CPU 보호에 유리하다.
- PR 리뷰 시 실제 운영 IP는 팀 네트워크 DHCP 예약 상태에 맞게 바꿔야 한다.
