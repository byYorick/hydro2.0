"""Unit tests: PID pipeline invariants (reset / freeze / keep I / gains)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.application.handlers.correction import CorrectionHandler
from ae3lite.application.services.correction_pipeline import maybe_advance_pipeline, pipeline_dose_flags
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.services.correction_planner import _ec_component_process_gain
from ae3lite.domain.services.nutrient_pipeline import PIPELINE_PHASE_FILL_CA


def _corr(**kwargs) -> CorrectionState:
    base = CorrectionState.build_default(
        corr_step="corr_check",
        max_attempts=20,
        ec_max_attempts=20,
        ph_max_attempts=20,
        activated_here=False,
        stabilization_sec=10,
        return_stage_success="prepare_recirculation_stop_to_ready",
        return_stage_fail="x",
    )
    return replace(base, **kwargs)


def test_ph_gate_freezes_ec_pid() -> None:
    flags = pipeline_dose_flags(_corr(pipeline_phase="recirc_ph_after_ca"))
    assert flags["freeze_ec_pid"] is True
    assert flags["allow_ec"] is False


def test_component_switch_requests_pid_reset() -> None:
    corr = _corr(pipeline_phase="recirc_ca", active_component="calcium")
    next_corr, finished, payload = maybe_advance_pipeline(
        corr=corr,
        current_stage="prepare_recirculation_check",
    )
    assert not finished
    assert next_corr.pipeline_phase == "recirc_ph_after_ca"
    # Ca → pH: no EC component switch reset (pH gate)
    # advance again to Mg
    next2, _, payload2 = maybe_advance_pipeline(
        corr=next_corr,
        current_stage="prepare_recirculation_check",
    )
    assert payload2 is not None
    assert payload2["from_component"] is None or payload2["to_component"] == "magnesium"
    assert payload2["reset_ec_pid"] is True  # None/calcium → magnesium


def test_fill_ca_to_recirc_ca_keeps_integral_flag() -> None:
    """Within same window fill→recirc isn't advanced; when both calcium, reset=False."""
    # Simulate advance from fill would finish; for recirc start at ca after fill,
    # component stays calcium so reset_ec_pid stays false across Ca→ph→… only on switch.
    corr = _corr(pipeline_phase=PIPELINE_PHASE_FILL_CA, active_component="calcium")
    _, finished, payload = maybe_advance_pipeline(
        corr=corr,
        current_stage="solution_fill_check",
    )
    assert finished is True
    assert payload is not None
    assert payload["reason"] == "fill_ca_done"


def test_per_component_gain() -> None:
    process_cfg = {
        "ec_gain_per_ml": 0.1,
        "ec_component_gains": {
            "calcium": {"ec_gain_per_ml": 0.25},
            "npk": {"ec_gain_per_ml": 0.15},
        },
    }
    gain_ca = _ec_component_process_gain(
        component="calcium",
        process_cfg=process_cfg,
        pid_entry={},
        phase_key="tank_recirc",
    )
    gain_npk = _ec_component_process_gain(
        component="npk",
        process_cfg=process_cfg,
        pid_entry={},
        phase_key="tank_recirc",
    )
    assert gain_ca == 0.25
    assert gain_npk == 0.15


def test_per_component_gain_accepts_flat_number() -> None:
    """Legacy UI payload: ec_component_gains.calcium = 0.25 (flat number)."""
    process_cfg = {
        "ec_gain_per_ml": 0.1,
        "ec_component_gains": {"calcium": 0.25, "npk": {"ec_gain_per_ml": 0.15}},
    }
    assert (
        _ec_component_process_gain(
            component="calcium",
            process_cfg=process_cfg,
            pid_entry={},
            phase_key="tank_recirc",
        )
        == 0.25
    )


@pytest.mark.asyncio
async def test_component_switch_resets_no_effect_with_pid() -> None:
    """On mid-pipeline EC component switch, no_effect_count resets with EC PID I/D."""
    now = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)
    pid_repo = SimpleNamespace(
        reset_no_effect_counts=AsyncMock(),
    )
    handler = CorrectionHandler(
        runtime_monitor=SimpleNamespace(),
        command_gateway=SimpleNamespace(),
        pid_state_repository=pid_repo,
    )
    handler._persist_pid_state_updates = AsyncMock()  # type: ignore[method-assign]
    handler._log_correction_event = AsyncMock()  # type: ignore[method-assign]
    handler._check_no_effect_block = lambda **_kw: None  # type: ignore[method-assign]
    handler._should_log_limit_policy = lambda **_kw: False  # type: ignore[method-assign]
    handler._require_runtime_plan = lambda **_kw: SimpleNamespace(  # type: ignore[method-assign]
        telemetry_max_age_sec=60,
        target_ph=6.0,
        target_ec=2.0,
        target_ec_prepare=2.0,
        target_ph_min=None,
        target_ph_max=None,
        target_ec_min=None,
        target_ec_max=None,
        target_ec_prepare_min=None,
        target_ec_prepare_max=None,
        npk_ec_share=1.0,
        pid_state={},
        solution_fill_timeout_sec=3600,
        prepare_tolerance={"ph_pct": 15.0, "ec_pct": 25.0},
        prepare_tolerance_by_phase={"tank_recirc": {"ph_pct": 15.0, "ec_pct": 25.0}},
        correction={"max_ec_correction_attempts": 20, "max_ph_correction_attempts": 20},
        process_calibrations={},
        day_night_config=None,
    )
    handler._irrigation_ready_short_circuit = lambda **_kw: False  # type: ignore[method-assign]
    handler._effective_ph_target = lambda **_kw: 6.0  # type: ignore[method-assign]
    handler._effective_ec_target = lambda **_kw: 2.0  # type: ignore[method-assign]
    handler._effective_ph_min = lambda **_kw: None  # type: ignore[method-assign]
    handler._effective_ph_max = lambda **_kw: None  # type: ignore[method-assign]
    handler._effective_ec_min = lambda **_kw: None  # type: ignore[method-assign]
    handler._effective_ec_max = lambda **_kw: None  # type: ignore[method-assign]
    handler._prepare_tolerance_for_task = lambda **_kw: {"ph_pct": 15.0, "ec_pct": 25.0}  # type: ignore[method-assign]
    handler._required_prepare_tolerance_pct = (  # type: ignore[method-assign]
        lambda *, tolerance, key: float(tolerance[key])
    )
    handler._correction_config = lambda **_kw: {}  # type: ignore[method-assign]
    handler._process_cfg_for_task = lambda **_kw: {}  # type: ignore[method-assign]
    handler._enforce_attempt_caps = lambda **_kw: True  # type: ignore[method-assign]

    from ae3lite.application.handlers.correction import _MeasurementSnapshot

    corr = _corr(pipeline_phase="recirc_ph_after_ca", active_component=None, ec_pid_frozen=True)
    task = SimpleNamespace(
        zone_id=90,
        id=9,
        current_stage="prepare_recirculation_check",
        workflow=SimpleNamespace(workflow_phase="tank_recirc"),
        correction=corr,
        topology="two_tank",
    )
    handler._read_measurements_or_interrupt = AsyncMock(  # type: ignore[method-assign]
        return_value=_MeasurementSnapshot(
            current_ph=6.0,
            current_ec=0.9,
            workflow_ready=False,
            current_stage="prepare_recirculation_check",
        )
    )

    outcome = await handler._run_check(
        task=task,
        plan=SimpleNamespace(),
        corr=corr,
        now=now,
    )

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.pipeline_phase == "recirc_mg"
    pid_repo.reset_no_effect_counts.assert_awaited_once_with(zone_id=90)
    handler._persist_pid_state_updates.assert_awaited()
    events = [c.kwargs.get("event_type") for c in handler._log_correction_event.await_args_list]
    assert "PIPELINE_STEP_CHANGED" in events
    assert "PID_EC_RESET" in events
