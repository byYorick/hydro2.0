"""E206: свежий EC ниже цели — один dose, кадра в этом тике нет."""

from __future__ import annotations

from datetime import datetime, timezone

from ae4.application.mutation_decision import decide_mutation
from ae4.domain.planting import LightIntegralCursor
from tests.unit.ae4.conftest_wave3 import make_phase, make_plan, make_telemetry
from tests.unit.ae4.conftest_wave4 import make_dose_plan


def test_e206_fresh_ec_below_target_one_dose_no_frame() -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    plan = make_plan(dose=make_dose_plan(), stale_ec_allows_shot=None)
    phase = make_phase(
        started_at=now.replace(hour=8),
        ec_target=1.4,
        ec_max=1.8,
        ec_unit="mS/cm",
        interval_sec=3600,
        duration_sec=60,
        on_time="06:00:00",
        off_time="22:00:00",
    )
    telemetry = make_telemetry(
        feed_min=1,
        clean_min=1,
        soil_value=50.0,
        ec_value=1.0,
        now=now,
    )
    decision = decide_mutation(
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
    assert decision.kind == "dose_pulse"
    assert decision.reagent == "nutrition"
    assert decision.dose_ml is not None and decision.dose_ml > 0
    assert decision.failed is False
    assert decision.create_task is True
