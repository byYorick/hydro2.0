"""Workflow model dataclasses."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class WorkflowState:
    zone_id: int
    workflow_phase: str
    workflow_stage: Optional[str] = None
