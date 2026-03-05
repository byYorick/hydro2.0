"""Prepare-recirculation branch handlers for two-tank startup workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from domain.models.decision_models import DecisionOutcome
from domain.workflows.two_tank_deps import TwoTankDeps
from domain.workflows.two_tank_result import two_tank_error, two_tank_success
from executor.executor_constants import (
    ERR_PREPARE_NPK_PH_TARGET_NOT_REACHED,
    ERR_TWO_TANK_COMMAND_FAILED,
    ERR_TWO_TANK_ENQUEUE_FAILED,
    REASON_CYCLE_REFILL_COMMAND_FAILED,
    REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
    REASON_PREPARE_RECIRCULATION_STARTED,
    REASON_PREPARE_TARGETS_NOT_REACHED,
    REASON_PREPARE_TARGETS_REACHED,
)
from executor.workflow_phase_policy import WORKFLOW_PHASE_READY
from scheduler_internal_enqueue import parse_iso_datetime


async def handle_two_tank_prepare_branches(
    deps: TwoTankDeps,
    *,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    workflow: str,
) -> Optional[Dict[str, Any]]:
    zone_id = deps.zone_id
    if workflow == "prepare_recirculation":
        return await deps._start_two_tank_prepare_recirculation(
            zone_id=zone_id,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
        )

    if workflow != "prepare_recirculation_check":
        return None

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    phase_started_at = parse_iso_datetime(str(payload.get("prepare_recirculation_started_at") or "")) or now
    phase_timeout_at = parse_iso_datetime(str(payload.get("prepare_recirculation_timeout_at") or ""))
    if phase_timeout_at is None:
        phase_timeout_at = phase_started_at + timedelta(seconds=runtime_cfg["prepare_recirculation_timeout_sec"])

    prepare_event = await deps._find_zone_event_since(
        zone_id=zone_id,
        event_types=("PREPARE_TARGETS_REACHED",),
        since=phase_started_at,
    )
    targets_state = await deps._evaluate_ph_ec_targets(
        zone_id=zone_id,
        target_ph=float(runtime_cfg["target_ph"]),
        target_ec=float(runtime_cfg["target_ec_prepare"]),
        tolerance=runtime_cfg["prepare_tolerance"],
        absolute_tolerance=runtime_cfg.get("prepare_absolute_tolerance"),
        hard_bounds=runtime_cfg.get("prepare_hard_bounds"),
    )
    if prepare_event or targets_state["targets_reached"]:
        stop_result = await deps._dispatch_two_tank_command_plan(
            zone_id=zone_id,
            command_plan=runtime_cfg["commands"]["prepare_recirculation_stop"],
            context=context,
            decision=DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code=REASON_PREPARE_TARGETS_REACHED,
                reason="Остановка рециркуляции подготовки по достижению целей",
            ),
        )
        stop_result = await deps._merge_with_sensor_mode_deactivate(
            zone_id=zone_id,
            context=context,
            stop_result=stop_result,
            reason_code=REASON_PREPARE_TARGETS_REACHED,
        )
        if not stop_result.get("success"):
            return two_tank_error(
                mode="two_tank_prepare_recirculation_stop_failed",
                workflow=workflow,
                reason_code=REASON_CYCLE_REFILL_COMMAND_FAILED,
                reason="Не удалось остановить prepare recirculation",
                error_code=str(stop_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED),
                error=str(stop_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED),
                commands_total=stop_result.get("commands_total", 0),
                commands_failed=stop_result.get("commands_failed", 1),
                command_statuses=stop_result.get("command_statuses", []),
            )
        await deps._update_zone_workflow_phase(
            zone_id=zone_id,
            workflow_phase=WORKFLOW_PHASE_READY,
            workflow_stage="prepare_recirculation_check",
            reason_code=REASON_PREPARE_TARGETS_REACHED,
            context=context,
        )
        return two_tank_success(
            mode="two_tank_prepare_recirculation_completed",
            workflow=workflow,
            reason_code=REASON_PREPARE_TARGETS_REACHED,
            reason="Prepare recirculation: EC/pH в пределах целевых границ",
            action_required=False,
            decision="skip",
            commands_total=stop_result.get("commands_total", 0),
            commands_failed=stop_result.get("commands_failed", 0),
            command_statuses=stop_result.get("command_statuses", []),
            targets_state=targets_state,
        )

    if now >= phase_timeout_at:
        stop_result = await deps._dispatch_two_tank_command_plan(
            zone_id=zone_id,
            command_plan=runtime_cfg["commands"]["prepare_recirculation_stop"],
            context=context,
            decision=DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code=REASON_PREPARE_TARGETS_NOT_REACHED,
                reason="Остановка prepare recirculation по таймауту",
            ),
        )
        stop_result = await deps._merge_with_sensor_mode_deactivate(
            zone_id=zone_id,
            context=context,
            stop_result=stop_result,
            reason_code=REASON_PREPARE_TARGETS_NOT_REACHED,
        )
        if deps.safety_config.stop_confirmation_required and not stop_result.get("success"):
            deps._log_two_tank_safety_guard(
                zone_id=zone_id,
                context=context,
                phase="prepare_recirculation_timeout",
                stop_result=stop_result,
            )
            return deps._build_two_tank_stop_not_confirmed_result(
                workflow=workflow,
                mode="two_tank_prepare_recirculation_timeout_stop_not_confirmed",
                reason="Таймаут prepare recirculation: stop не подтверждён",
                stop_result=stop_result,
            )
        return two_tank_error(
            mode="two_tank_prepare_recirculation_timeout",
            workflow=workflow,
            reason_code=REASON_PREPARE_TARGETS_NOT_REACHED,
            reason="Prepare recirculation не достиг целевых EC/pH до таймаута",
            error_code=ERR_PREPARE_NPK_PH_TARGET_NOT_REACHED,
            commands_total=stop_result.get("commands_total", 0),
            commands_failed=stop_result.get("commands_failed", 0),
            command_statuses=stop_result.get("command_statuses", []),
            targets_state=targets_state,
        )

    try:
        enqueue_result = await deps._enqueue_two_tank_check(
            zone_id=zone_id,
            payload=payload,
            workflow="prepare_recirculation_check",
            phase_started_at=phase_started_at,
            phase_timeout_at=phase_timeout_at,
            poll_interval_sec=runtime_cfg["poll_interval_sec"],
        )
    except ValueError as exc:
        return two_tank_error(
            mode="two_tank_prepare_recirculation_enqueue_failed",
            workflow=workflow,
            reason_code=REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
            reason="Не удалось запланировать следующую проверку prepare recirculation",
            error_code=ERR_TWO_TANK_ENQUEUE_FAILED,
            error=str(exc),
        )

    return two_tank_success(
        mode="two_tank_prepare_recirculation_in_progress",
        workflow=workflow,
        reason_code=REASON_PREPARE_RECIRCULATION_STARTED,
        reason="Prepare recirculation продолжается",
        action_required=True,
        decision="run",
        prepare_recirculation_started_at=phase_started_at.isoformat(),
        prepare_recirculation_timeout_at=phase_timeout_at.isoformat(),
        next_check=enqueue_result,
        targets_state=targets_state,
    )


__all__ = ["handle_two_tank_prepare_branches"]
