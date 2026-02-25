import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_sync_channels_does_not_prune_by_default():
    from mqtt_handlers import sync_node_channels_from_payload

    channels_payload = [
        {
            "name": "pump_a",
            "type": "ACTUATOR",
            "metric": "FLOW",
            "pump_calibration": {"ml_per_sec": 2.0},
            "poll_interval_ms": 1000,
        }
    ]

    with patch("mqtt_handlers.execute", new_callable=AsyncMock) as mock_execute:
        await sync_node_channels_from_payload(
            10,
            "nd-10",
            channels_payload,
            allow_prune=False,
        )

    assert mock_execute.await_count == 1
    sql, node_id, channel_name, _type, _metric, _unit, config = mock_execute.await_args_list[0].args
    assert "INSERT INTO node_channels" in sql
    assert node_id == 10
    assert channel_name == "pump_a"
    assert config == {"poll_interval_ms": 1000}


@pytest.mark.asyncio
async def test_sync_channels_prunes_only_with_explicit_flag():
    from mqtt_handlers import sync_node_channels_from_payload

    channels_payload = [
        {"name": "pump_a", "type": "ACTUATOR"},
        {"name": "pump_b", "type": "ACTUATOR"},
    ]

    with patch("mqtt_handlers.execute", new_callable=AsyncMock) as mock_execute:
        await sync_node_channels_from_payload(
            11,
            "nd-11",
            channels_payload,
            allow_prune=True,
        )

    assert mock_execute.await_count == 3
    delete_sql, delete_node_id, kept_channels = mock_execute.await_args_list[-1].args
    assert "UPDATE node_channels" in delete_sql
    assert "is_active = FALSE" in delete_sql
    assert delete_node_id == 11
    assert sorted(kept_channels) == ["pump_a", "pump_b"]
