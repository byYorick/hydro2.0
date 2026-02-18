"""Unit tests for application.decision_alerts helpers."""

from unittest.mock import AsyncMock

import pytest

from domain.models.decision_models import DecisionOutcome
from application.decision_alerts import emit_decision_alert, should_emit_decision_alert


def test_should_emit_decision_alert_for_known_reason_codes():
    assert should_emit_decision_alert("low_water") is True
    assert should_emit_decision_alert("nodes_unavailable") is True
    assert should_emit_decision_alert("other") is False


@pytest.mark.asyncio
async def test_emit_decision_alert_builds_expected_payload():
    send_infra_alert_fn = AsyncMock(return_value=True)
    decision = DecisionOutcome(
        action_required=False,
        decision="retry",
        reason_code="low_water",
        reason="x",
    )
    await emit_decision_alert(
        zone_id=5,
        task_type="diagnostics",
        decision=decision,
        result={"next_due_at": "2026-02-16T12:00:00"},
        send_infra_alert_fn=send_infra_alert_fn,
    )
    send_infra_alert_fn.assert_awaited_once()
    kwargs = send_infra_alert_fn.await_args.kwargs
    assert kwargs["code"] == "infra_diagnostics_low_water"
    assert kwargs["severity"] == "warning"
