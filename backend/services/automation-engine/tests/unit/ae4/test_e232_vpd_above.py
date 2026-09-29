"""E232: VPD выше нормы — один внеочередной кадр на полуинтервал."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ae4.domain.water_demand import evaluate_water_demand
from tests.unit.ae4.conftest_wave1 import TZ, fresh_cursor, later, phase, sample


def test_e232_vpd_above_max_extra_shot() -> None:
    tz = ZoneInfo(TZ)
    started = datetime(2026, 6, 1, 8, 0, tzinfo=tz)
    now = later(started, minutes=20)
    ph = phase(
        started_at=started,
        interval_sec=3600,
        duration_sec=90,
        vpd_min=0.4,
        vpd_max=0.8,
    )
    temp = sample(
        metric_type="TEMPERATURE",
        channel="air_temp_c",
        value=32.0,
        ts=now,
        unit="C",
    )
    hum = sample(
        metric_type="HUMIDITY",
        channel="air_rh",
        value=30.0,
        ts=now,
        unit="%",
    )
    decision = evaluate_water_demand(
        phase=ph,
        now=now,
        timezone_name=TZ,
        telemetry_max_age_sec=300,
        last_shot=None,
        last_planned_shot_at=started,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=fresh_cursor(at=started),
        new_light_samples=(),
        soil_moisture=None,
        temp_air=temp,
        humidity_air=hum,
        emergency_stop=False,
        feed_empty=False,
    )
    assert decision.shoot is True
    assert decision.kind == "extra"
    assert decision.reason_code == "vpd_above_max"
    assert ph.duration_sec == 90
