# Ubuntu 중앙 PC 설정 (실제 배포)

Ubuntu 22.04 머신을 AIP 스웜의 **중앙 PC** 로 세팅하는 최단 경로.
전용 Wi-Fi AP (`AIP_FLEET`, 192.168.0.0/24) 가 준비되어 있고, 이 머신이
**192.168.0.9** 으로 DHCP 예약 받았다고 가정.

두 가지 모드:
- **Mode A**: Docker Compose 기반 production 스택 (FastDDS DS + µROS Agent + Foxglove Br + rosbag2 + InfluxDB)
- **Mode B**: 로컬 시뮬 컨테이너만 (차량 없이 E2E, Windows 가이드와 동일 이미지)

개발 테스트는 Mode B → 실기 통합은 Mode A 순서 권장.

---

## 0. OS·하드웨어 전제

- Ubuntu 22.04 LTS (Desktop 또는 Server)
- 유선 또는 `AIP_FLEET` 무선 연결
- 관리자(sudo) 권한
- (권장) 16 GB RAM 이상 — rosbag2 + InfluxDB + 다수 차량 핸들링

네트워크 확인:
```bash
ip -4 addr show | grep 192.168.0.9  # 예약 IP 할당 여부
```

---

## 1. 기초 패키지 설치 (5 분)

```bash
sudo apt update
sudo apt install -y curl git rsync ca-certificates gnupg lsb-release \
                    net-tools openssh-server
```

SSH 가 필요하면 `sudo systemctl enable --now ssh`.

---

## 2. Docker + Compose v2 설치

공식 apt repo 사용:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
                    docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
```

**로그아웃 후 재로그인** 해서 그룹 반영.

검증:
```bash
docker version
docker compose version
```

---

## 3. 워크스페이스 배치

개발 PC(Windows) 에서 rsync:

```bash
# Windows Git Bash / WSL 에서
rsync -avz --delete \
  --exclude '.pio' --exclude 'build' --exclude 'install' --exclude 'log' \
  --exclude 'node_modules' --exclude 'secrets.ini' --exclude '.env' \
  /c/Users/user/aip_swarm_ws/ aip@192.168.0.9:~/aip_swarm_ws/
```

또는 Ubuntu 에서 직접 clone (private repo 라면):
```bash
git clone <repo-url> ~/aip_swarm_ws
cd ~/aip_swarm_ws
```

### 3.1 시크릿 파일 준비

```bash
cd ~/aip_swarm_ws

# InfluxDB 크레덴셜
cp docker/central/.env.example docker/central/.env
# Ubuntu 용: strong password + random token 생성
PASS=$(openssl rand -base64 24)
TOKEN=$(openssl rand -hex 32)
sed -i "s|REPLACE_WITH_STRONG_PASSWORD|${PASS}|" docker/central/.env
sed -i "s|REPLACE_WITH_RANDOM_64HEX_TOKEN|${TOKEN}|" docker/central/.env

# 결과 확인 (터미널에서 직접 저장 또는 pass/1password 로 이동)
cat docker/central/.env
```

ESP32 를 이 머신에서 빌드하지 않으면 `firmware/scout_microros/secrets.ini`
는 건드릴 필요 없음.

### 3.2 FastDDS 프로파일 배치

```bash
sudo mkdir -p /opt/aip
sudo cp config/fastdds_client_profile.xml /opt/aip/
```

---

## 4. Mode A — 중앙 프로덕션 스택

### 4.1 기동

```bash
cd ~/aip_swarm_ws/docker/central
docker compose up -d
docker compose ps
```

5 개 서비스가 모두 `Up` 상태여야 함:
- `aip_fastdds_ds`
- `aip_uros_agent`
- `aip_foxglove_bridge`
- `aip_rosbag_recorder`
- `aip_influxdb`

로그:
```bash
docker compose logs -f fastdds-ds uros-agent foxglove-bridge
```

### 4.2 Supervisor + Watchdog 구동

현재 중앙 스택 compose 에는 supervisor/watchdog 이 포함돼 있지 않음 —
**Ubuntu 네이티브 ROS2** 에서 띄우는 것이 launch 파일을 그대로 쓰기에
가장 깔끔. 아직 설치가 안 됐다면:

```bash
# ROS2 Humble 설치 (공식)
sudo apt install -y software-properties-common
sudo add-apt-repository universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
    http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | \
    sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt update
sudo apt install -y ros-humble-desktop ros-humble-foxglove-bridge \
                    ros-humble-twist-mux ros-humble-rosbag2-storage-mcap \
                    python3-colcon-common-extensions python3-rosdep
sudo rosdep init || true
rosdep update
```

워크스페이스 빌드:
```bash
cd ~/aip_swarm_ws
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
```

기동:
```bash
source install/setup.bash
export ROS_DOMAIN_ID=42
export ROS_DISCOVERY_SERVER=192.168.0.9:11811
export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/aip/fastdds_client_profile.xml

ros2 launch aip_fleet_bringup central.launch.py
```

### 4.3 검증

별도 터미널:
```bash
source /opt/ros/humble/setup.bash
source ~/aip_swarm_ws/install/setup.bash
export ROS_DOMAIN_ID=42
export ROS_DISCOVERY_SERVER=192.168.0.9:11811
export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/aip/fastdds_client_profile.xml

ros2 topic list
# 기대: /fleet/status, /fleet/override, /main/heartbeat, ... 등
```

Foxglove Studio (개발용 노트북) 에서 `ws://192.168.0.9:8765` 접속.

---

## 5. Mode B — 로컬 시뮬만 (하드웨어 없이)

Windows 가이드와 동일 이미지:

```bash
cd ~/aip_swarm_ws
docker compose -f docker/sim/docker-compose.yml up --build
```

Foxglove Studio 에서 `ws://<ubuntu-ip>:8765` (같은 머신이면 `localhost:8765`).

---

## 6. systemd 자동 기동 (선택)

중앙 PC 가 재부팅되어도 스택이 자동 기동되도록.
Unit 파일 원본: `docker/central/aip-central.service` (경로·사용자명 수정 후 설치):

```bash
# WorkingDirectory / User 를 실제 배포 경로에 맞게 수정
sudo install -m 644 ~/aip_swarm_ws/docker/central/aip-central.service \
    /etc/systemd/system/aip-central.service
# 경로·사용자를 수정해야 한다면:
# sudo nano /etc/systemd/system/aip-central.service

sudo systemctl daemon-reload
sudo systemctl enable --now aip-central.service
```

(`aip` 사용자명·경로는 `docker/central/aip-central.service` 내에서 직접 수정)

---

## 7. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `docker compose up` 이 `INFLUXDB_PASSWORD is required` | `.env` 미생성 | §3.1 재실행 |
| `ros2 topic list` 가 비어 있음 | Discovery Server 못 찾음 | `ROS_DISCOVERY_SERVER` env 확인, `docker compose logs fastdds-ds` |
| Foxglove 접속이 외부에서 안됨 | 방화벽 | `sudo ufw allow 8765/tcp` |
| 차량(main AGV)에서 DS 인식 안됨 | 방화벽 / Wi-Fi 분리 | `sudo ufw allow 11811/udp` + AP 에서 client isolation 해제 |
| `uros-agent` 에 스카우트 세션 안 뜸 | UDP 포트 차단 | `sudo ufw allow 8888/udp` |
| rosbag 볼륨이 계속 커짐 | 1 GiB 롤링만 있고 보존 한도 없음 | cron 으로 `/var/lib/docker/volumes/central_aip_rosbags/_data` 오래된 파일 prune |

---

## 8. 방화벽 기본 룰 요약 (UFW 사용 시)

```bash
sudo ufw allow from 192.168.0.0/24 to any port 11811 proto udp  # FastDDS DS
sudo ufw allow from 192.168.0.0/24 to any port 8888  proto udp  # micro-ROS
sudo ufw allow from 192.168.0.0/24 to any port 8765  proto tcp  # Foxglove
sudo ufw allow from 192.168.0.0/24 to any port 22    proto tcp  # SSH
sudo ufw enable
```

외부 인터넷에서의 접근은 기본 거부.

---

## 9. 상태 확인 체크리스트

배포 직후 한 번씩:

```bash
# 컨테이너
docker compose -f ~/aip_swarm_ws/docker/central/docker-compose.yml ps

# ROS2 그래프
ros2 topic list | sort
ros2 node list

# 차량 하트비트
ros2 topic echo /main/heartbeat --once
ros2 topic echo /fleet/status --once

# Foxglove 연결 확인 (다른 호스트에서)
curl -I http://192.168.0.9:8765
```

모두 정상이면 개발 루프 준비 완료.

---

## 10. 다음 단계

- Windows 개발 루프: `docs/SETUP_WINDOWS.md`
- 아키텍처: `docs/ARCHITECTURE.md`
- 개선점/버그: `docs/ANALYSIS.md`
- 보안 하드닝 (Phase 1 SROS2 등): `docs/SECURITY.md`
