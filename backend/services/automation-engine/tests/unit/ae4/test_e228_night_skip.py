"""E228: ночь и влажность в полосе — кадра нет; окна нет — ночь не запрещает."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ae4.domain.water_demand import evaluate_water_demand
from tests.unit.ae4.conftest_wave1 import TZ, fresh_cursor, later, phase, sample


def _base_kwargs(*, now: datetime, ph, **extra: object) -> dict:
    return {
        "phase": ph,
        "now": now,
        "timezone_name": TZ,
        "telemetry_max_age_sec": 300,
        "last_shot": None,
        "last_planned_shot_at": None,
        "extra_used_in_half_interval": False,
        "successful_shots_in_window": 0,
        "integral": fresh_cursor(at=ph.started_at),
        "new_light_samples": (),
        "soil_moisture": sample(
            metric_type="SOIL_MOISTURE",
            channel="soil_moisture",
            value=50.0,
            ts=now,
            unit="%",
        ),
        "temp_air": None,
        "humidity_air": None,
        "emergency_stop": False,
        "feed_empty": False,
        **extra,
    }


def test_e228_night_with_moisture_in_band_skips_shot() -> None:
    tz = ZoneInfo(TZ)
    started = datetime(2026, 6, 1, 6, 0, tzinfo=tz)
    # Интервал вышел, но ночь.
    now = datetime(2026, 6, 1, 23, 0, tzinfo=tz)
    ph = phase(
        started_at=started,
        interval_sec=3600,
        duration_sec=60,
        on_time="06:00:00",
        off_time="22:00:00",
        soil_moisture_min=40.0,
        soil_moisture_max=60.0,
        soil_moisture_unit="%",
    )
    decision = evaluate_water_demand(**_base_kwargs(now=now, ph=ph))
    assert decision.shoot is False
    assert decision.reason_code == "night_skip"
    assert decision.failed is False


def test_e228_no_light_window_does_not_block_planned_interval() -> None:
    tz = ZoneInfo(TZ)
    started = datetime(2026, 6, 1, 6, 0, tzinfo=tz)
    now = later(started, hours=2)
    ph = phase(
        started_at=started,
        interval_sec=3600,
        duration_sec=60,
        # окна нет
        on_time=None,
        off_time=None,
        lighting_start_time=None,
        lighting_photoperiod_hours=None,
    )
    decision = evaluate_water_demand(**_base_kwargs(now=now, ph=ph, soil_moisture=None))
    assert decision.shoot is True
    assert decision.kind == "planned"
