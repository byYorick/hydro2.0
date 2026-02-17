"""Health/readiness helpers for API layer decomposition."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple


ReadinessPair = Tuple[bool, str]


def is_command_bus_ready(
    *,
    command_bus: Any,
    command_bus_loop_id: Optional[int],
    is_loop_affinity_mismatch_fn: Callable[[Optional[int]], bool],
    loop_mismatch_code: str,
) -> ReadinessPair:
    if command_bus is None:
        return False, "command_bus_unavailable"
    if is_loop_affinity_mismatch_fn(command_bus_loop_id):
        return False, loop_mismatch_code
    return True, "ok"


def is_bootstrap_store_ready(
    *,
    scheduler_bootstrap_leases: Any,
    scheduler_bootstrap_lock: Any,
) -> ReadinessPair:
    if not isinstance(scheduler_bootstrap_leases, dict):
        return False, "lease_store_invalid"
    if scheduler_bootstrap_lock is None:
        return False, "lease_lock_missing"
    return True, "ok"


async def is_db_ready(
    *,
    fetch_fn: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
) -> ReadinessPair:
    try:
        # Lightweight readiness probe for DB transport path used by API.
        await fetch_fn("SELECT 1 AS ready")
        return True, "ok"
    except Exception as exc:
        logger.warning("Readiness DB probe failed: %s", exc, exc_info=True)
        return False, type(exc).__name__


async def build_readiness_payload(
    *,
    command_bus: Any,
    command_bus_loop_id: Optional[int],
    is_loop_affinity_mismatch_fn: Callable[[Optional[int]], bool],
    loop_mismatch_code: str,
    scheduler_bootstrap_leases: Any,
    scheduler_bootstrap_lock: Any,
    fetch_fn: Callable[..., Awaitable[Any]],
    logger: logging.Logger,
) -> Dict[str, Any]:
    command_bus_ready, command_bus_reason = is_command_bus_ready(
        command_bus=command_bus,
        command_bus_loop_id=command_bus_loop_id,
        is_loop_affinity_mismatch_fn=is_loop_affinity_mismatch_fn,
        loop_mismatch_code=loop_mismatch_code,
    )
    db_ready, db_reason = await is_db_ready(fetch_fn=fetch_fn, logger=logger)
    bootstrap_store_ready, bootstrap_store_reason = is_bootstrap_store_ready(
        scheduler_bootstrap_leases=scheduler_bootstrap_leases,
        scheduler_bootstrap_lock=scheduler_bootstrap_lock,
    )

    ready = command_bus_ready and db_ready and bootstrap_store_ready
    return {
        "status": "ok" if ready else "degraded",
        "service": "automation-engine",
        "ready": ready,
        "checks": {
            "command_bus": {"ok": command_bus_ready, "reason": command_bus_reason},
            "db": {"ok": db_ready, "reason": db_reason},
            "bootstrap_store": {"ok": bootstrap_store_ready, "reason": bootstrap_store_reason},
        },
    }


__all__ = [
    "build_readiness_payload",
    "is_bootstrap_store_ready",
    "is_command_bus_ready",
    "is_db_ready",
]
