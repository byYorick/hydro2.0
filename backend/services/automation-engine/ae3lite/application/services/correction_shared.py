"""Correction shared value records, immutable defaults and snapshot helpers."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from typing import Any, Mapping

from ae3lite.domain.entities.workflow_state import ALERT_BLOCK_SNAPSHOT_CMD_PREFIX, CorrectionState

_logger = logging.getLogger("ae3lite.application.handlers.correction")


@dataclass(frozen=True)
class _MeasurementSnapshot:
    """Immutable result of ``_read_measurements_or_interrupt``.

    Carries the validated current pH / EC readings plus the derived workflow
    readiness flag and normalized ``current_stage`` used by downstream
    success-check and routing helpers. Not a domain type — purely an internal
    plumbing record to avoid a tuple-of-four positional return.
    """

    current_ph: float
    current_ec: float
    workflow_ready: bool
    current_stage: str


_STALE_RECHECK_DELAY_SEC = 0.25

_AE_CORRECTION_ALERT_BLOCK_MAX_RETRIES = max(
    1,
    int(os.getenv("AE_CORRECTION_ALERT_BLOCK_MAX_RETRIES", "10")),
)

_ALERT_BLOCK_RETRY_DELAY_SEC = 60

_ALERT_BLOCK_SNAPSHOT_PREFIX = ALERT_BLOCK_SNAPSHOT_CMD_PREFIX

_DEFAULT_DILUTE_PULSE_SEC = 10

_DEFAULT_DILUTE_SETTLE_SEC = 30


def _alert_block_retry_count(corr: CorrectionState) -> int:
    raw = str(corr.snapshot_cmd_id or "")
    if not raw.startswith(_ALERT_BLOCK_SNAPSHOT_PREFIX):
        return 0
    try:
        return int(raw[len(_ALERT_BLOCK_SNAPSHOT_PREFIX) :])
    except ValueError:
        return 0


def _clear_alert_block_marker(corr: CorrectionState) -> CorrectionState:
    raw = str(corr.snapshot_cmd_id or "")
    if raw.startswith(_ALERT_BLOCK_SNAPSHOT_PREFIX):
        return replace(corr, snapshot_cmd_id=None)
    return corr


def _pid_entry_or_none(pid_state: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    """Return pid_state[key] if it is a Mapping, otherwise None.

    Avoids double-call `x.get(k) if isinstance(x.get(k), Mapping) else None`
    that would call .get() twice and confuse static analysers.
    pid_state is always a runtime-dict from PostgreSQL; individual keys are
    optional because AE3 may not have written a PID entry yet.
    """
    value = pid_state.get(key)
    return value if isinstance(value, Mapping) else None
