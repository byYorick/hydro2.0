"""E207: EC выше коридора — нет dose и кадра; долив или пауза; failed не ставится."""

from __future__ import annotations

from datetime import datetime, timezone

from ae4.application.mutation_decision import decide_mutation
from ae4.domain.planting import LightIntegralCursor
from tests.unit.ae4.conftest_wave3 import make_phase, make_plan, make_telemetry
from tests.unit.ae4.conftest_wave4 import make_dose_plan


def _decide(*, feed_max: int, ec_value: float = 2.5):
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    plan = make_plan(dose=make_dose_plan())
    phase = make_phase(
        started_at=now.replace(hour=8),
        ec_target=1.4,
        ec_max=1.8,
        ec_unit="mS/cm",
    )
    telemetry = make_telemetry(
        feed_min=1,
        feed_max=feed_max,
        clean_min=1,
        soil_value=50.0,
        ec_value=ec_value,
        now=now,
    )
    return decide_mutation(
        plan=plan,
        phase=phase,
        telemetry=telemetry,
        now=now,
        emergency_stop=False,
        last_shot=None,
        last_planned_shot_at=phase.started_at,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=LightIntegralCursor(
            accumulated=0.0,
            last_accounted_ts=phase.started_at,
            unit=None,
            status="ok",
        ),
        new_light_samples=(),
    )


def test_e207_ec_high_tank_not_full_dilutes_no_dose_no_failed() -> None:
    decision = _decide(feed_max=0)
    assert decision.kind == "clean_to_feed"
    assert decision.reason_code == "ec_high_dilute"
    assert decision.failed is False
    assert decision.reagent is None
    assert decision.dose_ml is None


def test_e207_ec_high_tank_full_pause_no_failed() -> None:
    decision = _decide(feed_max=1)
    assert decision.kind is None
    assert decision.reason_code == "ec_high_tank_full_await_drain"
    assert decision.failed is False
    assert decision.create_alert is True
    assert decision.create_task is False
