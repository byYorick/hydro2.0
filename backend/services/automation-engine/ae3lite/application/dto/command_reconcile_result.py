"""DTO for AE3-Lite command reconcile outcome."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ae3lite.domain.entities import AutomationTask


@dataclass(frozen=True)
class CommandReconcileResult:
    """Reconcile result for one waiting AE3-Lite command step."""

    task: AutomationTask
    ae_command_id: int
    external_id: Optional[str]
    legacy_cmd_id: Optional[str]
    legacy_status: Optional[str]
    terminal_status: Optional[str]
    is_terminal: bool
