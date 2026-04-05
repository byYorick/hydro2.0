"""DTO-модели результата startup recovery в AE3-Lite."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StartupRecoveryTerminalOutcome:
    """Терминальный итог legacy-intent, обнаруженный во время startup recovery."""

    task_id: int
    intent_id: int
    success: bool
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True)
class StartupRecoveryResult:
    """Агрегированный результат одного прохода startup recovery."""

    released_expired_leases: int
    scanned_tasks: int
    completed_tasks: int
    failed_tasks: int
    waiting_command_tasks: int
    recovered_waiting_command_tasks: int
    terminal_outcomes: tuple[StartupRecoveryTerminalOutcome, ...] = field(default_factory=tuple)
