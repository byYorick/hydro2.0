"""Tests for automation-engine."""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from main import (
    get_zone_recipe_and_targets,
    get_zone_telemetry_last,
    get_zone_nodes,
    check_and_correct_zone,
    _extract_gh_uid_from_config,
)


@pytest.mark.asyncio
async def test_extract_gh_uid_from_config():
    """Test extracting greenhouse uid from config."""
    cfg = {"greenhouses": [{"uid": "gh-1", "name": "Greenhouse 1"}]}
    assert _extract_gh_uid_from_config(cfg) == "gh-1"
    
    cfg_empty = {"greenhouses": []}
    assert _extract_gh_uid_from_config(cfg_empty) is None
    
    cfg_no_gh = {}
    assert _extract_gh_uid_from_config(cfg_no_gh) is None


@pytest.mark.asyncio
async def test_get_zone_recipe_and_targets():
    """Test fetching zone recipe and targets."""
    # Mock database fetch
    with patch("main.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {
                "zone_id": 1,
                "current_phase_index": 0,
                "targets": {"ph": 6.5, "ec": 1.8},
                "phase_name": "Germination",
            }
        ]
        result = await get_zone_recipe_and_targets(1)
        assert result is not None
        assert result["zone_id"] == 1
        assert result["targets"] == {"ph": 6.5, "ec": 1.8}


@pytest.mark.asyncio
async def test_get_zone_telemetry_last():
    """Test fetching zone telemetry last values."""
    with patch("main.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"metric_type": "ph", "value": 6.3},
            {"metric_type": "ec", "value": 1.7},
        ]
        result = await get_zone_telemetry_last(1)
        assert result["ph"] == 6.3
        assert result["ec"] == 1.7


@pytest.mark.asyncio
async def test_get_zone_nodes():
    """Test fetching zone nodes."""
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
        result = await get_zone_nodes(1)
        assert "irrigation:pump1" in result
        assert result["irrigation:pump1"]["node_uid"] == "nd-irrig-1"


@pytest.mark.asyncio
async def test_check_and_correct_zone_no_targets():
    """Test zone check when no targets exist."""
    mqtt = Mock()
    with patch("main.get_zone_recipe_and_targets") as mock_recipe:
        mock_recipe.return_value = None
        await check_and_correct_zone(1, mqtt, "gh-1", {})
        mqtt.publish_json.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_correct_zone_ph_correction():
    """Test pH correction command when pH is too low."""
    mqtt = Mock()
    with patch("main.get_zone_recipe_and_targets") as mock_recipe, \
         patch("main.get_zone_telemetry_last") as mock_telemetry, \
         patch("main.get_zone_nodes") as mock_nodes:
        mock_recipe.return_value = {
            "zone_id": 1,
            "targets": {"ph": 6.5, "ec": 1.8},
            "phase_name": "Germination",
        }
        mock_telemetry.return_value = {"ph": 6.2, "ec": 1.8}  # pH too low
        mock_nodes.return_value = {
            "irrigation:pump1": {
                "node_uid": "nd-irrig-1",
                "channel": "pump1",
                "type": "irrigation",
            }
        }
        await check_and_correct_zone(1, mqtt, "gh-1", {})
        # Should publish correction command
        assert mqtt.publish_json.called

