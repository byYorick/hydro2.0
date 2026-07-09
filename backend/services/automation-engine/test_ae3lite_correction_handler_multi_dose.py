from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.handlers.correction import CorrectionHandler
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError


class _GatewayStub:
    def __init__(self) -> None:
        self.batches: list[tuple] = []
        self._fail_on_call: int | None = None
        self._call_count = 0

    def fail_on_call(self, n: int) -> None:
        self._fail_on_call = n

    async def run_batch(self, **kwargs):
        self._call_count += 1
        self.batches.append(tuple(kwargs.get("commands") or ()))
        if self._fail_on_call is not None and self._call_count == self._fail_on_call:
            return {
                "success": False,
                "error_code": "hw_error",
                "error_message": "device offline",
                "command_statuses": [],
                "task": kwargs.get("task"),
            }
        return {"success": True, "command_statuses": [], "task": kwargs.get("task")}


def _make_seq_corr(*, seq: list[dict], seq_index: int = 0) -> CorrectionState:
    return CorrectionState(
        corr_step="corr_dose_ec",
        attempt=0,
        max_attempts=5,
        ec_attempt=0,
        ec_max_attempts=5,
        ph_attempt=0,
        ph_max_attempts=5,
        activated_here=False,
        stabilization_sec=1,
        return_stage_success="irrigation_check",
        return_stage_fail="irrigation_check",
        outcome_success=None,
        needs_ec=True,
        ec_node_uid="nd-ca",
        ec_channel="pump_b",
        ec_duration_ms=600,
        needs_ph_up=False,
        needs_ph_down=False,
        ph_node_uid=None,
        ph_channel=None,
        ph_duration_ms=None,
        wait_until=None,
        ec_component="multi_sequential",
        ec_amount_ml=6.0,
        ec_dose_sequence_json=json.dumps(seq),
        ec_current_seq_index=seq_index,
    )


@pytest.mark.asyncio
async def test_corr_dose_ec_dispatches_sequence_ca_mg_micro(monkeypatch) -> None:
    gateway = _GatewayStub()
    handler = CorrectionHandler(runtime_monitor=object(), command_gateway=gateway, pid_state_repository=None)

    # avoid event logging side-effects
    async def _noop_async(**_kwargs):
        return None

    async def _identity_task(**kwargs):
        return kwargs["task"]

    monkeypatch.setattr(handler, "_log_correction_event", _noop_async)
    monkeypatch.setattr(handler, "_persist_pid_state_updates", _noop_async)
    monkeypatch.setattr(handler, "_ensure_command_targets_online", _noop_async)
    monkeypatch.setattr(handler, "_ensure_sensor_mode_active_for_dosing", _identity_task)
    monkeypatch.setattr(handler, "_interrupt_for_control_mode_dosing", _noop_async)
    monkeypatch.setattr(handler, "_process_cfg_for_task", lambda **_kwargs: {"ec_gain_per_ml": 0.1})
    monkeypatch.setattr(handler, "_correction_config", lambda **_kwargs: {"stabilization_sec": 1})
    monkeypatch.setattr(handler, "_observation_config", lambda **_kwargs: {"hold_window_sec": 1})

    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    seq = [
        {"component": "calcium", "node_uid": "nd-ca", "channel": "pump_b", "amount_ml": 1.0, "duration_ms": 100},
        {"component": "magnesium", "node_uid": "nd-mg", "channel": "pump_c", "amount_ml": 2.0, "duration_ms": 200},
        {"component": "micro", "node_uid": "nd-mi", "channel": "pump_d", "amount_ml": 3.0, "duration_ms": 300},
    ]
    corr = _make_seq_corr(seq=seq)
    task = SimpleNamespace(
        id=1,
        zone_id=7,
        topology="two_tank",
        current_stage="irrigation_check",
        workflow=SimpleNamespace(workflow_phase="irrigating", control_mode="auto"),
    )
    plan = SimpleNamespace(runtime=make_runtime_plan(pid_state={}, target_ec=1.5))

    out1 = await handler._run_dose_ec(task=task, plan=plan, corr=corr, now=now)
    assert out1.kind == "enter_correction"
    assert out1.correction.ec_current_seq_index == 1
    assert len(gateway.batches[-1]) == 1
    assert gateway.batches[-1][0].node_uid == "nd-ca"

    out2 = await handler._run_dose_ec(task=task, plan=plan, corr=out1.correction, now=now)
    assert out2.kind == "enter_correction"
    assert out2.correction.ec_current_seq_index == 2
    assert len(gateway.batches[-1]) == 1
    assert gateway.batches[-1][0].node_uid == "nd-mg"

    out3 = await handler._run_dose_ec(task=task, plan=plan, corr=out2.correction, now=now)
    assert out3.kind == "enter_correction"
    assert out3.correction.corr_step == "corr_wait_ec"
    assert out3.correction.ec_current_seq_index == 3
    assert len(gateway.batches[-1]) == 1
    assert gateway.batches[-1][0].node_uid == "nd-mi"


@pytest.mark.asyncio
async def test_corr_dose_ec_partial_failure_emits_event_and_fails_window(monkeypatch) -> None:
    """§6.2 MVP: prior success + step N fail → EC_BATCH_PARTIAL_FAILURE + fail window."""
    gateway = _GatewayStub()
    gateway.fail_on_call(2)  # fail magnesium after calcium DONE
    handler = CorrectionHandler(runtime_monitor=object(), command_gateway=gateway, pid_state_repository=None)

    events: list[tuple[str, dict]] = []

    async def _capture_event(**kwargs):
        events.append((str(kwargs.get("event_type")), dict(kwargs.get("payload") or {})))

    async def _noop_async(**_kwargs):
        return None

    async def _identity_task(**kwargs):
        return kwargs["task"]

    monkeypatch.setattr(handler, "_log_correction_event", _capture_event)
    monkeypatch.setattr(handler, "_persist_pid_state_updates", _noop_async)
    monkeypatch.setattr(handler, "_ensure_command_targets_online", _noop_async)
    monkeypatch.setattr(handler, "_ensure_sensor_mode_active_for_dosing", _identity_task)
    monkeypatch.setattr(handler, "_interrupt_for_control_mode_dosing", _noop_async)
    monkeypatch.setattr(handler, "_process_cfg_for_task", lambda **_kwargs: {"ec_gain_per_ml": 0.1})
    monkeypatch.setattr(handler, "_correction_config", lambda **_kwargs: {"stabilization_sec": 1})
    monkeypatch.setattr(handler, "_observation_config", lambda **_kwargs: {"hold_window_sec": 1})

    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    seq = [
        {"component": "calcium", "node_uid": "nd-ca", "channel": "pump_b", "amount_ml": 1.0, "duration_ms": 100},
        {"component": "magnesium", "node_uid": "nd-mg", "channel": "pump_c", "amount_ml": 2.0, "duration_ms": 200},
        {"component": "micro", "node_uid": "nd-mi", "channel": "pump_d", "amount_ml": 3.0, "duration_ms": 300},
    ]
    corr = _make_seq_corr(seq=seq)
    task = SimpleNamespace(
        id=1,
        zone_id=7,
        topology="two_tank",
        current_stage="irrigation_check",
        workflow=SimpleNamespace(workflow_phase="irrigating", control_mode="auto"),
    )
    plan = SimpleNamespace(runtime=make_runtime_plan(pid_state={}, target_ec=1.5))

    out1 = await handler._run_dose_ec(task=task, plan=plan, corr=corr, now=now)
    assert out1.correction.ec_current_seq_index == 1
    assert gateway.batches[-1][0].node_uid == "nd-ca"

    out2 = await handler._run_dose_ec(task=task, plan=plan, corr=out1.correction, now=now)
    assert out2.kind == "exit_correction"
    assert out2.correction is not None
    assert out2.correction.outcome_success is False
    assert out2.correction.ec_current_seq_index == 1
    assert gateway.batches[-1][0].node_uid == "nd-mg"

    partial_events = [e for e in events if e[0] == "EC_BATCH_PARTIAL_FAILURE"]
    assert len(partial_events) == 1
    payload = partial_events[0][1]
    assert payload["status"] == "degraded"
    assert payload["failed_component"] == "magnesium"
    assert payload["successful_components"] == ["calcium"]
    assert payload["remaining_components"] == ["micro"]
    assert payload["mode"] == "multi_sequential"
    assert payload["error_code"] == "hw_error"


@pytest.mark.asyncio
async def test_corr_dose_ec_first_component_failure_raises(monkeypatch) -> None:
    """First-step failure has no prior success → ordinary TaskExecutionError."""
    gateway = _GatewayStub()
    gateway.fail_on_call(1)
    handler = CorrectionHandler(runtime_monitor=object(), command_gateway=gateway, pid_state_repository=None)

    events: list[str] = []

    async def _capture_event(**kwargs):
        events.append(str(kwargs.get("event_type")))

    async def _noop_async(**_kwargs):
        return None

    async def _identity_task(**kwargs):
        return kwargs["task"]

    monkeypatch.setattr(handler, "_log_correction_event", _capture_event)
    monkeypatch.setattr(handler, "_persist_pid_state_updates", _noop_async)
    monkeypatch.setattr(handler, "_ensure_command_targets_online", _noop_async)
    monkeypatch.setattr(handler, "_ensure_sensor_mode_active_for_dosing", _identity_task)
    monkeypatch.setattr(handler, "_interrupt_for_control_mode_dosing", _noop_async)
    monkeypatch.setattr(handler, "_process_cfg_for_task", lambda **_kwargs: {"ec_gain_per_ml": 0.1})
    monkeypatch.setattr(handler, "_correction_config", lambda **_kwargs: {"stabilization_sec": 1})
    monkeypatch.setattr(handler, "_observation_config", lambda **_kwargs: {"hold_window_sec": 1})

    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    seq = [
        {"component": "calcium", "node_uid": "nd-ca", "channel": "pump_b", "amount_ml": 1.0, "duration_ms": 100},
        {"component": "magnesium", "node_uid": "nd-mg", "channel": "pump_c", "amount_ml": 2.0, "duration_ms": 200},
    ]
    corr = _make_seq_corr(seq=seq)
    task = SimpleNamespace(
        id=1,
        zone_id=7,
        topology="two_tank",
        current_stage="irrigation_check",
        workflow=SimpleNamespace(workflow_phase="irrigating", control_mode="auto"),
    )
    plan = SimpleNamespace(runtime=make_runtime_plan(pid_state={}, target_ec=1.5))

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler._run_dose_ec(task=task, plan=plan, corr=corr, now=now)
    assert exc_info.value.code == "hw_error"
    assert "EC_BATCH_PARTIAL_FAILURE" not in events
