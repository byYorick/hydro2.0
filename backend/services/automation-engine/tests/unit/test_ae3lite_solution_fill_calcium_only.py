"""Unit tests: solution_fill calcium-only (no pH)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.application.handlers.solution_fill import SolutionFillCheckHandler
from ae3lite.application.services.correction_pipeline import pipeline_dose_flags
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.services.correction_planner import CorrectionPlanner
from ae3lite.domain.services.nutrient_pipeline import (
    PIPELINE_PHASE_FILL_CA,
    compute_component_targets,
)


def _cfg() -> dict:
    return {
        "controllers": {
            "ph": {"kp": 5, "ki": 0, "kd": 0, "deadband": 0.05, "max_dose_ml": 20, "min_interval_sec": 0},
            "ec": {"kp": 30, "ki": 0, "kd": 0, "deadband": 0.0, "max_dose_ml": 50, "min_interval_sec": 0},
        },
        "dose_ec_channel": "pump_a",
        "dose_ph_up_channel": "pump_base",
        "dose_ph_down_channel": "pump_acid",
        "max_ec_dose_ml": 50,
        "max_ph_dose_ml": 20,
        "solution_volume_l": 100.0,
        "pump_calibration": {"min_dose_ms": 50, "ml_per_sec_min": 0.01, "ml_per_sec_max": 100},
    }


def test_fill_pipeline_flags_no_ph() -> None:
    corr = CorrectionState.build_default(
        corr_step="corr_check",
        max_attempts=10,
        ec_max_attempts=10,
        ph_max_attempts=0,
        activated_here=False,
        stabilization_sec=10,
        return_stage_success="solution_fill_check",
        return_stage_fail="solution_fill_check",
    )
    from dataclasses import replace

    corr = replace(corr, pipeline_phase=PIPELINE_PHASE_FILL_CA, active_component="calcium")
    flags = pipeline_dose_flags(corr)
    assert flags["allow_ec"] is True
    assert flags["allow_ph"] is False
    assert flags["active_component"] == "calcium"


def test_fill_dose_only_calcium_pump_b() -> None:
    planner = CorrectionPlanner()
    plan = planner.build_dose_plan(
        current_ph=7.5,
        current_ec=0.5,
        target_ph=6.0,
        target_ec=0.9,  # T_ca
        ph_tolerance_pct=5.0,
        ec_tolerance_pct=5.0,
        correction_config=_cfg(),
        workflow_phase="tank_filling",
        process_calibrations={"solution_fill": {"ec_gain_per_ml": 0.2, "ph_down_gain_per_ml": 0.1}},
        active_component="calcium",
        allow_ph=False,
        ec_actuators={
            "calcium": {"node_uid": "ec-1", "channel": "pump_b", "calibration": {"ml_per_sec": 1.0}},
            "npk": {"node_uid": "ec-1", "channel": "pump_a", "calibration": {"ml_per_sec": 1.0}},
        },
        ph_down_actuator={"node_uid": "ph-1", "channel": "pump_acid", "calibration": {"ml_per_sec": 1.0}},
    )
    assert plan.needs_ec is True
    assert plan.ec_component == "calcium"
    assert plan.ec_channel == "pump_b"
    assert plan.needs_ph_up is False
    assert plan.needs_ph_down is False


@pytest.mark.asyncio
async def test_fill_gate_is_ec_only_ignores_ph(monkeypatch: pytest.MonkeyPatch) -> None:
    """Before fill-corr entry: wrong pH must not block EC-at-T_ca poll path."""
    now = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)
    targets = compute_component_targets(
        water_ec=0.4,
        water_ph=7.0,
        target_ec=2.0,
        ratios={"calcium": 0.25, "magnesium": 0.15, "npk": 0.45, "micro": 0.15},
    )
    corr = replace(
        CorrectionState.build_default(
            corr_step="corr_check",
            max_attempts=10,
            ec_max_attempts=10,
            ph_max_attempts=0,
            activated_here=False,
            stabilization_sec=10,
            return_stage_success="solution_fill_check",
            return_stage_fail="solution_fill_check",
        ),
        pipeline_phase=PIPELINE_PHASE_FILL_CA,
        active_component="calcium",
        water_ec=targets.water_ec,
        water_ph=targets.water_ph,
        nutrient_budget=targets.nutrient_budget,
        component_targets_json=targets.to_json(),
        baseline_id=11,
    )
    task = SimpleNamespace(id=8, zone_id=80, correction=corr)
    runtime = SimpleNamespace(
        telemetry_max_age_sec=60,
        target_ec=2.0,
        target_ec_prepare=targets.T_ca,
        npk_ec_share=0.25,
        prepare_tolerance={"ph_pct": 5.0, "ec_pct": 10.0},
        prepare_tolerance_by_phase={"solution_fill": {"ph_pct": 5.0, "ec_pct": 10.0}},
    )
    handler = SolutionFillCheckHandler(runtime_monitor=SimpleNamespace(), command_gateway=SimpleNamespace())
    monkeypatch.setattr(
        handler,
        "_load_existing_fill_baseline",
        AsyncMock(return_value=(targets, 11)),
    )
    # EC at T_ca; pH deliberately far from target — must still count as reached.
    handler._read_target_metric_window = AsyncMock(  # type: ignore[method-assign]
        return_value={"ready": True, "value": targets.T_ca},
    )
    handler._prepare_tolerance_for_task = lambda **_kw: {"ph_pct": 5.0, "ec_pct": 10.0}  # type: ignore[method-assign]
    handler._required_prepare_tolerance_pct = (  # type: ignore[method-assign]
        lambda *, tolerance, key: float(tolerance[key])
    )
    handler._correction_config_for_task = lambda **_kw: {}  # type: ignore[method-assign]
    handler._process_cfg_for_task = lambda **_kw: {}  # type: ignore[method-assign]
    handler._observation_config = lambda **_kw: {}  # type: ignore[method-assign]
    handler._irrigation_ec_target = lambda **_kw: 2.0  # type: ignore[method-assign]

    reached = await handler._fill_ec_target_reached(
        task=task,
        plan=SimpleNamespace(runtime=runtime),
        now=now,
        runtime=runtime,
    )
    assert reached is True
    # Gate reads EC only — one window call.
    assert handler._read_target_metric_window.await_count == 1
    assert handler._read_target_metric_window.await_args.kwargs["sensor_type"] == "EC"
