"""Extracted workflow core implementation.

This module is imported lazily from SchedulerTaskExecutor to keep startup import-order stable.
"""

from __future__ import annotations

from application.scheduler_executor_impl import *  # noqa: F401,F403


async def execute_three_tank_startup_workflow_core(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: DecisionOutcome,
) -> Dict[str, Any]:
    workflow = self._extract_workflow(payload)
    if workflow not in {"startup", "cycle_start", "refill_check"}:
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "three_tank_unknown_workflow",
            "workflow": workflow,
            "commands_total": 0,
            "commands_failed": 0,
            "action_required": True,
            "decision": "fail",
            "reason_code": "unsupported_workflow",
            "reason": f"Неподдерживаемый workflow для топологии three_tank: {workflow or '<missing>'}",
            "error": "unsupported_workflow",
            "error_code": "unsupported_workflow",
        }

    fallback_workflow = "refill_check" if workflow == "refill_check" else "cycle_start"
    payload_for_cycle_start = dict(payload)
    payload_for_cycle_start["workflow"] = fallback_workflow

    result = await self._execute_cycle_start_workflow(
        zone_id=zone_id,
        payload=payload_for_cycle_start,
        context=context,
        decision=decision,
    )
    mode_map = {
        "cycle_start": "three_tank_startup",
        "cycle_start_ready": "three_tank_startup_ready",
        "cycle_start_refill_timeout": "three_tank_startup_refill_timeout",
        "cycle_start_refill_started_without_check": "three_tank_startup_refill_started_without_check",
        "cycle_start_refill_in_progress": "three_tank_startup_refill_in_progress",
    }
    raw_mode = str(result.get("mode") or "")
    if raw_mode in mode_map:
        result["mode"] = mode_map[raw_mode]
    result["topology"] = self._extract_topology(payload) or "three_tank_drip_substrate_trays"
    result["workflow"] = workflow
    if bool(result.get("success")):
        if raw_mode == "cycle_start_ready":
            await self._update_zone_workflow_phase(
                zone_id=zone_id,
                workflow_phase=WORKFLOW_PHASE_READY,
                workflow_stage="startup",
                reason_code=result.get("reason_code"),
                context=context,
            )
        elif raw_mode in {"cycle_start_refill_started_without_check", "cycle_start_refill_in_progress"}:
            await self._update_zone_workflow_phase(
                zone_id=zone_id,
                workflow_phase=WORKFLOW_PHASE_TANK_FILLING,
                workflow_stage="startup",
                reason_code=result.get("reason_code"),
                context=context,
            )
    return result
