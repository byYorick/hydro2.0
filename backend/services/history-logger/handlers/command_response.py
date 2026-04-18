"""``handle_command_response``: ACK/DONE/ERROR от узла → commands table + Laravel correlation."""

from __future__ import annotations

import logging

from common.command_status_queue import deliver_status_to_laravel, normalize_status
from common.db import create_zone_event, execute, fetch
from common.simulation_events import record_simulation_event
from common.trace_context import clear_trace_id
from metrics import COMMAND_RESPONSE_ERROR, COMMAND_RESPONSE_RECEIVED
from utils import _extract_channel_from_topic, _extract_gh_uid, _extract_node_uid, _parse_json

from ._shared import (
    IRR_STATE_SNAPSHOT_EVENT_TYPE,
    apply_trace_context,
    normalize_command_response_details,
    normalize_irr_state_snapshot,
    resolve_stub_insert_status,
)

logger = logging.getLogger(__name__)


async def handle_command_response(topic: str, payload: bytes) -> None:
    """Обновляет статус команды через Laravel API с надёжной доставкой (queue on failure)."""
    try:
        logger.info(
            f"[COMMAND_RESPONSE] STEP 0: Received message on topic {topic}, payload length: {len(payload)}"
        )
        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(
                f"[COMMAND_RESPONSE] STEP 0.1: Invalid JSON in command_response from topic {topic}"
            )
            COMMAND_RESPONSE_ERROR.inc()
            return

        apply_trace_context(data, fallback_keys=("trace_id", "cmd_id", "cmdId"))

        cmd_id = data.get("cmd_id")
        raw_status = data.get("status", "")
        response_ts = data.get("ts")

        logger.info(
            "[COMMAND_RESPONSE] STEP 0.2: Parsed command_response: cmd_id=%s, status=%s, ts=%s, topic=%s",
            cmd_id,
            raw_status,
            response_ts,
            topic,
        )
        node_uid = _extract_node_uid(topic)
        channel = _extract_channel_from_topic(topic)
        gh_uid = _extract_gh_uid(topic)

        if (
            not cmd_id
            or not raw_status
            or not isinstance(response_ts, int)
            or response_ts < 0
        ):
            logger.warning(
                "[COMMAND_RESPONSE] Missing or invalid required fields in payload: cmd_id=%s status=%s ts=%s payload=%s",
                cmd_id,
                raw_status,
                response_ts,
                data,
            )
            COMMAND_RESPONSE_ERROR.inc()
            return

        normalized_status = normalize_status(raw_status)
        if not normalized_status:
            logger.warning(
                "[COMMAND_RESPONSE] Unknown status '%s' for cmd_id=%s, node_uid=%s, channel=%s",
                raw_status,
                cmd_id,
                node_uid,
                channel,
            )
            COMMAND_RESPONSE_ERROR.inc()
            return

        COMMAND_RESPONSE_RECEIVED.inc()

        zone_id, cmd_name, existing_status = await _ensure_command_row_for_response(
            cmd_id=cmd_id,
            node_uid=node_uid,
            channel=channel,
            normalized_status=normalized_status,
        )
        # Если duplicate terminal response — метод выше сам выйдет; здесь проверяем признак
        # (функция возвращает zone_id=None при дубликате terminal, но cmd_name=None не означает drop)
        if zone_id == "__DEDUP__":  # sentinel: duplicate terminal status
            return

        try:
            details = normalize_command_response_details(data.get("details"))
        except ValueError:
            logger.warning(
                "[COMMAND_RESPONSE] Invalid details type for cmd_id=%s: %s",
                cmd_id,
                type(data.get("details")).__name__,
            )
            COMMAND_RESPONSE_ERROR.inc()
            return

        if "error_code" in data and data.get("error_code") is not None:
            details["error_code"] = data.get("error_code")
        if "error_message" in data and data.get("error_message") is not None:
            details["error_message"] = data.get("error_message")
        elif "message" in data and data.get("message") is not None:
            details["error_message"] = data.get("message")
        elif "error" in data and data.get("error") is not None:
            details["error_message"] = data.get("error")
        details.update(
            {
                "raw_status": str(raw_status),
                "response_ts": response_ts,
                "node_uid": node_uid,
                "channel": channel,
                "gh_uid": gh_uid,
                "zone_id": zone_id,
            }
        )
        details = {k: v for k, v in details.items() if v is not None}

        delivery_result = await deliver_status_to_laravel(cmd_id, normalized_status, details)
        _log_delivery_result(
            delivery_result=delivery_result,
            cmd_id=cmd_id,
            normalized_status=normalized_status,
            node_uid=node_uid,
            channel=channel,
            existing_status=existing_status,
        )

        await _maybe_persist_irr_state_snapshot(
            zone_id=zone_id,
            cmd_name=cmd_name,
            channel=channel,
            cmd_id=cmd_id,
            node_uid=node_uid,
            response_ts=response_ts,
            details=details,
        )

        if zone_id:
            await _record_simulation_event_for_response(
                zone_id=zone_id,
                cmd_id=cmd_id,
                cmd_name=cmd_name,
                channel=channel,
                node_uid=node_uid,
                raw_status=raw_status,
                normalized_status=normalized_status,
                delivery_result=delivery_result,
            )

    except Exception as e:
        logger.error(
            f"[COMMAND_RESPONSE] Unexpected error processing message: {e}",
            exc_info=True,
        )
        COMMAND_RESPONSE_ERROR.inc()
    finally:
        clear_trace_id()


async def _ensure_command_row_for_response(
    *,
    cmd_id: str,
    node_uid: str | None,
    channel: str | None,
    normalized_status,
):
    """Обеспечивает строку ``commands`` для cmd_id: insert stub если новая, detect terminal duplicates."""
    zone_id = None
    cmd_name = None
    existing_status = None
    try:
        existing_cmd = await fetch(
            "SELECT status, zone_id, cmd FROM commands WHERE cmd_id = $1", cmd_id
        )
        if not existing_cmd:
            node_id = None
            if node_uid:
                node_rows = await fetch(
                    "SELECT id, zone_id FROM nodes WHERE uid = $1", node_uid
                )
                if node_rows:
                    node_id = node_rows[0]["id"]
                    zone_id = node_rows[0]["zone_id"]

            status_value = resolve_stub_insert_status(normalized_status)
            cmd_name = "unknown"

            if cmd_id and cmd_id.startswith("hl-"):
                logger.warning(
                    "[CMD_ID_FORENSICS] command_response stub INSERT with hl- prefix "
                    "cmd_id=%s node_uid=%s channel=%s status=%s",
                    cmd_id, node_uid, channel, status_value,
                    stack_info=True,
                )

            await execute(
                """
                INSERT INTO commands (zone_id, node_id, channel, cmd, params, status, source, cmd_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
                """,
                zone_id,
                node_id,
                channel,
                cmd_name,
                {},
                status_value,
                "device",
                cmd_id,
            )
            logger.info(
                "[COMMAND_RESPONSE] Created stub record for cmd_id=%s, status=%s, node_uid=%s, channel=%s, origin=device",
                cmd_id,
                status_value,
                node_uid,
                channel,
            )
        else:
            zone_id = existing_cmd[0].get("zone_id")
            cmd_name = existing_cmd[0].get("cmd")
            existing_status = str(existing_cmd[0].get("status") or "").strip().upper()
            _terminal = ("DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED")
            if (
                existing_status == normalized_status.value.upper()
                and existing_status in _terminal
            ):
                logger.debug(
                    "[COMMAND_RESPONSE] Duplicate response for cmd_id=%s (status=%s already set), skipping",
                    cmd_id,
                    existing_status,
                )
                return "__DEDUP__", None, existing_status
    except Exception as e:
        logger.warning(
            "[COMMAND_RESPONSE] Failed to ensure stub record for cmd_id=%s: %s",
            cmd_id,
            e,
            exc_info=True,
        )

    return zone_id, cmd_name, existing_status


def _log_delivery_result(
    *,
    delivery_result,
    cmd_id: str,
    normalized_status,
    node_uid,
    channel,
    existing_status,
) -> None:
    if delivery_result.delivered:
        logger.info(
            "[COMMAND_RESPONSE] Status '%s' delivered to Laravel for cmd_id=%s, node_uid=%s, channel=%s, local_status_before=%s",
            normalized_status.value,
            cmd_id,
            node_uid,
            channel,
            existing_status,
        )
    elif delivery_result.queued:
        logger.warning(
            "[COMMAND_RESPONSE] Status '%s' retry-enqueued for cmd_id=%s, node_uid=%s, channel=%s, local_status_before=%s, reason=%s, queue_size=%s, dlq_size=%s",
            normalized_status.value,
            cmd_id,
            node_uid,
            channel,
            existing_status,
            delivery_result.reason,
            (delivery_result.queue_metrics or {}).get("size"),
            (delivery_result.queue_metrics or {}).get("dlq_size"),
        )
    else:
        logger.error(
            "[COMMAND_RESPONSE] Status '%s' DROPPED for cmd_id=%s, node_uid=%s, channel=%s, local_status_before=%s, reason=%s, http_status=%s, queue_error=%s",
            normalized_status.value,
            cmd_id,
            node_uid,
            channel,
            existing_status,
            delivery_result.reason,
            delivery_result.http_status,
            delivery_result.queue_error,
        )
        COMMAND_RESPONSE_ERROR.inc()


async def _maybe_persist_irr_state_snapshot(
    *,
    zone_id,
    cmd_name,
    channel,
    cmd_id,
    node_uid,
    response_ts,
    details,
) -> None:
    cmd_name_normalized = str(cmd_name or "").strip().lower()
    channel_normalized = str(channel or "").strip().lower()
    should_persist_irr_snapshot = cmd_name_normalized == "state" or channel_normalized == "storage_state"
    if not (zone_id and should_persist_irr_snapshot):
        return

    snapshot_source = details.get("snapshot")
    if not isinstance(snapshot_source, dict):
        snapshot_source = details.get("state")
    snapshot = normalize_irr_state_snapshot(snapshot_source)
    if snapshot is None:
        return

    try:
        await create_zone_event(
            int(zone_id),
            IRR_STATE_SNAPSHOT_EVENT_TYPE,
            {
                "source": "command_response_state",
                "cmd_id": cmd_id,
                "node_uid": node_uid,
                "channel": channel,
                "response_ts": response_ts,
                "snapshot": snapshot,
            },
        )
    except Exception:
        logger.warning(
            "[COMMAND_RESPONSE] Failed to persist IRR_STATE_SNAPSHOT for zone_id=%s cmd_id=%s",
            zone_id,
            cmd_id,
            exc_info=True,
        )


async def _record_simulation_event_for_response(
    *,
    zone_id,
    cmd_id,
    cmd_name,
    channel,
    node_uid,
    raw_status,
    normalized_status,
    delivery_result,
) -> None:
    status_value = (
        normalized_status.value
        if hasattr(normalized_status, "value")
        else str(normalized_status)
    )
    event_status = status_value.lower()
    level = "info"
    if event_status in ("error", "failed", "timeout", "send_failed"):
        level = "error"
    elif event_status in ("invalid", "busy", "no_effect"):
        level = "warning"

    await record_simulation_event(
        zone_id,
        service="history-logger",
        stage="command_response",
        status=event_status,
        level=level,
        message="Получен ответ на команду",
        payload={
            "cmd_id": cmd_id,
            "cmd": cmd_name,
            "channel": channel,
            "node_uid": node_uid,
            "raw_status": raw_status,
            "delivery": (
                "delivered"
                if delivery_result.delivered
                else ("queued" if delivery_result.queued else "dropped")
            ),
            "delivery_reason": delivery_result.reason,
        },
    )
