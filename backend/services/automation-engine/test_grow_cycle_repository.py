"""Tests for GrowCycleRepository."""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Mock common.db before importing repositories
sys.modules['common'] = MagicMock()
sys.modules['common.db'] = MagicMock()

from repositories.grow_cycle_repository import GrowCycleRepository


@pytest.mark.asyncio
async def test_get_active_grow_cycle():
    """Test getting active grow cycle for zone."""
    repo = GrowCycleRepository()
    
    with patch("repositories.grow_cycle_repository.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{
            "id": 1,
            "greenhouse_id": 10,
            "zone_id": 5,
            "plant_id": 20,
            "recipe_id": 30,
            "zone_recipe_instance_id": 40,
            "status": "RUNNING",
            "started_at": "2025-01-01T10:00:00Z",
            "recipe_started_at": "2025-01-01T10:00:00Z",
            "expected_harvest_at": "2025-02-01T10:00:00Z",
            "actual_harvest_at": None,
            "batch_label": "Batch-001",
            "notes": "Test cycle",
            "settings": {"density": 10, "substrate": "coco"},
            "current_phase_index": 1,
            "targets": {"ph": 6.5, "ec": 1.8, "temp_air": 25.0},
            "phase_name": "Vegetation",
        }]
        
        result = await repo.get_active_grow_cycle(5)
        
        assert result is not None
        assert result["id"] == 1
        assert result["zone_id"] == 5
        assert result["status"] == "RUNNING"
        assert result["targets"]["ph"] == 6.5
        assert result["phase_name"] == "Vegetation"
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_get_active_grow_cycle_none():
    """Test getting active grow cycle when zone has no active cycle."""
    repo = GrowCycleRepository()
    
    with patch("repositories.grow_cycle_repository.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        
        result = await repo.get_active_grow_cycle(5)
        
        assert result is None


@pytest.mark.asyncio
async def test_get_zones_grow_cycles_batch():
    """Test batch getting active grow cycles for multiple zones."""
    repo = GrowCycleRepository()
    
    with patch("repositories.grow_cycle_repository.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {
                "id": 1,
                "zone_id": 5,
                "status": "RUNNING",
                "targets": {"ph": 6.5},
                "phase_name": "Vegetation",
                "greenhouse_id": 10,
                "plant_id": 20,
                "recipe_id": 30,
                "zone_recipe_instance_id": 40,
                "started_at": "2025-01-01T10:00:00Z",
                "recipe_started_at": "2025-01-01T10:00:00Z",
                "expected_harvest_at": None,
                "actual_harvest_at": None,
                "batch_label": None,
                "notes": None,
                "settings": None,
                "current_phase_index": 1,
            },
            {
                "id": 2,
                "zone_id": 6,
                "status": "PAUSED",
                "targets": {"ph": 6.8},
                "phase_name": "Flowering",
                "greenhouse_id": 10,
                "plant_id": 21,
                "recipe_id": 31,
                "zone_recipe_instance_id": 41,
                "started_at": "2025-01-02T10:00:00Z",
                "recipe_started_at": "2025-01-02T10:00:00Z",
                "expected_harvest_at": None,
                "actual_harvest_at": None,
                "batch_label": None,
                "notes": None,
                "settings": None,
                "current_phase_index": 2,
            },
        ]
        
        result = await repo.get_zones_grow_cycles_batch([5, 6, 7])
        
        assert 5 in result
        assert 6 in result
        assert 7 in result  # Zone without cycle should have None
        assert result[5] is not None
        assert result[5]["status"] == "RUNNING"
        assert result[6] is not None
        assert result[6]["status"] == "PAUSED"
        assert result[7] is None


@pytest.mark.asyncio
async def test_get_active_grow_cycle_with_circuit_breaker():
    """Test getting active grow cycle with circuit breaker."""
    from infrastructure.circuit_breaker import CircuitBreaker
    
    circuit_breaker = CircuitBreaker(
        name="test_db",
        failure_threshold=5,
        recovery_timeout=60
    )
    repo = GrowCycleRepository(db_circuit_breaker=circuit_breaker)
    
    with patch.object(circuit_breaker, "call", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = [{
            "id": 1,
            "zone_id": 5,
            "status": "RUNNING",
            "targets": {"ph": 6.5},
            "phase_name": "Vegetation",
            "greenhouse_id": 10,
            "plant_id": 20,
            "recipe_id": 30,
            "zone_recipe_instance_id": 40,
            "started_at": "2025-01-01T10:00:00Z",
            "recipe_started_at": "2025-01-01T10:00:00Z",
            "expected_harvest_at": None,
            "actual_harvest_at": None,
            "batch_label": None,
            "notes": None,
            "settings": None,
            "current_phase_index": 1,
        }]
        
        result = await repo.get_active_grow_cycle(5)
        
        assert result is not None
        assert result["status"] == "RUNNING"
        mock_call.assert_called_once()

