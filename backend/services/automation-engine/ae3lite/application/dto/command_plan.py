"""DTO результата planner'а для AE3-Lite v1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Tuple, Union

from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.entities import PlannedCommand


@dataclass(frozen=True)
class CommandPlan:
    """Разрешённый command plan для канонической задачи AE3-Lite.

    `runtime` field type (Phase 3.1 / B-5):
    - Production path (cycle_start_planner) populates it with a typed
      `RuntimePlan` Pydantic model (validated via `resolve_two_tank_runtime_plan`).
    - Legacy callers/tests may still pass a raw `Mapping` dict — handlers
      treat both uniformly because `RuntimePlan` exposes a dict-like
      `__getitem__`/`get`/`__contains__` API (transition shim).

    Phase 4 narrows this to `RuntimePlan` only and drops the dict-shim.
    """

    task_type: str
    workflow: str
    topology: str
    steps: Tuple[PlannedCommand, ...]
    targets: Mapping[str, Any]
    named_plans: Mapping[str, Tuple[PlannedCommand, ...]] = field(default_factory=dict)
    runtime: Union[RuntimePlan, Mapping[str, Any]] = field(default_factory=dict)
