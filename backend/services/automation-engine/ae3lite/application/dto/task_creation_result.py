"""Result DTO for canonical AE3-Lite task creation from legacy ingress."""

from __future__ import annotations

from dataclasses import dataclass

from ae3lite.domain.entities import AutomationTask


@dataclass(frozen=True)
class TaskCreationResult:
    """Describes whether a canonical AE3 task was newly created or deduplicated."""

    task: AutomationTask
    created: bool
