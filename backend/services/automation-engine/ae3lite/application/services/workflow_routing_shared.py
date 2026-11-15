"""Shared records and immutable policy values for WorkflowRouter."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger('ae3lite.application.use_cases.workflow_router')


class _StageUpdateNotApplied(Exception):
    """Internal sentinel: task update CAS did not apply inside an atomic transition."""


_DEFAULT_CORRECTION_SLACK_SEC: int = 900

_MAX_CORRECTION_SLACK_SEC: int = 7200

_MAX_STAGE_TOTAL_SEC: int = 86400

_MAX_DUE_DELAY_SEC: int = _MAX_STAGE_TOTAL_SEC

_DEFAULT_MANUAL_HOLD_TIMEOUT_SEC: int = 86400


def _clamp_due_delay_sec(raw: Any) -> int:
    """Clamp a handler-supplied ``due_delay_sec`` to ``[0, _MAX_DUE_DELAY_SEC]``.

    Treats non-numeric or negative values as 0 (immediate retry). Never
    raises — the scheduler should keep moving even if a handler returns
    something weird, and the value is also logged by the caller so
    observability surfaces the anomaly.
    """
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    if value < 0:
        return 0
    if value > _MAX_DUE_DELAY_SEC:
        logger.warning(
            "workflow_router: due_delay_sec=%s превышает верхний предел %ss; ограничиваю",
            value,
            _MAX_DUE_DELAY_SEC,
        )
        return _MAX_DUE_DELAY_SEC
    return value
