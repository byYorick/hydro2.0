"""PostgreSQL advisory lock for per-zone distributed execution serialization."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

_logger = logging.getLogger(__name__)

# "TWO\0" namespace prefix to reduce collision risk with other lock users.
_LOCK_NAMESPACE = 0x54_57_4F_00


@asynccontextmanager
async def zone_execution_context_pg(
    zone_id: int,
    *,
    fetch_fn: Any,
    task_type: str = "unknown",
    workflow: str = "",
) -> AsyncIterator[None]:
    """Acquire per-zone distributed lock using PostgreSQL advisory xact locks.

    NOTE:
    - Requires one dedicated DB connection/transaction per workflow execution.
    - `pg_advisory_xact_lock` auto-releases on transaction end.
    - This module is design scaffold and is not wired into runtime yet.

    TODO: integrate with executor connection lifecycle when horizontal scaling
    of automation-engine becomes required.
    """
    lock_key = _LOCK_NAMESPACE + int(zone_id)

    rows = await fetch_fn(
        "SELECT pg_try_advisory_xact_lock($1) AS acquired",
        lock_key,
    )
    acquired = bool(rows and rows[0].get("acquired"))

    if not acquired:
        _logger.warning(
            "Zone %s: distributed lock contention (task_type=%s workflow=%s) - waiting",
            zone_id,
            task_type,
            workflow or "<none>",
        )
        await fetch_fn("SELECT pg_advisory_xact_lock($1)", lock_key)

    try:
        yield
    finally:
        # xact advisory lock is released automatically by PostgreSQL.
        pass


__all__ = ["zone_execution_context_pg"]
