"""Two-tank startup branch extracted from monolithic core."""

from __future__ import annotations

from application.scheduler_executor_impl import *  # noqa: F401,F403


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
        clean_level = await self._read_level_switch(
            zone_id=zone_id,
            sensor_labels=runtime_cfg["clean_max_labels"],
            threshold=runtime_cfg["level_switch_on_threshold"],
        )
        await self._emit_task_event(
            zone_id=zone_id,
            task_type="diagnostics",
            context=context,
            event_type="TANK_LEVEL_CHECKED",
            payload={
                "tank": "clean",
                "sensor_id": clean_level["sensor_id"],
                "sensor_label": clean_level["sensor_label"],
                "level": clean_level["level"],
                "is_triggered": clean_level["is_triggered"],
                "sample_ts": clean_level["sample_ts"],
                "sample_age_sec": clean_level["sample_age_sec"],
                "is_stale": clean_level["is_stale"],
                "reason_code": REASON_TANK_LEVEL_CHECKED,
            },
        )
        if not clean_level["has_level"]:
            logger.warning(
                "Zone %s: two_tank clean level unavailable (startup), expected=%s available=%s source=%s",
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

        if clean_level["is_triggered"]:
            return await self._start_two_tank_solution_fill(
                zone_id=zone_id,
                payload=payload,
                context=context,
                runtime_cfg=runtime_cfg,
            )

        return await self._start_two_tank_clean_fill(
            zone_id=zone_id,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
            cycle=1,
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

    if workflow == "prepare_recirculation":
        return await self._start_two_tank_prepare_recirculation(
            zone_id=zone_id,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
        )

    if workflow == "prepare_recirculation_check":
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        phase_started_at = parse_iso_datetime(str(payload.get("prepare_recirculation_started_at") or "")) or now
        phase_timeout_at = parse_iso_datetime(str(payload.get("prepare_recirculation_timeout_at") or ""))
        if phase_timeout_at is None:
            phase_timeout_at = phase_started_at + timedelta(seconds=runtime_cfg["prepare_recirculation_timeout_sec"])

        prepare_event = await self._find_zone_event_since(
            zone_id=zone_id,
            event_types=("PREPARE_TARGETS_REACHED",),
            since=phase_started_at,
        )
        targets_state = await self._evaluate_ph_ec_targets(
            zone_id=zone_id,
            target_ph=float(runtime_cfg["target_ph"]),
            target_ec=float(runtime_cfg["target_ec_prepare"]),
            tolerance=runtime_cfg["prepare_tolerance"],
        )
        if prepare_event or targets_state["targets_reached"]:
            stop_result = await self._dispatch_two_tank_command_plan(
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
            stop_result = await self._merge_with_sensor_mode_deactivate(
                zone_id=zone_id,
                context=context,
                stop_result=stop_result,
                reason_code=REASON_PREPARE_TARGETS_REACHED,
            )
            if not stop_result.get("success"):
                return {
                    "success": False,
                    "task_type": "diagnostics",
                    "mode": "two_tank_prepare_recirculation_stop_failed",
                    "workflow": workflow,
                    "commands_total": stop_result.get("commands_total", 0),
                    "commands_failed": stop_result.get("commands_failed", 1),
                    "command_statuses": stop_result.get("command_statuses", []),
                    "action_required": True,
                    "decision": "run",
                    "reason_code": REASON_CYCLE_REFILL_COMMAND_FAILED,
                    "reason": "Не удалось остановить prepare recirculation",
                    "error": str(stop_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED),
                    "error_code": str(stop_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED),
                }
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
                "mode": "two_tank_prepare_recirculation_completed",
                "workflow": workflow,
                "commands_total": stop_result.get("commands_total", 0),
                "commands_failed": stop_result.get("commands_failed", 0),
                "command_statuses": stop_result.get("command_statuses", []),
                "action_required": False,
                "decision": "skip",
                "reason_code": REASON_PREPARE_TARGETS_REACHED,
                "reason": "Prepare recirculation достиг целевых EC/pH",
                "targets_state": targets_state,
            }

        if now >= phase_timeout_at:
            stop_result = await self._dispatch_two_tank_command_plan(
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
            stop_result = await self._merge_with_sensor_mode_deactivate(
                zone_id=zone_id,
                context=context,
                stop_result=stop_result,
                reason_code=REASON_PREPARE_TARGETS_NOT_REACHED,
            )
            if self._two_tank_safety_guards_enabled() and not stop_result.get("success"):
                self._log_two_tank_safety_guard(
                    zone_id=zone_id,
                    context=context,
                    phase="prepare_recirculation_timeout",
                    stop_result=stop_result,
                )
                return self._build_two_tank_stop_not_confirmed_result(
                    workflow=workflow,
                    mode="two_tank_prepare_recirculation_timeout_stop_not_confirmed",
                    reason="Таймаут prepare recirculation: stop не подтверждён",
                    stop_result=stop_result,
                )
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_prepare_recirculation_timeout",
                "workflow": workflow,
                "commands_total": stop_result.get("commands_total", 0),
                "commands_failed": stop_result.get("commands_failed", 0),
                "command_statuses": stop_result.get("command_statuses", []),
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_PREPARE_TARGETS_NOT_REACHED,
                "reason": "Prepare recirculation не достиг целевых EC/pH до таймаута",
                "error": ERR_PREPARE_NPK_PH_TARGET_NOT_REACHED,
                "error_code": ERR_PREPARE_NPK_PH_TARGET_NOT_REACHED,
                "targets_state": targets_state,
            }

        try:
            enqueue_result = await self._enqueue_two_tank_check(
                zone_id=zone_id,
                payload=payload,
                workflow="prepare_recirculation_check",
                phase_started_at=phase_started_at,
                phase_timeout_at=phase_timeout_at,
                poll_interval_sec=runtime_cfg["poll_interval_sec"],
            )
        except ValueError as exc:
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_prepare_recirculation_enqueue_failed",
                "workflow": workflow,
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
                "reason": "Не удалось запланировать следующую проверку prepare recirculation",
                "error": str(exc),
                "error_code": ERR_TWO_TANK_ENQUEUE_FAILED,
            }

        return {
            "success": True,
            "task_type": "diagnostics",
            "mode": "two_tank_prepare_recirculation_in_progress",
            "workflow": workflow,
            "commands_total": 0,
            "commands_failed": 0,
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_PREPARE_RECIRCULATION_STARTED,
            "reason": "Prepare recirculation продолжается",
            "prepare_recirculation_started_at": phase_started_at.isoformat(),
            "prepare_recirculation_timeout_at": phase_timeout_at.isoformat(),
            "next_check": enqueue_result,
            "targets_state": targets_state,
        }

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
