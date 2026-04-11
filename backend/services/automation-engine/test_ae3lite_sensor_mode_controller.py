"""Unit-тесты для SensorModeController (extracted from CorrectionHandler, B1).

Exercises the controller with fake command_gateway and event_logger so we
can observe dispatched commands and logged events without touching the DB
or a real runtime_monitor.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from ae3lite.application.services.correction_event_logger import CorrectionEventLogger
from ae3lite.application.services.decision_window_reader import DecisionWindowResult
from ae3lite.application.services.sensor_mode_controller import SensorModeController
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError


NOW = datetime(2026, 3, 10, 12, 0, 0)


class _FakeGateway:
    def __init__(self, *, success: bool = True, returned_task: Any = None) -> None:
        self._success = success
        self._returned_task = returned_task
        self.calls: list[dict[str, Any]] = []

    async def run_batch(self, *, task, commands, now, track_task_state: bool = True):
        self.calls.append(
            {
                "task": task,
                "commands": tuple(commands),
                "now": now,
            }
        )
        return {
            "success": self._success,
            "error_code": None if self._success else "hw_error",
            "error_message": None if self._success else "bad",
            "task": self._returned_task or task,
        }


class _FakeEventSink:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, dict]] = []

    async def __call__(self, zone_id: int, event_type: str, payload: Mapping[str, Any]) -> None:
        self.calls.append((zone_id, event_type, dict(payload)))


def _make_controller(
    *,
    gateway: _FakeGateway | None = None,
) -> tuple[SensorModeController, _FakeGateway, _FakeEventSink]:
    gw = gateway or _FakeGateway()
    sink = _FakeEventSink()
    logger = CorrectionEventLogger(
        create_event_fn=sink,
        probe_snapshot_context_fn=lambda *, task: None,
    )
    return SensorModeController(command_gateway=gw, event_logger=logger), gw, sink


def _plan(with_activate: bool = True) -> SimpleNamespace:
    templates = (
        (
            PlannedCommand(
                step_no=1, node_uid="sensor-1", channel="sensor_mode",
                payload={"cmd": "noop", "params": {}},
            ),
        )
        if with_activate
        else ()
    )
    return SimpleNamespace(
        named_plans={
            "sensor_mode_activate": templates,
            "sensor_mode_deactivate": templates,
        }
    )


def _task(current_stage: str = "solution_fill_check", zone_id: int = 447) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        zone_id=zone_id,
        current_stage=current_stage,
        workflow=SimpleNamespace(workflow_phase="tank_filling", stage_entered_at=None),
        topology="two_tank",
    )


def _corr(*, activated_here: bool = False, stabilization_sec: int = 30) -> CorrectionState:
    return CorrectionState(
        corr_step="corr_check",
        attempt=0,
        max_attempts=3,
        ec_attempt=0,
        ec_max_attempts=3,
        ph_attempt=0,
        ph_max_attempts=3,
        activated_here=activated_here,
        stabilization_sec=stabilization_sec,
        return_stage_success="next",
        return_stage_fail="fail",
        outcome_success=None,
        needs_ec=False,
        ec_node_uid=None,
        ec_channel=None,
        ec_duration_ms=None,
        needs_ph_up=False,
        needs_ph_down=False,
        ph_node_uid=None,
        ph_channel=None,
        ph_duration_ms=None,
        wait_until=None,
    )


# ── build_commands ──────────────────────────────────────────────────


def test_build_commands_renders_activate_batch_from_named_plans() -> None:
    ctrl, _, _ = _make_controller()
    commands = ctrl.build_commands(
        plan=_plan(),
        cmd="activate_sensor_mode",
        params={"stabilization_time_sec": 30},
    )
    assert len(commands) == 1
    cmd = commands[0]
    assert cmd.payload["cmd"] == "activate_sensor_mode"
    assert cmd.payload["params"]["stabilization_time_sec"] == 30
    assert cmd.node_uid == "sensor-1"


def test_build_commands_reads_deactivate_from_separate_key() -> None:
    ctrl, _, _ = _make_controller()
    commands = ctrl.build_commands(
        plan=_plan(),
        cmd="deactivate_sensor_mode",
        params={},
    )
    assert commands[0].payload["cmd"] == "deactivate_sensor_mode"


def test_build_commands_returns_empty_when_plan_has_no_templates() -> None:
    ctrl, _, _ = _make_controller()
    commands = ctrl.build_commands(
        plan=SimpleNamespace(named_plans={}),
        cmd="activate_sensor_mode",
        params={},
    )
    assert commands == ()


def test_build_commands_handles_missing_named_plans_attribute() -> None:
    ctrl, _, _ = _make_controller()
    commands = ctrl.build_commands(
        plan=SimpleNamespace(),  # no named_plans attribute
        cmd="activate_sensor_mode",
        params={},
    )
    assert commands == ()


# ── ensure_active_for_dosing ────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_active_for_dosing_dispatches_and_logs() -> None:
    ctrl, gateway, sink = _make_controller()
    task = _task()
    result_task = await ctrl.ensure_active_for_dosing(
        task=task,
        plan=_plan(),
        corr=_corr(stabilization_sec=45),
        now=NOW,
        failed_node_uid="ph-node",
        failed_channel="ph_down_pump",
        retry_cmd="dose",
    )
    assert result_task is task  # gateway returns same task
    assert len(gateway.calls) == 1
    commands = gateway.calls[0]["commands"]
    assert len(commands) == 1
    assert commands[0].payload["params"]["stabilization_time_sec"] == 45

    assert len(sink.calls) == 1
    zone_id, event_type, payload = sink.calls[0]
    assert event_type == "CORRECTION_SENSOR_MODE_REACTIVATED"
    assert payload["reason"] == "pre_dose_reactivation"
    assert payload["failed_node_uid"] == "ph-node"
    assert payload["failed_channel"] == "ph_down_pump"
    assert payload["retry_cmd"] == "dose"
    assert payload["stabilization_sec"] == 45


@pytest.mark.asyncio
async def test_ensure_active_for_dosing_noop_without_templates() -> None:
    ctrl, gateway, sink = _make_controller()
    task = _task()
    result_task = await ctrl.ensure_active_for_dosing(
        task=task,
        plan=_plan(with_activate=False),
        corr=_corr(),
        now=NOW,
        failed_node_uid=None,
        failed_channel=None,
        retry_cmd="dose",
    )
    assert result_task is task
    assert gateway.calls == []
    assert sink.calls == []


@pytest.mark.asyncio
async def test_ensure_active_for_dosing_raises_on_gateway_failure() -> None:
    ctrl, _, _ = _make_controller(gateway=_FakeGateway(success=False))
    with pytest.raises(TaskExecutionError) as excinfo:
        await ctrl.ensure_active_for_dosing(
            task=_task(),
            plan=_plan(),
            corr=_corr(),
            now=NOW,
            failed_node_uid=None,
            failed_channel=None,
            retry_cmd="dose",
        )
    assert excinfo.value.code == "hw_error"


# ── maybe_reactivate_after_empty_window ─────────────────────────────


def _empty_window(*, sample_count: int = 0) -> DecisionWindowResult:
    return DecisionWindowResult(
        ready=False,
        reason="insufficient_samples",
        sample_count=sample_count,
        window_min_samples=3,
        telemetry_period_sec=5,
    )


def _ready_window() -> DecisionWindowResult:
    return DecisionWindowResult(ready=True, value=2.0, sample_count=3, slope=0.01)


@pytest.mark.asyncio
async def test_reactivate_skipped_when_correction_owns_sensors() -> None:
    ctrl, gateway, sink = _make_controller()
    outcome = await ctrl.maybe_reactivate_after_empty_window(
        task=_task(),
        plan=_plan(),
        corr=_corr(activated_here=True),
        now=NOW,
        ph=_empty_window(),
        ec=_empty_window(),
    )
    assert outcome is None
    assert gateway.calls == []
    assert sink.calls == []


@pytest.mark.asyncio
async def test_reactivate_skipped_for_stages_with_persistent_sensors() -> None:
    ctrl, gateway, _ = _make_controller()
    outcome = await ctrl.maybe_reactivate_after_empty_window(
        task=_task(current_stage="irrigation_check"),
        plan=_plan(),
        corr=_corr(activated_here=False),
        now=NOW,
        ph=_empty_window(),
        ec=_empty_window(),
    )
    assert outcome is None
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_reactivate_skipped_when_windows_are_just_unstable() -> None:
    ctrl, gateway, _ = _make_controller()
    unstable = DecisionWindowResult(
        ready=False, reason="unstable", slope=0.5,
    )
    outcome = await ctrl.maybe_reactivate_after_empty_window(
        task=_task(),
        plan=_plan(),
        corr=_corr(),
        now=NOW,
        ph=unstable,
        ec=unstable,
    )
    assert outcome is None
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_reactivate_dispatches_on_empty_ph_window() -> None:
    ctrl, gateway, sink = _make_controller()
    outcome = await ctrl.maybe_reactivate_after_empty_window(
        task=_task(),
        plan=_plan(),
        corr=_corr(stabilization_sec=60),
        now=NOW,
        ph=_empty_window(),
        ec=_ready_window(),
    )
    assert outcome is not None
    assert outcome.kind == "enter_correction"
    assert outcome.correction.corr_step == "corr_wait_stable"
    assert outcome.due_delay_sec == 60
    assert len(gateway.calls) == 1
    assert len(sink.calls) == 1
    assert sink.calls[0][1] == "CORRECTION_SENSOR_MODE_REACTIVATED"


@pytest.mark.asyncio
async def test_reactivate_returns_none_when_plan_has_no_templates() -> None:
    ctrl, gateway, _ = _make_controller()
    outcome = await ctrl.maybe_reactivate_after_empty_window(
        task=_task(),
        plan=_plan(with_activate=False),
        corr=_corr(),
        now=NOW,
        ph=_empty_window(),
        ec=_empty_window(),
    )
    assert outcome is None
    assert gateway.calls == []


# ── stage_keeps_active / window_empty_for_reactivation ─────────────


def test_stage_keeps_active_for_irrigation_check() -> None:
    assert SensorModeController.stage_keeps_active(task=_task(current_stage="irrigation_check")) is True


def test_stage_keeps_active_for_irrigation_recovery_check() -> None:
    assert (
        SensorModeController.stage_keeps_active(
            task=_task(current_stage="irrigation_recovery_check"),
        )
        is True
    )


def test_stage_keeps_active_false_for_solution_fill() -> None:
    assert SensorModeController.stage_keeps_active(task=_task()) is False


def test_window_empty_false_when_ready() -> None:
    assert SensorModeController.window_empty_for_reactivation(metric=_ready_window()) is False


def test_window_empty_false_when_reason_is_unstable() -> None:
    metric = DecisionWindowResult(ready=False, reason="unstable", slope=0.5)
    assert SensorModeController.window_empty_for_reactivation(metric=metric) is False


def test_window_empty_true_when_samples_zero() -> None:
    assert SensorModeController.window_empty_for_reactivation(metric=_empty_window()) is True


def test_window_empty_true_when_sample_count_missing() -> None:
    metric = DecisionWindowResult(
        ready=False,
        reason="insufficient_samples",
        sample_count=None,
        window_min_samples=3,
    )
    assert SensorModeController.window_empty_for_reactivation(metric=metric) is True


def test_window_empty_false_when_some_samples_present() -> None:
    metric = _empty_window(sample_count=1)
    assert SensorModeController.window_empty_for_reactivation(metric=metric) is False
