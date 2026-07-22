#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# aip_env.sh — AIP Swarm 워크스페이스 환경 설정 스크립트
#
# 사용법 (반드시 source로 실행):
#   source ~/aip_swarm_ws/aip_env.sh           # 시뮬 모드 (기본)
#   source ~/aip_swarm_ws/aip_env.sh sim       # 로컬 시뮬레이션
#   source ~/aip_swarm_ws/aip_env.sh real      # 실차 배포 (FastDDS 클라이언트)
#   source ~/aip_swarm_ws/aip_env.sh central   # 중앙 PC (Discovery Server 호스트)
#
# MODE 별 차이:
#   sim     — Discovery Server 없음, 단순 UDP multicast (로컬 Gazebo 테스트)
#   real    — FastDDS CLIENT 프로파일 적용, Discovery Server 192.168.0.10:11811 연결
#   central — FastDDS SERVER 프로파일 적용 (중앙 PC에서만 사용)
# ─────────────────────────────────────────────────────────────────────────────

# source가 아닌 직접 실행 방지
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "[AIP] ERROR: 직접 실행하지 말고 'source'로 실행하세요."
    echo "       source ~/aip_swarm_ws/aip_env.sh [sim|real|central]"
    exit 1
fi

# ── 경로 고정 ─────────────────────────────────────────────────────────────────
_AIP_WS="$HOME/aip_swarm_ws"
_AIP_ROS="/opt/ros/humble"
_AIP_CFG="$_AIP_WS/config"

# ── MODE 파싱 ─────────────────────────────────────────────────────────────────
_AIP_MODE="${1:-sim}"
case "$_AIP_MODE" in
    sim|real|central) ;;
    *)
        echo "[AIP] 알 수 없는 모드: '$_AIP_MODE'. sim / real / central 중 선택."
        return 1
        ;;
esac

# ── 공통: ROS2 Humble + 워크스페이스 소싱 ────────────────────────────────────
source "$_AIP_ROS/setup.bash"
source "$_AIP_WS/install/setup.bash"

# ── 공통: 기본 ROS2 환경 변수 ─────────────────────────────────────────────────
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

# ── 공통: Ignition Gazebo 리소스 경로 ─────────────────────────────────────────
# install 내 패키지 world 파일이 gz/ign에서 검색되도록 추가
_IGN_SHARE="$_AIP_WS/install/aip_fleet_gazebo/share/aip_fleet_gazebo"
if [[ -d "$_IGN_SHARE" ]]; then
    export IGN_GAZEBO_RESOURCE_PATH="$_IGN_SHARE:${IGN_GAZEBO_RESOURCE_PATH:-}"
fi

# ── 모드별 FastDDS / Discovery Server 설정 ────────────────────────────────────
case "$_AIP_MODE" in

    sim)
        # 로컬 시뮬: Simple Discovery + SHM 비활성화(aip_central 동시 구동 시 충돌 방지)
        _SIM_XML="$_AIP_CFG/fastdds_sim_profile.xml"
        if [[ -f "$_SIM_XML" ]]; then
            export FASTRTPS_DEFAULT_PROFILES_FILE="$_SIM_XML"
        else
            unset FASTRTPS_DEFAULT_PROFILES_FILE
        fi
        unset ROS_DISCOVERY_SERVER
        ;;

    real)
        # 실차: FastDDS CLIENT — Discovery Server(192.168.0.10:11811)에 연결 (우리 PC)
        _CLIENT_XML="$_AIP_CFG/fastdds_client_profile.xml"
        if [[ ! -f "$_CLIENT_XML" ]]; then
            echo "[AIP] WARNING: FastDDS 클라이언트 프로파일을 찾을 수 없습니다."
            echo "     경로: $_CLIENT_XML"
        fi
        export FASTRTPS_DEFAULT_PROFILES_FILE="$_CLIENT_XML"
        export ROS_DISCOVERY_SERVER="192.168.0.10:11811"
        ;;

    central)
        # 중앙 PC: FastDDS SERVER 프로파일 (서버 측에서만 사용)
        _SERVER_XML="$_AIP_CFG/fastdds_discovery_server.xml"
        if [[ ! -f "$_SERVER_XML" ]]; then
            echo "[AIP] WARNING: FastDDS 서버 프로파일을 찾을 수 없습니다."
            echo "     경로: $_SERVER_XML"
        fi
        export FASTRTPS_DEFAULT_PROFILES_FILE="$_SERVER_XML"
        unset ROS_DISCOVERY_SERVER
        ;;
esac

# ── NVIDIA PRIME GPU 오프로드 (GPU 있는 경우만 활성화) ────────────────────────
# Ignition / RViz2 실행 시 NVIDIA GPU 강제 사용.
# 변수 노출만 해두고, 실제 GPU 바인딩은 aip_ign/aip_auto 등 alias에서 적용.
export AIP_NV_ENV="__NV_PRIME_RENDER_OFFLOAD=1 \
__NV_PRIME_RENDER_OFFLOAD_PROVIDER=NVIDIA-G0 \
__GLX_VENDOR_LIBRARY_NAME=nvidia \
__EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/10_nvidia.json"

# ── bash_aliases 로드 (없을 경우 안전하게 건너뜀) ─────────────────────────────
if [[ -f "$HOME/.bash_aliases" ]]; then
    # 이미 로드된 경우 중복 방지 (aip_help 함수 존재 여부로 판단)
    if ! declare -f aip_help > /dev/null 2>&1; then
        source "$HOME/.bash_aliases"
    fi
fi

# ── 완료 메시지 ───────────────────────────────────────────────────────────────
_aip_mode_label() {
    case "$_AIP_MODE" in
        sim)     echo "로컬 시뮬 (Simple Discovery)" ;;
        real)    echo "실차 배포 (FastDDS CLIENT → 192.168.0.10:11811)" ;;
        central) echo "중앙 PC   (FastDDS SERVER)" ;;
    esac
}

echo ""
echo "┌─────────────────────────────────────────────────────┐"
echo "│  AIP Swarm 환경 설정 완료                           │"
echo "├─────────────────────────────────────────────────────┤"
printf "│  모드         : %-35s │\n" "$(_aip_mode_label)"
printf "│  ROS_DOMAIN_ID: %-35s │\n" "$ROS_DOMAIN_ID"
printf "│  RMW          : %-35s │\n" "$RMW_IMPLEMENTATION"
if [[ -n "${ROS_DISCOVERY_SERVER:-}" ]]; then
printf "│  DS Server    : %-35s │\n" "$ROS_DISCOVERY_SERVER"
fi
printf "│  워크스페이스 : %-35s │\n" "$_AIP_WS"
echo "├─────────────────────────────────────────────────────┤"
echo "│  aip_help  — 전체 alias 목록 보기                  │"
echo "└─────────────────────────────────────────────────────┘"
echo ""

# 임시 내부 함수 정리
unset -f _aip_mode_label
