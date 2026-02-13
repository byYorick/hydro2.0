import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.mark.asyncio
async def test_monitor_offline_nodes_uses_fallback_timestamp_columns() -> None:
    from mqtt_handlers import monitor_offline_nodes, state

    shutdown_event = asyncio.Event()
    state.shutdown_event = shutdown_event

    captured_query = {"sql": ""}

    async def _execute(sql: str, timeout_sec: int):
        captured_query["sql"] = sql
        assert timeout_sec == 120
        shutdown_event.set()
        return "UPDATE 1"

    with patch("mqtt_handlers.get_settings", return_value=SimpleNamespace(
        node_offline_timeout_sec=120,
        node_offline_check_interval_sec=1,
    )), patch("mqtt_handlers.execute", new=AsyncMock(side_effect=_execute)), patch(
        "mqtt_handlers.logger.warning", new=Mock()
    ) as warning_mock:
        await monitor_offline_nodes()

    normalized_sql = " ".join(captured_query["sql"].split())
    assert "COALESCE(last_seen_at, last_heartbeat_at, updated_at, created_at)" in normalized_sql
    warning_mock.assert_called()
