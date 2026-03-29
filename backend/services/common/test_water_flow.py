"""Tests for water_flow helper module."""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
from datetime import timedelta

from common.utils.time import utcnow

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.water_flow import (
    _load_system_authority_policy,
    check_water_level,
    check_flow,
    check_dry_run_protection,
    calculate_irrigation_volume,
    ensure_water_level_alert,
    ensure_no_flow_alert,
    WATER_LEVEL_LOW_THRESHOLD,
    MIN_FLOW_THRESHOLD,
)


@pytest.mark.asyncio
async def test_load_system_authority_policy_uses_builtin_fallback_for_pump_calibration():
    with patch("common.water_flow.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []

        result = await _load_system_authority_policy("pump_calibration")

    assert result["calibration_duration_min_sec"] == 1
    assert result["calibration_duration_max_sec"] == 120
    assert result["ml_per_sec_min"] == pytest.approx(0.01)
    assert result["ml_per_sec_max"] == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_check_water_level_normal():
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [{"value": 0.5}]

        is_ok, level = await check_water_level(1)

    assert is_ok is True
    assert level == 0.5


@pytest.mark.asyncio
async def test_check_water_level_low():
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [{"value": 0.15}]

        is_ok, level = await check_water_level(1)

    assert is_ok is False
    assert level == 0.15


@pytest.mark.asyncio
async def test_check_water_level_no_data():
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = []

        is_ok, level = await check_water_level(1)

    assert is_ok is True
    assert level is None


@pytest.mark.asyncio
async def test_check_water_level_zero_value_is_bypassed_in_active_irrigation_phase():
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [{"value": 0.0}]

        is_ok, level = await check_water_level(1, workflow_phase="irrigating")

    assert is_ok is True
    assert level == 0.0


@pytest.mark.asyncio
async def test_check_water_level_zero_value_is_not_bypassed_outside_active_irrigation_phase():
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [{"value": 0.0}]

        is_ok, level = await check_water_level(1, workflow_phase="idle")

    assert is_ok is False
    assert level == 0.0


@pytest.mark.asyncio
async def test_check_water_level_prefers_clean_tank_labels_in_query():
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [{"value": 0.5}]

        await check_water_level(2)

    sql = mock_fetch.call_args.args[0]
    assert "LIKE '%clean%'" in sql
    assert "LIKE '%fresh%'" in sql
    assert "LIKE '%solution%'" in sql
    assert "LIKE '%min%'" in sql


@pytest.mark.asyncio
async def test_check_flow_normal():
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [{"value": 2.5}]

        is_ok, flow = await check_flow(1, min_flow=0.1)

    assert is_ok is True
    assert flow == 2.5


@pytest.mark.asyncio
async def test_check_flow_low():
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [{"value": 0.05}]

        is_ok, flow = await check_flow(1, min_flow=0.1)

    assert is_ok is False
    assert flow == 0.05


@pytest.mark.asyncio
async def test_check_flow_no_data():
    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = []

        is_ok, flow = await check_flow(1, min_flow=0.1)

    assert is_ok is False
    assert flow is None


@pytest.mark.asyncio
async def test_check_dry_run_protection_safe():
    pump_start_time = utcnow() - timedelta(seconds=1)

    with patch("common.water_flow.check_flow") as mock_check_flow:
        is_safe, error = await check_dry_run_protection(1, pump_start_time, min_flow=0.1)

    assert is_safe is True
    assert error is None
    mock_check_flow.assert_not_called()


@pytest.mark.asyncio
async def test_check_dry_run_protection_no_flow():
    pump_start_time = utcnow() - timedelta(seconds=5)

    with patch("common.water_flow.check_flow") as mock_check_flow, \
         patch("common.water_flow.create_zone_event") as mock_event:
        mock_check_flow.return_value = (False, 0.0)

        is_safe, error = await check_dry_run_protection(1, pump_start_time, min_flow=0.1)

    assert is_safe is False
    assert error is not None
    assert "NO_FLOW" in error
    mock_event.assert_called_once()


@pytest.mark.asyncio
async def test_check_dry_run_protection_flow_ok():
    pump_start_time = utcnow() - timedelta(seconds=5)

    with patch("common.water_flow.check_flow") as mock_check_flow:
        mock_check_flow.return_value = (True, 2.0)

        is_safe, error = await check_dry_run_protection(1, pump_start_time, min_flow=0.1)

    assert is_safe is True
    assert error is None


@pytest.mark.asyncio
async def test_calculate_irrigation_volume():
    start_time = utcnow() - timedelta(minutes=10)
    end_time = utcnow()

    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"value": 2.0, "ts": start_time},
            {"value": 2.0, "ts": end_time},
        ]

        volume = await calculate_irrigation_volume(1, start_time, end_time)

    assert volume > 0
    assert volume == pytest.approx(20.0, rel=0.1)


@pytest.mark.asyncio
async def test_calculate_irrigation_volume_no_data():
    start_time = utcnow() - timedelta(minutes=10)
    end_time = utcnow()

    with patch("common.water_flow.fetch") as mock_fetch:
        mock_fetch.return_value = []

        volume = await calculate_irrigation_volume(1, start_time, end_time)

    assert volume == 0.0


@pytest.mark.asyncio
async def test_ensure_water_level_alert_low():
    with patch("common.water_flow.create_zone_event") as mock_event, \
         patch("common.water_flow.create_alert") as mock_create_alert:
        mock_create_alert.return_value = {"id": 1}
        mock_event.return_value = None

        await ensure_water_level_alert(1, 0.15)

    assert mock_create_alert.call_count >= 1
    assert mock_event.call_count >= 1


@pytest.mark.asyncio
async def test_ensure_water_level_alert_normal():
    with patch("common.water_flow.create_zone_event") as mock_event, \
         patch("common.water_flow.create_alert") as mock_create_alert:
        await ensure_water_level_alert(1, 0.5)

    mock_create_alert.assert_not_called()
    mock_event.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_no_flow_alert():
    with patch("common.water_flow.create_zone_event") as mock_event, \
         patch("common.water_flow.create_alert") as mock_create_alert:
        mock_create_alert.return_value = {"id": 1}
        mock_event.return_value = None

        await ensure_no_flow_alert(1, 0.05, min_flow=0.1)

    assert mock_create_alert.call_count >= 1
    assert mock_event.call_count == 0


def test_water_flow_constants_are_canonical():
    assert WATER_LEVEL_LOW_THRESHOLD == pytest.approx(0.2)
    assert MIN_FLOW_THRESHOLD == pytest.approx(0.1)
