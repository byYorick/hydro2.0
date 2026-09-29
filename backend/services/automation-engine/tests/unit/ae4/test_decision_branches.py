"""Ветки decide_mutation, которых не закрывали отдельные E2xx-файлы."""

from __future__ import annotations

from datetime import datetime, timezone

from ae4.application.mutation_decision import decide_mutation
from ae4.domain.planting import LightIntegralCursor
from tests.unit.ae4.conftest_wave3 import make_phase, make_plan, make_telemetry
from tests.unit.ae4.conftest_wave4 import make_dose_plan
from tests.unit.ae4.test_e207_full_tank_drain import _drain_plans


def _now() -> datetime:
    return datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)


def _integral(at: datetime) -> LightIntegralCursor:
    return LightIntegralCursor(
        accumulated=0.0,
        last_accounted_ts=at,
        unit=None,
        status="ok",
    )


def _decide(**kwargs):
    now = kwargs.pop("now", _now())
    plan = kwargs.pop("plan", make_plan())
    phase = kwargs.pop("phase", make_phase(started_at=now.replace(hour=8)))
    telemetry = kwargs.pop("telemetry")
    return decide_mutation(
        plan=plan,
        phase=phase,
        telemetry=telemetry,
        now=now,
        emergency_stop=kwargs.pop("emergency_stop", False),
        last_shot=None,
        last_planned_shot_at=phase.started_at,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=_integral(now),
        new_light_samples=(),
    )


def _without_solution_fill():
    plans = dict(make_plan().command_plans["plans"])
    plans.pop("solution_fill_start", None)
    plans.pop("solution_fill_stop", None)
    return {"plans": plans}


def test_emergency_stop_blocks_before_tanks() -> None:
    now = _now()
    decision = _decide(
        emergency_stop=True,
        telemetry=make_telemetry(feed_min=0, clean_min=0, now=now),
        now=now,
    )
    assert decision.reason_code == "emergency_stop_activated"
    assert decision.kind is None
    assert decision.create_task is False
    assert decision.failed is True
    assert decision.create_alert is True


def test_empty_feed_with_clean_starts_topup() -> None:
    now = _now()
    decision = _decide(
        telemetry=make_telemetry(feed_min=0, clean_min=1, soil_value=50.0, now=now),
        now=now,
    )
    assert decision.kind == "clean_to_feed"
    assert decision.reason_code == "clean_to_feed_empty"
    assert decision.create_task is True
    assert decision.failed is False


def test_empty_feed_without_solution_fill_steps_does_not_invent_valve() -> None:
    now = _now()
    decision = _decide(
        plan=make_plan(command_plans=_without_solution_fill()),
        telemetry=make_telemetry(feed_min=0, clean_min=1, soil_value=50.0, now=now),
        now=now,
    )
    assert decision.kind is None
    assert decision.reason_code == "solution_fill_steps_missing"
    assert decision.create_task is False
    assert decision.create_alert is True


def test_ec_high_without_dilute_steps_alerts_and_skips_shot() -> None:
    now = _now()
    phase = make_phase(started_at=now.replace(hour=8), ec_target=1.4, ec_max=1.8, ec_unit="mS/cm")
    decision = _decide(
        plan=make_plan(command_plans=_without_solution_fill(), dose=make_dose_plan()),
        phase=phase,
        telemetry=make_telemetry(
            feed_min=1,
            feed_max=0,
            clean_min=1,
            soil_value=50.0,
            ec_value=2.5,
            now=now,
        ),
        now=now,
    )
    assert decision.kind is None
    assert decision.reason_code == "ec_high_no_dilute_steps"
    assert decision.failed is False
    assert decision.create_task is False
    assert decision.create_alert is True


def test_full_tank_drain_without_pump_rate_does_not_invent_seconds() -> None:
    now = _now()
    plan = make_plan(
        dose=make_dose_plan(),
        command_plans=_drain_plans(),
        ec_clean=0.2,
        nutrient_solution_volume_l=50.0,
        pump_main_ml_per_sec=None,
    )
    phase = make_phase(started_at=now.replace(hour=8), ec_target=1.4, ec_max=1.8, ec_unit="mS/cm")
    decision = _decide(
        plan=plan,
        phase=phase,
        telemetry=make_telemetry(
            feed_min=1,
            feed_max=1,
            clean_min=1,
            soil_value=50.0,
            ec_value=2.5,
            now=now,
            drain_bound=True,
            drain_min=1,
            drain_max=0,
            ec_drain_value=0.5,
        ),
        now=now,
    )
    assert decision.kind is None
    assert decision.reason_code == "drain_portion_pump_rate_missing"
    assert decision.create_task is False
    assert decision.create_alert is True
    assert decision.drain_duration_ms is None
