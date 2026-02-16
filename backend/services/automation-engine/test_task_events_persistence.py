"""Unit tests for application.task_events_persistence helpers."""

from unittest.mock import AsyncMock, Mock

import pytest

from application.task_events_persistence import persist_zone_event_safe


@pytest.mark.asyncio
async def test_persist_zone_event_safe_returns_true_when_event_created():
    create_zone_event_fn = AsyncMock(return_value=True)
    send_infra_alert_fn = AsyncMock(return_value=True)
    log_warning = Mock()

    result = await persist_zone_event_safe(
        zone_id=7,
        event_type="WORKFLOW_PHASE_UPDATED",
        payload={"x": 1},
        task_type="diagnostics",
        context={"task_id": "st-7", "correlation_id": "corr-7"},
        create_zone_event_fn=create_zone_event_fn,
        send_infra_alert_fn=send_infra_alert_fn,
        log_warning=log_warning,
    )

    assert result is True
    create_zone_event_fn.assert_awaited_once_with(7, "WORKFLOW_PHASE_UPDATED", {"x": 1})
    send_infra_alert_fn.assert_not_awaited()
    log_warning.assert_not_called()


@pytest.mark.asyncio
async def test_persist_zone_event_safe_alerts_and_returns_false_on_error():
    create_zone_event_fn = AsyncMock(side_effect=RuntimeError("db down"))
    send_infra_alert_fn = AsyncMock(return_value=True)
    log_warning = Mock()

    result = await persist_zone_event_safe(
        zone_id=9,
        event_type="SOME_EVENT",
        payload={"k": "v"},
        task_type="irrigation",
        context={"task_id": "st-9", "correlation_id": "corr-9"},
        create_zone_event_fn=create_zone_event_fn,
        send_infra_alert_fn=send_infra_alert_fn,
        log_warning=log_warning,
    )

    assert result is False
    log_warning.assert_called_once()
    send_infra_alert_fn.assert_awaited_once()
    kwargs = send_infra_alert_fn.await_args.kwargs
    assert kwargs["code"] == "infra_scheduler_task_event_persist_failed"
    assert kwargs["zone_id"] == 9
    assert kwargs["details"]["task_id"] == "st-9"
    assert kwargs["details"]["correlation_id"] == "corr-9"
