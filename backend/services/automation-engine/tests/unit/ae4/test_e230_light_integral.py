"""E230: интеграл с прошлого кадра достиг цели — один внеочередной."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ae4.domain.planting import LightIntegralCursor
from ae4.domain.water_demand import advance_light_integral, evaluate_water_demand
from tests.unit.ae4.conftest_wave1 import TZ, later, phase, sample


def test_e230_light_integral_triggers_extra_shot() -> None:
    tz = ZoneInfo(TZ)
    started = datetime(2026, 6, 1, 8, 0, tzinfo=tz)
    now = later(started, minutes=30)
    ph = phase(
        started_at=started,
        interval_sec=3600,
        duration_sec=60,
        light_integral_per_shot=1000.0,
        light_integral_unit="lux·s",
    )
    cursor = LightIntegralCursor(
        accumulated=0.0,
        last_accounted_ts=started,
        unit="lux·s",
        status="ok",
        last_value=100.0,
    )
    t1 = later(started, minutes=5)
    t2 = later(started, minutes=15)
    samples = (
        sample(
            metric_type="LIGHT_INTENSITY",
            channel="light",
            value=100.0,
            ts=t1,
            unit="lux·s",
        ),
        sample(
            metric_type="LIGHT_INTENSITY",
            channel="light",
            value=100.0,
            ts=t2,
            unit="lux·s",
        ),
    )
    # 100 * 600с от started с last_value + 100*600 между пробами = достаточно.
    advanced = advance_light_integral(
        cursor=cursor,
        samples=samples,
        now=now,
        telemetry_max_age_sec=3600,
        target_unit="lux·s",
        phase_started_at=started,
    )
    assert advanced.status == "ok"
    assert advanced.accumulated >= 1000.0

    decision = evaluate_water_demand(
        phase=ph,
        now=now,
        timezone_name=TZ,
        telemetry_max_age_sec=3600,
        last_shot=None,
        last_planned_shot_at=started,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=cursor,
        new_light_samples=samples,
        soil_moisture=None,
        temp_air=None,
        humidity_air=None,
        emergency_stop=False,
        feed_empty=False,
    )
    assert decision.shoot is True
    assert decision.kind == "extra"
    assert decision.reason_code == "light_integral_reached"
