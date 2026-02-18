"""Command model dataclasses."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CommandDispatchResult:
    command_submitted: bool
    command_effect_confirmed: bool
    terminal_status: Optional[str] = None
