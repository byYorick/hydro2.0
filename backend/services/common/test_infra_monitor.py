from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from common import infra_monitor


def _reset_state() -> None:
    for state in infra_monitor._infra_state.values():
        state["status"] = "unknown"
        state["last_check"] = None
        state["alert_sent"] = False


@pytest.mark.asyncio
async def test_check_service_health_sends_scoped_active_and_resolved_alerts() -> None:
    _reset_state()

    with patch("common.infra_monitor.send_infra_alert", new_callable=AsyncMock) as mock_active, \
         patch("common.infra_monitor.send_infra_resolved_alert", new_callable=AsyncMock) as mock_resolved:
        mock_active.return_value = True
        mock_resolved.return_value = True

        await infra_monitor.check_service_health("history_logger", available=False)
        await infra_monitor.check_service_health("history_logger", available=True)

    mock_active.assert_awaited_once()
    active_kwargs = mock_active.await_args.kwargs
    assert active_kwargs["service"] == "history_logger"
    assert active_kwargs["component"] == "history_logger"

    mock_resolved.assert_awaited_once()
    resolved_kwargs = mock_resolved.await_args.kwargs
    assert resolved_kwargs["service"] == "history_logger"
    assert resolved_kwargs["component"] == "history_logger"
