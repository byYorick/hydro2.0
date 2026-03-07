"""DTOs for AE3-Lite startup recovery outcome."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StartupRecoveryTerminalOutcome:
    """Terminal legacy-intent outcome discovered during startup recovery."""

    task_id: int
    intent_id: int
    success: bool
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True)
class StartupRecoveryResult:
    """Aggregated outcome of one startup recovery pass."""

    released_expired_leases: int
    scanned_tasks: int
    completed_tasks: int
    failed_tasks: int
    waiting_command_tasks: int
    recovered_waiting_command_tasks: int
    terminal_outcomes: tuple[StartupRecoveryTerminalOutcome, ...] = field(default_factory=tuple)
