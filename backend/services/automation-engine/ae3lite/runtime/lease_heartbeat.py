"""Zone lease heartbeat policy, independent from runtime drain orchestration.

Ownership rejection fails closed immediately. Transport errors use the bounded
per-tick retry and consecutive-failure budget configured by the worker.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.infrastructure.metrics import LEASE_HEARTBEAT_FAILED, ZONE_LEASE_LOST


async def extend_lease_with_transient_retry(
    *,
    zone_id: int,
    claim_generation: int,
    lease_repository: Any,
    owner: str,
    now_fn: Callable[[], datetime],
    lease_ttl_sec: int,
    transient_retries: int,
    logger: Any,
) -> bool | None:
    """Продлевает lease.

    True — владение подтверждено. False — extend явно отказал (чужой lease),
    без повторов. None — транспортная ошибка исчерпала retry этого тика.
    """
    max_attempts = 1 + transient_retries
    for attempt in range(max_attempts):
        try:
            extended = bool(
                await lease_repository.extend(
                    zone_id=zone_id,
                    owner=owner,
                    now=now_fn(),
                    lease_ttl_sec=lease_ttl_sec,
                    claim_generation=claim_generation,
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            if attempt + 1 >= max_attempts:
                logger.warning(
                    "AE3 lease heartbeat: extend failed after transient retries zone_id=%s owner=%s",
                    zone_id,
                    owner,
                    exc_info=True,
                )
                return None
            continue
        if not extended:
            return False
        return True
    return None


async def signal_lease_lost(
    *,
    zone_id: int,
    lease_lost_event: asyncio.Event,
    consecutive_failures: int,
    owner: str,
    logger: Any,
    send_alert: Callable[..., Awaitable[Any]],
) -> None:
    logger.error(
        "AE3 lease heartbeat: failed to extend lease for zone_id=%s owner=%s after %s attempts — "
        "signaling lease_lost; in-flight task execution will be cancelled",
        zone_id,
        owner,
        consecutive_failures,
    )
    ZONE_LEASE_LOST.labels(zone_id=str(zone_id)).inc()
    lease_lost_event.set()
    try:
        await send_alert(
            code="ae3_zone_lease_lost",
            alert_type="AE3 Zone Lease Lost",
            message=(
                "Heartbeat zone lease не смог продлить lease; worker помечает lease_lost "
                "и отменяет выполняющуюся задачу для этой зоны."
            ),
            severity="critical",
            zone_id=int(zone_id),
            service="automation-engine",
            component="worker:heartbeat",
            details={
                "owner": owner,
                "consecutive_failures": consecutive_failures,
                "message": "Heartbeat zone lease не смог продлить lease: зона могла быть перехвачена или зависнуть.",
            },
        )
    except Exception:
        logger.warning(
            "AE3 не смог отправить alert lease_lost zone_id=%s",
            zone_id,
            exc_info=True,
        )


async def run_lease_heartbeat(
    *,
    zone_id: int,
    lease_lost_event: asyncio.Event,
    claim_generation: int,
    owner: str,
    lease_ttl_sec: int,
    max_failures: int,
    extend_lease: Callable[..., Awaitable[bool | None]],
    signal_lost: Callable[..., Awaitable[None]],
    logger: Any,
    log_debug: Callable[..., None],
) -> None:
    """Периодически продлевает zone lease во время выполнения задачи.

    Heartbeat срабатывает примерно каждые 1/3 от TTL.
    ``extend()==False`` — подтверждённая потеря владения, lease_lost сразу.
    Исключение БД проходит transient retry и не гасит владение с первой ошибки.
    """
    interval = max(10.0, lease_ttl_sec / 3.0)
    consecutive_failures = 0
    while True:
        await asyncio.sleep(interval)
        try:
            extended = await extend_lease(
                zone_id=zone_id,
                claim_generation=claim_generation,
            )
            if extended is True:
                consecutive_failures = 0
                log_debug("AE3 lease heartbeat extended: zone_id=%s owner=%s", zone_id, owner)
                continue

            LEASE_HEARTBEAT_FAILED.labels(zone_id=str(zone_id)).inc()
            if extended is False:
                await signal_lost(
                    zone_id=zone_id,
                    lease_lost_event=lease_lost_event,
                    consecutive_failures=1,
                )
                break

            consecutive_failures += 1
            if consecutive_failures < max_failures:
                continue

            await signal_lost(
                zone_id=zone_id,
                lease_lost_event=lease_lost_event,
                consecutive_failures=consecutive_failures,
            )
            break
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning(
                "AE3 lease heartbeat error: zone_id=%s owner=%s error_type=%s",
                zone_id,
                owner,
                type(exc).__name__,
                exc_info=True,
            )
            consecutive_failures += 1
            LEASE_HEARTBEAT_FAILED.labels(zone_id=str(zone_id)).inc()
            if consecutive_failures < max_failures:
                continue

            await signal_lost(
                zone_id=zone_id,
                lease_lost_event=lease_lost_event,
                consecutive_failures=consecutive_failures,
            )
            break
