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
            "targets": {"ph": {"target": 6.5}, "ec": {"target": 1.8}},
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
            {"id": 1, "uid": "nd-irrig-1", "type": "irrig", "node_channel_id": 11, "channel": "default"},
            {"id": 2, "uid": "nd-light-1", "type": "light", "node_channel_id": 22, "channel": "default"},
        ]
        
        result = await repo.get_zone_nodes(1)
        
        assert "irrig:default" in result
        assert "light:default" in result
        assert result["irrig:default"]["node_uid"] == "nd-irrig-1"
        assert result["irrig:default"]["node_channel_id"] == 11
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_node_repository_get_zones_nodes_batch():
    """Test batch getting nodes for multiple zones."""
    repo = NodeRepository()
    
    with patch("repositories.node_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [
            {"zone_id": 1, "id": 1, "uid": "nd-irrig-1", "type": "irrig", "node_channel_id": 11, "channel": "default"},
            {"zone_id": 2, "id": 2, "uid": "nd-irrig-2", "type": "irrig", "node_channel_id": 22, "channel": "default"},
        ]
        
        result = await repo.get_zones_nodes_batch([1, 2])
        
        assert 1 in result
        assert 2 in result
        assert "irrig:default" in result[1]
        assert "irrig:default" in result[2]


@pytest.mark.asyncio
async def test_recipe_repository_get_zone_recipe_and_targets():
    """Test getting recipe and targets for zone."""
    with patch("repositories.recipe_repository.LaravelApiRepository") as mock_api_cls:
        mock_api = AsyncMock()
        mock_api.get_effective_targets.return_value = {
            "zone_id": 1,
            "cycle_id": 10,
            "phase": {"id": 2, "code": "GERMINATION", "name": "Germination"},
            "targets": {"ph": {"target": 6.5}, "ec": {"target": 1.8}},
        }
        mock_api_cls.return_value = mock_api
        repo = RecipeRepository()

        result = await repo.get_zone_recipe_and_targets(1)

        assert result is not None
        assert result["zone_id"] == 1
        assert result["targets"]["ph"]["target"] == 6.5
        mock_api.get_effective_targets.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_recipe_repository_get_zone_recipe_and_targets_none():
    """Test getting recipe when zone has no active recipe."""
    with patch("repositories.recipe_repository.LaravelApiRepository") as mock_api_cls:
        mock_api = AsyncMock()
        mock_api.get_effective_targets.return_value = None
        mock_api_cls.return_value = mock_api
        repo = RecipeRepository()

        result = await repo.get_zone_recipe_and_targets(1)

        assert result is None
        mock_api.get_effective_targets.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_recipe_repository_get_zones_recipes_batch():
    """Test batch getting recipes for multiple zones."""
    with patch("repositories.recipe_repository.LaravelApiRepository") as mock_api_cls:
        mock_api = AsyncMock()
        mock_api.get_effective_targets_batch.return_value = {
            1: {
                "zone_id": 1,
                "cycle_id": 10,
                "phase": {"id": 2, "code": "GERMINATION", "name": "Germination"},
                "targets": {"ph": {"target": 6.5}},
            },
            2: {
                "zone_id": 2,
                "cycle_id": 11,
                "phase": {"id": 3, "code": "VEGETATION", "name": "Vegetation"},
                "targets": {"ph": {"target": 6.8}},
            },
        }
        mock_api_cls.return_value = mock_api
        repo = RecipeRepository()

        result = await repo.get_zones_recipes_batch([1, 2])

        assert 1 in result
        assert 2 in result
        assert result[1]["targets"]["ph"]["target"] == 6.5
        assert result[2]["targets"]["ph"]["target"] == 6.8
        mock_api.get_effective_targets_batch.assert_awaited_once_with([1, 2])


@pytest.mark.asyncio
async def test_recipe_repository_get_zone_data_batch_reads_correction_flags_from_samples_metadata():
    """Correction flags should be taken from telemetry_samples metadata when present."""
    with patch("repositories.recipe_repository.LaravelApiRepository"):
        repo = RecipeRepository()

    with patch("repositories.recipe_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [{
            "zone_info": {"zone_id": 1, "capabilities": {"ph_control": True}},
            "telemetry": {
                "PH": {"value": 6.4, "updated_at": "2026-02-14T11:00:00+00:00"},
                "EC": {"value": 1.8, "updated_at": "2026-02-14T11:00:00+00:00"},
                "FLOW_ACTIVE": {"value": 0, "updated_at": "2026-02-14T10:58:00+00:00"},
            },
            "correction_flags": {
                "flow_active": "true",
                "flow_active_ts": "2026-02-14T11:00:01+00:00",
                "stable": "true",
                "stable_ts": "2026-02-14T11:00:02+00:00",
                "corrections_allowed": "false",
                "corrections_allowed_ts": "2026-02-14T11:00:03+00:00",
            },
            "nodes": [],
        }]

        result = await repo.get_zone_data_batch(1)

        flags = result["correction_flags"]
        assert flags["flow_active"] is True
        assert flags["stable"] is True
        assert flags["corrections_allowed"] is False
        assert flags["flow_active_ts"] == "2026-02-14T11:00:01+00:00"
        assert flags["stable_ts"] == "2026-02-14T11:00:02+00:00"
        assert flags["corrections_allowed_ts"] == "2026-02-14T11:00:03+00:00"


@pytest.mark.asyncio
async def test_recipe_repository_get_zone_data_batch_correction_flags_fallback_to_legacy_metrics():
    """Fallback to legacy telemetry_last metrics when metadata flags are missing."""
    with patch("repositories.recipe_repository.LaravelApiRepository"):
        repo = RecipeRepository()

    with patch("repositories.recipe_repository.fetch") as mock_fetch:
        mock_fetch.return_value = [{
            "zone_info": {"zone_id": 1, "capabilities": {"ph_control": True}},
            "telemetry": {
                "PH": {"value": 6.4, "updated_at": "2026-02-14T11:00:00+00:00"},
                "FLOW_ACTIVE": {"value": 1, "updated_at": "2026-02-14T10:58:00+00:00"},
                "STABLE": {"value": 1, "updated_at": "2026-02-14T10:58:01+00:00"},
                "CORRECTIONS_ALLOWED": {"value": 0, "updated_at": "2026-02-14T10:58:02+00:00"},
            },
            "correction_flags": {},
            "nodes": [],
        }]

        result = await repo.get_zone_data_batch(1)

        flags = result["correction_flags"]
        assert flags["flow_active"] is True
        assert flags["stable"] is True
        assert flags["corrections_allowed"] is False
        assert flags["flow_active_ts"] == "2026-02-14T10:58:00+00:00"
        assert flags["stable_ts"] == "2026-02-14T10:58:01+00:00"
        assert flags["corrections_allowed_ts"] == "2026-02-14T10:58:02+00:00"


@pytest.mark.asyncio
async def test_recipe_repository_get_zone_data_batch_emits_alert_when_samples_missing_for_correction_zone():
    with patch("repositories.recipe_repository.LaravelApiRepository"):
        repo = RecipeRepository()

    with patch("repositories.recipe_repository.fetch") as mock_fetch, patch(
        "repositories.recipe_repository.send_infra_alert", new_callable=AsyncMock
    ) as mock_send_alert, patch(
        "repositories.recipe_repository.create_zone_event", new_callable=AsyncMock
    ) as mock_create_zone_event:
        mock_send_alert.return_value = True
        mock_fetch.return_value = [{
            "zone_info": {"zone_id": 5, "capabilities": {"ph_control": True, "ec_control": True}},
            "telemetry": {},
            "correction_flags": {
                "samples_present": False,
                "latest_sample_ts": None,
            },
            "nodes": [],
        }]

        await repo.get_zone_data_batch(5)

        mock_send_alert.assert_awaited_once()
        mock_create_zone_event.assert_awaited_once()
        assert mock_create_zone_event.await_args.args[1] == "CORRECTION_FLAGS_SOURCE_MISSING"
        assert mock_send_alert.await_args.kwargs["code"] == "infra_correction_flags_telemetry_samples_missing"
        assert mock_send_alert.await_args.kwargs["zone_id"] == 5


@pytest.mark.asyncio
async def test_recipe_repository_get_zone_data_batch_emits_resolved_when_samples_restored():
    with patch("repositories.recipe_repository.LaravelApiRepository"):
        repo = RecipeRepository()

    with patch("repositories.recipe_repository.fetch") as mock_fetch, patch(
        "repositories.recipe_repository.send_infra_alert", new_callable=AsyncMock
    ) as mock_send_alert, patch(
        "repositories.recipe_repository.send_infra_resolved_alert", new_callable=AsyncMock
    ) as mock_send_resolved, patch(
        "repositories.recipe_repository.create_zone_event", new_callable=AsyncMock
    ) as mock_create_zone_event:
        mock_send_alert.return_value = True
        mock_send_resolved.return_value = True
        mock_fetch.side_effect = [
            [{
                "zone_info": {"zone_id": 5, "capabilities": {"ph_control": True}},
                "telemetry": {},
                "correction_flags": {"samples_present": False, "latest_sample_ts": None},
                "nodes": [],
            }],
            [{
                "zone_info": {"zone_id": 5, "capabilities": {"ph_control": True}},
                "telemetry": {},
                "correction_flags": {"samples_present": True, "latest_sample_ts": "2026-02-14T13:00:00+00:00"},
                "nodes": [],
            }],
        ]

        await repo.get_zone_data_batch(5)
        await repo.get_zone_data_batch(5)

        mock_send_alert.assert_awaited_once()
        mock_send_resolved.assert_awaited_once()
        assert mock_create_zone_event.await_count == 2
        assert mock_create_zone_event.await_args_list[0].args[1] == "CORRECTION_FLAGS_SOURCE_MISSING"
        assert mock_create_zone_event.await_args_list[1].args[1] == "CORRECTION_FLAGS_SOURCE_RESTORED"
        assert mock_send_resolved.await_args.kwargs["code"] == "infra_correction_flags_telemetry_samples_missing"
        assert mock_send_resolved.await_args.kwargs["zone_id"] == 5


@pytest.mark.asyncio
async def test_recipe_repository_get_zone_data_batch_skips_missing_samples_alert_for_non_correction_zone():
    with patch("repositories.recipe_repository.LaravelApiRepository"):
        repo = RecipeRepository()

    with patch("repositories.recipe_repository.fetch") as mock_fetch, patch(
        "repositories.recipe_repository.send_infra_alert", new_callable=AsyncMock
    ) as mock_send_alert, patch(
        "repositories.recipe_repository.create_zone_event", new_callable=AsyncMock
    ) as mock_create_zone_event:
        mock_fetch.return_value = [{
            "zone_info": {"zone_id": 8, "capabilities": {"ph_control": False, "ec_control": False}},
            "telemetry": {},
            "correction_flags": {"samples_present": False, "latest_sample_ts": None},
            "nodes": [],
        }]

        await repo.get_zone_data_batch(8)

        mock_send_alert.assert_not_awaited()
        mock_create_zone_event.assert_not_awaited()
