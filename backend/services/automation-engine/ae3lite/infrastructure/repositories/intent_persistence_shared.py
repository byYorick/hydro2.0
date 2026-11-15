"""Shared records and immutable policy values for PgZoneIntentRepository."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from ae3lite.domain.errors import ErrorCodes

logger = logging.getLogger('ae3lite.infrastructure.repositories.zone_intent_repository')


def _affected_rows(command_tag: Any) -> int:
    try:
        return int(str(command_tag).split()[-1])
    except (AttributeError, IndexError, TypeError, ValueError):
        return 0


_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

_ACTIVE_STATUSES = frozenset({"claimed", "running"})


def _is_retryable_failed_intent(existing: Mapping[str, Any]) -> bool:
    try:
        retry_count = int(existing.get("retry_count") or 0)
        max_retries = int(existing.get("max_retries") or 0)
    except (TypeError, ValueError):
        return False
    return retry_count < max_retries


_TRANSIENT_RETRYABLE_ERROR_CODES = frozenset(
    {
        ErrorCodes.AE3_REQUIRED_NODE_OFFLINE,
        "ae3_required_node_offline",
        ErrorCodes.COMMAND_SEND_FAILED,
        "command_send_failed",
        ErrorCodes.IRR_STATE_UNAVAILABLE,
        "irr_state_unavailable",
        ErrorCodes.IRR_STATE_STALE,
        "irr_state_stale",
        "command_timeout",
    }
)
