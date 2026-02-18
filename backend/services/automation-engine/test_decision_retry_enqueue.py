"""Unit tests for application.decision_retry_enqueue helpers."""

from unittest.mock import AsyncMock, Mock

import pytest

from domain.models.decision_models import DecisionOutcome
from application.decision_retry_enqueue import enqueue_decision_retry
from services.resilience_contract import (
    SCHEDULER_RETRY_REASON_PAYLOAD_KEY,
    SCHEDULER_RETRY_SOURCE,
    SCHEDULER_RETRY_STATUS_FAILED,
)


@pytest.mark.asyncio
async def test_enqueue_decision_retry_success():
    enqueue_task_fn = AsyncMock(return_value={"status": "queued"})
    decision = DecisionOutcome(
        action_required=False,
        decision="retry",
        reason_code="low_water",
        reason="x",
        details={"retry_attempt": 2},
    )
    result = await enqueue_decision_retry(
        zone_id=1,
        task_type="diagnostics",
        payload={},
        decision=decision,
        context={"correlation_id": "corr-1"},
        safe_int_fn=lambda v: int(v) if v is not None else None,
        extract_next_due_at_fn=lambda _d, _r: "2026-02-16T12:00:00",
        build_correlation_id_fn=lambda **kwargs: f"corr-{kwargs['zone_id']}",
        enqueue_task_fn=enqueue_task_fn,
        log_warning=Mock(),
    )
    assert result["status"] == "queued"
    kwargs = enqueue_task_fn.await_args.kwargs
    assert kwargs["source"] == SCHEDULER_RETRY_SOURCE
    assert kwargs["payload"][SCHEDULER_RETRY_REASON_PAYLOAD_KEY] == "low_water"


@pytest.mark.asyncio
async def test_enqueue_decision_retry_handles_enqueue_value_error():
    decision = DecisionOutcome(
        action_required=False,
        decision="retry",
        reason_code="low_water",
        reason="x",
        details={"retry_attempt": 2},
    )
    result = await enqueue_decision_retry(
        zone_id=1,
        task_type="diagnostics",
        payload={},
        decision=decision,
        context={"correlation_id": "corr-1"},
        safe_int_fn=lambda v: int(v) if v is not None else None,
        extract_next_due_at_fn=lambda _d, _r: "2026-02-16T12:00:00",
        build_correlation_id_fn=lambda **kwargs: f"corr-{kwargs['zone_id']}",
        enqueue_task_fn=AsyncMock(side_effect=ValueError("bad enqueue")),
        log_warning=Mock(),
    )
    assert result["status"] == SCHEDULER_RETRY_STATUS_FAILED
    assert "bad enqueue" in result["error"]
