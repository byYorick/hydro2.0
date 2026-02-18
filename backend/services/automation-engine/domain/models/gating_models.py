"""Gating model dataclasses."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CorrectionGatingSnapshot:
    can_run: bool
    reason_code: str
