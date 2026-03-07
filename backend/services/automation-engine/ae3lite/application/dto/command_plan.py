"""Planner output DTO for AE3-Lite v1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Tuple

from ae3lite.domain.entities import PlannedCommand


@dataclass(frozen=True)
class CommandPlan:
    """Resolved command plan for a canonical AE3-Lite task."""

    task_type: str
    workflow: str
    topology: str
    steps: Tuple[PlannedCommand, ...]
    targets: Mapping[str, Any]
    named_plans: Mapping[str, Tuple[PlannedCommand, ...]] = field(default_factory=dict)
    runtime: Mapping[str, Any] = field(default_factory=dict)
