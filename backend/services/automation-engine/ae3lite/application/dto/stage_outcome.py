"""Stage outcome DTO returned by handler classes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, Tuple

from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState


@dataclass(frozen=True)
class StageOutcome:
    """Value object returned by every stage handler to describe what happened.

    The ``kind`` field determines how :class:`WorkflowRouter` interprets the outcome:

    * ``poll`` – stay in the same stage, re-enqueue with *due_delay_sec*.
    * ``transition`` – move to *next_stage* (clears correction state).
    * ``enter_correction`` – start or continue correction (keeps current stage).
    * ``exit_correction`` – correction finished, transition to *next_stage*.
    * ``complete`` – mark task completed.
    * ``fail`` – mark task failed with *error_code* / *error_message*.
    """

    kind: Literal[
        "poll",
        "transition",
        "enter_correction",
        "exit_correction",
        "complete",
        "fail",
    ]

    next_stage: Optional[str] = None
    due_delay_sec: float = 0

    # Workflow state overrides applied on transition
    stage_retry_count: Optional[int] = None
    clean_fill_cycle: Optional[int] = None

    # Correction state (set on enter_correction / exit_correction)
    correction: Optional[CorrectionState] = None

    # Error info (set on fail)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
