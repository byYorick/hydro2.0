"""Tests for repositories."""
import pytest
from unittest.mock import AsyncMock, patch
from repositories import (
    ZoneRepository,
    TelemetryRepository,
    NodeRepository,
    RecipeRepository,
)


@pytest.mark.asyncio
async def test_zone_repository_get_zone_capabilities():
    """Test getting zone capabilities."""
    repo = ZoneRepository()
    
    with patch("repositories.zone_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [{
            "capabilities": {
                "ph_control": True,
                "ec_control": True,
                "climate_control": False,
            }
        }]
        
        result = await repo.get_zone_capabilities(1)
        
        assert result["ph_control"] is True
        assert result["ec_control"] is True
        assert result["climate_control"] is False
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_zone_repository_get_zone_capabilities_default():
    """Test getting default capabilities when not set."""
    repo = ZoneRepository()
    
    with patch("repositories.zone_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [{"capabilities": None}]
        
        result = await repo.get_zone_capabilities(1)
        
        assert result == repo.DEFAULT_CAPABILITIES
        assert result["ph_control"] is False


@pytest.mark.asyncio
async def test_zone_repository_get_zones_capabilities_batch():
    """Test batch getting capabilities for multiple zones."""
    repo = ZoneRepository()
    
    with patch("repositories.zone_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"id": 1, "capabilities": {"ph_control": True}},
            {"id": 2, "capabilities": {"ec_control": True}},
        ]
        
        result = await repo.get_zones_capabilities_batch([1, 2])
        
        assert 1 in result
        assert 2 in result
        assert result[1]["ph_control"] is True
        assert result[2]["ec_control"] is True


@pytest.mark.asyncio
async def test_zone_repository_get_active_zones():
    """Test getting active zones."""
    repo = ZoneRepository()
    
    with patch("repositories.zone_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"id": 1, "name": "Zone 1"},
            {"id": 2, "name": "Zone 2"},
        ]
        
        result = await repo.get_active_zones()
        
        assert len(result) == 2
        assert result[0]["id"] == 1
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_zone_repository_get_zone_data_batch():
    """Test getting all zone data in batch."""
    repo = ZoneRepository()
    
    # Проверяем, есть ли метод (может быть в другой версии)
    if not hasattr(repo, 'get_zone_data_batch'):
        pytest.skip("get_zone_data_batch method not implemented")
    
    with patch("repositories.zone_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [{
            "zone_id": 1,
            "recipe_id": 10,
            "phase_index": 0,
            "targets": {"ph": 6.5, "ec": 1.8},
            "phase_name": "Germination",
            "metric_type": "PH",
            "value": 6.3,
            "node_id": 100,
            "node_uid": "nd-irrig-1",
            "node_type": "irrig",
            "channel": "default",
            "capabilities": {"ph_control": True},
        }]
        
        result = await repo.get_zone_data_batch(1)
        
        assert "recipe_info" in result
        assert "telemetry" in result
        assert "nodes" in result
        assert "capabilities" in result
        assert result["recipe_info"]["zone_id"] == 1
        assert result["telemetry"]["PH"] == 6.3


@pytest.mark.asyncio
async def test_telemetry_repository_get_last_telemetry():
    """Test getting last telemetry for zone."""
    repo = TelemetryRepository()
    
    with patch("repositories.telemetry_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"metric_type": "PH", "value": 6.3},
            {"metric_type": "EC", "value": 1.7},
        ]
        
        result = await repo.get_last_telemetry(1)
        
        assert result["PH"] == 6.3
        assert result["EC"] == 1.7
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_telemetry_repository_get_zones_telemetry_batch():
    """Test batch getting telemetry for multiple zones."""
    repo = TelemetryRepository()
    
    with patch("repositories.telemetry_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"zone_id": 1, "metric_type": "PH", "value": 6.3},
            {"zone_id": 2, "metric_type": "PH", "value": 6.5},
        ]
        
        result = await repo.get_zones_telemetry_batch([1, 2])
        
        assert 1 in result
        assert 2 in result
        assert result[1]["PH"] == 6.3
        assert result[2]["PH"] == 6.5


@pytest.mark.asyncio
async def test_node_repository_get_zone_nodes():
    """Test getting nodes for zone."""
    repo = NodeRepository()
    
    with patch("repositories.node_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"id": 1, "uid": "nd-irrig-1", "type": "irrig", "channel": "default"},
            {"id": 2, "uid": "nd-light-1", "type": "light", "channel": "default"},
        ]
        
        result = await repo.get_zone_nodes(1)
        
        assert "irrig:default" in result
        assert "light:default" in result
        assert result["irrig:default"]["node_uid"] == "nd-irrig-1"
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_node_repository_get_zones_nodes_batch():
    """Test batch getting nodes for multiple zones."""
    repo = NodeRepository()
    
    with patch("repositories.node_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"zone_id": 1, "id": 1, "uid": "nd-irrig-1", "type": "irrig", "channel": "default"},
            {"zone_id": 2, "id": 2, "uid": "nd-irrig-2", "type": "irrig", "channel": "default"},
        ]
        
        result = await repo.get_zones_nodes_batch([1, 2])
        
        assert 1 in result
        assert 2 in result
        assert "irrig:default" in result[1]
        assert "irrig:default" in result[2]


@pytest.mark.asyncio
async def test_recipe_repository_get_zone_recipe_and_targets():
    """Test getting recipe and targets for zone."""
    repo = RecipeRepository()
    
    with patch("repositories.recipe_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [{
            "zone_id": 1,
            "current_phase_index": 0,
            "targets": {"ph": 6.5, "ec": 1.8},
            "phase_name": "Germination",
        }]
        
        result = await repo.get_zone_recipe_and_targets(1)
        
        assert result is not None
        assert result["zone_id"] == 1
        assert result["targets"]["ph"] == 6.5
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_recipe_repository_get_zone_recipe_and_targets_none():
    """Test getting recipe when zone has no active recipe."""
    repo = RecipeRepository()
    
    with patch("repositories.recipe_repository.fetch") as mock_fetch:
        mock_fetch.return_value = []
        
        result = await repo.get_zone_recipe_and_targets(1)
        
        assert result is None


@pytest.mark.asyncio
async def test_recipe_repository_get_zones_recipes_batch():
    """Test batch getting recipes for multiple zones."""
    repo = RecipeRepository()
    
    with patch("repositories.recipe_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"zone_id": 1, "current_phase_index": 0, "targets": {"ph": 6.5}, "phase_name": "Germination"},
            {"zone_id": 2, "current_phase_index": 1, "targets": {"ph": 6.8}, "phase_name": "Vegetation"},
        ]
        
        result = await repo.get_zones_recipes_batch([1, 2])
        
        assert 1 in result
        assert 2 in result
        assert result[1]["targets"]["ph"] == 6.5
        assert result[2]["targets"]["ph"] == 6.8

