"""Runtime listener for effective-targets cache invalidation via ae_signal_update."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Optional, Tuple

from ae2lite.pg_notify_listener import PgNotifyListener
from common.env import get_settings

InvalidateCacheFn = Callable[[int], None]

# Ignore telemetry churn; invalidate on domain updates that can change targets.
_INVALIDATION_KINDS = {
    "zone_event",
    "grow_cycle",
    "grow_cycle_phase",
    "grow_cycle_override",
    "grow_cycle_transition",
}


def _to_zone_id(raw_zone_id: Any) -> Optional[int]:
    try:
        value = int(raw_zone_id)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def should_invalidate_for_kind(kind: Any) -> bool:
    normalized = str(kind or "").strip().lower()
    if not normalized:
        return False
    if normalized == "telemetry_last":
        return False
    return normalized in _INVALIDATION_KINDS


async def handle_ae_signal_update_payload(
    payload: str,
    *,
    invalidate_cache_fn: InvalidateCacheFn,
    logger: logging.Logger,
) -> None:
    try:
        event = json.loads(payload) if payload else {}
    except Exception:
        logger.debug("Failed to decode ae_signal_update payload: %s", payload)
        return

    if not isinstance(event, dict):
        return

    zone_id = _to_zone_id(event.get("zone_id"))
    if zone_id is None:
        return

    if not should_invalidate_for_kind(event.get("kind")):
        return

    invalidate_cache_fn(zone_id)


async def start_effective_targets_notify_listener(
    *,
    invalidate_cache_fn: InvalidateCacheFn,
    shutdown_event: asyncio.Event,
    logger: logging.Logger,
) -> Tuple[Optional[PgNotifyListener], Optional[asyncio.Task[None]]]:
    settings = get_settings()
    dsn = (
        f"postgresql://{settings.pg_user}:{settings.pg_pass}@"
        f"{settings.pg_host}:{settings.pg_port}/{settings.pg_db}"
    )

    listener = PgNotifyListener(
        dsn=dsn,
        channel="ae_signal_update",
        handler=lambda payload: handle_ae_signal_update_payload(
            payload,
            invalidate_cache_fn=invalidate_cache_fn,
            logger=logger,
        ),
    )

    try:
        await listener.connect()
    except Exception as exc:
        logger.warning(
            "Failed to connect ae_signal_update listener, using TTL fallback only: %s",
            exc,
            exc_info=True,
        )
        await listener.close()
        return None, None

    async def _pump() -> None:
        while not shutdown_event.is_set():
            try:
                await listener.pump_once(timeout_sec=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("ae_signal_update listener loop error: %s", exc, exc_info=True)
                await listener.close()
                await asyncio.sleep(1.0)
                try:
                    await listener.connect()
                except Exception:
                    await asyncio.sleep(1.0)

        await listener.close()

    task = asyncio.create_task(_pump(), name="ae_signal_update_listener")
    logger.info("Started ae_signal_update listener for effective-targets cache invalidation")
    return listener, task


async def stop_effective_targets_notify_listener(
    *,
    listener: Optional[PgNotifyListener],
    task: Optional[asyncio.Task[None]],
) -> None:
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    if listener is not None:
        await listener.close()


__all__ = [
    "handle_ae_signal_update_payload",
    "should_invalidate_for_kind",
    "start_effective_targets_notify_listener",
    "stop_effective_targets_notify_listener",
]
