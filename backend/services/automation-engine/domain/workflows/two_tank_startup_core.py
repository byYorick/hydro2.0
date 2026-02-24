"""Two-tank startup branch extracted from monolithic core."""

from __future__ import annotations

from executor.scheduler_executor_impl import *  # noqa: F401,F403
from domain.workflows.two_tank_startup_prepare_branch import handle_two_tank_prepare_branches
from domain.workflows.two_tank_startup_solution_branch import handle_two_tank_solution_fill_check
from domain.workflows.two_tank_startup_start_branch import (
    build_sensor_state_inconsistent_result,
    handle_two_tank_startup_initial,
)


async def execute_two_tank_startup_branch(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    workflow: str,
) -> Dict[str, Any]:
    if workflow == "startup":
        return await handle_two_tank_startup_initial(
            self,
            zone_id=zone_id,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
            workflow=workflow,
        )

    if workflow == "clean_fill_check":
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        clean_started_at = parse_iso_datetime(str(payload.get("clean_fill_started_at") or "")) or now
        clean_timeout_at = parse_iso_datetime(str(payload.get("clean_fill_timeout_at") or ""))
        if clean_timeout_at is None:
            clean_timeout_at = clean_started_at + timedelta(seconds=runtime_cfg["clean_fill_timeout_sec"])
        clean_cycle = self._resolve_int(payload.get("clean_fill_cycle"), 1, 1)

        clean_event = await self._find_zone_event_since(
            zone_id=zone_id,
            event_types=("CLEAN_FILL_COMPLETED",),
            since=clean_started_at,
        )
        clean_triggered = bool(clean_event)
        clean_level: Dict[str, Any] = {
            "sensor_id": None,
            "sensor_label": None,
            "level": None,
            "sample_ts": None,
            "sample_age_sec": None,
            "is_stale": False,
            "has_level": False,
            "is_triggered": False,
        }
        if not clean_triggered:
            clean_level = await self._read_level_switch(
                zone_id=zone_id,
                sensor_labels=runtime_cfg["clean_max_labels"],
                threshold=runtime_cfg["level_switch_on_threshold"],
            )
            clean_triggered = bool(clean_level["is_triggered"])
            if not clean_level["has_level"]:
                logger.warning(
                    "Zone %s: two_tank clean level unavailable (clean_fill_check), expected=%s available=%s source=%s",
                    zone_id,
                    clean_level.get("expected_labels", runtime_cfg["clean_max_labels"]),
                    clean_level.get("available_sensor_labels", []),
                    clean_level.get("level_source", "none"),
                )
                return {
                    "success": False,
                    "task_type": "diagnostics",
                    "mode": "two_tank_clean_level_unavailable",
                    "workflow": workflow,
                    "commands_total": 0,
                    "commands_failed": 0,
                    "action_required": True,
                    "decision": "run",
                    "reason_code": REASON_SENSOR_LEVEL_UNAVAILABLE,
                    "reason": "Нет данных датчика верхнего уровня чистого бака",
                    "error": ERR_TWO_TANK_LEVEL_UNAVAILABLE,
                    "error_code": ERR_TWO_TANK_LEVEL_UNAVAILABLE,
                    "expected_sensor_labels": clean_level.get("expected_labels", runtime_cfg["clean_max_labels"]),
                    "available_sensor_labels": clean_level.get("available_sensor_labels", []),
                    "level_source": clean_level.get("level_source", "none"),
                }
            if self._telemetry_freshness_enforce() and clean_level["is_stale"]:
                return {
                    "success": False,
                    "task_type": "diagnostics",
                    "mode": "two_tank_clean_level_stale",
                    "workflow": workflow,
                    "commands_total": 0,
                    "commands_failed": 0,
                    "action_required": True,
                    "decision": "run",
                    "reason_code": REASON_SENSOR_STALE_DETECTED,
                    "reason": "Телеметрия датчика верхнего уровня чистого бака устарела",
                    "error": ERR_TWO_TANK_LEVEL_STALE,
                    "error_code": ERR_TWO_TANK_LEVEL_STALE,
                }

        if clean_triggered:
            clean_min_level = await self._read_level_switch(
                zone_id=zone_id,
                sensor_labels=runtime_cfg["clean_min_labels"],
                threshold=runtime_cfg["level_switch_on_threshold"],
            )
            if not clean_min_level["has_level"]:
                return {
                    "success": False,
                    "task_type": "diagnostics",
                    "mode": "two_tank_clean_min_level_unavailable",
                    "workflow": workflow,
                    "commands_total": 0,
                    "commands_failed": 0,
                    "action_required": True,
                    "decision": "run",
                    "reason_code": REASON_SENSOR_LEVEL_UNAVAILABLE,
                    "reason": "Нет данных датчика нижнего уровня чистого бака",
                    "error": ERR_TWO_TANK_LEVEL_UNAVAILABLE,
                    "error_code": ERR_TWO_TANK_LEVEL_UNAVAILABLE,
                    "expected_sensor_labels": clean_min_level.get("expected_labels", runtime_cfg["clean_min_labels"]),
                    "available_sensor_labels": clean_min_level.get("available_sensor_labels", []),
                    "level_source": clean_min_level.get("level_source", "none"),
                }
            if self._telemetry_freshness_enforce() and clean_min_level["is_stale"]:
                return {
                    "success": False,
                    "task_type": "diagnostics",
                    "mode": "two_tank_clean_min_level_stale",
                    "workflow": workflow,
                    "commands_total": 0,
                    "commands_failed": 0,
                    "action_required": True,
                    "decision": "run",
                    "reason_code": REASON_SENSOR_STALE_DETECTED,
                    "reason": "Телеметрия датчика нижнего уровня чистого бака устарела",
                    "error": ERR_TWO_TANK_LEVEL_STALE,
                    "error_code": ERR_TWO_TANK_LEVEL_STALE,
                }
            if not clean_min_level["is_triggered"]:
                return build_sensor_state_inconsistent_result(
                    workflow=workflow,
                    reason="Несогласованность датчиков чистого бака после наполнения: max=1 и min=0",
                    clean_level_max=True,
                    clean_level_min=False,
                )
            stop_result = await self._dispatch_two_tank_command_plan(
                zone_id=zone_id,
                command_plan=runtime_cfg["commands"]["clean_fill_stop"],
                context=context,
                decision=DecisionOutcome(
                    action_required=True,
                    decision="run",
                    reason_code=REASON_CLEAN_FILL_COMPLETED,
                    reason="Остановка наполнения чистого бака",
                ),
            )
            if not stop_result.get("success"):
                return {
                    "success": False,
                    "task_type": "diagnostics",
                    "mode": "two_tank_clean_fill_stop_failed",
                    "workflow": workflow,
                    "commands_total": stop_result.get("commands_total", 0),
                    "commands_failed": stop_result.get("commands_failed", 1),
                    "command_statuses": stop_result.get("command_statuses", []),
                    "action_required": True,
                    "decision": "run",
                    "reason_code": REASON_CYCLE_REFILL_COMMAND_FAILED,
                    "reason": "Не удалось остановить наполнение чистого бака",
                    "error": str(stop_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED),
                    "error_code": str(stop_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED),
                }

            await self._emit_task_event(
                zone_id=zone_id,
                task_type="diagnostics",
                context=context,
                event_type="CLEAN_FILL_COMPLETED",
                payload={
                    "source": "event" if clean_event else "sensor",
                    "clean_fill_cycle": clean_cycle,
                    "reason_code": REASON_CLEAN_FILL_COMPLETED,
                },
            )
            return await self._start_two_tank_solution_fill(
                zone_id=zone_id,
                payload=payload,
                context=context,
                runtime_cfg=runtime_cfg,
            )

        if now >= clean_timeout_at:
            stop_result = await self._dispatch_two_tank_command_plan(
                zone_id=zone_id,
                command_plan=runtime_cfg["commands"]["clean_fill_stop"],
                context=context,
                decision=DecisionOutcome(
                    action_required=True,
                    decision="run",
                    reason_code=REASON_CLEAN_FILL_TIMEOUT,
                    reason="Остановка наполнения чистого бака по таймауту",
                ),
            )
            if self._two_tank_safety_guards_enabled() and not stop_result.get("success"):
                self._log_two_tank_safety_guard(
                    zone_id=zone_id,
                    context=context,
                    phase="clean_fill_timeout",
                    stop_result=stop_result,
                )
                return self._build_two_tank_stop_not_confirmed_result(
                    workflow=workflow,
                    mode="two_tank_clean_fill_timeout_stop_not_confirmed",
                    reason="Таймаут clean fill: stop не подтверждён, повторный старт запрещён",
                    stop_result=stop_result,
                )
            if clean_cycle <= runtime_cfg["clean_fill_retry_cycles"]:
                await self._emit_task_event(
                    zone_id=zone_id,
                    task_type="diagnostics",
                    context=context,
                    event_type="CLEAN_FILL_RETRY_STARTED",
                    payload={
                        "clean_fill_cycle": clean_cycle + 1,
                        "reason_code": REASON_CLEAN_FILL_RETRY_STARTED,
                    },
                )
                return await self._start_two_tank_clean_fill(
                    zone_id=zone_id,
                    payload=payload,
                    context=context,
                    runtime_cfg=runtime_cfg,
                    cycle=clean_cycle + 1,
                )

            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_clean_fill_timeout",
                "workflow": workflow,
                "commands_total": stop_result.get("commands_total", 0),
                "commands_failed": stop_result.get("commands_failed", 0),
                "command_statuses": stop_result.get("command_statuses", []),
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_CLEAN_FILL_TIMEOUT,
                "reason": "Таймаут наполнения чистого бака",
                "error": ERR_CLEAN_TANK_NOT_FILLED_TIMEOUT,
                "error_code": ERR_CLEAN_TANK_NOT_FILLED_TIMEOUT,
            }

        try:
            enqueue_result = await self._enqueue_two_tank_check(
                zone_id=zone_id,
                payload=payload,
                workflow="clean_fill_check",
                phase_started_at=clean_started_at,
                phase_timeout_at=clean_timeout_at,
                poll_interval_sec=runtime_cfg["poll_interval_sec"],
                phase_cycle=clean_cycle,
            )
        except ValueError as exc:
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_clean_fill_enqueue_failed",
                "workflow": workflow,
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
                "reason": "Не удалось запланировать следующую проверку наполнения чистого бака",
                "error": str(exc),
                "error_code": ERR_TWO_TANK_ENQUEUE_FAILED,
            }

        return {
            "success": True,
            "task_type": "diagnostics",
            "mode": "two_tank_clean_fill_in_progress",
            "workflow": workflow,
            "commands_total": 0,
            "commands_failed": 0,
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_CLEAN_FILL_IN_PROGRESS,
            "reason": "Наполнение чистого бака продолжается",
            "clean_fill_cycle": clean_cycle,
            "clean_fill_started_at": clean_started_at.isoformat(),
            "clean_fill_timeout_at": clean_timeout_at.isoformat(),
            "next_check": enqueue_result,
        }

    if workflow == "solution_fill_check":
        return await handle_two_tank_solution_fill_check(
            self,
            zone_id=zone_id,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
            workflow=workflow,
        )

    prepare_result = await handle_two_tank_prepare_branches(
        self,
        zone_id=zone_id,
        payload=payload,
        context=context,
        runtime_cfg=runtime_cfg,
        workflow=workflow,
    )
    if prepare_result is not None:
        return prepare_result

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
        "reason": f"Неподдерживаемый startup workflow для топологии two_tank: {workflow}",
        "error": "unsupported_workflow",
        "error_code": "unsupported_workflow",
    }
