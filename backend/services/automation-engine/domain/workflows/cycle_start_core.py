"""Extracted workflow core implementation.

This module is imported lazily from SchedulerTaskExecutor to keep startup import-order stable.
"""

from __future__ import annotations

from application.scheduler_executor_impl import *  # noqa: F401,F403
from services.resilience_contract import (
    INFRA_CYCLE_START_ENQUEUE_FAILED,
    INFRA_CYCLE_START_NODES_UNAVAILABLE,
    INFRA_CYCLE_START_REFILL_COMMAND_FAILED,
    INFRA_CYCLE_START_TANK_LEVEL_STALE,
    INFRA_CYCLE_START_TANK_LEVEL_UNAVAILABLE,
    INFRA_TANK_REFILL_TIMEOUT,
)


async def execute_cycle_start_workflow_core(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: DecisionOutcome,
) -> Dict[str, Any]:
    workflow = self._extract_workflow(payload)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    refill_attempt = self._resolve_refill_attempt(payload)
    refill_started_at = self._resolve_refill_started_at(payload, now)
    refill_timeout_at = self._resolve_refill_timeout_at(payload, refill_started_at)

    await self._emit_task_event(
        zone_id=zone_id,
        task_type="diagnostics",
        context=context,
        event_type="CYCLE_START_INITIATED",
        payload={
            "workflow": workflow,
            "refill_attempt": refill_attempt,
            "refill_started_at": refill_started_at.isoformat(),
            "refill_timeout_at": refill_timeout_at.isoformat(),
            "action_required": decision.action_required,
            "decision": decision.decision,
            "reason_code": decision.reason_code,
        },
    )

    required_types = self._resolve_required_node_types(payload)
    nodes_state = await self._check_required_nodes_online(zone_id, required_types)
    missing_types = nodes_state["missing_types"]
    await self._emit_task_event(
        zone_id=zone_id,
        task_type="diagnostics",
        context=context,
        event_type="NODES_AVAILABILITY_CHECKED",
        payload={
            "required_node_types": nodes_state["required_types"],
            "online_node_counts": nodes_state["online_counts"],
            "missing_node_types": missing_types,
            "action_required": decision.action_required,
            "decision": decision.decision,
            "reason_code": REASON_REQUIRED_NODES_CHECKED,
        },
    )
    if missing_types:
        error = ERR_CYCLE_REQUIRED_NODES_UNAVAILABLE
        await self._emit_cycle_alert(
            zone_id=zone_id,
            code=INFRA_CYCLE_START_NODES_UNAVAILABLE,
            message=f"Старт цикла заблокирован: нет online-нод ({', '.join(missing_types)})",
            severity="error",
            details={
                "workflow": workflow,
                "missing_node_types": missing_types,
                "required_node_types": nodes_state["required_types"],
            },
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
            "reason_code": REASON_CYCLE_BLOCKED_NODES_UNAVAILABLE,
            "reason": "Не хватает обязательных online-нод для старта цикла",
            "error": error,
            "error_code": error,
        }

    tank_level = await self._read_clean_tank_level(zone_id, payload)
    await self._emit_task_event(
        zone_id=zone_id,
        task_type="diagnostics",
        context=context,
        event_type="TANK_LEVEL_CHECKED",
        payload={
            "sensor_id": tank_level["sensor_id"],
            "sensor_label": tank_level["sensor_label"],
            "level": tank_level["level"],
            "threshold": tank_level["threshold"],
            "is_full": tank_level["is_full"],
            "sample_ts": tank_level["sample_ts"],
            "sample_age_sec": tank_level["sample_age_sec"],
            "is_stale": tank_level["is_stale"],
            "action_required": decision.action_required,
            "decision": decision.decision,
            "reason_code": REASON_TANK_LEVEL_CHECKED,
        },
    )
    if not tank_level["has_level"]:
        error = ERR_CYCLE_TANK_LEVEL_UNAVAILABLE
        await self._emit_cycle_alert(
            zone_id=zone_id,
            code=INFRA_CYCLE_START_TANK_LEVEL_UNAVAILABLE,
            message="Старт цикла невозможен: нет валидной телеметрии уровня бака чистой воды",
            severity="error",
            details={
                "workflow": workflow,
                "sensor_id": tank_level["sensor_id"],
                "sensor_label": tank_level["sensor_label"],
            },
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
            "reason_code": REASON_CYCLE_TANK_LEVEL_UNAVAILABLE,
            "reason": "Нет данных уровня бака чистой воды",
            "error": error,
            "error_code": error,
        }

    if self._telemetry_freshness_enforce() and tank_level["is_stale"]:
        error = ERR_CYCLE_TANK_LEVEL_STALE
        await self._emit_task_event(
            zone_id=zone_id,
            task_type="diagnostics",
            context=context,
            event_type="TANK_LEVEL_STALE",
            payload={
                "sensor_id": tank_level["sensor_id"],
                "sensor_label": tank_level["sensor_label"],
                "level": tank_level["level"],
                "sample_ts": tank_level["sample_ts"],
                "sample_age_sec": tank_level["sample_age_sec"],
                "max_age_sec": self._telemetry_freshness_max_age_sec(),
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_CYCLE_TANK_LEVEL_STALE,
                "error_code": error,
            },
        )
        await self._emit_cycle_alert(
            zone_id=zone_id,
            code=INFRA_CYCLE_START_TANK_LEVEL_STALE,
            message="Старт цикла заблокирован: телеметрия уровня бака устарела",
            severity="error",
            details={
                "workflow": workflow,
                "sensor_id": tank_level["sensor_id"],
                "sensor_label": tank_level["sensor_label"],
                "sample_ts": tank_level["sample_ts"],
                "sample_age_sec": tank_level["sample_age_sec"],
                "max_age_sec": self._telemetry_freshness_max_age_sec(),
            },
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
            "reason_code": REASON_CYCLE_TANK_LEVEL_STALE,
            "reason": "Телеметрия уровня бака устарела, выполнение запрещено fail-safe политикой",
            "error": error,
            "error_code": error,
            "sample_ts": tank_level["sample_ts"],
            "sample_age_sec": tank_level["sample_age_sec"],
            "max_age_sec": self._telemetry_freshness_max_age_sec(),
        }

    if tank_level["is_full"]:
        if workflow == "refill_check":
            await self._emit_task_event(
                zone_id=zone_id,
                task_type="diagnostics",
                context=context,
                event_type="TANK_REFILL_COMPLETED",
                payload={
                    "level": tank_level["level"],
                    "threshold": tank_level["threshold"],
                    "refill_attempt": refill_attempt,
                    "action_required": False,
                    "decision": "skip",
                    "reason_code": REASON_TANK_REFILL_COMPLETED,
                },
            )
        return {
            "success": True,
            "task_type": "diagnostics",
            "mode": "cycle_start_ready",
            "workflow": workflow,
            "commands_total": 0,
            "commands_failed": 0,
            "action_required": False,
            "decision": "skip",
            "reason_code": REASON_TANK_REFILL_NOT_REQUIRED,
            "reason": "Бак чистой воды уже заполнен, наполнение не требуется",
            "tank_level": tank_level["level"],
            "tank_threshold": tank_level["threshold"],
        }

    if workflow == "refill_check" and now >= refill_timeout_at:
        await self._emit_task_event(
            zone_id=zone_id,
            task_type="diagnostics",
            context=context,
            event_type="TANK_REFILL_TIMEOUT",
            payload={
                "level": tank_level["level"],
                "threshold": tank_level["threshold"],
                "refill_started_at": refill_started_at.isoformat(),
                "refill_timeout_at": refill_timeout_at.isoformat(),
                "refill_attempt": refill_attempt,
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_CYCLE_REFILL_TIMEOUT,
                "error_code": ERR_CYCLE_REFILL_TIMEOUT,
            },
        )
        await self._emit_cycle_alert(
            zone_id=zone_id,
            code=INFRA_TANK_REFILL_TIMEOUT,
            message="Таймаут наполнения бака чистой воды",
            severity="critical",
            details={
                "workflow": workflow,
                "level": tank_level["level"],
                "threshold": tank_level["threshold"],
                "refill_started_at": refill_started_at.isoformat(),
                "refill_timeout_at": refill_timeout_at.isoformat(),
                "refill_attempt": refill_attempt,
            },
        )
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "cycle_start_refill_timeout",
            "workflow": workflow,
            "commands_total": 0,
            "commands_failed": 0,
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_CYCLE_REFILL_TIMEOUT,
            "reason": "Бак чистой воды не заполнился до таймаута",
            "error": ERR_CYCLE_REFILL_TIMEOUT,
            "error_code": ERR_CYCLE_REFILL_TIMEOUT,
            "tank_level": tank_level["level"],
            "tank_threshold": tank_level["threshold"],
            "refill_started_at": refill_started_at.isoformat(),
            "refill_timeout_at": refill_timeout_at.isoformat(),
        }

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
