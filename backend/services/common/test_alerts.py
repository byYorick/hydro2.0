"""Tests for alerts module."""
import pytest
from unittest.mock import AsyncMock, patch
from common.alerts import AlertSource, AlertCode, create_alert


@pytest.mark.asyncio
async def test_create_alert_with_all_fields():
    """Test creating alert with all fields."""
    with patch("common.alerts.execute") as mock_execute:
        await create_alert(
            zone_id=1,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type="No water flow detected",
            details={"flow_value": 0.0, "min_flow": 1.0}
        )
        
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        assert call_args[0][0] == """
        INSERT INTO alerts (zone_id, source, code, type, details, status, created_at)
        VALUES ($1, $2, $3, $4, $5, 'ACTIVE', NOW())
        """
        assert call_args[0][1] == 1  # zone_id
        assert call_args[0][2] == AlertSource.BIZ.value  # source
        assert call_args[0][3] == AlertCode.BIZ_NO_FLOW.value  # code
        assert call_args[0][4] == "No water flow detected"  # type
        assert '"flow_value": 0.0' in call_args[0][5]  # details JSON


@pytest.mark.asyncio
async def test_create_alert_without_details():
    """Test creating alert without details."""
    with patch("common.alerts.execute") as mock_execute:
        await create_alert(
            zone_id=1,
            source=AlertSource.INFRA.value,
            code=AlertCode.INFRA_MQTT_DOWN.value,
            type="MQTT connection lost"
        )
        
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        assert call_args[0][5] is None  # details is None


@pytest.mark.asyncio
async def test_create_alert_with_null_zone_id():
    """Test creating alert with null zone_id (global alert)."""
    with patch("common.alerts.execute") as mock_execute:
        await create_alert(
            zone_id=None,
            source=AlertSource.INFRA.value,
            code=AlertCode.INFRA_SERVICE_DOWN.value,
            type="Service unavailable"
        )
        
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        assert call_args[0][1] is None  # zone_id is None


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

