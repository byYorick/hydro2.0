"""Tests for InfrastructureRepository."""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from repositories.infrastructure_repository import InfrastructureRepository


@pytest.mark.asyncio
async def test_get_zone_bindings_by_role():
    """Test getting bindings for zone grouped by role."""
    repo = InfrastructureRepository()
    
    with patch("repositories.infrastructure_repository.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {
                "role": "vent",
                "node_id": 1,
                "node_uid": "nd-climate-1",
                "node_channel_id": 101,
                "channel": "fan_A",
                "asset_id": 10,
                "asset_type": "VENT",
                "direction": "actuator",
            },
            {
                "role": "heater",
                "node_id": 2,
                "node_uid": "nd-climate-1",
                "node_channel_id": 102,
                "channel": "heater_1",
                "asset_id": 11,
                "asset_type": "HEATER",
                "direction": "actuator",
            },
            {
                "role": "main_pump",
                "node_id": 3,
                "node_uid": "nd-irrig-1",
                "node_channel_id": 103,
                "channel": "pump_1",
                "asset_id": 12,
                "asset_type": "PUMP",
                "direction": "actuator",
            },
        ]
        
        result = await repo.get_zone_bindings_by_role(5)
        
        assert "vent" in result
        assert "heater" in result
        assert "main_pump" in result
        assert result["vent"]["node_uid"] == "nd-climate-1"
        assert result["vent"]["node_channel_id"] == 101
        assert result["vent"]["channel"] == "fan_A"
        assert result["heater"]["node_uid"] == "nd-climate-1"
        assert result["main_pump"]["node_uid"] == "nd-irrig-1"
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_get_zone_bindings_by_role_empty():
    """Test getting bindings when zone has no bindings."""
    repo = InfrastructureRepository()
    
    with patch("repositories.infrastructure_repository.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        
        result = await repo.get_zone_bindings_by_role(5)
        
        assert result == {}


@pytest.mark.asyncio
async def test_get_zones_bindings_batch():
    """Test batch getting bindings for multiple zones."""
    repo = InfrastructureRepository()
    
    with patch("repositories.infrastructure_repository.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {
                "zone_id": 5,
                "role": "vent",
                "node_id": 1,
                "node_uid": "nd-climate-1",
                "node_channel_id": 201,
                "channel": "fan_A",
                "asset_id": 10,
                "asset_type": "VENT",
                "direction": "actuator",
            },
            {
                "zone_id": 6,
                "role": "main_pump",
                "node_id": 3,
                "node_uid": "nd-irrig-1",
                "node_channel_id": 202,
                "channel": "pump_1",
                "asset_id": 12,
                "asset_type": "PUMP",
                "direction": "actuator",
            },
        ]
        
        result = await repo.get_zones_bindings_batch([5, 6, 7])
        
        assert 5 in result
        assert 6 in result
        assert 7 in result  # Zone without bindings should have empty dict
        assert "vent" in result[5]
        assert result[5]["vent"]["node_channel_id"] == 201
        assert "main_pump" in result[6]
        assert result[7] == {}  # Empty dict for zone without bindings


@pytest.mark.asyncio
async def test_get_zone_asset_instances():
    """Test getting asset instances for zone."""
    repo = InfrastructureRepository()
    
    with patch("repositories.infrastructure_repository.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [
            {
                "id": 10,
                "owner_type": "zone",
                "owner_id": 5,
                "asset_type": "VENT",
                "label": "Main Ventilation",
                "required": True,
                "capacity_liters": None,
                "flow_rate": None,
                "specs": {"power": 100},
            },
            {
                "id": 11,
                "owner_type": "zone",
                "owner_id": 5,
                "asset_type": "PUMP",
                "label": "Main Pump",
                "required": True,
                "capacity_liters": None,
                "flow_rate": 50.0,
                "specs": {"max_pressure": 3.0},
            },
        ]
        
        result = await repo.get_zone_asset_instances(5)
        
        assert len(result) == 2
        assert result[0]["asset_type"] == "VENT"
        assert result[1]["asset_type"] == "PUMP"
        assert result[0]["owner_type"] == "zone"
        assert result[1]["owner_id"] == 5
        assert result[0]["required"] is True
        assert result[1]["flow_rate"] == 50.0


@pytest.mark.asyncio
async def test_get_zone_bindings_by_role_with_circuit_breaker():
    """Test getting bindings with circuit breaker."""
    from infrastructure.circuit_breaker import CircuitBreaker
    from prometheus_client import CollectorRegistry
    
    circuit_breaker = CircuitBreaker(
        name="test_db",
        failure_threshold=5,
        timeout=60,
        registry=CollectorRegistry()
    )
    repo = InfrastructureRepository(db_circuit_breaker=circuit_breaker)
    
    with patch.object(circuit_breaker, "call", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = [
            {
                "role": "vent",
                "node_id": 1,
                "node_uid": "nd-climate-1",
                "node_channel_id": 301,
                "channel": "fan_A",
                "asset_id": 10,
                "asset_type": "VENT",
                "direction": "actuator",
            },
        ]
        
        result = await repo.get_zone_bindings_by_role(5)
        
        assert "vent" in result
        mock_call.assert_called_once()
