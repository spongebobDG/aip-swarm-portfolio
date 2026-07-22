#!/usr/bin/env python3
"""Start/stop temporary UDP status overlays for the three live vehicles.

This helper does not store passwords and does not install services on vehicles.
It only creates /tmp/status_<vehicle>.py on each host and runs it in the
background so the dashboard can show aip1/aip2/aip3 while ROS heartbeat
integration is being finalized.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import os
import pty
import select
import shlex
import sys
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    vid: str
    host: str
    user: str
    password_env: str
    container: str = ""
    pose_topics: str = ""


TARGETS: dict[str, Target] = {
    "aip1": Target(
        "aip1", "192.168.0.3", "jh", "AIP1_SSH_PASSWORD",
        pose_topics="/aip1/odom,/main/odom,/aip1/pose,/main/pose",
    ),
    "aip2": Target(
        "aip2", "192.168.0.4", "aip2", "AIP2_SSH_PASSWORD", "turtlebot3_humble",
        pose_topics="/aip2/odom,/scout_1/odom,/scout_1/dashboard/odom,/odom,"
        "/aip2/pose,/scout_1/pose,/scout_1/dashboard/pose,/pose",
    ),
    "aip3": Target(
        "aip3", "192.168.0.5", "aip3", "AIP3_SSH_PASSWORD", "docker-robot-1",
        pose_topics="/aip3/odom,/scout_2/odom,/scout_2/dashboard/odom,/odom,"
        "/aip3/pose,/scout_2/pose,/scout_2/dashboard/pose,/pose",
    ),
}


REMOTE_STATUS_TEMPLATE = r"""
set -e
cat > /tmp/status___VID__.py <<'PY'
#!/usr/bin/env python3
import json
import os
import shlex
import socket
import subprocess
import threading
import time

TARGET = ('__CENTRAL_IP__', __PORT__)
VID = '__VID__'
CONTAINER = '__CONTAINER__'
POSE_TOPICS = [item.strip() for item in '__POSE_TOPICS__'.split(',') if item.strip()]
POSE_REFRESH_SEC = 8.0
POSE_STALE_SEC = 24.0

POSE_READER_CODE = r'''
import json
import math
import os
import sys
import time

try:
    import rclpy
    from geometry_msgs.msg import PoseStamped
    from nav_msgs.msg import Odometry
except Exception:
    sys.exit(2)

topics = json.loads(os.environ.get('AIP_POSE_TOPICS_JSON', '[]'))
if not topics:
    sys.exit(1)

result = {}

def quat_to_yaw(q):
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)

def make_cb(topic):
    def cb(msg):
        if result:
            return
        if hasattr(msg, 'pose') and hasattr(msg.pose, 'pose'):
            pose = msg.pose.pose
        elif hasattr(msg, 'pose'):
            pose = msg.pose
        else:
            return
        result.update({
            'x': float(pose.position.x),
            'y': float(pose.position.y),
            'z': float(pose.position.z),
            'yaw_rad': quat_to_yaw(pose.orientation),
            'source_topic': topic,
            'stamp': time.time(),
        })
    return cb

try:
    rclpy.init(args=[])
    node = rclpy.create_node('aip_udp_status_pose_probe')
    odom_topics = [topic for topic in topics if 'odom' in topic.rsplit('/', 1)[-1].lower()]
    pose_topics = [topic for topic in topics if 'pose' in topic.rsplit('/', 1)[-1].lower()]
    for topic in odom_topics + [topic for topic in topics if topic not in odom_topics + pose_topics]:
        node.create_subscription(Odometry, topic, make_cb(topic), 10)
    for topic in pose_topics:
        node.create_subscription(PoseStamped, topic, make_cb(topic), 10)
    deadline = time.time() + 5.0
    while time.time() < deadline and not result:
        rclpy.spin_once(node, timeout_sec=0.1)
finally:
    try:
        node.destroy_node()
    except Exception:
        pass
    rclpy.try_shutdown()

if not result:
    sys.exit(1)
print(json.dumps(result, separators=(',', ':')))
'''

def vehicle_ok():
    if not CONTAINER:
        return True
    try:
        out = subprocess.check_output(
            ['docker', 'inspect', '-f', '{{.State.Running}}', CONTAINER],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1.5,
        ).strip().lower()
        return out == 'true'
    except Exception:
        return False

def cpu_percent():
    try:
        with open('/proc/stat', 'r', encoding='utf-8') as f:
            fields = [int(x) for x in f.readline().split()[1:]]
        idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
        total = sum(fields)
        time.sleep(0.03)
        with open('/proc/stat', 'r', encoding='utf-8') as f:
            fields2 = [int(x) for x in f.readline().split()[1:]]
        idle2 = fields2[3] + (fields2[4] if len(fields2) > 4 else 0)
        total2 = sum(fields2)
        dt = max(1, total2 - total)
        return max(0.0, min(100.0, 100.0 * (1.0 - (idle2 - idle) / dt)))
    except Exception:
        return 0.0

def read_pose_once():
    if not POSE_TOPICS:
        return None
    ros_setup = '''
set +e
for f in \
  /opt/ros/humble/setup.bash \
  /root/colcon_ws/install/setup.bash \
  /root/ros2_ws/install/setup.bash \
  /home/$USER/colcon_ws/install/setup.bash \
  /home/$USER/aip_swarm_ws/install/setup.bash; do
  [ -f "$f" ] && . "$f"
done
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
export ROS_DISCOVERY_SERVER="${ROS_DISCOVERY_SERVER:-__CENTRAL_IP__:11811}"
export AIP_POSE_TOPICS_JSON=''' + shlex.quote(json.dumps(POSE_TOPICS)) + '''
python3 - <<'POSEPY'
''' + POSE_READER_CODE + '''
POSEPY
'''
    cmd = ['timeout', '-k', '1', '8', 'bash', '-lc', ros_setup]
    if CONTAINER:
        cmd = ['docker', 'exec', CONTAINER, 'timeout', '-k', '1', '8', 'bash', '-lc', ros_setup]
    try:
        out = subprocess.check_output(
            cmd,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10.0,
        )
    except Exception:
        return None
    for line in reversed(out.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            pose = json.loads(line)
        except Exception:
            continue
        if isinstance(pose, dict) and 'x' in pose and 'y' in pose:
            return pose
    return None

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
seq = 0
last_pose = None
last_pose_lock = threading.Lock()

def pose_loop():
    global last_pose
    while True:
        pose = read_pose_once()
        if pose is not None:
            with last_pose_lock:
                last_pose = pose
        time.sleep(POSE_REFRESH_SEC)

if POSE_TOPICS:
    threading.Thread(target=pose_loop, daemon=True).start()

while True:
    ok = vehicle_ok()
    behaviors = ['udp_status_only']
    if CONTAINER:
        behaviors.append(CONTAINER)
    now = time.time()
    with last_pose_lock:
        pose_snapshot = dict(last_pose) if last_pose is not None else None
    if pose_snapshot is not None and now - float(pose_snapshot.get('stamp', 0.0)) <= POSE_STALE_SEC:
        behaviors.append('pose_udp')
    payload = {
        'vehicle_id': VID,
        'state': 'MANUAL' if ok else 'FAULT',
        'mode': 'manual' if ok else 'offline',
        'healthy': bool(ok),
        'estop': False,
        'battery': 100.0 if VID == 'aip1' else 0.0,
        'cpu': round(cpu_percent(), 1),
        'behaviors': behaviors,
        'status': 'container_up_udp_status_only' if ok and CONTAINER else (
            'aip1_udp_status_only_dds_unseen' if ok else 'container_not_running_udp_status_only'
        ),
        'container': CONTAINER,
        'seq': seq,
        'stamp': now,
        'host': os.uname().nodename,
    }
    if pose_snapshot is not None and now - float(pose_snapshot.get('stamp', 0.0)) <= POSE_STALE_SEC:
        payload['pose'] = {
            'x': float(pose_snapshot.get('x', 0.0)),
            'y': float(pose_snapshot.get('y', 0.0)),
            'z': float(pose_snapshot.get('z', 0.0)),
            'yaw_rad': float(pose_snapshot.get('yaw_rad', 0.0)),
            'source_topic': pose_snapshot.get('source_topic', ''),
        }
    sock.sendto(json.dumps(payload, separators=(',', ':')).encode('utf-8'), TARGET)
    seq += 1
    time.sleep(1.0)
PY
chmod +x /tmp/status___VID__.py
pkill -f '[s]tatus___VID__.py' || true
pkill -f '[a]ip_udp_status_pose_probe|AIP_POSE_TOPICS_JSON' || true
nohup /tmp/status___VID__.py >/tmp/status___VID__.log 2>&1 &
sleep 2
printf 'STARTED __VID__ on __HOST__\n'
pgrep -a -f 'status___VID__.py' || true
if [ -n '__CONTAINER__' ]; then
  docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | grep -E '__CONTAINER__' || true
fi
"""


def remote_script_for_start(target: Target, central_ip: str, port: int) -> str:
    return (
        REMOTE_STATUS_TEMPLATE
        .replace("__VID__", target.vid)
        .replace("__HOST__", target.host)
        .replace("__CONTAINER__", target.container)
        .replace("__POSE_TOPICS__", target.pose_topics)
        .replace("__CENTRAL_IP__", central_ip)
        .replace("__PORT__", str(port))
    )


def remote_script_for_esp32_reset(target: Target) -> str:
    """fleet_main launch를 재시작해서 ESP32 DTR 리셋을 유발한다 (aip1 전용)."""
    if target.vid != "aip1":
        return f'printf "ESP32 reset not supported for {target.vid}\\n"\n'
    return r"""
set -e
printf 'ESP32 RESET: fleet_main 재시작 시작\n'
pkill -f 'ros2 launch aip_bringup fleet_main' 2>/dev/null && printf 'launch 종료됨\n' || printf 'launch 없음\n'
sleep 1.5
source /opt/ros/humble/setup.bash
source ~/aip_ws/install/setup.bash
export ROS_DOMAIN_ID=42 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DISCOVERY_SERVER=192.168.0.10:11811
export FASTRTPS_DEFAULT_PROFILES_FILE=$HOME/aip_ws/install/aip_bringup/share/aip_bringup/config/fastdds_client_profile.xml
nohup ros2 launch aip_bringup fleet_main.launch.py with_base:=true > /tmp/fleet_main.log 2>&1 &
printf 'Launch PID=%s\n' "$!"
sleep 4
pgrep -f aip_serial_bridge > /dev/null && printf 'SERIAL_OK\n' || printf 'SERIAL_FAIL\n'
"""


def remote_script_for_stop(target: Target) -> str:
    return f"""
set -e
pkill -f '[s]tatus_{target.vid}.py' || true
pkill -f '[a]ip_udp_status_pose_probe|AIP_POSE_TOPICS_JSON' || true
printf 'STOPPED {target.vid} status overlay\\n'
pgrep -a -f 'status_{target.vid}.py' || true
"""


def remote_script_for_status(target: Target) -> str:
    container_check = ""
    if target.container:
        container_check = (
            "printf 'CONTAINER\\n'\n"
            f"docker ps --format '{{{{.Names}}}} {{{{.Status}}}}' 2>/dev/null | "
            f"grep -E '{target.container}' || true\n"
        )
    heartbeat_check = ""
    if target.vid == "aip1":
        heartbeat_check = "printf 'AIP1_HEARTBEAT_PROC\\n'\npgrep -a -f 'heartbeat_pub' || true\n"
    return f"""
set -e
printf 'HOST {target.host} VID {target.vid}\\n'
printf 'STATUS_OVERLAY_PROC\\n'
pgrep -a -f 'status_{target.vid}.py' || true
{container_check}{heartbeat_check}printf 'LOG\\n'
tail -n 10 /tmp/status_{target.vid}.log 2>/dev/null || true
"""


class MissingPasswordError(RuntimeError):
    pass


def password_for(target: Target, *, allow_prompt: bool) -> str:
    pw = os.environ.get(target.password_env)
    if pw:
        return pw
    if not allow_prompt:
        raise MissingPasswordError(
            f"{target.password_env} is not set and no interactive password prompt is available"
        )
    return getpass.getpass(f"{target.user}@{target.host} password ({target.password_env}): ")


def run_ssh(target: Target, remote_script: str, password: str, timeout: float) -> tuple[int, str]:
    b64 = base64.b64encode(remote_script.encode("utf-8")).decode("ascii")
    remote_cmd = "base64 -d <<< " + shlex.quote(b64) + " | bash"
    cmd = [
        "ssh",
        "-tt",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/tmp/aip_known_hosts_codex",
        "-o",
        "ConnectTimeout=8",
        f"{target.user}@{target.host}",
        "bash -lc " + shlex.quote(remote_cmd),
    ]
    child_pid, fd = pty.fork()
    if child_pid == 0:
        os.execvp(cmd[0], cmd)

    output = bytearray()
    sent_pw = False
    deadline = time.time() + timeout
    status = 124
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.2)
        if fd in r:
            try:
                data = os.read(fd, 4096)
            except OSError:
                break
            if not data:
                break
            output.extend(data)
            tail = output[-4000:].decode("utf-8", errors="ignore").lower()
            if "are you sure you want to continue connecting" in tail:
                os.write(fd, b"yes\n")
            if "password:" in tail and not sent_pw:
                os.write(fd, (password + "\n").encode("utf-8"))
                sent_pw = True
        try:
            pid, raw_status = os.waitpid(child_pid, os.WNOHANG)
            if pid == child_pid:
                status = os.waitstatus_to_exitcode(raw_status)
                break
        except ChildProcessError:
            status = 0
            break
    else:
        try:
            os.kill(child_pid, 9)
        except ProcessLookupError:
            pass
    return status, output.decode("utf-8", errors="replace")


def parse_targets(raw: str) -> list[Target]:
    names = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [name for name in names if name not in TARGETS]
    if unknown:
        raise SystemExit(f"unknown target(s): {', '.join(unknown)}")
    return [TARGETS[name] for name in names]


def _systemd_unit_for(target: Target, central_ip: str, port: int) -> str:
    """차량 호스트에 설치할 systemd user 서비스 유닛 파일 내용을 반환.

    설치 방법 (차량 SSH 접속 후):
      mkdir -p ~/.config/systemd/user/
      cat > ~/.config/systemd/user/aip-status-<vid>.service <<'EOF'
      <이 함수 출력>
      EOF
      systemctl --user daemon-reload
      systemctl --user enable --now aip-status-<vid>.service
    """
    return f"""\
[Unit]
Description=AIP UDP status overlay for {target.vid}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStartPre=/bin/bash -c 'python3 - <<\\'GENPY\\'
import socket, json, os, subprocess, time
TARGET = (\\'{central_ip}\\', {port})
VID = \\'{target.vid}\\'
CONTAINER = \\'{target.container}\\'
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
while True:
    ok = True
    if CONTAINER:
        try:
            out = subprocess.check_output([\\"docker\\",\\"inspect\\",\\"-f\\",\\"{{{{.State.Running}}}}\\",CONTAINER],
                stderr=subprocess.DEVNULL, text=True, timeout=2).strip()
            ok = out == \\"true\\"
        except Exception:
            ok = False
    payload = {{\\"vehicle_id\\": VID, \\"state\\": \\"MANUAL\\" if ok else \\"FAULT\\",
                \\"healthy\\": bool(ok), \\"estop\\": False}}
    sock.sendto(json.dumps(payload).encode(), TARGET)
    time.sleep(1.0)
GENPY
'
ExecStart=/bin/bash -c 'python3 /tmp/status_{target.vid}.py'
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""


def _print_systemd_install_guide(targets: list[Target], central_ip: str, port: int) -> None:
    """--install-systemd: 각 차량용 systemd 유닛을 stdout에 출력."""
    print("=" * 60)
    print("systemd user 서비스 설치 가이드")
    print("각 차량에서 아래 명령 순서대로 실행:")
    print("=" * 60)
    for target in targets:
        unit_name = f"aip-status-{target.vid}.service"
        unit_path = f"~/.config/systemd/user/{unit_name}"
        print(f"\n### {target.vid} ({target.user}@{target.host}) ###")
        print(f"# 1. SSH 접속 후 서비스 파일 생성:")
        print(f"mkdir -p ~/.config/systemd/user/")
        print(f"cat > {unit_path} << 'UNIT'")
        print(_systemd_unit_for(target, central_ip, port))
        print("UNIT")
        print(f"# 2. 서비스 등록 및 시작:")
        print(f"systemctl --user daemon-reload")
        print(f"systemctl --user enable --now {unit_name}")
        print(f"# 3. 상태 확인:")
        print(f"systemctl --user status {unit_name}")
        print(f"# 4. 로그 확인:")
        print(f"journalctl --user -u {unit_name} -f")
    print("\n주의: 이 서비스는 UDP status overlay를 영구화한다.")
    print("      재부팅 후 자동 기동, 5초 간격 재시작. 정식 DDS heartbeat 통합 후 제거.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status", "install-systemd", "esp32_reset"])
    parser.add_argument("--targets", default="aip1,aip2,aip3")
    parser.add_argument("--central-ip", default=os.environ.get("AIP_CENTRAL_IP", "192.168.0.8"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("AIP_UDP_HEARTBEAT_ADAPTER_PORT", "19051")))
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="fail fast if a password environment variable is missing",
    )
    args = parser.parse_args()

    targets = parse_targets(args.targets)

    if args.action == "install-systemd":
        _print_systemd_install_guide(targets, args.central_ip, args.port)
        return 0

    exit_code = 0
    allow_prompt = not args.no_prompt and sys.stdin.isatty()
    for target in targets:
        if args.action == "start":
            remote = remote_script_for_start(target, args.central_ip, args.port)
        elif args.action == "stop":
            remote = remote_script_for_stop(target)
        elif args.action == "esp32_reset":
            remote = remote_script_for_esp32_reset(target)
        else:
            remote = remote_script_for_status(target)
        print(f"===== {args.action.upper()} {target.vid} {target.user}@{target.host} =====")
        try:
            password = password_for(target, allow_prompt=allow_prompt)
        except MissingPasswordError as exc:
            print(f"[SKIP] {exc}")
            exit_code = 2
            continue
        status, output = run_ssh(target, remote, password, args.timeout)
        print(output)
        if status != 0:
            exit_code = status
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
