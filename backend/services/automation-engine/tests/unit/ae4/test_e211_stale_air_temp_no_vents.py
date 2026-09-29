"""E211: нет свежей температуры воздуха — список команд форточек пуст.

Один wake на greenhouse_id (не N по числу зон) — рядом.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from ae4.domain.planting import TelemetrySample
from ae4.infrastructure.climate_wake import wake_greenhouse_climate_ticks
from ae4.leaf_climate.air_temp import has_fresh_air_temperature
from ae4.leaf_climate.decision import compute_climate_decision
from ae4.leaf_climate.vent_commands import list_vent_commands


def _exec(**kwargs: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "decision_interval_sec": 900,
        "min_command_interval_sec": 0,
        "max_step_pct": 25,
        "position_deadband_pct": 0,
        "day_min_open_pct": 0,
        "day_max_open_pct": 100,
        "night_min_open_pct": 0,
        "night_max_open_pct": 20,
        "day_base_open_pct": 10,
        "night_base_open_pct": 5,
        "daylight_lux_threshold": 50,
        "temp_full_open_delta_c": 6,
        "rh_full_open_delta_pct": 20,
        "cold_guard_margin_c": 1,
        "cold_guard_max_open_pct": 10,
        "outside_hotter_gain": 1.0,
        "outside_wetter_gain": 1.0,
        "wind_reduce_threshold_ms": 8,
        "wind_close_threshold_ms": 12,
        "wind_reduce_windward_max_pct": 25,
        "wind_reduce_leeward_max_pct": 50,
        "wind_storm_windward_max_pct": 0,
        "wind_storm_leeward_max_pct": 10,
        "rain_windward_position_pct": 0,
        "rain_leeward_position_pct": 10,
        "rain_unknown_direction_max_pct": 5,
        "overheat_emergency_temp_c": 38,
        "emergency_open_pct": 100,
        "greenhouse_targets": {
            "temp_min_c": 18,
            "temp_max_c": 28,
            "humidity_min_pct": 40,
            "humidity_max_pct": 70,
        },
    }
    base.update(kwargs)
    return base


def _vents() -> dict[str, dict[str, Any]]:
    return {
        "roof_vent_left": {
            "node_uid": "nd-left",
            "zone_id": 10,
            "greenhouse_uid": "gh-1",
        },
        "roof_vent_right": {
            "node_uid": "nd-right",
            "zone_id": 10,
            "greenhouse_uid": "gh-1",
        },
    }


def test_e211_no_fresh_air_temp_command_list_empty() -> None:
    now = datetime(2026, 9, 24, 12, 0, 0)
    stale = TelemetrySample(
        metric_type="TEMPERATURE",
        channel="air_temp_c",
        value=32.0,
        ts=now - timedelta(hours=2),
    )
    solution = TelemetrySample(
        metric_type="TEMPERATURE",
        channel="solution_temp_c",
        value=22.0,
        ts=now,
    )
    assert (
        has_fresh_air_temperature(
            samples=(stale, solution),
            now=now,
            telemetry_max_age_sec=300,
        )
        is False
    )
    assert (
        has_fresh_air_temperature(
            samples=(solution,),
            now=now,
            telemetry_max_age_sec=300,
        )
        is False
    )
    assert (
        has_fresh_air_temperature(
            samples=(stale,),
            now=now,
            telemetry_max_age_sec=None,
        )
        is False
    )

    decision = compute_climate_decision(
        execution=_exec(),
        control_mode="auto",
        manual_override=None,
        inside_temp_median=None,
        inside_temp_max=None,
        inside_rh_max=None,
        outside_temp=15.0,
        outside_humidity=40.0,
        wind_speed=1.0,
        wind_direction_deg=None,
        rain_detected=False,
        outside_light_lux=200.0,
        schedule_day=True,
        weather_fresh=True,
        inside_fresh=False,
        current_left_pct=0,
        current_right_pct=0,
        now_ts=1_000_000.0,
        last_command_ts=None,
    )
    assert decision.suppress_commands is True
    assert decision.command_sides == ()
    assert decision.decision_reason == "air_temp_stale"

    commands = list_vent_commands(
        decision=decision,
        vents=_vents(),
        current_left_pct=0,
        current_right_pct=0,
        max_step_pct=25,
    )
    assert commands == []


def test_e211_fresh_air_temp_can_produce_commands() -> None:
    now = datetime(2026, 9, 24, 12, 0, 0)
    fresh = TelemetrySample(
        metric_type="TEMPERATURE",
        channel="temperature",
        value=32.0,
        ts=now - timedelta(seconds=10),
    )
    assert (
        has_fresh_air_temperature(
            samples=(fresh,),
            now=now,
            telemetry_max_age_sec=300,
        )
        is True
    )
    decision = compute_climate_decision(
        execution=_exec(),
        control_mode="auto",
        manual_override=None,
        inside_temp_median=32.0,
        inside_temp_max=32.0,
        inside_rh_max=50.0,
        outside_temp=15.0,
        outside_humidity=40.0,
        wind_speed=1.0,
        wind_direction_deg=None,
        rain_detected=False,
        outside_light_lux=200.0,
        schedule_day=True,
        weather_fresh=True,
        inside_fresh=True,
        current_left_pct=0,
        current_right_pct=0,
        now_ts=1_000_000.0,
        last_command_ts=None,
    )
    commands = list_vent_commands(
        decision=decision,
        vents=_vents(),
        current_left_pct=0,
        current_right_pct=0,
        max_step_pct=25,
    )
    assert commands
    assert all(c.channel.startswith("roof_vent_") for c in commands)


@pytest.mark.asyncio
async def test_e211_one_wake_per_greenhouse_not_per_zone() -> None:
    """Несколько зон одной теплицы → один POST start-climate-tick."""
    posts: list[str] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        posts.append(str(request.url.path))
        return httpx.Response(200, json={"status": "accepted"})

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://ae.test") as client:
        woken = await wake_greenhouse_climate_ticks(
            greenhouse_ids=[7, 7, 7, 9, 7],
            now=datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc),
            base_url="http://ae.test",
            token="t",
            client=client,
        )

    assert woken == [7, 9]
    assert posts == [
        "/greenhouses/7/start-climate-tick",
        "/greenhouses/9/start-climate-tick",
    ]
    assert posts.count("/greenhouses/7/start-climate-tick") == 1
