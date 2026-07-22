#!/usr/bin/env python3
"""follower_trigger_node — /fleet/map_ready 수신 시 팔로워 Nav2 풀스택 기동.

타이머 기반 _NAV_START 를 완전히 대체한다.
맵 준비 신호 수신 → 각 팔로워의 controller_manager 서비스 응답 확인 →
ros2 launch + ros2 run 으로 Nav2 스택(+ 선택적 patrol_node) 실행.

파라미터
----------
leader             : str    리더 차량 네임스페이스 (기본 'peer_1', 실차 시 'aip1')
follower_ids       : str    팔로워 네임스페이스 쉼표 구분 (기본 'peer_2,peer_3', 실차 시 'aip2,aip3')
spawn_in_gazebo    : bool   팔로워 Gazebo 스폰 여부 (시뮬 true, 실차 false)
with_patrol        : bool   순찰 노드도 함께 기동할지 여부 (기본 false)
waypoints_<vid>    : float[] 각 차량 순찰 웨이포인트 flat list [x,y,yaw_deg,…]
                             예) waypoints_peer_2 / waypoints_aip2
spawn_x_<vid>      : float  팔로워 스폰 X 좌표 (Gazebo 전용)
spawn_y_<vid>      : float  팔로워 스폰 Y 좌표 (Gazebo 전용)
spawn_yaw_<vid>    : float  팔로워 스폰 yaw 각 (Gazebo 전용)
spawn_stagger_<vid>: float  팔로워 스폰 스태거 대기 시간(s, Gazebo 전용, 기본 0)
patrol_start_delay : float  Nav2 기동 후 patrol_node 시작까지 대기(s, 기본 40)
"""
import os
import struct
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import rclpy
import tf2_ros
import yaml as pyyaml
from geometry_msgs.msg import Pose
from nav_msgs.msg import MapMetaData, OccupancyGrid
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from std_msgs.msg import Bool
from std_srvs.srv import Trigger

_LATCHED_QOS = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)

# 시뮬 기본값 — launch 파라미터로 오버라이드 가능 (실차: 'aip2,aip3', spawn_in_gazebo:=false)
_DEFAULT_LEADER    = 'peer_1'
_DEFAULT_FOLLOWERS = 'peer_2,peer_3'
_DEFAULT_SPAWN_STAGGER = {'peer_2': 0.0, 'peer_3': 90.0}  # Gazebo 전용 스태거(s)
_CM_TIMEOUT      = 90.0   # controller_manager 응답 최대 대기 (s)
_TF_TIMEOUT      = 60.0   # odom→base_link TF 안정화 대기 최대 (s)
_MAP_DIR         = Path.home() / 'aip_maps'  # 영구 맵 저장 디렉토리
_SAVED_MAP_STEM  = str(_MAP_DIR / 'latest_fleet_map')  # skip_explore 시 사용할 저장 맵


class FollowerTriggerNode(Node):
    def __init__(self):
        super().__init__('follower_trigger_node')

        self.declare_parameter('leader',          _DEFAULT_LEADER)
        self.declare_parameter('follower_ids',    _DEFAULT_FOLLOWERS)
        self.declare_parameter('spawn_in_gazebo', True)
        self.declare_parameter('with_patrol',     False)
        self.declare_parameter('skip_explore',    False)
        self.declare_parameter('patrol_start_delay', 40.0)

        self._leader       = self.get_parameter('leader').value
        self._spawn_gazebo = self.get_parameter('spawn_in_gazebo').value
        self._with_patrol  = self.get_parameter('with_patrol').value
        self._skip_explore = self.get_parameter('skip_explore').value
        self._patrol_delay = self.get_parameter('patrol_start_delay').value

        follower_str = self.get_parameter('follower_ids').value
        follower_ids = [v.strip() for v in follower_str.split(',') if v.strip()]
        all_ids = [self._leader] + follower_ids

        # 차량별 파라미터를 vehicle_id에서 동적으로 선언 — peer_N/aip_N 양쪽 수용.
        self._waypoints: dict[str, list[float]] = {}
        for vid in all_ids:
            self.declare_parameter(f'waypoints_{vid}', [0.0, 0.0, 0.0])
            self._waypoints[vid] = list(self.get_parameter(f'waypoints_{vid}').value)

        self._spawn_pose: dict[str, tuple[float, float, float]] = {}
        self._spawn_stagger: dict[str, float] = {}
        for vid in follower_ids:
            default_stagger = _DEFAULT_SPAWN_STAGGER.get(vid, 0.0)
            self.declare_parameter(f'spawn_x_{vid}',       0.0)
            self.declare_parameter(f'spawn_y_{vid}',       0.0)
            self.declare_parameter(f'spawn_yaw_{vid}',     0.0)
            self.declare_parameter(f'spawn_stagger_{vid}', default_stagger)
            self._spawn_pose[vid] = (
                self.get_parameter(f'spawn_x_{vid}').value,
                self.get_parameter(f'spawn_y_{vid}').value,
                self.get_parameter(f'spawn_yaw_{vid}').value,
            )
            self._spawn_stagger[vid] = self.get_parameter(f'spawn_stagger_{vid}').value

        # _followers: [(vid, stagger_sec)] — Gazebo 스폰 순서 결정용
        self._followers = [(vid, self._spawn_stagger[vid]) for vid in follower_ids]
        self._triggered     = False
        self._procs: list[subprocess.Popen] = []

        # /map_static 직접 발행 — map_server subprocess 대신 이 노드에서 직접 발행.
        # TRANSIENT_LOCAL: 나중에 subscribe한 AMCL도 맵을 받을 수 있음.
        _map_qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self._map_static_pub = self.create_publisher(OccupancyGrid, '/map_static', _map_qos)

        # /map 실시간 캐시 — 저장 맵 파일 없을 때 fallback으로 사용
        self._live_map_msg: OccupancyGrid | None = None
        self._live_map_event = threading.Event()
        self._map_live_sub = self.create_subscription(
            OccupancyGrid, '/map', self._on_live_map, _LATCHED_QOS)

        self._tf_buffer   = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)

        self._sub = self.create_subscription(
            Bool, '/fleet/map_ready', self._on_ready, _LATCHED_QOS)

        # skip_explore 모드: 'ros2 topic pub --once'는 DDS discovery 완료 전에
        # 발행·종료하므로 TRANSIENT_LOCAL 히스토리가 소실될 수 있음.
        # 토픽 의존 대신 타이머로 직접 트리거 — 이 노드 시작(t=50s) 후 10s = t=60s.
        # t=60s 기준: slam_toolbox(t=16s~)와 peer_1 Nav2(t=40s~) 모두 충분히 안정화됨.
        if self._skip_explore:
            self._auto_timer = self.create_timer(10.0, self._auto_trigger_once)

        # B. 수동 저장 서비스 — 언제든지 호출 가능
        self._save_srv = self.create_service(
            Trigger, '/save_map_now', self._on_save_map_service)

        _MAP_DIR.mkdir(parents=True, exist_ok=True)
        self.get_logger().info(
            f'follower_trigger_node 대기 중 … '
            f'(with_patrol={self._with_patrol}, skip_explore={self._skip_explore})\n'
            f'  맵 저장 디렉토리: {_MAP_DIR}\n'
            f'  수동 저장: ros2 service call /save_map_now std_srvs/srv/Trigger'
        )

    # ── /map 실시간 캐시 콜백 ───────────────────────────────────────────────
    def _on_live_map(self, msg: OccupancyGrid):
        self._live_map_msg = msg
        self._live_map_event.set()

    # ── skip_explore 자동 트리거 (토픽 대신 타이머) ─────────────────────────
    def _auto_trigger_once(self):
        self._auto_timer.cancel()   # 1회만 실행
        self.get_logger().info('skip_explore 자동 트리거 — slam_toolbox 안정화 확인 후 기동')
        self._on_ready(Bool(data=True))

    # ── 맵 준비 신호 ────────────────────────────────────────────────────────
    def _on_ready(self, msg: Bool):
        if not msg.data or self._triggered:
            return
        self._triggered = True
        self.get_logger().info('/fleet/map_ready 수신 — 팔로워 Nav2 기동 시작')
        threading.Thread(target=self._launch_all, daemon=True).start()

    def _stop_peer1_exploration(self):
        """explore_lite 중단 + peer_1 현재 네비게이션 취소 — 맵 안정화.

        순서:
          1. explore_lite 프로세스 종료 (새 goal 전송 차단)
          2. bt_navigator action cancel (현재 진행 중인 goal 취소)
          3. 10s 대기 (peer_1 정지 + SLAM 맵 최종 안정화)
        """
        self.get_logger().info('peer_1 탐색 중단 시작 — 맵 안정화 대기 …')

        # explore_lite 프로세스 종료
        try:
            subprocess.run(
                ['pkill', '-SIGTERM', '-f', 'explore_lite/explore'],
                capture_output=True, timeout=5.0,
            )
            self.get_logger().info('explore_lite 종료 신호 전송')
        except Exception as e:
            self.get_logger().warn(f'explore_lite 종료 실패: {e}')

        # bt_navigator 현재 goal 취소 (리더 이동 중단)
        try:
            subprocess.run(
                [
                    'ros2', 'service', 'call',
                    f'/{self._leader}/navigate_to_pose/_action/cancel_goal',
                    'action_msgs/srv/CancelGoal', '{}',
                ],
                capture_output=True, text=True, timeout=10.0,
                env=os.environ.copy(),
            )
            self.get_logger().info(f'{self._leader} 네비게이션 취소 완료')
        except Exception as e:
            self.get_logger().warn(f'{self._leader} nav 취소 실패: {e}')

        # 리더 정지 + SLAM 마지막 스캔 반영 대기
        self.get_logger().info(f'{self._leader} 정지 확인 중 (10s 대기) …')
        time.sleep(10.0)
        self.get_logger().info('맵 안정화 완료 — 팔로워 스폰 진행')

    # ── 팔로워 순차 기동 (별도 스레드) ──────────────────────────────────────
    def _launch_all(self):
        if self._skip_explore:
            # skip_explore: 탐색 없이 저장 맵 사용 → peer_1 중단 불필요
            self.get_logger().info('skip_explore=true — explore_lite 중단 건너뜀')
        else:
            # 1단계: explore_lite + peer_1 네비게이션 중단
            # 이유: peer_2/3 스폰 전 SLAM 맵이 안정화돼야 AMCL 수렴 가능.
            #       explore가 실행 중이면 peer_1이 계속 이동 → /map 실시간 변경 → AMCL 실패.
            self._stop_peer1_exploration()

        # 2단계: 맵 안정화 대기 후 저장 → 정적 map_server 기동.
        # peer_2/3 스폰 시 peer_1 LiDAR가 차체를 감지 → SLAM 맵에 phantom wall.
        # 저장된 정적 맵(/map_static)을 AMCL에 제공하면 오염 영향 없음.
        self._freeze_map_and_serve()

        # 3단계: peer_1 patrol 시작 (탐색 완료 or skip_explore 직후).
        # peer_1 Nav2는 leader_nav가 t=40s에 이미 기동 → follow_path 서버 대기만 하면 됨.
        # peer_2/3 스폰과 병렬로 진행 (스레드 분리).
        if self._with_patrol:
            threading.Thread(
                target=self._launch_patrol_leader, daemon=True
            ).start()

        for vid, stagger in self._followers:
            if stagger > 0.0:
                self.get_logger().info(
                    f'{vid}: 이전 차량 초기화 대기 중 ({stagger:.0f}s) …'
                )
                time.sleep(stagger)
            if self._spawn_gazebo:
                self._spawn_in_gazebo(vid)   # 매핑 완료 후 Gazebo 스폰
            self._wait_for_cm(vid)
            self._wait_for_tf(vid)       # EKF: odom→base_link 확인
            self._launch_nav2(vid)
            self._wait_for_amcl_tf(vid)  # AMCL: map→base_link 수렴 확인
            if self._with_patrol:
                threading.Thread(
                    target=self._launch_patrol, args=(vid,), daemon=True
                ).start()

    # ── 맵 영구 저장 (공통 헬퍼) ────────────────────────────────────────────
    def _save_map_permanent(self, label: str = '') -> tuple[bool, str]:
        """~/aip_maps/ 에 타임스탬프 파일명으로 맵 저장 + latest 심볼릭 링크 갱신.

        Returns (success, message).
        """
        ts   = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        tag  = f'_{label}' if label else ''
        stem = f'{ts}{tag}_fleet_map'
        dest = str(_MAP_DIR / stem)

        self.get_logger().info(f'영구 맵 저장 중 → {dest}.yaml …')
        try:
            result = subprocess.run(
                [
                    'ros2', 'run', 'nav2_map_server', 'map_saver_cli',
                    '-f', dest,
                    '--ros-args',
                    '-p', 'use_sim_time:=true',
                ],
                capture_output=True, text=True, timeout=20.0,
            )
            if result.returncode != 0:
                msg = f'map_saver_cli 실패: {result.stderr[:200]}'
                self.get_logger().warn(msg)
                return False, msg
        except Exception as e:
            msg = f'map_saver_cli 예외: {e}'
            self.get_logger().warn(msg)
            return False, msg

        # latest 심볼릭 링크 갱신 (최신 맵을 항상 동일 경로로 참조 가능)
        for ext in ('.yaml', '.pgm'):
            link = _MAP_DIR / f'latest_fleet_map{ext}'
            try:
                link.unlink(missing_ok=True)
                link.symlink_to(f'{stem}{ext}')
            except Exception as e:
                self.get_logger().warn(f'심볼릭 링크 생성 실패: {e}')

        msg = f'영구 저장 완료 → {dest}.yaml'
        self.get_logger().info(msg)
        return True, msg

    # ── B. 수동 저장 서비스 핸들러 ──────────────────────────────────────────
    def _on_save_map_service(self,
                              request: Trigger.Request,
                              response: Trigger.Response) -> Trigger.Response:
        """ros2 service call /save_map_now std_srvs/srv/Trigger 로 호출."""
        ok, msg = self._save_map_permanent('manual')
        response.success = ok
        response.message = msg
        return response

    def _freeze_map_and_serve(self):
        """SLAM 맵 저장 → nav2_map_server로 /map_static 발행.

        peer 스폰 이전에 호출: 스폰 후 peer_1 LiDAR가 차체를 감지해도
        이미 저장된 /map_static에는 phantom wall이 없으므로 AMCL 수렴 안정.

        skip_explore=true: ~/aip_maps/latest_fleet_map 을 직접 복사해 사용.
        skip_explore=false: map_saver_cli 로 현재 SLAM 맵을 저장.

        slam_toolbox save_map 서비스는 내부적으로 map_saver lifecycle 노드를 생성하는데,
        use_sim_time 없이 실행되어 sim_time 환경에서 /map 구독 타임스탬프 불일치로 실패.
        → map_saver_cli를 use_sim_time:=true로 직접 실행하여 대체.
        """
        map_path = '/tmp/fleet_map_static'

        if self._skip_explore:
            # 저장된 맵을 /tmp 로 복사해서 map_server 에 제공
            import re
            import shutil
            saved_ok = all(Path(_SAVED_MAP_STEM + ext).exists() for ext in ('.yaml', '.pgm'))
            if not saved_ok:
                self.get_logger().warn(
                    f'저장 맵 없음 ({_SAVED_MAP_STEM}) — /map 직접 재발행으로 fallback'
                )
                self._republish_live_map_as_static()
                return
            for ext in ('.yaml', '.pgm'):
                src = Path(_SAVED_MAP_STEM + ext)
                dst = Path(map_path + ext)
                if not src.exists():
                    self.get_logger().error(
                        f'저장 맵 없음: {src}. '
                        'aip_map_solo 로 먼저 매핑 후 저장하세요.'
                    )
                    return
                shutil.copy2(src, dst)
                self.get_logger().info(f'맵 파일 복사: {src} → {dst}')
                # YAML 내 image 경로를 복사된 PGM 절대경로로 교정.
                # map_saver_cli는 상대경로(파일명만) 또는 절대경로 모두 사용 가능 →
                # image: 줄 전체를 regex로 교체해 두 경우 모두 처리.
                if ext == '.yaml':
                    text = dst.read_text()
                    new_text = re.sub(
                        r'^image:.*$',
                        f'image: {map_path}.pgm',
                        text,
                        flags=re.MULTILINE,
                    )
                    dst.write_text(new_text)
                    self.get_logger().info(
                        f'YAML image 경로 교정 완료 → {map_path}.pgm'
                    )
            self.get_logger().info(f'저장 맵 복사 완료 → {map_path}.yaml')
        else:
            self.get_logger().info(f'SLAM 맵 저장 중 → {map_path}.yaml …')
            try:
                result = subprocess.run(
                    [
                        'ros2', 'run', 'nav2_map_server', 'map_saver_cli',
                        '-f', map_path,
                        '--ros-args',
                        '-p', 'use_sim_time:=true',
                    ],
                    capture_output=True, text=True, timeout=20.0,
                )
                if result.returncode != 0:
                    self.get_logger().warn(f'map_saver_cli 실패: {result.stderr[:200]}')
                    return
                self.get_logger().info('맵 저장 완료')
            except Exception as e:
                self.get_logger().warn(f'map_saver_cli 예외: {e}')
                return

            # A. 자동 영구 저장 (explore 완료 시 ~/aip_maps/ 에 보존)
            threading.Thread(
                target=self._save_map_permanent,
                args=('auto',),
                daemon=True,
            ).start()

        # /map_static 직접 발행 — map_server subprocess/lifecycle 불필요
        self._publish_map_static(f'{map_path}.yaml')

    def _republish_live_map_as_static(self):
        """/map 토픽을 직접 /map_static으로 재발행 (저장 맵 파일 없을 때 fallback)."""
        self.get_logger().info('/map 수신 대기 중 (최대 60s) …')
        got_it = self._live_map_event.wait(timeout=60.0)
        if not got_it or self._live_map_msg is None:
            self.get_logger().error('/map 수신 실패 (60s 타임아웃) — AMCL 맵 없이 진행')
            return
        msg = self._live_map_msg
        msg.header.stamp = self.get_clock().now().to_msg()
        self._map_static_pub.publish(msg)
        self._map_static_grid = msg
        if not hasattr(self, '_map_republish_timer'):
            self._map_republish_timer = self.create_timer(3.0, self._on_map_republish_timer)
        self.get_logger().info(
            f'/map_static 발행 완료 ({msg.info.width}×{msg.info.height}) '
            f'— /map 직접 복사 (fallback)'
        )
        # 향후 runs를 위해 백그라운드로 맵 파일 저장
        threading.Thread(target=self._save_live_map_to_disk, daemon=True).start()

    def _save_live_map_to_disk(self):
        """현재 /map을 ~/aip_maps/latest_fleet_map에 저장 (향후 skip_explore 재사용)."""
        try:
            result = subprocess.run(
                [
                    'ros2', 'run', 'nav2_map_server', 'map_saver_cli',
                    '-f', str(_SAVED_MAP_STEM),
                    '--ros-args', '-p', 'use_sim_time:=true',
                ],
                capture_output=True, text=True, timeout=30.0,
                env=os.environ.copy(),
            )
            if result.returncode == 0:
                self.get_logger().info(f'맵 파일 저장 완료 → {_SAVED_MAP_STEM}.yaml')
            else:
                self.get_logger().warn(f'맵 파일 저장 실패: {result.stderr[:200]}')
        except Exception as e:
            self.get_logger().warn(f'맵 파일 저장 예외: {e}')

    def _publish_map_static(self, yaml_path: str):
        """YAML+PGM 파일을 읽어 /map_static(OccupancyGrid)을 직접 발행.

        외부 map_server subprocess + lifecycle 전환 없이 이 노드 내에서 직접 발행.
        TRANSIENT_LOCAL QoS — 나중에 subscribe한 AMCL도 맵을 받을 수 있음.
        """
        try:
            with open(yaml_path) as f:
                meta = pyyaml.safe_load(f)

            resolution       = float(meta['resolution'])
            origin           = meta['origin']          # [x, y, theta]
            negate           = int(meta.get('negate', 0))
            occupied_thresh  = float(meta.get('occupied_thresh', 0.65))
            free_thresh      = float(meta.get('free_thresh', 0.25))

            image_path = meta['image']
            if not Path(image_path).is_absolute():
                image_path = str(Path(yaml_path).parent / image_path)

            with open(image_path, 'rb') as f:
                magic = f.readline().decode().strip()
                if magic not in ('P5', 'P2'):
                    self.get_logger().error(f'지원되지 않는 PGM 형식: {magic}')
                    return
                line = f.readline().decode().strip()
                while line.startswith('#'):
                    line = f.readline().decode().strip()
                width, height = map(int, line.split())
                maxval = int(f.readline().decode().strip())
                if magic == 'P5':
                    raw = f.read()
                    pixels = list(struct.unpack(f'{width * height}B', raw[:width * height]))
                else:
                    pixels = list(map(int, f.read().split()))

            # trinary 변환 + 행 역순.
            # PGM: 행 0 = 이미지 상단. OccupancyGrid: 행 0 = 세계 y=0 (하단).
            # nav2_map_server와 동일하게 PGM을 아래→위 순서로 읽어야 방향이 일치.
            occupancy: list[int] = []
            for row in range(height - 1, -1, -1):   # PGM 하단부터 역순
                for col in range(width):
                    px = pixels[row * width + col]
                    norm = (maxval - px) / maxval if negate == 0 else px / maxval
                    if norm < free_thresh:
                        occupancy.append(0)     # free
                    elif norm > occupied_thresh:
                        occupancy.append(100)   # occupied
                    else:
                        occupancy.append(-1)    # unknown

            grid = OccupancyGrid()
            grid.header.frame_id = 'map'
            grid.header.stamp = self.get_clock().now().to_msg()
            grid.info.resolution = resolution
            grid.info.width  = width
            grid.info.height = height
            grid.info.origin.position.x = float(origin[0])
            grid.info.origin.position.y = float(origin[1])
            grid.info.origin.position.z = 0.0
            grid.info.origin.orientation.w = 1.0
            grid.data = occupancy

            self._map_static_pub.publish(grid)
            self.get_logger().info(
                f'/map_static 발행 완료 ({width}×{height} px, {resolution} m/px, '
                f'origin=[{origin[0]:.2f}, {origin[1]:.2f}])'
            )

            # 3초 주기 재발행 — RViz(VOLATILE)나 늦게 구독한 노드도 맵 수신 가능
            self._map_static_grid = grid
            if not hasattr(self, '_map_republish_timer'):
                self._map_republish_timer = self.create_timer(
                    3.0, self._on_map_republish_timer
                )

        except Exception as e:
            self.get_logger().error(f'/map_static 발행 실패: {e}')

    def _on_map_republish_timer(self):
        """RViz(VOLATILE) 대상 초기 재발행 — 2회 후 자동 종료.
        3회 이상 발행하면 AMCL이 map 재수신 때마다 파티클 필터를 리셋하므로
        수렴 불가 상태에 빠진다.
        """
        if not hasattr(self, '_map_republish_count'):
            self._map_republish_count = 0
        self._map_republish_count += 1

        if hasattr(self, '_map_static_grid'):
            self._map_static_grid.header.stamp = self.get_clock().now().to_msg()
            self._map_static_pub.publish(self._map_static_grid)

        if self._map_republish_count >= 2:
            self._map_republish_timer.cancel()
            self.get_logger().info('/map_static 재발행 완료 (총 3회) — 타이머 종료')

    def _spawn_in_gazebo(self, vid: str):
        """map_ready 수신 후 Gazebo에 차량 스폰 — 매핑 중 차체가 벽으로 기록되는 것을 방지."""
        sx, sy, syaw = self._spawn_pose.get(vid, (0.0, 0.0, 0.0))
        cmd = [
            'ros2', 'launch', 'aip_fleet_gazebo', 'spawn_vehicle.launch.py',
            f'vehicle_id:={vid}',
            f'spawn_x:={sx}',
            f'spawn_y:={sy}',
            'spawn_z:=0.05',
            f'spawn_yaw:={syaw}',
            'world_name:=fleet_world',
        ]
        self.get_logger().info(f'{vid}: Gazebo 스폰 시작 (x={sx}, y={sy})')
        proc = subprocess.Popen(cmd, env=os.environ.copy())
        self._procs.append(proc)
        self.get_logger().info(f'{vid}: Gazebo 스폰 프로세스 시작됨 (pid={proc.pid})')

    def _launch_patrol_leader(self):
        """리더 차량 patrol 기동 — explore/skip_explore 완료 직후 호출.

        리더 Nav2는 leader_nav.launch.py가 이미 기동했으므로
        patrol_start_delay(팔로워용) 없이 바로 follow_path 서버 확인 후 시작.
        """
        vid = self._leader
        self.get_logger().info(f'{vid}: patrol 준비 — follow_path 서버 대기 …')
        self._wait_for_follow_path(vid, timeout=120.0)
        wps    = self._waypoints.get(vid, [0.0, 0.0, 0.0])
        wp_str = '[' + ','.join(str(float(v)) for v in wps) + ']'
        cmd = [
            'ros2', 'run', 'aip_fleet_autonomous', 'patrol_node',
            '--ros-args',
            '-p', f'vehicle_id:={vid}',
            '-p', f'waypoints:={wp_str}',
            '-p', 'loop_patrol:=true',
            '-p', 'start_delay_sec:=5.0',
        ]
        self.get_logger().info(f'{vid}: patrol_node 기동')
        proc = subprocess.Popen(cmd, env=os.environ.copy())
        self._procs.append(proc)

    def _wait_for_cm(self, vid: str):
        """diff_drive_controller 활성 상태 확인 — 최대 _CM_TIMEOUT 초.

        CM 서비스 존재 여부가 아니라 실제 컨트롤러가 active 상태인지 확인한다.
        gz_ros2_control이 URDF 로딩에 실패하면 CM은 뜨더라도 컨트롤러가
        로드되지 않으므로, 서비스 유무만으로는 false positive가 발생한다.
        """
        deadline = time.monotonic() + _CM_TIMEOUT
        self.get_logger().info(f'{vid}: diff_drive_controller 활성 대기 중 …')
        while time.monotonic() < deadline:
            try:
                result = subprocess.run(
                    ['ros2', 'control', 'list_controllers',
                     '--controller-manager', f'/{vid}/controller_manager'],
                    capture_output=True, text=True, timeout=5.0,
                    env=os.environ.copy(),
                )
                if 'diff_drive_controller' in result.stdout and 'active' in result.stdout:
                    self.get_logger().info(f'{vid}: diff_drive_controller active 확인 ✓')
                    return
            except Exception:
                pass
            time.sleep(3.0)
        self.get_logger().warn(
            f'{vid}: diff_drive_controller 타임아웃 — Nav2 강제 기동'
        )

    def _wait_for_tf(self, vid: str):
        """EKF가 odom→base_link TF를 안정적으로 발행할 때까지 대기 — 최대 _TF_TIMEOUT 초.

        TF가 없는 상태에서 AMCL이 기동되면 파티클 전파 실패로 map→odom TF를
        발행하지 못해 TF 트리 단절이 발생한다.  Nav2 기동 전 여기서 확인한다.
        """
        parent = f'{vid}/odom'
        child  = f'{vid}/base_link'
        deadline = time.monotonic() + _TF_TIMEOUT
        self.get_logger().info(f'{vid}: EKF TF ({parent}→{child}) 안정화 대기 …')
        consecutive_ok = 0
        while time.monotonic() < deadline:
            try:
                self._tf_buffer.lookup_transform(
                    parent, child, rclpy.time.Time(),
                    timeout=Duration(seconds=1.0),
                )
                consecutive_ok += 1
                if consecutive_ok >= 3:   # 3회 연속 성공 = 안정
                    self.get_logger().info(f'{vid}: TF 안정화 확인 — Nav2 기동')
                    return
            except Exception:
                consecutive_ok = 0
            time.sleep(1.0)
        self.get_logger().warn(
            f'{vid}: TF 안정화 타임아웃 — Nav2 강제 기동 (AMCL 초기화 실패 가능성 있음)'
        )

    def _launch_nav2(self, vid: str):
        cmd = [
            'ros2', 'launch', 'aip_fleet_autonomous',
            'autonomous_nav.launch.py',
            f'vehicle_id:={vid}',
        ]
        self.get_logger().info(f'{vid}: Nav2 기동: {" ".join(cmd)}')
        proc = subprocess.Popen(cmd, env=os.environ.copy())
        self._procs.append(proc)
        self.get_logger().info(f'{vid}: Nav2 시작됨 (pid={proc.pid})')

    def _wait_for_amcl_tf(self, vid: str, timeout: float = 90.0) -> bool:
        """AMCL이 map→{vid}/base_link TF를 안정적으로 발행할 때까지 대기.

        odom→base_link (EKF) 확인 후 Nav2를 기동해도 map→odom (AMCL) TF는
        첫 레이저 스캔 처리 완료 후에야 발행된다. 이 메서드는 AMCL 수렴까지
        대기해 planner_server의 'Timed out waiting for transform' 오류를 방지.
        """
        child = f'{vid}/base_link'
        deadline = time.monotonic() + timeout
        consecutive_ok = 0
        self.get_logger().info(
            f'{vid}: AMCL TF (map→{child}) 수렴 대기 (최대 {timeout:.0f}s) …'
        )
        while time.monotonic() < deadline:
            try:
                self._tf_buffer.lookup_transform(
                    'map', child, rclpy.time.Time(),
                    timeout=Duration(seconds=2.0),
                )
                consecutive_ok += 1
                if consecutive_ok >= 3:
                    self.get_logger().info(f'{vid}: AMCL TF 수렴 완료 ✓')
                    return True
            except Exception:
                consecutive_ok = 0
            time.sleep(2.0)
        self.get_logger().warn(
            f'{vid}: AMCL TF 수렴 타임아웃 — patrol 진행 (위치 추정 불안정 가능성)'
        )
        return False

    def _wait_for_follow_path(self, vid: str, timeout: float = 120.0) -> bool:
        """follow_path 액션 서버가 실제로 응답할 때까지 대기.

        controller_server가 ACTIVE 상태가 되어야 follow_path 서버가 열림.
        RotationShim 같은 무거운 플러그인은 초기화 시간이 길어질 수 있음.
        """
        deadline = time.monotonic() + timeout
        action   = f'/{vid}/follow_path'
        self.get_logger().info(f'{vid}: follow_path 액션 서버 대기 (최대 {timeout:.0f}s) …')
        while time.monotonic() < deadline:
            try:
                result = subprocess.run(
                    ['ros2', 'action', 'info', action],
                    capture_output=True, text=True, timeout=5.0,
                    env=os.environ.copy(),
                )
                # "Action: /<vid>/follow_path\nAction clients: 0\nAction servers: 1" 패턴
                if 'Action servers: 1' in result.stdout:
                    self.get_logger().info(f'{vid}: follow_path 액션 서버 확인 ✓')
                    return True
            except Exception:
                pass
            time.sleep(3.0)
        self.get_logger().warn(
            f'{vid}: follow_path 서버 타임아웃 — patrol 강제 시작 (controller 이상 가능성)')
        return False

    def _launch_patrol(self, vid: str):
        """Nav2 lifecycle activate + follow_path 서버 확인 후 patrol_node 기동."""
        time.sleep(self._patrol_delay)
        # 고정 대기 후 액션 서버가 실제 응답하는지 추가 확인
        self._wait_for_follow_path(vid, timeout=120.0)
        wps   = self._waypoints.get(vid, [0.0, 0.0, 0.0])
        wp_str = '[' + ','.join(str(float(v)) for v in wps) + ']'
        cmd = [
            'ros2', 'run', 'aip_fleet_autonomous', 'patrol_node',
            '--ros-args',
            '-p', f'vehicle_id:={vid}',
            '-p', f'waypoints:={wp_str}',
            '-p', 'loop_patrol:=true',
            '-p', 'start_delay_sec:=5.0',
        ]
        self.get_logger().info(f'{vid}: patrol_node 기동')
        proc = subprocess.Popen(cmd, env=os.environ.copy())
        self._procs.append(proc)

    def destroy_node(self):
        for p in self._procs:
            try:
                p.terminate()
            except Exception:
                pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = FollowerTriggerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
