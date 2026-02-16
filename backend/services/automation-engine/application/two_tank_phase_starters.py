"""Helpers for starting two-tank workflow phases."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Sequence

from domain.models.decision_models import DecisionOutcome

DispatchTwoTankCommandPlanFn = Callable[..., Awaitable[Dict[str, Any]]]
EnqueueTwoTankCheckFn = Callable[..., Awaitable[Dict[str, Any]]]
CompensateStartEnqueueFailureFn = Callable[..., Awaitable[Dict[str, Any]]]
EmitTaskEventFn = Callable[..., Awaitable[None]]
TwoTankSafetyGuardsEnabledFn = Callable[[], bool]
DispatchSensorModeFn = Callable[..., Awaitable[Dict[str, Any]]]
MergeDispatchResultsFn = Callable[..., Dict[str, Any]]
UpdateWorkflowPhaseFn = Callable[..., Awaitable[None]]


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
    plan_result = await dispatch_two_tank_command_plan_fn(
        zone_id=zone_id,
        command_plan=runtime_cfg["commands"]["solution_fill_start"],
        context=context,
        decision=DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code=reason_solution_fill_started,
            reason="Запуск наполнения бака рабочего раствора",
        ),
    )
    if not plan_result.get("success"):
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_solution_fill_command_failed",
            "workflow": "startup",
            "commands_total": plan_result.get("commands_total", 0),
            "commands_failed": plan_result.get("commands_failed", 1),
            "command_statuses": plan_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_cycle_refill_command_failed,
            "reason": "Не удалось отправить команды наполнения бака раствора",
            "error": str(plan_result.get("error") or err_two_tank_command_failed),
            "error_code": str(plan_result.get("error_code") or err_two_tank_command_failed),
        }

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
    )
    start_result = merge_command_dispatch_results_fn(plan_result, sensor_mode_result)
    if not start_result.get("success"):
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_solution_fill_sensor_mode_failed",
            "workflow": "startup",
            "commands_total": start_result.get("commands_total", 0),
            "commands_failed": start_result.get("commands_failed", 1),
            "command_statuses": start_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_cycle_refill_command_failed,
            "reason": "Команды solution_fill отправлены, но sensor mode не подтверждён",
            "error": str(start_result.get("error") or err_two_tank_command_failed),
            "error_code": str(start_result.get("error_code") or err_two_tank_command_failed),
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


async def start_two_tank_irrigation_recovery(
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    attempt: int,
    dispatch_two_tank_command_plan_fn: DispatchTwoTankCommandPlanFn,
    update_zone_workflow_phase_fn: UpdateWorkflowPhaseFn,
    enqueue_two_tank_check_fn: EnqueueTwoTankCheckFn,
    compensate_two_tank_start_enqueue_failure_fn: CompensateStartEnqueueFailureFn,
    two_tank_safety_guards_enabled_fn: TwoTankSafetyGuardsEnabledFn,
    workflow_phase_irrig_recirc: str,
    reason_irrigation_recovery_started: str,
    reason_irrigation_recovery_failed: str,
    reason_cycle_self_task_enqueue_failed: str,
    err_two_tank_command_failed: str,
    err_two_tank_enqueue_failed: str,
) -> Dict[str, Any]:
    plan_result = await dispatch_two_tank_command_plan_fn(
        zone_id=zone_id,
        command_plan=runtime_cfg["commands"]["irrigation_recovery_start"],
        context=context,
        decision=DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code=reason_irrigation_recovery_started,
            reason="Запуск рециркуляции recovery для полива",
        ),
    )
    if not plan_result.get("success"):
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_irrigation_recovery_command_failed",
            "workflow": "irrigation_recovery",
            "commands_total": plan_result.get("commands_total", 0),
            "commands_failed": plan_result.get("commands_failed", 1),
            "command_statuses": plan_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_irrigation_recovery_failed,
            "reason": "Не удалось отправить команды irrigation recovery",
            "error": str(plan_result.get("error") or err_two_tank_command_failed),
            "error_code": str(plan_result.get("error_code") or err_two_tank_command_failed),
        }

    await update_zone_workflow_phase_fn(
        zone_id=zone_id,
        workflow_phase=workflow_phase_irrig_recirc,
        workflow_stage="irrigation_recovery",
        reason_code=reason_irrigation_recovery_started,
        context=context,
    )

    phase_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    phase_timeout_at = phase_started_at + timedelta(seconds=runtime_cfg["irrigation_recovery_timeout_sec"])
    try:
        enqueue_result = await enqueue_two_tank_check_fn(
            zone_id=zone_id,
            payload={**payload, "irrigation_recovery_attempt": attempt},
            workflow="irrigation_recovery_check",
            phase_started_at=phase_started_at,
            phase_timeout_at=phase_timeout_at,
            poll_interval_sec=runtime_cfg["poll_interval_sec"],
        )
    except ValueError as exc:
        stop_result = await compensate_two_tank_start_enqueue_failure_fn(
            zone_id=zone_id,
            context=context,
            workflow="irrigation_recovery",
            phase="irrigation_recovery_start",
            stop_command_plan=runtime_cfg["commands"]["irrigation_recovery_stop"],
        )
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_irrigation_recovery_enqueue_failed",
            "workflow": "irrigation_recovery",
            "commands_total": plan_result.get("commands_total", 0),
            "commands_failed": plan_result.get("commands_failed", 0),
            "command_statuses": plan_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_cycle_self_task_enqueue_failed,
            "reason": "Команды irrigation recovery отправлены, но self-task не поставлен",
            "error": str(exc),
            "error_code": err_two_tank_enqueue_failed,
            "stop_result": stop_result,
            "feature_flag_state": two_tank_safety_guards_enabled_fn(),
        }

    return {
        "success": True,
        "task_type": "diagnostics",
        "mode": "two_tank_irrigation_recovery_in_progress",
        "workflow": "irrigation_recovery",
        "commands_total": plan_result.get("commands_total", 0),
        "commands_failed": plan_result.get("commands_failed", 0),
        "command_statuses": plan_result.get("command_statuses", []),
        "action_required": True,
        "decision": "run",
        "reason_code": reason_irrigation_recovery_started,
        "reason": "Запущен recovery-процесс для продолжения полива",
        "irrigation_recovery_attempt": attempt,
        "irrigation_recovery_started_at": phase_started_at.isoformat(),
        "irrigation_recovery_timeout_at": phase_timeout_at.isoformat(),
        "next_check": enqueue_result,
    }


__all__ = [
    "start_two_tank_clean_fill",
    "start_two_tank_solution_fill",
    "start_two_tank_prepare_recirculation",
    "start_two_tank_irrigation_recovery",
]
