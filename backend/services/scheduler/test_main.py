"""Tests for scheduler."""
import pytest
from datetime import time
from unittest.mock import Mock, patch
from main import (
    _parse_time_spec,
    get_active_schedules,
    get_zone_nodes_for_type,
    execute_irrigation_schedule,
)


def test_parse_time_spec():
    """Test parsing time spec."""
    assert _parse_time_spec("08:00") == time(8, 0)
    assert _parse_time_spec("14:30") == time(14, 30)
    assert _parse_time_spec("invalid") is None
    assert _parse_time_spec("25:00") is None


@pytest.mark.asyncio
async def test_get_active_schedules():
    """Test fetching active schedules."""
    with patch("main.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {
                "zone_id": 1,
                "current_phase_index": 0,
                "targets": {
                    "ph": 6.5,
                    "irrigation_schedule": ["08:00", "14:00", "20:00"],
                    "lighting_schedule": "06:00-22:00",
                },
                "status": "online",
            }
        ]
        schedules = await get_active_schedules()
        assert len(schedules) > 0
        irrigation_schedules = [s for s in schedules if s["type"] == "irrigation"]
        assert len(irrigation_schedules) == 3  # Three irrigation times
        lighting_schedules = [s for s in schedules if s["type"] == "lighting"]
        assert len(lighting_schedules) == 1  # One lighting window


@pytest.mark.asyncio
async def test_get_zone_nodes_for_type():
    """Test fetching zone nodes by type."""
    with patch("main.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {
                "id": 1,
                "uid": "nd-irrig-1",
                "type": "irrigation",
                "channel_name": "pump1",
                "channel_id": None,
            }
        ]
        nodes = await get_zone_nodes_for_type(1, "irrigation")
        assert len(nodes) == 1
        assert nodes[0]["node_uid"] == "nd-irrig-1"
        assert nodes[0]["type"] == "irrigation"


@pytest.mark.asyncio
async def test_execute_irrigation_schedule():
    """Test executing irrigation schedule."""
    mqtt = Mock()
    with patch("main.get_zone_nodes_for_type") as mock_nodes:
        mock_nodes.return_value = [
            {
                "node_uid": "nd-irrig-1",
                "channel": "pump1",
                "type": "irrigation",
            }
        ]
        await execute_irrigation_schedule(1, mqtt, "gh-1", {})
        # Should publish irrigation command
        assert mqtt.publish_json.called
        call_args = mqtt.publish_json.call_args
        assert "irrigate" in call_args[0][1]["cmd"]

