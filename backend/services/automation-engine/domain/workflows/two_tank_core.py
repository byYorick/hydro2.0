"""Extracted two-tank workflow coordinator.

This module is imported lazily from SchedulerTaskExecutor to keep startup import-order stable.
"""

from __future__ import annotations

from application.scheduler_executor_impl import *  # noqa: F401,F403


TWO_TANK_STARTUP_WORKFLOWS = {
    "startup",
    "clean_fill_check",
    "solution_fill_check",
    "prepare_recirculation",
    "prepare_recirculation_check",
}

TWO_TANK_RECOVERY_WORKFLOWS = {
    "irrigation_recovery",
    "irrigation_recovery_check",
}

TWO_TANK_SUPPORTED_WORKFLOWS = TWO_TANK_STARTUP_WORKFLOWS | TWO_TANK_RECOVERY_WORKFLOWS


async def execute_two_tank_startup_workflow_core(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: DecisionOutcome,
) -> Dict[str, Any]:
    runtime_cfg = self._resolve_two_tank_runtime_config(payload)
    workflow = self._normalize_two_tank_workflow(payload)

    if workflow not in TWO_TANK_SUPPORTED_WORKFLOWS:
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_unknown_workflow",
            "workflow": workflow,
            "commands_total": 0,
            "commands_failed": 0,
            "action_required": True,
            "decision": "run",
            "reason_code": "unsupported_workflow",
            "reason": f"Неподдерживаемый workflow для топологии two_tank: {workflow or '<missing>'}",
            "error": "unsupported_workflow",
            "error_code": "unsupported_workflow",
        }

    await self._emit_task_event(
        zone_id=zone_id,
        task_type="diagnostics",
        context=context,
        event_type="TWO_TANK_STARTUP_INITIATED",
        payload={
            "workflow": workflow,
            "topology": self._extract_topology(payload),
            "action_required": decision.action_required,
            "decision": decision.decision,
            "reason_code": decision.reason_code,
        },
    )

    stage_phase = WORKFLOW_STAGE_TO_PHASE.get(workflow)
    if stage_phase:
        await self._update_zone_workflow_phase(
            zone_id=zone_id,
            workflow_phase=stage_phase,
            workflow_stage=workflow,
            reason_code=decision.reason_code,
            context=context,
        )

    nodes_state = await self._check_required_nodes_online(zone_id, runtime_cfg["required_node_types"])
    if nodes_state["missing_types"]:
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_required_nodes_missing",
            "workflow": workflow,
            "commands_total": 0,
            "commands_failed": 0,
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_CYCLE_BLOCKED_NODES_UNAVAILABLE,
            "reason": "Нет online-нод, необходимых для startup 2-бакового контура",
            "error": ERR_CYCLE_REQUIRED_NODES_UNAVAILABLE,
            "error_code": ERR_CYCLE_REQUIRED_NODES_UNAVAILABLE,
            "missing_node_types": nodes_state["missing_types"],
        }

    if workflow in TWO_TANK_STARTUP_WORKFLOWS:
        from domain.workflows.two_tank_startup_core import execute_two_tank_startup_branch

        return await execute_two_tank_startup_branch(
            self,
            zone_id=zone_id,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
            workflow=workflow,
        )

    if workflow in TWO_TANK_RECOVERY_WORKFLOWS:
        from domain.workflows.two_tank_recovery_core import execute_two_tank_recovery_branch

        return await execute_two_tank_recovery_branch(
            self,
            zone_id=zone_id,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
            workflow=workflow,
        )

    return {
        "success": False,
        "task_type": "diagnostics",
        "mode": "two_tank_unknown_workflow",
        "workflow": workflow,
        "commands_total": 0,
        "commands_failed": 0,
        "action_required": True,
        "decision": "run",
        "reason_code": "unsupported_workflow",
        "reason": f"Неподдерживаемый workflow для топологии two_tank: {workflow}",
        "error": "unsupported_workflow",
        "error_code": "unsupported_workflow",
    }
