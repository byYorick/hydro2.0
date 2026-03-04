"""Two-tank recovery branch extracted from monolithic core."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from domain.models.decision_models import DecisionOutcome
from domain.workflows.two_tank_deps import TwoTankDeps
from domain.workflows.two_tank_result import two_tank_error, two_tank_success
from executor.executor_constants import (
    ERR_IRRIGATION_RECOVERY_ATTEMPTS_EXCEEDED,
    ERR_TWO_TANK_COMMAND_FAILED,
    ERR_TWO_TANK_ENQUEUE_FAILED,
    REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
    REASON_IRRIGATION_CORRECTION_ATTEMPTS_EXHAUSTED_CONTINUE_IRRIGATION,
    REASON_IRRIGATION_RECOVERY_DEGRADED,
    REASON_IRRIGATION_RECOVERY_FAILED,
    REASON_IRRIGATION_RECOVERY_RECOVERED,
    REASON_IRRIGATION_RECOVERY_STARTED,
)
from executor.workflow_phase_policy import WORKFLOW_PHASE_IRRIGATING
from scheduler_internal_enqueue import parse_iso_datetime


async def execute_two_tank_recovery_branch(
    deps: TwoTankDeps,
    *,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    workflow: str,
) -> Dict[str, Any]:
    zone_id = deps.zone_id
    if workflow == "irrigation_recovery":
        attempt = deps._resolve_int(payload.get("irrigation_recovery_attempt"), 1, 1)
        return await deps._start_two_tank_irrigation_recovery(
            zone_id=zone_id,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
            attempt=attempt,
        )

    if workflow == "irrigation_recovery_check":
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        attempt = deps._resolve_int(payload.get("irrigation_recovery_attempt"), 1, 1)
        max_attempts = max(1, int(runtime_cfg["irrigation_recovery_max_attempts"]))
        phase_started_at = parse_iso_datetime(str(payload.get("irrigation_recovery_started_at") or "")) or now
        phase_timeout_at = parse_iso_datetime(str(payload.get("irrigation_recovery_timeout_at") or ""))
        if phase_timeout_at is None:
            phase_timeout_at = phase_started_at + timedelta(seconds=runtime_cfg["irrigation_recovery_timeout_sec"])
        # Final attempt should converge quickly to a terminal decision.
        if attempt >= max_attempts:
            final_attempt_deadline = phase_started_at + timedelta(
                seconds=max(30, int(runtime_cfg["poll_interval_sec"]))
            )
            if phase_timeout_at > final_attempt_deadline:
                phase_timeout_at = final_attempt_deadline

        recovery_state = await deps._evaluate_ph_ec_targets(
            zone_id=zone_id,
            target_ph=float(runtime_cfg["target_ph"]),
            target_ec=float(runtime_cfg["target_ec"]),
            tolerance=runtime_cfg["recovery_tolerance"],
        )
        if recovery_state["targets_reached"]:
            stop_result = await deps._dispatch_two_tank_command_plan(
                zone_id=zone_id,
                command_plan=runtime_cfg["commands"]["irrigation_recovery_stop"],
                context=context,
                decision=DecisionOutcome(
                    action_required=True,
                    decision="run",
                    reason_code=REASON_IRRIGATION_RECOVERY_RECOVERED,
                    reason="Остановка irrigation recovery по достижению цели",
                ),
            )
            stop_result = await deps._merge_with_sensor_mode_deactivate(
                zone_id=zone_id,
                context=context,
                stop_result=stop_result,
                reason_code=REASON_IRRIGATION_RECOVERY_RECOVERED,
            )
            if not stop_result.get("success"):
                return two_tank_error(
                    mode="two_tank_irrigation_recovery_stop_failed",
                    workflow=workflow,
                    reason_code=REASON_IRRIGATION_RECOVERY_FAILED,
                    reason="Не удалось остановить irrigation recovery",
                    error_code=str(stop_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED),
                    error=str(stop_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED),
                    commands_total=stop_result.get("commands_total", 0),
                    commands_failed=stop_result.get("commands_failed", 1),
                    command_statuses=stop_result.get("command_statuses", []),
                )
            await deps._update_zone_workflow_phase(
                zone_id=zone_id,
                workflow_phase=WORKFLOW_PHASE_IRRIGATING,
                workflow_stage="irrigation_recovery_check",
                reason_code=REASON_IRRIGATION_RECOVERY_RECOVERED,
                context=context,
            )
            return two_tank_success(
                mode="two_tank_irrigation_recovery_completed",
                workflow=workflow,
                reason_code=REASON_IRRIGATION_RECOVERY_RECOVERED,
                reason="Irrigation recovery успешно завершен",
                action_required=False,
                decision="skip",
                commands_total=stop_result.get("commands_total", 0),
                commands_failed=stop_result.get("commands_failed", 0),
                command_statuses=stop_result.get("command_statuses", []),
                irrigation_recovery_attempt=attempt,
                targets_state=recovery_state,
            )

        if now >= phase_timeout_at:
            stop_result = await deps._dispatch_two_tank_command_plan(
                zone_id=zone_id,
                command_plan=runtime_cfg["commands"]["irrigation_recovery_stop"],
                context=context,
                decision=DecisionOutcome(
                    action_required=True,
                    decision="run",
                    reason_code=REASON_IRRIGATION_RECOVERY_FAILED,
                    reason="Остановка irrigation recovery по таймауту попытки",
                ),
            )
            stop_result = await deps._merge_with_sensor_mode_deactivate(
                zone_id=zone_id,
                context=context,
                stop_result=stop_result,
                reason_code=REASON_IRRIGATION_RECOVERY_FAILED,
            )
            if deps.safety_config.stop_confirmation_required and not stop_result.get("success"):
                deps._log_two_tank_safety_guard(
                    zone_id=zone_id,
                    context=context,
                    phase="irrigation_recovery_timeout",
                    stop_result=stop_result,
                )
                return deps._build_two_tank_stop_not_confirmed_result(
                    workflow=workflow,
                    mode="two_tank_irrigation_recovery_timeout_stop_not_confirmed",
                    reason="Таймаут irrigation recovery: stop не подтверждён, retry запрещён",
                    stop_result=stop_result,
                )
            degraded_state = await deps._evaluate_ph_ec_targets(
                zone_id=zone_id,
                target_ph=float(runtime_cfg["target_ph"]),
                target_ec=float(runtime_cfg["target_ec"]),
                tolerance=runtime_cfg["degraded_tolerance"],
            )
            if degraded_state["targets_reached"]:
                await deps._emit_task_event(
                    zone_id=zone_id,
                    task_type="diagnostics",
                    context=context,
                    event_type="IRRIGATION_RECOVERY_DEGRADED",
                    payload={
                        "irrigation_recovery_attempt": attempt,
                        "targets_state": degraded_state,
                        "reason_code": REASON_IRRIGATION_RECOVERY_DEGRADED,
                        "reason": "Полив возобновлен в degraded tolerance - pH/EC вне нормальных допусков",
                        "action_required_human": True,
                    },
                )
                await deps._update_zone_workflow_phase(
                    zone_id=zone_id,
                    workflow_phase=WORKFLOW_PHASE_IRRIGATING,
                    workflow_stage="irrigation_recovery_check",
                    reason_code=REASON_IRRIGATION_RECOVERY_DEGRADED,
                    context=context,
                )
                return two_tank_success(
                    mode="two_tank_irrigation_recovery_degraded",
                    workflow=workflow,
                    reason_code=REASON_IRRIGATION_RECOVERY_DEGRADED,
                    reason="Irrigation recovery завершен в degraded tolerance",
                    action_required=True,
                    decision="skip",
                    commands_total=stop_result.get("commands_total", 0),
                    commands_failed=stop_result.get("commands_failed", 0),
                    command_statuses=stop_result.get("command_statuses", []),
                    degraded=True,
                    irrigation_recovery_attempt=attempt,
                    targets_state=degraded_state,
                )

            if attempt < max_attempts:
                return await deps._start_two_tank_irrigation_recovery(
                    zone_id=zone_id,
                    payload={**payload, "irrigation_recovery_attempt": attempt + 1},
                    context=context,
                    runtime_cfg=runtime_cfg,
                    attempt=attempt + 1,
                )

            await deps._emit_task_event(
                zone_id=zone_id,
                task_type="diagnostics",
                context=context,
                event_type="IRRIGATION_RECOVERY_DEGRADED",
                payload={
                    "irrigation_recovery_attempt": attempt,
                    "targets_state": recovery_state,
                    "reason_code": REASON_IRRIGATION_CORRECTION_ATTEMPTS_EXHAUSTED_CONTINUE_IRRIGATION,
                    "reason": "Коррекция pH/EC исчерпала автопопытки, полив продолжается в degraded режиме",
                    "action_required_human": True,
                    "manual_ack_required": True,
                    "error_code": ERR_IRRIGATION_RECOVERY_ATTEMPTS_EXCEEDED,
                },
            )
            await deps._update_zone_workflow_phase(
                zone_id=zone_id,
                workflow_phase=WORKFLOW_PHASE_IRRIGATING,
                workflow_stage="irrigation_recovery_check",
                reason_code=REASON_IRRIGATION_CORRECTION_ATTEMPTS_EXHAUSTED_CONTINUE_IRRIGATION,
                context=context,
            )
            return two_tank_success(
                mode="two_tank_irrigation_recovery_attempts_exhausted_continue_irrigation",
                workflow=workflow,
                reason_code=REASON_IRRIGATION_CORRECTION_ATTEMPTS_EXHAUSTED_CONTINUE_IRRIGATION,
                reason="Автопопытки irrigation recovery исчерпаны, полив продолжается в degraded режиме",
                action_required=True,
                decision="skip",
                commands_total=stop_result.get("commands_total", 0),
                commands_failed=stop_result.get("commands_failed", 0),
                command_statuses=stop_result.get("command_statuses", []),
                irrigation_recovery_attempt=attempt,
                targets_state=recovery_state,
                degraded=True,
                manual_ack_required=True,
                error_code=ERR_IRRIGATION_RECOVERY_ATTEMPTS_EXCEEDED,
            )

        try:
            enqueue_result = await deps._enqueue_two_tank_check(
                zone_id=zone_id,
                payload={**payload, "irrigation_recovery_attempt": attempt},
                workflow="irrigation_recovery_check",
                phase_started_at=phase_started_at,
                phase_timeout_at=phase_timeout_at,
                poll_interval_sec=runtime_cfg["poll_interval_sec"],
                phase_cycle=attempt,
            )
        except ValueError as exc:
            return two_tank_error(
                mode="two_tank_irrigation_recovery_enqueue_failed",
                workflow=workflow,
                reason_code=REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
                reason="Не удалось запланировать следующую проверку irrigation recovery",
                error_code=ERR_TWO_TANK_ENQUEUE_FAILED,
                error=str(exc),
            )

        return two_tank_success(
            mode="two_tank_irrigation_recovery_in_progress",
            workflow=workflow,
            reason_code=REASON_IRRIGATION_RECOVERY_STARTED,
            reason="Irrigation recovery продолжается",
            action_required=True,
            decision="run",
            irrigation_recovery_attempt=attempt,
            irrigation_recovery_started_at=phase_started_at.isoformat(),
            irrigation_recovery_timeout_at=phase_timeout_at.isoformat(),
            next_check=enqueue_result,
            targets_state=recovery_state,
        )

    return two_tank_error(
        mode="two_tank_unknown_workflow",
        workflow=workflow,
        reason_code="unsupported_workflow",
        reason=f"Неподдерживаемый workflow для топологии two_tank: {workflow}",
        error_code="unsupported_workflow",
        error="unsupported_workflow",
    )
