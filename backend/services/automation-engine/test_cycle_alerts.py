"""Unit tests for application.cycle_alerts helpers."""

from unittest.mock import AsyncMock

import pytest

from application.cycle_alerts import emit_cycle_alert


@pytest.mark.asyncio
async def test_emit_cycle_alert_forwards_expected_payload():
    send_infra_alert_fn = AsyncMock(return_value=True)

    await emit_cycle_alert(
        zone_id=28,
        code="infra_cycle_start_nodes_unavailable",
        message="nodes missing",
        severity="error",
        details={"workflow": "cycle_start"},
        send_infra_alert_fn=send_infra_alert_fn,
    )

    send_infra_alert_fn.assert_awaited_once()
    kwargs = send_infra_alert_fn.await_args.kwargs
    assert kwargs["code"] == "infra_cycle_start_nodes_unavailable"
    assert kwargs["alert_type"] == "Automation Cycle Start"
    assert kwargs["zone_id"] == 28
    assert kwargs["service"] == "automation-engine"
    assert kwargs["component"] == "scheduler_task_executor"
    assert kwargs["error_type"] == "infra_cycle_start_nodes_unavailable"
