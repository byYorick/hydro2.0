"""Unit tests for application.execution_decision helpers."""

from unittest.mock import AsyncMock

import pytest

from domain.models.decision_models import DecisionOutcome
from application.execution_decision import run_decision_phase


@pytest.mark.asyncio
async def test_run_decision_phase_without_climate_guard():
    decide_action = lambda _task_type, _payload: DecisionOutcome(
        action_required=False,
        decision="skip",
        reason_code="ok",
        reason="ok",
    )
    apply_guards = AsyncMock()
    emit_event = AsyncMock(return_value=None)

    decision = await run_decision_phase(
        zone_id=1,
        task_type="diagnostics",
        payload={},
        context={},
        auto_logic_climate_guards_v1=True,
        decide_action_fn=decide_action,
        apply_ventilation_climate_guards_fn=apply_guards,
        emit_task_event_fn=emit_event,
        build_decision_payload_fn=lambda d: {"decision": d.decision},
    )
    assert decision.decision == "skip"
    apply_guards.assert_not_awaited()
    emit_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_decision_phase_with_ventilation_climate_guard():
    base = DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok")
    guarded = DecisionOutcome(action_required=False, decision="skip", reason_code="wind_blocked", reason="x")
    apply_guards = AsyncMock(return_value=guarded)

    decision = await run_decision_phase(
        zone_id=1,
        task_type="ventilation",
        payload={},
        context={},
        auto_logic_climate_guards_v1=True,
        decide_action_fn=lambda _t, _p: base,
        apply_ventilation_climate_guards_fn=apply_guards,
        emit_task_event_fn=AsyncMock(return_value=None),
        build_decision_payload_fn=lambda d: {"decision": d.decision},
    )
    assert decision.reason_code == "wind_blocked"
    apply_guards.assert_awaited_once()
