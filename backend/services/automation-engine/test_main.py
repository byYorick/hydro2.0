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
    with patch("main.RecipeRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_zone_recipe_and_targets.return_value = {
            "zone_id": 1,
            "phase_index": 0,
            "targets": {"ph": {"target": 6.5}, "ec": {"target": 1.8}},
            "phase_name": "Germination",
        }
        mock_repo_cls.return_value = mock_repo
        result = await get_zone_recipe_and_targets(1)
        assert result is not None
        assert result["zone_id"] == 1
        assert result["targets"] == {"ph": {"target": 6.5}, "ec": {"target": 1.8}}


@pytest.mark.asyncio
async def test_get_zone_telemetry_last():
    """Test fetching zone telemetry last values."""
    with patch("main.TelemetryRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_last_telemetry.return_value = {"PH": 6.3, "EC": 1.7}
        mock_repo_cls.return_value = mock_repo
        result = await get_zone_telemetry_last(1)
        assert result["PH"] == 6.3
        assert result["EC"] == 1.7


@pytest.mark.asyncio
async def test_get_zone_nodes():
    """Test fetching zone nodes."""
    with patch("main.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {
                "id": 1,
                "uid": "nd-irrig-1",
                "type": "irrigation",
                "channel": "pump1",
            }
        ]
        result = await get_zone_nodes(1)
        assert "irrigation:pump1" in result
        assert result["irrigation:pump1"]["node_uid"] == "nd-irrig-1"


@pytest.mark.asyncio
async def test_check_and_correct_zone_no_targets():
    """Test zone check when no targets exist."""
    from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository
    
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    
    # get_zone_data_batch находится в RecipeRepository
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={
        "recipe_info": None,
        "telemetry": {},
        "nodes": {},
        "capabilities": {}
    })
    
    mqtt = Mock()
    with patch("services.zone_automation_service.ZoneAutomationService.process_zone") as mock_process:
        mock_process.return_value = None
        await check_and_correct_zone(1, mqtt, "gh-1", {}, zone_repo, telemetry_repo, node_repo, recipe_repo)
        mock_process.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_check_and_correct_zone_ph_correction():
    """Test pH correction command when pH is too low."""
    from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository
    
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={
        "recipe_info": {
            "zone_id": 1,
            "targets": {"ph": {"target": 6.5}, "ec": {"target": 1.8}},
            "phase_name": "Germination",
        },
        "telemetry": {"PH": 6.2, "EC": 1.8},  # pH too low
        "nodes": {
            "irrig:default": {
                "node_uid": "nd-irrig-1",
                "channel": "default",
                "type": "irrig",
            }
        },
        "capabilities": {"ph_control": True, "ec_control": False}
    })
    
    mqtt = Mock()
    mqtt.publish_json = AsyncMock()
    
    with patch("services.zone_automation_service.ZoneAutomationService.process_zone") as mock_process:
        mock_process.return_value = None
        await check_and_correct_zone(1, mqtt, "gh-1", {}, zone_repo, telemetry_repo, node_repo, recipe_repo)
        # Should call process_zone
        mock_process.assert_called_once_with(1)


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
    from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository
    
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={
        "recipe_info": {
            "zone_id": 1,
            "phase_index": 0,
            "targets": {
                "ph": {"target": 6.5},
                "ec": {"target": 1.8},
                "climate_request": {"temp_air_target": 25.0},
            },
            "phase_name": "Germination",
        },
        "telemetry": {"PH": 6.3, "EC": 1.7, "TEMPERATURE": 24.0},
        "nodes": {
            "irrig:default": {"node_uid": "nd-irrig-1", "channel": "default", "type": "irrig"}
        },
        "capabilities": {
            "ph_control": True,
            "ec_control": True,
            "climate_control": True,
            "light_control": True,
            "irrigation_control": True,
            "recirculation": True,
            "flow_sensor": True,
        }
    })
    
    mqtt = Mock()
    mqtt.publish_json = AsyncMock()
    cfg = {"greenhouses": [{"uid": "gh-1"}]}
    
    with patch("services.zone_automation_service.ZoneAutomationService.process_zone") as mock_process:
        mock_process.return_value = None
        await check_and_correct_zone(1, mqtt, "gh-1", cfg, zone_repo, telemetry_repo, node_repo, recipe_repo)
        mock_process.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_check_and_correct_zone_with_capabilities_disabled():
    """Test zone correction with capabilities disabled."""
    from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository
    
    zone_repo = Mock(spec=ZoneRepository)
    telemetry_repo = Mock(spec=TelemetryRepository)
    node_repo = Mock(spec=NodeRepository)
    recipe_repo = Mock(spec=RecipeRepository)
    
    recipe_repo.get_zone_data_batch = AsyncMock(return_value={
        "recipe_info": {
            "zone_id": 1,
            "phase_index": 0,
            "targets": {"ph": {"target": 6.5}, "ec": {"target": 1.8}},
            "phase_name": "Germination",
        },
        "telemetry": {"PH": 6.3, "EC": 1.7},
        "nodes": {},
        "capabilities": {
            "ph_control": False,
            "ec_control": False,
            "climate_control": False,
            "light_control": False,
            "irrigation_control": False,
            "recirculation": False,
            "flow_sensor": False,
        }
    })
    
    mqtt = Mock()
    mqtt.publish_json = AsyncMock()
    cfg = {"greenhouses": [{"uid": "gh-1"}]}
    
    with patch("services.zone_automation_service.ZoneAutomationService.process_zone") as mock_process:
        mock_process.return_value = None
        await check_and_correct_zone(1, mqtt, "gh-1", cfg, zone_repo, telemetry_repo, node_repo, recipe_repo)
        mock_process.assert_called_once_with(1)
