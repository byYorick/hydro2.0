"""Unit tests for application.execution_finalize helpers."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from domain.models.decision_models import DecisionOutcome
from application.execution_finalize import finalize_execution


@pytest.mark.asyncio
async def test_finalize_execution_with_extended_outcome_enabled():
    decision = DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok")
    result = await finalize_execution(
        zone_id=1,
        task_type="diagnostics",
        payload={"workflow": "startup"},
        context={"task_id": "st-1", "correlation_id": "corr-1"},
        decision=decision,
        result={"success": True},
        execute_started_at=datetime(2026, 2, 16, 0, 0, 0),
        auto_logic_extended_outcome_v1=True,
        ensure_extended_outcome_fn=lambda **kwargs: {**kwargs["result"], "extended": True},
        workflow_state_sync_fn=AsyncMock(return_value=None),
        emit_task_event_fn=AsyncMock(return_value=None),
        create_zone_event_safe_fn=AsyncMock(return_value=True),
        build_task_finished_payload_fn=lambda r: {"result": r},
        build_execution_finished_zone_event_payload_fn=lambda **kwargs: {"task_type": kwargs["task_type"]},
        log_execution_finished_fn=Mock(),
    )
    assert result["extended"] is True


@pytest.mark.asyncio
async def test_finalize_execution_without_extended_outcome():
    sync = AsyncMock(return_value=None)
    emit_event = AsyncMock(return_value=None)
    create_event = AsyncMock(return_value=True)
    log_finish = Mock()
    decision = DecisionOutcome(action_required=False, decision="skip", reason_code="ok", reason="ok")

    result = await finalize_execution(
        zone_id=2,
        task_type="irrigation",
        payload={},
        context={},
        decision=decision,
        result={"success": True},
        execute_started_at=datetime(2026, 2, 16, 0, 0, 0),
        auto_logic_extended_outcome_v1=False,
        ensure_extended_outcome_fn=lambda **kwargs: {"unexpected": True},
        workflow_state_sync_fn=sync,
        emit_task_event_fn=emit_event,
        create_zone_event_safe_fn=create_event,
        build_task_finished_payload_fn=lambda r: {"result": r},
        build_execution_finished_zone_event_payload_fn=lambda **kwargs: {"x": 1},
        log_execution_finished_fn=log_finish,
    )
    assert result["success"] is True
    sync.assert_awaited_once()
    emit_event.assert_awaited_once()
    create_event.assert_awaited_once()
    log_finish.assert_called_once()
