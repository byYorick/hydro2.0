"""E208: протухший pH — кислоты нет, полив этим фактом не запрещён."""

from __future__ import annotations

from datetime import datetime, timezone

from ae4.application.mutation_decision import decide_mutation
from ae4.domain.planting import LightIntegralCursor, ShotMark
from tests.unit.ae4.conftest_wave3 import make_phase, make_plan, make_telemetry
from tests.unit.ae4.conftest_wave4 import make_dose_plan


def test_e208_stale_ph_no_acid_shot_not_blocked() -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    started = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    plan = make_plan(dose=make_dose_plan(), stale_ec_allows_shot=True)
    phase = make_phase(
        started_at=started,
        interval_sec=3600,
        duration_sec=60,
        ph_target=5.8,
        ec_target=1.4,
        ec_max=1.8,
        ec_unit="mS/cm",
        soil_moisture_min=40.0,
        soil_moisture_max=60.0,
        on_time="06:00:00",
        off_time="22:00:00",
    )
    # EC свежий на цели — соли нет; pH протух — кислоты нет; сушь даёт кадр.
    telemetry = make_telemetry(
        feed_min=1,
        clean_min=1,
        soil_value=20.0,
        ec_value=1.4,
        ph_value=5.0,
        stale_ph=True,
        now=now,
    )
    decision = decide_mutation(
        plan=plan,
        phase=phase,
        telemetry=telemetry,
        now=now,
        emergency_stop=False,
        last_shot=ShotMark(
            at=started,
            kind="planned",
            phase_id=phase.phase_id,
            duration_sec=60,
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
    )
    assert decision.kind == "feed_to_plants"
    assert decision.reagent is None
    assert decision.failed is False
    if decision.dose_decision is not None:
        assert decision.dose_decision.allow_pulse is False
        assert decision.dose_decision.blocks_shot is False
