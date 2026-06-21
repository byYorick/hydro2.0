import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_raise_node_offline_alert_publishes_biz_node_offline() -> None:
    from handlers.node_connectivity_alerts import raise_node_offline_alert

    with patch(
        "handlers.node_connectivity_alerts.fetch",
        new=AsyncMock(return_value=[{"uid": "nd-irrig-1", "zone_id": 1, "hardware_id": "esp32-1", "type": "irrig"}]),
    ), patch(
        "handlers.node_connectivity_alerts._publisher.raise_active",
        new=AsyncMock(return_value=True),
    ) as raise_mock:
        await raise_node_offline_alert(node_uid="nd-irrig-1", reason="mqtt_lwt")

    raise_mock.assert_awaited_once()
    kwargs = raise_mock.await_args.kwargs
    assert kwargs["code"] == "biz_node_offline"
    assert kwargs["node_uid"] == "nd-irrig-1"
    assert kwargs["zone_id"] == 1
    assert "LWT" in kwargs["details"]["message"]


@pytest.mark.asyncio
async def test_resolve_node_online_alert_resolves_biz_node_offline() -> None:
    from handlers.node_connectivity_alerts import resolve_node_online_alert

    with patch(
        "handlers.node_connectivity_alerts.fetch",
        new=AsyncMock(return_value=[{"uid": "nd-irrig-1", "zone_id": 1, "hardware_id": "esp32-1", "type": "irrig"}]),
    ), patch(
        "handlers.node_connectivity_alerts._publisher.resolve",
        new=AsyncMock(return_value=True),
    ) as resolve_mock:
        await resolve_node_online_alert(node_uid="nd-irrig-1", reason="heartbeat")

    resolve_mock.assert_awaited_once()
    assert resolve_mock.await_args.kwargs["code"] == "biz_node_offline"
