"""Recovery phase starter for two-tank workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from common.pump_safety import can_run_pump
from executor.two_tank_common import resolve_primary_pump_channel
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


async def start_two_tank_irrigation_recovery(
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    attempt: int,
    dispatch_two_tank_command_plan_fn: DispatchTwoTankCommandPlanFn,
    dispatch_sensor_mode_command_for_nodes_fn: DispatchSensorModeFn,
    merge_command_dispatch_results_fn: MergeDispatchResultsFn,
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
    pump_channel = resolve_primary_pump_channel(runtime_cfg["commands"].get("irrigation_recovery_start"))
    sensor_mode_result = await dispatch_sensor_mode_command_for_nodes_fn(
        zone_id=zone_id,
        context=context,
        decision=DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code=reason_irrigation_recovery_started,
            reason="Активация sensor mode для pH/EC в irrigation_recovery",
        ),
        activate=True,
        reason_code=reason_irrigation_recovery_started,
        stabilization_time_sec=int(runtime_cfg.get("sensor_mode_stabilization_time_sec") or 60),
    )
    if not sensor_mode_result.get("success"):
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_irrigation_recovery_sensor_mode_failed",
            "workflow": "irrigation_recovery",
            "commands_total": sensor_mode_result.get("commands_total", 0),
            "commands_failed": sensor_mode_result.get("commands_failed", 1),
            "command_statuses": sensor_mode_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_irrigation_recovery_failed,
            "reason": "Не удалось активировать sensor mode для pH/EC перед irrigation_recovery",
            "error": str(sensor_mode_result.get("error") or err_two_tank_command_failed),
            "error_code": str(sensor_mode_result.get("error_code") or err_two_tank_command_failed),
            "pump_channel": pump_channel,
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
            "mode": "two_tank_irrigation_recovery_safety_blocked",
            "workflow": "irrigation_recovery",
            "commands_total": sensor_mode_result.get("commands_total", 0),
            "commands_failed": sensor_mode_result.get("commands_failed", 0),
            "command_statuses": sensor_mode_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": "safety_blocked",
            "reason": "Запуск irrigation_recovery заблокирован safety policy",
            "error": str(safety_error or "two_tank_pump_safety_blocked"),
            "error_code": "two_tank_pump_safety_blocked",
            "pump_channel": pump_channel,
            "safety_error": str(safety_error or ""),
        }

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
    start_result = merge_command_dispatch_results_fn(plan_result, sensor_mode_result)
    if not plan_result.get("success"):
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_irrigation_recovery_command_failed",
            "workflow": "irrigation_recovery",
            "commands_total": start_result.get("commands_total", 0),
            "commands_failed": start_result.get("commands_failed", 1),
            "command_statuses": start_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": reason_irrigation_recovery_failed,
            "reason": "Не удалось отправить команды irrigation recovery",
            "error": str(start_result.get("error") or err_two_tank_command_failed),
            "error_code": str(start_result.get("error_code") or err_two_tank_command_failed),
        }

    await update_zone_workflow_phase_fn(
        zone_id=zone_id,
        workflow_phase=workflow_phase_irrig_recirc,
        workflow_stage="irrigation_recovery",
        reason_code=reason_irrigation_recovery_started,
        context=context,
    )

    phase_started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    timeout_sec = int(runtime_cfg["irrigation_recovery_timeout_sec"])
    if attempt > 1:
        retry_multiplier = float(runtime_cfg.get("irrigation_recovery_retry_timeout_multiplier") or 1.0)
        timeout_sec = max(timeout_sec, int(round(timeout_sec * retry_multiplier)))
    phase_timeout_at = phase_started_at + timedelta(seconds=timeout_sec)
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
            "commands_total": start_result.get("commands_total", 0),
            "commands_failed": start_result.get("commands_failed", 0),
            "command_statuses": start_result.get("command_statuses", []),
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
        "commands_total": start_result.get("commands_total", 0),
        "commands_failed": start_result.get("commands_failed", 0),
        "command_statuses": start_result.get("command_statuses", []),
        "action_required": True,
        "decision": "run",
        "reason_code": reason_irrigation_recovery_started,
        "reason": "Запущен recovery-процесс для продолжения полива",
        "irrigation_recovery_attempt": attempt,
        "irrigation_recovery_started_at": phase_started_at.isoformat(),
        "irrigation_recovery_timeout_at": phase_timeout_at.isoformat(),
        "next_check": enqueue_result,
    }


__all__ = ["start_two_tank_irrigation_recovery"]
