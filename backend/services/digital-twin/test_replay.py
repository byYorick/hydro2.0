"""Тесты replay endpoint (Phase B / B7)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from replay import (
    ReplayRequest,
    _compute_mae,
    _interpolate_actual,
    _load_commands,
    _load_initial_state,
    replay_zone,
)


FROM_TS = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
TO_TS = FROM_TS + timedelta(hours=2)


# --- helpers --------------------------------------------------------------


def test_interpolate_actual_returns_none_for_empty():
    assert _interpolate_actual([], 0.5) is None


def test_interpolate_actual_clamps_before_first():
    samples = [{"t": 1.0, "value": 6.0}, {"t": 2.0, "value": 6.4}]
    # До первого — возвращаем первое значение
    assert _interpolate_actual(samples, 0.0) == 6.0


def test_interpolate_actual_linear_between():
    samples = [{"t": 1.0, "value": 6.0}, {"t": 2.0, "value": 6.4}]
    assert _interpolate_actual(samples, 1.5) == pytest.approx(6.2, abs=1e-6)


def test_interpolate_actual_clamps_after_last():
    samples = [{"t": 1.0, "value": 6.0}, {"t": 2.0, "value": 6.4}]
    assert _interpolate_actual(samples, 5.0) == 6.4


def test_compute_mae_returns_per_metric():
    points = [
        {"t": 0.0, "ph": 6.0, "ec": 1.2, "temp_air": 22.0, "humidity_air": 60.0},
        {"t": 1.0, "ph": 6.2, "ec": 1.3, "temp_air": 22.0, "humidity_air": 60.0},
    ]
    actual = {
        "PH": [{"t": 0.0, "value": 6.0}, {"t": 1.0, "value": 6.4}],
        "EC": [{"t": 0.0, "value": 1.0}, {"t": 1.0, "value": 1.5}],
    }
    mae = _compute_mae(points, actual)
    assert mae["ph"] == pytest.approx((0.0 + 0.2) / 2, abs=1e-6)
    assert mae["ec"] == pytest.approx((0.2 + 0.2) / 2, abs=1e-6)
    # TEMPERATURE/HUMIDITY нет в actual → метрики нет
    assert "temp_air" not in mae


# --- DB readers (mocked) --------------------------------------------------


@pytest.mark.asyncio
async def test_load_initial_state_picks_latest_per_metric():
    with patch("replay.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {"metric_type": "PH", "value": 6.1},
            {"metric_type": "EC", "value": 1.3},
            {"metric_type": "GARBAGE", "value": 1.0},
        ]
        result = await _load_initial_state(zone_id=1, ts=FROM_TS)
    assert result == {"ph": 6.1, "ec": 1.3}


@pytest.mark.asyncio
async def test_load_commands_translates_to_relative_t_min():
    with patch("replay.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {
                "created_at": FROM_TS,
                "cmd": "set_relay",
                "channel": "valve_clean_fill",
                "params": {"state": True},
            },
            {
                "created_at": FROM_TS + timedelta(minutes=30),
                "cmd": "dose",
                "channel": "pump_a",
                "params": {"ml": 5.0},
            },
            {
                # NULL ts — пропускаем
                "created_at": None,
                "cmd": "dose",
                "channel": "pump_a",
                "params": {"ml": 5.0},
            },
        ]
        commands = await _load_commands(zone_id=1, from_ts=FROM_TS, to_ts=TO_TS)
    assert len(commands) == 2
    assert commands[0]["t_min"] == pytest.approx(0.0)
    assert commands[1]["t_min"] == pytest.approx(30.0)
    assert commands[1]["params"] == {"ml": 5.0}


# --- Replay logic ---------------------------------------------------------


@pytest.mark.asyncio
async def test_replay_zone_returns_points_with_volume_fields():
    request = ReplayRequest(
        zone_id=42,
        from_ts=FROM_TS,
        to_ts=TO_TS,
        step_minutes=30,
        include_actual=False,
    )

    with patch("replay._load_initial_state", new_callable=AsyncMock) as mock_init, \
         patch("main.get_zone_dt_params", new_callable=AsyncMock) as mock_params, \
         patch("replay._load_commands", new_callable=AsyncMock) as mock_cmds:
        mock_init.return_value = {"ph": 6.0, "ec": 1.2, "temp_air": 22.0}
        mock_params.return_value = {}
        mock_cmds.return_value = [
            {
                "t_min": 0.0,
                "cmd": "set_relay",
                "channel": "valve_clean_fill",
                "params": {"state": True},
            },
        ]
        result = await replay_zone(request)

    assert result["commands_replayed"] == 1
    assert len(result["points"]) == 4   # 2 часа / 30 минут
    assert "solution_volume_l" in result["points"][0]
    assert result["actual"] is None
    assert result["mae"] is None
    # valve_clean_fill включён → clean_volume растёт
    assert result["points"][-1]["clean_volume_l"] > result["points"][0]["clean_volume_l"]


@pytest.mark.asyncio
async def test_replay_zone_to_ts_must_be_greater_than_from_ts():
    request = ReplayRequest(
        zone_id=1,
        from_ts=TO_TS,
        to_ts=FROM_TS,
        step_minutes=5,
    )
    with pytest.raises(HTTPException) as exc:
        await replay_zone(request)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_replay_zone_rejects_too_long_intervals():
    request = ReplayRequest(
        zone_id=1,
        from_ts=FROM_TS,
        to_ts=FROM_TS + timedelta(days=31),
        step_minutes=60,
    )
    with pytest.raises(HTTPException) as exc:
        await replay_zone(request)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_replay_zone_with_include_actual_computes_mae():
    request = ReplayRequest(
        zone_id=42,
        from_ts=FROM_TS,
        to_ts=TO_TS,
        step_minutes=60,
        include_actual=True,
    )
    with patch("replay._load_initial_state", new_callable=AsyncMock) as mock_init, \
         patch("main.get_zone_dt_params", new_callable=AsyncMock) as mock_params, \
         patch("replay._load_commands", new_callable=AsyncMock) as mock_cmds, \
         patch("replay._load_actual_telemetry", new_callable=AsyncMock) as mock_actual:
        mock_init.return_value = {"ph": 6.0, "ec": 1.2}
        mock_params.return_value = {}
        mock_cmds.return_value = []
        mock_actual.return_value = {
            "PH": [{"t": 0.0, "value": 6.0}, {"t": 2.0, "value": 6.0}],
            "EC": [{"t": 0.0, "value": 1.2}, {"t": 2.0, "value": 1.2}],
        }
        result = await replay_zone(request)

    assert result["actual"] is not None
    assert result["mae"] is not None
    # ph и ec MAE присутствуют (сравнение по interpolated)
    assert "ph" in result["mae"]
    assert "ec" in result["mae"]
