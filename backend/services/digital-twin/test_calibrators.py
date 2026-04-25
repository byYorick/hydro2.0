"""Unit-тесты Phase D: tank_calibrator, storage, runner, drift."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from calibrators.drift import DEFAULT_DRIFT_THRESHOLDS, compute_drift_for_zone
from calibrators.runner import calibrate_zone, calibrate_zone_with_persist
from calibrators.storage import (
    list_active_params,
    list_versions,
    persist_param_group,
)
from calibrators.tank import (
    _estimate_evaporation,
    _estimate_fill_rate,
    calibrate_tank_model,
)


NOW = datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)


# --- TankCalibrator: estimators ------------------------------------------


def test_estimate_fill_rate_returns_none_for_empty_inputs():
    rate, n = _estimate_fill_rate([], [])
    assert rate is None and n == 0


def test_estimate_fill_rate_simple_episode():
    on_ts = NOW - timedelta(hours=2)
    latch_ts = NOW - timedelta(hours=1)  # 1h fill
    rate, n = _estimate_fill_rate(
        valve_events=[{"ts": on_ts, "channel": "valve_clean_fill", "state": True}],
        level_transitions=[{"ts": latch_ts, "state": 1}],
    )
    # 80л за 1ч → 80 l/час
    assert n == 1
    assert rate == pytest.approx(80.0, abs=1e-3)


def test_estimate_fill_rate_skips_short_episodes():
    on_ts = NOW
    latch_ts = NOW + timedelta(seconds=30)  # < 60s — skip
    rate, n = _estimate_fill_rate(
        valve_events=[{"ts": on_ts, "channel": "valve_clean_fill", "state": True}],
        level_transitions=[{"ts": latch_ts, "state": 1}],
    )
    assert rate is None
    assert n == 0


@pytest.mark.asyncio
async def test_calibrate_tank_model_returns_defaults_when_no_data():
    with patch("calibrators.tank.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        result = await calibrate_tank_model(zone_id=1, days=7)
    assert result.params["source_clean_l_per_hour"] == 60.0
    assert result.params["evaporation_l_per_hour"] == 0.05
    assert "clean_fill_rate" in " ".join(result.notes)


@pytest.mark.asyncio
async def test_estimate_evaporation_returns_none_when_no_volume_channel():
    with patch("calibrators.tank.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        rate, n = await _estimate_evaporation(zone_id=1, cutoff=NOW)
    assert rate is None
    assert n == 0


@pytest.mark.asyncio
async def test_estimate_evaporation_uses_volume_drops():
    rows = [
        {"ts": NOW - timedelta(hours=4), "value": 100.0},
        {"ts": NOW - timedelta(hours=3), "value": 99.5},
        {"ts": NOW - timedelta(hours=2), "value": 99.0},
        {"ts": NOW - timedelta(hours=1), "value": 98.6},
    ]
    with patch("calibrators.tank.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = rows
        rate, n = await _estimate_evaporation(zone_id=1, cutoff=NOW)
    assert n == 3
    assert 0.4 <= rate <= 0.6   # ~0.5 l/h в среднем


# --- Storage --------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_param_group_inserts_first_version():
    """Активной версии нет — INSERT с version=1, без UPDATE."""
    with patch("calibrators.storage.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("calibrators.storage.execute", new_callable=AsyncMock) as mock_exec:
        mock_fetch.return_value = []   # нет активной
        version = await persist_param_group(
            zone_id=42,
            param_group="tank",
            params={"source_clean_l_per_hour": 75.0},
            calibrated_from_start=NOW - timedelta(days=7),
            calibrated_from_end=NOW,
            calibration_mae={"ph": 0.05},
            n_samples_used=12,
        )
    assert version == 1
    # Один execute — INSERT (без UPDATE)
    mock_exec.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_param_group_supersedes_active_version():
    """Активная версия есть — UPDATE superseded_at + INSERT version+1."""
    with patch("calibrators.storage.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("calibrators.storage.execute", new_callable=AsyncMock) as mock_exec:
        mock_fetch.return_value = [{"id": 99, "version": 3}]
        version = await persist_param_group(
            zone_id=42,
            param_group="ph",
            params={"correction_rate": 0.07},
            calibrated_from_start=NOW - timedelta(days=7),
            calibrated_from_end=NOW,
        )
    assert version == 4
    # Два execute: UPDATE superseded_at, INSERT new
    assert mock_exec.await_count == 2


@pytest.mark.asyncio
async def test_persist_param_group_rejects_unknown_group():
    with pytest.raises(ValueError):
        await persist_param_group(
            zone_id=1, param_group="weather",
            params={"x": 1.0},
            calibrated_from_start=NOW, calibrated_from_end=NOW,
        )


@pytest.mark.asyncio
async def test_persist_param_group_rejects_empty_params():
    with pytest.raises(ValueError):
        await persist_param_group(
            zone_id=1, param_group="ph", params={},
            calibrated_from_start=NOW, calibrated_from_end=NOW,
        )


@pytest.mark.asyncio
async def test_list_active_params_returns_decoded_jsonb():
    with patch("calibrators.storage.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {
                "param_group": "tank",
                "params": {"source_clean_l_per_hour": 55.0},
                "version": 2,
                "calibrated_at": NOW,
                "calibration_mae": None,
                "n_samples_used": 5,
            },
            {
                # params как строка (если JSONB пришёл сериализованным)
                "param_group": "ph",
                "params": '{"natural_drift": 0.012}',
                "version": 1,
                "calibrated_at": NOW,
                "calibration_mae": '{"ph": 0.04}',
                "n_samples_used": 100,
            },
        ]
        result = await list_active_params(zone_id=42)
    assert "tank" in result
    assert result["tank"]["params"]["source_clean_l_per_hour"] == 55.0
    assert result["ph"]["params"]["natural_drift"] == 0.012
    assert result["ph"]["calibration_mae"] == {"ph": 0.04}


@pytest.mark.asyncio
async def test_list_versions_returns_history():
    with patch("calibrators.storage.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {
                "version": 2,
                "calibrated_at": NOW,
                "superseded_at": None,
                "calibration_mae": None,
                "n_samples_used": 12,
            },
            {
                "version": 1,
                "calibrated_at": NOW - timedelta(days=7),
                "superseded_at": NOW,
                "calibration_mae": None,
                "n_samples_used": 7,
            },
        ]
        out = await list_versions(zone_id=1, param_group="tank")
    assert len(out) == 2
    assert out[0]["version"] == 2
    assert out[0]["superseded_at"] is None
    assert out[1]["superseded_at"] is not None


# --- Runner ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_calibrate_zone_combines_all_models():
    """calibrate_zone() агрегирует ph/ec/climate/tank."""
    with patch("calibrators.runner.calibrate_ph_model", new_callable=AsyncMock) as ph, \
         patch("calibrators.runner.calibrate_ec_model", new_callable=AsyncMock) as ec, \
         patch("calibrators.runner.calibrate_climate_model", new_callable=AsyncMock) as cl, \
         patch("calibrators.runner.calibrate_tank_model", new_callable=AsyncMock) as tank:
        ph.return_value = {"correction_rate": 0.05}
        ec.return_value = {"evaporation_rate": 0.02}
        cl.return_value = {"heat_loss_rate": 0.4}
        from calibrators.tank import TankCalibrationResult
        tank.return_value = TankCalibrationResult(
            params={"source_clean_l_per_hour": 70.0},
            n_samples_used=3,
            notes=[],
        )
        result = await calibrate_zone(zone_id=1, days=7)
    assert "ph" in result["models"]
    assert "ec" in result["models"]
    assert "climate" in result["models"]
    assert "tank" in result["models"]
    assert result["models"]["tank"]["source_clean_l_per_hour"] == 70.0


@pytest.mark.asyncio
async def test_calibrate_zone_with_persist_writes_each_group():
    """Каждая непустая группа пишется в zone_dt_params."""
    with patch("calibrators.runner.calibrate_ph_model", new_callable=AsyncMock) as ph, \
         patch("calibrators.runner.calibrate_ec_model", new_callable=AsyncMock) as ec, \
         patch("calibrators.runner.calibrate_climate_model", new_callable=AsyncMock) as cl, \
         patch("calibrators.runner.calibrate_tank_model", new_callable=AsyncMock) as tank, \
         patch("calibrators.runner.persist_param_group", new_callable=AsyncMock) as persist:
        ph.return_value = {"correction_rate": 0.05}
        ec.return_value = {"evaporation_rate": 0.02}
        cl.return_value = {"heat_loss_rate": 0.4}
        from calibrators.tank import TankCalibrationResult
        tank.return_value = TankCalibrationResult(
            params={"source_clean_l_per_hour": 70.0},
            n_samples_used=3, notes=[],
        )
        persist.side_effect = [1, 1, 1, 1]
        result = await calibrate_zone_with_persist(zone_id=1, days=7)
    assert persist.await_count == 4
    persisted_groups = [p["param_group"] for p in result["persisted"]]
    assert sorted(persisted_groups) == sorted(["ph", "ec", "climate", "tank"])


# --- Drift monitor --------------------------------------------------------


@pytest.mark.asyncio
async def test_compute_drift_for_zone_no_drift():
    """MAE ниже threshold → drift_detected=False."""
    with patch("replay.replay_zone", new_callable=AsyncMock) as mock_replay:
        mock_replay.return_value = {
            "points": [{"t": 0}],
            "commands_replayed": 5,
            "mae": {"ph": 0.05, "ec": 0.03, "temp_air": 0.5},
        }
        result = await compute_drift_for_zone(
            zone_id=1, from_ts=NOW, to_ts=NOW + timedelta(hours=2),
        )
    assert result["drift_detected"] is False
    assert result["drift_metrics"] == []
    assert result["thresholds"] == DEFAULT_DRIFT_THRESHOLDS


@pytest.mark.asyncio
async def test_compute_drift_for_zone_drift_detected():
    with patch("replay.replay_zone", new_callable=AsyncMock) as mock_replay:
        mock_replay.return_value = {
            "points": [],
            "commands_replayed": 0,
            "mae": {"ph": 0.5, "ec": 0.05},   # ph выше threshold (0.20)
        }
        result = await compute_drift_for_zone(
            zone_id=1, from_ts=NOW, to_ts=NOW + timedelta(hours=2),
        )
    assert result["drift_detected"] is True
    assert "ph" in result["drift_metrics"]
    assert "ec" not in result["drift_metrics"]


@pytest.mark.asyncio
async def test_compute_drift_for_zone_custom_thresholds():
    with patch("replay.replay_zone", new_callable=AsyncMock) as mock_replay:
        mock_replay.return_value = {
            "points": [],
            "commands_replayed": 0,
            "mae": {"ph": 0.05},
        }
        result = await compute_drift_for_zone(
            zone_id=1, from_ts=NOW, to_ts=NOW + timedelta(hours=2),
            thresholds={"ph": 0.01},   # очень строгий
        )
    assert result["drift_detected"] is True
    assert "ph" in result["drift_metrics"]
