"""``handle_diagnostics`` + ``handle_error`` — делегируют в общий error_handler,
unassigned error-ы сохраняют в ``unassigned_node_errors`` для диагностики temp-топиков.
"""

from __future__ import annotations

import logging

from common.db import fetch, upsert_unassigned_node_error
from common.error_handler import get_error_handler
from common.trace_context import clear_trace_id
from metrics import DIAGNOSTICS_RECEIVED, ERROR_RECEIVED
from utils import _extract_gh_uid, _extract_node_uid, _extract_zone_uid, _parse_json

from ._shared import apply_trace_context

logger = logging.getLogger(__name__)


async def handle_diagnostics(topic: str, payload: bytes) -> None:
    """Метрики ошибок узла → общий error_handler component."""
    try:
        logger.info("[DIAGNOSTICS] ===== START processing diagnostics =====")
        logger.info(f"[DIAGNOSTICS] Topic: {topic}, payload length: {len(payload)}")

        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[DIAGNOSTICS] Invalid JSON in diagnostics from topic {topic}")
            return

        apply_trace_context(data)

        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[DIAGNOSTICS] Could not extract node_uid from topic {topic}")
            return

        logger.info(f"[DIAGNOSTICS] Processing diagnostics for node_uid: {node_uid}")

        error_handler = get_error_handler()
        await error_handler.handle_diagnostics(node_uid, data)

        DIAGNOSTICS_RECEIVED.labels(node_uid=node_uid).inc()
    finally:
        clear_trace_id()


async def handle_error(topic: str, payload: bytes) -> None:
    """Error от узла: temp-топики → ``unassigned_node_errors``, normal → общий error_handler."""
    try:
        logger.info("[ERROR] ===== START processing error =====")
        logger.info(f"[ERROR] Topic: {topic}, payload length: {len(payload)}")

        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[ERROR] Invalid JSON in error from topic {topic}")
            return

        apply_trace_context(data)

        gh_uid = _extract_gh_uid(topic)
        zone_uid = _extract_zone_uid(topic)
        is_temp_topic = gh_uid == "gh-temp" and zone_uid == "zn-temp"

        if is_temp_topic:
            await _save_unassigned_error_from_temp(topic, data)
            return

        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[ERROR] Could not extract node_uid from topic {topic}")
            return

        level = data.get("level", "ERROR")
        component = data.get("component", "unknown")
        error_code = data.get("error_code", "unknown")

        logger.info(
            "[ERROR] Processing error for node_uid: %s, level: %s, component: %s, error_code: %s",
            node_uid,
            level,
            component,
            error_code,
        )

        try:
            node_rows = await fetch(
                """
                SELECT n.id, n.hardware_id, n.zone_id
                FROM nodes n
                WHERE n.uid = $1
                """,
                node_uid,
            )

            if not node_rows:
                await _save_unassigned_error_node_not_found(
                    node_uid=node_uid,
                    data=data,
                    error_code=error_code,
                    level=level,
                    topic=topic,
                )
                return

            node = node_rows[0]
            zone_id = node.get("zone_id")

            if not zone_id:
                await _save_unassigned_error_no_zone(
                    node=node,
                    node_uid=node_uid,
                    data=data,
                    error_code=error_code,
                    level=level,
                    topic=topic,
                )
                return

            error_handler = get_error_handler()
            await error_handler.handle_error(node_uid, data)

        except Exception as e:
            logger.error(f"[ERROR] Error checking node in DB: {e}", exc_info=True)
            error_handler = get_error_handler()
            await error_handler.handle_error(node_uid, data)

        ERROR_RECEIVED.labels(node_uid=node_uid, level=level.lower()).inc()
    finally:
        clear_trace_id()


async def _save_unassigned_error_from_temp(topic: str, data: dict) -> None:
    hardware_id = _extract_node_uid(topic)
    if not hardware_id:
        logger.warning(f"[ERROR] Could not extract hardware_id from temp topic {topic}")
        return

    level = data.get("level", "ERROR")
    component = data.get("component", "unknown")
    error_code = data.get("error_code")
    error_message = data.get("message", data.get("error", "Unknown error"))

    logger.info(
        "[ERROR] Processing error for unassigned node (hardware_id: %s), level: %s, component: %s, error_code: %s",
        hardware_id,
        level,
        component,
        error_code,
    )

    try:
        await upsert_unassigned_node_error(
            hardware_id=hardware_id,
            error_message=error_message,
            error_code=error_code,
            severity=level,
            topic=topic,
            last_payload=data,
        )
        logger.info(f"[ERROR] Saved error for unassigned node hardware_id={hardware_id}")
    except Exception as e:
        logger.error(f"[ERROR] Failed to save unassigned node error: {e}", exc_info=True)

    ERROR_RECEIVED.labels(node_uid=f"unassigned-{hardware_id}", level=level.lower()).inc()


async def _save_unassigned_error_node_not_found(
    *, node_uid: str, data: dict, error_code: str, level: str, topic: str
) -> None:
    hardware_id_from_topic = node_uid
    hardware_id_from_payload = data.get("hardware_id")
    hardware_id = hardware_id_from_payload or hardware_id_from_topic
    error_message = data.get("message", data.get("error", "Unknown error"))

    logger.info(
        "[ERROR] Node not found in DB, saving to unassigned errors: node_uid=%s, hardware_id=%s",
        node_uid,
        hardware_id,
    )

    try:
        await upsert_unassigned_node_error(
            hardware_id=hardware_id,
            error_message=error_message,
            error_code=error_code,
            severity=level,
            topic=topic,
            last_payload=data,
        )
        logger.info(f"[ERROR] Saved error for unassigned node hardware_id={hardware_id}")
    except Exception as e:
        logger.error(f"[ERROR] Failed to save unassigned node error: {e}", exc_info=True)

    ERROR_RECEIVED.labels(node_uid=f"unassigned-{hardware_id}", level=level.lower()).inc()


async def _save_unassigned_error_no_zone(
    *, node: dict, node_uid: str, data: dict, error_code: str, level: str, topic: str
) -> None:
    hardware_id = node.get("hardware_id")
    if not hardware_id:
        return

    error_message = data.get("message", data.get("error", "Unknown error"))
    logger.info(
        "[ERROR] Node not assigned to zone, saving to unassigned errors: node_uid=%s, hardware_id=%s, node_id=%s",
        node_uid,
        hardware_id,
        node["id"],
    )
    try:
        await upsert_unassigned_node_error(
            hardware_id=hardware_id,
            error_message=error_message,
            error_code=error_code,
            severity=level,
            topic=topic,
            last_payload=data,
        )
        logger.info(f"[ERROR] Saved error for unassigned node hardware_id={hardware_id}")
    except Exception as e:
        logger.error(f"[ERROR] Failed to save unassigned node error: {e}", exc_info=True)
    ERROR_RECEIVED.labels(node_uid=f"unassigned-{hardware_id}", level=level.lower()).inc()
