"""Reject operator mutating commands while AE3 holds the zone lease."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from fastapi import HTTPException

from common.db import fetch as default_fetch

logger = logging.getLogger(__name__)

_AE_SOURCE_PREFIX = "automation-engine"
_READ_ONLY_CMDS = {"state", "test_sensor"}
# test_node-only diagnostic: seed level/pH/EC/E-Stop without fighting AE3 actuators.
_DIAGNOSTIC_CMDS = {"set_fault_mode"}
_TEST_NODE_UID_PREFIX = "nd-test-"
_TEST_NODE_TYPES = {"test", "test_node"}

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


def _uid_is_test_node(node_uid: str | None) -> bool:
    return str(node_uid or "").strip().lower().startswith(_TEST_NODE_UID_PREFIX)


def _type_is_test_node(node_type: Any) -> bool:
    return str(node_type or "").strip().lower() in _TEST_NODE_TYPES


def _row_mapping(row: Any) -> Mapping[str, Any]:
    if isinstance(row, Mapping):
        return row
    return {}


async def _is_test_node(
    *,
    node_uid: str | None,
    node_id: int | None,
    fetch_fn: FetchFn,
) -> bool:
    """Fail-closed: one matching sign is enough (uid nd-test-* or type test/test_node)."""
    if _uid_is_test_node(node_uid):
        return True

    uid = str(node_uid or "").strip() or None
    resolved_id: int | None = None
    if node_id is not None:
        try:
            resolved_id = int(node_id)
        except (TypeError, ValueError):
            resolved_id = None

    if resolved_id is None and uid is None:
        return False

    if resolved_id is not None:
        rows = await fetch_fn(
            """
            SELECT uid, type
            FROM nodes
            WHERE id = $1
            LIMIT 1
            """,
            resolved_id,
        )
    else:
        rows = await fetch_fn(
            """
            SELECT uid, type
            FROM nodes
            WHERE uid = $1
            LIMIT 1
            """,
            uid,
        )
    if not rows:
        return False

    row = _row_mapping(rows[0])
    return _uid_is_test_node(row.get("uid")) or _type_is_test_node(row.get("type"))


async def reject_if_zone_lease_held(
    *,
    zone_id: int,
    cmd: str,
    params: Mapping[str, Any] | None,
    source: str | None,
    node_uid: str | None = None,
    node_id: int | None = None,
    fetch_fn: FetchFn | None = None,
) -> None:
    name = str(cmd or "").strip().lower()
    query_fetch = fetch_fn or default_fetch
    if (
        _is_ae_source(source)
        or name in _READ_ONLY_CMDS
        or is_fail_safe_off_command(name, params)
    ):
        return

    if name in _DIAGNOSTIC_CMDS and await _is_test_node(
        node_uid=node_uid,
        node_id=node_id,
        fetch_fn=query_fetch,
    ):
        return

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
        "Rejecting command %s for zone %s: AE3 lease is held (source=%s node_uid=%s)",
        name,
        zone_id,
        source,
        node_uid,
    )
    raise HTTPException(
        status_code=409,
        detail={"error": "ae3_zone_lease_held", "zone_id": int(zone_id)},
    )
