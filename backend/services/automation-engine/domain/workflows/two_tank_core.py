"""Extracted two-tank workflow coordinator.

This module is imported lazily from SchedulerTaskExecutor to keep startup import-order stable.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from application.scheduler_executor_impl import *  # noqa: F401,F403
from domain.workflows.two_tank_irr_state_helpers import (
    request_irr_state_snapshot_best_effort,
    validate_irr_state_expected_vs_actual,
)

_logger = logging.getLogger(__name__)


TWO_TANK_STARTUP_WORKFLOWS = {
    "startup",
    "clean_fill_check",
    "solution_fill_check",
    "prepare_recirculation",
    "prepare_recirculation_check",
    "manual_step",
}

TWO_TANK_RECOVERY_WORKFLOWS = {
    "irrigation_recovery",
    "irrigation_recovery_check",
}

TWO_TANK_SUPPORTED_WORKFLOWS = TWO_TANK_STARTUP_WORKFLOWS | TWO_TANK_RECOVERY_WORKFLOWS

_CRITICAL_IRR_STATE_EXPECTATIONS: Dict[str, Dict[str, bool]] = {
    "startup": {
        "pump_main": False,
    },
    "solution_fill_check": {
        "valve_clean_supply": True,
        "valve_solution_fill": True,
        "pump_main": True,
    },
    "prepare_recirculation_check": {
        "valve_solution_supply": True,
        "valve_solution_fill": True,
        "pump_main": True,
    },
    "irrigation_recovery_check": {
        "valve_solution_supply": True,
        "valve_solution_fill": True,
        "valve_irrigation": False,
        "pump_main": True,
    },
}

_MANUAL_STEP_TO_COMMAND_PLAN: Dict[str, str] = {
    "clean_fill_start": "clean_fill_start",
    "clean_fill_stop": "clean_fill_stop",
    "solution_fill_start": "solution_fill_start",
    "solution_fill_stop": "solution_fill_stop",
    "prepare_recirculation_start": "prepare_recirculation_start",
    "prepare_recirculation_stop": "prepare_recirculation_stop",
    "irrigation_recovery_start": "irrigation_recovery_start",
    "irrigation_recovery_stop": "irrigation_recovery_stop",
}

_MANUAL_STEP_TO_PHASE: Dict[str, str] = {
    "clean_fill_start": "tank_filling",
    "clean_fill_stop": "idle",
    "solution_fill_start": "tank_filling",
    "solution_fill_stop": "idle",
    "prepare_recirculation_start": "tank_recirc",
    "prepare_recirculation_stop": "idle",
    "irrigation_recovery_start": "irrig_recirc",
    "irrigation_recovery_stop": "idle",
}


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

    if workflow == "manual_step":
        manual_step = str(payload.get("manual_step") or "").strip().lower()
        command_plan_name = _MANUAL_STEP_TO_COMMAND_PLAN.get(manual_step)
        if not command_plan_name:
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_manual_step_unsupported",
                "workflow": workflow,
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": True,
                "decision": "run",
                "reason_code": "manual_step_unsupported",
                "reason": f"Неподдерживаемый manual_step: {manual_step or '<missing>'}",
                "error": "manual_step_unsupported",
                "error_code": "manual_step_unsupported",
                "manual_step": manual_step or None,
            }

        phase = _MANUAL_STEP_TO_PHASE.get(manual_step)
        if phase:
            await self._update_zone_workflow_phase(
                zone_id=zone_id,
                workflow_phase=phase,
                workflow_stage="manual_step",
                reason_code="manual_step_requested",
                context=context,
            )

        await self._emit_task_event(
            zone_id=zone_id,
            task_type="diagnostics",
            context=context,
            event_type="MANUAL_STEP_REQUESTED",
            payload={
                "workflow": workflow,
                "manual_step": manual_step,
                "command_plan": command_plan_name,
                "reason_code": "manual_step_requested",
            },
        )

        command_plan = runtime_cfg["commands"].get(command_plan_name)
        if not isinstance(command_plan, list) or not command_plan:
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_manual_step_failed",
                "workflow": workflow,
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": True,
                "decision": "run",
                "reason_code": "manual_step_command_plan_missing",
                "reason": f"Не найден command plan для manual step: {manual_step}",
                "error": "manual_step_command_plan_missing",
                "error_code": "manual_step_command_plan_missing",
                "manual_step": manual_step,
                "workflow_phase": phase,
            }

        plan_result = await self._dispatch_two_tank_command_plan(
            zone_id=zone_id,
            command_plan=command_plan,
            context=context,
            decision=DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code="manual_step_requested",
                reason=f"Выполнение manual step: {manual_step}",
            ),
        )
        if not plan_result.get("success"):
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_manual_step_failed",
                "workflow": workflow,
                "commands_total": plan_result.get("commands_total", 0),
                "commands_failed": plan_result.get("commands_failed", 1),
                "command_statuses": plan_result.get("command_statuses", []),
                "action_required": True,
                "decision": "run",
                "reason_code": "manual_step_failed",
                "reason": f"Не удалось выполнить manual step: {manual_step}",
                "error": str(plan_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED),
                "error_code": str(plan_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED),
                "manual_step": manual_step,
                "workflow_phase": phase,
            }

        await self._emit_task_event(
            zone_id=zone_id,
            task_type="diagnostics",
            context=context,
            event_type="MANUAL_STEP_EXECUTED",
            payload={
                "workflow": workflow,
                "manual_step": manual_step,
                "command_plan": command_plan_name,
                "commands_total": plan_result.get("commands_total", 0),
                "commands_effect_confirmed": plan_result.get("commands_effect_confirmed", 0),
                "commands_failed": plan_result.get("commands_failed", 0),
                "reason_code": "manual_step_executed",
            },
        )

        return {
            "success": True,
            "task_type": "diagnostics",
            "mode": "two_tank_manual_step_executed",
            "workflow": workflow,
            "manual_step": manual_step,
            "workflow_phase": phase,
            "commands_total": plan_result.get("commands_total", 0),
            "commands_failed": plan_result.get("commands_failed", 0),
            "commands_effect_confirmed": plan_result.get("commands_effect_confirmed", 0),
            "command_statuses": plan_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": "manual_step_executed",
            "reason": f"Manual step выполнен: {manual_step}",
        }

    state_cmd_id = await request_irr_state_snapshot_best_effort(
        self,
        zone_id=zone_id,
        workflow=workflow,
    )
    irr_state_guard_result = await validate_irr_state_expected_vs_actual(
        self,
        zone_id=zone_id,
        workflow=workflow,
        runtime_cfg=runtime_cfg,
        critical_expectations=_CRITICAL_IRR_STATE_EXPECTATIONS,
        requested_state_cmd_id=state_cmd_id,
    )
    if irr_state_guard_result is not None:
        return irr_state_guard_result

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
