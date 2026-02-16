"""Unit tests for application.no_action_branch helpers."""

from unittest.mock import AsyncMock, Mock

import pytest

from domain.models.decision_models import DecisionOutcome
from application.no_action_branch import execute_no_action_branch


@pytest.mark.asyncio
async def test_execute_no_action_branch_handles_retry_and_next_due():
    decision = DecisionOutcome(
        action_required=False,
        decision="retry",
        reason_code="low_water",
        reason="x",
    )
    emit_alert = AsyncMock(return_value=None)
    result = await execute_no_action_branch(
        zone_id=1,
        task_type="diagnostics",
        payload={},
        context={},
        decision=decision,
        build_no_action_result_fn=lambda task_type, decision, retry_enqueue: {
            "task_type": task_type,
            "decision": decision.decision,
            "retry_enqueued": retry_enqueue,
        },
        extract_next_due_at_fn=lambda _d, _r: "2026-02-16T12:00:00",
        enqueue_decision_retry_fn=AsyncMock(return_value={"status": "queued"}),
        should_emit_decision_alert_fn=lambda _r: True,
        emit_decision_alert_fn=emit_alert,
    )
    assert result["retry_enqueued"]["status"] == "queued"
    assert result["next_due_at"] == "2026-02-16T12:00:00"
    emit_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_no_action_branch_skips_alert_when_not_needed():
    decision = DecisionOutcome(
        action_required=False,
        decision="skip",
        reason_code="ok",
        reason="ok",
    )
    emit_alert = AsyncMock(return_value=None)
    enqueue_retry = AsyncMock(return_value=None)
    result = await execute_no_action_branch(
        zone_id=1,
        task_type="diagnostics",
        payload={},
        context={},
        decision=decision,
        build_no_action_result_fn=lambda task_type, decision, retry_enqueue: {
            "task_type": task_type,
            "decision": decision.decision,
            "retry_enqueued": retry_enqueue,
        },
        extract_next_due_at_fn=lambda _d, _r: None,
        enqueue_decision_retry_fn=enqueue_retry,
        should_emit_decision_alert_fn=lambda _r: False,
        emit_decision_alert_fn=emit_alert,
    )
    assert result["decision"] == "skip"
    enqueue_retry.assert_not_awaited()
    emit_alert.assert_not_awaited()
