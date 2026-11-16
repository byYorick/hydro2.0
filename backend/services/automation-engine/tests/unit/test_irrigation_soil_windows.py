from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.infrastructure.read_models.runtime_monitor_metric_windows import (
    RuntimeMonitorMetricWindows,
    RuntimeMonitorMetricWindowsPorts,
)
from test_irrigation_decision_audit_regressions import NOW


async def read_windows(*, sensors=None, rows=None):
    sensors = (
        sensors
        if sensors is not None
        else [dict(sensor_id=1, sensor_label="soil", unit="%", value=30, sample_ts=NOW, last_quality="GOOD")]
    )
    rows = rows if rows is not None else [dict(sensor_id=1, ts=NOW, value=30, quality="GOOD", metadata={})]
    conn = SimpleNamespace(fetch=AsyncMock(side_effect=[sensors, rows]))

    @asynccontextmanager
    async def acquire():
        yield conn

    component = RuntimeMonitorMetricWindows(
        RuntimeMonitorMetricWindowsPorts(
            age_sec=lambda ts: 0,
            normalize_timestamp=lambda ts: ts,
            read_metric_sensor=AsyncMock(),
            global_get_pool=AsyncMock(return_value=SimpleNamespace(acquire=acquire)),
        )
    )
    result = await component.read_metric_windows(
        zone_id=7,
        sensor_type="SOIL_MOISTURE",
        since_ts=NOW - timedelta(minutes=30),
        until_ts=NOW,
        telemetry_max_age_sec=600,
    )
    return result, conn


@pytest.mark.asyncio
@pytest.mark.parametrize("quality", ["BAD", "STUB"])
async def test_latest_bad_quality_invalidates_sensor_even_with_historical_good_values(quality):
    result, _ = await read_windows(sensors=[dict(sensor_id=1, value=30, sample_ts=NOW, last_quality=quality)])
    assert result["is_stale"] is True
    assert not result["sensor_windows"][0]["samples"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value,quality", [(None, "GOOD"), (-1, "GOOD"), (float('nan'), "GOOD"), (30, "BAD"), (30, "STUB")]
)
async def test_rejected_history_does_not_refresh_older_readings(value, quality):
    result, _ = await read_windows(
        rows=[
            dict(sensor_id=1, ts=NOW - timedelta(seconds=700), value=30, quality="GOOD"),
            dict(sensor_id=1, ts=NOW, value=value, quality=quality),
        ]
    )
    assert result["is_stale"] is True
    assert result["sensor_windows"][0]["latest_sample_ts"] == NOW - timedelta(seconds=700)


@pytest.mark.asyncio
async def test_future_measurement_cannot_authorize_irrigation():
    result, _ = await read_windows(rows=[dict(sensor_id=1, ts=NOW + timedelta(minutes=10), value=20, quality="GOOD")])
    assert result["is_stale"] is True
    assert not result["sensor_windows"][0]["samples"]


@pytest.mark.asyncio
async def test_timestamp_rounding_tolerance_does_not_block_a_live_sensor():
    result, _ = await read_windows(rows=[dict(sensor_id=1, ts=NOW + timedelta(seconds=1), value=20, quality="GOOD")])
    assert result["is_stale"] is False


@pytest.mark.asyncio
async def test_non_percentage_sensor_unit_is_not_compared_to_percentage_target():
    result, _ = await read_windows(
        sensors=[dict(sensor_id=1, unit="ratio", value=0.8, sample_ts=NOW, last_quality="GOOD")]
    )
    assert result["is_stale"] is True


@pytest.mark.asyncio
async def test_hundred_active_sensors_use_two_queries_not_hundred_and_one():
    result, conn = await read_windows(
        sensors=[dict(sensor_id=i, value=30, sample_ts=NOW, last_quality="GOOD") for i in range(1, 101)],
        rows=[dict(sensor_id=i, ts=NOW, value=30, quality="GOOD") for i in range(1, 101)],
    )
    assert len(result["sensor_windows"]) == 100
    assert result["is_stale"] is False
    assert conn.fetch.await_count == 2
