"""Результат фонового reconcile orphan intent ↔ terminal task."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrphanIntentReconcileResult:
    scanned_intents: int
    reconciled_intents: int
    failed_intents: int


__all__ = ["OrphanIntentReconcileResult"]
