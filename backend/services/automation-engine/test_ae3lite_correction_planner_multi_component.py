from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ae3lite.domain.services.correction_planner import CorrectionPlanner
from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.errors import PlannerConfigurationError


def _actuator(node_uid: str, channel: str, *, min_effective_ml: float = 0.1) -> dict:
    return {
        "node_uid": node_uid,
        "channel": channel,
        "calibration": {
            "ml_per_sec": 10.0,
            "min_effective_ml": min_effective_ml,
        },
    }


def _base_correction_cfg() -> dict:
    return {
        "dose_ec_channel": "pump_a",
        "dose_ph_up_channel": "pump_base",
        "dose_ph_down_channel": "pump_acid",
        "solution_volume_l": 100.0,
        "max_ec_dose_ml": 50.0,
        "max_ph_dose_ml": 20.0,
        "pump_calibration": {
            "min_dose_ms": 50,
            "ml_per_sec_min": 1.0,
            "ml_per_sec_max": 50.0,
        },
        "controllers": {
            "ec": {"kp": 1.0, "ki": 0.0, "kd": 0.0, "deadband": 0.01},
            "ph": {"kp": 0.0, "ki": 0.0, "kd": 0.0, "deadband": 999.0},
        },
    }


def test_multi_sequential_splits_ec_gap_by_renormalized_ratios_excluding_npk() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)

    correction_cfg = {
        **_base_correction_cfg(),
        "ec_dosing_mode": "multi_sequential",
        "ec_component_ratios": {"npk": 0.6, "calcium": 0.2, "magnesium": 0.12, "micro": 0.08},
        "ec_excluded_components": ("npk",),
        "actuators": {},
    }
    process_calibrations = {
        "irrigation": {
            "ec_gain_per_ml": 0.1,
            "ec_component_gains": {
                "calcium": {"ec_gain_per_ml": 0.1},
                "magnesium": {"ec_gain_per_ml": 0.1},
                "micro": {"ec_gain_per_ml": 0.1},
            },
        }
    }
    ec_actuators = {
        "calcium": _actuator("nd-ca", "pump_b"),
        "magnesium": _actuator("nd-mg", "pump_c"),
        "micro": _actuator("nd-mi", "pump_d"),
    }

    plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.0,
        target_ph=6.0,
        target_ec=1.4,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
        correction_config=correction_cfg,
        workflow_phase="irrigating",
        process_calibrations=process_calibrations,
        ec_component_policy={},
        pid_state={"ec": {"integral": 0.0, "prev_error": 0.0, "prev_derivative": 0.0}},
        pid_configs={},
        now=now,
        ec_actuators=ec_actuators,
    )

    assert plan.needs_ec is True
    assert plan.ec_component == "multi_sequential"
    assert len(plan.ec_dose_sequence) == 3
    components = [s.component for s in plan.ec_dose_sequence]
    assert components == ["calcium", "magnesium", "micro"]


def test_single_mode_backward_compatible_has_empty_sequence() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    correction_cfg = {**_base_correction_cfg(), "ec_dosing_mode": "single"}
    ec_actuator = _actuator("nd-ec", "pump_a")
    plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.0,
        target_ph=6.0,
        target_ec=1.4,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
        correction_config=correction_cfg,
        workflow_phase="tank_recirc",
        process_calibrations={"tank_recirc": {"ec_gain_per_ml": 0.1}},
        ec_component_policy={},
        pid_state={"ec": {"integral": 0.0, "prev_error": 0.0, "prev_derivative": 0.0}},
        pid_configs={},
        now=now,
        ec_actuator=ec_actuator,
    )
    assert plan.needs_ec is True
    assert plan.ec_dose_sequence == ()


def test_multi_sequential_reapplies_caps_after_min_effective_bump() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)

    correction_cfg = {
        **_base_correction_cfg(),
        "max_ec_dose_ml": 1.0,
        "ec_dosing_mode": "multi_sequential",
        "ec_component_ratios": {"calcium": 0.2, "magnesium": 0.4, "micro": 0.4},
        "pump_calibration": {
            "min_dose_ms": 10,
            "ml_per_sec_min": 1.0,
            "ml_per_sec_max": 50.0,
        },
    }
    process_calibrations = {
        "irrigation": {
            "ec_gain_per_ml": 0.1,
            "ec_component_gains": {
                "calcium": {"ec_gain_per_ml": 0.1},
                "magnesium": {"ec_gain_per_ml": 0.1},
                "micro": {"ec_gain_per_ml": 0.1},
            },
        }
    }
    ec_actuators = {
        "calcium": _actuator("nd-ca", "pump_b", min_effective_ml=0.3),
        "magnesium": _actuator("nd-mg", "pump_c", min_effective_ml=0.1),
        "micro": _actuator("nd-mi", "pump_d", min_effective_ml=0.1),
    }

    plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.0,
        target_ph=6.0,
        target_ec=1.4,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
        correction_config=correction_cfg,
        workflow_phase="irrigating",
        process_calibrations=process_calibrations,
        ec_component_policy={},
        pid_state={"ec": {"integral": 0.0, "prev_error": 0.0, "prev_derivative": 0.0}},
        pid_configs={},
        now=now,
        ec_actuators=ec_actuators,
    )

    assert [step.component for step in plan.ec_dose_sequence] == ["magnesium", "micro"]
    assert plan.ec_amount_ml <= 1.0


def test_multi_sequential_fail_closed_when_npk_excluded_and_no_safe_components() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)

    correction_cfg = {
        **_base_correction_cfg(),
        "max_ec_dose_ml": 1.0,
        "ec_dosing_mode": "multi_sequential",
        "ec_component_ratios": {"npk": 1.0},
        "ec_excluded_components": ("npk",),
    }

    with pytest.raises(PlannerConfigurationError, match="no active EC components are configured"):
        planner.build_dose_plan(
            current_ph=6.0,
            current_ec=1.0,
            target_ph=6.0,
            target_ec=1.4,
            ph_tolerance_pct=1.0,
            ec_tolerance_pct=1.0,
            correction_config=correction_cfg,
            workflow_phase="irrigating",
            process_calibrations={"irrigation": {"ec_gain_per_ml": 0.1}},
            ec_component_policy={},
            pid_state={"ec": {"integral": 0.0, "prev_error": 0.0, "prev_derivative": 0.0}},
            pid_configs={},
            now=now,
            ec_actuators={},
        )


@pytest.mark.asyncio
async def test_multi_sequential_irrigating_excluded_npk_requires_active_components_fail_closed() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    correction_cfg = {
        **_base_correction_cfg(),
        "ec_dosing_mode": "multi_sequential",
        "ec_component_ratios": {"npk": 1.0},
        "ec_excluded_components": ("npk",),
        "actuators": {},
    }
    process_calibrations = {"irrigation": {"ec_gain_per_ml": 0.1, "ec_component_gains": {}}}

    with pytest.raises(PlannerConfigurationError, match="excludes NPK"):
        planner.build_dose_plan(
            current_ph=6.0,
            current_ec=1.0,
            target_ph=6.0,
            target_ec=1.4,
            ph_tolerance_pct=1.0,
            ec_tolerance_pct=1.0,
            correction_config=correction_cfg,
            workflow_phase="irrigating",
            process_calibrations=process_calibrations,
            ec_component_policy={},
            pid_state={"ec": {"integral": 0.0, "prev_error": 0.0, "prev_derivative": 0.0}},
            pid_configs={},
            now=now,
            ec_actuators={},
        )


def test_multi_sequential_irrigating_excluded_npk_no_effective_pulses_fails_closed() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)

    correction_cfg = {
        **_base_correction_cfg(),
        "ec_dosing_mode": "multi_sequential",
        "ec_component_ratios": {"npk": 0.6, "calcium": 0.2, "magnesium": 0.12, "micro": 0.08},
        "ec_excluded_components": ("npk",),
        "actuators": {},
        # Extremely low cap, but min_effective_ml will be higher -> should discard all components.
        "max_ec_dose_ml": 0.01,
    }
    process_calibrations = {
        "irrigation": {
            "ec_gain_per_ml": 0.1,
            "ec_component_gains": {
                "calcium": {"ec_gain_per_ml": 0.1},
                "magnesium": {"ec_gain_per_ml": 0.1},
                "micro": {"ec_gain_per_ml": 0.1},
            },
        }
    }
    ec_actuators = {
        "calcium": _actuator("nd-ca", "pump_b", min_effective_ml=0.1),
        "magnesium": _actuator("nd-mg", "pump_c", min_effective_ml=0.1),
        "micro": _actuator("nd-mi", "pump_d", min_effective_ml=0.1),
    }

    with pytest.raises(PlannerConfigurationError, match="no safe non-NPK doses during irrigation"):
        planner.build_dose_plan(
            current_ph=6.0,
            current_ec=1.0,
            target_ph=6.0,
            target_ec=1.4,
            ph_tolerance_pct=1.0,
            ec_tolerance_pct=1.0,
            correction_config=correction_cfg,
            workflow_phase="irrigating",
            process_calibrations=process_calibrations,
            ec_component_policy={},
            pid_state={"ec": {"integral": 0.0, "prev_error": 0.0, "prev_derivative": 0.0}},
            pid_configs={},
            now=now,
            ec_actuators=ec_actuators,
        )


def test_multi_parallel_allows_aliases_for_same_npk_pump() -> None:
    planner = CorrectionPlanner()
    now = datetime(2026, 3, 31, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)

    correction_cfg = {
        **_base_correction_cfg(),
        "ec_dosing_mode": "multi_parallel",
        "ec_component_ratios": {"npk": 0.6, "calcium": 0.25, "magnesium": 0.15},
        "actuators": {},
    }
    process_calibrations = {
        "irrigation": {
            "ec_gain_per_ml": 0.1,
            "ec_component_gains": {
                "npk": {"ec_gain_per_ml": 0.1},
                "calcium": {"ec_gain_per_ml": 0.1},
                "magnesium": {"ec_gain_per_ml": 0.1},
            },
        }
    }
    npk = _actuator("nd-ec-1", "pump_a")
    ec_actuators = {
        "pump_a": npk,
        "pump_a": npk,
        "ec_npk": npk,
        "pump_a": npk,
        "calcium": _actuator("nd-ca", "pump_b"),
        "magnesium": _actuator("nd-mg", "pump_c"),
    }

    plan = planner.build_dose_plan(
        current_ph=6.0,
        current_ec=1.0,
        target_ph=6.0,
        target_ec=1.4,
        ph_tolerance_pct=1.0,
        ec_tolerance_pct=1.0,
        correction_config=correction_cfg,
        workflow_phase="irrigating",
        process_calibrations=process_calibrations,
        ec_component_policy={},
        pid_state={"ec": {"integral": 0.0, "prev_error": 0.0, "prev_derivative": 0.0}},
        pid_configs={},
        now=now,
        ec_actuators=ec_actuators,
    )

    assert plan.needs_ec is True
    assert plan.ec_component == "multi_parallel"
    assert {step.component for step in plan.ec_dose_sequence} == {"npk", "calcium", "magnesium"}
