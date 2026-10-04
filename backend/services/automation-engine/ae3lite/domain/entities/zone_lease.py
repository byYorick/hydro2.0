"""Сущность ZoneLease для AE3-Lite v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class ZoneLease:
    """Single-writer lease на уровне зоны."""

    zone_id: int
    owner: str
    leased_until: datetime
    updated_at: datetime
    claim_generation: int = 0
    process_run_id: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ZoneLease":
        raw_run = row.get("process_run_id")
        return cls(
            zone_id=int(row["zone_id"]),
            owner=str(row.get("owner") or ""),
            leased_until=row["leased_until"],
            updated_at=row["updated_at"],
            claim_generation=int(row.get("claim_generation") or 0),
            process_run_id=str(raw_run) if raw_run not in (None, "") else None,
        )

    def is_expired(self, *, now: datetime) -> bool:
        return self.leased_until <= now

    def can_be_claimed_by(self, *, owner: str, now: datetime) -> bool:
        return self.owner == owner or self.is_expired(now=now)
