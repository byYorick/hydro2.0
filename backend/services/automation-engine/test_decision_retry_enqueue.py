"""Unit tests for application.decision_retry_enqueue helpers."""

from unittest.mock import AsyncMock, Mock

import pytest

from domain.models.decision_models import DecisionOutcome
from application.decision_retry_enqueue import enqueue_decision_retry


@pytest.mark.asyncio
async def test_enqueue_decision_retry_success():
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
        enqueue_task_fn=AsyncMock(return_value={"status": "queued"}),
        log_warning=Mock(),
    )
    assert result["status"] == "queued"


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
    assert result["status"] == "failed"
    assert "bad enqueue" in result["error"]
