"""Unit tests: dilute-on-overshoot helpers + CorrectionHandler pulse/settle path."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ae3lite.application.handlers.correction import CorrectionHandler, _MeasurementSnapshot
from ae3lite.application.services.correction_pipeline import should_dilute
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError
from ae3lite.domain.services.nutrient_pipeline import ec_overshoot_requires_dilute


NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)


def _corr(**kwargs) -> CorrectionState:
    base = CorrectionState.build_default(
        corr_step="corr_check",
        max_attempts=20,
        ec_max_attempts=20,
        ph_max_attempts=20,
        activated_here=False,
        stabilization_sec=10,
        return_stage_success="prepare_recirculation_stop_to_ready",
        return_stage_fail="prepare_recirculation_window_exhausted",
    )
    return replace(base, **kwargs)


def test_overshoot_threshold() -> None:
    assert ec_overshoot_requires_dilute(current_ec=1.2, t_step=1.0, overshoot_pct=15) is True
    assert ec_overshoot_requires_dilute(current_ec=1.1, t_step=1.0, overshoot_pct=15) is False


def test_seed_155_not_dilute_when_t_ca_collapsed_to_t_full() -> None:
    """Regression: fill calcium-only ratios → T_ca==T_full≈2.33; seed 1.55 is under, not overshoot."""
    t_full = 2.33
    assert ec_overshoot_requires_dilute(current_ec=1.55, t_step=t_full, overshoot_pct=15) is False
    assert ec_overshoot_requires_dilute(current_ec=2.90, t_step=t_full, overshoot_pct=15) is True
    # Correct full ratios → T_ca≈1.01; both seeds would dilute, but 2.90 stays robust either way.
    t_ca = 0.59 + 1.74 * 0.30  # ≈1.11
    assert ec_overshoot_requires_dilute(current_ec=2.90, t_step=t_ca, overshoot_pct=15) is True


def test_full_ec_component_ratios_prefers_tank_recirc() -> None:
    handler = CorrectionHandler(runtime_monitor=SimpleNamespace(), command_gateway=SimpleNamespace())
    runtime = SimpleNamespace(
        ec_component_ratios={"calcium": 1.0},  # collapsed fill-style map on runtime
        correction_by_phase={
            "tank_recirc": SimpleNamespace(
                ec_component_ratios={"calcium": 30, "magnesium": 20, "npk": 40, "micro": 10}
            ),
            "solution_fill": SimpleNamespace(ec_component_ratios={"calcium": 30}),
        },
    )
    ratios = handler._full_ec_component_ratios(
        runtime=runtime,
        correction_cfg={"ec_component_ratios": {"calcium": 1.0}},
    )
    assert ratios == {"calcium": 30, "magnesium": 20, "npk": 40, "micro": 10}


def test_should_dilute_only_on_recirc_ec_step() -> None:
    corr = _corr(pipeline_phase="recirc_ca", active_component="calcium", dilute_attempts=0)
    runtime = SimpleNamespace(
        recirc=SimpleNamespace(
            ec_overshoot_dilute_pct=15,
            dilute_max_attempts=3,
        )
    )
    assert should_dilute(
        corr=corr,
        runtime=runtime,
        current_ec=2.0,
        t_step=1.0,
        current_stage="prepare_recirculation_check",
    )
    # pH gate — no dilute
    corr_ph = replace(corr, pipeline_phase="recirc_ph_after_ca", active_component=None)
    assert not should_dilute(
        corr=corr_ph,
        runtime=runtime,
        current_ec=2.0,
        t_step=1.0,
        current_stage="prepare_recirculation_check",
    )
    # max attempts
    corr_max = replace(corr, dilute_attempts=3)
    assert not should_dilute(
        corr=corr_max,
        runtime=runtime,
        current_ec=2.0,
        t_step=1.0,
        current_stage="prepare_recirculation_check",
    )


def _dilute_cmds(*, state: bool) -> tuple[PlannedCommand, ...]:
    return (
        PlannedCommand(
            step_no=1,
            node_uid="irr-node",
            channel="valve_clean_supply",
            payload={"cmd": "set_relay", "params": {"state": state}},
        ),
    )


def _make_dilute_handler(
    *,
    pid_repo: Any | None = None,
) -> tuple[CorrectionHandler, Any]:
    pid = pid_repo or SimpleNamespace(
        upsert_states=AsyncMock(),
        reset_no_effect_counts=AsyncMock(),
        clear_feedforward_bias=AsyncMock(),
    )
    gateway = SimpleNamespace(run_batch=AsyncMock(return_value={"success": True, "command_statuses": []}))
    handler = CorrectionHandler(
        runtime_monitor=SimpleNamespace(),
        command_gateway=gateway,
        pid_state_repository=pid,
    )
    handler._log_correction_event = AsyncMock()  # type: ignore[method-assign]
    handler._persist_pid_state_updates = AsyncMock()  # type: ignore[method-assign]
    handler._check_no_effect_block = lambda **_kw: None  # type: ignore[method-assign]
    handler._should_log_limit_policy = lambda **_kw: False  # type: ignore[method-assign]
    handler._irrigation_ready_short_circuit = lambda **_kw: False  # type: ignore[method-assign]
    handler._interrupt_for_control_mode_dosing = AsyncMock(return_value=None)  # type: ignore[method-assign]
    handler._enforce_attempt_caps = lambda **_kw: True  # type: ignore[method-assign]
    handler._resolve_actuators = lambda **_kw: {}  # type: ignore[method-assign]
    return handler, gateway


def _wire_check_runtime(handler: CorrectionHandler, *, t_step: float = 1.0) -> None:
    handler._require_runtime_plan = lambda **_kw: SimpleNamespace(  # type: ignore[method-assign]
        telemetry_max_age_sec=60,
        target_ph=6.0,
        target_ec=t_step,
        target_ec_prepare=t_step,
        target_ph_min=None,
        target_ph_max=None,
        target_ec_min=None,
        target_ec_max=None,
        target_ec_prepare_min=None,
        target_ec_prepare_max=None,
        npk_ec_share=1.0,
        pid_state={},
        solution_fill_timeout_sec=3600,
        prepare_tolerance={"ph_pct": 15.0, "ec_pct": 15.0},
        prepare_tolerance_by_phase={"tank_recirc": {"ph_pct": 15.0, "ec_pct": 15.0}},
        correction={"max_ec_correction_attempts": 20, "max_ph_correction_attempts": 20},
        process_calibrations={},
        day_night_config=None,
        recirc=SimpleNamespace(
            ec_overshoot_dilute_pct=15.0,
            dilute_pulse_sec=4,
            dilute_max_attempts=3,
            dilute_settle_sec=6,
        ),
        solution_max_sensor_labels=["level_solution_max"],
        level_switch_on_threshold=0.5,
        irr_state_wait_timeout_sec=12,
        irr_state_max_age_sec=15,
        prepare_recirculation_correction_slack_sec=0,
    )
    handler._effective_ph_target = lambda **_kw: 6.0  # type: ignore[method-assign]
    handler._effective_ec_target = lambda **_kw: t_step  # type: ignore[method-assign]
    handler._effective_ph_min = lambda **_kw: None  # type: ignore[method-assign]
    handler._effective_ph_max = lambda **_kw: None  # type: ignore[method-assign]
    handler._effective_ec_min = lambda **_kw: None  # type: ignore[method-assign]
    handler._effective_ec_max = lambda **_kw: None  # type: ignore[method-assign]
    handler._prepare_tolerance_for_task = lambda **_kw: {"ph_pct": 15.0, "ec_pct": 15.0}  # type: ignore[method-assign]
    handler._required_prepare_tolerance_pct = (  # type: ignore[method-assign]
        lambda *, tolerance, key: float(tolerance[key])
    )
    handler._correction_config = lambda **_kw: {}  # type: ignore[method-assign]
    handler._process_cfg_for_task = lambda **_kw: {}  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_corr_check_overshoot_enters_dilute_pulse() -> None:
    """EC above T_step*(1+pct) on recirc_ca → RECIRC_DILUTE_STARTED + corr_dilute_pulse."""
    handler, _gateway = _make_dilute_handler()
    _wire_check_runtime(handler, t_step=1.0)
    corr = _corr(
        pipeline_phase="recirc_ca",
        active_component="calcium",
        dilute_attempts=0,
        corr_step="corr_check",
    )
    task = SimpleNamespace(
        zone_id=120,
        id=12,
        current_stage="prepare_recirculation_check",
        workflow=SimpleNamespace(workflow_phase="tank_recirc", stage_deadline_at=None, stage_retry_count=0),
        correction=corr,
        topology="two_tank",
    )
    # 1.20 > 1.0*1.15 → dilute; also outside ±15% tolerance so step not reached
    handler._read_measurements_or_interrupt = AsyncMock(  # type: ignore[method-assign]
        return_value=_MeasurementSnapshot(
            current_ph=6.0,
            current_ec=1.20,
            workflow_ready=False,
            current_stage="prepare_recirculation_check",
        )
    )

    outcome = await handler._run_check(task=task, plan=SimpleNamespace(), corr=corr, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_dilute_pulse"
    assert outcome.correction.dilute_attempts == 1
    events = [c.kwargs.get("event_type") for c in handler._log_correction_event.await_args_list]
    assert "RECIRC_DILUTE_STARTED" in events
    assert "PIPELINE_STEP_CHANGED" not in events


@pytest.mark.asyncio
async def test_corr_check_respects_dilute_max_attempts() -> None:
    """At dilute_max_attempts, overshoot does not re-enter dilute pulse."""
    handler, _gateway = _make_dilute_handler()
    _wire_check_runtime(handler, t_step=1.0)
    # Planner will be asked to dose — stub a simple DosePlan-less path via config error skip:
    # force interrupt hold so we don't need full actuator/planner wiring.
    handler._interrupt_for_control_mode_dosing = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(kind="wait", due_delay_sec=5.0)
    )
    corr = _corr(
        pipeline_phase="recirc_ca",
        active_component="calcium",
        dilute_attempts=3,
        corr_step="corr_check",
        attempt=1,
        max_attempts=20,
    )
    task = SimpleNamespace(
        zone_id=120,
        id=12,
        current_stage="prepare_recirculation_check",
        workflow=SimpleNamespace(workflow_phase="tank_recirc", stage_deadline_at=None, stage_retry_count=0),
        correction=corr,
        topology="two_tank",
    )
    handler._read_measurements_or_interrupt = AsyncMock(  # type: ignore[method-assign]
        return_value=_MeasurementSnapshot(
            current_ph=6.0,
            current_ec=1.20,
            workflow_ready=False,
            current_stage="prepare_recirculation_check",
        )
    )

    outcome = await handler._run_check(task=task, plan=SimpleNamespace(), corr=corr, now=NOW)

    events = [c.kwargs.get("event_type") for c in handler._log_correction_event.await_args_list]
    assert "RECIRC_DILUTE_STARTED" not in events
    assert outcome.kind == "wait"


@pytest.mark.asyncio
async def test_run_dilute_pulse_opens_valve_clean_supply() -> None:
    handler, gateway = _make_dilute_handler()
    _wire_check_runtime(handler, t_step=1.0)
    handler._read_level = AsyncMock(return_value={"is_triggered": False})  # type: ignore[method-assign]
    corr = _corr(
        pipeline_phase="recirc_ca",
        active_component="calcium",
        dilute_attempts=1,
        corr_step="corr_dilute_pulse",
    )
    task = SimpleNamespace(
        zone_id=120,
        id=12,
        current_stage="prepare_recirculation_check",
        workflow=SimpleNamespace(workflow_phase="tank_recirc", stage_deadline_at=None, stage_retry_count=0),
        correction=corr,
        topology="two_tank",
    )
    plan = SimpleNamespace(
        named_plans={
            "recirc_dilute_start": _dilute_cmds(state=True),
            "recirc_dilute_stop": _dilute_cmds(state=False),
        }
    )

    outcome = await handler._run_dilute_pulse(task=task, plan=plan, corr=corr, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_dilute_settle"
    assert outcome.due_delay_sec == 4.0
    gateway.run_batch.assert_awaited()
    batch_cmds = gateway.run_batch.await_args.kwargs["commands"]
    assert len(batch_cmds) == 1
    assert batch_cmds[0].channel == "valve_clean_supply"
    assert batch_cmds[0].payload["params"]["state"] is True


@pytest.mark.asyncio
async def test_run_dilute_pulse_blocked_on_solution_max() -> None:
    handler, gateway = _make_dilute_handler()
    _wire_check_runtime(handler, t_step=1.0)
    handler._read_level = AsyncMock(return_value={"is_triggered": True})  # type: ignore[method-assign]
    corr = _corr(corr_step="corr_dilute_pulse", dilute_attempts=1, pipeline_phase="recirc_ca")
    task = SimpleNamespace(
        zone_id=120,
        id=12,
        current_stage="prepare_recirculation_check",
        workflow=SimpleNamespace(workflow_phase="tank_recirc", stage_deadline_at=None, stage_retry_count=0),
        correction=corr,
        topology="two_tank",
    )
    plan = SimpleNamespace(named_plans={"recirc_dilute_start": _dilute_cmds(state=True)})

    with pytest.raises(TaskExecutionError) as exc:
        await handler._run_dilute_pulse(task=task, plan=plan, corr=corr, now=NOW)

    assert exc.value.code == ErrorCodes.AE3_RECIRC_DILUTE_BLOCKED_SOLUTION_MAX
    events = [c.kwargs.get("event_type") for c in handler._log_correction_event.await_args_list]
    assert "RECIRC_DILUTE_BLOCKED" in events
    gateway.run_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_dilute_settle_resets_pid_and_emits_completed() -> None:
    pid = SimpleNamespace(
        upsert_states=AsyncMock(),
        reset_no_effect_counts=AsyncMock(),
        clear_feedforward_bias=AsyncMock(),
    )
    handler, gateway = _make_dilute_handler(pid_repo=pid)
    _wire_check_runtime(handler, t_step=1.0)
    corr = _corr(
        pipeline_phase="recirc_ca",
        active_component="calcium",
        dilute_attempts=1,
        corr_step="corr_dilute_settle",
    )
    task = SimpleNamespace(
        zone_id=120,
        id=12,
        current_stage="prepare_recirculation_check",
        workflow=SimpleNamespace(workflow_phase="tank_recirc", stage_deadline_at=None, stage_retry_count=0),
        correction=corr,
        topology="two_tank",
    )
    plan = SimpleNamespace(
        named_plans={
            "recirc_dilute_start": _dilute_cmds(state=True),
            "recirc_dilute_stop": _dilute_cmds(state=False),
        }
    )

    outcome = await handler._run_dilute_settle(task=task, plan=plan, corr=corr, now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.due_delay_sec == 6.0
    gateway.run_batch.assert_awaited()
    stop_cmds = gateway.run_batch.await_args.kwargs["commands"]
    assert stop_cmds[0].channel == "valve_clean_supply"
    assert stop_cmds[0].payload["params"]["state"] is False
    pid.reset_no_effect_counts.assert_awaited_once_with(zone_id=120)
    handler._persist_pid_state_updates.assert_awaited()
    events = [c.kwargs.get("event_type") for c in handler._log_correction_event.await_args_list]
    assert "PID_EC_RESET" in events
    assert "RECIRC_DILUTE_COMPLETED" in events
    completed = next(
        c for c in handler._log_correction_event.await_args_list
        if c.kwargs.get("event_type") == "RECIRC_DILUTE_COMPLETED"
    )
    assert completed.kwargs["payload"]["dilute_attempts"] == 1
    pid_reset = next(
        c for c in handler._log_correction_event.await_args_list
        if c.kwargs.get("event_type") == "PID_EC_RESET"
    )
    assert pid_reset.kwargs["payload"]["reason"] == "dilute"
