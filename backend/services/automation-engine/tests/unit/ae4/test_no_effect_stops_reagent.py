"""Третий подряд no-effect останавливает реагент — следующий импульс не публикуется."""

from __future__ import annotations

from datetime import datetime, timezone

from ae4.application.mutation_decision import decide_mutation
from ae4.domain.dose_policy import DoseReagentState
from ae4.domain.planting import LightIntegralCursor
from tests.unit.ae4.conftest_wave3 import make_phase, make_plan, make_telemetry
from tests.unit.ae4.conftest_wave4 import make_dose_plan


def test_third_no_effect_stops_reagent_no_pulse() -> None:
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
        clean_min=1,
        soil_value=50.0,
        ec_value=1.0,
        now=now,
    )
    stopped = DoseReagentState(
        reagent="nutrition",
        last_dose_at=now.replace(hour=9),
        no_effect_count=3,
        baseline_value=1.0,
        last_dose_ml=1.0,
        observation="no_effect",
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
        ec_state=stopped,
    )
    assert decision.kind != "dose_pulse"
    assert decision.dose_ml is None
    assert decision.create_task is False or decision.kind == "feed_to_plants"
    assert decision.dose_decision is not None
    assert decision.dose_decision.reason_code == "reagent_no_effect_stopped"
    assert decision.dose_decision.allow_pulse is False
    # Критический вызов один раз (dedupe на failure_report) — здесь флаг create_alert.
    assert decision.create_alert is True or decision.dose_decision.critical_alert is True
    if decision.kind is None:
        assert decision.reason_code == "reagent_no_effect_stopped"
