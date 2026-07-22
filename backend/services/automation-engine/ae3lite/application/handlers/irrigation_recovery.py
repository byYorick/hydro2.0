"""Removed post-irrigation chemistry recovery handler.

Topology no longer has ``irrigation_recovery_*`` stages. After irrigation the
only transitions are ``irrigation_stop_to_ready`` (normal) and
``irrigation_stop_to_setup`` (solution_min). This module remains as a fail-closed
stub so accidental imports fail loudly instead of dosing EC/pH in irrig_recirc.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError


class IrrigationRecoveryCheckHandler(BaseStageHandler):
    """Fail-closed stub — not registered in ``WorkflowRouter.HANDLER_MAP``."""

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        raise TaskExecutionError(
            "irrigation_recovery_removed",
            "Post-irrigation chemistry recovery stages were removed; "
            "irrigation ends with stop→ready (pH-only during irrig).",
        )


__all__ = ["IrrigationRecoveryCheckHandler"]
