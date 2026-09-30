"""Раствор вне коридора без импульса в этом тике — кадра нет."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ae4.application.mutation_decision import decide_mutation
from ae4.config.zone_plan import _build_dose_plan
from ae4.domain.dose_policy import DoseReagentState
from ae4.domain.planting import LightIntegralCursor, ShotMark
from tests.unit.ae4.conftest_wave3 import make_phase, make_plan, make_telemetry
from tests.unit.ae4.conftest_wave4 import make_dose_plan


def _decide(**kwargs):
    now = kwargs.pop("now", datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc))
    started = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    phase = kwargs.pop(
        "phase",
        make_phase(
            started_at=started,
            interval_sec=900,
            duration_sec=15,
            ph_target=5.8,
            ph_min=5.6,
            ph_max=6.0,
            ec_target=1.4,
            ec_min=1.2,
            ec_max=1.6,
            ec_unit="mS/cm",
        ),
    )
    plan = kwargs.pop("plan", make_plan(dose=make_dose_plan(max_dose_ml=None)))
    telemetry = kwargs.pop(
        "telemetry",
        make_telemetry(
            feed_min=1,
            clean_min=1,
            soil_value=50.0,
            ec_value=0.4,
            ph_value=7.03,
            now=now,
        ),
    )
    return decide_mutation(
        plan=plan,
        phase=phase,
        telemetry=telemetry,
        now=now,
        emergency_stop=False,
        last_shot=ShotMark(
            at=started,
            kind="planned",
            phase_id=phase.phase_id,
            duration_sec=15,
        ),
        last_planned_shot_at=started,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=LightIntegralCursor(
            accumulated=0.0,
            last_accounted_ts=started,
            unit=None,
            status="ok",
        ),
        new_light_samples=(),
        **kwargs,
    )


def test_outside_corridor_without_pulse_holds_shot_and_alerts() -> None:
    decision = _decide()
    assert decision.kind is None
    assert decision.create_task is False
    assert decision.create_alert is True
    assert decision.failed is False
    assert decision.reason_code == "solution_not_ready"
    assert "ждём решения" in decision.human_message


def test_outside_corridor_while_interval_waits_does_not_alert() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    decision = _decide(
        now=now,
        plan=make_plan(dose=make_dose_plan()),
        ec_state=DoseReagentState(
            reagent="nutrition",
            last_dose_at=now - timedelta(seconds=10),
            no_effect_count=0,
            baseline_value=0.4,
            last_dose_ml=5.0,
            observation="effect",
        ),
    )
    assert decision.kind is None
    assert decision.create_alert is False
    assert decision.reason_code == "solution_correcting"


def test_inside_corridor_still_irrigates_when_pulse_is_not_due() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    started = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    decision = _decide(
        now=now,
        plan=make_plan(dose=make_dose_plan(max_dose_ml=None)),
        phase=make_phase(
            started_at=started,
            interval_sec=900,
            duration_sec=15,
            ph_target=5.8,
            ph_min=5.6,
            ph_max=6.0,
            ec_target=1.5,
            ec_min=1.2,
            ec_max=1.6,
            ec_unit="mS/cm",
        ),
        telemetry=make_telemetry(
            feed_min=1,
            clean_min=1,
            soil_value=50.0,
            ec_value=1.4,
            ph_value=5.8,
            now=now,
        ),
    )
    assert decision.kind == "feed_to_plants"


def test_outside_corridor_without_sensor_mode_waits_instead_of_failing_task() -> None:
    decision = _decide(plan=make_plan(dose=make_dose_plan()))
    assert decision.kind is None
    assert decision.create_task is False
    assert decision.create_alert is True
    assert decision.reason_code == "solution_not_ready"


def test_outside_corridor_with_sensor_mode_doses_instead_of_shot() -> None:
    plan = make_plan(dose=make_dose_plan())
    plans = dict(plan.command_plans)
    inner = dict(plans["plans"])
    inner["sensor_mode_activate"] = [
        {
            "node_uid": "nd-ec",
            "channel": "ec_sensor",
            "cmd": "set_relay",
            "params": {"state": True},
        }
    ]
    plans["plans"] = inner
    from dataclasses import replace

    decision = _decide(plan=replace(plan, command_plans=plans))
    assert decision.kind == "dose_pulse"
    assert decision.reagent == "nutrition"


def test_controller_caps_are_read_from_base_controllers() -> None:
    plan = _build_dose_plan(
        correction_root={
            "base": {
                "controllers": {
                    "ec": {"max_dose_ml": 80, "min_interval_sec": 25},
                    "ph": {"max_dose_ml": 35, "min_interval_sec": 20},
                }
            },
            "pump_calibration": {},
        },
        zone_bundle={
            "process_calibration": {
                "irrigation": {
                    "ec_gain_per_ml": 0.008,
                    "ph_up_gain_per_ml": 0.018,
                    "ph_down_gain_per_ml": 0.018,
                }
            }
        },
        stale_ec_allows_shot=None,
    )
    assert plan.ec.max_dose_ml == 80
    assert plan.ph.max_dose_ml == 35
    assert plan.ec.gain == 0.008
