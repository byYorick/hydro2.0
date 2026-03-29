from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from common.error_handler import NodeErrorHandler


@pytest.mark.asyncio
async def test_node_error_handler_uses_alert_publisher_with_dedupe_key() -> None:
    handler = NodeErrorHandler()

    with patch("common.error_handler.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("common.error_handler._alert_publisher.raise_active", new_callable=AsyncMock) as mock_raise:
        mock_fetch.return_value = [{"id": 1, "zone_id": 8, "zone_id_check": 8}]
        mock_raise.return_value = True

        await handler._create_alert(
            node_uid="nd-test-1",
            level="critical",
            component="sensor",
            error_code="timeout",
            message="Sensor timeout",
            details={"ts": 1710000000},
        )

    mock_raise.assert_awaited_once()
    kwargs = mock_raise.await_args.kwargs
    assert kwargs["zone_id"] == 8
    assert kwargs["source"] == "node"
    assert kwargs["code"] == "node_error_sensor_timeout"
    assert kwargs["scoped"] is True
    assert kwargs["dedupe_key"] == kwargs["details"]["dedupe_key"]
    assert "node_uid:nd-test-1" in kwargs["dedupe_key"]
    assert kwargs["ts_device"].endswith("+00:00")
