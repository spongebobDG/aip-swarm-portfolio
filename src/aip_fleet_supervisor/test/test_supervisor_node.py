import time
import json
import pytest
import rclpy
from unittest.mock import MagicMock, call
from geometry_msgs.msg import Twist
from std_msgs.msg import Bool, String

from aip_fleet_msgs.msg import FleetHeartbeat, OverrideCommand
from aip_fleet_supervisor.supervisor_node import SupervisorNode


@pytest.fixture(scope='module')
def ros_context():
    rclpy.init(args=[])
    yield
    rclpy.try_shutdown()


@pytest.fixture
def node(ros_context):
    n = SupervisorNode()
    for vid in n.vehicle_ids:
        n._estop_pubs[vid].publish = MagicMock()
        n._estop_lock_pubs[vid].publish = MagicMock()
        n._override_twist_pubs[vid].publish = MagicMock()
    n._status_pub.publish = MagicMock()
    n._control_lock_state_pub.publish = MagicMock()
    yield n
    n.destroy_node()


def _override(vehicle_id='aip1', command=OverrideCommand.CMD_ESTOP, manual_cmd_vel=None):
    msg = OverrideCommand()
    msg.vehicle_id = vehicle_id
    msg.command = command
    if manual_cmd_vel is not None:
        msg.manual_cmd_vel = manual_cmd_vel
    return msg


def _heartbeat(vehicle_id='aip1'):
    hb = FleetHeartbeat()
    hb.robot_id = vehicle_id
    return hb


def _control_lock(operator_id='op-a', vehicle_id='aip1', locked=True):
    return String(data=json.dumps({
        'operator_id': operator_id,
        'vehicle_id': vehicle_id,
        'locked': locked,
    }))


# ---------------------------------------------------------------------------
# _on_override: CMD_ESTOP
# ---------------------------------------------------------------------------

class TestEstop:
    def test_adds_to_locked_set(self, node):
        node._estop_locked.discard('aip1')
        node._on_override(_override('aip1', OverrideCommand.CMD_ESTOP))
        assert 'aip1' in node._estop_locked

    def test_publishes_lock_true(self, node):
        node._on_override(_override('aip1', OverrideCommand.CMD_ESTOP))
        node._estop_lock_pubs['aip1'].publish.assert_called_with(Bool(data=True))

    def test_publishes_estop_true(self, node):
        node._on_override(_override('aip1', OverrideCommand.CMD_ESTOP))
        node._estop_pubs['aip1'].publish.assert_called_with(Bool(data=True))

    def test_publishes_zero_twist(self, node):
        node._on_override(_override('aip1', OverrideCommand.CMD_ESTOP))
        node._override_twist_pubs['aip1'].publish.assert_called_with(Twist())


# ---------------------------------------------------------------------------
# _on_override: CMD_CLEAR / CMD_RESUME
# ---------------------------------------------------------------------------

class TestClearResume:
    def test_clear_removes_from_locked_set(self, node):
        node._estop_locked.add('aip2')
        node._on_override(_override('aip2', OverrideCommand.CMD_CLEAR))
        assert 'aip2' not in node._estop_locked

    def test_clear_publishes_lock_false(self, node):
        node._on_override(_override('aip2', OverrideCommand.CMD_CLEAR))
        node._estop_lock_pubs['aip2'].publish.assert_called_with(Bool(data=False))

    def test_clear_publishes_estop_false(self, node):
        node._on_override(_override('aip2', OverrideCommand.CMD_CLEAR))
        node._estop_pubs['aip2'].publish.assert_called_with(Bool(data=False))

    def test_resume_removes_from_locked_set(self, node):
        node._estop_locked.add('aip3')
        node._on_override(_override('aip3', OverrideCommand.CMD_RESUME))
        assert 'aip3' not in node._estop_locked

    def test_resume_publishes_lock_false(self, node):
        node._on_override(_override('aip3', OverrideCommand.CMD_RESUME))
        node._estop_lock_pubs['aip3'].publish.assert_called_with(Bool(data=False))


# ---------------------------------------------------------------------------
# _on_override: CMD_PAUSE / CMD_MANUAL
# ---------------------------------------------------------------------------

class TestPauseManual:
    def test_pause_publishes_zero_twist(self, node):
        node._on_override(_override('aip1', OverrideCommand.CMD_PAUSE))
        node._override_twist_pubs['aip1'].publish.assert_called_with(Twist())

    def test_pause_does_not_touch_estop(self, node):
        node._on_override(_override('aip1', OverrideCommand.CMD_PAUSE))
        node._estop_pubs['aip1'].publish.assert_not_called()

    def test_manual_forwards_twist(self, node):
        twist = Twist()
        twist.linear.x = 0.5
        twist.angular.z = -0.3
        node._on_override(_override('aip1', OverrideCommand.CMD_MANUAL, twist))
        node._override_twist_pubs['aip1'].publish.assert_called_with(twist)


# ---------------------------------------------------------------------------
# _on_override: wildcard and edge cases
# ---------------------------------------------------------------------------

class TestWildcardAndEdge:
    def test_wildcard_estop_all_vehicles(self, node):
        node._on_override(_override('*', OverrideCommand.CMD_ESTOP))
        for vid in node.vehicle_ids:
            assert vid in node._estop_locked
            node._estop_pubs[vid].publish.assert_called_with(Bool(data=True))

    def test_wildcard_clear_all_vehicles(self, node):
        node._estop_locked = set(node.vehicle_ids)
        node._on_override(_override('*', OverrideCommand.CMD_CLEAR))
        assert node._estop_locked == set()
        for vid in node.vehicle_ids:
            node._estop_lock_pubs[vid].publish.assert_called_with(Bool(data=False))

    def test_unknown_vehicle_does_not_crash(self, node):
        node._on_override(_override('ghost_vehicle', OverrideCommand.CMD_ESTOP))

    def test_unknown_command_does_not_crash(self, node):
        node._on_override(_override('aip1', 99))

    def test_unknown_command_no_publish(self, node):
        node._on_override(_override('aip1', 99))
        node._estop_pubs['aip1'].publish.assert_not_called()
        node._estop_lock_pubs['aip1'].publish.assert_not_called()


# ---------------------------------------------------------------------------
# _on_control_lock: operator session lock bookkeeping
# ---------------------------------------------------------------------------

class TestControlLock:
    def test_lock_adds_vehicle_entry(self, node):
        node._on_control_lock(_control_lock('op-a', 'aip1', True))
        assert node._control_locks['aip1'].operator_id == 'op-a'

    def test_unlock_by_owner_removes_vehicle_entry(self, node):
        node._on_control_lock(_control_lock('op-a', 'aip1', True))
        node._on_control_lock(_control_lock('op-a', 'aip1', False))
        assert 'aip1' not in node._control_locks

    def test_unlock_by_other_operator_is_ignored(self, node):
        node._on_control_lock(_control_lock('op-a', 'aip1', True))
        node._on_control_lock(_control_lock('op-b', 'aip1', False))
        assert node._control_locks['aip1'].operator_id == 'op-a'

    def test_wildcard_lock_targets_all_vehicles(self, node):
        node._on_control_lock(_control_lock('op-a', '*', True))
        assert set(node._control_locks) == set(node.vehicle_ids)

    def test_stale_lock_is_pruned(self, node):
        node._on_control_lock(_control_lock('op-a', 'aip1', True))
        node._control_locks['aip1'].stamp_wall = time.monotonic() - node.control_lock_ttl - 0.1
        node._prune_stale_control_locks()
        assert 'aip1' not in node._control_locks

    def test_require_lock_rejects_manual_without_lock(self, node):
        node.require_control_lock = True
        twist = Twist()
        twist.linear.x = 0.5
        node._on_override(_override('aip1', OverrideCommand.CMD_MANUAL, twist))
        node._override_twist_pubs['aip1'].publish.assert_not_called()

    def test_require_lock_allows_manual_with_lock(self, node):
        node.require_control_lock = True
        node._on_control_lock(_control_lock('op-a', 'aip1', True))
        twist = Twist()
        twist.linear.x = 0.5
        node._on_override(_override('aip1', OverrideCommand.CMD_MANUAL, twist))
        node._override_twist_pubs['aip1'].publish.assert_called_with(twist)


# ---------------------------------------------------------------------------
# _publish_status: online / offline detection
# ---------------------------------------------------------------------------

class TestPublishStatus:
    def _seed_all_fresh(self, node):
        now = time.monotonic()
        for vid in node.vehicle_ids:
            node._last_heartbeat[vid] = _heartbeat(vid)
            node._last_heartbeat_wall[vid] = now

    def test_all_online_with_fresh_heartbeats(self, node):
        self._seed_all_fresh(node)
        node._publish_status()
        status = node._status_pub.publish.call_args[0][0]
        assert status.offline_vehicle_ids == []
        assert {v.robot_id for v in status.vehicles} == set(node.vehicle_ids)

    def test_stale_heartbeat_is_offline(self, node):
        self._seed_all_fresh(node)
        node._last_heartbeat_wall['aip2'] = (
            time.monotonic() - node.heartbeat_timeout - 0.1
        )
        node._publish_status()
        status = node._status_pub.publish.call_args[0][0]
        assert 'aip2' in status.offline_vehicle_ids
        assert all(v.robot_id != 'aip2' for v in status.vehicles)

    def test_never_seen_vehicle_is_offline(self, node):
        node._last_heartbeat.clear()
        node._last_heartbeat_wall.clear()
        node._publish_status()
        status = node._status_pub.publish.call_args[0][0]
        assert set(status.offline_vehicle_ids) == set(node.vehicle_ids)
        assert status.vehicles == []

    def test_only_stale_vehicle_goes_offline(self, node):
        self._seed_all_fresh(node)
        node._last_heartbeat_wall['aip3'] = (
            time.monotonic() - node.heartbeat_timeout - 0.1
        )
        node._publish_status()
        status = node._status_pub.publish.call_args[0][0]
        assert status.offline_vehicle_ids == ['aip3']
        assert len(status.vehicles) == len(node.vehicle_ids) - 1

    def test_estop_lock_reasserted_on_status_cycle(self, node):
        node._estop_locked = {'aip1'}
        node._estop_lock_pubs['aip1'].publish.reset_mock()
        node._publish_status()
        node._estop_lock_pubs['aip1'].publish.assert_called_with(Bool(data=True))

    def test_unlocked_vehicle_reasserted_false(self, node):
        node._estop_locked = set()
        node._estop_lock_pubs['aip1'].publish.reset_mock()
        node._estop_pubs['aip1'].publish.reset_mock()
        node._publish_status()
        node._estop_lock_pubs['aip1'].publish.assert_called_with(Bool(data=False))
        node._estop_pubs['aip1'].publish.assert_called_with(Bool(data=False))
