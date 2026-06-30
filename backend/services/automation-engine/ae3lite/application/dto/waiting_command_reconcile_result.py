"""Результат фонового reconcile для задач в `waiting_command`."""

from __future__ import annotations

from dataclasses import dataclass

from .startup_recovery_result import StartupRecoveryTerminalOutcome


@dataclass(frozen=True)
class WaitingCommandReconcileResult:
    scanned_tasks: int
    progressed_tasks: int
    failed_tasks: int
    unchanged_tasks: int
    skipped_lease_tasks: int
    terminal_outcomes: tuple[StartupRecoveryTerminalOutcome, ...]

    @property
    def kick_needed(self) -> bool:
        return self.progressed_tasks > 0
