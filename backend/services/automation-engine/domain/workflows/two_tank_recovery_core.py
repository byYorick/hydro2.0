"""Two-tank recovery branch extracted from monolithic core."""

from __future__ import annotations

from executor.scheduler_executor_impl import *  # noqa: F401,F403


async def execute_two_tank_recovery_branch(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    workflow: str,
) -> Dict[str, Any]:
    if workflow == "irrigation_recovery":
        attempt = self._resolve_int(payload.get("irrigation_recovery_attempt"), 1, 1)
        return await self._start_two_tank_irrigation_recovery(
            zone_id=zone_id,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
            attempt=attempt,
        )

    if workflow == "irrigation_recovery_check":
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        attempt = self._resolve_int(payload.get("irrigation_recovery_attempt"), 1, 1)
        phase_started_at = parse_iso_datetime(str(payload.get("irrigation_recovery_started_at") or "")) or now
        phase_timeout_at = parse_iso_datetime(str(payload.get("irrigation_recovery_timeout_at") or ""))
        if phase_timeout_at is None:
            phase_timeout_at = phase_started_at + timedelta(seconds=runtime_cfg["irrigation_recovery_timeout_sec"])

        recovery_state = await self._evaluate_ph_ec_targets(
            zone_id=zone_id,
            target_ph=float(runtime_cfg["target_ph"]),
            target_ec=float(runtime_cfg["target_ec"]),
            tolerance=runtime_cfg["recovery_tolerance"],
        )
        if recovery_state["targets_reached"]:
            stop_result = await self._dispatch_two_tank_command_plan(
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
            stop_result = await self._merge_with_sensor_mode_deactivate(
                zone_id=zone_id,
                context=context,
                stop_result=stop_result,
                reason_code=REASON_IRRIGATION_RECOVERY_RECOVERED,
            )
            if not stop_result.get("success"):
                return {
                    "success": False,
                    "task_type": "diagnostics",
                    "mode": "two_tank_irrigation_recovery_stop_failed",
                    "workflow": workflow,
                    "commands_total": stop_result.get("commands_total", 0),
                    "commands_failed": stop_result.get("commands_failed", 1),
                    "command_statuses": stop_result.get("command_statuses", []),
                    "action_required": True,
                    "decision": "run",
                    "reason_code": REASON_IRRIGATION_RECOVERY_FAILED,
                    "reason": "Не удалось остановить irrigation recovery",
                    "error": str(stop_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED),
                    "error_code": str(stop_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED),
                }
            await self._update_zone_workflow_phase(
                zone_id=zone_id,
                workflow_phase=WORKFLOW_PHASE_IRRIGATING,
                workflow_stage="irrigation_recovery_check",
                reason_code=REASON_IRRIGATION_RECOVERY_RECOVERED,
                context=context,
            )
            return {
                "success": True,
                "task_type": "diagnostics",
                "mode": "two_tank_irrigation_recovery_completed",
                "workflow": workflow,
                "commands_total": stop_result.get("commands_total", 0),
                "commands_failed": stop_result.get("commands_failed", 0),
                "command_statuses": stop_result.get("command_statuses", []),
                "action_required": False,
                "decision": "skip",
                "reason_code": REASON_IRRIGATION_RECOVERY_RECOVERED,
                "reason": "Irrigation recovery успешно завершен",
                "irrigation_recovery_attempt": attempt,
                "targets_state": recovery_state,
            }

        if now >= phase_timeout_at:
            stop_result = await self._dispatch_two_tank_command_plan(
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
            stop_result = await self._merge_with_sensor_mode_deactivate(
                zone_id=zone_id,
                context=context,
                stop_result=stop_result,
                reason_code=REASON_IRRIGATION_RECOVERY_FAILED,
            )
            if self._two_tank_safety_guards_enabled() and not stop_result.get("success"):
                self._log_two_tank_safety_guard(
                    zone_id=zone_id,
                    context=context,
                    phase="irrigation_recovery_timeout",
                    stop_result=stop_result,
                )
                return self._build_two_tank_stop_not_confirmed_result(
                    workflow=workflow,
                    mode="two_tank_irrigation_recovery_timeout_stop_not_confirmed",
                    reason="Таймаут irrigation recovery: stop не подтверждён, retry запрещён",
                    stop_result=stop_result,
                )
            degraded_state = await self._evaluate_ph_ec_targets(
                zone_id=zone_id,
                target_ph=float(runtime_cfg["target_ph"]),
                target_ec=float(runtime_cfg["target_ec"]),
                tolerance=runtime_cfg["degraded_tolerance"],
            )
            if degraded_state["targets_reached"]:
                await self._update_zone_workflow_phase(
                    zone_id=zone_id,
                    workflow_phase=WORKFLOW_PHASE_IRRIGATING,
                    workflow_stage="irrigation_recovery_check",
                    reason_code=REASON_IRRIGATION_RECOVERY_DEGRADED,
                    context=context,
                )
                return {
                    "success": True,
                    "task_type": "diagnostics",
                    "mode": "two_tank_irrigation_recovery_degraded",
                    "workflow": workflow,
                    "commands_total": stop_result.get("commands_total", 0),
                    "commands_failed": stop_result.get("commands_failed", 0),
                    "command_statuses": stop_result.get("command_statuses", []),
                    "action_required": False,
                    "decision": "skip",
                    "reason_code": REASON_IRRIGATION_RECOVERY_DEGRADED,
                    "reason": "Irrigation recovery завершен в degraded tolerance",
                    "irrigation_recovery_attempt": attempt,
                    "targets_state": degraded_state,
                }

            if attempt < runtime_cfg["irrigation_recovery_max_attempts"]:
                return await self._start_two_tank_irrigation_recovery(
                    zone_id=zone_id,
                    payload={**payload, "irrigation_recovery_attempt": attempt + 1},
                    context=context,
                    runtime_cfg=runtime_cfg,
                    attempt=attempt + 1,
                )

            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_irrigation_recovery_failed",
                "workflow": workflow,
                "commands_total": stop_result.get("commands_total", 0),
                "commands_failed": stop_result.get("commands_failed", 0),
                "command_statuses": stop_result.get("command_statuses", []),
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_MANUAL_ACK_REQUIRED_AFTER_RETRIES,
                "reason": "Превышено число автопопыток irrigation recovery, требуется ручное подтверждение",
                "error": ERR_IRRIGATION_RECOVERY_ATTEMPTS_EXCEEDED,
                "error_code": ERR_IRRIGATION_RECOVERY_ATTEMPTS_EXCEEDED,
                "irrigation_recovery_attempt": attempt,
                "targets_state": recovery_state,
                "manual_ack_required": True,
            }

        try:
            enqueue_result = await self._enqueue_two_tank_check(
                zone_id=zone_id,
                payload={**payload, "irrigation_recovery_attempt": attempt},
                workflow="irrigation_recovery_check",
                phase_started_at=phase_started_at,
                phase_timeout_at=phase_timeout_at,
                poll_interval_sec=runtime_cfg["poll_interval_sec"],
                phase_cycle=attempt,
            )
        except ValueError as exc:
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_irrigation_recovery_enqueue_failed",
                "workflow": workflow,
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
                "reason": "Не удалось запланировать следующую проверку irrigation recovery",
                "error": str(exc),
                "error_code": ERR_TWO_TANK_ENQUEUE_FAILED,
            }

        return {
            "success": True,
            "task_type": "diagnostics",
            "mode": "two_tank_irrigation_recovery_in_progress",
            "workflow": workflow,
            "commands_total": 0,
            "commands_failed": 0,
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_IRRIGATION_RECOVERY_STARTED,
            "reason": "Irrigation recovery продолжается",
            "irrigation_recovery_attempt": attempt,
            "irrigation_recovery_started_at": phase_started_at.isoformat(),
            "irrigation_recovery_timeout_at": phase_timeout_at.isoformat(),
            "next_check": enqueue_result,
            "targets_state": recovery_state,
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
        "reason": f"Неподдерживаемый workflow для топологии two_tank: {workflow}",
        "error": "unsupported_workflow",
        "error_code": "unsupported_workflow",
    }
