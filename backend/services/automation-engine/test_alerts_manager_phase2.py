"""Tests for alerts_manager with Phase 2 features."""
import pytest
from unittest.mock import patch
from alerts_manager import (
    ensure_alert,
    resolve_alert,
    _build_dedupe_key,
    _get_alert_source_and_code,
    ALERT_TYPE_MAPPING,
)
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
    """Test that ensure_alert publishes canonical source and code."""
    with patch("alerts_manager.send_biz_alert") as mock_send_biz_alert:
        mock_send_biz_alert.return_value = True

        await ensure_alert(1, "PH_HIGH", {"ph": 7.5, "target": 6.5})

        mock_send_biz_alert.assert_called_once()
        kwargs = mock_send_biz_alert.call_args.kwargs
        assert kwargs["zone_id"] == 1
        assert kwargs["code"] == AlertCode.BIZ_HIGH_PH.value
        assert kwargs["alert_type"] == "PH_HIGH"
        assert kwargs["details"]["ph"] == 7.5
        assert kwargs["details"]["target"] == 6.5
        assert kwargs["details"]["dedupe_key"] == kwargs["dedupe_key"]


@pytest.mark.asyncio
async def test_ensure_alert_updates_existing_alert():
    """Existing alerts are updated only by Laravel deduplication."""
    with patch("alerts_manager.send_biz_alert") as mock_send_biz_alert:
        mock_send_biz_alert.return_value = True

        await ensure_alert(1, "PH_HIGH", {"ph": 7.5, "target": 6.5})

        mock_send_biz_alert.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_alert_uses_same_code_and_dedupe_key():
    with patch("alerts_manager._publisher.resolve") as mock_resolve:
        mock_resolve.return_value = True

        assert await resolve_alert(1, "PH_HIGH") is True

        kwargs = mock_resolve.call_args.kwargs
        assert kwargs["source"] == AlertSource.BIZ.value
        assert kwargs["code"] == AlertCode.BIZ_HIGH_PH.value
        assert kwargs["dedupe_key"] == _build_dedupe_key(1, AlertCode.BIZ_HIGH_PH.value, {})


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
