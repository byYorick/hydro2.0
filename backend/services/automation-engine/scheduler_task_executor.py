"""Исполнение абстрактных задач расписания внутри automation-engine."""

from __future__ import annotations

import logging
import os
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from common.db import create_zone_event, fetch
from common.infra_alerts import send_infra_alert
from common.node_types import normalize_node_type
from config.scheduler_task_mapping import SchedulerTaskMapping, get_task_mapping
from infrastructure.command_bus import CommandBus
from scheduler_internal_enqueue import enqueue_internal_scheduler_task, parse_iso_datetime

logger = logging.getLogger(__name__)

def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


CYCLE_START_REQUIRED_NODE_TYPES = tuple(
    item.strip()
    for item in os.getenv(
        "AE_CYCLE_START_REQUIRED_NODE_TYPES",
        "irrig,climate,light",
    ).split(",")
    if item.strip()
)
CLEAN_TANK_FULL_THRESHOLD = max(0.0, min(1.0, _env_float("AE_CLEAN_TANK_FULL_THRESHOLD", 0.95)))
REFILL_CHECK_DELAY_SEC = max(10, _env_int("AE_REFILL_CHECK_DELAY_SEC", 60))
REFILL_TIMEOUT_SEC = max(30, _env_int("AE_REFILL_TIMEOUT_SEC", 600))
REFILL_COMMAND_DURATION_SEC = max(1, _env_int("AE_REFILL_COMMAND_DURATION_SEC", 30))
TASK_EXECUTE_CLOSED_LOOP_ENFORCE = _env_bool("AE_TASK_EXECUTE_CLOSED_LOOP", True)
TASK_EXECUTE_CLOSED_LOOP_TIMEOUT_SEC = max(1.0, _env_float("AE_TASK_EXECUTE_CLOSED_LOOP_TIMEOUT_SEC", 60.0))
TELEMETRY_FRESHNESS_ENFORCE = _env_bool("AE_TELEMETRY_FRESHNESS_ENFORCE", True)
TELEMETRY_FRESHNESS_MAX_AGE_SEC = max(30, _env_int("AE_TELEMETRY_FRESHNESS_MAX_AGE_SEC", 300))


ERR_COMMAND_PUBLISH_FAILED = "command_publish_failed"
ERR_COMMAND_SEND_FAILED = "command_send_failed"
ERR_COMMAND_TIMEOUT = "command_timeout"
ERR_COMMAND_ERROR = "command_error"
ERR_COMMAND_INVALID = "command_invalid"
ERR_COMMAND_BUSY = "command_busy"
ERR_COMMAND_NO_EFFECT = "command_no_effect"
ERR_COMMAND_TRACKER_UNAVAILABLE = "command_tracker_unavailable"
ERR_COMMAND_EFFECT_NOT_CONFIRMED = "command_effect_not_confirmed"
ERR_MAPPING_NOT_FOUND = "mapping_not_found"
ERR_NO_ONLINE_NODES = "no_online_nodes"
ERR_CYCLE_REQUIRED_NODES_UNAVAILABLE = "cycle_start_required_nodes_unavailable"
ERR_CYCLE_TANK_LEVEL_UNAVAILABLE = "cycle_start_tank_level_unavailable"
ERR_CYCLE_TANK_LEVEL_STALE = "cycle_start_tank_level_stale"
ERR_CYCLE_REFILL_TIMEOUT = "cycle_start_refill_timeout"
ERR_CYCLE_REFILL_NODE_NOT_FOUND = "cycle_start_refill_node_not_found"
ERR_CYCLE_REFILL_COMMAND_FAILED = "cycle_start_refill_command_failed"
ERR_CYCLE_SELF_TASK_ENQUEUE_FAILED = "cycle_start_self_task_enqueue_failed"
ERR_CLEAN_TANK_NOT_FILLED_TIMEOUT = "clean_tank_not_filled_timeout"
ERR_SOLUTION_TANK_NOT_FILLED_TIMEOUT = "solution_tank_not_filled_timeout"
ERR_TWO_TANK_LEVEL_UNAVAILABLE = "two_tank_level_unavailable"
ERR_TWO_TANK_LEVEL_STALE = "two_tank_level_stale"
ERR_TWO_TANK_COMMAND_FAILED = "two_tank_command_failed"
ERR_TWO_TANK_ENQUEUE_FAILED = "two_tank_enqueue_failed"
ERR_TWO_TANK_CHANNEL_NOT_FOUND = "two_tank_channel_not_found"
ERR_PREPARE_NPK_PH_TARGET_NOT_REACHED = "prepare_npk_ph_target_not_reached"
ERR_IRRIGATION_RECOVERY_ATTEMPTS_EXCEEDED = "irrigation_recovery_attempts_exceeded"
ERR_DIAGNOSTICS_SERVICE_UNAVAILABLE = "diagnostics_service_unavailable"

REASON_REQUIRED_NODES_CHECKED = "required_nodes_checked"
REASON_TANK_LEVEL_CHECKED = "tank_level_checked"
REASON_TANK_REFILL_REQUIRED = "tank_refill_required"
REASON_TANK_REFILL_STARTED = "tank_refill_started"
REASON_TANK_REFILL_IN_PROGRESS = "tank_refill_in_progress"
REASON_TANK_REFILL_COMPLETED = "tank_refill_completed"
REASON_TANK_REFILL_NOT_REQUIRED = "tank_refill_not_required"
REASON_CYCLE_BLOCKED_NODES_UNAVAILABLE = "cycle_start_blocked_nodes_unavailable"
REASON_CYCLE_TANK_LEVEL_UNAVAILABLE = "cycle_start_tank_level_unavailable"
REASON_CYCLE_TANK_LEVEL_STALE = "cycle_start_tank_level_stale"
REASON_CYCLE_REFILL_TIMEOUT = "cycle_start_refill_timeout"
REASON_CYCLE_REFILL_COMMAND_FAILED = "cycle_start_refill_command_failed"
REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED = "cycle_start_self_task_enqueue_failed"
REASON_CLEAN_FILL_STARTED = "clean_fill_started"
REASON_CLEAN_FILL_COMPLETED = "clean_fill_completed"
REASON_CLEAN_FILL_IN_PROGRESS = "clean_fill_in_progress"
REASON_CLEAN_FILL_TIMEOUT = "clean_fill_timeout"
REASON_CLEAN_FILL_RETRY_STARTED = "clean_fill_retry_started"
REASON_SOLUTION_FILL_STARTED = "solution_fill_started"
REASON_SOLUTION_FILL_COMPLETED = "solution_fill_completed"
REASON_SOLUTION_FILL_IN_PROGRESS = "solution_fill_in_progress"
REASON_SOLUTION_FILL_TIMEOUT = "solution_fill_timeout"
REASON_PREPARE_RECIRCULATION_STARTED = "prepare_recirculation_started"
REASON_PREPARE_TARGETS_REACHED = "prepare_targets_reached"
REASON_PREPARE_TARGETS_NOT_REACHED = "prepare_targets_not_reached"
REASON_IRRIGATION_RECOVERY_STARTED = "irrigation_recovery_started"
REASON_IRRIGATION_RECOVERY_RECOVERED = "irrigation_recovery_recovered"
REASON_IRRIGATION_RECOVERY_FAILED = "irrigation_recovery_failed"
REASON_IRRIGATION_RECOVERY_DEGRADED = "irrigation_recovery_degraded"
REASON_ONLINE_CORRECTION_FAILED = "online_correction_failed"
REASON_TANK_TO_TANK_CORRECTION_STARTED = "tank_to_tank_correction_started"
REASON_SENSOR_STALE_DETECTED = "sensor_stale_detected"
REASON_SENSOR_LEVEL_UNAVAILABLE = "sensor_level_unavailable"
REASON_DIAGNOSTICS_SERVICE_UNAVAILABLE = "diagnostics_service_unavailable"
REASON_WIND_BLOCKED = "wind_blocked"
REASON_OUTSIDE_TEMP_BLOCKED = "outside_temp_blocked"


@dataclass(frozen=True)
class DecisionOutcome:
    action_required: bool
    decision: str
    reason_code: str
    reason: str


class SchedulerTaskExecutor:
    """Исполняет абстрактные задачи от scheduler через CommandBus."""

    def __init__(self, command_bus: CommandBus, zone_service: Optional[Any] = None):
        self.command_bus = command_bus
        self.zone_service = zone_service

    async def execute(
        self,
        *,
        zone_id: int,
        task_type: str,
        payload: Dict[str, Any],
        task_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        task_type = str(task_type or "").strip().lower()
        payload = payload if isinstance(payload, dict) else {}
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        mapping = get_task_mapping(task_type, config)

        context = {
            "task_id": str((task_context or {}).get("task_id") or ""),
            "correlation_id": str((task_context or {}).get("correlation_id") or ""),
            "scheduled_for": (task_context or {}).get("scheduled_for"),
            "event_seq": 0,
        }

        await self._emit_task_event(
            zone_id=zone_id,
            task_type=task_type,
            context=context,
            event_type="TASK_RECEIVED",
            payload={
                "payload": payload,
                "scheduled_for": context.get("scheduled_for"),
            },
        )
        await self._emit_task_event(
            zone_id=zone_id,
            task_type=task_type,
            context=context,
            event_type="TASK_STARTED",
            payload={"payload": payload},
        )
        await create_zone_event(
            zone_id,
            "SCHEDULE_TASK_EXECUTION_STARTED",
            {
                "task_type": task_type,
                "payload": payload,
                "task_id": context["task_id"] or None,
                "correlation_id": context["correlation_id"] or None,
            },
        )

        decision = self._decide_action(task_type=task_type, payload=payload)
        if task_type == "ventilation":
            decision = await self._apply_ventilation_climate_guards(
                zone_id=zone_id,
                payload=payload,
                decision=decision,
            )
        await self._emit_task_event(
            zone_id=zone_id,
            task_type=task_type,
            context=context,
            event_type="DECISION_MADE",
            payload={
                "action_required": decision.action_required,
                "decision": decision.decision,
                "reason_code": decision.reason_code,
                "reason": decision.reason,
            },
        )

        if not decision.action_required:
            result = {
                "success": True,
                "task_type": task_type,
                "mode": "decision_skip",
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": False,
                "decision": "skip",
                "reason_code": decision.reason_code,
                "reason": decision.reason,
            }
        elif task_type == "diagnostics" and self._is_two_tank_startup_workflow(payload):
            result = await self._execute_two_tank_startup_workflow(
                zone_id=zone_id,
                payload=payload,
                context=context,
                decision=decision,
            )
        elif task_type == "diagnostics" and self._is_three_tank_startup_workflow(payload):
            result = await self._execute_three_tank_startup_workflow(
                zone_id=zone_id,
                payload=payload,
                context=context,
                decision=decision,
            )
        elif task_type == "diagnostics" and self._is_cycle_start_workflow(payload):
            result = await self._execute_cycle_start_workflow(
                zone_id=zone_id,
                payload=payload,
                context=context,
                decision=decision,
            )
        elif task_type == "diagnostics":
            result = await self._execute_diagnostics(
                zone_id,
                payload,
                context=context,
                decision=decision,
            )
        else:
            result = await self._execute_device_task(
                zone_id,
                payload,
                mapping,
                context=context,
                decision=decision,
            )
            if task_type == "irrigation":
                recovery_result = await self._try_start_two_tank_irrigation_recovery_from_irrigation_failure(
                    zone_id=zone_id,
                    payload=payload,
                    context=context,
                    result=result,
                )
                if recovery_result is not None:
                    result = recovery_result

        result.setdefault("action_required", decision.action_required)
        result.setdefault("decision", decision.decision)
        result.setdefault("reason_code", decision.reason_code)
        result.setdefault("reason", decision.reason)

        await self._emit_task_event(
            zone_id=zone_id,
            task_type=task_type,
            context=context,
            event_type="TASK_FINISHED",
            payload={
                "success": bool(result.get("success")),
                "result": result,
                "action_required": bool(result.get("action_required")),
                "decision": str(result.get("decision") or "unknown"),
                "reason_code": str(result.get("reason_code") or "unknown"),
            },
        )
        await create_zone_event(
            zone_id,
            "SCHEDULE_TASK_EXECUTION_FINISHED",
            {
                "task_type": task_type,
                "success": bool(result.get("success")),
                "result": result,
                "task_id": context["task_id"] or None,
                "correlation_id": context["correlation_id"] or None,
            },
        )
        return result

    @staticmethod
    def _decide_action(task_type: str, payload: Dict[str, Any]) -> DecisionOutcome:
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}

        if execution.get("force_skip") is True:
            return DecisionOutcome(
                action_required=False,
                decision="skip",
                reason_code=f"{task_type}_not_required",
                reason="Пропуск задачи по force_skip",
            )

        if execution.get("force_execute") is True:
            return DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code=f"{task_type}_required",
                reason="Принудительное выполнение по force_execute",
            )

        explicit_action_required = payload.get("action_required")
        if isinstance(explicit_action_required, bool):
            if explicit_action_required:
                return DecisionOutcome(
                    action_required=True,
                    decision="run",
                    reason_code=f"{task_type}_required",
                    reason="Явно запрошено выполнение action_required=true",
                )
            return DecisionOutcome(
                action_required=False,
                decision="skip",
                reason_code=f"{task_type}_not_required",
                reason="Явно запрошен пропуск action_required=false",
            )

        if task_type == "lighting":
            desired_state = payload.get("desired_state")
            current_state = payload.get("current_state")
            if isinstance(desired_state, bool) and isinstance(current_state, bool) and desired_state == current_state:
                return DecisionOutcome(
                    action_required=False,
                    decision="skip",
                    reason_code="lighting_already_in_target_state",
                    reason="Свет уже находится в целевом состоянии",
                )

        return DecisionOutcome(
            action_required=True,
            decision="run",
            reason_code=f"{task_type}_required",
            reason="Требуется выполнить задачу по расписанию",
        )

    async def _emit_task_event(
        self,
        *,
        zone_id: int,
        task_type: str,
        context: Dict[str, Any],
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        context["event_seq"] = int(context.get("event_seq") or 0) + 1
        event_payload = {
            "event_id": f"evt-{uuid4().hex}",
            "event_seq": context["event_seq"],
            "event_type": event_type,
            "occurred_at": datetime.utcnow().isoformat(),
            "zone_id": zone_id,
            "task_type": task_type,
            "task_id": context.get("task_id") or None,
            "correlation_id": context.get("correlation_id") or None,
        }
        if isinstance(payload, dict):
            event_payload.update(payload)
        await create_zone_event(zone_id, event_type, event_payload)

    async def _get_zone_nodes(self, zone_id: int, node_types: Sequence[str]) -> List[Dict[str, Any]]:
        normalized_types = [str(item).strip().lower() for item in node_types if str(item).strip()]
        if not normalized_types:
            return []

        rows = await fetch(
            """
            SELECT n.uid, n.type, COALESCE(nc.channel, 'default') AS channel
            FROM nodes n
            LEFT JOIN node_channels nc ON nc.node_id = n.id
            WHERE n.zone_id = $1
              AND LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
              AND LOWER(TRIM(COALESCE(n.type, ''))) = ANY($2::text[])
            """,
            zone_id,
            normalized_types,
        )
        result: List[Dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "node_uid": row["uid"],
                    "type": row["type"],
                    "channel": row["channel"] or "default",
                }
            )
        return result

    async def _publish_batch(
        self,
        *,
        zone_id: int,
        task_type: str,
        nodes: Sequence[Dict[str, Any]],
        cmd: str,
        params: Optional[Dict[str, Any]] = None,
        context: Dict[str, Any],
        decision: DecisionOutcome,
    ) -> Dict[str, Any]:
        commands_total = 0
        commands_submitted = 0
        commands_effect_confirmed = 0
        commands_failed = 0
        first_failure_error_code: Optional[str] = None
        command_statuses: List[Dict[str, Any]] = []

        for node in nodes:
            node_uid = node["node_uid"]
            channel = node.get("channel") or "default"
            await self._emit_task_event(
                zone_id=zone_id,
                task_type=task_type,
                context=context,
                event_type="COMMAND_DISPATCHED",
                payload={
                    "node_uid": node_uid,
                    "channel": channel,
                    "cmd": cmd,
                    "params": params or {},
                    "action_required": decision.action_required,
                    "decision": decision.decision,
                    "reason_code": decision.reason_code,
                },
            )

            commands_total += 1
            controller_command = {
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
                "params": params or {},
            }

            submitted = False
            effect_confirmed = False
            terminal_status = "SEND_FAILED"
            failure_error_code = ERR_COMMAND_SEND_FAILED
            cmd_id: Optional[str] = None

            if TASK_EXECUTE_CLOSED_LOOP_ENFORCE and hasattr(self.command_bus, "publish_controller_command_closed_loop"):
                closed_loop_result = await self.command_bus.publish_controller_command_closed_loop(
                    zone_id=zone_id,
                    command=controller_command,
                    context={
                        "task_id": context.get("task_id"),
                        "correlation_id": context.get("correlation_id"),
                        "task_type": task_type,
                        "reason_code": decision.reason_code,
                    },
                    timeout_sec=TASK_EXECUTE_CLOSED_LOOP_TIMEOUT_SEC,
                )
                submitted = bool(closed_loop_result.get("command_submitted"))
                effect_confirmed = bool(closed_loop_result.get("command_effect_confirmed"))
                terminal_status = str(closed_loop_result.get("terminal_status") or "ERROR").upper()
                cmd_id_raw = closed_loop_result.get("cmd_id")
                cmd_id = str(cmd_id_raw).strip() if isinstance(cmd_id_raw, str) and cmd_id_raw.strip() else None
                failure_error_code = self._terminal_status_to_error_code(terminal_status)
            elif TASK_EXECUTE_CLOSED_LOOP_ENFORCE:
                submitted = False
                effect_confirmed = False
                terminal_status = "TRACKER_UNAVAILABLE"
                failure_error_code = ERR_COMMAND_TRACKER_UNAVAILABLE
            else:
                submitted = await self.command_bus.publish_command(
                    zone_id=zone_id,
                    node_uid=node_uid,
                    channel=channel,
                    cmd=cmd,
                    params=params or {},
                )
                effect_confirmed = bool(submitted)
                terminal_status = "DONE" if submitted else "SEND_FAILED"
                failure_error_code = self._terminal_status_to_error_code(terminal_status)

            if submitted:
                commands_submitted += 1
            if effect_confirmed:
                commands_effect_confirmed += 1

            command_statuses.append(
                {
                    "node_uid": node_uid,
                    "channel": channel,
                    "cmd": cmd,
                    "cmd_id": cmd_id,
                    "command_submitted": submitted,
                    "command_effect_confirmed": effect_confirmed,
                    "terminal_status": terminal_status,
                }
            )

            if not effect_confirmed:
                commands_failed += 1
                if first_failure_error_code is None:
                    first_failure_error_code = failure_error_code
                await self._emit_task_event(
                    zone_id=zone_id,
                    task_type=task_type,
                    context=context,
                    event_type="COMMAND_FAILED",
                    payload={
                        "node_uid": node_uid,
                        "channel": channel,
                        "cmd": cmd,
                        "params": params or {},
                        "cmd_id": cmd_id,
                        "terminal_status": terminal_status,
                        "command_submitted": submitted,
                        "command_effect_confirmed": effect_confirmed,
                        "error_code": failure_error_code,
                        "action_required": decision.action_required,
                        "decision": decision.decision,
                        "reason_code": decision.reason_code,
                    },
                )

        success = commands_total > 0 and commands_effect_confirmed == commands_total and commands_failed == 0
        result = {
            "success": success,
            "task_type": task_type,
            "commands_total": commands_total,
            "commands_submitted": commands_submitted,
            "commands_effect_confirmed": commands_effect_confirmed,
            "commands_failed": commands_failed,
            "command_submitted": commands_total > 0 and commands_submitted == commands_total,
            "command_effect_confirmed": commands_total > 0 and commands_effect_confirmed == commands_total,
            "command_statuses": command_statuses,
            "cmd": cmd,
            "params": params or {},
        }
        if not success:
            result["error"] = first_failure_error_code or ERR_COMMAND_EFFECT_NOT_CONFIRMED
            result["error_code"] = first_failure_error_code or ERR_COMMAND_EFFECT_NOT_CONFIRMED
        return result

    @staticmethod
    def _terminal_status_to_error_code(status: str) -> str:
        normalized = str(status or "").strip().upper()
        if normalized == "DONE":
            return ""
        if normalized == "SEND_FAILED":
            return ERR_COMMAND_SEND_FAILED
        if normalized == "TIMEOUT":
            return ERR_COMMAND_TIMEOUT
        if normalized == "ERROR":
            return ERR_COMMAND_ERROR
        if normalized == "INVALID":
            return ERR_COMMAND_INVALID
        if normalized == "BUSY":
            return ERR_COMMAND_BUSY
        if normalized == "NO_EFFECT":
            return ERR_COMMAND_NO_EFFECT
        if normalized == "TRACKER_UNAVAILABLE":
            return ERR_COMMAND_TRACKER_UNAVAILABLE
        return ERR_COMMAND_EFFECT_NOT_CONFIRMED

    @staticmethod
    def _extract_duration_sec(payload: Dict[str, Any], mapping: SchedulerTaskMapping) -> Optional[float]:
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        targets = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}

        duration_raw = config.get("duration_sec")
        if duration_raw is None:
            execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
            duration_raw = execution.get("duration_sec")

        if duration_raw is None:
            for section, field in mapping.duration_target_paths:
                section_payload = targets.get(section)
                if isinstance(section_payload, dict) and field in section_payload:
                    duration_raw = section_payload.get(field)
                    break

        if duration_raw is None:
            duration_raw = mapping.default_duration_sec

        try:
            duration_sec = float(duration_raw) if duration_raw is not None else None
        except (TypeError, ValueError):
            duration_sec = mapping.default_duration_sec

        if duration_sec is None or duration_sec <= 0:
            return None
        return duration_sec

    def _resolve_command_name(self, payload: Dict[str, Any], mapping: SchedulerTaskMapping) -> Optional[str]:
        if mapping.state_key and (mapping.cmd_true or mapping.cmd_false):
            state_value = payload.get(mapping.state_key, mapping.default_state)
            state_bool = bool(state_value) if state_value is not None else bool(mapping.default_state)
            if state_bool and mapping.cmd_true:
                return mapping.cmd_true
            if not state_bool and mapping.cmd_false:
                return mapping.cmd_false
        return mapping.cmd

    def _resolve_command_params(self, payload: Dict[str, Any], mapping: SchedulerTaskMapping) -> Dict[str, Any]:
        params = dict(mapping.default_params)
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
        if isinstance(execution.get("params"), dict):
            params.update(execution.get("params") or {})

        duration_sec = self._extract_duration_sec(payload, mapping)
        if duration_sec is not None and "duration_ms" not in params:
            params["duration_ms"] = max(100, int(duration_sec * 1000))

        if mapping.state_key and "state" not in params:
            state_value = payload.get(mapping.state_key, mapping.default_state)
            if state_value is not None:
                params["state"] = bool(state_value)

        return params

    async def _execute_device_task(
        self,
        zone_id: int,
        payload: Dict[str, Any],
        mapping: SchedulerTaskMapping,
        *,
        context: Dict[str, Any],
        decision: DecisionOutcome,
    ) -> Dict[str, Any]:
        if not mapping.node_types:
            return {
                "success": False,
                "task_type": mapping.task_type,
                "error": "mapping_has_no_node_types",
                "error_code": ERR_MAPPING_NOT_FOUND,
            }

        nodes = await self._get_zone_nodes(zone_id, mapping.node_types)
        if not nodes:
            await send_infra_alert(
                code="infra_task_no_online_nodes",
                alert_type="Scheduler Task No Online Nodes",
                message=f"Задача {mapping.task_type} не выполнена: нет online-нод целевых типов",
                severity="warning",
                zone_id=zone_id,
                service="automation-engine",
                component="scheduler_task_executor",
                error_type=ERR_NO_ONLINE_NODES,
                details={
                    "task_type": mapping.task_type,
                    "node_types": list(mapping.node_types),
                },
            )
            return {
                "success": False,
                "task_type": mapping.task_type,
                "error": f"no_online_nodes_for_{mapping.task_type}",
                "error_code": ERR_NO_ONLINE_NODES,
            }

        cmd = self._resolve_command_name(payload, mapping)
        if not cmd:
            return {
                "success": False,
                "task_type": mapping.task_type,
                "error": "command_not_configured",
                "error_code": ERR_MAPPING_NOT_FOUND,
            }
        params = self._resolve_command_params(payload, mapping)

        return await self._publish_batch(
            zone_id=zone_id,
            task_type=mapping.task_type,
            nodes=nodes,
            cmd=cmd,
            params=params,
            context=context,
            decision=decision,
        )

    @staticmethod
    def _extract_execution_config(payload: Dict[str, Any]) -> Dict[str, Any]:
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
        return execution

    @staticmethod
    def _extract_refill_config(payload: Dict[str, Any]) -> Dict[str, Any]:
        execution = SchedulerTaskExecutor._extract_execution_config(payload)
        execution_refill = execution.get("refill") if isinstance(execution.get("refill"), dict) else {}
        payload_refill = payload.get("refill") if isinstance(payload.get("refill"), dict) else {}
        merged = dict(execution_refill)
        merged.update(payload_refill)
        return merged

    @staticmethod
    def _extract_workflow(payload: Dict[str, Any]) -> str:
        execution = SchedulerTaskExecutor._extract_execution_config(payload)
        raw_workflow = (
            payload.get("workflow")
            or payload.get("diagnostics_workflow")
            or execution.get("workflow")
            or "cycle_start"
        )
        return str(raw_workflow or "").strip().lower()

    def _is_cycle_start_workflow(self, payload: Dict[str, Any]) -> bool:
        workflow = self._extract_workflow(payload)
        return workflow in {"cycle_start", "refill_check"}

    @staticmethod
    def _extract_topology(payload: Dict[str, Any]) -> str:
        execution = SchedulerTaskExecutor._extract_execution_config(payload)
        targets = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}
        diagnostics_targets = targets.get("diagnostics") if isinstance(targets.get("diagnostics"), dict) else {}
        diagnostics_execution = (
            diagnostics_targets.get("execution")
            if isinstance(diagnostics_targets.get("execution"), dict)
            else {}
        )
        raw = (
            payload.get("topology")
            or execution.get("topology")
            or diagnostics_execution.get("topology")
            or (
                execution.get("solution_prepare", {}).get("topology")
                if isinstance(execution.get("solution_prepare"), dict)
                else None
            )
            or ""
        )
        return str(raw).strip().lower()

    def _normalize_two_tank_workflow(self, payload: Dict[str, Any]) -> str:
        workflow = self._extract_workflow(payload)
        if workflow == "cycle_start":
            return "startup"
        if workflow == "refill_check":
            return "clean_fill_check"
        return workflow

    def _is_two_tank_startup_workflow(self, payload: Dict[str, Any]) -> bool:
        topology = self._extract_topology(payload)
        workflow = self._normalize_two_tank_workflow(payload)
        if topology != "two_tank_drip_substrate_trays":
            return False
        return workflow in {
            "startup",
            "clean_fill_check",
            "solution_fill_check",
            "prepare_recirculation",
            "prepare_recirculation_check",
            "irrigation_recovery",
            "irrigation_recovery_check",
        }

    def _is_three_tank_startup_workflow(self, payload: Dict[str, Any]) -> bool:
        topology = self._extract_topology(payload)
        if topology not in {
            "three_tank_drip_substrate_trays",
            "three_tank_substrate_trays",
            "three_tank",
        }:
            return False
        workflow = self._extract_workflow(payload)
        return workflow in {"startup", "cycle_start", "refill_check"}

    @staticmethod
    def _to_optional_float(raw: Any) -> Optional[float]:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        return value

    async def _apply_ventilation_climate_guards(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        decision: DecisionOutcome,
    ) -> DecisionOutcome:
        if not decision.action_required:
            return decision

        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
        limits = execution.get("limits") if isinstance(execution.get("limits"), dict) else {}
        external_guard = execution.get("external_guard") if isinstance(execution.get("external_guard"), dict) else {}

        strong_wind_mps = self._to_optional_float(
            execution.get("strong_wind_mps")
            or limits.get("strong_wind_mps")
            or external_guard.get("strong_wind_mps")
            or external_guard.get("wind_max")
        )
        low_outside_temp_c = self._to_optional_float(
            execution.get("low_outside_temp_c")
            or execution.get("low_outside_temperature_c")
            or limits.get("low_outside_temp_c")
            or limits.get("low_outside_temperature_c")
            or external_guard.get("low_outside_temp_c")
            or external_guard.get("temp_min")
        )

        if strong_wind_mps is not None:
            wind = await self._read_latest_metric(zone_id=zone_id, sensor_type="WIND_SPEED")
            wind_value = self._to_optional_float(wind.get("value"))
            if (
                wind.get("has_value")
                and not wind.get("is_stale")
                and wind_value is not None
                and wind_value >= strong_wind_mps
            ):
                return DecisionOutcome(
                    action_required=False,
                    decision="skip",
                    reason_code=REASON_WIND_BLOCKED,
                    reason=(
                        f"Вентиляция заблокирована: скорость ветра {wind_value:.2f} м/с "
                        f"выше порога {strong_wind_mps:.2f} м/с"
                    ),
                )

        if low_outside_temp_c is not None:
            outside = await self._read_latest_metric(zone_id=zone_id, sensor_type="OUTSIDE_TEMP")
            outside_temp = self._to_optional_float(outside.get("value"))
            if (
                outside.get("has_value")
                and not outside.get("is_stale")
                and outside_temp is not None
                and outside_temp <= low_outside_temp_c
            ):
                return DecisionOutcome(
                    action_required=False,
                    decision="skip",
                    reason_code=REASON_OUTSIDE_TEMP_BLOCKED,
                    reason=(
                        f"Вентиляция заблокирована: наружная температура {outside_temp:.2f}°C "
                        f"ниже порога {low_outside_temp_c:.2f}°C"
                    ),
                )

        return decision

    @staticmethod
    def _resolve_int(raw: Any, default: int, minimum: int) -> int:
        try:
            value = int(raw) if raw is not None else default
        except (TypeError, ValueError):
            value = default
        return max(minimum, value)

    @staticmethod
    def _resolve_float(raw: Any, default: float, minimum: float, maximum: float) -> float:
        try:
            value = float(raw) if raw is not None else default
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _normalize_labels(raw: Any, default: Sequence[str]) -> List[str]:
        if isinstance(raw, str):
            labels = [item.strip().lower() for item in raw.split(",") if item.strip()]
            return labels or [str(item).strip().lower() for item in default if str(item).strip()]
        if isinstance(raw, Sequence):
            labels = [str(item).strip().lower() for item in raw if str(item).strip()]
            return labels or [str(item).strip().lower() for item in default if str(item).strip()]
        return [str(item).strip().lower() for item in default if str(item).strip()]

    @staticmethod
    def _merge_dict_recursive(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(base)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = SchedulerTaskExecutor._merge_dict_recursive(
                    merged.get(key) if isinstance(merged.get(key), dict) else {},
                    value,
                )
            else:
                merged[key] = value
        return merged

    def _build_two_tank_runtime_payload(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
        targets = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}
        diagnostics_targets = targets.get("diagnostics") if isinstance(targets.get("diagnostics"), dict) else {}
        diagnostics_execution = (
            diagnostics_targets.get("execution")
            if isinstance(diagnostics_targets.get("execution"), dict)
            else {}
        )
        merged_execution = self._merge_dict_recursive(diagnostics_execution, execution)
        topology = str(merged_execution.get("topology") or "").strip().lower()
        if topology != "two_tank_drip_substrate_trays":
            return None
        runtime_payload = dict(payload)
        runtime_config = dict(config)
        runtime_config["execution"] = merged_execution
        runtime_payload["config"] = runtime_config
        return runtime_payload

    async def _try_start_two_tank_irrigation_recovery_from_irrigation_failure(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if bool(result.get("success")):
            return None
        failure_error_code = str(result.get("error_code") or "").strip().lower()
        if failure_error_code not in {
            ERR_COMMAND_TIMEOUT,
            ERR_COMMAND_ERROR,
            ERR_COMMAND_INVALID,
            ERR_COMMAND_BUSY,
            ERR_COMMAND_NO_EFFECT,
            ERR_COMMAND_EFFECT_NOT_CONFIRMED,
            ERR_COMMAND_TRACKER_UNAVAILABLE,
        }:
            return None

        runtime_payload = self._build_two_tank_runtime_payload(payload)
        if runtime_payload is None:
            return None
        runtime_cfg = self._resolve_two_tank_runtime_config(runtime_payload)

        await self._emit_task_event(
            zone_id=zone_id,
            task_type="irrigation",
            context=context,
            event_type="IRRIGATION_ONLINE_CORRECTION_FAILED",
            payload={
                "reason_code": REASON_ONLINE_CORRECTION_FAILED,
                "error_code": failure_error_code,
                "workflow": "irrigation_recovery",
                "previous_result": result,
            },
        )

        recovery_result = await self._start_two_tank_irrigation_recovery(
            zone_id=zone_id,
            payload={**runtime_payload, "workflow": "irrigation_recovery", "irrigation_recovery_attempt": 1},
            context=context,
            runtime_cfg=runtime_cfg,
            attempt=1,
        )
        recovery_result["task_type"] = "irrigation"
        recovery_result["source_reason_code"] = REASON_ONLINE_CORRECTION_FAILED
        recovery_result["transition_reason_code"] = REASON_TANK_TO_TANK_CORRECTION_STARTED
        recovery_result["online_correction_error_code"] = failure_error_code
        recovery_result["online_correction_result"] = result
        return recovery_result

    def _default_two_tank_command_plan(self, plan_name: str) -> List[Dict[str, Any]]:
        defaults: Dict[str, List[Dict[str, Any]]] = {
            "clean_fill_start": [
                {"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": True}},
            ],
            "clean_fill_stop": [
                {"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": False}},
            ],
            "solution_fill_start": [
                {"channel": "valve_clean_supply", "cmd": "set_relay", "params": {"state": True}},
                {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": True}},
                {"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}},
            ],
            "solution_fill_stop": [
                {"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}},
                {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": False}},
                {"channel": "valve_clean_supply", "cmd": "set_relay", "params": {"state": False}},
            ],
            "prepare_recirculation_start": [
                {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": True}},
                {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": True}},
                {"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}},
            ],
            "prepare_recirculation_stop": [
                {"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}},
                {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": False}},
                {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": False}},
            ],
            "irrigation_recovery_start": [
                {"channel": "valve_irrigation", "cmd": "set_relay", "params": {"state": False}},
                {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": True}},
                {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": True}},
                {"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}},
            ],
            "irrigation_recovery_stop": [
                {"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}},
                {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": False}},
                {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": False}},
            ],
        }
        return [dict(item) for item in defaults.get(plan_name, [])]

    def _normalize_command_plan(
        self,
        raw: Any,
        *,
        default_plan: Sequence[Dict[str, Any]],
        default_node_types: Sequence[str],
    ) -> List[Dict[str, Any]]:
        if not isinstance(raw, Sequence):
            raw = default_plan
        normalized: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            channel = str(item.get("channel") or "").strip().lower()
            if not channel:
                continue
            cmd = str(item.get("cmd") or "set_relay").strip() or "set_relay"
            params = item.get("params") if isinstance(item.get("params"), dict) else {}
            node_types = self._normalize_node_type_list(item.get("node_types"), default_node_types)
            normalized.append(
                {
                    "channel": channel,
                    "cmd": cmd,
                    "params": dict(params),
                    "node_types": node_types,
                }
            )
        return normalized

    def _resolve_two_tank_runtime_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        execution = self._extract_execution_config(payload)
        startup = execution.get("startup") if isinstance(execution.get("startup"), dict) else {}
        required_node_types = self._normalize_node_type_list(
            startup.get("required_node_types"),
            ("irrig",),
        )

        commands_cfg = execution.get("two_tank_commands") if isinstance(execution.get("two_tank_commands"), dict) else {}
        clean_fill_start_default = self._default_two_tank_command_plan("clean_fill_start")
        clean_fill_stop_default = self._default_two_tank_command_plan("clean_fill_stop")
        solution_fill_start_default = self._default_two_tank_command_plan("solution_fill_start")
        solution_fill_stop_default = self._default_two_tank_command_plan("solution_fill_stop")
        prepare_recirculation_start_default = self._default_two_tank_command_plan("prepare_recirculation_start")
        prepare_recirculation_stop_default = self._default_two_tank_command_plan("prepare_recirculation_stop")
        irrigation_recovery_start_default = self._default_two_tank_command_plan("irrigation_recovery_start")
        irrigation_recovery_stop_default = self._default_two_tank_command_plan("irrigation_recovery_stop")

        clean_fill_start = self._normalize_command_plan(
            commands_cfg.get("clean_fill_start"),
            default_plan=clean_fill_start_default,
            default_node_types=required_node_types,
        )
        clean_fill_stop = self._normalize_command_plan(
            commands_cfg.get("clean_fill_stop"),
            default_plan=clean_fill_stop_default,
            default_node_types=required_node_types,
        )
        solution_fill_start = self._normalize_command_plan(
            commands_cfg.get("solution_fill_start"),
            default_plan=solution_fill_start_default,
            default_node_types=required_node_types,
        )
        solution_fill_stop = self._normalize_command_plan(
            commands_cfg.get("solution_fill_stop"),
            default_plan=solution_fill_stop_default,
            default_node_types=required_node_types,
        )
        prepare_recirculation_start = self._normalize_command_plan(
            commands_cfg.get("prepare_recirculation_start"),
            default_plan=prepare_recirculation_start_default,
            default_node_types=required_node_types,
        )
        prepare_recirculation_stop = self._normalize_command_plan(
            commands_cfg.get("prepare_recirculation_stop"),
            default_plan=prepare_recirculation_stop_default,
            default_node_types=required_node_types,
        )
        irrigation_recovery_start = self._normalize_command_plan(
            commands_cfg.get("irrigation_recovery_start"),
            default_plan=irrigation_recovery_start_default,
            default_node_types=required_node_types,
        )
        irrigation_recovery_stop = self._normalize_command_plan(
            commands_cfg.get("irrigation_recovery_stop"),
            default_plan=irrigation_recovery_stop_default,
            default_node_types=required_node_types,
        )

        recovery_cfg = execution.get("irrigation_recovery") if isinstance(execution.get("irrigation_recovery"), dict) else {}
        degraded_cfg = recovery_cfg.get("degraded_tolerance") if isinstance(recovery_cfg.get("degraded_tolerance"), dict) else {}
        prepare_tolerance_cfg = execution.get("prepare_tolerance") if isinstance(execution.get("prepare_tolerance"), dict) else {}
        recovery_tolerance_cfg = recovery_cfg.get("target_tolerance") if isinstance(recovery_cfg.get("target_tolerance"), dict) else {}
        fallback_prepare_tolerance_cfg = execution.get("prepare_target_tolerance") if isinstance(execution.get("prepare_target_tolerance"), dict) else {}

        targets_payload = payload.get("targets") if isinstance(payload.get("targets"), dict) else {}
        ph_payload = targets_payload.get("ph") if isinstance(targets_payload.get("ph"), dict) else {}
        ec_payload = targets_payload.get("ec") if isinstance(targets_payload.get("ec"), dict) else {}
        nutrition_payload = (
            targets_payload.get("nutrition")
            if isinstance(targets_payload.get("nutrition"), dict)
            else {}
        )
        nutrition_components = (
            nutrition_payload.get("components")
            if isinstance(nutrition_payload.get("components"), dict)
            else {}
        )
        nutrition_npk = (
            nutrition_components.get("npk")
            if isinstance(nutrition_components.get("npk"), dict)
            else {}
        )
        target_ph_raw = execution.get("target_ph")
        if target_ph_raw is None:
            target_ph_raw = ph_payload.get("target")
        target_ec_raw = execution.get("target_ec")
        if target_ec_raw is None:
            target_ec_raw = ec_payload.get("target")
        target_ph = self._resolve_float(target_ph_raw, 5.8, 0.1, 14.0)
        target_ec = self._resolve_float(target_ec_raw, 1.6, 0.0, 20.0)
        npk_ratio_raw = execution.get("nutrient_npk_ratio_pct")
        if npk_ratio_raw is None:
            npk_ratio_raw = execution.get("npk_ratio_pct")
        if npk_ratio_raw is None:
            npk_ratio_raw = startup.get("nutrient_npk_ratio_pct")
        if npk_ratio_raw is None:
            npk_ratio_raw = nutrition_npk.get("ratio_pct")
        nutrient_npk_ratio_pct = self._resolve_float(npk_ratio_raw, 100.0, 0.0, 100.0)
        target_ec_prepare_raw = execution.get("target_ec_prepare_npk")
        if target_ec_prepare_raw is None:
            target_ec_prepare_raw = startup.get("target_ec_prepare_npk")
        if target_ec_prepare_raw is None:
            target_ec_prepare_raw = target_ec * (nutrient_npk_ratio_pct / 100.0)
        target_ec_prepare = self._resolve_float(target_ec_prepare_raw, target_ec, 0.0, 20.0)

        return {
            "required_node_types": required_node_types,
            "clean_fill_timeout_sec": self._resolve_int(
                startup.get("clean_fill_timeout_sec"),
                1200,
                30,
            ),
            "solution_fill_timeout_sec": self._resolve_int(
                startup.get("solution_fill_timeout_sec"),
                1800,
                30,
            ),
            "poll_interval_sec": self._resolve_int(
                startup.get("level_poll_interval_sec"),
                REFILL_CHECK_DELAY_SEC,
                10,
            ),
            "clean_fill_retry_cycles": self._resolve_int(
                startup.get("clean_fill_retry_cycles"),
                1,
                0,
            ),
            "prepare_recirculation_timeout_sec": self._resolve_int(
                startup.get("prepare_recirculation_timeout_sec"),
                1200,
                30,
            ),
            "irrigation_recovery_timeout_sec": self._resolve_int(
                recovery_cfg.get("timeout_sec"),
                600,
                30,
            ),
            "irrigation_recovery_max_attempts": self._resolve_int(
                recovery_cfg.get("max_continue_attempts"),
                5,
                1,
            ),
            "level_switch_on_threshold": self._resolve_float(
                startup.get("level_switch_on_threshold"),
                0.5,
                0.0,
                1.0,
            ),
            "clean_max_labels": self._normalize_labels(
                startup.get("clean_max_sensor_labels"),
                ("level_clean_max", "clean_max"),
            ),
            "solution_max_labels": self._normalize_labels(
                startup.get("solution_max_sensor_labels"),
                ("level_solution_max", "solution_max"),
            ),
            "target_ph": target_ph,
            "target_ec": target_ec,
            "target_ec_prepare": target_ec_prepare,
            "nutrient_npk_ratio_pct": nutrient_npk_ratio_pct,
            "prepare_tolerance": {
                "ec_pct": self._resolve_float(
                    prepare_tolerance_cfg.get("ec_pct", fallback_prepare_tolerance_cfg.get("ec_pct")),
                    25.0,
                    0.1,
                    100.0,
                ),
                "ph_pct": self._resolve_float(
                    prepare_tolerance_cfg.get("ph_pct", fallback_prepare_tolerance_cfg.get("ph_pct")),
                    15.0,
                    0.1,
                    100.0,
                ),
            },
            "recovery_tolerance": {
                "ec_pct": self._resolve_float(
                    recovery_tolerance_cfg.get("ec_pct"),
                    10.0,
                    0.1,
                    100.0,
                ),
                "ph_pct": self._resolve_float(
                    recovery_tolerance_cfg.get("ph_pct"),
                    5.0,
                    0.1,
                    100.0,
                ),
            },
            "degraded_tolerance": {
                "ec_pct": self._resolve_float(
                    degraded_cfg.get("ec_pct"),
                    20.0,
                    0.1,
                    100.0,
                ),
                "ph_pct": self._resolve_float(
                    degraded_cfg.get("ph_pct"),
                    10.0,
                    0.1,
                    100.0,
                ),
            },
            "commands": {
                "clean_fill_start": clean_fill_start,
                "clean_fill_stop": clean_fill_stop,
                "solution_fill_start": solution_fill_start,
                "solution_fill_stop": solution_fill_stop,
                "prepare_recirculation_start": prepare_recirculation_start,
                "prepare_recirculation_stop": prepare_recirculation_stop,
                "irrigation_recovery_start": irrigation_recovery_start,
                "irrigation_recovery_stop": irrigation_recovery_stop,
            },
        }

    async def _read_level_switch(
        self,
        *,
        zone_id: int,
        sensor_labels: Sequence[str],
        threshold: float,
    ) -> Dict[str, Any]:
        labels = [str(item).strip().lower() for item in sensor_labels if str(item).strip()]
        if not labels:
            return {
                "sensor_id": None,
                "sensor_label": None,
                "level": None,
                "sample_ts": None,
                "sample_age_sec": None,
                "is_stale": False,
                "has_level": False,
                "is_triggered": False,
            }

        rows = await fetch(
            """
            SELECT
                s.id AS sensor_id,
                s.label AS sensor_label,
                tl.last_value AS level,
                COALESCE(tl.last_ts, tl.updated_at) AS sample_ts
            FROM sensors s
            LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
            WHERE s.zone_id = $1
              AND s.type = 'WATER_LEVEL'
              AND s.is_active = TRUE
              AND LOWER(TRIM(COALESCE(s.label, ''))) = ANY($2::text[])
            ORDER BY
                COALESCE(tl.last_ts, tl.updated_at) DESC NULLS LAST,
                s.id DESC
            LIMIT 1
            """,
            zone_id,
            labels,
        )

        if not rows:
            return {
                "sensor_id": None,
                "sensor_label": None,
                "level": None,
                "sample_ts": None,
                "sample_age_sec": None,
                "is_stale": False,
                "has_level": False,
                "is_triggered": False,
            }

        row = rows[0]
        raw_level = row.get("level")
        try:
            level = float(raw_level) if raw_level is not None else None
        except (TypeError, ValueError):
            level = None

        sample_ts_raw = row.get("sample_ts")
        if isinstance(sample_ts_raw, datetime):
            sample_dt = sample_ts_raw
        elif isinstance(sample_ts_raw, str):
            sample_dt = parse_iso_datetime(sample_ts_raw)
        else:
            sample_dt = None

        if isinstance(sample_dt, datetime) and sample_dt.tzinfo is not None:
            sample_dt = sample_dt.astimezone(timezone.utc).replace(tzinfo=None)

        sample_ts = sample_dt.isoformat() if isinstance(sample_dt, datetime) else None
        sample_age_sec = max(0.0, (datetime.utcnow() - sample_dt).total_seconds()) if sample_dt else None
        has_level = level is not None
        is_stale = bool(has_level and (sample_dt is None or (sample_age_sec or 0.0) > TELEMETRY_FRESHNESS_MAX_AGE_SEC))
        return {
            "sensor_id": row.get("sensor_id"),
            "sensor_label": row.get("sensor_label"),
            "level": level,
            "sample_ts": sample_ts,
            "sample_age_sec": sample_age_sec,
            "is_stale": is_stale,
            "has_level": has_level,
            "is_triggered": bool(has_level and level >= threshold),
        }

    async def _read_latest_metric(self, *, zone_id: int, sensor_type: str) -> Dict[str, Any]:
        rows = await fetch(
            """
            SELECT
                s.id AS sensor_id,
                s.label AS sensor_label,
                tl.last_value AS value,
                COALESCE(tl.last_ts, tl.updated_at) AS sample_ts
            FROM sensors s
            LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
            WHERE s.zone_id = $1
              AND s.type = $2
              AND s.is_active = TRUE
            ORDER BY
                COALESCE(tl.last_ts, tl.updated_at) DESC NULLS LAST,
                s.id DESC
            LIMIT 1
            """,
            zone_id,
            sensor_type,
        )
        if not rows:
            return {
                "sensor_id": None,
                "sensor_label": None,
                "value": None,
                "sample_ts": None,
                "sample_age_sec": None,
                "is_stale": False,
                "has_value": False,
            }

        row = rows[0]
        raw_value = row.get("value")
        try:
            value = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            value = None

        sample_ts_raw = row.get("sample_ts")
        if isinstance(sample_ts_raw, datetime):
            sample_dt = sample_ts_raw
        elif isinstance(sample_ts_raw, str):
            sample_dt = parse_iso_datetime(sample_ts_raw)
        else:
            sample_dt = None
        if isinstance(sample_dt, datetime) and sample_dt.tzinfo is not None:
            sample_dt = sample_dt.astimezone(timezone.utc).replace(tzinfo=None)

        sample_ts = sample_dt.isoformat() if isinstance(sample_dt, datetime) else None
        sample_age_sec = max(0.0, (datetime.utcnow() - sample_dt).total_seconds()) if sample_dt else None
        has_value = value is not None
        is_stale = bool(has_value and (sample_dt is None or (sample_age_sec or 0.0) > TELEMETRY_FRESHNESS_MAX_AGE_SEC))
        return {
            "sensor_id": row.get("sensor_id"),
            "sensor_label": row.get("sensor_label"),
            "value": value,
            "sample_ts": sample_ts,
            "sample_age_sec": sample_age_sec,
            "is_stale": is_stale,
            "has_value": has_value,
        }

    def _is_value_within_pct(self, *, value: float, target: float, tolerance_pct: float) -> bool:
        if target <= 0:
            return abs(value - target) <= max(0.1, tolerance_pct / 100.0)
        tolerance_abs = abs(target) * (tolerance_pct / 100.0)
        return abs(value - target) <= tolerance_abs

    async def _evaluate_ph_ec_targets(
        self,
        *,
        zone_id: int,
        target_ph: float,
        target_ec: float,
        tolerance: Dict[str, float],
    ) -> Dict[str, Any]:
        ph_sample = await self._read_latest_metric(zone_id=zone_id, sensor_type="PH")
        ec_sample = await self._read_latest_metric(zone_id=zone_id, sensor_type="EC")

        if not ph_sample["has_value"] or not ec_sample["has_value"]:
            return {
                "has_data": False,
                "is_stale": bool(ph_sample["is_stale"] or ec_sample["is_stale"]),
                "targets_reached": False,
                "ph": ph_sample,
                "ec": ec_sample,
            }
        if TELEMETRY_FRESHNESS_ENFORCE and (ph_sample["is_stale"] or ec_sample["is_stale"]):
            return {
                "has_data": True,
                "is_stale": True,
                "targets_reached": False,
                "ph": ph_sample,
                "ec": ec_sample,
            }

        ph_ok = self._is_value_within_pct(
            value=float(ph_sample["value"]),
            target=target_ph,
            tolerance_pct=float(tolerance.get("ph_pct", 5.0)),
        )
        ec_ok = self._is_value_within_pct(
            value=float(ec_sample["value"]),
            target=target_ec,
            tolerance_pct=float(tolerance.get("ec_pct", 10.0)),
        )
        return {
            "has_data": True,
            "is_stale": False,
            "targets_reached": bool(ph_ok and ec_ok),
            "ph_ok": ph_ok,
            "ec_ok": ec_ok,
            "ph": ph_sample,
            "ec": ec_sample,
            "target_ph": target_ph,
            "target_ec": target_ec,
            "tolerance": tolerance,
        }

    async def _find_zone_event_since(
        self,
        *,
        zone_id: int,
        event_types: Sequence[str],
        since: Optional[datetime],
    ) -> Optional[Dict[str, Any]]:
        normalized_types = [str(item).strip().upper() for item in event_types if str(item).strip()]
        if not normalized_types or since is None:
            return None

        rows = await fetch(
            """
            SELECT id, type, created_at, details
            FROM zone_events
            WHERE zone_id = $1
              AND type = ANY($2::text[])
              AND created_at >= $3
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            zone_id,
            normalized_types,
            since,
        )
        if not rows:
            return None
        return dict(rows[0])

    async def _resolve_online_node_for_channel(
        self,
        *,
        zone_id: int,
        channel: str,
        node_types: Sequence[str],
    ) -> Optional[Dict[str, Any]]:
        normalized_channel = str(channel or "").strip().lower()
        if not normalized_channel:
            return None
        normalized_node_types = [str(item).strip().lower() for item in node_types if str(item).strip()]
        if not normalized_node_types:
            return None
        rows = await fetch(
            """
            SELECT
                n.uid AS node_uid,
                LOWER(COALESCE(n.type, '')) AS node_type,
                LOWER(COALESCE(nc.channel, 'default')) AS channel
            FROM nodes n
            JOIN node_channels nc ON nc.node_id = n.id
            WHERE n.zone_id = $1
              AND LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
              AND LOWER(COALESCE(nc.channel, 'default')) = $2
              AND LOWER(COALESCE(n.type, '')) = ANY($3::text[])
            ORDER BY n.id ASC, nc.id ASC
            LIMIT 1
            """,
            zone_id,
            normalized_channel,
            normalized_node_types,
        )
        if not rows:
            return None
        row = rows[0]
        node_uid = str(row.get("node_uid") or "").strip()
        if not node_uid:
            return None
        return {
            "node_uid": node_uid,
            "type": str(row.get("node_type") or "").strip().lower(),
            "channel": str(row.get("channel") or normalized_channel).strip().lower() or normalized_channel,
        }

    async def _dispatch_two_tank_command_plan(
        self,
        *,
        zone_id: int,
        command_plan: Sequence[Dict[str, Any]],
        context: Dict[str, Any],
        decision: DecisionOutcome,
    ) -> Dict[str, Any]:
        if not command_plan:
            return {
                "success": True,
                "commands_total": 0,
                "commands_failed": 0,
                "commands_submitted": 0,
                "commands_effect_confirmed": 0,
                "command_statuses": [],
            }

        combined_statuses: List[Dict[str, Any]] = []
        commands_total = 0
        commands_failed = 0
        commands_submitted = 0
        commands_effect_confirmed = 0
        first_error_code: Optional[str] = None
        first_error: Optional[str] = None

        for entry in command_plan:
            channel = str(entry.get("channel") or "").strip().lower()
            cmd = str(entry.get("cmd") or "set_relay").strip() or "set_relay"
            params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
            node_types = entry.get("node_types") if isinstance(entry.get("node_types"), Sequence) else ()
            node = await self._resolve_online_node_for_channel(
                zone_id=zone_id,
                channel=channel,
                node_types=[str(item) for item in node_types],
            )
            if not node:
                commands_total += 1
                commands_failed += 1
                if first_error_code is None:
                    first_error_code = ERR_TWO_TANK_CHANNEL_NOT_FOUND
                    first_error = f"channel_not_found:{channel}"
                combined_statuses.append(
                    {
                        "node_uid": None,
                        "channel": channel,
                        "cmd": cmd,
                        "command_submitted": False,
                        "command_effect_confirmed": False,
                        "terminal_status": "CHANNEL_NOT_FOUND",
                        "error_code": ERR_TWO_TANK_CHANNEL_NOT_FOUND,
                    }
                )
                continue

            step_result = await self._publish_batch(
                zone_id=zone_id,
                task_type="diagnostics",
                nodes=[node],
                cmd=cmd,
                params=params,
                context=context,
                decision=decision,
            )
            commands_total += int(step_result.get("commands_total") or 0)
            commands_failed += int(step_result.get("commands_failed") or 0)
            commands_submitted += int(step_result.get("commands_submitted") or 0)
            commands_effect_confirmed += int(step_result.get("commands_effect_confirmed") or 0)
            combined_statuses.extend(step_result.get("command_statuses") or [])
            if not step_result.get("success") and first_error_code is None:
                first_error_code = str(step_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED)
                first_error = str(step_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED)

        result = {
            "success": commands_total > 0 and commands_failed == 0 and commands_effect_confirmed == commands_total,
            "commands_total": commands_total,
            "commands_failed": commands_failed,
            "commands_submitted": commands_submitted,
            "commands_effect_confirmed": commands_effect_confirmed,
            "command_statuses": combined_statuses,
        }
        if not result["success"]:
            result["error_code"] = first_error_code or ERR_TWO_TANK_COMMAND_FAILED
            result["error"] = first_error or ERR_TWO_TANK_COMMAND_FAILED
        return result

    @staticmethod
    def _normalize_text_list(raw: Any, default: Sequence[str]) -> List[str]:
        if isinstance(raw, str):
            values = [item.strip().lower() for item in raw.split(",") if item.strip()]
            return values or [str(item).strip().lower() for item in default if str(item).strip()]
        if isinstance(raw, Sequence):
            values = [str(item).strip().lower() for item in raw if str(item).strip()]
            return values or [str(item).strip().lower() for item in default if str(item).strip()]
        return [str(item).strip().lower() for item in default if str(item).strip()]

    @staticmethod
    def _normalize_node_type_list(raw: Any, default: Sequence[str]) -> List[str]:
        raw_values = SchedulerTaskExecutor._normalize_text_list(raw, default)
        canonical: List[str] = []
        for value in raw_values:
            normalized = normalize_node_type(value)
            if normalized == "unknown":
                continue
            if normalized not in canonical:
                canonical.append(normalized)

        if canonical:
            return canonical

        fallback: List[str] = []
        for value in default:
            normalized = normalize_node_type(str(value))
            if normalized == "unknown":
                continue
            if normalized not in fallback:
                fallback.append(normalized)
        return fallback

    def _resolve_required_node_types(self, payload: Dict[str, Any]) -> List[str]:
        execution = self._extract_execution_config(payload)
        override = execution.get("required_node_types")
        return self._normalize_node_type_list(override, CYCLE_START_REQUIRED_NODE_TYPES)

    def _resolve_clean_tank_threshold(self, payload: Dict[str, Any]) -> float:
        execution = self._extract_execution_config(payload)
        refill_cfg = self._extract_refill_config(payload)
        threshold_raw = (
            refill_cfg.get("clean_tank_full_threshold")
            if isinstance(refill_cfg, dict)
            else None
        )
        if threshold_raw is None:
            threshold_raw = execution.get("clean_tank_full_threshold")
        try:
            threshold = float(threshold_raw) if threshold_raw is not None else CLEAN_TANK_FULL_THRESHOLD
        except (TypeError, ValueError):
            threshold = CLEAN_TANK_FULL_THRESHOLD
        return max(0.0, min(1.0, threshold))

    def _resolve_refill_duration_ms(self, payload: Dict[str, Any]) -> int:
        execution = self._extract_execution_config(payload)
        refill_cfg = self._extract_refill_config(payload)
        duration_raw = refill_cfg.get("duration_sec")
        if duration_raw is None:
            duration_raw = execution.get("refill_duration_sec")
        try:
            duration_sec = float(duration_raw) if duration_raw is not None else float(REFILL_COMMAND_DURATION_SEC)
        except (TypeError, ValueError):
            duration_sec = float(REFILL_COMMAND_DURATION_SEC)
        duration_sec = max(0.1, duration_sec)
        return max(100, int(duration_sec * 1000))

    def _resolve_refill_attempt(self, payload: Dict[str, Any]) -> int:
        raw_attempt = payload.get("refill_attempt")
        try:
            attempt = int(raw_attempt) if raw_attempt is not None else 0
        except (TypeError, ValueError):
            attempt = 0
        return max(0, attempt)

    def _resolve_refill_started_at(self, payload: Dict[str, Any], now: datetime) -> datetime:
        raw_started_at = payload.get("refill_started_at")
        parsed = parse_iso_datetime(str(raw_started_at)) if raw_started_at else None
        return parsed or now

    def _resolve_refill_timeout_at(self, payload: Dict[str, Any], started_at: datetime) -> datetime:
        execution = self._extract_execution_config(payload)
        refill_cfg = self._extract_refill_config(payload)

        raw_timeout = payload.get("refill_timeout_at")
        if raw_timeout is None:
            raw_timeout = refill_cfg.get("timeout_at")
        if raw_timeout is None:
            raw_timeout = execution.get("refill_timeout_at")

        parsed_timeout = parse_iso_datetime(str(raw_timeout)) if raw_timeout else None
        if parsed_timeout is not None:
            return parsed_timeout

        timeout_sec_raw = refill_cfg.get("timeout_sec")
        if timeout_sec_raw is None:
            timeout_sec_raw = execution.get("refill_timeout_sec")
        try:
            timeout_sec = int(timeout_sec_raw) if timeout_sec_raw is not None else REFILL_TIMEOUT_SEC
        except (TypeError, ValueError):
            timeout_sec = REFILL_TIMEOUT_SEC
        timeout_sec = max(30, timeout_sec)
        return started_at + timedelta(seconds=timeout_sec)

    def _build_refill_check_payload(
        self,
        *,
        payload: Dict[str, Any],
        refill_started_at: datetime,
        refill_timeout_at: datetime,
        next_attempt: int,
    ) -> Dict[str, Any]:
        next_payload = dict(payload)
        next_payload["workflow"] = "refill_check"
        next_payload["refill_started_at"] = refill_started_at.isoformat()
        next_payload["refill_timeout_at"] = refill_timeout_at.isoformat()
        next_payload["refill_attempt"] = next_attempt
        return next_payload

    async def _check_required_nodes_online(self, zone_id: int, required_types: Sequence[str]) -> Dict[str, Any]:
        normalized_types = [str(item).strip().lower() for item in required_types if str(item).strip()]
        if not normalized_types:
            return {"required_types": [], "online_counts": {}, "missing_types": []}

        rows = await fetch(
            """
            SELECT
                LOWER(COALESCE(n.type, '')) AS node_type,
                COUNT(*)::int AS online_count
            FROM nodes n
            WHERE n.zone_id = $1
              AND LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
              AND LOWER(COALESCE(n.type, '')) = ANY($2::text[])
            GROUP BY LOWER(COALESCE(n.type, ''))
            """,
            zone_id,
            normalized_types,
        )
        online_counts: Dict[str, int] = {}
        for row in rows:
            node_type = str(row.get("node_type") or "").strip().lower()
            if not node_type:
                continue
            try:
                online_counts[node_type] = int(row.get("online_count") or 0)
            except (TypeError, ValueError):
                online_counts[node_type] = 0

        missing = [node_type for node_type in normalized_types if online_counts.get(node_type, 0) <= 0]
        return {
            "required_types": normalized_types,
            "online_counts": online_counts,
            "missing_types": missing,
        }

    async def _read_clean_tank_level(self, zone_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        threshold = self._resolve_clean_tank_threshold(payload)
        rows = await fetch(
            """
            SELECT
                s.id AS sensor_id,
                s.label AS sensor_label,
                tl.last_value AS level,
                COALESCE(tl.last_ts, tl.updated_at) AS sample_ts
            FROM sensors s
            LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
            WHERE s.zone_id = $1
              AND s.type = 'WATER_LEVEL'
              AND s.is_active = TRUE
            ORDER BY
                CASE
                    WHEN LOWER(COALESCE(s.label, '')) LIKE '%clean%' THEN 0
                    WHEN LOWER(COALESCE(s.label, '')) LIKE '%fresh%' THEN 0
                    WHEN LOWER(COALESCE(s.label, '')) LIKE '%чист%' THEN 0
                    WHEN LOWER(COALESCE(s.label, '')) LIKE '%drain%' THEN 2
                    WHEN LOWER(COALESCE(s.label, '')) LIKE '%waste%' THEN 2
                    WHEN LOWER(COALESCE(s.label, '')) LIKE '%слив%' THEN 2
                    ELSE 1
                END ASC,
                COALESCE(tl.last_ts, tl.updated_at) DESC NULLS LAST,
                s.id DESC
            LIMIT 1
            """,
            zone_id,
        )
        if not rows:
            return {
                "sensor_id": None,
                "sensor_label": None,
                "level": None,
                "sample_ts": None,
                "sample_age_sec": None,
                "is_stale": False,
                "threshold": threshold,
                "has_level": False,
                "is_full": False,
            }

        row = rows[0]
        level_value = row.get("level")
        try:
            level = float(level_value) if level_value is not None else None
        except (TypeError, ValueError):
            level = None

        has_level = level is not None
        is_full = bool(has_level and level >= threshold)
        sample_ts_raw = row.get("sample_ts")
        if isinstance(sample_ts_raw, datetime):
            sample_dt = sample_ts_raw
        elif isinstance(sample_ts_raw, str):
            sample_dt = parse_iso_datetime(sample_ts_raw)
        else:
            sample_dt = None

        if isinstance(sample_dt, datetime) and sample_dt.tzinfo is not None:
            sample_dt = sample_dt.astimezone(timezone.utc).replace(tzinfo=None)

        sample_ts = sample_dt.isoformat() if isinstance(sample_dt, datetime) else None
        sample_age_sec = max(0.0, (datetime.utcnow() - sample_dt).total_seconds()) if sample_dt else None
        is_stale = bool(has_level and (sample_dt is None or (sample_age_sec or 0.0) > TELEMETRY_FRESHNESS_MAX_AGE_SEC))
        return {
            "sensor_id": row.get("sensor_id"),
            "sensor_label": row.get("sensor_label"),
            "level": level,
            "sample_ts": sample_ts,
            "sample_age_sec": sample_age_sec,
            "is_stale": is_stale,
            "threshold": threshold,
            "has_level": has_level,
            "is_full": is_full,
        }

    async def _resolve_refill_command(self, zone_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        refill_cfg = self._extract_refill_config(payload)
        requested_channel = str(refill_cfg.get("channel") or "").strip().lower()
        node_types = self._normalize_node_type_list(refill_cfg.get("node_types"), ("irrig",))
        preferred_channels = self._normalize_text_list(
            refill_cfg.get("preferred_channels"),
            ("fill_valve", "water_control", "main_pump", "default"),
        )

        rows = await fetch(
            """
            SELECT
                n.uid AS node_uid,
                LOWER(COALESCE(n.type, '')) AS node_type,
                LOWER(COALESCE(nc.channel, 'default')) AS channel
            FROM nodes n
            LEFT JOIN node_channels nc ON nc.node_id = n.id
            WHERE n.zone_id = $1
              AND LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
              AND (
                  LOWER(COALESCE(n.type, '')) = ANY($2::text[])
                  OR LOWER(COALESCE(nc.channel, '')) = ANY($3::text[])
              )
            ORDER BY n.id ASC, nc.id ASC
            """,
            zone_id,
            node_types,
            preferred_channels,
        )
        if not rows:
            return None

        candidates: List[Dict[str, Any]] = []
        for row in rows:
            node_uid = str(row.get("node_uid") or "").strip()
            if not node_uid:
                continue
            candidates.append(
                {
                    "node_uid": node_uid,
                    "type": str(row.get("node_type") or "").strip().lower(),
                    "channel": str(row.get("channel") or "default").strip().lower() or "default",
                }
            )
        if not candidates:
            return None

        selected: Optional[Dict[str, Any]] = None
        if requested_channel:
            selected = next((item for item in candidates if item["channel"] == requested_channel), None)
        if selected is None:
            channel_rank = {channel: idx for idx, channel in enumerate(preferred_channels)}
            selected = sorted(
                candidates,
                key=lambda item: (
                    channel_rank.get(item["channel"], len(channel_rank) + 10),
                    item["type"] not in set(node_types),
                    item["node_uid"],
                ),
            )[0]

        cmd = str(refill_cfg.get("cmd") or "run_pump").strip() or "run_pump"
        params = dict(refill_cfg.get("params") if isinstance(refill_cfg.get("params"), dict) else {})
        if cmd == "run_pump" and "duration_ms" not in params:
            params["duration_ms"] = self._resolve_refill_duration_ms(payload)
        if cmd == "set_relay" and "state" not in params:
            params["state"] = True

        return {"node": selected, "cmd": cmd, "params": params}

    async def _emit_cycle_alert(
        self,
        *,
        zone_id: int,
        code: str,
        message: str,
        severity: str,
        details: Dict[str, Any],
    ) -> None:
        await send_infra_alert(
            code=code,
            alert_type="Automation Cycle Start",
            message=message,
            severity=severity,
            zone_id=zone_id,
            service="automation-engine",
            component="scheduler_task_executor",
            error_type=code,
            details=details,
        )

    def _build_two_tank_check_payload(
        self,
        *,
        payload: Dict[str, Any],
        workflow: str,
        phase_started_at: datetime,
        phase_timeout_at: datetime,
        phase_cycle: Optional[int] = None,
    ) -> Dict[str, Any]:
        next_payload = dict(payload)
        next_payload["workflow"] = workflow
        if workflow == "clean_fill_check":
            next_payload["clean_fill_started_at"] = phase_started_at.isoformat()
            next_payload["clean_fill_timeout_at"] = phase_timeout_at.isoformat()
            if phase_cycle is not None:
                next_payload["clean_fill_cycle"] = max(1, int(phase_cycle))
        elif workflow == "solution_fill_check":
            next_payload["solution_fill_started_at"] = phase_started_at.isoformat()
            next_payload["solution_fill_timeout_at"] = phase_timeout_at.isoformat()
        elif workflow == "prepare_recirculation_check":
            next_payload["prepare_recirculation_started_at"] = phase_started_at.isoformat()
            next_payload["prepare_recirculation_timeout_at"] = phase_timeout_at.isoformat()
        elif workflow == "irrigation_recovery_check":
            next_payload["irrigation_recovery_started_at"] = phase_started_at.isoformat()
            next_payload["irrigation_recovery_timeout_at"] = phase_timeout_at.isoformat()
            if phase_cycle is not None:
                next_payload["irrigation_recovery_attempt"] = max(1, int(phase_cycle))
        return next_payload

    async def _enqueue_two_tank_check(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        workflow: str,
        phase_started_at: datetime,
        phase_timeout_at: datetime,
        poll_interval_sec: int,
        phase_cycle: Optional[int] = None,
    ) -> Dict[str, Any]:
        next_payload = self._build_two_tank_check_payload(
            payload=payload,
            workflow=workflow,
            phase_started_at=phase_started_at,
            phase_timeout_at=phase_timeout_at,
            phase_cycle=phase_cycle,
        )
        next_check_at = datetime.utcnow() + timedelta(seconds=poll_interval_sec)
        if next_check_at > phase_timeout_at:
            next_check_at = phase_timeout_at
        return await enqueue_internal_scheduler_task(
            zone_id=zone_id,
            task_type="diagnostics",
            payload=next_payload,
            scheduled_for=next_check_at.isoformat(),
            expires_at=phase_timeout_at.isoformat(),
            source="automation-engine:two-tank-startup",
        )

    async def _start_two_tank_clean_fill(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        runtime_cfg: Dict[str, Any],
        cycle: int,
    ) -> Dict[str, Any]:
        plan_result = await self._dispatch_two_tank_command_plan(
            zone_id=zone_id,
            command_plan=runtime_cfg["commands"]["clean_fill_start"],
            context=context,
            decision=DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code=REASON_CLEAN_FILL_STARTED,
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
                "reason_code": REASON_CYCLE_REFILL_COMMAND_FAILED,
                "reason": "Не удалось отправить команду наполнения бака чистой воды",
                "error": str(plan_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED),
                "error_code": str(plan_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED),
            }

        phase_started_at = datetime.utcnow()
        phase_timeout_at = phase_started_at + timedelta(seconds=runtime_cfg["clean_fill_timeout_sec"])
        try:
            enqueue_result = await self._enqueue_two_tank_check(
                zone_id=zone_id,
                payload=payload,
                workflow="clean_fill_check",
                phase_started_at=phase_started_at,
                phase_timeout_at=phase_timeout_at,
                poll_interval_sec=runtime_cfg["poll_interval_sec"],
                phase_cycle=cycle,
            )
        except ValueError as exc:
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
                "reason_code": REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
                "reason": "Команда наполнения отправлена, но self-task не поставлен",
                "error": str(exc),
                "error_code": ERR_TWO_TANK_ENQUEUE_FAILED,
            }

        await self._emit_task_event(
            zone_id=zone_id,
            task_type="diagnostics",
            context=context,
            event_type="CLEAN_FILL_STARTED",
            payload={
                "clean_fill_cycle": cycle,
                "clean_fill_started_at": phase_started_at.isoformat(),
                "clean_fill_timeout_at": phase_timeout_at.isoformat(),
                "next_check": enqueue_result,
                "reason_code": REASON_CLEAN_FILL_STARTED,
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
            "reason_code": REASON_CLEAN_FILL_STARTED,
            "reason": "Запущено наполнение бака чистой воды",
            "clean_fill_cycle": cycle,
            "clean_fill_started_at": phase_started_at.isoformat(),
            "clean_fill_timeout_at": phase_timeout_at.isoformat(),
            "next_check": enqueue_result,
        }

    async def _start_two_tank_solution_fill(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        runtime_cfg: Dict[str, Any],
    ) -> Dict[str, Any]:
        plan_result = await self._dispatch_two_tank_command_plan(
            zone_id=zone_id,
            command_plan=runtime_cfg["commands"]["solution_fill_start"],
            context=context,
            decision=DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code=REASON_SOLUTION_FILL_STARTED,
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
                "reason_code": REASON_CYCLE_REFILL_COMMAND_FAILED,
                "reason": "Не удалось отправить команды наполнения бака раствора",
                "error": str(plan_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED),
                "error_code": str(plan_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED),
            }

        phase_started_at = datetime.utcnow()
        phase_timeout_at = phase_started_at + timedelta(seconds=runtime_cfg["solution_fill_timeout_sec"])
        try:
            enqueue_result = await self._enqueue_two_tank_check(
                zone_id=zone_id,
                payload=payload,
                workflow="solution_fill_check",
                phase_started_at=phase_started_at,
                phase_timeout_at=phase_timeout_at,
                poll_interval_sec=runtime_cfg["poll_interval_sec"],
            )
        except ValueError as exc:
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_solution_fill_enqueue_failed",
                "workflow": "startup",
                "commands_total": plan_result.get("commands_total", 0),
                "commands_failed": plan_result.get("commands_failed", 0),
                "command_statuses": plan_result.get("command_statuses", []),
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
                "reason": "Команды наполнения раствора отправлены, но self-task не поставлен",
                "error": str(exc),
                "error_code": ERR_TWO_TANK_ENQUEUE_FAILED,
            }

        await self._emit_task_event(
            zone_id=zone_id,
            task_type="diagnostics",
            context=context,
            event_type="SOLUTION_FILL_STARTED",
            payload={
                "solution_fill_started_at": phase_started_at.isoformat(),
                "solution_fill_timeout_at": phase_timeout_at.isoformat(),
                "next_check": enqueue_result,
                "reason_code": REASON_SOLUTION_FILL_STARTED,
            },
        )

        return {
            "success": True,
            "task_type": "diagnostics",
            "mode": "two_tank_solution_fill_in_progress",
            "workflow": "startup",
            "commands_total": plan_result.get("commands_total", 0),
            "commands_failed": plan_result.get("commands_failed", 0),
            "command_statuses": plan_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_SOLUTION_FILL_STARTED,
            "reason": "Запущено наполнение бака рабочего раствора",
            "solution_fill_started_at": phase_started_at.isoformat(),
            "solution_fill_timeout_at": phase_timeout_at.isoformat(),
            "next_check": enqueue_result,
        }

    async def _start_two_tank_prepare_recirculation(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        runtime_cfg: Dict[str, Any],
    ) -> Dict[str, Any]:
        plan_result = await self._dispatch_two_tank_command_plan(
            zone_id=zone_id,
            command_plan=runtime_cfg["commands"]["prepare_recirculation_start"],
            context=context,
            decision=DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code=REASON_PREPARE_RECIRCULATION_STARTED,
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
                "reason_code": REASON_CYCLE_REFILL_COMMAND_FAILED,
                "reason": "Не удалось отправить команды prepare recirculation",
                "error": str(plan_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED),
                "error_code": str(plan_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED),
            }

        phase_started_at = datetime.utcnow()
        phase_timeout_at = phase_started_at + timedelta(seconds=runtime_cfg["prepare_recirculation_timeout_sec"])
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
                "workflow": "prepare_recirculation",
                "commands_total": plan_result.get("commands_total", 0),
                "commands_failed": plan_result.get("commands_failed", 0),
                "command_statuses": plan_result.get("command_statuses", []),
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
                "reason": "Команды prepare recirculation отправлены, но self-task не поставлен",
                "error": str(exc),
                "error_code": ERR_TWO_TANK_ENQUEUE_FAILED,
            }

        return {
            "success": True,
            "task_type": "diagnostics",
            "mode": "two_tank_prepare_recirculation_in_progress",
            "workflow": "prepare_recirculation",
            "commands_total": plan_result.get("commands_total", 0),
            "commands_failed": plan_result.get("commands_failed", 0),
            "command_statuses": plan_result.get("command_statuses", []),
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_PREPARE_RECIRCULATION_STARTED,
            "reason": "Запущена рециркуляция подготовки раствора",
            "prepare_recirculation_started_at": phase_started_at.isoformat(),
            "prepare_recirculation_timeout_at": phase_timeout_at.isoformat(),
            "next_check": enqueue_result,
        }

    async def _start_two_tank_irrigation_recovery(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        runtime_cfg: Dict[str, Any],
        attempt: int,
    ) -> Dict[str, Any]:
        plan_result = await self._dispatch_two_tank_command_plan(
            zone_id=zone_id,
            command_plan=runtime_cfg["commands"]["irrigation_recovery_start"],
            context=context,
            decision=DecisionOutcome(
                action_required=True,
                decision="run",
                reason_code=REASON_IRRIGATION_RECOVERY_STARTED,
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
                "reason_code": REASON_IRRIGATION_RECOVERY_FAILED,
                "reason": "Не удалось отправить команды irrigation recovery",
                "error": str(plan_result.get("error") or ERR_TWO_TANK_COMMAND_FAILED),
                "error_code": str(plan_result.get("error_code") or ERR_TWO_TANK_COMMAND_FAILED),
            }

        phase_started_at = datetime.utcnow()
        phase_timeout_at = phase_started_at + timedelta(seconds=runtime_cfg["irrigation_recovery_timeout_sec"])
        try:
            enqueue_result = await self._enqueue_two_tank_check(
                zone_id=zone_id,
                payload={**payload, "irrigation_recovery_attempt": attempt},
                workflow="irrigation_recovery_check",
                phase_started_at=phase_started_at,
                phase_timeout_at=phase_timeout_at,
                poll_interval_sec=runtime_cfg["poll_interval_sec"],
            )
        except ValueError as exc:
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
                "reason_code": REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED,
                "reason": "Команды irrigation recovery отправлены, но self-task не поставлен",
                "error": str(exc),
                "error_code": ERR_TWO_TANK_ENQUEUE_FAILED,
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
            "reason_code": REASON_IRRIGATION_RECOVERY_STARTED,
            "reason": "Запущен recovery-контур полива",
            "irrigation_recovery_attempt": attempt,
            "irrigation_recovery_started_at": phase_started_at.isoformat(),
            "irrigation_recovery_timeout_at": phase_timeout_at.isoformat(),
            "next_check": enqueue_result,
        }

    async def _execute_two_tank_startup_workflow(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        decision: DecisionOutcome,
    ) -> Dict[str, Any]:
        runtime_cfg = self._resolve_two_tank_runtime_config(payload)
        workflow = self._normalize_two_tank_workflow(payload)

        await self._emit_task_event(
            zone_id=zone_id,
            task_type="diagnostics",
            context=context,
            event_type="TWO_TANK_STARTUP_INITIATED",
            payload={
                "workflow": workflow,
                "topology": self._extract_topology(payload),
                "action_required": decision.action_required,
                "decision": decision.decision,
                "reason_code": decision.reason_code,
            },
        )

        nodes_state = await self._check_required_nodes_online(zone_id, runtime_cfg["required_node_types"])
        if nodes_state["missing_types"]:
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_required_nodes_missing",
                "workflow": workflow,
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_CYCLE_BLOCKED_NODES_UNAVAILABLE,
                "reason": "Нет online-нод, необходимых для startup 2-бакового контура",
                "error": ERR_CYCLE_REQUIRED_NODES_UNAVAILABLE,
                "error_code": ERR_CYCLE_REQUIRED_NODES_UNAVAILABLE,
                "missing_node_types": nodes_state["missing_types"],
            }

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
                }
            if TELEMETRY_FRESHNESS_ENFORCE and clean_level["is_stale"]:
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
            now = datetime.utcnow()
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
                    }
                if TELEMETRY_FRESHNESS_ENFORCE and clean_level["is_stale"]:
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
            now = datetime.utcnow()
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
                    }
                if TELEMETRY_FRESHNESS_ENFORCE and solution_level["is_stale"]:
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
            now = datetime.utcnow()
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
            now = datetime.utcnow()
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
                degraded_state = await self._evaluate_ph_ec_targets(
                    zone_id=zone_id,
                    target_ph=float(runtime_cfg["target_ph"]),
                    target_ec=float(runtime_cfg["target_ec"]),
                    tolerance=runtime_cfg["degraded_tolerance"],
                )
                if degraded_state["targets_reached"]:
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
                    "reason_code": REASON_IRRIGATION_RECOVERY_FAILED,
                    "reason": "Превышено число попыток irrigation recovery",
                    "error": ERR_IRRIGATION_RECOVERY_ATTEMPTS_EXCEEDED,
                    "error_code": ERR_IRRIGATION_RECOVERY_ATTEMPTS_EXCEEDED,
                    "irrigation_recovery_attempt": attempt,
                    "targets_state": recovery_state,
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

    async def _execute_three_tank_startup_workflow(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        decision: DecisionOutcome,
    ) -> Dict[str, Any]:
        workflow = self._extract_workflow(payload)
        fallback_workflow = "refill_check" if workflow == "refill_check" else "cycle_start"
        payload_for_cycle_start = dict(payload)
        payload_for_cycle_start["workflow"] = fallback_workflow

        result = await self._execute_cycle_start_workflow(
            zone_id=zone_id,
            payload=payload_for_cycle_start,
            context=context,
            decision=decision,
        )
        mode_map = {
            "cycle_start": "three_tank_startup",
            "cycle_start_ready": "three_tank_startup_ready",
            "cycle_start_refill_timeout": "three_tank_startup_refill_timeout",
            "cycle_start_refill_started_without_check": "three_tank_startup_refill_started_without_check",
            "cycle_start_refill_in_progress": "three_tank_startup_refill_in_progress",
        }
        raw_mode = str(result.get("mode") or "")
        if raw_mode in mode_map:
            result["mode"] = mode_map[raw_mode]
        result["topology"] = self._extract_topology(payload) or "three_tank_drip_substrate_trays"
        result["workflow"] = workflow
        return result

    async def _execute_cycle_start_workflow(
        self,
        *,
        zone_id: int,
        payload: Dict[str, Any],
        context: Dict[str, Any],
        decision: DecisionOutcome,
    ) -> Dict[str, Any]:
        workflow = self._extract_workflow(payload)
        now = datetime.utcnow()
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
                code="infra_cycle_start_nodes_unavailable",
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
                code="infra_cycle_start_tank_level_unavailable",
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

        if TELEMETRY_FRESHNESS_ENFORCE and tank_level["is_stale"]:
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
                    "max_age_sec": TELEMETRY_FRESHNESS_MAX_AGE_SEC,
                    "action_required": True,
                    "decision": "run",
                    "reason_code": REASON_CYCLE_TANK_LEVEL_STALE,
                    "error_code": error,
                },
            )
            await self._emit_cycle_alert(
                zone_id=zone_id,
                code="infra_cycle_start_tank_level_stale",
                message="Старт цикла заблокирован: телеметрия уровня бака устарела",
                severity="error",
                details={
                    "workflow": workflow,
                    "sensor_id": tank_level["sensor_id"],
                    "sensor_label": tank_level["sensor_label"],
                    "sample_ts": tank_level["sample_ts"],
                    "sample_age_sec": tank_level["sample_age_sec"],
                    "max_age_sec": TELEMETRY_FRESHNESS_MAX_AGE_SEC,
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
                "max_age_sec": TELEMETRY_FRESHNESS_MAX_AGE_SEC,
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
                code="infra_tank_refill_timeout",
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
                code="infra_cycle_start_refill_command_failed",
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
                code="infra_cycle_start_refill_command_failed",
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
            enqueue_result = await enqueue_internal_scheduler_task(
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
                code="infra_cycle_start_enqueue_failed",
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

    async def _execute_diagnostics(
        self,
        zone_id: int,
        payload: Dict[str, Any],
        *,
        context: Dict[str, Any],
        decision: DecisionOutcome,
    ) -> Dict[str, Any]:
        if self.zone_service is None:
            await self._emit_task_event(
                zone_id=zone_id,
                task_type="diagnostics",
                context=context,
                event_type="DIAGNOSTICS_SERVICE_UNAVAILABLE",
                payload={
                    "action_required": decision.action_required,
                    "decision": decision.decision,
                    "reason_code": REASON_DIAGNOSTICS_SERVICE_UNAVAILABLE,
                    "error_code": ERR_DIAGNOSTICS_SERVICE_UNAVAILABLE,
                },
            )
            await send_infra_alert(
                code="infra_diagnostics_service_unavailable",
                alert_type="Diagnostics Service Unavailable",
                message="Diagnostics задача не выполнена: ZoneAutomationService недоступен",
                severity="error",
                zone_id=zone_id,
                service="automation-engine",
                component="scheduler_task_executor",
                error_type=ERR_DIAGNOSTICS_SERVICE_UNAVAILABLE,
                details={"payload": payload},
            )
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "diagnostics_unavailable",
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": decision.action_required,
                "decision": decision.decision,
                "reason_code": REASON_DIAGNOSTICS_SERVICE_UNAVAILABLE,
                "reason": "Diagnostics задача не может быть исполнена без ZoneAutomationService",
                "error": ERR_DIAGNOSTICS_SERVICE_UNAVAILABLE,
                "error_code": ERR_DIAGNOSTICS_SERVICE_UNAVAILABLE,
            }

        try:
            await self.zone_service.process_zone(zone_id)
            return {
                "success": True,
                "task_type": "diagnostics",
                "mode": "zone_service",
                "commands_total": 0,
                "commands_failed": 0,
            }
        except Exception as exc:
            logger.warning(
                "Zone %s: diagnostics via zone_service failed: %s",
                zone_id,
                exc,
                exc_info=True,
            )
            await self._emit_task_event(
                zone_id=zone_id,
                task_type="diagnostics",
                context=context,
                event_type="DIAGNOSTICS_SERVICE_UNAVAILABLE",
                payload={
                    "action_required": decision.action_required,
                    "decision": decision.decision,
                    "reason_code": REASON_DIAGNOSTICS_SERVICE_UNAVAILABLE,
                    "error_code": ERR_DIAGNOSTICS_SERVICE_UNAVAILABLE,
                },
            )
            await send_infra_alert(
                code="infra_diagnostics_service_unavailable",
                alert_type="Diagnostics Service Unavailable",
                message=f"Diagnostics задача завершилась ошибкой zone_service: {exc}",
                severity="error",
                zone_id=zone_id,
                service="automation-engine",
                component="scheduler_task_executor",
                error_type=type(exc).__name__,
                details={"payload": payload, "error": str(exc)},
            )
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "diagnostics_failed",
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": decision.action_required,
                "decision": decision.decision,
                "reason_code": REASON_DIAGNOSTICS_SERVICE_UNAVAILABLE,
                "reason": "Diagnostics задача завершилась ошибкой ZoneAutomationService",
                "error": ERR_DIAGNOSTICS_SERVICE_UNAVAILABLE,
                "error_code": ERR_DIAGNOSTICS_SERVICE_UNAVAILABLE,
            }
