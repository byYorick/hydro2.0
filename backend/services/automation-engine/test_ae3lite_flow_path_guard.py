"""Тесты FlowPathGuard и manual_hold (PR7)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ae3_preflight_helpers import patch_fetch_zone_nodes_diagnostics
from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.flow_path_guard import (
    MANUAL_HOLD_STAGE,
    FlowStopOutcome,
    decode_manual_hold_return_stage,
    emit_correction_interrupted_hardware_risk,
    ensure_flow_stopped,
    handle_control_mode_flow_path_interrupt,
    should_interrupt_flow_for_control_mode,
)
from ae3lite.application.handlers.manual_hold import ManualHoldHandler
from ae3lite.application.handlers.prepare_recirc_window import PrepareRecircWindowHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.entities.workflow_state import WorkflowState
from ae3lite.domain.errors import TaskExecutionError

NOW = datetime(2026, 7, 6, 8, 0, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(hours=1)


@pytest.fixture(autouse=True)
def _ae3_online_zone_nodes_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_fetch_zone_nodes_diagnostics(monkeypatch)


@pytest.fixture(autouse=True)
def _noop_zone_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ae3lite.application.handlers.flow_path_guard.create_zone_event",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "ae3lite.application.handlers.flow_path_guard.send_biz_alert",
        AsyncMock(return_value=None),
    )


def test_should_interrupt_flow_for_control_mode_defaults() -> None:
    runtime = SimpleNamespace(semi_allows_active_flow=False)
    assert should_interrupt_flow_for_control_mode(control_mode="manual", runtime=runtime) is True
    assert should_interrupt_flow_for_control_mode(control_mode="semi", runtime=runtime) is True
    assert should_interrupt_flow_for_control_mode(control_mode="auto", runtime=runtime) is False

    runtime_allow = SimpleNamespace(semi_allows_active_flow=True)
    assert should_interrupt_flow_for_control_mode(control_mode="semi", runtime=runtime_allow) is False


def test_decode_manual_hold_return_stage() -> None:
    assert decode_manual_hold_return_stage("__mh_return:solution_fill_check") == "solution_fill_check"
    assert decode_manual_hold_return_stage("solution_fill_stop") is None


def test_solution_drain_check_is_flow_path_stage() -> None:
    from ae3lite.application.handlers.flow_path_guard import is_flow_path_check_stage

    assert is_flow_path_check_stage("solution_drain_check") is True


class _HandlerStub:
    def __init__(self, *, probe_raises: bool = False, batch_raises: bool = False) -> None:
        self._probe_raises = probe_raises
        self._batch_raises = batch_raises
        self.batch_calls = 0
        self.probe_calls = 0

    def _require_runtime_plan(self, *, plan: Any) -> Any:
        return plan.runtime

    async def _run_command_batch_checked(self, **_: Any) -> dict[str, Any]:
        self.batch_calls += 1
        if self._batch_raises:
            raise TaskExecutionError("command_timeout", "stop timed out")
        return {"success": True, "task": None}

    async def _probe_irr_state(self, **_: Any) -> None:
        self.probe_calls += 1
        if self._probe_raises:
            raise TaskExecutionError("irr_state_mismatch", "pump still on")


def _plan_with_stop_plans() -> SimpleNamespace:
    return SimpleNamespace(
        runtime=make_runtime_plan(level_poll_interval_sec=10),
        named_plans={
            "solution_fill_stop": ("stop_cmd",),
            "sensor_mode_deactivate": ("deact_cmd",),
            "irr_state_probe": ("probe_cmd",),
        },
    )


@pytest.mark.asyncio
async def test_ensure_flow_stopped_confirmed_after_probe() -> None:
    handler = _HandlerStub()
    task = SimpleNamespace(id=1, zone_id=2, current_stage="solution_fill_check")
    outcome = await ensure_flow_stopped(
        handler,
        task=task,
        plan=_plan_with_stop_plans(),
        now=NOW,
        stage="solution_fill_check",
        reason="test",
    )
    assert outcome.confirmed is True
    assert handler.batch_calls == 1
    assert handler.probe_calls == 1


@pytest.mark.asyncio
async def test_ensure_flow_stopped_fails_on_command_timeout() -> None:
    handler = _HandlerStub(batch_raises=True)
    task = SimpleNamespace(id=1, zone_id=2, current_stage="solution_fill_check", workflow=SimpleNamespace())
    outcome = await ensure_flow_stopped(
        handler,
        task=task,
        plan=_plan_with_stop_plans(),
        now=NOW,
        stage="solution_fill_check",
        reason="test",
    )
    assert outcome.confirmed is False
    assert outcome.error_code == "command_timeout"


@pytest.mark.asyncio
async def test_ensure_flow_stopped_emits_event_and_alert_on_command_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_mock = AsyncMock(return_value=None)
    alert_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "ae3lite.application.handlers.flow_path_guard.create_zone_event",
        event_mock,
    )
    monkeypatch.setattr(
        "ae3lite.application.handlers.flow_path_guard.send_biz_alert",
        alert_mock,
    )
    handler = _HandlerStub(batch_raises=True)
    task = SimpleNamespace(id=1, zone_id=2, current_stage="solution_fill_check", workflow=SimpleNamespace())
    await ensure_flow_stopped(
        handler,
        task=task,
        plan=_plan_with_stop_plans(),
        now=NOW,
        stage="solution_fill_check",
        reason="test_timeout",
    )
    event_mock.assert_awaited_once()
    assert event_mock.await_args.args[1] == "FLOW_STOP_FAILED_HARDWARE_MAY_BE_ACTIVE"
    alert_mock.assert_awaited_once()
    assert alert_mock.await_args.kwargs["code"] == "biz_flow_stop_failed_hardware_may_be_active"
    assert alert_mock.await_args.kwargs["severity"] == "critical"


def test_encode_decode_manual_hold_operator_step() -> None:
    from ae3lite.application.handlers.flow_path_guard import encode_manual_hold_operator_step

    encoded = encode_manual_hold_operator_step(
        return_stage="solution_fill_check",
        manual_step="solution_fill_stop",
    )
    assert encoded == "__mh_step:solution_fill_check:solution_fill_stop"
    assert decode_manual_hold_return_stage(encoded) == "solution_fill_check"
    from ae3lite.application.handlers.flow_path_guard import decode_manual_hold_operator_step

    assert decode_manual_hold_operator_step(encoded) == "solution_fill_stop"


@pytest.mark.asyncio
async def test_handle_control_mode_interrupt_transitions_to_manual_hold() -> None:
    handler = _HandlerStub()
    task = SimpleNamespace(
        id=5,
        zone_id=9,
        current_stage="solution_fill_check",
        workflow=SimpleNamespace(control_mode="manual"),
    )
    outcome = await handle_control_mode_flow_path_interrupt(
        handler,
        task=task,
        plan=_plan_with_stop_plans(),
        now=NOW,
        control_mode="manual",
    )
    assert isinstance(outcome, StageOutcome)
    assert outcome.kind == "transition"
    assert outcome.next_stage == MANUAL_HOLD_STAGE
    assert outcome.flow_hold_return_stage == "solution_fill_check"


@pytest.mark.asyncio
async def test_handle_control_mode_interrupt_fails_when_stop_unconfirmed() -> None:
    handler = _HandlerStub(probe_raises=True)
    task = SimpleNamespace(
        id=5,
        zone_id=9,
        current_stage="solution_fill_check",
        workflow=SimpleNamespace(control_mode="manual"),
    )
    outcome = await handle_control_mode_flow_path_interrupt(
        handler,
        task=task,
        plan=_plan_with_stop_plans(),
        now=NOW,
        control_mode="manual",
    )
    assert outcome is not None
    assert outcome.kind == "fail"
    assert outcome.error_code == "ae3_flow_stop_unconfirmed"


def _make_task(*, control_mode: str = "manual", pending_manual_step: str | None = None) -> AutomationTask:
    return AutomationTask.from_row(
        {
            "id": 11,
            "zone_id": 22,
            "task_type": "cycle_start",
            "status": "running",
            "idempotency_key": "mh",
            "scheduled_for": NOW,
            "due_at": NOW,
            "claimed_by": "w",
            "claimed_at": NOW,
            "error_code": None,
            "error_message": None,
            "created_at": NOW,
            "updated_at": NOW,
            "completed_at": None,
            "topology": "two_tank",
            "intent_source": None,
            "intent_trigger": None,
            "intent_id": None,
            "intent_meta": {},
            "current_stage": "manual_hold",
            "workflow_phase": "tank_filling",
            "stage_deadline_at": FUTURE,
            "stage_retry_count": 0,
            "stage_entered_at": NOW,
            "clean_fill_cycle": 1,
            "control_mode_snapshot": control_mode,
            "pending_manual_step": pending_manual_step,
            "corr_step": None,
        }
    )


@pytest.mark.asyncio
async def test_manual_hold_returns_to_saved_stage_when_auto() -> None:
    handler = ManualHoldHandler(runtime_monitor=SimpleNamespace(), command_gateway=SimpleNamespace())
    outcome = await handler.run(
        task=_make_task(
            control_mode="auto",
            pending_manual_step="__mh_return:solution_fill_check",
        ),
        plan=SimpleNamespace(runtime=make_runtime_plan(level_poll_interval_sec=10)),
        stage_def=None,
        now=NOW,
    )
    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_check"


@pytest.mark.asyncio
async def test_manual_hold_returns_to_saved_stage_on_operator_step() -> None:
    handler = ManualHoldHandler(runtime_monitor=SimpleNamespace(), command_gateway=SimpleNamespace())
    outcome = await handler.run(
        task=_make_task(
            control_mode="manual",
            pending_manual_step="__mh_step:solution_fill_check:solution_fill_stop",
        ),
        plan=SimpleNamespace(runtime=make_runtime_plan(level_poll_interval_sec=10)),
        stage_def=None,
        now=NOW,
    )
    assert outcome.kind == "transition"
    assert outcome.next_stage == "solution_fill_check"


@pytest.mark.asyncio
async def test_manual_hold_polls_while_manual() -> None:
    handler = ManualHoldHandler(runtime_monitor=SimpleNamespace(), command_gateway=SimpleNamespace())
    outcome = await handler.run(
        task=_make_task(
            control_mode="manual",
            pending_manual_step="__mh_return:solution_fill_check",
        ),
        plan=SimpleNamespace(runtime=make_runtime_plan(level_poll_interval_sec=10)),
        stage_def=None,
        now=NOW,
    )
    assert outcome.kind == "poll"
    assert outcome.due_delay_sec == 10


@pytest.mark.asyncio
async def test_prepare_recirc_window_fails_when_stop_unconfirmed() -> None:
    handler = PrepareRecircWindowHandler(
        runtime_monitor=SimpleNamespace(),
        command_gateway=SimpleNamespace(),
    )

    async def _fail_stop(**_: Any) -> FlowStopOutcome:
        return FlowStopOutcome(
            confirmed=False,
            error_code="ae3_flow_stop_unconfirmed",
            error_message="probe mismatch",
        )

    handler._ensure_flow_path_stopped = _fail_stop  # type: ignore[method-assign]
    handler._run_commands = AsyncMock(side_effect=AssertionError("must not restart window"))  # type: ignore[method-assign]

    task = SimpleNamespace(
        id=3,
        zone_id=4,
        current_stage="prepare_recirculation_window_exhausted",
        workflow=SimpleNamespace(stage_retry_count=0),
    )
    plan = SimpleNamespace(
        runtime=make_runtime_plan(
            level_poll_interval_sec=10,
            correction={"prepare_recirculation_max_attempts": 3},
        ),
        named_plans=_plan_with_stop_plans().named_plans,
    )
    outcome = await handler.run(
        task=task,
        plan=plan,
        stage_def=None,
        now=NOW,
    )
    assert outcome.kind == "fail"
    assert outcome.error_code == "ae3_flow_stop_unconfirmed"


@pytest.mark.asyncio
async def test_emit_correction_interrupted_hardware_risk_on_dose_step() -> None:
    correction = SimpleNamespace(corr_step="corr_dose_ec")
    task = SimpleNamespace(
        id=7,
        zone_id=8,
        current_stage="solution_fill_check",
        correction=correction,
        workflow=SimpleNamespace(),
    )
    await emit_correction_interrupted_hardware_risk(task=task, now=NOW)
    # no exception — event/alert mocked in fixture
