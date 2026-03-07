"""ZoneWorkflow entity for AE3-Lite v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class ZoneWorkflow:
    """Canonical workflow state owned by AE3 `cycle_start` execution."""

    zone_id: int
    workflow_phase: str
    version: int
    scheduler_task_id: Optional[str]
    started_at: Optional[datetime]
    updated_at: datetime
    payload: Mapping[str, Any]

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ZoneWorkflow":
        payload = row.get("payload")
        normalized_payload = payload if isinstance(payload, Mapping) else {}
        return cls(
            zone_id=int(row["zone_id"]),
            workflow_phase=str(row.get("workflow_phase") or "").strip().lower(),
            version=int(row.get("version") or 0),
            scheduler_task_id=str(row["scheduler_task_id"]) if row.get("scheduler_task_id") is not None else None,
            started_at=row.get("started_at"),
            updated_at=row["updated_at"],
            payload=normalized_payload,
        )

    @property
    def is_idle(self) -> bool:
        return self.workflow_phase == "idle"
