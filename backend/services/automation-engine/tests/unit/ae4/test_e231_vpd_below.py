"""E231: VPD ниже нормы — кадра нет; температура раствора в VPD не подставляется."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ae4.domain.water_demand import compute_vpd_kpa, evaluate_water_demand, is_solution_temp
from tests.unit.ae4.conftest_wave1 import TZ, fresh_cursor, later, phase, sample


def test_e231_vpd_below_min_blocks_shot() -> None:
    tz = ZoneInfo(TZ)
    started = datetime(2026, 6, 1, 8, 0, tzinfo=tz)
    now = later(started, hours=2)
    ph = phase(
        started_at=started,
        interval_sec=3600,
        duration_sec=60,
        vpd_min=1.5,
        vpd_max=2.5,
    )
    # Прохладно и влажно → низкий VPD.
    temp = sample(
        metric_type="TEMPERATURE",
        channel="temperature",
        value=18.0,
        ts=now,
        unit="C",
    )
    hum = sample(
        metric_type="HUMIDITY",
        channel="humidity",
        value=90.0,
        ts=now,
        unit="%",
    )
    vpd, status = compute_vpd_kpa(
        phase=ph,
        temp_air=temp,
        humidity_air=hum,
        now=now,
        telemetry_max_age_sec=300,
    )
    assert status == "ok"
    assert vpd is not None and vpd < 1.5

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
    assert decision.shoot is False
    assert decision.reason_code == "vpd_below_min"
    assert decision.failed is False


def test_e231_solution_temp_not_used_for_vpd() -> None:
    sol = sample(
        metric_type="TEMPERATURE",
        channel="solution_temp_c",
        value=25.0,
        ts=datetime(2026, 6, 1, 12, 0, tzinfo=ZoneInfo(TZ)),
        unit="C",
    )
    assert is_solution_temp(sol) is True
    ph = phase(vpd_min=0.5, vpd_max=1.5)
    vpd, status = compute_vpd_kpa(
        phase=ph,
        temp_air=sol,
        humidity_air=sample(
            metric_type="HUMIDITY",
            channel="humidity",
            value=50.0,
            ts=sol.ts,
            unit="%",
        ),
        now=sol.ts,
        telemetry_max_age_sec=300,
    )
    assert status == "unseen"
    assert vpd is None
