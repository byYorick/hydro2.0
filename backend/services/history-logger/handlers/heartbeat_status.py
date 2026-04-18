"""Heartbeat / status / LWT handlers + offline node monitor."""

from __future__ import annotations

import asyncio
import logging

import state
from common.db import execute, fetch
from common.env import get_settings
from common.trace_context import clear_trace_id
from metrics import HEARTBEAT_RECEIVED, STATUS_RECEIVED
from utils import _extract_gh_uid, _extract_node_uid, _extract_zone_uid, _parse_json

from ._shared import apply_trace_context

logger = logging.getLogger(__name__)


async def handle_heartbeat(topic: str, payload: bytes) -> None:
    """Обновляет ``nodes`` на heartbeat: uptime / free_heap / rssi / last_seen."""
    try:
        logger.info("[HEARTBEAT] ===== START processing heartbeat =====")
        logger.info(f"[HEARTBEAT] Topic: {topic}, payload length: {len(payload)}")

        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[HEARTBEAT] Invalid JSON in heartbeat from topic {topic}")
            return

        apply_trace_context(data)

        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[HEARTBEAT] Could not extract node_uid from topic {topic}")
            return

        gh_uid = _extract_gh_uid(topic)
        zone_uid = _extract_zone_uid(topic)
        is_temp_topic = gh_uid == "gh-temp" and zone_uid == "zn-temp"

        logger.info(
            f"[HEARTBEAT] Extracted gh_uid='{gh_uid}', zone_uid='{zone_uid}', is_temp_topic={is_temp_topic}, topic='{topic}'"
        )

        if is_temp_topic:
            # Для temp топиков ``node_uid`` на самом деле hardware_id
            hardware_id = node_uid
            logger.info(
                f"[HEARTBEAT] Processing heartbeat for temp topic, hardware_id: {hardware_id}, data: {data}"
            )
            node_rows = await fetch(
                "SELECT uid FROM nodes WHERE hardware_id = $1",
                hardware_id,
            )
            if not node_rows:
                logger.debug(
                    "[HEARTBEAT] Temp heartbeat buffered by registration flow: hardware_id=%s",
                    hardware_id,
                )
                return
            node_uid = node_rows[0]["uid"]
            logger.info(f"[HEARTBEAT] Found node_uid: {node_uid} for hardware_id: {hardware_id}")
        else:
            logger.info(f"[HEARTBEAT] Processing heartbeat for node_uid: {node_uid}, data: {data}")

        uptime = data.get("uptime")
        free_heap = data.get("free_heap") or data.get("free_heap_bytes")
        rssi = data.get("rssi")

        updates: list[str] = []
        params: list = [node_uid]
        param_index = 1

        if uptime is not None:
            try:
                uptime_seconds = int(float(uptime))
                updates.append(f"uptime_seconds=${param_index + 1}")
                params.append(uptime_seconds)
                param_index += 1
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Invalid uptime value: %s",
                    uptime,
                    extra={"error": str(e), "node_uid": node_uid},
                )

        if free_heap is not None:
            try:
                free_heap_int = int(free_heap)
                updates.append(f"free_heap_bytes=${param_index + 1}")
                params.append(free_heap_int)
                param_index += 1
            except (ValueError, TypeError):
                logger.warning(f"Invalid free_heap value: {free_heap}")

        if rssi is not None:
            try:
                rssi_int = int(rssi)
                updates.append(f"rssi=${param_index + 1}")
                params.append(rssi_int)
                param_index += 1
            except (ValueError, TypeError):
                logger.warning(f"Invalid rssi value: {rssi}")

        updates.append("last_heartbeat_at=NOW()")
        updates.append("updated_at=NOW()")
        updates.append("last_seen_at=NOW()")
        updates.append("status='online'")

        if len(updates) > 4:
            query = "UPDATE nodes SET " + ", ".join(updates) + " WHERE uid=$1"
            await execute(query, *params)
        else:
            await execute(
                "UPDATE nodes SET last_heartbeat_at=NOW(), updated_at=NOW(), last_seen_at=NOW(), status='online' WHERE uid=$1",
                node_uid,
            )

        HEARTBEAT_RECEIVED.labels(node_uid=node_uid).inc()

        logged_uptime = None
        if uptime is not None:
            try:
                logged_uptime = int(float(uptime))
            except (ValueError, TypeError):
                logged_uptime = uptime

        logger.info(
            "[HEARTBEAT] Node heartbeat processed successfully: node_uid=%s, uptime_seconds=%s, free_heap=%s, rssi=%s",
            node_uid,
            logged_uptime,
            free_heap,
            rssi,
        )
    finally:
        clear_trace_id()


async def handle_status(topic: str, payload: bytes) -> None:
    """Помечает ноду ONLINE/OFFLINE на основании ``status`` в payload."""
    try:
        logger.info("[STATUS] ===== START processing status =====")
        logger.info(f"[STATUS] Topic: {topic}, payload length: {len(payload)}")

        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[STATUS] Invalid JSON in status from topic {topic}")
            return

        apply_trace_context(data)

        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[STATUS] Could not extract node_uid from topic {topic}")
            return

        status = data.get("status", "").upper()

        logger.info("[STATUS] Processing status for node_uid: %s, status: %s", node_uid, status)

        if status == "ONLINE":
            await execute(
                "UPDATE nodes SET status='online', last_seen_at=NOW(), updated_at=NOW() WHERE uid=$1",
                node_uid,
            )
            logger.info(f"[STATUS] Node {node_uid} marked as ONLINE")
        elif status == "OFFLINE":
            await execute(
                "UPDATE nodes SET status='offline', updated_at=NOW() WHERE uid=$1",
                node_uid,
            )
            logger.info(f"[STATUS] Node {node_uid} marked as OFFLINE")
        else:
            logger.warning(f"[STATUS] Unknown status value: {status} for node {node_uid}")

        STATUS_RECEIVED.labels(node_uid=node_uid, status=status.lower()).inc()
    finally:
        clear_trace_id()


async def handle_lwt(topic: str, payload: bytes) -> None:
    """LWT от узла: строка ``offline`` при потере связи (MQTT broker-driven)."""
    try:
        logger.info("[LWT] ===== START processing LWT =====")
        logger.info(f"[LWT] Topic: {topic}, payload length: {len(payload)}")

        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[LWT] Could not extract node_uid from topic {topic}")
            return

        raw_payload = payload.decode("utf-8", errors="ignore").strip()
        status = raw_payload.upper()
        if not status:
            data = _parse_json(payload)
            if isinstance(data, dict):
                apply_trace_context(data)
                status = str(data.get("status", "")).upper()

        if status not in ("OFFLINE", "ONLINE"):
            status = "OFFLINE"

        if status == "ONLINE":
            await execute(
                "UPDATE nodes SET status='online', last_seen_at=NOW(), updated_at=NOW() WHERE uid=$1",
                node_uid,
            )
            logger.info(f"[LWT] Node {node_uid} marked as ONLINE (unexpected LWT payload)")
        else:
            await execute(
                "UPDATE nodes SET status='offline', updated_at=NOW() WHERE uid=$1",
                node_uid,
            )
            logger.info(f"[LWT] Node {node_uid} marked as OFFLINE")

        STATUS_RECEIVED.labels(node_uid=node_uid, status=status.lower()).inc()
    finally:
        clear_trace_id()


async def monitor_offline_nodes() -> None:
    """Periodically помечает узлы ``offline`` при stale ``last_seen_at``."""
    s = get_settings()
    timeout_sec = max(1, s.node_offline_timeout_sec)
    interval_sec = max(1, s.node_offline_check_interval_sec)

    logger.info(f"[OFFLINE_MONITOR] Started (timeout={timeout_sec}s, interval={interval_sec}s)")

    while not state.shutdown_event.is_set():
        try:
            result = await execute(
                """
                UPDATE nodes
                SET status='offline', updated_at=NOW()
                WHERE status='online'
                  AND COALESCE(last_seen_at, last_heartbeat_at, updated_at, created_at)
                      < NOW() - ($1 * interval '1 second')
                """,
                timeout_sec,
            )
            if isinstance(result, str) and result.startswith("UPDATE"):
                try:
                    updated = int(result.split()[-1])
                except (ValueError, IndexError):
                    updated = 0
                if updated > 0:
                    logger.warning(f"[OFFLINE_MONITOR] Marked offline: {updated}")
        except Exception as exc:
            logger.error(f"[OFFLINE_MONITOR] Failed to update offline nodes: {exc}")

        try:
            await asyncio.wait_for(state.shutdown_event.wait(), timeout=interval_sec)
        except asyncio.TimeoutError:
            continue
