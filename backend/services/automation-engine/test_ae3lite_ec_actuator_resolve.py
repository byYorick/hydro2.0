"""Unit tests: pump_b ↔ calcium actuator resolve."""

from __future__ import annotations

import pytest

from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError
from ae3lite.domain.services.correction_planner import CorrectionPlanner, _find_ec_component_actuator
from ae3lite.domain.services.nutrient_pipeline import resolve_component_from_role_or_channel


def test_resolve_component_from_pump_b_role() -> None:
    assert resolve_component_from_role_or_channel(
        role="pump_b", channel="pump_b", calibration_component=None,
    ) == "calcium"


def test_find_actuator_by_pump_b_key() -> None:
    actuators = {
        "pump_b": {
            "node_uid": "ec-1",
            "channel": "pump_b",
            "calibration": {"ml_per_sec": 1.0},
        }
    }
    found = _find_ec_component_actuator(ec_actuators=actuators, component="calcium")
    assert found is not None
    assert found["channel"] == "pump_b"


def test_find_actuator_missing_fail_closed_in_planner() -> None:
    planner = CorrectionPlanner()
    with pytest.raises(PlannerConfigurationError) as exc:
        planner.build_dose_plan(
            current_ph=6.0,
            current_ec=0.5,
            target_ph=6.0,
            target_ec=1.0,
            ph_tolerance_pct=5.0,
            ec_tolerance_pct=5.0,
            correction_config={
                "controllers": {
                    "ph": {"kp": 1, "ki": 0, "kd": 0, "deadband": 0.05, "max_dose_ml": 10, "min_interval_sec": 0},
                    "ec": {"kp": 1, "ki": 0, "kd": 0, "deadband": 0.0, "max_dose_ml": 50, "min_interval_sec": 0},
                },
                "dose_ec_channel": "pump_a",
                "dose_ph_up_channel": "pump_base",
                "dose_ph_down_channel": "pump_acid",
                "max_ec_dose_ml": 50,
                "max_ph_dose_ml": 10,
                "solution_volume_l": 100.0,
                "pump_calibration": {"min_dose_ms": 50, "ml_per_sec_min": 0.01, "ml_per_sec_max": 100},
                "ec_dosing_mode": "single",
            },
            workflow_phase="tank_recirc",
            process_calibrations={"tank_recirc": {"ec_gain_per_ml": 0.2}},
            ec_actuators={},  # unresolved
            active_component="calcium",
            allow_ph=False,
        )
    assert exc.value.code == ErrorCodes.AE3_EC_ACTUATOR_COMPONENT_UNRESOLVED
