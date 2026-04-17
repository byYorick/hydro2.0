"""DTO результата planner'а для AE3-Lite v1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Tuple

from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.entities import PlannedCommand


@dataclass(frozen=True)
class CommandPlan:
    """Разрешённый command plan для канонической задачи AE3-Lite.

    `runtime` field type:
    - Production path (cycle_start_planner) populates it with a typed
      `RuntimePlan` Pydantic model (validated via `resolve_two_tank_runtime_plan`).
    - Tasks without runtime contract (например, lighting tick) оставляют `runtime=None`.
    """

    task_type: str
    workflow: str
    topology: str
    steps: Tuple[PlannedCommand, ...]
    targets: Mapping[str, Any]
    named_plans: Mapping[str, Tuple[PlannedCommand, ...]] = field(default_factory=dict)
    runtime: RuntimePlan | None = None

    def __post_init__(self) -> None:
        if self.runtime is not None and not isinstance(self.runtime, RuntimePlan):
            raise TypeError(
                "CommandPlan.runtime must be RuntimePlan | None; raw Mapping compatibility is removed",
            )
