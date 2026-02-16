"""Helpers for scheduler execution decision phase."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from domain.models.decision_models import DecisionOutcome

DecideActionFn = Callable[[str, Dict[str, Any]], DecisionOutcome]
ApplyVentilationClimateGuardsFn = Callable[..., Awaitable[DecisionOutcome]]
EmitTaskEventFn = Callable[..., Awaitable[None]]
BuildDecisionPayloadFn = Callable[[DecisionOutcome], Dict[str, Any]]


async def run_decision_phase(
    *,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    auto_logic_climate_guards_v1: bool,
    decide_action_fn: DecideActionFn,
    apply_ventilation_climate_guards_fn: ApplyVentilationClimateGuardsFn,
    emit_task_event_fn: EmitTaskEventFn,
    build_decision_payload_fn: BuildDecisionPayloadFn,
) -> DecisionOutcome:
    decision = decide_action_fn(task_type, payload)
    if auto_logic_climate_guards_v1 and task_type == "ventilation":
        decision = await apply_ventilation_climate_guards_fn(
            zone_id=zone_id,
            payload=payload,
            decision=decision,
        )
    await emit_task_event_fn(
        zone_id=zone_id,
        task_type=task_type,
        context=context,
        event_type="DECISION_MADE",
        payload=build_decision_payload_fn(decision),
    )
    return decision


__all__ = ["run_decision_phase"]
