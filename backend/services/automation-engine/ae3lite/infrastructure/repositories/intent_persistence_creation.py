"""PgZoneIntentRepository creation: explicit collaborators and invocation context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


@dataclass(frozen=True)
class IntentPersistenceCreationPorts:
    global_fetch: Callable[..., Any]


class IntentPersistenceCreation:
    def __init__(self, ports: IntentPersistenceCreationPorts) -> None:
        self._ports = ports

    async def upsert_irrigation_replay_intent(
        self,
        *,
        zone_id: int,
        idempotency_key: str,
        topology: str,
        now: datetime,
        mode: str = "normal",
        requested_duration_sec: int | None = None,
        source: str = "ae3_startup_recovery",
        failed_task_id: int | None = None,
    ) -> int | None:
        """Создаёт pending irrigation intent для продолжения после recovery."""
        normalized_mode = "force" if str(mode).strip().lower() == "force" else "normal"
        normalized_topology = str(topology or "").strip().lower() or "two_tank_drip_substrate_trays"
        intent_source = str(source or "").strip() or "ae3_startup_recovery"
        duration = int(requested_duration_sec) if requested_duration_sec not in (None, "") else None
        if duration is not None and duration <= 0:
            duration = None
        payload = {
            "mode": normalized_mode,
            "task_type": "irrigation_start",
            "workflow": "irrigation_start",
            "topology": normalized_topology,
            "trigger": "startup_recovery_replay",
            "failed_task_id": failed_task_id,
            "requested_duration_sec": duration,
        }
        rows = await self._ports.global_fetch(
            """
            INSERT INTO zone_automation_intents (
                zone_id,
                intent_type,
                task_type,
                topology,
                irrigation_mode,
                irrigation_requested_duration_sec,
                intent_source,
                idempotency_key,
                payload,
                status,
                not_before,
                retry_count,
                max_retries,
                created_at,
                updated_at
            )
            VALUES (
                $1, 'IRRIGATE_ONCE', 'irrigation_start', $2,
                $3, $4, $5, $6, $7::jsonb,
                'pending', NULL, 0, 3, $8, $8
            )
            ON CONFLICT (zone_id, idempotency_key)
            DO UPDATE SET
                task_type = EXCLUDED.task_type,
                topology = EXCLUDED.topology,
                irrigation_mode = EXCLUDED.irrigation_mode,
                irrigation_requested_duration_sec = EXCLUDED.irrigation_requested_duration_sec,
                intent_source = EXCLUDED.intent_source,
                payload = EXCLUDED.payload,
                not_before = NULL,
                updated_at = EXCLUDED.updated_at
            WHERE zone_automation_intents.status NOT IN ('completed', 'failed', 'cancelled', 'claimed', 'running')
            RETURNING id
            """,
            zone_id,
            normalized_topology,
            normalized_mode,
            duration,
            intent_source,
            idempotency_key,
            json.dumps(payload),
            now,
        )
        if not rows:
            return None
        intent_id = rows[0].get("id")
        return int(intent_id) if intent_id is not None else None

    async def upsert_solution_topup_intent(
        self,
        *,
        zone_id: int,
        idempotency_key: str,
        source: str,
        trigger: str,
        topology: str,
        now: datetime,
        mode: str = "normal",
    ) -> int | None:
        normalized_mode = "force" if str(mode).strip().lower() == "force" else "normal"
        normalized_topology = str(topology or "").strip().lower() or "two_tank_drip_substrate_trays"
        intent_source = str(source or "").strip() or "level_event"
        payload = {
            "mode": normalized_mode,
            "task_type": "solution_topup",
            "workflow": "solution_topup",
            "topology": normalized_topology,
            "trigger": str(trigger or "").strip() or "level_switch",
        }
        rows = await self._ports.global_fetch(
            """
            INSERT INTO zone_automation_intents (
                zone_id,
                intent_type,
                task_type,
                topology,
                irrigation_mode,
                irrigation_requested_duration_sec,
                intent_source,
                idempotency_key,
                payload,
                status,
                not_before,
                retry_count,
                max_retries,
                created_at,
                updated_at
            )
            VALUES (
                $1, 'SOLUTION_TOPUP', 'solution_topup', $2,
                NULL, NULL, $3, $4, $5::jsonb,
                'pending', NULL, 0, 3, $6, $6
            )
            ON CONFLICT (zone_id, idempotency_key)
            DO UPDATE SET
                task_type = EXCLUDED.task_type,
                topology = EXCLUDED.topology,
                intent_source = EXCLUDED.intent_source,
                payload = EXCLUDED.payload,
                not_before = NULL,
                updated_at = EXCLUDED.updated_at
            WHERE zone_automation_intents.status NOT IN ('completed', 'failed', 'cancelled')
            RETURNING id
            """,
            zone_id,
            normalized_topology,
            intent_source,
            idempotency_key,
            json.dumps(payload),
            now,
        )
        if not rows:
            return None
        intent_id = rows[0].get("id")
        return int(intent_id) if intent_id is not None else None
