"""Prepare-recirculation starter for two-tank workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from common.pump_safety import can_run_pump
from executor.two_tank_phase_starters_types import (
    CompensateStartEnqueueFailureFn,
    DispatchSensorModeFn,
    DispatchTwoTankCommandPlanFn,
    EnqueueTwoTankCheckFn,
    MergeDispatchResultsFn,
    TwoTankSafetyGuardsEnabledFn,
    UpdateWorkflowPhaseFn,
)
from domain.models.decision_models import DecisionOutcome


def _resolve_primary_pump_channel(command_plan: Any) -> str:
    if isinstance(command_plan, list):
        for item in command_plan:
            if not isinstance(item, dict):
                continue
            channel = str(item.get("channel") or "").strip().lower()
            if channel.startswith("pump"):
                return channel
    return "pump_main"


async def start_two_tank_prepare_recirculation(
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    dispatch_two_tank_command_plan_fn: DispatchTwoTankCommandPlanFn,
    dispatch_sensor_mode_command_for_nodes_fn: DispatchSensorModeFn,
    merge_command_dispatch_results_fn: MergeDispatchResultsFn,
    update_zone_workflow_phase_fn: UpdateWorkflowPhaseFn,
    enqueue_two_tank_check_fn: EnqueueTwoTankCheckFn,
    compensate_two_tank_start_enqueue_failure_fn: CompensateStartEnqueueFailureFn,
    two_tank_safety_guards_enabled_fn: TwoTankSafetyGuardsEnabledFn,
    workflow_phase_tank_recirc: str,
    reason_prepare_recirculation_started: str,
    reason_cycle_refill_command_failed: str,
    reason_cycle_self_task_enqueue_failed: str,
    err_two_tank_command_failed: str,
    err_two_tank_enqueue_failed: str,
) -> Dict[str, Any]:
    safety_guards_enabled = bool(two_tank_safety_guards_enabled_fn())
    if safety_guards_enabled:
        pump_channel = _resolve_primary_pump_channel(runtime_cfg["commands"].get("prepare_recirculation_start"))
        can_run, safety_error = await can_run_pump(zone_id=zone_id, pump_channel=pump_channel)
        if not can_run:
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_prepare_recirculation_safety_blocked",
                "workflow": "prepare_recirculation",
                "commands_total": 0,
                "commands_failed": 0,
                "command_statuses": [],
                "action_required": True,
                "decision": "run",
                "reason_code": "safety_blocked",
                "reason": "Запуск prepare_recirculation заблокирован safety policy",
                "error": str(safety_error or "two_tank_pump_safety_blocked"),
                "error_code": "two_tank_pump_safety_blocked",
                "pump_channel": pump_channel,
                "safety_error": str(safety_error or ""),
                "feature_flag_state": safety_guards_enabled,
            }

    plan_result = await dispatch_two_tank_command_plan_fn(
        zone_id=zone_id,
        command_plan=runtime_cfg["commands"]["prepare_recirculation_start"],
        context=context,
        decision=DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code=reason_prepare_recirculation_started,
            reason="Запуск рециркуляции для подготовки раствора",
        ),
    )
    if not plan_result.get("success"):
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_prepare_recirculation_command_failed",
            "workflow": "prepare_recirculation",
            "commands_total": plan_result.get("commands_total", 0),
            "commands_failed": plan_result.get("commands_failed", 1),
            "command_statuses": plan_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_cycle_refill_command_failed,
            "reason": "Не удалось отправить команды prepare recirculation",
            "error": str(plan_result.get("error") or err_two_tank_command_failed),
            "error_code": str(plan_result.get("error_code") or err_two_tank_command_failed),
        }

    sensor_mode_result = await dispatch_sensor_mode_command_for_nodes_fn(
        zone_id=zone_id,
        context=context,
        decision=DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code=reason_prepare_recirculation_started,
            reason="Активация sensor mode для pH/EC в prepare_recirculation",
        ),
        activate=True,
        reason_code=reason_prepare_recirculation_started,
    )
    start_result = merge_command_dispatch_results_fn(plan_result, sensor_mode_result)
    if not start_result.get("success"):
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_prepare_recirculation_sensor_mode_failed",
            "workflow": "prepare_recirculation",
            "commands_total": start_result.get("commands_total", 0),
            "commands_failed": start_result.get("commands_failed", 1),
            "command_statuses": start_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_cycle_refill_command_failed,
            "reason": "Команды prepare_recirculation отправлены, но sensor mode не подтверждён",
            "error": str(start_result.get("error") or err_two_tank_command_failed),
            "error_code": str(start_result.get("error_code") or err_two_tank_command_failed),
        }

    await update_zone_workflow_phase_fn(
        zone_id=zone_id,
        workflow_phase=workflow_phase_tank_recirc,
        workflow_stage="prepare_recirculation_check",
        reason_code=reason_prepare_recirculation_started,
        context=context,
    )

    phase_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    phase_timeout_at = phase_started_at + timedelta(seconds=runtime_cfg["prepare_recirculation_timeout_sec"])
    try:
        enqueue_result = await enqueue_two_tank_check_fn(
            zone_id=zone_id,
            payload=payload,
            workflow="prepare_recirculation_check",
            phase_started_at=phase_started_at,
            phase_timeout_at=phase_timeout_at,
            poll_interval_sec=runtime_cfg["poll_interval_sec"],
        )
    except ValueError as exc:
        stop_result = await compensate_two_tank_start_enqueue_failure_fn(
            zone_id=zone_id,
            context=context,
            workflow="prepare_recirculation",
            phase="prepare_recirculation_start",
            stop_command_plan=runtime_cfg["commands"]["prepare_recirculation_stop"],
        )
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_prepare_recirculation_enqueue_failed",
            "workflow": "prepare_recirculation",
            "commands_total": start_result.get("commands_total", 0),
            "commands_failed": start_result.get("commands_failed", 0),
            "command_statuses": start_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_cycle_self_task_enqueue_failed,
            "reason": "Команды prepare recirculation отправлены, но self-task не поставлен",
            "error": str(exc),
            "error_code": err_two_tank_enqueue_failed,
            "stop_result": stop_result,
            "feature_flag_state": two_tank_safety_guards_enabled_fn(),
        }

    return {
        "success": True,
        "task_type": "diagnostics",
        "mode": "two_tank_prepare_recirculation_in_progress",
        "workflow": "prepare_recirculation",
        "commands_total": start_result.get("commands_total", 0),
        "commands_failed": start_result.get("commands_failed", 0),
        "command_statuses": start_result.get("command_statuses", []),
        "action_required": True,
        "decision": "run",
        "reason_code": reason_prepare_recirculation_started,
        "reason": "Запущена рециркуляция подготовки раствора",
        "prepare_recirculation_started_at": phase_started_at.isoformat(),
        "prepare_recirculation_timeout_at": phase_timeout_at.isoformat(),
        "next_check": enqueue_result,
    }


__all__ = ["start_two_tank_prepare_recirculation"]
