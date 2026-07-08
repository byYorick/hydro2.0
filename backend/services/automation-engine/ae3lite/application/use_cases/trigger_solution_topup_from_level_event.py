"""Реактивный запуск solution_topup по событию level_switch_changed (этап B+)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from ae3lite.api.contracts import StartSolutionTopupRequest
from ae3lite.application.level_monitor import (
    DEFAULT_SOLUTION_MAX_LABELS,
    level_snapshot_aliases,
    load_zone_level_monitor_config,
    solution_topup_need_active,
)
from ae3lite.domain.errors import TaskCreateError
from ae3lite.infrastructure.read_models.zone_runtime_monitor import PgZoneRuntimeMonitor

_logger = logging.getLogger(__name__)

_SOLUTION_MAX_CHANNELS = frozenset(
    alias
    for label in DEFAULT_SOLUTION_MAX_LABELS
    for alias in level_snapshot_aliases(label)
)


def _normalize_channel(value: object) -> str:
    return str(value or "").strip().lower()


def _is_solution_max_channel(channel: object) -> bool:
    normalized = _normalize_channel(channel)
    return normalized in _SOLUTION_MAX_CHANNELS


def _coerce_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return None


class TriggerSolutionTopupFromLevelEventUseCase:
    """Создаёт intent+task solution_topup после level_switch на solution_max (DB-first)."""

    def __init__(
        self,
        *,
        zone_intent_repository: Any,
        create_task_from_intent_use_case: Any,
        runtime_monitor: Any | None = None,
        fetch_fn: Any,
    ) -> None:
        self._zone_intent_repository = zone_intent_repository
        self._create_task_from_intent_use_case = create_task_from_intent_use_case
        self._runtime_monitor = runtime_monitor or PgZoneRuntimeMonitor()
        self._fetch_fn = fetch_fn

    async def run(self, *, zone_id: int, event_data: Mapping[str, Any], now: datetime) -> dict[str, Any]:
        event_type = str(event_data.get("event_type") or "").strip().upper()
        if event_type != "LEVEL_SWITCH_CHANGED":
            return {"triggered": False, "reason": "event_type_not_relevant"}

        channel = _normalize_channel(event_data.get("channel"))
        if not _is_solution_max_channel(channel):
            return {"triggered": False, "reason": "channel_not_solution_max", "channel": channel or None}

        if _coerce_bool(event_data.get("initial")) is True:
            return {"triggered": False, "reason": "initial_event_skipped"}

        state = _coerce_bool(event_data.get("state"))
        if state is not False:
            return {"triggered": False, "reason": "not_topup_start_edge", "state": state}

        runtime_rows = await self._fetch_fn(
            """
            SELECT z.automation_runtime, w.workflow_phase
            FROM zones z
            LEFT JOIN zone_workflow_state w ON w.zone_id = z.id
            WHERE z.id = $1
            LIMIT 1
            """,
            zone_id,
        )
        if not runtime_rows:
            return {"triggered": False, "reason": "zone_missing"}
        zone_row = dict(runtime_rows[0])
        if str(zone_row.get("automation_runtime") or "").strip().lower() != "ae3":
            return {"triggered": False, "reason": "automation_runtime_not_ae3"}
        workflow_phase = str(zone_row.get("workflow_phase") or "").strip().lower()
        if workflow_phase != "ready":
            return {"triggered": False, "reason": "workflow_not_ready", "workflow_phase": workflow_phase or None}

        active_task_rows = await self._fetch_fn(
            """
            SELECT id, task_type, status, current_stage
            FROM ae_tasks
            WHERE zone_id = $1
              AND status IN ('pending', 'claimed', 'running', 'waiting_command')
            ORDER BY id DESC
            LIMIT 1
            """,
            zone_id,
        )
        if active_task_rows:
            active = dict(active_task_rows[0])
            if str(active.get("task_type") or "").strip().lower() == "solution_topup":
                return {
                    "triggered": False,
                    "reason": "active_solution_topup_task",
                    "task_id": active.get("id"),
                }
            return {
                "triggered": False,
                "reason": "zone_busy",
                "task_id": active.get("id"),
                "task_type": active.get("task_type"),
            }

        level_cfg = await load_zone_level_monitor_config(zone_id=zone_id, fetch_fn=self._fetch_fn)
        solution_min = await self._runtime_monitor.read_level_switch(
            zone_id=zone_id,
            sensor_labels=level_cfg["solution_min_sensor_labels"],
            threshold=level_cfg["level_switch_on_threshold"],
            telemetry_max_age_sec=int(level_cfg["telemetry_max_age_sec"]),
        )
        solution_max = await self._runtime_monitor.read_level_switch(
            zone_id=zone_id,
            sensor_labels=level_cfg["solution_max_sensor_labels"],
            threshold=level_cfg["level_switch_on_threshold"],
            telemetry_max_age_sec=int(level_cfg["telemetry_max_age_sec"]),
        )
        if not solution_topup_need_active(
            solution_min_triggered=bool(solution_min.get("is_triggered")),
            solution_max_triggered=bool(solution_max.get("is_triggered")),
        ):
            return {
                "triggered": False,
                "reason": "level_not_need_topup",
                "solution_min_triggered": solution_min.get("is_triggered"),
                "solution_max_triggered": solution_max.get("is_triggered"),
            }

        topology = await self._resolve_topology(zone_id=zone_id)
        now_utc = now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now
        idempotency_key = (
            f"level_event:z{zone_id}:solution_topup:"
            f"{now_utc.strftime('%Y%m%d%H%M')}"
        )
        intent_id = await self._zone_intent_repository.upsert_solution_topup_intent(
            zone_id=zone_id,
            idempotency_key=idempotency_key,
            source="level_event",
            trigger="level_switch",
            topology=topology,
            now=now_utc,
        )
        if intent_id is None:
            return {"triggered": False, "reason": "intent_upsert_failed"}

        req = StartSolutionTopupRequest(
            source="level_event",
            idempotency_key=idempotency_key,
            mode="normal",
            trigger="level_switch",
        )
        claim = await self._zone_intent_repository.claim_start_solution_topup(
            zone_id=zone_id,
            req=req,
            now=now_utc,
        )
        decision = str(claim.get("decision") or "").strip().lower()
        intent_row = dict(claim.get("intent") or {})
        if decision == "zone_busy":
            return {"triggered": False, "reason": "intent_claim_zone_busy", "intent_id": intent_id}
        if decision == "missing":
            return {"triggered": False, "reason": "intent_claim_missing", "intent_id": intent_id}
        if decision == "deduplicated":
            return {"triggered": False, "reason": "intent_deduplicated", "intent_id": intent_id}
        if decision == "terminal":
            return {"triggered": False, "reason": "intent_terminal", "intent_id": intent_id}
        if decision != "claimed":
            return {"triggered": False, "reason": "intent_claim_unavailable", "intent_id": intent_id}

        try:
            creation = await self._create_task_from_intent_use_case.run(
                zone_id=zone_id,
                source="level_event",
                idempotency_key=idempotency_key,
                intent_row=intent_row,
                now=now_utc,
                allow_create=True,
                solution_topup_mode="normal",
                solution_topup_trigger="level_switch",
            )
        except TaskCreateError as exc:
            _logger.info(
                "Level-event solution_topup preconditions failed zone_id=%s code=%s",
                zone_id,
                exc.code,
            )
            return {
                "triggered": False,
                "reason": str(exc.code or "task_create_failed"),
                "intent_id": intent_id,
            }
        except Exception as exc:
            _logger.warning(
                "Level-event solution_topup task create failed zone_id=%s error=%s",
                zone_id,
                exc,
                exc_info=True,
            )
            return {"triggered": False, "reason": "task_create_exception", "intent_id": intent_id}

        task = creation.task
        return {
            "triggered": True,
            "intent_id": intent_id,
            "task_id": int(task.id),
            "idempotency_key": idempotency_key,
        }

    async def _resolve_topology(self, *, zone_id: int) -> str:
        rows = await self._fetch_fn(
            """
            SELECT aeb.config
            FROM grow_cycles gc
            JOIN automation_effective_bundles aeb
              ON aeb.scope_type = 'grow_cycle'
             AND aeb.scope_id = gc.id
            WHERE gc.zone_id = $1
              AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
            ORDER BY
                CASE gc.status
                    WHEN 'RUNNING' THEN 0
                    WHEN 'PAUSED' THEN 1
                    ELSE 2
                END,
                gc.id DESC
            LIMIT 1
            """,
            zone_id,
        )
        if rows:
            config = dict(rows[0]).get("config")
            if isinstance(config, Mapping):
                zone_bundle = config.get("zone")
                if isinstance(zone_bundle, Mapping):
                    logic_profile = zone_bundle.get("logic_profile")
                    if isinstance(logic_profile, Mapping):
                        active_profile = logic_profile.get("active_profile")
                        if isinstance(active_profile, Mapping):
                            subsystems = active_profile.get("subsystems")
                            if isinstance(subsystems, Mapping):
                                diagnostics = subsystems.get("diagnostics")
                                if isinstance(diagnostics, Mapping):
                                    execution = diagnostics.get("execution")
                                    if isinstance(execution, Mapping):
                                        topology = str(execution.get("topology") or "").strip().lower()
                                        if topology:
                                            return topology

        fallback_rows = await self._fetch_fn(
            """
            SELECT topology
            FROM zone_automation_intents
            WHERE zone_id = $1
              AND topology IS NOT NULL
              AND topology <> ''
            ORDER BY id DESC
            LIMIT 1
            """,
            zone_id,
        )
        if fallback_rows:
            topology = str(dict(fallback_rows[0]).get("topology") or "").strip().lower()
            if topology:
                return topology

        return "two_tank_drip_substrate_trays"


__all__ = ["TriggerSolutionTopupFromLevelEventUseCase"]
