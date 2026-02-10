"""Исполнение абстрактных задач расписания внутри automation-engine."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from common.db import create_zone_event, fetch
from common.infra_alerts import send_infra_alert
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


CYCLE_START_REQUIRED_NODE_TYPES = tuple(
    item.strip()
    for item in os.getenv("AE_CYCLE_START_REQUIRED_NODE_TYPES", "irrig,irrigation,climate,light,lighting").split(",")
    if item.strip()
)
CLEAN_TANK_FULL_THRESHOLD = max(0.0, min(1.0, _env_float("AE_CLEAN_TANK_FULL_THRESHOLD", 0.95)))
REFILL_CHECK_DELAY_SEC = max(10, _env_int("AE_REFILL_CHECK_DELAY_SEC", 60))
REFILL_TIMEOUT_SEC = max(30, _env_int("AE_REFILL_TIMEOUT_SEC", 600))
REFILL_COMMAND_DURATION_SEC = max(1, _env_int("AE_REFILL_COMMAND_DURATION_SEC", 30))


ERR_COMMAND_PUBLISH_FAILED = "command_publish_failed"
ERR_MAPPING_NOT_FOUND = "mapping_not_found"
ERR_NO_ONLINE_NODES = "no_online_nodes"
ERR_CYCLE_REQUIRED_NODES_UNAVAILABLE = "cycle_start_required_nodes_unavailable"
ERR_CYCLE_TANK_LEVEL_UNAVAILABLE = "cycle_start_tank_level_unavailable"
ERR_CYCLE_REFILL_TIMEOUT = "cycle_start_refill_timeout"
ERR_CYCLE_REFILL_NODE_NOT_FOUND = "cycle_start_refill_node_not_found"
ERR_CYCLE_REFILL_COMMAND_FAILED = "cycle_start_refill_command_failed"
ERR_CYCLE_SELF_TASK_ENQUEUE_FAILED = "cycle_start_self_task_enqueue_failed"

REASON_REQUIRED_NODES_CHECKED = "required_nodes_checked"
REASON_TANK_LEVEL_CHECKED = "tank_level_checked"
REASON_TANK_REFILL_REQUIRED = "tank_refill_required"
REASON_TANK_REFILL_STARTED = "tank_refill_started"
REASON_TANK_REFILL_IN_PROGRESS = "tank_refill_in_progress"
REASON_TANK_REFILL_COMPLETED = "tank_refill_completed"
REASON_TANK_REFILL_NOT_REQUIRED = "tank_refill_not_required"
REASON_CYCLE_BLOCKED_NODES_UNAVAILABLE = "cycle_start_blocked_nodes_unavailable"
REASON_CYCLE_TANK_LEVEL_UNAVAILABLE = "cycle_start_tank_level_unavailable"
REASON_CYCLE_REFILL_TIMEOUT = "cycle_start_refill_timeout"
REASON_CYCLE_REFILL_COMMAND_FAILED = "cycle_start_refill_command_failed"
REASON_CYCLE_SELF_TASK_ENQUEUE_FAILED = "cycle_start_self_task_enqueue_failed"


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
        elif task_type == "diagnostics" and self._is_cycle_start_workflow(payload):
            result = await self._execute_cycle_start_workflow(
                zone_id=zone_id,
                payload=payload,
                context=context,
                decision=decision,
            )
        elif task_type == "diagnostics":
            result = await self._execute_diagnostics(zone_id, payload)
        else:
            result = await self._execute_device_task(
                zone_id,
                payload,
                mapping,
                context=context,
                decision=decision,
            )

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
                decision="execute",
                reason_code=f"{task_type}_required",
                reason="Принудительное выполнение по force_execute",
            )

        explicit_action_required = payload.get("action_required")
        if isinstance(explicit_action_required, bool):
            if explicit_action_required:
                return DecisionOutcome(
                    action_required=True,
                    decision="execute",
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
            decision="execute",
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
        rows = await fetch(
            """
            SELECT n.uid, n.type, COALESCE(nc.channel, 'default') AS channel
            FROM nodes n
            LEFT JOIN node_channels nc ON nc.node_id = n.id
            WHERE n.zone_id = $1
              AND n.status = 'online'
              AND n.type = ANY($2::text[])
            """,
            zone_id,
            list(node_types),
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
        commands_failed = 0

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
            ok = await self.command_bus.publish_command(
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                params=params or {},
            )
            if not ok:
                commands_failed += 1
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
                        "error_code": ERR_COMMAND_PUBLISH_FAILED,
                        "action_required": decision.action_required,
                        "decision": decision.decision,
                        "reason_code": decision.reason_code,
                    },
                )

        success = commands_total > 0 and commands_failed == 0
        result = {
            "success": success,
            "task_type": task_type,
            "commands_total": commands_total,
            "commands_failed": commands_failed,
            "cmd": cmd,
            "params": params or {},
        }
        if not success:
            result["error"] = ERR_COMMAND_PUBLISH_FAILED
            result["error_code"] = ERR_COMMAND_PUBLISH_FAILED
        return result

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
            if mapping.fallback_mode == "zone_service" and self.zone_service is not None:
                await self.zone_service.process_zone(zone_id)
                return {
                    "success": True,
                    "task_type": mapping.task_type,
                    "mode": "zone_service_fallback",
                    "commands_total": 0,
                    "commands_failed": 0,
                }
            if mapping.fallback_mode == "event_only":
                await create_zone_event(
                    zone_id,
                    "SCHEDULE_TASK_FALLBACK_EVENT_ONLY",
                    {"task_type": mapping.task_type, "payload": payload},
                )
                return {
                    "success": True,
                    "task_type": mapping.task_type,
                    "mode": "event_only_fallback",
                    "commands_total": 0,
                    "commands_failed": 0,
                }
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
    def _normalize_text_list(raw: Any, default: Sequence[str]) -> List[str]:
        if isinstance(raw, str):
            values = [item.strip().lower() for item in raw.split(",") if item.strip()]
            return values or [str(item).strip().lower() for item in default if str(item).strip()]
        if isinstance(raw, Sequence):
            values = [str(item).strip().lower() for item in raw if str(item).strip()]
            return values or [str(item).strip().lower() for item in default if str(item).strip()]
        return [str(item).strip().lower() for item in default if str(item).strip()]

    def _resolve_required_node_types(self, payload: Dict[str, Any]) -> List[str]:
        execution = self._extract_execution_config(payload)
        override = execution.get("required_node_types")
        return self._normalize_text_list(override, CYCLE_START_REQUIRED_NODE_TYPES)

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
              AND n.status = 'online'
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
        sample_ts = sample_ts_raw.isoformat() if hasattr(sample_ts_raw, "isoformat") else sample_ts_raw
        return {
            "sensor_id": row.get("sensor_id"),
            "sensor_label": row.get("sensor_label"),
            "level": level,
            "sample_ts": sample_ts,
            "threshold": threshold,
            "has_level": has_level,
            "is_full": is_full,
        }

    async def _resolve_refill_command(self, zone_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        refill_cfg = self._extract_refill_config(payload)
        requested_channel = str(refill_cfg.get("channel") or "").strip().lower()
        node_types = self._normalize_text_list(refill_cfg.get("node_types"), ("irrig", "irrigation"))
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
              AND n.status = 'online'
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
                "decision": "execute",
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
                "decision": "execute",
                "reason_code": REASON_CYCLE_TANK_LEVEL_UNAVAILABLE,
                "reason": "Нет данных уровня бака чистой воды",
                "error": error,
                "error_code": error,
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
                    "decision": "execute",
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
                "decision": "execute",
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
                "decision": "execute",
                "reason_code": REASON_CYCLE_REFILL_COMMAND_FAILED,
                "reason": "Не найден online-узел для команды наполнения бака",
                "error": error,
                "error_code": error,
            }

        refill_decision = DecisionOutcome(
            action_required=True,
            decision="execute",
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
                "decision": "execute",
                "reason_code": REASON_CYCLE_REFILL_COMMAND_FAILED,
                "reason": "Команда наполнения бака не была отправлена",
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
                "decision": "execute",
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
                "decision": "execute",
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
                "decision": "execute",
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
            "decision": "execute",
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

    async def _execute_diagnostics(self, zone_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.zone_service is not None:
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

        await create_zone_event(
            zone_id,
            "SCHEDULE_DIAGNOSTICS_REQUESTED",
            {"payload": payload},
        )
        return {
            "success": True,
            "task_type": "diagnostics",
            "mode": "event_only",
            "commands_total": 0,
            "commands_failed": 0,
        }
