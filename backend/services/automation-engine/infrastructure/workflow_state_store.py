"""Persistence store for per-zone workflow state."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from common.db import execute, fetch
from common.utils.time import utcnow


WORKFLOW_PHASE_VALUES = {"idle", "tank_filling", "tank_recirc", "ready", "irrigating", "irrig_recirc"}
logger = logging.getLogger(__name__)


def _normalize_phase(raw_phase: Any) -> str:
    value = str(raw_phase or "").strip().lower()
    return value if value in WORKFLOW_PHASE_VALUES else "idle"


def _normalize_payload(raw_payload: Any) -> Dict[str, Any]:
    if isinstance(raw_payload, dict):
        return dict(raw_payload)

    if isinstance(raw_payload, (bytes, bytearray)):
        try:
            raw_payload = raw_payload.decode("utf-8")
        except Exception:
            return {}

    if isinstance(raw_payload, str):
        source = raw_payload.strip()
        if source == "":
            return {}
        try:
            decoded = json.loads(source)
        except Exception:
            return {}
        if isinstance(decoded, dict):
            return decoded

    return {}


class WorkflowStateStore:
    """DB-backed storage for workflow phase recovery."""

    async def get(self, zone_id: int) -> Optional[Dict[str, Any]]:
        rows = await fetch(
            """
            SELECT zone_id, workflow_phase, started_at, updated_at, payload, scheduler_task_id
            FROM zone_workflow_state
            WHERE zone_id = $1
            LIMIT 1
            """,
            zone_id,
        )
        if not rows:
            return None
        row = rows[0]
        payload = _normalize_payload(row.get("payload"))
        return {
            "zone_id": int(row["zone_id"]),
            "workflow_phase_raw": row.get("workflow_phase"),
            "workflow_phase": _normalize_phase(row.get("workflow_phase")),
            "started_at": row.get("started_at"),
            "updated_at": row.get("updated_at"),
            "payload": row.get("payload"),
            "payload_normalized": payload,
            "scheduler_task_id": row.get("scheduler_task_id"),
        }

    async def list_active(self) -> List[Dict[str, Any]]:
        rows = await fetch(
            """
            SELECT zone_id, workflow_phase, started_at, updated_at, payload, scheduler_task_id
            FROM zone_workflow_state
            WHERE workflow_phase <> 'idle'
            ORDER BY zone_id ASC
            """
        )
        result: List[Dict[str, Any]] = []
        for row in rows:
            try:
                zone_id = int(row["zone_id"])
            except (TypeError, ValueError):
                logger.warning(
                    "Skipping malformed zone_workflow_state row: invalid zone_id=%r",
                    row.get("zone_id"),
                )
                continue

            payload = row.get("payload")
            normalized_payload = _normalize_payload(payload)
            result.append(
                {
                    "zone_id": zone_id,
                    "workflow_phase_raw": row.get("workflow_phase"),
                    "workflow_phase": _normalize_phase(row.get("workflow_phase")),
                    "started_at": row.get("started_at"),
                    "updated_at": row.get("updated_at"),
                    "payload": payload,
                    "payload_normalized": normalized_payload,
                    "scheduler_task_id": row.get("scheduler_task_id"),
                }
            )
        return result

    async def set(
        self,
        *,
        zone_id: int,
        workflow_phase: str,
        payload: Optional[Dict[str, Any]] = None,
        scheduler_task_id: Optional[str] = None,
    ) -> None:
        normalized_phase = _normalize_phase(workflow_phase)
        existing = await self.get(zone_id)
        existing_payload = existing.get("payload_normalized") if isinstance(existing, dict) else {}
        if not isinstance(existing_payload, dict):
            existing_payload = {}

        started_at: Optional[datetime]
        if normalized_phase == "idle":
            started_at = None
        elif (
            existing is not None
            and _normalize_phase(existing.get("workflow_phase")) == normalized_phase
            and existing.get("started_at") is not None
        ):
            started_at = existing.get("started_at")
        else:
            started_at = utcnow()

        next_payload = dict(payload) if isinstance(payload, dict) else {}
        if "control_mode" not in next_payload and "control_mode" in existing_payload:
            next_payload["control_mode"] = existing_payload["control_mode"]

        payload_json = json.dumps(next_payload)
        await execute(
            """
            INSERT INTO zone_workflow_state (
                zone_id,
                workflow_phase,
                started_at,
                updated_at,
                payload,
                scheduler_task_id
            )
            VALUES ($1, $2, $3, NOW(), $4::jsonb, $5)
            ON CONFLICT (zone_id) DO UPDATE
            SET workflow_phase = EXCLUDED.workflow_phase,
                started_at = EXCLUDED.started_at,
                updated_at = NOW(),
                payload = EXCLUDED.payload,
                scheduler_task_id = EXCLUDED.scheduler_task_id
            """,
            zone_id,
            normalized_phase,
            started_at,
            payload_json,
            scheduler_task_id,
        )
