import pytest

from infrastructure.command_bus_controller import publish_controller_command_closed_loop


class _Tracker:
    def __init__(self, status_from_db=None, pending_ids=None) -> None:
        self._status_from_db = status_from_db
        self.pending_commands = {cmd_id: {} for cmd_id in (pending_ids or [])}
        self.wait_calls = 0
        self.confirm_calls = 0
        self.confirm_statuses = []

    async def wait_for_command_done(self, **kwargs):
        _ = kwargs
        self.wait_calls += 1
        return None

    async def _get_command_status_from_db(self, cmd_id):
        _ = cmd_id
        return self._status_from_db

    async def confirm_command_status(self, cmd_id, status, error=None):
        self.confirm_calls += 1
        self.confirm_statuses.append((cmd_id, status, error))
        self.pending_commands.pop(cmd_id, None)


class _CommandBus:
    def __init__(self, *, tracker, dedupe_decision, cmd_id="cmd-1") -> None:
        self.tracker = tracker
        self._dedupe_decision = dedupe_decision
        self._cmd_id = cmd_id
        self.zone_events = []
        self.failure_alerts = []

    async def publish_controller_command(self, zone_id, command, context=None):
        _ = zone_id, context
        command["dedupe_decision"] = self._dedupe_decision
        command["cmd_id"] = self._cmd_id
        return True

    async def _safe_create_zone_event(self, zone_id, event_type, payload):
        self.zone_events.append((zone_id, event_type, payload))

    async def _emit_closed_loop_failure_alert(self, **kwargs):
        self.failure_alerts.append(kwargs)


@pytest.mark.asyncio
async def test_closed_loop_duplicate_no_effect_without_db_row_finishes_successfully():
    tracker = _Tracker(status_from_db=None, pending_ids=[])
    bus = _CommandBus(tracker=tracker, dedupe_decision="duplicate_no_effect", cmd_id="cmd-missing")

    result = await publish_controller_command_closed_loop(
        bus,
        zone_id=9,
        command={"node_uid": "nd-test-irrig-1", "channel": "pump_main", "cmd": "set_relay"},
        context={},
        timeout_sec=1,
    )

    assert result["command_submitted"] is True
    assert result["command_effect_confirmed"] is True
    assert result["terminal_status"] == "NO_EFFECT"
    assert tracker.wait_calls == 0
    assert bus.zone_events == []
    assert bus.failure_alerts == []


@pytest.mark.asyncio
async def test_closed_loop_duplicate_no_effect_propagates_known_terminal_failure():
    tracker = _Tracker(status_from_db="TIMEOUT", pending_ids=[])
    bus = _CommandBus(tracker=tracker, dedupe_decision="duplicate_no_effect", cmd_id="cmd-timeout")

    result = await publish_controller_command_closed_loop(
        bus,
        zone_id=9,
        command={"node_uid": "nd-test-irrig-1", "channel": "pump_main", "cmd": "set_relay"},
        context={},
        timeout_sec=1,
    )

    assert result["command_submitted"] is True
    assert result["command_effect_confirmed"] is False
    assert result["terminal_status"] == "TIMEOUT"
    assert tracker.wait_calls == 0
    assert any(event[1] == "COMMAND_EFFECT_NOT_CONFIRMED" for event in bus.zone_events)
    assert len(bus.failure_alerts) == 1


@pytest.mark.asyncio
async def test_closed_loop_duplicate_no_effect_with_stale_pending_marks_no_effect():
    tracker = _Tracker(status_from_db=None, pending_ids=["cmd-stale"])
    bus = _CommandBus(tracker=tracker, dedupe_decision="duplicate_no_effect", cmd_id="cmd-stale")

    result = await publish_controller_command_closed_loop(
        bus,
        zone_id=9,
        command={"node_uid": "nd-test-irrig-1", "channel": "pump_main", "cmd": "set_relay"},
        context={},
        timeout_sec=1,
    )

    assert result["command_submitted"] is True
    assert result["command_effect_confirmed"] is True
    assert result["terminal_status"] == "NO_EFFECT"
    assert tracker.wait_calls == 0
    assert tracker.confirm_calls == 1
    assert tracker.confirm_statuses == [("cmd-stale", "NO_EFFECT", "dedupe_no_effect_without_db_row")]
    assert bus.zone_events == []
    assert bus.failure_alerts == []
