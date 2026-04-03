"""Unit tests for SequentialCommandGateway.

Covers:
 - Successful batch: single and multiple commands
 - Command publish failure → TaskExecutionError
 - Legacy status: DONE → done, ERROR → failed, TIMEOUT → failed
 - Batch stops on first failure
 - recover_waiting_command: no ae_command → raises
 - recover_waiting_command: non-terminal status → waiting_command
 - recover_waiting_command: terminal DONE → done
 - recover_waiting_command: terminal ERROR → failed
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from prometheus_client import REGISTRY

from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.errors import CommandPublishError, ErrorCodes, TaskExecutionError, TaskTerminalStateReached
from ae3lite.infrastructure.gateways import sequential_command_gateway as sequential_command_gateway_module
from ae3lite.infrastructure.gateways.sequential_command_gateway import SequentialCommandGateway
from ae3lite.infrastructure.metrics import COMMAND_POLL_ITERATIONS


NOW = datetime(2026, 3, 10, 12, 0, 0)

_DONE_ROW = {
    "id": 1001,
    "cmd_id": "hl-ae3-t1-z1-s1",
    "status": "DONE",
    "error_message": None,
    "ack_at": NOW,
    "failed_at": None,
    "updated_at": NOW,
    "sent_at": None,
    "created_at": NOW,
}
_ERROR_ROW = {**_DONE_ROW, "status": "ERROR", "error_message": "hw_error", "ack_at": None, "failed_at": NOW}
_PENDING_ROW = {**_DONE_ROW, "status": "PENDING"}
_MISSING = object()


def _planned(*, channel="pump_main", step_no=1):
    return PlannedCommand(
        node_uid="nd-1",
        channel=channel,
        payload={"cmd": "set_relay", "params": {"state": True}},
        step_no=step_no,
    )


class _FakeCommandRepo:
    def __init__(
        self,
        *,
        legacy_row=_DONE_ROW,
        ae_command_row=_MISSING,
        create_pending_returns_none: bool = False,
        accept_publish_ok: bool = True,
    ):
        self._legacy_row = legacy_row
        self._ae_command_row = (
            {"id": 9, "external_id": None, "payload": {"cmd_id": "ae3-t1-z1-s1"}}
            if ae_command_row is _MISSING
            else ae_command_row
        )
        self._create_pending_returns_none = create_pending_returns_none
        self._accept_publish_ok = accept_publish_ok
        self.step_no = 0
        self.created_ids: list[int] = []
        self.updated: list[dict] = []
        self.publish_accepted_calls: list[dict] = []
        self.publish_failed_calls: list[dict] = []

    async def get_next_step_no(self, *, task_id):
        self.step_no += 1
        return self.step_no

    async def create_pending(self, *, task_id, step_no, node_uid, channel, payload, now):
        if self._create_pending_returns_none:
            return None
        ae_id = 100 + step_no
        self.created_ids.append(ae_id)
        return ae_id

    async def resolve_greenhouse_uid(self, *, zone_id):
        return "gh-test-001"

    async def resolve_legacy_command_id(self, *, zone_id, cmd_id):
        return 1001

    async def mark_publish_accepted(self, *, ae_command_id, external_id, now):
        self.publish_accepted_calls.append(
            {"ae_command_id": ae_command_id, "external_id": external_id, "now": now}
        )
        return self._accept_publish_ok

    async def mark_publish_failed(self, *, ae_command_id, last_error, now):
        self.publish_failed_calls.append(
            {"ae_command_id": ae_command_id, "last_error": last_error, "now": now}
        )

    async def update_from_legacy(self, **_kw):
        pass

    async def get_legacy_command_by_id(self, *, external_id):
        return self._legacy_row

    async def get_legacy_command_by_cmd_id(self, *, zone_id, cmd_id):
        return self._legacy_row

    async def get_latest_for_task(self, *, task_id):
        return self._ae_command_row


class _SequencedLegacyCommandRepo(_FakeCommandRepo):
    def __init__(self, *, legacy_rows):
        super().__init__(legacy_row=legacy_rows[-1])
        self._legacy_rows = list(legacy_rows)
        self._legacy_index = 0

    async def get_legacy_command_by_cmd_id(self, *, zone_id, cmd_id):
        row = self._legacy_rows[min(self._legacy_index, len(self._legacy_rows) - 1)]
        self._legacy_index += 1
        return row


def _mock_task(task_id=1, **kwargs):
    """MagicMock task with workflow.stage_deadline_at=None by default."""
    wf = MagicMock()
    wf.stage_deadline_at = None
    m = MagicMock()
    m.id = task_id
    m.zone_id = 1
    m.claimed_by = "w1"
    m.workflow = wf
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


class _FakeTaskRepo:
    def __init__(
        self,
        *,
        resumed_task=_MISSING,
        failed_task=_MISSING,
        current_task=_MISSING,
        waiting_command_result=_MISSING,
    ):
        self._resumed = (
            _mock_task(error_code=None, error_message=None)
            if resumed_task is _MISSING
            else resumed_task
        )
        self._failed = (
            _mock_task(error_code="command_error", error_message="hw_error")
            if failed_task is _MISSING
            else failed_task
        )
        if current_task is _MISSING:
            self._current = _mock_task(status="running")
        else:
            self._current = current_task
        self._waiting_command_result = waiting_command_result

    async def mark_waiting_command(self, *, task_id, owner, now):
        if self._waiting_command_result is not _MISSING:
            return self._waiting_command_result
        return _mock_task(task_id=task_id, claimed_by=owner)

    async def resume_after_waiting_command(self, *, task_id, owner, now):
        return self._resumed

    async def get_by_id(self, *, task_id):
        return self._current

    async def mark_failed(self, *, task_id, owner, error_code, error_message, now):
        m = MagicMock(id=task_id, zone_id=1, error_code=error_code, error_message=error_message)
        return m


class _FakeHistoryLogger:
    def __init__(self, *, fail=False):
        self._fail = fail
        self.calls: list[dict] = []

    async def publish(self, *, greenhouse_uid, zone_id, node_uid, channel, cmd, params, cmd_id=None):
        self.calls.append({"cmd": cmd, "channel": channel})
        if self._fail:
            raise CommandPublishError("MQTT publish failed")
        return f"hl-{cmd_id}"


def _make_task(zone_id=1, task_id=1):
    workflow = MagicMock()
    workflow.stage_deadline_at = None
    m = MagicMock()
    m.id = task_id
    m.zone_id = zone_id
    m.claimed_by = "w1"
    m.topology = "two_tank"
    m.workflow = workflow
    return m


def _make_gw(*, command_repo=None, task_repo=None, history_logger=None, poll_interval=0.01):
    return SequentialCommandGateway(
        task_repository=task_repo or _FakeTaskRepo(),
        command_repository=command_repo or _FakeCommandRepo(),
        history_logger_client=history_logger or _FakeHistoryLogger(),
        poll_interval_sec=poll_interval,
    )


# ── run_batch: happy path ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_batch_single_command_done():
    gw = _make_gw()
    task = _make_task()
    result = await gw.run_batch(task=task, commands=[_planned()], now=NOW)
    assert result["success"] is True
    assert result["commands_total"] == 1
    assert result["commands_failed"] == 0


@pytest.mark.asyncio
async def test_run_batch_multiple_commands_all_done():
    gw = _make_gw()
    task = _make_task()
    commands = [_planned(channel="ch1"), _planned(channel="ch2"), _planned(channel="ch3")]
    result = await gw.run_batch(task=task, commands=commands, now=NOW)
    assert result["success"] is True
    assert result["commands_total"] == 3
    assert result["commands_failed"] == 0


@pytest.mark.asyncio
async def test_run_batch_complete_on_ack_resumes_task_without_terminal_wait() -> None:
    cmd_repo = _SequencedLegacyCommandRepo(legacy_rows=[{**_DONE_ROW, "status": "ACK"}])
    task_repo = _FakeTaskRepo()
    gw = _make_gw(command_repo=cmd_repo, task_repo=task_repo)
    task = _make_task()
    command = PlannedCommand(
        node_uid="nd-1",
        channel="pump_main",
        payload={"cmd": "set_relay", "params": {"state": True, "timeout_ms": 45000, "stage": "solution_fill"}, "complete_on_ack": True},
        step_no=1,
    )

    result = await gw.run_batch(task=task, commands=[command], now=NOW)

    assert result["success"] is True
    assert result["commands_total"] == 1
    assert result["command_statuses"][0]["terminal_status"] == "ACK"


@pytest.mark.asyncio
async def test_run_batch_empty_commands():
    gw = _make_gw()
    result = await gw.run_batch(task=_make_task(), commands=[], now=NOW)
    assert result["success"] is True
    assert result["commands_total"] == 0


# ── run_batch: failures ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_batch_publish_failure_raises():
    gw = _make_gw(history_logger=_FakeHistoryLogger(fail=True))
    with pytest.raises(TaskExecutionError) as exc_info:
        await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)
    assert exc_info.value.code == "command_send_failed"


@pytest.mark.asyncio
async def test_run_batch_create_pending_task_missing_returns_fail_closed():
    cmd_repo = _FakeCommandRepo(create_pending_returns_none=True)
    gw = _make_gw(command_repo=cmd_repo)
    result = await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)
    assert result["success"] is False
    assert result["error_code"] == ErrorCodes.AE3_TASK_MISSING_DURING_PUBLISH
    assert result["commands_total"] == 0


@pytest.mark.asyncio
async def test_run_batch_mark_accept_miss_task_missing_returns_fail_closed():
    cmd_repo = _FakeCommandRepo(accept_publish_ok=False)
    task_repo = _FakeTaskRepo(current_task=None)
    gw = _make_gw(command_repo=cmd_repo, task_repo=task_repo)
    result = await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)
    assert result["success"] is False
    assert result["error_code"] == ErrorCodes.AE3_TASK_MISSING_DURING_PUBLISH


@pytest.mark.asyncio
async def test_run_batch_mark_accept_miss_task_still_present_raises():
    cmd_repo = _FakeCommandRepo(accept_publish_ok=False)
    task_repo = _FakeTaskRepo(current_task=_mock_task(status="running"))
    gw = _make_gw(command_repo=cmd_repo, task_repo=task_repo)
    with pytest.raises(TaskExecutionError) as exc_info:
        await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)
    assert exc_info.value.code == "command_send_failed"


@pytest.mark.asyncio
async def test_run_batch_waiting_command_miss_task_missing_returns_fail_closed():
    task_repo = _FakeTaskRepo(waiting_command_result=None, current_task=None)
    gw = _make_gw(task_repo=task_repo)
    result = await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)
    assert result["success"] is False
    assert result["error_code"] == ErrorCodes.AE3_TASK_MISSING_DURING_PUBLISH


@pytest.mark.asyncio
async def test_run_batch_publish_exception_task_missing_returns_fail_closed():
    cmd_repo = _FakeCommandRepo()
    task_repo = _FakeTaskRepo(current_task=None)
    gw = _make_gw(
        command_repo=cmd_repo,
        history_logger=_FakeHistoryLogger(fail=True),
        task_repo=task_repo,
    )
    result = await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)
    assert result["success"] is False
    assert result["error_code"] == ErrorCodes.AE3_TASK_MISSING_DURING_PUBLISH
    assert len(cmd_repo.publish_failed_calls) == 1


@pytest.mark.asyncio
async def test_run_batch_error_status_returns_failure():
    cmd_repo = _FakeCommandRepo(legacy_row=_ERROR_ROW)
    gw = _make_gw(command_repo=cmd_repo)
    result = await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)
    assert result["success"] is False
    assert result["commands_failed"] == 1
    assert result["error_code"] == "command_error"


@pytest.mark.asyncio
async def test_run_batch_stops_after_first_failure():
    cmd_repo = _FakeCommandRepo(legacy_row=_ERROR_ROW)
    gw = _make_gw(command_repo=cmd_repo)
    result = await gw.run_batch(
        task=_make_task(),
        commands=[_planned(channel="ch1"), _planned(channel="ch2")],
        now=NOW,
    )
    assert result["success"] is False
    # Only first command attempted
    assert result["commands_total"] == 1


# ── Legacy terminal statuses ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeout_status_returns_failure():
    timeout_row = {**_DONE_ROW, "status": "TIMEOUT", "ack_at": None, "failed_at": NOW}
    cmd_repo = _FakeCommandRepo(legacy_row=timeout_row)
    gw = _make_gw(command_repo=cmd_repo)
    result = await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)
    assert result["success"] is False
    assert "timeout" in result["error_code"]


@pytest.mark.asyncio
async def test_done_status_success():
    cmd_repo = _FakeCommandRepo(legacy_row=_DONE_ROW)
    gw = _make_gw(command_repo=cmd_repo)
    result = await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)
    assert result["success"] is True


# ── recover_waiting_command ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recover_waiting_command_no_ae_command_raises():
    cmd_repo = _FakeCommandRepo(ae_command_row=None)

    async def _none(*a, **kw):
        return None

    cmd_repo.get_latest_for_task = _none
    gw = _make_gw(
        command_repo=cmd_repo,
        task_repo=_FakeTaskRepo(current_task=_mock_task(status="running")),
    )
    with pytest.raises(TaskExecutionError) as exc_info:
        await gw.recover_waiting_command(task=_make_task(), now=NOW)
    assert exc_info.value.code == "ae3_missing_ae_command"


@pytest.mark.asyncio
async def test_recover_waiting_command_no_ae_command_after_cancel_returns_done():
    cmd_repo = _FakeCommandRepo(ae_command_row=None)

    async def _none(*a, **kw):
        return None

    cmd_repo.get_latest_for_task = _none
    cancelled_task = _mock_task(status="cancelled")
    gw = _make_gw(
        command_repo=cmd_repo,
        task_repo=_FakeTaskRepo(current_task=cancelled_task),
    )
    result = await gw.recover_waiting_command(task=_make_task(), now=NOW)
    assert result["state"] == "done"
    assert result["task"] is cancelled_task


@pytest.mark.asyncio
async def test_recover_waiting_command_done_returns_done_state():
    cmd_repo = _FakeCommandRepo(legacy_row=_DONE_ROW)
    gw = _make_gw(command_repo=cmd_repo)
    result = await gw.recover_waiting_command(task=_make_task(), now=NOW)
    assert result["state"] == "done"
    assert result["legacy_status"] == "DONE"


@pytest.mark.asyncio
async def test_recover_waiting_command_done_after_task_cancel_returns_done_state():
    cmd_repo = _FakeCommandRepo(legacy_row=_DONE_ROW)
    cancelled_task = _mock_task(status="cancelled")
    gw = _make_gw(
        command_repo=cmd_repo,
        task_repo=_FakeTaskRepo(resumed_task=None, current_task=cancelled_task),
    )
    result = await gw.recover_waiting_command(task=_make_task(), now=NOW)
    assert result["state"] == "done"
    assert result["task"] is cancelled_task
    assert result["legacy_status"] == "DONE"


@pytest.mark.asyncio
async def test_run_batch_done_after_task_cancel_raises_terminal_state():
    cmd_repo = _FakeCommandRepo(legacy_row=_DONE_ROW)
    cancelled_task = _mock_task(status="cancelled")
    gw = _make_gw(
        command_repo=cmd_repo,
        task_repo=_FakeTaskRepo(resumed_task=None, current_task=cancelled_task),
    )

    with pytest.raises(TaskTerminalStateReached) as exc_info:
        await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)

    assert exc_info.value.task is cancelled_task


@pytest.mark.asyncio
async def test_recover_waiting_command_error_returns_failed_state():
    cmd_repo = _FakeCommandRepo(legacy_row=_ERROR_ROW)
    gw = _make_gw(command_repo=cmd_repo)
    result = await gw.recover_waiting_command(task=_make_task(), now=NOW)
    assert result["state"] == "failed"
    assert result["legacy_status"] == "ERROR"


@pytest.mark.asyncio
async def test_recover_waiting_command_pending_returns_waiting():
    cmd_repo = _FakeCommandRepo(legacy_row=_PENDING_ROW)
    gw = _make_gw(command_repo=cmd_repo)
    result = await gw.recover_waiting_command(task=_make_task(), now=NOW)
    assert result["state"] == "waiting_command"
    assert result["legacy_status"] == "PENDING"


# ── greenhouse_uid not found ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_fails_if_no_greenhouse_uid():
    cmd_repo = _FakeCommandRepo()

    async def _no_gh(**_kw):
        return None

    cmd_repo.resolve_greenhouse_uid = _no_gh
    gw = _make_gw(command_repo=cmd_repo)
    with pytest.raises(TaskExecutionError) as exc_info:
        await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)
    assert exc_info.value.code == "command_send_failed"


# ── legacy_command_id not found ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_fails_if_legacy_cmd_id_not_found():
    cmd_repo = _FakeCommandRepo()

    async def _none(**_kw):
        return None

    cmd_repo.resolve_legacy_command_id = _none
    gw = _make_gw(command_repo=cmd_repo)
    with pytest.raises(TaskExecutionError) as exc_info:
        await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)
    assert exc_info.value.code == "command_send_failed"


@pytest.mark.asyncio
async def test_run_batch_uses_exponential_backoff_while_command_is_non_terminal(
    monkeypatch: pytest.MonkeyPatch,
):
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(sequential_command_gateway_module.asyncio, "sleep", fake_sleep)
    command_repo = _SequencedLegacyCommandRepo(
        legacy_rows=[
            _PENDING_ROW,
            _PENDING_ROW,
            _PENDING_ROW,
            _DONE_ROW,
        ]
    )
    gw = _make_gw(command_repo=command_repo, poll_interval=0.1)

    result = await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)

    assert result["success"] is True
    assert sleep_calls == pytest.approx([0.1, 0.15, 0.225, 0.3375])


@pytest.mark.asyncio
async def test_run_batch_records_roundtrip_latency_and_poll_iterations():
    labels = {"channel": "pump_main", "terminal_status": "DONE"}
    before_roundtrip_count = REGISTRY.get_sample_value("ae3_command_roundtrip_duration_seconds_count", labels) or 0.0
    before_roundtrip_sum = REGISTRY.get_sample_value("ae3_command_roundtrip_duration_seconds_sum", labels) or 0.0
    before_poll_iterations = COMMAND_POLL_ITERATIONS.labels(**labels)._value.get()

    gw = _make_gw(command_repo=_SequencedLegacyCommandRepo(legacy_rows=[_PENDING_ROW, _DONE_ROW]), poll_interval=0.001)

    result = await gw.run_batch(task=_make_task(), commands=[_planned()], now=NOW)

    assert result["success"] is True
    assert (REGISTRY.get_sample_value("ae3_command_roundtrip_duration_seconds_count", labels) or 0.0) == (
        before_roundtrip_count + 1.0
    )
    assert (REGISTRY.get_sample_value("ae3_command_roundtrip_duration_seconds_sum", labels) or 0.0) > before_roundtrip_sum
    assert COMMAND_POLL_ITERATIONS.labels(**labels)._value.get() == before_poll_iterations + 2.0


@pytest.mark.asyncio
async def test_run_batch_reconciles_terminal_status_before_stage_deadline_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    current_times = iter([
        NOW,
        NOW.replace(second=NOW.second + 2),
    ])

    monkeypatch.setattr(sequential_command_gateway_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        sequential_command_gateway_module,
        "_utcnow",
        lambda: next(current_times),
    )

    command_repo = _SequencedLegacyCommandRepo(
        legacy_rows=[
            _PENDING_ROW,
            _DONE_ROW,
        ]
    )
    task = _make_task()
    task.workflow.stage_deadline_at = NOW.replace(second=NOW.second + 1)
    gw = _make_gw(command_repo=command_repo, poll_interval=0.1)

    result = await gw.run_batch(task=task, commands=[_planned(channel="pump_acid")], now=NOW)

    assert result["success"] is True
    assert sleep_calls == pytest.approx([0.1, 0.15])


@pytest.mark.asyncio
async def test_run_batch_fails_closed_when_waiting_command_exceeds_stage_deadline(
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_sleep(_delay: float) -> None:
        return None

    captured_events: list[dict[str, object]] = []

    async def fake_create_zone_event(zone_id: int, event_type: str, details: dict[str, object]) -> None:
        captured_events.append({"zone_id": zone_id, "event_type": event_type, "details": details})

    current_times = iter([
        NOW.replace(second=NOW.second + 2),
        NOW.replace(second=NOW.second + 4),
        NOW.replace(second=NOW.second + 6),
    ])

    monkeypatch.setattr(sequential_command_gateway_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        sequential_command_gateway_module,
        "_utcnow",
        lambda: next(current_times),
    )
    monkeypatch.setattr(sequential_command_gateway_module, "create_zone_event", fake_create_zone_event)

    command_repo = _SequencedLegacyCommandRepo(
        legacy_rows=[
            _PENDING_ROW,
            _PENDING_ROW,
            _DONE_ROW,
        ]
    )
    task = _make_task()
    task.current_stage = "prepare_recirculation_check"
    task.workflow.workflow_phase = "tank_recirc"
    task.workflow.corr_step = "corr_dose_ph"
    task.workflow.stage_deadline_at = NOW.replace(second=NOW.second + 1)
    gw = _make_gw(command_repo=command_repo, poll_interval=0.1)

    result = await gw.run_batch(task=task, commands=[_planned(channel="pump_acid")], now=NOW)

    assert result["success"] is False
    assert result["error_code"] == "ae3_command_poll_deadline_exceeded"
    assert len(captured_events) == 1
    assert captured_events[0]["zone_id"] == 1
    assert captured_events[0]["event_type"] == "AE_COMMAND_POLL_DEADLINE_EXCEEDED"
    details = captured_events[0]["details"]
    assert details["stage"] == "prepare_recirculation_check"
    assert details["workflow_phase"] == "tank_recirc"
    assert details["corr_step"] == "corr_dose_ph"
    assert details["channel"] == "pump_acid"
    assert details["stage_deadline_at"] == task.workflow.stage_deadline_at.isoformat()


@pytest.mark.asyncio
async def test_run_batch_publish_only_skips_waiting_command_tracking():
    command_repo = _FakeCommandRepo(legacy_row=_PENDING_ROW)
    task_repo = _FakeTaskRepo()

    async def _boom(**_kwargs):
        raise AssertionError("mark_waiting_command must not be called for publish-only batch")

    task_repo.mark_waiting_command = _boom
    gw = _make_gw(command_repo=command_repo, task_repo=task_repo)

    result = await gw.run_batch(
        task=_make_task(),
        commands=[_planned(channel="valve_clean_fill")],
        now=NOW,
        track_task_state=False,
    )

    assert result["success"] is True
    assert result["commands_total"] == 1
    assert result["command_statuses"][0]["legacy_cmd_id"] == "hl-ae3-t1-z1-s1"
    assert result["command_statuses"][0]["terminal_status"] is None
    assert len(command_repo.publish_accepted_calls) == 1
    assert command_repo.publish_failed_calls == []
