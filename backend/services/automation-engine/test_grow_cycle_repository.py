"""Tests for GrowCycleRepository."""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

# Add services + automation-engine directories to path for imports
base_dir = Path(__file__).parent
sys.path.insert(0, str(base_dir))
sys.path.insert(0, str(base_dir.parent))

from repositories.grow_cycle_repository import GrowCycleRepository


@pytest.mark.asyncio
async def test_get_active_grow_cycle():
    """Test getting active grow cycle for zone."""
    with patch("repositories.grow_cycle_repository.LaravelApiRepository") as mock_api_cls:
        mock_api = AsyncMock()
        mock_api.get_effective_targets_batch.return_value = {
            5: {
                "cycle_id": 1,
                "zone_id": 5,
                "phase": {"id": 10, "code": "VEG", "name": "Vegetation"},
                "targets": {
                    "ph": {"target": 6.5, "min": 6.2, "max": 6.8},
                    "ec": {"target": 1.8, "min": 1.6, "max": 2.0},
                },
            }
        }
        mock_api_cls.return_value = mock_api
        repo = GrowCycleRepository()

        result = await repo.get_active_grow_cycle(5)

        assert result is not None
        assert result["id"] == 1
        assert result["zone_id"] == 5
        assert result["status"] == "RUNNING"
        assert result["targets"]["ph"]["target"] == 6.5
        assert result["phase_name"] == "Vegetation"
        mock_api.get_effective_targets_batch.assert_awaited_once_with([5])


@pytest.mark.asyncio
async def test_get_active_grow_cycle_none():
    """Test getting active grow cycle when zone has no active cycle."""
    with patch("repositories.grow_cycle_repository.LaravelApiRepository") as mock_api_cls:
        mock_api = AsyncMock()
        mock_api.get_effective_targets_batch.return_value = {5: None}
        mock_api_cls.return_value = mock_api
        repo = GrowCycleRepository()

        result = await repo.get_active_grow_cycle(5)

        assert result is None
        mock_api.get_effective_targets_batch.assert_awaited_once_with([5])


@pytest.mark.asyncio
async def test_get_zones_grow_cycles_batch():
    """Test batch getting active grow cycles for multiple zones."""
    with patch("repositories.grow_cycle_repository.LaravelApiRepository") as mock_api_cls:
        mock_api = AsyncMock()
        mock_api.get_effective_targets_batch.return_value = {
            5: {
                "cycle_id": 1,
                "zone_id": 5,
                "phase": {"id": 10, "code": "VEG", "name": "Vegetation"},
                "targets": {"ph": {"target": 6.5}},
            },
            6: {
                "cycle_id": 2,
                "zone_id": 6,
                "phase": {"id": 11, "code": "FLOW", "name": "Flowering"},
                "targets": {"ph": {"target": 6.8}},
            },
            7: None,
        }
        mock_api_cls.return_value = mock_api
        repo = GrowCycleRepository()

        result = await repo.get_zones_grow_cycles_batch([5, 6, 7])

        assert 5 in result
        assert 6 in result
        assert 7 in result  # Zone without cycle should have None
        assert result[5] is not None
        assert result[6] is not None
        assert result[7] is None
        mock_api.get_effective_targets_batch.assert_awaited_once_with([5, 6, 7])


@pytest.mark.asyncio
async def test_get_active_grow_cycle_with_circuit_breaker():
    """Test getting active grow cycle with circuit breaker."""
    from infrastructure.circuit_breaker import CircuitBreaker
    from prometheus_client import CollectorRegistry
    
    circuit_breaker = CircuitBreaker(
        name="test_db",
        failure_threshold=5,
        timeout=60,
        registry=CollectorRegistry()
    )
    repo = GrowCycleRepository(db_circuit_breaker=circuit_breaker)
    
    with patch.object(circuit_breaker, "call", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {
            5: {
                "cycle_id": 1,
                "zone_id": 5,
                "phase": {"id": 10, "code": "VEG", "name": "Vegetation"},
                "targets": {"ph": {"target": 6.5}},
            }
        }

        result = await repo.get_active_grow_cycle(5)

        assert result is not None
        assert result["status"] == "RUNNING"
        mock_call.assert_called_once()
