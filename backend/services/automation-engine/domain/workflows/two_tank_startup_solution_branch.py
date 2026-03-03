"""Solution-fill branch handler for two-tank startup workflow."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from domain.models.decision_models import DecisionOutcome
from executor.executor_constants import (
    ERR_SOLUTION_TANK_NOT_FILLED_TIMEOUT,
    ERR_TWO_TANK_COMMAND_FAILED,
    ERR_TWO_TANK_ENQUEUE_FAILED,
    ERR_TWO_TANK_LEVEL_STALE,
    ERR_TWO_TANK_LEVEL_UNAVAILABLE,
    REASON_CYCLE_REFILL_COMMAND_FAILED,
    REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
    REASON_PREPARE_TARGETS_REACHED,
    REASON_SENSOR_LEVEL_UNAVAILABLE,
    REASON_SENSOR_STALE_DETECTED,
    REASON_SOLUTION_FILL_COMPLETED,
    REASON_SOLUTION_FILL_IN_PROGRESS,
    REASON_SOLUTION_FILL_TIMEOUT,
)
from executor.workflow_phase_policy import WORKFLOW_PHASE_READY
from scheduler_internal_enqueue import parse_iso_datetime

logger = logging.getLogger(__name__)


async def handle_two_tank_solution_fill_check(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    workflow: str,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    solution_started_at = parse_iso_datetime(str(payload.get("solution_fill_started_at") or "")) or now
    solution_timeout_at = parse_iso_datetime(str(payload.get("solution_fill_timeout_at") or ""))
    if solution_timeout_at is None:
        solution_timeout_at = solution_started_at + timedelta(seconds=runtime_cfg["solution_fill_timeout_sec"])

    solution_event = await self._find_zone_event_since(
        zone_id=zone_id,
        event_types=("SOLUTION_FILL_COMPLETED",),
        since=solution_started_at,
    )
    solution_triggered = bool(solution_event)
    solution_level: Dict[str, Any] = {
        "sensor_id": None,
        "sensor_label": None,
        "level": None,
        "sample_ts": None,
        "sample_age_sec": None,
        "is_stale": False,
        "has_level": False,
        "is_triggered": False,
    }
    if not solution_triggered:
        solution_level = await self._read_level_switch(
            zone_id=zone_id,
            sensor_labels=runtime_cfg["solution_max_labels"],
            threshold=runtime_cfg["level_switch_on_threshold"],
        )
        solution_triggered = bool(solution_level["is_triggered"])
        if not solution_level["has_level"]:
            logger.warning(
                "Zone %s: two_tank solution level unavailable (solution_fill_check), expected=%s available=%s source=%s",
                zone_id,
                solution_level.get("expected_labels", runtime_cfg["solution_max_labels"]),
                solution_level.get("available_sensor_labels", []),
                solution_level.get("level_source", "none"),
            )
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_solution_level_unavailable",
                "workflow": workflow,
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_SENSOR_LEVEL_UNAVAILABLE,
                "reason": "Нет данных датчика верхнего уровня бака раствора",
                "error": ERR_TWO_TANK_LEVEL_UNAVAILABLE,
                "error_code": ERR_TWO_TANK_LEVEL_UNAVAILABLE,
                "expected_sensor_labels": solution_level.get("expected_labels", runtime_cfg["solution_max_labels"]),
                "available_sensor_labels": solution_level.get("available_sensor_labels", []),
                "level_source": solution_level.get("level_source", "none"),
            }
        if self._telemetry_freshness_enforce() and solution_level["is_stale"]:
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_solution_level_stale",
                "workflow": workflow,
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_SENSOR_STALE_DETECTED,
                "reason": "Телеметрия датчика верхнего уровня бака раствора устарела",
                "error": ERR_TWO_TANK_LEVEL_STALE,
                "error_code": ERR_TWO_TANK_LEVEL_STALE,
            }

    if solution_triggered:
        stop_result = await self._dispatch_two_tank_command_plan(
            zone_id=zone_id,
            command_plan=runtime_cfg["commands"]["solution_fill_stop"],
            context=context,
            decision=DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code=REASON_SOLUTION_FILL_COMPLETED,
                reason="Остановка наполнения бака рабочего раствора",
            ),
        )
        stop_result = await self._merge_with_sensor_mode_deactivate(
            zone_id=zone_id,
            context=context,
            stop_result=stop_result,
            reason_code=REASON_SOLUTION_FILL_COMPLETED,
        )
        if not stop_result.get("success"):
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_solution_fill_stop_failed",
                "workflow": workflow,
                "commands_total": stop_result.get("commands_total", 0),
                "commands_failed": stop_result.get("commands_failed", 1),
                "command_statuses": stop_result.get("command_statuses", []),
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_CYCLE_REFILL_COMMAND_FAILED,
                "reason": "Не удалось остановить наполнение бака раствора",
                "error": str(stop_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED),
                "error_code": str(stop_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED),
            }
        prepare_targets_state = await self._evaluate_ph_ec_targets(
            zone_id=zone_id,
            target_ph=float(runtime_cfg["target_ph"]),
            target_ec=float(runtime_cfg["target_ec_prepare"]),
            tolerance=runtime_cfg["prepare_tolerance"],
        )
        if not prepare_targets_state["targets_reached"]:
            return await self._start_two_tank_prepare_recirculation(
                zone_id=zone_id,
                payload=payload,
                context=context,
                runtime_cfg=runtime_cfg,
            )
        await self._update_zone_workflow_phase(
            zone_id=zone_id,
            workflow_phase=WORKFLOW_PHASE_READY,
            workflow_stage="prepare_recirculation_check",
            reason_code=REASON_PREPARE_TARGETS_REACHED,
            context=context,
        )
        return {
            "success": True,
            "task_type": "diagnostics",
            "mode": "two_tank_startup_completed",
            "workflow": workflow,
            "commands_total": stop_result.get("commands_total", 0),
            "commands_failed": stop_result.get("commands_failed", 0),
            "command_statuses": stop_result.get("command_statuses", []),
            "action_required": False,
            "decision": "skip",
            "reason_code": REASON_SOLUTION_FILL_COMPLETED,
            "reason": "Бак рабочего раствора заполнен, startup завершен",
            "targets_state": prepare_targets_state,
        }

    if now >= solution_timeout_at:
        stop_result = await self._dispatch_two_tank_command_plan(
            zone_id=zone_id,
            command_plan=runtime_cfg["commands"]["solution_fill_stop"],
            context=context,
            decision=DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code=REASON_SOLUTION_FILL_TIMEOUT,
                reason="Остановка наполнения бака раствора по таймауту",
            ),
        )
        stop_result = await self._merge_with_sensor_mode_deactivate(
            zone_id=zone_id,
            context=context,
            stop_result=stop_result,
            reason_code=REASON_SOLUTION_FILL_TIMEOUT,
        )
        if self._two_tank_safety_guards_enabled() and not stop_result.get("success"):
            self._log_two_tank_safety_guard(
                zone_id=zone_id,
                context=context,
                phase="solution_fill_timeout",
                stop_result=stop_result,
            )
            return self._build_two_tank_stop_not_confirmed_result(
                workflow=workflow,
                mode="two_tank_solution_fill_timeout_stop_not_confirmed",
                reason="Таймаут solution fill: stop не подтверждён",
                stop_result=stop_result,
            )
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_solution_fill_timeout",
            "workflow": workflow,
            "commands_total": stop_result.get("commands_total", 0),
            "commands_failed": stop_result.get("commands_failed", 0),
            "command_statuses": stop_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_SOLUTION_FILL_TIMEOUT,
            "reason": "Таймаут наполнения бака рабочего раствора",
            "error": ERR_SOLUTION_TANK_NOT_FILLED_TIMEOUT,
            "error_code": ERR_SOLUTION_TANK_NOT_FILLED_TIMEOUT,
        }

    try:
        enqueue_result = await self._enqueue_two_tank_check(
            zone_id=zone_id,
            payload=payload,
            workflow="solution_fill_check",
            phase_started_at=solution_started_at,
            phase_timeout_at=solution_timeout_at,
            poll_interval_sec=runtime_cfg["poll_interval_sec"],
        )
    except ValueError as exc:
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_solution_fill_enqueue_failed",
            "workflow": workflow,
            "commands_total": 0,
            "commands_failed": 0,
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
            "reason": "Не удалось запланировать следующую проверку бака раствора",
            "error": str(exc),
            "error_code": ERR_TWO_TANK_ENQUEUE_FAILED,
        }

    return {
        "success": True,
        "task_type": "diagnostics",
        "mode": "two_tank_solution_fill_in_progress",
        "workflow": workflow,
        "commands_total": 0,
        "commands_failed": 0,
        "action_required": True,
        "decision": "run",
        "reason_code": REASON_SOLUTION_FILL_IN_PROGRESS,
        "reason": "Наполнение бака рабочего раствора продолжается",
        "solution_fill_started_at": solution_started_at.isoformat(),
        "solution_fill_timeout_at": solution_timeout_at.isoformat(),
        "next_check": enqueue_result,
    }


__all__ = ["handle_two_tank_solution_fill_check"]
