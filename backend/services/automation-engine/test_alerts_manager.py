"""Tests for alerts_manager module."""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from alerts_manager import (
    ensure_alert,
    resolve_alert,
    find_active_alert,
    _build_dedupe_key,
)


@pytest.mark.asyncio
async def test_ensure_alert_new():
    """Test publishing a new active alert intent."""
    with patch("alerts_manager.send_biz_alert") as mock_send_biz_alert:
        mock_send_biz_alert.return_value = True

        await ensure_alert(1, "TEMP_HIGH", {"temp": 30.0, "target": 25.0})

        mock_send_biz_alert.assert_called_once()
        kwargs = mock_send_biz_alert.call_args.kwargs
        assert kwargs["zone_id"] == 1
        assert kwargs["code"] == "biz_high_temp"
        assert kwargs["alert_type"] == "TEMP_HIGH"
        assert kwargs["details"]["legacy_alert_type"] == "TEMP_HIGH"
        assert kwargs["details"]["dedupe_key"] == kwargs["dedupe_key"]


@pytest.mark.asyncio
async def test_ensure_alert_update_existing():
    """Repeated ensure still goes through Laravel dedup path."""
    with patch("alerts_manager.send_biz_alert") as mock_send_biz_alert:
        mock_send_biz_alert.return_value = True

        await ensure_alert(1, "TEMP_HIGH", {"temp": 30.0, "target": 25.0})

        mock_send_biz_alert.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_alert():
    """Test publishing a resolved alert intent."""
    with patch("alerts_manager._publisher.resolve") as mock_resolve:
        mock_resolve.return_value = True

        result = await resolve_alert(1, "TEMP_HIGH")

        assert result is True
        mock_resolve.assert_called_once()
        kwargs = mock_resolve.call_args.kwargs
        assert kwargs["zone_id"] == 1
        assert kwargs["source"] == "biz"
        assert kwargs["code"] == "biz_high_temp"
        assert kwargs["alert_type"] == "TEMP_HIGH"
        assert kwargs["details"]["dedupe_key"] == kwargs["dedupe_key"]


@pytest.mark.asyncio
async def test_resolve_alert_not_found():
    """Missing active alerts are resolved by Laravel, not checked in Python."""
    with patch("alerts_manager._publisher.resolve") as mock_resolve:
        mock_resolve.return_value = False

        result = await resolve_alert(1, "TEMP_HIGH")

        assert result is False
        mock_resolve.assert_called_once()


@pytest.mark.asyncio
async def test_find_active_alert():
    """Test finding active alert."""
    with patch("alerts_manager.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {
                "id": 123,
                "code": "biz_high_temp",
                "type": "TEMP_HIGH",
                "details": '{"temp": 30.0}',
                "status": "ACTIVE",
                "created_at": datetime.utcnow(),
            }
        ]
        
        alert = await find_active_alert(1, "TEMP_HIGH")
        
        assert alert is not None
        assert alert["id"] == 123
        assert alert["code"] == "biz_high_temp"
        assert alert["type"] == "TEMP_HIGH"
        assert alert["status"] == "ACTIVE"
        sql = mock_fetch.call_args.args[0]
        assert "LOWER(code)" in sql
        assert "details->>'dedupe_key'" in sql


@pytest.mark.asyncio
async def test_find_active_alert_not_found():
    """Test finding active alert when not found."""
    with patch("alerts_manager.fetch") as mock_fetch:
        mock_fetch.return_value = []
        
        alert = await find_active_alert(1, "TEMP_HIGH")
        
        assert alert is None


def test_build_dedupe_key_uses_explicit_value():
    assert _build_dedupe_key(1, "biz_high_temp", {"dedupe_key": "explicit"}) == "explicit"


def test_build_dedupe_key_is_scoped_by_zone_and_code():
    dedupe = _build_dedupe_key(1, "biz_high_temp", {})
    assert "biz_high_temp" in dedupe
    assert "zone:1" in dedupe
    assert "code_scope:biz_high_temp" in dedupe
