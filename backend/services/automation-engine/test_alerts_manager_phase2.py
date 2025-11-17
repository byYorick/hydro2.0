"""Tests for alerts_manager with Phase 2 features."""
import pytest
from unittest.mock import AsyncMock, patch
from alerts_manager import ensure_alert, _get_alert_source_and_code, ALERT_TYPE_MAPPING
from common.alerts import AlertSource, AlertCode


def test_get_alert_source_and_code_known_types():
    """Test _get_alert_source_and_code for known alert types."""
    source, code = _get_alert_source_and_code("PH_HIGH")
    assert source == AlertSource.BIZ.value
    assert code == AlertCode.BIZ_HIGH_PH.value
    
    source, code = _get_alert_source_and_code("PH_LOW")
    assert source == AlertSource.BIZ.value
    assert code == AlertCode.BIZ_LOW_PH.value
    
    source, code = _get_alert_source_and_code("TEMP_HIGH")
    assert source == AlertSource.BIZ.value
    assert code == AlertCode.BIZ_HIGH_TEMP.value
    
    source, code = _get_alert_source_and_code("TEMP_LOW")
    assert source == AlertSource.BIZ.value
    assert code == AlertCode.BIZ_LOW_TEMP.value
    
    source, code = _get_alert_source_and_code("HUMIDITY_HIGH")
    assert source == AlertSource.BIZ.value
    assert code == AlertCode.BIZ_HIGH_HUMIDITY.value
    
    source, code = _get_alert_source_and_code("HUMIDITY_LOW")
    assert source == AlertSource.BIZ.value
    assert code == AlertCode.BIZ_LOW_HUMIDITY.value
    
    source, code = _get_alert_source_and_code("LIGHT_FAILURE")
    assert source == AlertSource.BIZ.value
    assert code == AlertCode.BIZ_LIGHT_FAILURE.value
    
    source, code = _get_alert_source_and_code("NO_FLOW")
    assert source == AlertSource.BIZ.value
    assert code == AlertCode.BIZ_NO_FLOW.value


def test_get_alert_source_and_code_unknown_type():
    """Test _get_alert_source_and_code for unknown alert types."""
    source, code = _get_alert_source_and_code("UNKNOWN_TYPE")
    assert source == AlertSource.BIZ.value
    assert code == AlertCode.BIZ_CONFIG_ERROR.value  # Default


@pytest.mark.asyncio
async def test_ensure_alert_creates_new_alert_with_source_and_code():
    """Test that ensure_alert creates new alert with source and code."""
    with patch("alerts_manager.fetch") as mock_fetch, \
         patch("alerts_manager.create_alert") as mock_create_alert, \
         patch("alerts_manager.create_zone_event") as mock_create_event:
        # Mock no existing alert
        mock_fetch.return_value = []
        
        await ensure_alert(1, "PH_HIGH", {"ph": 7.5, "target": 6.5})
        
        # Check that create_alert was called with correct source and code
        mock_create_alert.assert_called_once()
        call_args = mock_create_alert.call_args
        assert call_args[1]["zone_id"] == 1
        assert call_args[1]["source"] == AlertSource.BIZ.value
        assert call_args[1]["code"] == AlertCode.BIZ_HIGH_PH.value
        assert call_args[1]["type"] == "PH_HIGH"
        assert call_args[1]["details"] == {"ph": 7.5, "target": 6.5}


@pytest.mark.asyncio
async def test_ensure_alert_updates_existing_alert():
    """Test that ensure_alert updates existing alert details."""
    with patch("alerts_manager.fetch") as mock_fetch, \
         patch("alerts_manager.execute") as mock_execute, \
         patch("alerts_manager.create_alert") as mock_create_alert:
        # Mock existing alert
        mock_fetch.return_value = [{"id": 123, "details": '{"ph": 7.0}'}]
        
        await ensure_alert(1, "PH_HIGH", {"ph": 7.5, "target": 6.5})
        
        # Should update, not create
        mock_create_alert.assert_not_called()
        mock_execute.assert_called_once()


def test_alert_type_mapping_completeness():
    """Test that ALERT_TYPE_MAPPING contains expected mappings."""
    expected_mappings = [
        "PH_HIGH", "PH_LOW", "EC_HIGH", "EC_LOW",
        "NO_FLOW", "WATER_LEVEL_LOW", "LIGHT_FAILURE"
    ]
    
    for alert_type in expected_mappings:
        assert alert_type in ALERT_TYPE_MAPPING
        source, code = ALERT_TYPE_MAPPING[alert_type]
        assert source in [AlertSource.BIZ.value, AlertSource.INFRA.value]
        assert code.startswith("biz_") or code.startswith("infra_")

