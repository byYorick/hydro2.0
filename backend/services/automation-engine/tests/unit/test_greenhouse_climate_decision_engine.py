from ae3lite.greenhouse_climate.decision_engine import compute_climate_decision
from ae3lite.greenhouse_climate import run_tick
from datetime import datetime, timedelta, timezone

import pytest


def _exec(**kwargs):
    base = {
        "decision_interval_sec": 900,
        "min_command_interval_sec": 0,
        "max_step_pct": 25,
        "position_deadband_pct": 0,
        "sensor_freshness_sec": 1200,
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
        "fallback_open_pct": 5,
        "greenhouse_targets": {
            "temp_min_c": 18,
            "temp_max_c": 28,
            "humidity_min_pct": 40,
            "humidity_max_pct": 70,
        },
    }
    base.update(kwargs)
    return base


def test_high_temperature_opens_more_than_base() -> None:
    ex = _exec()
    d = compute_climate_decision(
        execution=ex,
        control_mode="auto",
        manual_override=None,
        inside_temp_median=30.0,
        inside_temp_max=30.0,
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
    assert d.left_target_pct > 10
    assert d.suppress_commands is False


def test_manual_mode_suppresses_commands() -> None:
    ex = _exec()
    d = compute_climate_decision(
        execution=ex,
        control_mode="manual",
        manual_override=None,
        inside_temp_median=30.0,
        inside_temp_max=30.0,
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
    assert d.suppress_commands is True


def test_wind_storm_clamps_targets() -> None:
    ex = _exec(left_roof_normal_deg=0.0, right_roof_normal_deg=180.0)
    d = compute_climate_decision(
        execution=ex,
        control_mode="auto",
        manual_override=None,
        inside_temp_median=30.0,
        inside_temp_max=30.0,
        inside_rh_max=50.0,
        outside_temp=15.0,
        outside_humidity=40.0,
        wind_speed=15.0,
        wind_direction_deg=0.0,
        rain_detected=False,
        outside_light_lux=200.0,
        schedule_day=True,
        weather_fresh=True,
        inside_fresh=True,
        current_left_pct=50,
        current_right_pct=50,
        now_ts=1_000_000.0,
        last_command_ts=None,
    )
    assert d.left_target_pct <= 25
    assert d.right_target_pct <= 25


@pytest.mark.asyncio
async def test_sensor_snapshot_ignores_stale_values_and_reads_rain_label(monkeypatch) -> None:
    now = datetime.now(timezone.utc)

    async def fake_fetch(_sql, greenhouse_id):
        assert greenhouse_id == 1
        return [
            {
                "scope": "inside",
                "type": "TEMPERATURE",
                "label": "temperature",
                "last_value": 99.0,
                "last_ts": now - timedelta(hours=3),
                "last_quality": "GOOD",
            },
            {
                "scope": "inside",
                "type": "TEMPERATURE",
                "label": "temperature",
                "last_value": 24.0,
                "last_ts": now,
                "last_quality": "GOOD",
            },
            {
                "scope": "inside",
                "type": "TEMPERATURE",
                "label": "temperature",
                "last_value": 30.0,
                "last_ts": now,
                "last_quality": "GOOD",
            },
            {
                "scope": "inside",
                "type": "HUMIDITY",
                "label": "humidity",
                "last_value": 55.0,
                "last_ts": now,
                "last_quality": "GOOD",
            },
            {
                "scope": "inside",
                "type": "HUMIDITY",
                "label": "humidity",
                "last_value": 70.0,
                "last_ts": now,
                "last_quality": "GOOD",
            },
            {
                "scope": "outside",
                "type": "OTHER",
                "label": "rain_detected",
                "last_value": 1,
                "last_ts": now,
                "last_quality": "GOOD",
            },
        ]

    monkeypatch.setattr(run_tick, "fetch", fake_fetch)

    snap = await run_tick._sensor_snapshot(1, 1200)

    assert snap["inside_temp_median"] == 27.0
    assert snap["inside_temp_max"] == 30.0
    assert snap["inside_temp_min"] == 24.0
    assert snap["inside_temp_spread"] == 6.0
    assert snap["inside_rh_median"] == 62.5
    assert snap["inside_rh_spread"] == 15.0
    assert snap["rain_detected"] is True
    assert snap["inside_fresh"] is True
    assert snap["weather_fresh"] is False
    assert snap["outside_fresh"]["rain_detected"] is True


@pytest.mark.asyncio
async def test_sensor_snapshot_weather_fresh_when_core_outside_sensors_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Freshness считается относительно datetime.now(utc); фиксированная дата
    # быстро становится stale и ломает weather_fresh.
    now = datetime.now(timezone.utc)

    async def fake_fetch(_sql, _gh_id):
        return [
            {
                "scope": "outside",
                "type": "TEMPERATURE",
                "label": "outside_temp",
                "last_value": 22.0,
                "last_ts": now,
                "last_quality": "GOOD",
            },
            {
                "scope": "outside",
                "type": "HUMIDITY",
                "label": "outside_humidity",
                "last_value": 55.0,
                "last_ts": now,
                "last_quality": "GOOD",
            },
        ]

    monkeypatch.setattr(run_tick, "fetch", fake_fetch)

    snap = await run_tick._sensor_snapshot(1, 1200)

    assert snap["weather_fresh"] is True
    assert snap["outside_fresh"]["outside_temp"] is True
    assert snap["outside_fresh"]["rain_detected"] is False


def test_spread_alert_thresholds_detect_high_inside_sensor_spread() -> None:
    snap = {
        "inside_temp_spread": 5.0,
        "inside_rh_spread": 10.0,
    }
    alerts = run_tick._spread_alerts(snap, {"inside_temp_spread_alert_c": 4, "inside_rh_spread_alert_pct": 15})

    assert alerts == ["GREENHOUSE_CLIMATE_SENSOR_SPREAD_HIGH"]


@pytest.mark.asyncio
async def test_wait_command_terminal_skips_non_terminal_status(monkeypatch) -> None:
    statuses = iter(["SENT", "ACK", "DONE"])

    async def fake_fetch(_sql, cmd_id):
        assert cmd_id == "cmd-1"
        return [{"status": next(statuses)}]

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(run_tick, "fetch", fake_fetch)
    monkeypatch.setattr(run_tick.asyncio, "sleep", fake_sleep)

    assert await run_tick._wait_command_terminal("cmd-1", timeout_sec=5, poll_sec=0.1) == "DONE"


def test_semi_mode_always_suppresses_commands() -> None:
    ex = _exec()
    d = compute_climate_decision(
        execution=ex,
        control_mode="semi",
        manual_override=None,
        inside_temp_median=40.0,
        inside_temp_max=40.0,
        inside_rh_max=90.0,
        outside_temp=10.0,
        outside_humidity=30.0,
        wind_speed=0.0,
        wind_direction_deg=None,
        rain_detected=False,
        outside_light_lux=500.0,
        schedule_day=True,
        weather_fresh=True,
        inside_fresh=True,
        current_left_pct=0,
        current_right_pct=0,
        now_ts=1_000_000.0,
        last_command_ts=None,
    )
    assert d.suppress_commands is True


def test_stale_inside_and_weather_uses_fallback_open() -> None:
    ex = _exec(fallback_open_pct=12)
    d = compute_climate_decision(
        execution=ex,
        control_mode="auto",
        manual_override=None,
        inside_temp_median=None,
        inside_temp_max=None,
        inside_rh_max=None,
        outside_temp=None,
        outside_humidity=None,
        wind_speed=None,
        wind_direction_deg=None,
        rain_detected=False,
        outside_light_lux=None,
        schedule_day=True,
        weather_fresh=False,
        inside_fresh=False,
        current_left_pct=0,
        current_right_pct=0,
        now_ts=1_000_000.0,
        last_command_ts=None,
    )
    assert d.left_target_pct >= 12
    assert d.right_target_pct >= 12


def test_weather_stale_caps_schedule_and_temperature_demand() -> None:
    ex = _exec(weather_stale_max_open_pct=20, day_base_open_pct=30)
    d = compute_climate_decision(
        execution=ex,
        control_mode="auto",
        manual_override=None,
        inside_temp_median=36.0,
        inside_temp_max=36.0,
        inside_rh_max=50.0,
        outside_temp=None,
        outside_humidity=None,
        wind_speed=None,
        wind_direction_deg=None,
        rain_detected=False,
        outside_light_lux=None,
        schedule_day=True,
        weather_fresh=False,
        inside_fresh=True,
        current_left_pct=0,
        current_right_pct=0,
        now_ts=1_000_000.0,
        last_command_ts=None,
    )

    assert d.left_target_pct <= 20
    assert d.right_target_pct <= 20


def test_inside_stale_uses_fallback_even_when_weather_is_fresh() -> None:
    ex = _exec(fallback_open_pct=12, day_base_open_pct=40)
    d = compute_climate_decision(
        execution=ex,
        control_mode="auto",
        manual_override=None,
        inside_temp_median=None,
        inside_temp_max=None,
        inside_rh_max=None,
        outside_temp=20.0,
        outside_humidity=40.0,
        wind_speed=0.0,
        wind_direction_deg=None,
        rain_detected=False,
        outside_light_lux=500.0,
        schedule_day=True,
        weather_fresh=True,
        inside_fresh=False,
        current_left_pct=0,
        current_right_pct=0,
        now_ts=1_000_000.0,
        last_command_ts=None,
    )

    assert d.left_target_pct == 12
    assert d.right_target_pct == 12


def test_rain_with_direction_prefers_leeward_higher_cap() -> None:
    ex = _exec(
        left_roof_normal_deg=0.0,
        right_roof_normal_deg=180.0,
        rain_windward_position_pct=0,
        rain_leeward_position_pct=15,
    )
    d = compute_climate_decision(
        execution=ex,
        control_mode="auto",
        manual_override=None,
        inside_temp_median=30.0,
        inside_temp_max=30.0,
        inside_rh_max=50.0,
        outside_temp=20.0,
        outside_humidity=50.0,
        wind_speed=2.0,
        wind_direction_deg=0.0,
        rain_detected=True,
        outside_light_lux=200.0,
        schedule_day=True,
        weather_fresh=True,
        inside_fresh=True,
        current_left_pct=80,
        current_right_pct=80,
        now_ts=1_000_000.0,
        last_command_ts=None,
    )
    assert "rain_clamp" in d.decision_reason


def test_unknown_wind_direction_uses_symmetric_conservative_clamp() -> None:
    ex = _exec()
    d = compute_climate_decision(
        execution=ex,
        control_mode="auto",
        manual_override=None,
        inside_temp_median=40.0,
        inside_temp_max=40.0,
        inside_rh_max=50.0,
        outside_temp=20.0,
        outside_humidity=40.0,
        wind_speed=15.0,
        wind_direction_deg=None,
        rain_detected=False,
        outside_light_lux=200.0,
        schedule_day=True,
        weather_fresh=True,
        inside_fresh=True,
        current_left_pct=50,
        current_right_pct=50,
        now_ts=1_000_000.0,
        last_command_ts=None,
    )

    assert d.left_target_pct == d.right_target_pct


def test_deadband_suppresses_only_unchanged_side() -> None:
    ex = _exec(position_deadband_pct=5, max_step_pct=100)
    d = compute_climate_decision(
        execution=ex,
        control_mode="auto",
        manual_override=None,
        inside_temp_median=31.0,
        inside_temp_max=31.0,
        inside_rh_max=50.0,
        outside_temp=20.0,
        outside_humidity=40.0,
        wind_speed=0.0,
        wind_direction_deg=None,
        rain_detected=False,
        outside_light_lux=200.0,
        schedule_day=True,
        weather_fresh=True,
        inside_fresh=True,
        current_left_pct=52,
        current_right_pct=10,
        now_ts=1_000_000.0,
        last_command_ts=None,
    )

    assert "right" in d.command_sides
    assert "left" not in d.command_sides
    assert d.suppress_commands is False


def _decision(**kwargs):
    params = {
        "execution": _exec(),
        "control_mode": "auto",
        "manual_override": None,
        "inside_temp_median": 30.0,
        "inside_temp_max": 30.0,
        "inside_rh_max": 50.0,
        "outside_temp": 15.0,
        "outside_humidity": 40.0,
        "wind_speed": 1.0,
        "wind_direction_deg": None,
        "rain_detected": False,
        "outside_light_lux": 200.0,
        "schedule_day": True,
        "weather_fresh": True,
        "inside_fresh": True,
        "current_left_pct": 0,
        "current_right_pct": 0,
        "now_ts": 1_000_000.0,
        "last_command_ts": None,
    }
    params.update(kwargs)
    return compute_climate_decision(**params)


def test_without_vpd_targets_keeps_previous_open_percent() -> None:
    # Прежний вход test_high_temperature: temp_open ≈ 33.3, шаг 25 → 25.
    # Целей VPD нет, наружный воздух холоднее — проценты не сдвигаются.
    d = _decision()
    assert d.left_target_pct == 25
    assert d.right_target_pct == 25
    assert d.factors["air_vpd_kpa"] == pytest.approx(2.122, abs=0.05)
    assert d.factors["dew_point_c"] == pytest.approx(18.44, abs=0.2)
    assert d.factors["inside_vapor_pressure_kpa"] == pytest.approx(2.122, abs=0.05)
    assert d.factors["outside_vapor_pressure_kpa"] == pytest.approx(0.682, abs=0.05)
    assert d.factors.get("moisture_vent_suppressed") is not True

    wide = _decision(execution=_exec(max_step_pct=100))
    assert wide.left_target_pct == 33
    assert wide.right_target_pct == 33


def test_air_vpd_and_dew_point_at_25c_60rh() -> None:
    # 25 °C / 60 %: VPD ≈ 1.267 кПа, точка росы ≈ 16.70 °C. Допуск 0.05 кПа / 0.2 °C.
    d = _decision(
        execution=_exec(max_step_pct=100),
        inside_temp_median=25.0,
        inside_temp_max=25.0,
        inside_rh_max=60.0,
        outside_temp=15.0,
        outside_humidity=40.0,
    )
    assert d.factors["air_vpd_kpa"] == pytest.approx(1.267, abs=0.05)
    assert d.factors["dew_point_c"] == pytest.approx(16.70, abs=0.2)
    assert d.factors["inside_vapor_pressure_kpa"] == pytest.approx(1.901, abs=0.05)
    assert d.factors["outside_vapor_pressure_kpa"] == pytest.approx(0.682, abs=0.05)
    assert d.left_target_pct == 10
    assert d.right_target_pct == 10


def test_missing_temperature_or_rh_omits_vpd_keys() -> None:
    no_rh = _decision(inside_rh_max=None)
    assert "air_vpd_kpa" not in no_rh.factors
    assert "dew_point_c" not in no_rh.factors
    assert "inside_vapor_pressure_kpa" not in no_rh.factors
    assert no_rh.factors["outside_vapor_pressure_kpa"] == pytest.approx(0.682, abs=0.05)

    no_temp = _decision(inside_temp_median=None, inside_temp_max=None)
    assert "air_vpd_kpa" not in no_temp.factors
    assert "dew_point_c" not in no_temp.factors
    assert "inside_vapor_pressure_kpa" not in no_temp.factors

    stale = _decision(inside_fresh=False)
    assert "air_vpd_kpa" not in stale.factors
    assert "dew_point_c" not in stale.factors
    assert "inside_vapor_pressure_kpa" not in stale.factors

    outside_half = _decision(outside_humidity=None)
    assert "outside_vapor_pressure_kpa" not in outside_half.factors
    assert "air_vpd_kpa" in outside_half.factors


def test_rh_zero_does_not_raise_and_does_not_fake_zero_vpd() -> None:
    d = _decision(
        inside_temp_median=20.0,
        inside_temp_max=20.0,
        inside_rh_max=0.0,
        outside_temp=18.0,
        outside_humidity=0.0,
    )
    assert d.factors["air_vpd_kpa"] == pytest.approx(2.315, abs=0.05)
    assert d.factors["air_vpd_kpa"] > 0.0
    assert d.factors["dew_point_c"] == pytest.approx(-37.71, abs=0.2)
    assert "outside_vapor_pressure_kpa" in d.factors
    assert d.factors["outside_vapor_pressure_kpa"] > 0.0


def test_dry_air_zeros_only_humidity_branch() -> None:
    # 30 °C / 95 %: влажностная добавка 100, temp_open ≈ 33.3, VPD ≈ 0.212 > 0.15.
    targets = {
        "temp_min_c": 18,
        "temp_max_c": 28,
        "humidity_min_pct": 40,
        "humidity_max_pct": 70,
        "vpd_min_kpa": 0.05,
        "vpd_max_kpa": 0.15,
    }
    common = {
        "execution": _exec(max_step_pct=100, greenhouse_targets=targets),
        "inside_temp_median": 30.0,
        "inside_temp_max": 30.0,
        "inside_rh_max": 95.0,
        "outside_temp": 15.0,
        "outside_humidity": 40.0,
    }
    without = _decision(execution=_exec(max_step_pct=100), **{k: v for k, v in common.items() if k != "execution"})
    assert without.left_target_pct == 100

    dry = _decision(**common)
    assert dry.factors["air_vpd_kpa"] == pytest.approx(0.212, abs=0.05)
    assert dry.left_target_pct == 33
    assert dry.right_target_pct == 33
    assert "humidity_high" not in dry.decision_reason
    assert "temp_high" in dry.decision_reason
    assert dry.factors.get("moisture_vent_suppressed") is not True


def test_low_vpd_raises_humidity_open_without_touching_temp() -> None:
    targets = {
        "temp_min_c": 18,
        "temp_max_c": 28,
        "humidity_min_pct": 40,
        "humidity_max_pct": 70,
        "vpd_min_kpa": 2.0,
        "vpd_max_kpa": 2.5,
    }
    d = _decision(
        execution=_exec(max_step_pct=100, greenhouse_targets=targets),
        inside_temp_median=25.0,
        inside_temp_max=25.0,
        inside_rh_max=50.0,
        outside_temp=10.0,
        outside_humidity=30.0,
    )
    assert d.factors["air_vpd_kpa"] == pytest.approx(1.584, abs=0.05)
    assert d.left_target_pct == 21
    assert d.right_target_pct == 21
    assert "temp_high" not in d.decision_reason
    assert "humidity_high" in d.decision_reason


def test_high_vpd_below_temp_min_does_not_zero_humidity() -> None:
    targets = {
        "temp_min_c": 18,
        "temp_max_c": 28,
        "humidity_min_pct": 40,
        "humidity_max_pct": 70,
        "vpd_min_kpa": 0.01,
        "vpd_max_kpa": 0.05,
    }
    d = _decision(
        execution=_exec(
            max_step_pct=100,
            day_base_open_pct=0,
            cold_guard_max_open_pct=80,
            greenhouse_targets=targets,
        ),
        inside_temp_median=16.0,
        inside_temp_max=16.0,
        inside_rh_max=95.0,
        outside_temp=10.0,
        outside_humidity=40.0,
    )
    assert d.factors["air_vpd_kpa"] > 0.05
    assert d.left_target_pct == 80
    assert d.right_target_pct == 80


def test_one_vpd_target_does_not_change_percent() -> None:
    targets = {
        "temp_min_c": 18,
        "temp_max_c": 28,
        "humidity_min_pct": 40,
        "humidity_max_pct": 70,
        "vpd_max_kpa": 0.15,
    }
    d = _decision(
        execution=_exec(max_step_pct=100, greenhouse_targets=targets),
        inside_rh_max=95.0,
    )
    assert d.left_target_pct == 100
    assert d.right_target_pct == 100


def test_warm_humid_outside_zeros_only_humidity_addition() -> None:
    targets = {
        "temp_min_c": 18,
        "temp_max_c": 28,
        "humidity_min_pct": 40,
        "humidity_max_pct": 70,
        "vpd_min_kpa": 0.2,
        "vpd_max_kpa": 1.0,
    }
    common = {
        "inside_temp_median": 32.0,
        "inside_temp_max": 32.0,
        "inside_rh_max": 90.0,
        "outside_temp": 33.0,
        "outside_humidity": 95.0,
    }
    plain = _decision(execution=_exec(max_step_pct=100), **common)
    assert plain.left_target_pct == 100
    assert plain.factors.get("moisture_vent_suppressed") is not True

    suppressed = _decision(execution=_exec(max_step_pct=100, greenhouse_targets=targets), **common)
    assert suppressed.factors["air_vpd_kpa"] == pytest.approx(0.475, abs=0.05)
    assert suppressed.factors["moisture_vent_suppressed"] is True
    assert suppressed.left_target_pct == 67
    assert suppressed.right_target_pct == 67
    assert "temp_high" in suppressed.decision_reason
    assert "humidity_high" not in suppressed.decision_reason


def test_stale_outside_air_does_not_suppress_humidity_or_publish_vapor() -> None:
    targets = {
        "temp_min_c": 18,
        "temp_max_c": 28,
        "humidity_min_pct": 40,
        "humidity_max_pct": 70,
        "vpd_min_kpa": 0.2,
        "vpd_max_kpa": 1.0,
    }
    common = {
        "inside_temp_median": 32.0,
        "inside_temp_max": 32.0,
        "inside_rh_max": 90.0,
        "outside_temp": 33.0,
        "outside_humidity": 95.0,
        "weather_fresh": False,
    }
    plain = _decision(execution=_exec(max_step_pct=100), **common)
    d = _decision(execution=_exec(max_step_pct=100, greenhouse_targets=targets), **common)
    assert d.factors.get("moisture_vent_suppressed") is not True
    assert "outside_vapor_pressure_kpa" not in d.factors
    assert d.left_target_pct == plain.left_target_pct
    assert d.right_target_pct == plain.right_target_pct


def test_emergency_overheat_opens_despite_humid_outside() -> None:
    targets = {
        "temp_min_c": 18,
        "temp_max_c": 28,
        "humidity_min_pct": 40,
        "humidity_max_pct": 70,
        "vpd_min_kpa": 0.2,
        "vpd_max_kpa": 1.0,
    }
    d = _decision(
        execution=_exec(max_step_pct=100, greenhouse_targets=targets),
        inside_temp_median=32.0,
        inside_temp_max=40.0,
        inside_rh_max=90.0,
        outside_temp=33.0,
        outside_humidity=95.0,
    )
    assert d.emergency_overheat is True
    assert d.factors.get("moisture_vent_suppressed") is not True
    assert d.left_target_pct == 100
    assert d.right_target_pct == 100
    assert "emergency_overheat" in d.decision_reason


def test_greenhouse_targets_keep_optional_vpd_pair() -> None:
    out = run_tick._greenhouse_targets(
        {
            "greenhouse_targets": {
                "temp_min_c": 18,
                "temp_max_c": 28,
                "humidity_min_pct": 40,
                "humidity_max_pct": 70,
                "vpd_min_kpa": 0.8,
                "vpd_max_kpa": 1.2,
            }
        }
    )
    assert out["vpd_min_kpa"] == 0.8
    assert out["vpd_max_kpa"] == 1.2

    bare = run_tick._greenhouse_targets(
        {
            "greenhouse_targets": {
                "temp_min_c": 18,
                "temp_max_c": 28,
                "humidity_min_pct": 40,
                "humidity_max_pct": 70,
            }
        }
    )
    assert "vpd_min_kpa" not in bare
    assert "vpd_max_kpa" not in bare
