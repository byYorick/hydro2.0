"""Tests for automation-engine."""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from main import (
    get_zone_recipe_and_targets,
    get_zone_telemetry_last,
    get_zone_nodes,
    get_zone_capabilities,
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


@pytest.mark.asyncio
async def test_get_zone_capabilities():
    """Test fetching zone capabilities."""
    with patch("main.fetch") as mock_fetch:
        # Тест с capabilities
        mock_fetch.return_value = [
            {
                "capabilities": {
                    "ph_control": True,
                    "ec_control": True,
                    "climate_control": False,
                    "light_control": True,
                    "irrigation_control": True,
                    "recirculation": False,
                    "flow_sensor": True,
                }
            }
        ]
        result = await get_zone_capabilities(1)
        assert result["ph_control"] is True
        assert result["ec_control"] is True
        assert result["climate_control"] is False
        assert result["light_control"] is True
        assert result["irrigation_control"] is True
        assert result["recirculation"] is False
        assert result["flow_sensor"] is True


@pytest.mark.asyncio
async def test_get_zone_capabilities_default():
    """Test fetching zone capabilities when not set (defaults)."""
    with patch("main.fetch") as mock_fetch:
        # Тест без capabilities (None или пустой)
        mock_fetch.return_value = [{"capabilities": None}]
        result = await get_zone_capabilities(1)
        # Все должны быть False по умолчанию
        assert result["ph_control"] is False
        assert result["ec_control"] is False
        assert result["climate_control"] is False
        assert result["light_control"] is False
        assert result["irrigation_control"] is False
        assert result["recirculation"] is False
        assert result["flow_sensor"] is False


@pytest.mark.asyncio
async def test_check_and_correct_zone_with_capabilities():
    """Test zone correction with capabilities enabled."""
    mqtt = Mock()
    mqtt.publish_json = Mock()
    cfg = {"greenhouses": [{"uid": "gh-1"}]}
    
    with patch("main.get_zone_recipe_and_targets") as mock_recipe, \
         patch("main.get_zone_telemetry_last") as mock_telemetry, \
         patch("main.get_zone_nodes") as mock_nodes, \
         patch("main.get_zone_capabilities") as mock_capabilities, \
         patch("main.check_water_level") as mock_water_level, \
         patch("main.check_and_control_lighting") as mock_light, \
         patch("main.check_and_control_climate") as mock_climate, \
         patch("main.check_and_control_irrigation") as mock_irrigation, \
         patch("main.check_and_control_recirculation") as mock_recirculation, \
         patch("main.create_zone_event") as mock_event, \
         patch("main.publish_correction_command") as mock_publish:
        
        mock_recipe.return_value = {
            "zone_id": 1,
            "phase_index": 0,
            "targets": {"ph": 6.5, "ec": 1.8, "temp_air": 25.0},
            "phase_name": "Germination",
        }
        mock_telemetry.return_value = {"ph": 6.3, "ec": 1.7, "TEMP_AIR": 24.0}
        mock_nodes.return_value = {
            "irrig:default": {"node_uid": "nd-irrig-1", "channel": "pump1", "type": "irrig"}
        }
        # Все capabilities включены
        mock_capabilities.return_value = {
            "ph_control": True,
            "ec_control": True,
            "climate_control": True,
            "light_control": True,
            "irrigation_control": True,
            "recirculation": True,
            "flow_sensor": True,
        }
        mock_water_level.return_value = (True, 0.5)
        mock_light.return_value = None
        mock_climate.return_value = []
        mock_irrigation.return_value = None
        mock_recirculation.return_value = None
        
        await check_and_correct_zone(1, mqtt, "gh-1", cfg)
        
        # Проверяем, что capabilities были получены
        mock_capabilities.assert_called_once_with(1)
        
        # Проверяем, что контроллеры были вызваны
        mock_light.assert_called_once()
        mock_climate.assert_called_once()
        mock_irrigation.assert_called_once()
        mock_recirculation.assert_called_once()


@pytest.mark.asyncio
async def test_check_and_correct_zone_with_capabilities_disabled():
    """Test zone correction with capabilities disabled."""
    mqtt = Mock()
    mqtt.publish_json = Mock()
    cfg = {"greenhouses": [{"uid": "gh-1"}]}
    
    with patch("main.get_zone_recipe_and_targets") as mock_recipe, \
         patch("main.get_zone_telemetry_last") as mock_telemetry, \
         patch("main.get_zone_nodes") as mock_nodes, \
         patch("main.get_zone_capabilities") as mock_capabilities, \
         patch("main.check_water_level") as mock_water_level, \
         patch("main.check_and_control_lighting") as mock_light, \
         patch("main.check_and_control_climate") as mock_climate, \
         patch("main.check_and_control_irrigation") as mock_irrigation, \
         patch("main.check_and_control_recirculation") as mock_recirculation, \
         patch("main.create_zone_event") as mock_event:
        
        mock_recipe.return_value = {
            "zone_id": 1,
            "phase_index": 0,
            "targets": {"ph": 6.5, "ec": 1.8},
            "phase_name": "Germination",
        }
        mock_telemetry.return_value = {"ph": 6.3, "ec": 1.7}
        mock_nodes.return_value = {}
        # Все capabilities отключены
        mock_capabilities.return_value = {
            "ph_control": False,
            "ec_control": False,
            "climate_control": False,
            "light_control": False,
            "irrigation_control": False,
            "recirculation": False,
            "flow_sensor": False,
        }
        mock_water_level.return_value = (True, 0.5)
        
        await check_and_correct_zone(1, mqtt, "gh-1", cfg)
        
        # Проверяем, что контроллеры НЕ были вызваны
        mock_light.assert_not_called()
        mock_climate.assert_not_called()
        mock_irrigation.assert_not_called()
        mock_recirculation.assert_not_called()

