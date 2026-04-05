"""DTO результата reconcile команды в AE3-Lite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ae3lite.domain.entities import AutomationTask


@dataclass(frozen=True)
class CommandReconcileResult:
    """Результат reconcile для одного шага команды в состоянии waiting в AE3-Lite."""

    task: AutomationTask
    ae_command_id: int
    external_id: Optional[str]
    legacy_cmd_id: Optional[str]
    legacy_status: Optional[str]
    terminal_status: Optional[str]
    is_terminal: bool
