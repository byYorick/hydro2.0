"""Reject operator mutating commands while AE3 holds the zone lease."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Mapping

from fastapi import HTTPException

from common.db import fetch as default_fetch

logger = logging.getLogger(__name__)

_AE_SOURCE_PREFIX = "automation-engine"
_READ_ONLY_CMDS = {"state", "test_sensor"}

FetchFn = Callable[..., Awaitable[Any]]


def _is_ae_source(source: str | None) -> bool:
    value = str(source or "").strip().lower()
    return value == _AE_SOURCE_PREFIX or value.startswith(f"{_AE_SOURCE_PREFIX}:")


def _truthy_off(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"0", "false", "off", "no"}
    return value in {0, False}


def is_fail_safe_off_command(cmd: str, params: Mapping[str, Any] | None) -> bool:
    name = str(cmd or "").strip().lower()
    payload = params if isinstance(params, Mapping) else {}
    if name in {"set_relay", "set_state"}:
        return _truthy_off(payload.get("state"))
    if name == "set_pwm":
        duty = payload.get("duty", payload.get("duty_pct", payload.get("percent")))
        try:
            return duty is not None and float(duty) <= 0
        except (TypeError, ValueError):
            return False
    return False


async def reject_if_zone_lease_held(
    *,
    zone_id: int,
    cmd: str,
    params: Mapping[str, Any] | None,
    source: str | None,
    fetch_fn: FetchFn | None = None,
) -> None:
    name = str(cmd or "").strip().lower()
    if _is_ae_source(source) or name in _READ_ONLY_CMDS or is_fail_safe_off_command(name, params):
        return

    query_fetch = fetch_fn or default_fetch
    rows = await query_fetch(
        """
        SELECT 1
        FROM ae_zone_leases
        WHERE zone_id = $1
          AND leased_until > NOW()
        LIMIT 1
        """,
        int(zone_id),
    )
    if not rows:
        return

    logger.warning(
        "Rejecting command %s for zone %s: AE3 lease is held (source=%s)",
        name,
        zone_id,
        source,
    )
    raise HTTPException(
        status_code=409,
        detail={"error": "ae3_zone_lease_held", "zone_id": int(zone_id)},
    )
