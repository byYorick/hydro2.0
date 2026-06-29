"""Drain stale QUEUED/SEND_FAILED commands after HL restart or transient outage."""

from __future__ import annotations

import logging
from typing import Any

from command_service import _create_command_payload, _get_gh_uid_from_zone_id, _get_zone_uid_from_id
from commands.publisher import publish_command_with_retry
from common.db import fetch

logger = logging.getLogger(__name__)


async def _fetch_stale_queued_command_rows(
    *,
    stale_after_seconds: float,
    limit: int,
) -> list[dict[str, Any]]:
    rows = await fetch(
        """
        SELECT
            c.cmd_id,
            c.zone_id,
            c.channel,
            c.cmd,
            c.params,
            c.status,
            n.uid AS node_uid
        FROM commands c
        INNER JOIN nodes n ON n.id = c.node_id
        WHERE c.status IN ('QUEUED', 'SEND_FAILED')
          AND c.created_at <= NOW() - ($1 * INTERVAL '1 second')
        ORDER BY c.created_at ASC, c.id ASC
        LIMIT $2
        """,
        stale_after_seconds,
        limit,
    )
    return [dict(row) for row in rows]


async def drain_stale_queued_commands_once(
    *,
    stale_after_seconds: float = 15.0,
    limit: int = 25,
) -> dict[str, int]:
    """Republish commands, застрявшие в QUEUED/SEND_FAILED после сбоя publish."""
    candidates = await _fetch_stale_queued_command_rows(
        stale_after_seconds=stale_after_seconds,
        limit=limit,
    )
    summary = {
        "scanned": len(candidates),
        "drained": 0,
        "failed": 0,
    }

    for row in candidates:
        cmd_id = str(row.get("cmd_id") or "").strip()
        zone_id = int(row.get("zone_id") or 0)
        node_uid = str(row.get("node_uid") or "").strip()
        channel = str(row.get("channel") or "").strip()
        cmd_name = str(row.get("cmd") or "").strip()
        params = row.get("params") if isinstance(row.get("params"), dict) else {}

        if not cmd_id or zone_id <= 0 or not node_uid or not channel or not cmd_name:
            summary["failed"] += 1
            continue

        try:
            effective_gh_uid = await _get_gh_uid_from_zone_id(zone_id)
            zone_uid = await _get_zone_uid_from_id(zone_id)
            payload = _create_command_payload(
                cmd_id=cmd_id,
                params=params,
                cmd=cmd_name,
            )
            await publish_command_with_retry(
                payload=payload,
                cmd_id=cmd_id,
                cmd_name=cmd_name,
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                effective_gh_uid=effective_gh_uid,
                zone_uid=zone_uid,
            )
            summary["drained"] += 1
            logger.info(
                "[QUEUED_DRAIN] republished cmd_id=%s zone_id=%s node_uid=%s",
                cmd_id,
                zone_id,
                node_uid,
            )
        except Exception:
            summary["failed"] += 1
            logger.warning(
                "[QUEUED_DRAIN] failed cmd_id=%s zone_id=%s node_uid=%s",
                cmd_id,
                zone_id,
                node_uid,
                exc_info=True,
            )

    return summary


async def drain_worker(
    *,
    interval: float = 20.0,
    stale_after_seconds: float = 15.0,
    batch_size: int = 25,
    shutdown_event: Any | None = None,
) -> None:
    import asyncio

    logger.info(
        "Starting queued command drain worker: interval=%s stale_after_seconds=%s batch_size=%s",
        interval,
        stale_after_seconds,
        batch_size,
    )
    while True:
        if shutdown_event is not None and shutdown_event.is_set():
            break
        try:
            summary = await drain_stale_queued_commands_once(
                stale_after_seconds=stale_after_seconds,
                limit=batch_size,
            )
            if summary["drained"] > 0 or summary["failed"] > 0:
                logger.info("[QUEUED_DRAIN] cycle summary=%s", summary)
        except Exception:
            logger.warning("[QUEUED_DRAIN] worker cycle failed", exc_info=True)

        if shutdown_event is not None:
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                continue
        else:
            await asyncio.sleep(interval)
