"""Tests for alerts module."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from common.alerts import AlertSource, AlertCode, create_alert


@pytest.mark.asyncio
async def test_create_alert_with_all_fields():
    """Test creating alert with all fields when no existing alert."""
    with patch("common.alerts._publisher.raise_active", new_callable=AsyncMock) as mock_raise:
        mock_raise.return_value = True
        
        await create_alert(
            zone_id=1,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type="No water flow detected",
            details={"flow_value": 0.0, "min_flow": 1.0}
        )
        
        mock_raise.assert_called_once()
        call_args = mock_raise.call_args
        assert call_args.kwargs["zone_id"] == 1
        assert call_args.kwargs["source"] == AlertSource.BIZ.value
        assert call_args.kwargs["code"] == AlertCode.BIZ_NO_FLOW.value
        assert call_args.kwargs["alert_type"] == "No water flow detected"
        
        details = call_args.kwargs["details"]
        assert "last_seen_at" in details
        assert details["flow_value"] == 0.0
        assert details["min_flow"] == 1.0
        assert "dedupe_key" in details


@pytest.mark.asyncio
async def test_create_alert_without_details():
    """Test creating alert without details when no existing alert."""
    with patch("common.alerts._publisher.raise_active", new_callable=AsyncMock) as mock_raise:
        mock_raise.return_value = True
        
        await create_alert(
            zone_id=1,
            source=AlertSource.INFRA.value,
            code=AlertCode.INFRA_MQTT_DOWN.value,
            type="MQTT connection lost"
        )
        
        mock_raise.assert_called_once()
        details = mock_raise.call_args.kwargs["details"]
        assert "last_seen_at" in details


@pytest.mark.asyncio
async def test_create_alert_with_null_zone_id():
    """Test creating alert with null zone_id (global alert)."""
    with patch("common.alerts._publisher.raise_active", new_callable=AsyncMock) as mock_raise:
        mock_raise.return_value = True
        
        await create_alert(
            zone_id=None,
            source=AlertSource.INFRA.value,
            code=AlertCode.INFRA_SERVICE_DOWN.value,
            type="Service unavailable"
        )
        
        mock_raise.assert_called_once()
        assert mock_raise.call_args.kwargs["zone_id"] is None


def test_alert_source_enum():
    """Test AlertSource enum values."""
    assert AlertSource.BIZ.value == "biz"
    assert AlertSource.INFRA.value == "infra"


def test_alert_code_enum():
    """Test AlertCode enum values."""
    assert AlertCode.BIZ_NO_FLOW.value == "biz_no_flow"
    assert AlertCode.BIZ_OVERCURRENT.value == "biz_overcurrent"
    assert AlertCode.BIZ_DRY_RUN.value == "biz_dry_run"
    assert AlertCode.BIZ_PUMP_STUCK_ON.value == "biz_pump_stuck_on"
    assert AlertCode.BIZ_HIGH_PH.value == "biz_high_ph"
    assert AlertCode.BIZ_LOW_PH.value == "biz_low_ph"
    assert AlertCode.BIZ_HIGH_EC.value == "biz_high_ec"
    assert AlertCode.BIZ_LOW_EC.value == "biz_low_ec"
    assert AlertCode.BIZ_HIGH_TEMP.value == "biz_high_temp"
    assert AlertCode.BIZ_LOW_TEMP.value == "biz_low_temp"
    assert AlertCode.BIZ_HIGH_HUMIDITY.value == "biz_high_humidity"
    assert AlertCode.BIZ_LOW_HUMIDITY.value == "biz_low_humidity"
    assert AlertCode.BIZ_LIGHT_FAILURE.value == "biz_light_failure"
    assert AlertCode.BIZ_NODE_OFFLINE.value == "biz_node_offline"
    assert AlertCode.BIZ_CONFIG_ERROR.value == "biz_config_error"
    assert AlertCode.INFRA_MQTT_DOWN.value == "infra_mqtt_down"
    assert AlertCode.INFRA_DB_UNREACHABLE.value == "infra_db_unreachable"
    assert AlertCode.INFRA_SERVICE_DOWN.value == "infra_service_down"


@pytest.mark.asyncio
async def test_create_alert_deduplicates_existing():
    """Test that create_alert delegates deduplication to Laravel contract."""
    with patch("common.alerts._publisher.raise_active", new_callable=AsyncMock) as mock_raise:
        mock_raise.return_value = True

        await create_alert(
            zone_id=1,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type="No water flow detected",
            details={"flow_value": 0.1, "additional_info": "test"}
        )
        
        mock_raise.assert_called_once()
        details = mock_raise.call_args.kwargs["details"]
        assert "last_seen_at" in details
        assert details["flow_value"] == 0.1
        assert details["additional_info"] == "test"


@pytest.mark.asyncio
async def test_create_alert_suppression_window():
    """Test that suppression_window prevents updates if last_seen_at is recent."""
    with patch("common.alerts.fetch") as mock_fetch, \
         patch("common.alerts._publisher.raise_active", new_callable=AsyncMock) as mock_raise:
        now = datetime.now(timezone.utc)
        recent_time = (now.replace(microsecond=0)).isoformat()
        existing_alert = {
            "id": 123,
            "details": {
                "count": 5,
                "last_seen_at": recent_time
            }
        }
        mock_fetch.return_value = [existing_alert]
        
        await create_alert(
            zone_id=1,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type="No water flow detected",
            suppression_window_sec=60
        )
        
        mock_fetch.assert_called_once()
        mock_raise.assert_not_called()


@pytest.mark.asyncio
async def test_create_alert_suppression_window_expired():
    """Test that suppression_window allows updates if last_seen_at is old."""
    with patch("common.alerts.fetch") as mock_fetch, \
         patch("common.alerts._publisher.raise_active", new_callable=AsyncMock) as mock_raise:
        old_time = "2024-01-01T12:00:00+00:00"
        existing_alert = {
            "id": 123,
            "details": {
                "count": 5,
                "last_seen_at": old_time
            }
        }
        mock_fetch.return_value = [existing_alert]
        
        await create_alert(
            zone_id=1,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type="No water flow detected",
            suppression_window_sec=60
        )
        
        mock_raise.assert_called_once()


@pytest.mark.asyncio
async def test_create_alert_deduplication_key_zone_code_status():
    """Test that producer computes a stable dedupe key for zone/code scoped alerts."""
    with patch("common.alerts._publisher.raise_active", new_callable=AsyncMock) as mock_raise:
        mock_raise.return_value = True
        await create_alert(
            zone_id=1,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type="No flow",
            details={"pump_channel": "pump_main"}
        )

        mock_raise.assert_called_once()
        dedupe_key = mock_raise.call_args.kwargs["dedupe_key"]
        assert dedupe_key is not None
        assert "biz_no_flow" in dedupe_key
        assert "zone:1" in dedupe_key
        assert "pump_channel:pump_main" in dedupe_key
