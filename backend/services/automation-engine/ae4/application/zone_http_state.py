"""Сборка состояния зоны для экрана (без имён стадий бака)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ae4.application.zone_state import enrich_zone_automation_state
from ae4.infrastructure.repositories.automation_task_repository import PgAutomationTaskRepository
from ae4.infrastructure.repositories.zone_lease_repository import PgZoneLeaseRepository
from ae4.runtime.worker import AE4_WORKER_OWNER
from common.db import execute, fetch

logger = logging.getLogger(__name__)

_AVAILABLE_CONTROL_MODES = ("auto", "semi", "manual")


def normalize_control_mode(raw: Any) -> str:
    value = str(raw or "auto").strip().lower()
    if value in _AVAILABLE_CONTROL_MODES:
        return value
    return "auto"


async def build_zone_automation_state(*, zone_id: int) -> dict[str, Any]:
    """Payload /zones/{id}/state для runtime 1.0.0."""
    zone_rows = await fetch(
        """
        SELECT id, control_mode, automation_runtime, status
        FROM zones
        WHERE id = $1
        LIMIT 1
        """,
        zone_id,
    )
    if not zone_rows:
        raise LookupError(f"zone {zone_id} not found")

    zone = zone_rows[0]
    control_mode = normalize_control_mode(zone.get("control_mode"))
    runtime = str(zone.get("automation_runtime") or "").strip().lower()

    repo = PgAutomationTaskRepository()
    active = await repo.get_active_for_zone(zone_id=zone_id)
    last = None if active is not None else await repo.get_last_for_zone(zone_id=zone_id)
    task = active or last

    due_at = None
    task_id = None
    task_status = None
    if task is not None:
        task_id = int(task.id)
        task_status = str(task.status)
        raw_due = getattr(task, "due_at", None)
        if raw_due is not None:
            due_at = raw_due.isoformat() if hasattr(raw_due, "isoformat") else str(raw_due)

    payload: dict[str, Any] = {
        "zone_id": zone_id,
        "state": "RUNNING" if active is not None else "IDLE",
        "state_label": "Задача выполняется" if active is not None else "Ожидание",
        "state_details": {
            "failed": False,
            "control_mode": control_mode,
            "task_id": task_id,
            "task_status": task_status,
            "due_at": due_at,
            "automation_runtime": runtime or "ae4",
        },
        "control_mode": control_mode,
        "available_control_modes": list(_AVAILABLE_CONTROL_MODES),
        "allowed_manual_steps": [],
        "system_config": {},
        "current_levels": [],
        "active_processes": [],
        "timeline": [],
        "due_at": due_at,
    }

    return await enrich_zone_automation_state(zone_id=zone_id, payload=payload)


async def get_zone_control_state(*, zone_id: int) -> dict[str, Any]:
    rows = await fetch(
        "SELECT control_mode FROM zones WHERE id = $1 LIMIT 1",
        zone_id,
    )
    if not rows:
        raise LookupError(f"zone {zone_id} not found")
    control_mode = normalize_control_mode(rows[0].get("control_mode"))
    return {
        "control_mode": control_mode,
        "available_control_modes": list(_AVAILABLE_CONTROL_MODES),
        "allowed_manual_steps": [],
        "current_stage": None,
        "workflow_phase": None,
        "pending_manual_step": None,
    }


async def set_zone_control_mode(
    *,
    zone_id: int,
    control_mode: str,
    user_id: int | None = None,
    user_role: str | None = None,
    source: str = "api",
    reason: str | None = None,
) -> str:
    del user_id, user_role, source, reason
    normalized = normalize_control_mode(control_mode)
    await execute(
        """
        UPDATE zones
        SET control_mode = $2, updated_at = NOW()
        WHERE id = $1
        """,
        zone_id,
        normalized,
    )
    if normalized == "manual":
        repo = PgAutomationTaskRepository()
        active = await repo.get_active_for_zone(zone_id=zone_id)
        if active is not None:
            await repo.force_fail(
                task_id=active.id,
                now=datetime.now(timezone.utc).replace(tzinfo=None),
                error_code="control_mode_switched_to_manual",
                error_message="Режим переключён в manual",
            )
    return normalized


async def operator_unblock_zone(
    *,
    zone_id: int,
    reason: str | None = None,
    source: str = "laravel_api",
    user_id: int | None = None,
    user_role: str | None = None,
) -> dict[str, Any]:
    del source, user_id, user_role
    repo = PgAutomationTaskRepository()
    active = await repo.get_active_for_zone(zone_id=zone_id)
    failed_task_id = None
    if active is not None:
        failed_task_id = int(active.id)
        await repo.force_fail(
            task_id=active.id,
            now=datetime.now(timezone.utc).replace(tzinfo=None),
            error_code="operator_unblock",
            error_message=str(reason or "operator_unblock"),
        )
        lease_repo = PgZoneLeaseRepository()
        try:
            await lease_repo.release(zone_id=zone_id, owner=AE4_WORKER_OWNER)
        except Exception:
            logger.warning("operator_unblock: lease release failed zone_id=%s", zone_id, exc_info=True)

    return {
        "zone_id": zone_id,
        "failed_task_id": failed_task_id,
        "reason": reason,
    }


__all__ = [
    "build_zone_automation_state",
    "get_zone_control_state",
    "set_zone_control_mode",
    "operator_unblock_zone",
    "normalize_control_mode",
]
