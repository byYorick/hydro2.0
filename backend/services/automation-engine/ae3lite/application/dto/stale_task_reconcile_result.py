"""Результат фонового reconcile застрявших claimed/running задач."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StaleTaskReconcileResult:
    released_expired_leases: int
    scanned_tasks: int
    requeued_tasks: int
    failed_tasks: int
    skipped_lease_tasks: int

    @property
    def kick_needed(self) -> bool:
        return self.requeued_tasks > 0 or self.failed_tasks > 0 or self.failed_tasks > 0 or self.failed_tasks > 0
