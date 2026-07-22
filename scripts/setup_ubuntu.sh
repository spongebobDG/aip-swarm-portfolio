#!/usr/bin/env bash
# =============================================================================
# AIP Fleet — Ubuntu 22.04 개발/배포 환경 자동 설정 스크립트
#
# 사용법:
#   git clone <repo-url> ~/aip_swarm_ws
#   cd ~/aip_swarm_ws
#   bash scripts/setup_ubuntu.sh [옵션]
#
# 옵션:
#   --skip-ros2       ROS2 Humble 이미 설치된 경우 건너뜀
#   --skip-docker     Docker 이미 설치된 경우 건너뜀
#   --skip-nodejs     Node.js / Foxglove 패널 빌드 건너뜀
#   --with-systemd    systemd aip-central.service 등록
#   --with-ufw        UFW 방화벽 룰 적용 (주의: 기존 룰에 추가)
#   --with-sros2      SROS2 키스토어 초기화 (scripts/sros2_init.sh 호출)
#   --dry-run         실제 변경 없이 수행 단계만 출력
#
# 멱등성(idempotent): 이미 완료된 단계는 자동으로 건너뜀. 반복 실행 안전.
# =============================================================================

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────────
# 색상 출력 헬퍼
# ──────────────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET} $*"; }
ok()      { echo -e "${GREEN}[OK]${RESET}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
section() { echo -e "\n${BOLD}━━━ $* ━━━${RESET}"; }
die()     { echo -e "${RED}[ERR]${RESET}  $*" >&2; exit 1; }

DRY_RUN=false
run() {
    if $DRY_RUN; then
        echo -e "${YELLOW}[DRY]${RESET} $*"
    else
        eval "$@"
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
# 인자 파싱
# ──────────────────────────────────────────────────────────────────────────────
SKIP_ROS2=false; SKIP_DOCKER=false; SKIP_NODEJS=false
WITH_SYSTEMD=false; WITH_UFW=false; WITH_SROS2=false

for arg in "$@"; do
    case $arg in
        --skip-ros2)    SKIP_ROS2=true ;;
        --skip-docker)  SKIP_DOCKER=true ;;
        --skip-nodejs)  SKIP_NODEJS=true ;;
        --with-systemd) WITH_SYSTEMD=true ;;
        --with-ufw)     WITH_UFW=true ;;
        --with-sros2)   WITH_SROS2=true ;;
        --dry-run)      DRY_RUN=true; warn "DRY-RUN 모드: 실제 변경 없음" ;;
        --help|-h)
            sed -n '/^# 사용법/,/^# =/p' "$0" | head -20
            exit 0 ;;
        *) die "알 수 없는 옵션: $arg (--help 참조)" ;;
    esac
done

# ──────────────────────────────────────────────────────────────────────────────
# 전제 조건 확인
# ──────────────────────────────────────────────────────────────────────────────
section "전제 조건 확인"

[[ "$(uname -s)" == "Linux" ]] || die "Ubuntu Linux 에서만 실행 가능"
if [[ -f /etc/os-release ]]; then
    source /etc/os-release
    [[ "$ID" == "ubuntu" && "$VERSION_ID" == "22.04" ]] \
        || warn "Ubuntu 22.04 권장. 현재: $PRETTY_NAME"
fi
[[ $EUID -ne 0 ]] || die "root 로 실행하지 마세요. 일반 사용자로 실행 후 sudo 위임"

# 워크스페이스 루트 확인
WS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$WS_ROOT/CLAUDE.md" ]] \
    || die "워크스페이스 루트를 찾을 수 없습니다: $WS_ROOT"
info "워크스페이스: $WS_ROOT"
cd "$WS_ROOT"

# ──────────────────────────────────────────────────────────────────────────────
# 1. 기초 패키지
# ──────────────────────────────────────────────────────────────────────────────
section "1. 기초 패키지 설치"

run sudo apt-get update -qq
run sudo apt-get install -y --no-install-recommends \
    curl git rsync ca-certificates gnupg lsb-release \
    net-tools openssh-server software-properties-common \
    build-essential python3-pip python3-venv
ok "기초 패키지 완료"

# ──────────────────────────────────────────────────────────────────────────────
# 2. Docker + Compose v2
# ──────────────────────────────────────────────────────────────────────────────
section "2. Docker 설치"

if $SKIP_DOCKER; then
    info "--skip-docker: 건너뜀"
elif command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
    ok "Docker $(docker --version | awk '{print $3}' | tr -d ,) 이미 설치됨"
else
    info "Docker 공식 apt repo 추가..."
    run sudo install -m 0755 -d /etc/apt/keyrings
    run "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg"
    run sudo chmod a+r /etc/apt/keyrings/docker.gpg
    run "echo \"deb [arch=\$(dpkg --print-architecture) \
        signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu \$(lsb_release -cs) stable\" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null"
    run sudo apt-get update -qq
    run sudo apt-get install -y --no-install-recommends \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    run sudo usermod -aG docker "$USER"
    ok "Docker 설치 완료 (그룹 반영은 재로그인 후)"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 3. ROS2 Humble
# ──────────────────────────────────────────────────────────────────────────────
section "3. ROS2 Humble 설치"

if $SKIP_ROS2; then
    info "--skip-ros2: 건너뜀"
elif [[ -f /opt/ros/humble/setup.bash ]]; then
    ok "ROS2 Humble 이미 설치됨"
else
    info "ROS2 apt repo 추가..."
    run sudo add-apt-repository universe -y
    run "sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        -o /usr/share/keyrings/ros-archive-keyring.gpg"
    run "echo \"deb [arch=\$(dpkg --print-architecture) \
        signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
        http://packages.ros.org/ros2/ubuntu \$(. /etc/os-release && echo \$UBUNTU_CODENAME) main\" | \
        sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null"
    run sudo apt-get update -qq
    run sudo apt-get install -y \
        ros-humble-desktop \
        ros-humble-foxglove-bridge \
        ros-humble-twist-mux \
        ros-humble-cv-bridge \
        ros-humble-camera-calibration \
        ros-humble-rosbag2-storage-mcap \
        ros-humble-tf2-ros \
        ros-humble-tf2-geometry-msgs \
        python3-colcon-common-extensions \
        python3-rosdep \
        python3-argcomplete
    ok "ROS2 Humble 설치 완료"
fi

# rosdep 초기화 (멱등)
if [[ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
    run sudo rosdep init
fi
run rosdep update --rosdistro humble -q
ok "rosdep 업데이트 완료"

# ──────────────────────────────────────────────────────────────────────────────
# 4. 워크스페이스 의존성 설치 및 빌드
# ──────────────────────────────────────────────────────────────────────────────
section "4. 워크스페이스 빌드"

info "rosdep으로 패키지 의존성 설치..."
run "source /opt/ros/humble/setup.bash && \
    rosdep install --from-paths src --ignore-src -r -y -q"

info "colcon 빌드..."
run "source /opt/ros/humble/setup.bash && \
    colcon build --symlink-install \
    --cmake-args -DCMAKE_BUILD_TYPE=Release \
    --event-handlers console_cohesion+"
ok "워크스페이스 빌드 완료"

# ──────────────────────────────────────────────────────────────────────────────
# 5. Node.js 20.x + Foxglove 패널 빌드
# ──────────────────────────────────────────────────────────────────────────────
section "5. Node.js / Foxglove 패널"

if $SKIP_NODEJS; then
    info "--skip-nodejs: 건너뜀"
else
    if command -v node &>/dev/null && [[ $(node --version | cut -d. -f1 | tr -d v) -ge 20 ]]; then
        ok "Node.js $(node --version) 이미 설치됨"
    else
        info "Node.js 20.x LTS 설치..."
        run "curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
        run sudo apt-get install -y nodejs
        ok "Node.js $(node --version) 설치 완료"
    fi

    PANEL_DIR="$WS_ROOT/src/aip_fleet_foxglove_panels"
    info "Foxglove 패널 빌드..."
    run "cd '$PANEL_DIR' && npm ci --silent && npm run build"
    ok "Foxglove 패널 빌드 완료"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 6. OpenCV contrib (ArUco 위치추정용)
# ──────────────────────────────────────────────────────────────────────────────
section "6. OpenCV contrib (ArUco)"

if python3 -c "import cv2.aruco" &>/dev/null 2>&1; then
    ok "cv2.aruco 이미 사용 가능"
else
    info "opencv-contrib-python 설치..."
    run pip3 install --quiet opencv-contrib-python
    ok "opencv-contrib-python 설치 완료"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 7. 환경 파일 준비
# ──────────────────────────────────────────────────────────────────────────────
section "7. 환경 파일 준비"

# 7-1. InfluxDB .env
ENV_FILE="$WS_ROOT/docker/central/.env"
if [[ -f "$ENV_FILE" ]]; then
    ok "docker/central/.env 이미 존재"
else
    info "InfluxDB 크레덴셜 자동 생성..."
    PASS=$(openssl rand -base64 24)
    TOKEN=$(openssl rand -hex 32)
    run cp "$WS_ROOT/docker/central/.env.example" "$ENV_FILE"
    if ! $DRY_RUN; then
        sed -i "s|REPLACE_WITH_STRONG_PASSWORD|${PASS}|g" "$ENV_FILE"
        sed -i "s|REPLACE_WITH_RANDOM_64HEX_TOKEN|${TOKEN}|g" "$ENV_FILE"
    fi
    warn "생성된 크레덴셜을 안전한 곳에 백업하세요: $ENV_FILE"
    ok "docker/central/.env 생성 완료"
fi

# 7-2. FastDDS 프로파일
if [[ ! -f /opt/aip/fastdds_client_profile.xml ]]; then
    run sudo mkdir -p /opt/aip
    run sudo cp "$WS_ROOT/config/fastdds_client_profile.xml" /opt/aip/
    ok "FastDDS 프로파일 → /opt/aip/"
else
    ok "/opt/aip/fastdds_client_profile.xml 이미 존재"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 8. ~/.bashrc 환경변수 등록
# ──────────────────────────────────────────────────────────────────────────────
section "8. .bashrc 환경변수 등록"

BASHRC="$HOME/.bashrc"
MARKER="# >>> AIP Fleet Setup <<<"

if grep -q "$MARKER" "$BASHRC" 2>/dev/null; then
    ok ".bashrc 이미 설정됨"
else
    info ".bashrc에 ROS2 + 워크스페이스 환경변수 추가..."
    if ! $DRY_RUN; then
        cat >> "$BASHRC" <<EOF

$MARKER
source /opt/ros/humble/setup.bash
[[ -f "$WS_ROOT/install/setup.bash" ]] && source "$WS_ROOT/install/setup.bash"
export ROS_DOMAIN_ID=42
export ROS_DISCOVERY_SERVER=192.168.0.9:11811
export FASTRTPS_DEFAULT_PROFILES_FILE=/opt/aip/fastdds_client_profile.xml
# <<< AIP Fleet Setup <<<
EOF
    else
        run "echo '# .bashrc 블록 추가 예정'"
    fi
    ok ".bashrc 설정 완료 (새 터미널에서 반영)"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 9. UFW 방화벽 룰 (선택)
# ──────────────────────────────────────────────────────────────────────────────
if $WITH_UFW; then
    section "9. UFW 방화벽 룰"
    SUBNET="192.168.0.0/24"
    run sudo ufw allow from "$SUBNET" to any port 11811 proto udp comment 'AIP FastDDS DS'
    run sudo ufw allow from "$SUBNET" to any port 8888  proto udp comment 'AIP micro-ROS'
    run sudo ufw allow from "$SUBNET" to any port 8765  proto tcp comment 'AIP Foxglove'
    run sudo ufw allow from "$SUBNET" to any port 22    proto tcp comment 'AIP SSH'
    run sudo ufw --force enable
    ok "UFW 룰 적용 완료"
else
    info "UFW 룰 건너뜀 (--with-ufw 로 적용)"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 10. systemd aip-central.service (선택)
# ──────────────────────────────────────────────────────────────────────────────
if $WITH_SYSTEMD; then
    section "10. systemd 서비스 등록"
    SERVICE_FILE="/etc/systemd/system/aip-central.service"
    if [[ -f "$SERVICE_FILE" ]]; then
        ok "aip-central.service 이미 존재"
    else
        info "systemd 유닛 파일 생성..."
        run "sudo tee '$SERVICE_FILE' > /dev/null <<EOF
[Unit]
Description=AIP Fleet Central Stack (Docker Compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$WS_ROOT/docker/central
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=$USER

[Install]
WantedBy=multi-user.target
EOF"
        run sudo systemctl daemon-reload
        run sudo systemctl enable --now aip-central.service
        ok "aip-central.service 등록 및 기동 완료"
    fi
else
    info "systemd 서비스 건너뜀 (--with-systemd 로 등록)"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 11. SROS2 키스토어 초기화 (선택)
# ──────────────────────────────────────────────────────────────────────────────
if $WITH_SROS2; then
    section "11. SROS2 키스토어 초기화"
    KEYSTORE="$WS_ROOT/config/security/keystore"
    if [[ -d "$KEYSTORE" ]]; then
        ok "SROS2 키스토어 이미 존재: $KEYSTORE"
    else
        run "source /opt/ros/humble/setup.bash && \
             source '$WS_ROOT/install/setup.bash' && \
             bash '$WS_ROOT/scripts/sros2_init.sh' <<< 'y'"
        ok "SROS2 키스토어 생성 완료"
    fi
else
    info "SROS2 건너뜀 (--with-sros2 로 초기화, 또는 scripts/sros2_init.sh 직접 실행)"
fi

# ──────────────────────────────────────────────────────────────────────────────
# 완료 요약
# ──────────────────────────────────────────────────────────────────────────────
section "설정 완료"

echo -e "
${GREEN}${BOLD}✔ AIP Fleet 환경 설정 완료${RESET}

다음 단계:
  1. 새 터미널 열기 (또는 source ~/.bashrc)
  2. Docker 그룹 반영: 로그아웃 후 재로그인 (또는 newgrp docker)

시뮬 E2E 실행:
  docker compose -f docker/sim/docker-compose.yml up --build

중앙 스택 실행 (프로덕션):
  cd $WS_ROOT/docker/central && docker compose up -d
  source ~/.bashrc
  ros2 launch aip_fleet_bringup central.launch.py

SROS2 활성화 (키스토어 생성 후):
  bash scripts/sros2_init.sh
  ros2 launch aip_fleet_bringup central.launch.py with_security:=true

Foxglove Studio → ws://\$(hostname -I | awk '{print \$1}'):8765
"
