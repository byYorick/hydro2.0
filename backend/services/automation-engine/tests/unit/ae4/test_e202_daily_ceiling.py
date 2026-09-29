"""E202: потолок — число успешных кадров, не floor(окно/interval)."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ae4.domain.planting import PhaseTargets
from ae4.domain.water_demand import (
    daily_shot_ceiling,
    evaluate_water_demand,
    resolve_light_window,
)
from tests.unit.ae4.conftest_wave1 import TZ, fresh_cursor


def test_e202_ceiling_is_not_floor_window_over_interval() -> None:
    tz = ZoneInfo(TZ)
    # started_at в середине окна 06:00–22:00: плановых моментов мало,
    # floor(16h/1h)=16 было бы неверно.
    started = datetime(2026, 6, 1, 18, 0, tzinfo=tz)
    phase = PhaseTargets(
        phase_id=1,
        started_at=started,
        interval_sec=3600,
        duration_sec=60,
        on_time="06:00:00",
        off_time="22:00:00",
    )
    now = datetime(2026, 6, 1, 19, 0, tzinfo=tz)
    window = resolve_light_window(phase=phase, now=now, tz=tz)
    assert window is not None
    ceiling = daily_shot_ceiling(
        phase=phase,
        interval_sec=3600,
        now=now,
        tz=tz,
        window=window,
    )
    window_sec = (window.end_local - window.start_local).total_seconds()
    floor_wrong = math.floor(window_sec / 3600)
    assert floor_wrong == 16
    assert ceiling < floor_wrong
    assert ceiling == 4  # 18:00, 19:00, 20:00, 21:00


def test_e202_interval_or_duration_nonpositive_blocks_irrigation() -> None:
    tz_now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    phase = PhaseTargets(
        phase_id=1,
        started_at=tz_now,
        interval_sec=0,
        duration_sec=60,
    )
    decision = evaluate_water_demand(
        phase=phase,
        now=tz_now,
        timezone_name=TZ,
        telemetry_max_age_sec=120,
        last_shot=None,
        last_planned_shot_at=None,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=fresh_cursor(at=tz_now),
        new_light_samples=(),
        soil_moisture=None,
        temp_air=None,
        humidity_air=None,
        emergency_stop=False,
        feed_empty=False,
    )
    assert decision.shoot is False
    assert decision.reason_code == "irrigation_config_error"
    assert decision.failed is False


def test_e202_shot_belongs_to_window_where_it_started() -> None:
    """Кадр через полночь учитывается в окне старта (потолок того окна)."""
    tz = ZoneInfo(TZ)
    started = datetime(2026, 6, 1, 20, 0, tzinfo=tz)
    phase = PhaseTargets(
        phase_id=1,
        started_at=started,
        interval_sec=3600,
        duration_sec=60,
        on_time="20:00:00",
        off_time="02:00:00",
    )
    # 01:30 — ещё вчерашнее окно, начавшееся в 20:00.
    now = datetime(2026, 6, 2, 1, 30, tzinfo=tz)
    window = resolve_light_window(phase=phase, now=now, tz=tz)
    assert window is not None
    assert window.start_local.hour == 20
    ceiling = daily_shot_ceiling(
        phase=phase,
        interval_sec=3600,
        now=now,
        tz=tz,
        window=window,
    )
    assert ceiling >= 1
