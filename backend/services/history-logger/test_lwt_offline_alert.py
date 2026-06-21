import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_handle_lwt_offline_raises_node_offline_alert() -> None:
    from handlers.heartbeat_status import handle_lwt

    with patch("handlers.heartbeat_status.execute", new=AsyncMock()), patch(
        "handlers.heartbeat_status.raise_node_offline_alert",
        new=AsyncMock(),
    ) as alert_mock:
        await handle_lwt(
            "hydro/gh-6464/zn-4345/nd-irrig-1/lwt",
            b"offline",
        )

    alert_mock.assert_awaited_once_with(node_uid="nd-irrig-1", reason="mqtt_lwt")
