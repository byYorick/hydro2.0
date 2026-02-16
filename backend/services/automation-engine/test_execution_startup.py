"""Unit tests for application.execution_startup helpers."""

from unittest.mock import AsyncMock

import pytest

from application.execution_startup import emit_execution_started_events


@pytest.mark.asyncio
async def test_emit_execution_started_events_emits_expected_sequence():
    emit_task_event = AsyncMock(return_value=None)
    create_event = AsyncMock(return_value=True)

    await emit_execution_started_events(
        zone_id=9,
        task_type="diagnostics",
        payload={"workflow": "startup"},
        context={"task_id": "st-9"},
        emit_task_event_fn=emit_task_event,
        create_zone_event_safe_fn=create_event,
        build_task_received_payload_fn=lambda **kwargs: {"wrapped": kwargs["payload"]},
        build_execution_started_zone_event_payload_fn=lambda **kwargs: {"task_type": kwargs["task_type"]},
    )

    assert emit_task_event.await_count == 2
    create_event.assert_awaited_once()
    first_call = emit_task_event.await_args_list[0].kwargs
    second_call = emit_task_event.await_args_list[1].kwargs
    assert first_call["event_type"] == "TASK_RECEIVED"
    assert second_call["event_type"] == "TASK_STARTED"
