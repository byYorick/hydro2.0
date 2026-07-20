"""Drain stale QUEUED/SEND_FAILED commands after HL restart or transient outage."""

from __future__ import annotations

import logging
import zlib
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from command_service import (
    NodeSecretResolutionError,
    _create_command_payload,
    _get_gh_uid_from_zone_id,
    _get_zone_uid_from_id,
    _resolve_node_secret,
)
from commands.lifecycle import ensure_command_for_publish
from commands.publisher import publish_command_with_retry
from common.commands import _affected_rows
from common.db import execute, get_pool
from metrics import (
    COMMAND_QUEUE_DRAIN_FAILED,
    COMMAND_QUEUE_DRAIN_SCANNED,
    COMMAND_QUEUE_DRAIN_SKIPPED,
    COMMAND_QUEUE_DRAIN_SUCCEEDED,
)

logger = logging.getLogger(__name__)

_SUSTAINED_FAIL_CYCLES_BEFORE_ALERT = 3
_consecutive_fail_cycles = 0

# Namespace for per-cmd_id session advisory locks during MQTT republish.
# Keeps concurrent drain workers from double-publishing the same row after
# FOR UPDATE is released (previous bug: SKIP LOCKED ended with the SELECT txn).
_DRAIN_PUBLISH_LOCK_NAMESPACE = zlib.crc32(b"hl_queued_cmd_drain_publish") & 0x7FFFFFFF


def _cmd_publish_advisory_lock_key(cmd_id: str) -> int:
    """Stable 63-bit key: namespace in high 31 bits + crc32(cmd_id) in low 32."""
    cmd_hash = zlib.crc32(cmd_id.encode("utf-8")) & 0xFFFFFFFF
    return (_DRAIN_PUBLISH_LOCK_NAMESPACE << 32) | cmd_hash


def _extract_signed_payload_fields(params: dict[str, Any]) -> tuple[dict[str, Any], int | None, str | None]:
    """Preserve ``__hl_ts`` / ``__hl_sig`` metadata without leaking them to MQTT params."""
    if not isinstance(params, dict):
        return {}, None, None
    clean_params = dict(params)
    stored_ts = clean_params.pop("__hl_ts", None)
    stored_sig = clean_params.pop("__hl_sig", None)
    ts_value = int(stored_ts) if isinstance(stored_ts, (int, float)) else None
    sig_value = str(stored_sig) if isinstance(stored_sig, str) and stored_sig else None
    return clean_params, ts_value, sig_value


async def _abandon_non_republishable_command(
    *,
    cmd_id: str | None,
    reason: str,
    zone_id: int | None = None,
    node_uid: str | None = None,
    channel: str | None = None,
    cmd_name: str | None = None,
) -> bool:
    """Mark QUEUED/SEND_FAILED rows that can never be republished as INVALID.

    Returns True when the row left the drain set (so the cycle counts as skip).
    """
    if not cmd_id:
        logger.warning(
            "[QUEUED_DRAIN] cannot abandon row without cmd_id reason=%s zone_id=%s node_uid=%s",
            reason,
            zone_id,
            node_uid,
        )
        return False

    try:
        result = await execute(
            """
            UPDATE commands
            SET status = 'INVALID',
                failed_at = NOW(),
                error_code = 'DRAIN_ABANDON',
                error_message = $2,
                result_code = 1,
                updated_at = NOW()
            WHERE cmd_id = $1
              AND status IN ('QUEUED', 'SEND_FAILED')
            """,
            cmd_id,
            reason,
        )
        abandoned = _affected_rows(result) > 0

        logger.warning(
            "[QUEUED_DRAIN] abandoned non-republishable cmd_id=%s reason=%s "
            "zone_id=%s node_uid=%s channel=%s cmd=%s abandoned=%s",
            cmd_id,
            reason,
            zone_id,
            node_uid,
            channel,
            cmd_name,
            abandoned,
        )
        return abandoned
    except Exception:
        logger.warning(
            "[QUEUED_DRAIN] failed to abandon cmd_id=%s reason=%s",
            cmd_id,
            reason,
            exc_info=True,
        )
        return False


async def _claim_stale_queued_command_rows(
    *,
    stale_after_seconds: float,
    limit: int,
) -> list[dict[str, Any]]:
    """List drain candidates without row locks.

    Publish exclusivity is enforced per cmd_id via session advisory lock held
    for the full MQTT republish window (see ``_try_claim_cmd_for_publish``).
    The name ``_claim_*`` is historical; row-level FOR UPDATE is intentionally
    not used here because it would release before MQTT PUBACK.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.cmd_id,
                c.zone_id,
                c.node_id,
                c.channel,
                c.cmd,
                c.params,
                c.status,
                c.source,
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


@asynccontextmanager
async def _try_claim_cmd_for_publish(cmd_id: str) -> AsyncIterator[bool]:
    """Hold a session advisory lock on ``cmd_id`` for the publish window.

    Yields True only when the lock was acquired AND the row is still in
    QUEUED/SEND_FAILED. Connection stays checked out until exit so the
    session lock survives MQTT I/O (unlike FOR UPDATE SKIP LOCKED alone).
    """
    lock_key = _cmd_publish_advisory_lock_key(cmd_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        acquired = bool(
            await conn.fetchval("SELECT pg_try_advisory_lock($1::bigint)", int(lock_key))
        )
        if not acquired:
            yield False
            return
        try:
            still_pending = await conn.fetchval(
                """
                SELECT 1
                FROM commands
                WHERE cmd_id = $1
                  AND status IN ('QUEUED', 'SEND_FAILED')
                """,
                cmd_id,
            )
            yield still_pending is not None
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1::bigint)", int(lock_key))


async def drain_stale_queued_commands_once(
    *,
    stale_after_seconds: float = 15.0,
    limit: int = 25,
) -> dict[str, int]:
    """Republish commands, застрявшие в QUEUED/SEND_FAILED после сбоя publish."""
    candidates = await _claim_stale_queued_command_rows(
        stale_after_seconds=stale_after_seconds,
        limit=limit,
    )
    summary = {
        "scanned": len(candidates),
        "drained": 0,
        "skipped": 0,
        "failed": 0,
    }

    if summary["scanned"] > 0:
        COMMAND_QUEUE_DRAIN_SCANNED.inc(summary["scanned"])

    for row in candidates:
        cmd_id = str(row.get("cmd_id") or "").strip()
        zone_id = int(row.get("zone_id") or 0)
        node_id = int(row.get("node_id") or 0)
        node_uid = str(row.get("node_uid") or "").strip()
        channel = str(row.get("channel") or "").strip()
        cmd_name = str(row.get("cmd") or "").strip()
        raw_params = row.get("params") if isinstance(row.get("params"), dict) else {}
        command_source = str(row.get("source") or "api").strip() or "api"

        if not cmd_id or zone_id <= 0 or node_id <= 0 or not node_uid or not channel or not cmd_name:
            # Permanently non-republishable row (e.g. SEND_FAILED reset_binding with
            # zone_id=NULL after sim unbind). Leave the drain queue as INVALID so
            # sustained-fail alerts are not re-fired every cycle.
            abandoned = await _abandon_non_republishable_command(
                cmd_id=cmd_id or None,
                reason="missing_required_publish_fields",
                zone_id=zone_id if zone_id > 0 else None,
                node_uid=node_uid or None,
                channel=channel or None,
                cmd_name=cmd_name or None,
            )
            if abandoned:
                summary["skipped"] += 1
                COMMAND_QUEUE_DRAIN_SKIPPED.inc()
            else:
                summary["failed"] += 1
                COMMAND_QUEUE_DRAIN_FAILED.inc()
            continue

        async with _try_claim_cmd_for_publish(cmd_id) as claimed:
            if not claimed:
                # Another drain worker holds the publish lease, or status left
                # the drain set between SELECT and claim.
                summary["skipped"] += 1
                COMMAND_QUEUE_DRAIN_SKIPPED.inc()
                logger.info(
                    "[QUEUED_DRAIN] skipped cmd_id=%s zone_id=%s reason=publish_claim_busy",
                    cmd_id,
                    zone_id,
                )
                continue

            try:
                skip_response = await ensure_command_for_publish(
                    cmd_id=cmd_id,
                    zone_id=zone_id,
                    node_id=node_id,
                    node_uid=node_uid,
                    channel=channel,
                    cmd_name=cmd_name,
                    params=raw_params,
                    command_source=command_source,
                )
                if skip_response:
                    summary["skipped"] += 1
                    COMMAND_QUEUE_DRAIN_SKIPPED.inc()
                    logger.info(
                        "[QUEUED_DRAIN] skipped cmd_id=%s zone_id=%s reason=non_republishable",
                        cmd_id,
                        zone_id,
                    )
                    continue

                effective_gh_uid = await _get_gh_uid_from_zone_id(zone_id)
                zone_uid = await _get_zone_uid_from_id(zone_id)
                params, stored_ts, stored_sig = _extract_signed_payload_fields(raw_params)
                try:
                    secret = await _resolve_node_secret(
                        node_uid=node_uid,
                        node_id=node_id,
                        zone_id=zone_id,
                    )
                except NodeSecretResolutionError as exc:
                    # Permanent: node left the command's zone (rebind TOCTOU).
                    # Transient missing-secret / DB errors stay QUEUED for retry.
                    if "not assigned to zone" not in str(exc):
                        raise
                    abandoned = await _abandon_non_republishable_command(
                        cmd_id=cmd_id,
                        reason=f"secret_or_zone_mismatch:{exc}",
                        zone_id=zone_id,
                        node_uid=node_uid,
                        channel=channel,
                        cmd_name=cmd_name,
                    )
                    if abandoned:
                        summary["skipped"] += 1
                        COMMAND_QUEUE_DRAIN_SKIPPED.inc()
                    else:
                        summary["failed"] += 1
                        COMMAND_QUEUE_DRAIN_FAILED.inc()
                    continue

                payload = _create_command_payload(
                    node_uid=node_uid,
                    secret=secret,
                    cmd_id=cmd_id,
                    params=params,
                    cmd=cmd_name,
                    ts=stored_ts,
                    sig=stored_sig,
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
                COMMAND_QUEUE_DRAIN_SUCCEEDED.inc()
                logger.info(
                    "[QUEUED_DRAIN] republished cmd_id=%s zone_id=%s node_uid=%s",
                    cmd_id,
                    zone_id,
                    node_uid,
                )
            except Exception:
                summary["failed"] += 1
                COMMAND_QUEUE_DRAIN_FAILED.inc()
                logger.warning(
                    "[QUEUED_DRAIN] failed cmd_id=%s zone_id=%s node_uid=%s",
                    cmd_id,
                    zone_id,
                    node_uid,
                    exc_info=True,
                )

    return summary


async def _maybe_emit_sustained_drain_fail_alert(summary: dict[str, int]) -> None:
    global _consecutive_fail_cycles

    if (
        summary.get("scanned", 0) > 0
        and summary.get("drained", 0) == 0
        and summary.get("failed", 0) > 0
    ):
        _consecutive_fail_cycles += 1
    else:
        _consecutive_fail_cycles = 0

    if _consecutive_fail_cycles < _SUSTAINED_FAIL_CYCLES_BEFORE_ALERT:
        return

    try:
        from commands.alerts import emit_command_queue_drain_sustained_fail_alert

        await emit_command_queue_drain_sustained_fail_alert(
            consecutive_cycles=_consecutive_fail_cycles,
            last_summary=summary,
        )
        _consecutive_fail_cycles = 0
    except Exception:
        logger.warning(
            "[QUEUED_DRAIN] failed to emit sustained-fail alert summary=%s",
            summary,
            exc_info=True,
        )


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
            await _maybe_emit_sustained_drain_fail_alert(summary)
            if summary["drained"] > 0 or summary["failed"] > 0 or summary["skipped"] > 0:
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
