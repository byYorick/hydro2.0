import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.mark.asyncio
async def test_monitor_offline_nodes_uses_fallback_timestamp_columns() -> None:
    from handlers.heartbeat_status import monitor_offline_nodes

    shutdown_event = asyncio.Event()
    import state as hl_state

    hl_state.shutdown_event = shutdown_event

    captured_query = {"sql": ""}

    async def _fetch(sql: str, timeout_sec: int):
        captured_query["sql"] = sql
        assert timeout_sec == 120
        shutdown_event.set()
        return [{"uid": "nd-irrig-1"}]

    with patch("handlers.heartbeat_status.get_settings", return_value=SimpleNamespace(
        node_offline_timeout_sec=120,
        node_offline_check_interval_sec=1,
    )), patch("handlers.heartbeat_status.fetch", new=AsyncMock(side_effect=_fetch)), patch(
        "handlers.heartbeat_status.raise_node_offline_alert",
        new=AsyncMock(),
    ) as alert_mock, patch(
        "handlers.heartbeat_status.logger.warning", new=Mock()
    ) as warning_mock:
        await monitor_offline_nodes()

    normalized_sql = " ".join(captured_query["sql"].split())
    assert "COALESCE(last_seen_at, last_heartbeat_at, updated_at, created_at)" in normalized_sql
    assert "RETURNING uid" in normalized_sql
    warning_mock.assert_called()
    alert_mock.assert_awaited_once_with(node_uid="nd-irrig-1", reason="heartbeat_timeout")
