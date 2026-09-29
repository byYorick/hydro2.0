"""E233: разные единицы света или редкие пробы — интеграл unseen, не ноль-цель."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ae4.domain.planting import LightIntegralCursor
from ae4.domain.water_demand import advance_light_integral
from tests.unit.ae4.conftest_wave1 import TZ, later, sample


def test_e233_unit_mismatch_integral_unseen() -> None:
    tz = ZoneInfo(TZ)
    started = datetime(2026, 6, 1, 8, 0, tzinfo=tz)
    now = later(started, minutes=10)
    cursor = LightIntegralCursor(
        accumulated=0.0,
        last_accounted_ts=started,
        unit="PPFD·s",
        status="ok",
        last_value=10.0,
    )
    advanced = advance_light_integral(
        cursor=cursor,
        samples=(
            sample(
                metric_type="LIGHT_INTENSITY",
                channel="light",
                value=100.0,
                ts=later(started, minutes=1),
                unit="lux",
            ),
        ),
        now=now,
        telemetry_max_age_sec=600,
        target_unit="PPFD·s",
        phase_started_at=started,
    )
    assert advanced.status == "unseen"
    assert advanced.accumulated == 0.0


def test_e233_sparse_samples_integral_unseen_not_zero_target() -> None:
    tz = ZoneInfo(TZ)
    started = datetime(2026, 6, 1, 8, 0, tzinfo=tz)
    now = later(started, hours=2)
    cursor = LightIntegralCursor(
        accumulated=50.0,
        last_accounted_ts=started,
        unit="lux·s",
        status="ok",
        last_value=10.0,
    )
    advanced = advance_light_integral(
        cursor=cursor,
        samples=(
            sample(
                metric_type="LIGHT_INTENSITY",
                channel="light",
                value=10.0,
                ts=later(started, hours=1, minutes=30),
                unit="lux·s",
            ),
        ),
        now=now,
        telemetry_max_age_sec=600,
        target_unit="lux·s",
        phase_started_at=started,
    )
    assert advanced.status == "unseen"
    # unseen не выдаёт «цель достигнута нулём».
    assert advanced.accumulated == 0.0
