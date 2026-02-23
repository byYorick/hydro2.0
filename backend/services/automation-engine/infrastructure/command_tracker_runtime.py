"""Runtime LISTEN/poll/restore helpers for CommandTracker."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import asyncpg

from common.env import get_settings


def on_command_status_notify_impl(tracker: Any, payload: str) -> None:
    try:
        tracker._notify_queue.put_nowait(payload)
    except asyncio.QueueFull:
        tracker._logger.warning("Command status notify queue is full, fallback polling will reconcile state")


async def handle_notify_payload_impl(tracker: Any, payload: str) -> None:
    try:
        event = json.loads(payload) if payload else {}
    except Exception:
        tracker._logger.debug("Failed to decode ae_command_status payload: %s", payload)
        return

    if not isinstance(event, dict):
        return

    cmd_id = str(event.get("cmd_id") or "").strip()
    status = str(event.get("status") or "").strip().upper()
    if not cmd_id or not status:
        return
    if cmd_id not in tracker.pending_commands:
        return
    if status not in {"DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"}:
        return

    error = None
    if status in {"ERROR", "INVALID", "BUSY", "TIMEOUT", "SEND_FAILED"}:
        error = f"Command {status}"
    await tracker._confirm_command_internal(cmd_id, status, error=error)


async def close_notify_connection_impl(tracker: Any) -> None:
    conn = tracker._notify_conn
    if conn is None:
        return
    tracker._notify_conn = None
    try:
        await conn.remove_listener("ae_command_status", tracker._on_command_status_notify)
    except Exception:
        pass
    try:
        await conn.close()
    except Exception:
        pass


async def listen_command_statuses_impl(tracker: Any) -> None:
    settings = get_settings()
    dsn = (
        f"postgresql://{settings.pg_user}:{settings.pg_pass}@"
        f"{settings.pg_host}:{settings.pg_port}/{settings.pg_db}"
    )

    while not tracker._shutdown_event.is_set():
        try:
            if tracker._notify_conn is None or tracker._notify_conn.is_closed():
                tracker._notify_conn = await asyncpg.connect(dsn=dsn)
                await tracker._notify_conn.add_listener("ae_command_status", tracker._on_command_status_notify)
                tracker._logger.info("Started LISTEN ae_command_status for command tracker")

            payload = await asyncio.wait_for(
                tracker._notify_queue.get(),
                timeout=max(1.0, float(tracker.poll_interval)),
            )
            await tracker._handle_notify_payload(payload)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break
        except Exception as exc:
            tracker._logger.warning("Command status LISTEN loop error: %s", exc, exc_info=True)
            await tracker._close_notify_connection()
            await asyncio.sleep(max(1, tracker.poll_interval))
        finally:
            if tracker._shutdown_event.is_set() and tracker._notify_conn is not None:
                await tracker._close_notify_connection()


async def poll_command_statuses_impl(tracker: Any) -> None:
    while not tracker._shutdown_event.is_set():
        try:
            await asyncio.sleep(tracker.poll_interval)

            if not tracker.pending_commands:
                continue

            cmd_ids = list(tracker.pending_commands.keys())
            if not cmd_ids:
                continue

            try:
                rows = await tracker._fetch_rows(
                    """
                    SELECT cmd_id, status, ack_at, failed_at, error_message
                    FROM commands
                    WHERE cmd_id = ANY($1::text[])
                    AND status IN ('DONE', 'ERROR', 'INVALID', 'BUSY', 'NO_EFFECT', 'TIMEOUT', 'SEND_FAILED')
                    """,
                    cmd_ids,
                )

                for row in rows:
                    cmd_id = row["cmd_id"]
                    status = row["status"]
                    if cmd_id in tracker.pending_commands:
                        error = None
                        if status in ("ERROR", "INVALID", "BUSY", "TIMEOUT", "SEND_FAILED"):
                            error = row.get("error_message") or f"Command {status}"
                        await tracker._confirm_command_internal(cmd_id, status, error=error)
            except Exception as exc:
                tracker._logger.warning("Error polling command statuses from DB: %s", exc, exc_info=True)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            tracker._logger.error("Error in command status polling loop: %s", exc, exc_info=True)
            await asyncio.sleep(tracker.poll_interval)


async def start_polling_impl(tracker: Any) -> None:
    tracker._shutdown_event.clear()

    if tracker._poll_task is None or tracker._poll_task.done():
        tracker._poll_task = asyncio.create_task(tracker._poll_command_statuses())
        tracker._logger.info("Started command status polling (interval: %ss)", tracker.poll_interval)
    if tracker._notify_task is None or tracker._notify_task.done():
        tracker._notify_task = asyncio.create_task(tracker._listen_command_statuses())
        tracker._logger.info("Started command status LISTEN task")


async def stop_polling_impl(tracker: Any) -> None:
    tracker._shutdown_event.set()
    if tracker._poll_task and not tracker._poll_task.done():
        tracker._poll_task.cancel()
        try:
            await tracker._poll_task
        except asyncio.CancelledError:
            pass
    if tracker._notify_task and not tracker._notify_task.done():
        tracker._notify_task.cancel()
        try:
            await tracker._notify_task
        except asyncio.CancelledError:
            pass
    await tracker._close_notify_connection()
    tracker._poll_task = None
    tracker._notify_task = None
    tracker._logger.info("Stopped command status polling/LISTEN")


async def restore_pending_commands_impl(tracker: Any) -> None:
    try:
        rows = await tracker._fetch_rows(
            """
            SELECT cmd_id, zone_id, cmd, params, status, sent_at, created_at
            FROM commands
            WHERE status IN ('QUEUED', 'SENT', 'ACK')
            AND (
                (sent_at IS NOT NULL AND sent_at > NOW() - ($1 * INTERVAL '1 second'))
                OR (sent_at IS NULL AND created_at > NOW() - ($2 * INTERVAL '1 second'))
            )
            ORDER BY created_at DESC, cmd_id DESC
            LIMIT 1000
            """,
            tracker.command_timeout,
            tracker.command_timeout,
        )

        restored_count = 0
        for row in rows:
            cmd_id = row["cmd_id"]
            zone_id = row["zone_id"]
            cmd = row["cmd"]
            params = row.get("params") or {}
            status = row["status"]
            sent_at = row.get("sent_at") or row.get("created_at")

            command_info = {
                "cmd_id": cmd_id,
                "zone_id": zone_id,
                "command": {"cmd": cmd, "params": params},
                "command_type": cmd,
                "sent_at": tracker._normalize_utc_datetime(sent_at),
                "status": status,
                "context": {},
            }

            tracker.pending_commands[cmd_id] = command_info
            tracker._metrics["PENDING_COMMANDS"].labels(zone_id=str(zone_id)).inc()

            timeout_task = asyncio.create_task(tracker._check_timeout(cmd_id))
            tracker._timeout_tasks[cmd_id] = timeout_task
            restored_count += 1

        if restored_count > 0:
            tracker._logger.info("Restored %s pending commands from DB after restart", restored_count)
        else:
            tracker._logger.debug("No pending commands to restore from DB")
    except Exception as exc:
        tracker._logger.warning("Failed to restore pending commands from DB: %s", exc, exc_info=True)


__all__ = [
    "close_notify_connection_impl",
    "handle_notify_payload_impl",
    "listen_command_statuses_impl",
    "on_command_status_notify_impl",
    "poll_command_statuses_impl",
    "restore_pending_commands_impl",
    "start_polling_impl",
    "stop_polling_impl",
]
