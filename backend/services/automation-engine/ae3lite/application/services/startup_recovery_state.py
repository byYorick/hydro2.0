"""Per-instance lifecycle state; no repositories or policy methods."""

from __future__ import annotations

from dataclasses import dataclass, field

from ae3lite.application.services.correction_interrupt_safety import (
    CorrectionInterruptPendingCheck,
)


@dataclass
class StartupRecoveryState:
    pending_correction_safety_checks: list[CorrectionInterruptPendingCheck] = field(default_factory=list)
