"""Refill sequence helpers for cycle-start workflow."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

from executor.scheduler_executor_impl import *  # noqa: F401,F403
from services.resilience_contract import (
    INFRA_CYCLE_START_ENQUEUE_FAILED,
    INFRA_CYCLE_START_REFILL_COMMAND_FAILED,
)


async def execute_cycle_start_refill_sequence(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    workflow: str,
    now: datetime,
    refill_attempt: int,
    refill_started_at: datetime,
    refill_timeout_at: datetime,
    tank_level: Dict[str, Any],
) -> Dict[str, Any]:
    refill_command = await self._resolve_refill_command(zone_id, payload)
    if not refill_command:
        error = ERR_CYCLE_REFILL_NODE_NOT_FOUND
        await self._emit_cycle_alert(
            zone_id=zone_id,
            code=INFRA_CYCLE_START_REFILL_COMMAND_FAILED,
            message="Невозможно запустить refill: не найден online-узел для наполнения бака",
            severity="error",
            details={"workflow": workflow, "error_code": error},
        )
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "cycle_start",
            "workflow": workflow,
            "commands_total": 0,
            "commands_failed": 0,
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_CYCLE_REFILL_COMMAND_FAILED,
            "reason": "Не найден online-узел для команды наполнения бака",
            "error": error,
            "error_code": error,
        }

    refill_decision = DecisionOutcome(
        action_required=True,
        decision="run",
        reason_code=REASON_TANK_REFILL_REQUIRED,
        reason="Бак чистой воды неполный, требуется наполнение",
    )
    publish_result = await self._publish_batch(
        zone_id=zone_id,
        task_type="diagnostics",
        nodes=[refill_command["node"]],
        cmd=str(refill_command["cmd"]),
        params=refill_command["params"],
        context=context,
        decision=refill_decision,
    )
    if not publish_result["success"]:
        error_code = str(publish_result.get("error_code") or ERR_COMMAND_PUBLISH_FAILED)
        await self._emit_cycle_alert(
            zone_id=zone_id,
            code=INFRA_CYCLE_START_REFILL_COMMAND_FAILED,
            message=f"Не удалось отправить refill-команду ({error_code})",
            severity="error",
            details={
                "workflow": workflow,
                "node_uid": refill_command["node"]["node_uid"],
                "channel": refill_command["node"]["channel"],
                "cmd": refill_command["cmd"],
                "error_code": error_code,
            },
        )
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "cycle_start",
            "workflow": workflow,
            "commands_total": publish_result.get("commands_total", 0),
            "commands_failed": publish_result.get("commands_failed", 1),
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_CYCLE_REFILL_COMMAND_FAILED,
            "reason": "Команда наполнения бака не получила подтверждение DONE",
            "error": str(publish_result.get("error") or ERR_CYCLE_REFILL_COMMAND_FAILED),
            "error_code": error_code,
        }

    await self._emit_task_event(
        zone_id=zone_id,
        task_type="diagnostics",
        context=context,
        event_type="TANK_REFILL_STARTED",
        payload={
            "node_uid": refill_command["node"]["node_uid"],
            "channel": refill_command["node"]["channel"],
            "cmd": refill_command["cmd"],
            "params": refill_command["params"],
            "refill_started_at": refill_started_at.isoformat(),
            "refill_timeout_at": refill_timeout_at.isoformat(),
            "refill_attempt": refill_attempt + 1,
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_TANK_REFILL_STARTED,
        },
    )

    next_attempt = refill_attempt + 1
    next_payload = self._build_refill_check_payload(
        payload=payload,
        refill_started_at=refill_started_at,
        refill_timeout_at=refill_timeout_at,
        next_attempt=next_attempt,
    )
    next_check_at = now + timedelta(seconds=REFILL_CHECK_DELAY_SEC)
    # Не ставим self-task позже refill_timeout_at: иначе scheduler получает
    # enqueue, который гарантированно "expired before dispatch".
    if next_check_at > refill_timeout_at:
        next_check_at = refill_timeout_at
    try:
        enqueue_result = await self.enqueue_internal_scheduler_task_fn(
            zone_id=zone_id,
            task_type="diagnostics",
            payload=next_payload,
            scheduled_for=next_check_at.isoformat(),
            expires_at=refill_timeout_at.isoformat(),
            source="automation-engine:cycle-start",
        )
    except ValueError as exc:
        error = ERR_CYCLE_SELF_TASK_ENQUEUE_FAILED
        await self._emit_cycle_alert(
            zone_id=zone_id,
            code=INFRA_CYCLE_START_ENQUEUE_FAILED,
            message=f"Refill запущен, но self-task не поставлен: {exc}",
            severity="error",
            details={
                "workflow": workflow,
                "next_check_at": next_check_at.isoformat(),
                "refill_timeout_at": refill_timeout_at.isoformat(),
                "error": str(exc),
            },
        )
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "cycle_start_refill_started_without_check",
            "workflow": workflow,
            "commands_total": publish_result.get("commands_total", 1),
            "commands_failed": publish_result.get("commands_failed", 0),
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
            "reason": "Команда refill отправлена, но не удалось запланировать проверку",
            "error": error,
            "error_code": error,
            "refill_started_at": refill_started_at.isoformat(),
            "refill_timeout_at": refill_timeout_at.isoformat(),
        }

    await self._emit_task_event(
        zone_id=zone_id,
        task_type="diagnostics",
        context=context,
        event_type="SELF_TASK_ENQUEUED",
        payload={
            "enqueue_id": enqueue_result["enqueue_id"],
            "scheduled_for": enqueue_result["scheduled_for"],
            "expires_at": enqueue_result["expires_at"],
            "correlation_id": enqueue_result["correlation_id"],
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_TANK_REFILL_IN_PROGRESS,
        },
    )

    return {
        "success": True,
        "task_type": "diagnostics",
        "mode": "cycle_start_refill_in_progress",
        "workflow": workflow,
        "commands_total": publish_result.get("commands_total", 1),
        "commands_failed": publish_result.get("commands_failed", 0),
        "action_required": True,
        "decision": "run",
        "reason_code": REASON_TANK_REFILL_STARTED if workflow == "cycle_start" else REASON_TANK_REFILL_IN_PROGRESS,
        "reason": "Запущено наполнение бака и запланирована отложенная проверка",
        "tank_level": tank_level["level"],
        "tank_threshold": tank_level["threshold"],
        "refill_started_at": refill_started_at.isoformat(),
        "refill_timeout_at": refill_timeout_at.isoformat(),
        "refill_attempt": next_attempt,
        "next_check": {
            "enqueue_id": enqueue_result["enqueue_id"],
            "scheduled_for": enqueue_result["scheduled_for"],
            "expires_at": enqueue_result["expires_at"],
            "correlation_id": enqueue_result["correlation_id"],
        },
    }


__all__ = ["execute_cycle_start_refill_sequence"]
