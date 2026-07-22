"""Scout ArUco localizer — detects ArUco markers on Scout vehicles from the
main AGV's camera and publishes map-frame poses as dynamic TF.

TF chain resolved at each detection:
  map → <camera_frame>         (tf2 lookup — handles both fixed mount and arm)
  <camera_frame> → marker_N   (ArUco pose estimation, cv2.aruco DICT_4X4_50)
  marker_N → scout_N/base_link (rigid offset, default identity)

=========================================================================
DEPLOYMENT MODES  (선택 — 론치 파라미터로 구분)
=========================================================================

MODE A — 차체 고정 카메라 (현재 기본값, with_localizer:=true)
  - 카메라가 main/base_link에 고정 장착.
  - central.launch.py의 static_transform_publisher가
    main/base_link → main/camera_link 정적 TF를 발행.
  - 연속적인 위치추정, 구현 단순.

MODE B — 4-DOF 서보 암 탑재 카메라 (미구현, 확장 예정)
  STATUS: 개발 일시 중단 (2026-04-23)

  재개 조건:
    1. 암 제어기가 ROS2에 JointState 또는 직접 TF를 발행해야 함.
       확인 명령: ros2 topic list | grep -E 'joint|arm'
    2. URDF + robot_state_publisher 로 FK → TF 체인 구성,
       또는 암 드라이버가 end-effector TF를 직접 퍼블리시.
    3. central.launch.py에서 static_transform_publisher를 제거하고
       camera_frame 파라미터를 암 end-effector 프레임명으로 변경:
         camera_frame: "main/arm_camera_link"  # 암 드라이버가 발행하는 프레임
    4. 온도 모니터링 ↔ 위치추정 스캔 모드 전환 로직 추가.
       (암이 Scout를 향하지 않을 때 coordinator는 마지막 유효 pose 캐시 사용)

  이 노드 자체는 수정 불필요 — tf2 lookup이 동적 TF를 이미 지원함.

=========================================================================
HARDWARE CHECKLIST  (MODE A 기준)
=========================================================================
  [ ] 광각 USB 카메라 ($20–40, 110° FOV 퓨전센서 RGB 채널 활용 가능)
  [ ] ArUco 마커 인쇄: DICT_4X4_50, ID=1(aip2), ID=2(aip3), 변 15 cm
  [ ] 카메라 캘리브레이션:
        ros2 run camera_calibration cameracalibrator \
            --size 8x6 --square 0.025 \
            image:=/aip1/camera/image_raw \
            camera:=/aip1/camera
  [ ] camera_offset_x/y/z 측정 후 launch 인자로 전달

=========================================================================
Parameters
=========================================================================
camera_ns         : str    = "aip1"               topic prefix (/<ns>/camera/*)
camera_frame      : str    = "main/camera_link"   TF frame of the camera
marker_size       : float  = 0.15                 physical marker side length (m)
marker_ids        : int[]  = [1, 2]               ArUco marker IDs (DICT_4X4_50)
marker_namespaces : str[]  = ["aip2","aip3"] vehicle ns per marker id
marker_offset_x/y/z : float = 0.0                marker centre → Scout base_link
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import cv2
import cv2.aruco as aruco
import numpy as np

import rclpy
import rclpy.duration
import rclpy.time
from cv_bridge import CvBridge
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy,
)
from sensor_msgs.msg import CameraInfo, Image
import tf2_ros


# Use the legacy OpenCV 4.5 aruco API (contrib, available in ROS2 Humble).
_ARUCO_DICT = aruco.Dictionary_get(aruco.DICT_4X4_50)
_ARUCO_PARAMS = aruco.DetectorParameters_create()


def _rvec_tvec_to_matrix(rvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    """Convert OpenCV (rvec, tvec) to a 4×4 homogeneous transform matrix."""
    R, _ = cv2.Rodrigues(rvec)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = tvec.flatten()
    return T


def _matrix_to_tf(mat: np.ndarray, stamp, parent: str, child: str) -> TransformStamped:
    t = TransformStamped()
    t.header.stamp = stamp
    t.header.frame_id = parent
    t.child_frame_id = child

    t.transform.translation.x = float(mat[0, 3])
    t.transform.translation.y = float(mat[1, 3])
    t.transform.translation.z = float(mat[2, 3])

    # Extract quaternion from rotation matrix.
    R = mat[:3, :3]
    trace = R[0, 0] + R[1, 1] + R[2, 2]
    if trace > 0:
        s = 0.5 / math.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s

    norm = math.sqrt(x*x + y*y + z*z + w*w)
    t.transform.rotation.x = x / norm
    t.transform.rotation.y = y / norm
    t.transform.rotation.z = z / norm
    t.transform.rotation.w = w / norm
    return t


def _tf_to_matrix(tf: TransformStamped) -> np.ndarray:
    tr = tf.transform.translation
    ro = tf.transform.rotation
    q = [ro.x, ro.y, ro.z, ro.w]
    x, y, z, w = q
    R = np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - z*w),     2*(x*z + y*w)],
        [2*(x*y + z*w),     1 - 2*(x*x + z*z),  2*(y*z - x*w)],
        [2*(x*z - y*w),     2*(y*z + x*w),       1 - 2*(x*x + y*y)],
    ])
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = [tr.x, tr.y, tr.z]
    return T


class ScoutLocalizerNode(Node):
    def __init__(self) -> None:
        super().__init__('scout_localizer_node')

        self.declare_parameter('camera_ns', 'aip1')
        self.declare_parameter('camera_frame', 'main/camera_link')
        self.declare_parameter('marker_size', 0.15)
        self.declare_parameter('marker_ids', [1, 2])
        self.declare_parameter('marker_namespaces', ['aip2', 'aip3'])
        # Rigid offset from marker centre to Scout base_link (in marker frame).
        self.declare_parameter('marker_offset_x', 0.0)
        self.declare_parameter('marker_offset_y', 0.0)
        self.declare_parameter('marker_offset_z', 0.0)

        def p(name):
            return self.get_parameter(name).value

        self._cam_frame = str(p('camera_frame'))
        self._marker_size = float(p('marker_size'))
        ids_raw = p('marker_ids')
        ns_raw = p('marker_namespaces')
        if len(ids_raw) != len(ns_raw):
            raise ValueError('marker_ids and marker_namespaces must have the same length')
        self._marker_map: Dict[int, str] = dict(zip(ids_raw, ns_raw))

        # Constant marker → base_link offset (identity by default).
        ox, oy, oz = float(p('marker_offset_x')), float(p('marker_offset_y')), float(p('marker_offset_z'))
        self._T_marker_base = np.eye(4)
        self._T_marker_base[:3, 3] = [ox, oy, oz]

        self._bridge = CvBridge()
        self._camera_matrix: Optional[np.ndarray] = None
        self._dist_coeffs: Optional[np.ndarray] = None

        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)
        self._tf_broadcaster = tf2_ros.TransformBroadcaster(self)

        cam_ns = str(p('camera_ns'))
        best_effort = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        transient = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.create_subscription(
            CameraInfo, f'/{cam_ns}/camera/camera_info', self._on_camera_info, transient
        )
        self.create_subscription(
            Image, f'/{cam_ns}/camera/image_raw', self._on_image, best_effort
        )

        self.get_logger().info(
            f'ScoutLocalizer: tracking {list(self._marker_map.values())} '
            f'via {self._cam_frame}, marker_size={self._marker_size} m'
        )

    # ------------------------------------------------------------------

    def _on_camera_info(self, msg: CameraInfo) -> None:
        self._camera_matrix = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        self._dist_coeffs = np.array(msg.d, dtype=np.float64)

    def _on_image(self, msg: Image) -> None:
        if self._camera_matrix is None:
            return

        try:
            frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().warning(f'cv_bridge error: {e}')
            return

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = aruco.detectMarkers(gray, _ARUCO_DICT, parameters=_ARUCO_PARAMS)

        if ids is None or len(ids) == 0:
            return

        rvecs, tvecs, _ = aruco.estimatePoseSingleMarkers(
            corners, self._marker_size, self._camera_matrix, self._dist_coeffs
        )

        # Camera pose in map frame (needed once per frame).
        try:
            tf_map_cam = self._tf_buffer.lookup_transform(
                'map', self._cam_frame,
                rclpy.time.Time(),
                timeout=rclpy.duration.Duration(seconds=0.05),
            )
        except (tf2_ros.LookupException, tf2_ros.ConnectivityException,
                tf2_ros.ExtrapolationException):
            return

        T_map_cam = _tf_to_matrix(tf_map_cam)
        stamp = msg.header.stamp

        for i, marker_id_arr in enumerate(ids):
            mid = int(marker_id_arr[0])
            if mid not in self._marker_map:
                continue

            scout_ns = self._marker_map[mid]
            T_cam_marker = _rvec_tvec_to_matrix(rvecs[i], tvecs[i])

            # map → scout/base_link = T_map_cam × T_cam_marker × T_marker_base
            T_map_scout = T_map_cam @ T_cam_marker @ self._T_marker_base

            tf_out = _matrix_to_tf(T_map_scout, stamp, 'map', f'{scout_ns}/base_link')
            self._tf_broadcaster.sendTransform(tf_out)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ScoutLocalizerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
