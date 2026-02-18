"""Unit tests for application.command_publish_batch helpers."""

from unittest.mock import AsyncMock, Mock

import pytest

from domain.models.decision_models import DecisionOutcome
from application.command_publish_batch import publish_batch


@pytest.mark.asyncio
async def test_publish_batch_non_closed_loop_success():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=True)
    emit_event = AsyncMock(return_value=None)
    result = await publish_batch(
        zone_id=1,
        task_type="irrigation",
        nodes=[{"node_uid": "nd-1", "channel": "pump_main"}],
        cmd="set",
        params={"state": True},
        context={"task_id": "st-1", "correlation_id": "corr-1"},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok"),
        accepted_terminal_statuses=None,
        command_bus=command_bus,
        task_execute_closed_loop_enforce=False,
        task_execute_closed_loop_timeout_sec=10,
        err_command_send_failed="command_send_failed",
        err_command_tracker_unavailable="command_tracker_unavailable",
        err_command_effect_not_confirmed="command_effect_not_confirmed",
        terminal_status_to_error_code_fn=lambda status: status.lower(),
        emit_task_event_fn=emit_event,
    )
    assert result["success"] is True
    assert result["commands_failed"] == 0
    assert emit_event.await_count == 1


@pytest.mark.asyncio
async def test_publish_batch_non_closed_loop_failure_emits_failed_event():
    command_bus = Mock()
    command_bus.publish_command = AsyncMock(return_value=False)
    emit_event = AsyncMock(return_value=None)
    result = await publish_batch(
        zone_id=2,
        task_type="irrigation",
        nodes=[{"node_uid": "nd-2", "channel": "pump_main"}],
        cmd="set",
        params={"state": True},
        context={"task_id": "st-2", "correlation_id": "corr-2"},
        decision=DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok"),
        accepted_terminal_statuses=None,
        command_bus=command_bus,
        task_execute_closed_loop_enforce=False,
        task_execute_closed_loop_timeout_sec=10,
        err_command_send_failed="command_send_failed",
        err_command_tracker_unavailable="command_tracker_unavailable",
        err_command_effect_not_confirmed="command_effect_not_confirmed",
        terminal_status_to_error_code_fn=lambda status: status.lower(),
        emit_task_event_fn=emit_event,
    )
    assert result["success"] is False
    assert result["commands_failed"] == 1
    assert result["error_code"] == "send_failed"
    assert emit_event.await_count == 2
    failed_event = emit_event.await_args_list[1].kwargs
    assert failed_event["event_type"] == "COMMAND_FAILED"
