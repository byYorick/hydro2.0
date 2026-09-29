"""E229: сушь — один внеочередной на полуинтервал; пауза не даёт второй."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ae4.domain.planting import ShotMark
from ae4.domain.water_demand import evaluate_water_demand
from tests.unit.ae4.conftest_wave1 import TZ, fresh_cursor, later, phase, sample


def test_e229_drought_one_extra_per_half_interval() -> None:
    tz = ZoneInfo(TZ)
    started = datetime(2026, 6, 1, 8, 0, tzinfo=tz)
    now = later(started, minutes=10)
    ph = phase(
        started_at=started,
        interval_sec=3600,
        duration_sec=60,
        soil_moisture_min=40.0,
        soil_moisture_max=60.0,
        soil_moisture_unit="%",
    )
    moist = sample(
        metric_type="SOIL_MOISTURE",
        channel="soil_moisture",
        value=20.0,
        ts=now,
        unit="%",
    )
    first = evaluate_water_demand(
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
        soil_moisture=moist,
        temp_air=None,
        humidity_air=None,
        emergency_stop=False,
        feed_empty=False,
    )
    assert first.shoot is True
    assert first.kind == "extra"

    after_pause = later(now, seconds=61)
    moist2 = sample(
        metric_type="SOIL_MOISTURE",
        channel="soil_moisture",
        value=20.0,
        ts=after_pause,
        unit="%",
    )
    second = evaluate_water_demand(
        phase=ph,
        now=after_pause,
        timezone_name=TZ,
        telemetry_max_age_sec=300,
        last_shot=ShotMark(at=now, kind="extra", phase_id=1, duration_sec=60),
        last_planned_shot_at=started,
        extra_used_in_half_interval=True,
        successful_shots_in_window=1,
        integral=fresh_cursor(at=started),
        new_light_samples=(),
        soil_moisture=moist2,
        temp_air=None,
        humidity_air=None,
        emergency_stop=False,
        feed_empty=False,
    )
    assert second.shoot is False
    assert second.kind is None


def test_e229_planned_shot_does_not_consume_extra_flag() -> None:
    tz = ZoneInfo(TZ)
    started = datetime(2026, 6, 1, 8, 0, tzinfo=tz)
    now = later(started, hours=1)
    ph = phase(started_at=started, interval_sec=3600, duration_sec=60)
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
        temp_air=None,
        humidity_air=None,
        emergency_stop=False,
        feed_empty=False,
    )
    assert decision.shoot is True
    assert decision.kind == "planned"
