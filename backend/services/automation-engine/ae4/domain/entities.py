"""Сущности runtime AE4 (без импорта ae3lite)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

ACTIVE_TASK_STATUSES = frozenset({"pending", "claimed", "running", "waiting_command"})
INFLIGHT_TASK_STATUSES = frozenset({"claimed", "running", "waiting_command"})


@dataclass(frozen=True)
class ZoneLease:
    zone_id: int
    owner: str
    leased_until: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ZoneLease":
        return cls(
            zone_id=int(row["zone_id"]),
            owner=str(row.get("owner") or ""),
            leased_until=row["leased_until"],
            updated_at=row["updated_at"],
        )


@dataclass(frozen=True)
class Ae4Task:
    id: int
    zone_id: int
    task_type: str
    status: str
    idempotency_key: str
    due_at: datetime
    claimed_by: Optional[str]
    claimed_at: Optional[datetime]
    error_code: Optional[str]
    error_message: Optional[str]
    intent_meta: Mapping[str, Any]
    current_stage: str
    workflow_phase: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Ae4Task":
        meta = row.get("intent_meta")
        if isinstance(meta, str):
            import json

            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        if not isinstance(meta, Mapping):
            meta = {}
        return cls(
            id=int(row["id"]),
            zone_id=int(row["zone_id"]),
            task_type=str(row["task_type"]),
            status=str(row["status"]),
            idempotency_key=str(row["idempotency_key"]),
            due_at=row["due_at"],
            claimed_by=(str(row["claimed_by"]) if row.get("claimed_by") else None),
            claimed_at=row.get("claimed_at"),
            error_code=(str(row["error_code"]) if row.get("error_code") else None),
            error_message=(
                str(row["error_message"]) if row.get("error_message") else None
            ),
            intent_meta=dict(meta),
            current_stage=str(row.get("current_stage") or ""),
            workflow_phase=str(row.get("workflow_phase") or "idle"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row.get("completed_at"),
        )


__all__ = [
    "ACTIVE_TASK_STATUSES",
    "INFLIGHT_TASK_STATUSES",
    "Ae4Task",
    "ZoneLease",
]
