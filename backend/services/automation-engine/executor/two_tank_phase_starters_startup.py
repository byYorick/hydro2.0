"""Startup phase starters for two-tank workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from common.pump_safety import can_run_pump
from executor.two_tank_common import resolve_primary_pump_channel
from executor.two_tank_phase_starters_prepare import start_two_tank_prepare_recirculation
from executor.two_tank_phase_starters_types import (
    CompensateStartEnqueueFailureFn,
    DispatchSensorModeFn,
    DispatchTwoTankCommandPlanFn,
    EmitTaskEventFn,
    EnqueueTwoTankCheckFn,
    MergeDispatchResultsFn,
    TwoTankSafetyGuardsEnabledFn,
    UpdateWorkflowPhaseFn,
)
from domain.models.decision_models import DecisionOutcome


async def start_two_tank_clean_fill(
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    cycle: int,
    dispatch_two_tank_command_plan_fn: DispatchTwoTankCommandPlanFn,
    enqueue_two_tank_check_fn: EnqueueTwoTankCheckFn,
    compensate_two_tank_start_enqueue_failure_fn: CompensateStartEnqueueFailureFn,
    emit_task_event_fn: EmitTaskEventFn,
    two_tank_safety_guards_enabled_fn: TwoTankSafetyGuardsEnabledFn,
    reason_clean_fill_started: str,
    reason_cycle_refill_command_failed: str,
    reason_cycle_self_task_enqueue_failed: str,
    err_two_tank_command_failed: str,
    err_two_tank_enqueue_failed: str,
) -> Dict[str, Any]:
    plan_result = await dispatch_two_tank_command_plan_fn(
        zone_id=zone_id,
        command_plan=runtime_cfg["commands"]["clean_fill_start"],
        context=context,
        decision=DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code=reason_clean_fill_started,
            reason="Запуск наполнения бака чистой воды",
        ),
    )
    if not plan_result.get("success"):
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_clean_fill_command_failed",
            "workflow": "startup",
            "commands_total": plan_result.get("commands_total", 0),
            "commands_failed": plan_result.get("commands_failed", 1),
            "command_statuses": plan_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_cycle_refill_command_failed,
            "reason": "Не удалось отправить команду наполнения бака чистой воды",
            "error": str(plan_result.get("error") or err_two_tank_command_failed),
            "error_code": str(plan_result.get("error_code") or err_two_tank_command_failed),
        }

    phase_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    phase_timeout_at = phase_started_at + timedelta(seconds=runtime_cfg["clean_fill_timeout_sec"])
    try:
        enqueue_result = await enqueue_two_tank_check_fn(
            zone_id=zone_id,
            payload=payload,
            workflow="clean_fill_check",
            phase_started_at=phase_started_at,
            phase_timeout_at=phase_timeout_at,
            poll_interval_sec=runtime_cfg["poll_interval_sec"],
            phase_cycle=cycle,
        )
    except ValueError as exc:
        stop_result = await compensate_two_tank_start_enqueue_failure_fn(
            zone_id=zone_id,
            context=context,
            workflow="startup",
            phase="clean_fill_start",
            stop_command_plan=runtime_cfg["commands"]["clean_fill_stop"],
        )
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_clean_fill_enqueue_failed",
            "workflow": "startup",
            "commands_total": plan_result.get("commands_total", 0),
            "commands_failed": plan_result.get("commands_failed", 0),
            "command_statuses": plan_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_cycle_self_task_enqueue_failed,
            "reason": "Команда наполнения отправлена, но self-task не поставлен",
            "error": str(exc),
            "error_code": err_two_tank_enqueue_failed,
            "stop_result": stop_result,
            "feature_flag_state": two_tank_safety_guards_enabled_fn(),
        }

    await emit_task_event_fn(
        zone_id=zone_id,
        task_type="diagnostics",
        context=context,
        event_type="CLEAN_FILL_STARTED",
        payload={
            "clean_fill_cycle": cycle,
            "clean_fill_started_at": phase_started_at.isoformat(),
            "clean_fill_timeout_at": phase_timeout_at.isoformat(),
            "next_check": enqueue_result,
            "reason_code": reason_clean_fill_started,
        },
    )

    return {
        "success": True,
        "task_type": "diagnostics",
        "mode": "two_tank_clean_fill_in_progress",
        "workflow": "startup",
        "commands_total": plan_result.get("commands_total", 0),
        "commands_failed": plan_result.get("commands_failed", 0),
        "command_statuses": plan_result.get("command_statuses", []),
        "action_required": True,
        "decision": "run",
        "reason_code": reason_clean_fill_started,
        "reason": "Запущено наполнение бака чистой воды",
        "clean_fill_cycle": cycle,
        "clean_fill_started_at": phase_started_at.isoformat(),
        "clean_fill_timeout_at": phase_timeout_at.isoformat(),
        "next_check": enqueue_result,
    }


async def start_two_tank_solution_fill(
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
    emit_task_event_fn: EmitTaskEventFn,
    two_tank_safety_guards_enabled_fn: TwoTankSafetyGuardsEnabledFn,
    workflow_phase_tank_filling: str,
    reason_solution_fill_started: str,
    reason_cycle_refill_command_failed: str,
    reason_cycle_self_task_enqueue_failed: str,
    err_two_tank_command_failed: str,
    err_two_tank_enqueue_failed: str,
) -> Dict[str, Any]:
    pump_channel = resolve_primary_pump_channel(runtime_cfg["commands"].get("solution_fill_start"))
    sensor_mode_result = await dispatch_sensor_mode_command_for_nodes_fn(
        zone_id=zone_id,
        context=context,
        decision=DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code=reason_solution_fill_started,
            reason="Активация sensor mode для pH/EC в solution_fill",
        ),
        activate=True,
        reason_code=reason_solution_fill_started,
        stabilization_time_sec=int(runtime_cfg.get("sensor_mode_stabilization_time_sec") or 60),
    )
    if not sensor_mode_result.get("success"):
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_solution_fill_sensor_mode_failed",
            "workflow": "startup",
            "commands_total": sensor_mode_result.get("commands_total", 0),
            "commands_failed": sensor_mode_result.get("commands_failed", 1),
            "command_statuses": sensor_mode_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_cycle_refill_command_failed,
            "reason": "Не удалось активировать sensor mode для pH/EC перед solution_fill",
            "error": str(sensor_mode_result.get("error") or err_two_tank_command_failed),
            "error_code": str(sensor_mode_result.get("error_code") or err_two_tank_command_failed),
        }

    can_run, safety_error = await can_run_pump(
        zone_id=zone_id,
        pump_channel=pump_channel,
        telemetry_grace_sec=int(runtime_cfg.get("sensor_mode_telemetry_grace_sec") or 0),
        grace_node_types=["ph", "ec"],
    )
    if not can_run:
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_solution_fill_safety_blocked",
            "workflow": "startup",
            "commands_total": sensor_mode_result.get("commands_total", 0),
            "commands_failed": sensor_mode_result.get("commands_failed", 0),
            "command_statuses": sensor_mode_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": "safety_blocked",
            "reason": "Запуск solution_fill заблокирован safety policy",
            "error": str(safety_error or "two_tank_pump_safety_blocked"),
            "error_code": "two_tank_pump_safety_blocked",
            "pump_channel": pump_channel,
            "safety_error": str(safety_error or ""),
        }

    plan_result = await dispatch_two_tank_command_plan_fn(
        zone_id=zone_id,
        command_plan=runtime_cfg["commands"]["solution_fill_start"],
        decision=DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code=reason_solution_fill_started,
            reason="Запуск наполнения бака рабочего раствора",
        ),
        context=context,
    )
    start_result = merge_command_dispatch_results_fn(plan_result, sensor_mode_result)
    if not plan_result.get("success"):
        stop_result = await compensate_two_tank_start_enqueue_failure_fn(
            zone_id=zone_id,
            context=context,
            workflow="startup",
            phase="solution_fill_start",
            stop_command_plan=runtime_cfg["commands"]["solution_fill_stop"],
        )
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_solution_fill_command_failed",
            "workflow": "startup",
            "commands_total": start_result.get("commands_total", 0),
            "commands_failed": start_result.get("commands_failed", 1),
            "command_statuses": start_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_cycle_refill_command_failed,
            "reason": "Не удалось отправить команды наполнения бака раствора",
            "error": str(start_result.get("error") or err_two_tank_command_failed),
            "error_code": str(start_result.get("error_code") or err_two_tank_command_failed),
            "stop_result": stop_result,
            "feature_flag_state": two_tank_safety_guards_enabled_fn(),
        }

    await update_zone_workflow_phase_fn(
        zone_id=zone_id,
        workflow_phase=workflow_phase_tank_filling,
        workflow_stage="solution_fill_check",
        reason_code=reason_solution_fill_started,
        context=context,
    )

    phase_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    phase_timeout_at = phase_started_at + timedelta(seconds=runtime_cfg["solution_fill_timeout_sec"])
    try:
        enqueue_result = await enqueue_two_tank_check_fn(
            zone_id=zone_id,
            payload=payload,
            workflow="solution_fill_check",
            phase_started_at=phase_started_at,
            phase_timeout_at=phase_timeout_at,
            poll_interval_sec=runtime_cfg["poll_interval_sec"],
        )
    except ValueError as exc:
        stop_result = await compensate_two_tank_start_enqueue_failure_fn(
            zone_id=zone_id,
            context=context,
            workflow="startup",
            phase="solution_fill_start",
            stop_command_plan=runtime_cfg["commands"]["solution_fill_stop"],
        )
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_solution_fill_enqueue_failed",
            "workflow": "startup",
            "commands_total": start_result.get("commands_total", 0),
            "commands_failed": start_result.get("commands_failed", 0),
            "command_statuses": start_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_cycle_self_task_enqueue_failed,
            "reason": "Команды наполнения раствора отправлены, но self-task не поставлен",
            "error": str(exc),
            "error_code": err_two_tank_enqueue_failed,
            "stop_result": stop_result,
            "feature_flag_state": two_tank_safety_guards_enabled_fn(),
        }

    await emit_task_event_fn(
        zone_id=zone_id,
        task_type="diagnostics",
        context=context,
        event_type="SOLUTION_FILL_STARTED",
        payload={
            "solution_fill_started_at": phase_started_at.isoformat(),
            "solution_fill_timeout_at": phase_timeout_at.isoformat(),
            "next_check": enqueue_result,
            "reason_code": reason_solution_fill_started,
        },
    )

    return {
        "success": True,
        "task_type": "diagnostics",
        "mode": "two_tank_solution_fill_in_progress",
        "workflow": "startup",
        "commands_total": start_result.get("commands_total", 0),
        "commands_failed": start_result.get("commands_failed", 0),
        "command_statuses": start_result.get("command_statuses", []),
        "action_required": True,
        "decision": "run",
        "reason_code": reason_solution_fill_started,
        "reason": "Запущено наполнение бака рабочего раствора",
        "solution_fill_started_at": phase_started_at.isoformat(),
        "solution_fill_timeout_at": phase_timeout_at.isoformat(),
        "next_check": enqueue_result,
    }


__all__ = [
    "start_two_tank_clean_fill",
    "start_two_tank_prepare_recirculation",
    "start_two_tank_solution_fill",
]
