"""``handle_node_event``: channel-level events от ESP32 → ``zone_events`` + NOTIFY.

Топик: ``hydro/{gh}/{zone}/{node}/{channel}/event``.
"""

from __future__ import annotations

import logging

from common.db import create_zone_event, notify_zone_event_ingested
from common.trace_context import clear_trace_id
from metrics import NODE_EVENT_ERROR, NODE_EVENT_RECEIVED, NODE_EVENT_UNKNOWN
from utils import _extract_channel_from_topic, _extract_gh_uid, _extract_node_uid, _extract_zone_uid, _parse_json

from ._shared import (
    IRR_STATE_SNAPSHOT_EVENT_TYPE,
    NODE_EVENT_METRIC_FALLBACK,
    apply_trace_context,
    build_node_event_notify_payload,
    metric_event_code_label,
    normalize_node_event_payload,
    normalize_node_event_type,
    resolve_zone_id_for_node_event,
)

logger = logging.getLogger(__name__)


async def handle_node_event(topic: str, payload: bytes) -> None:
    """Обработчик channel-level event сообщений от узлов ESP32."""
    try:
        logger.info("[NODE_EVENT] ===== START processing node event =====")
        logger.info("[NODE_EVENT] Topic: %s, payload length: %s", topic, len(payload))

        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning("[NODE_EVENT] Invalid JSON in event from topic %s", topic)
            NODE_EVENT_ERROR.labels(reason="invalid_json").inc()
            return

        apply_trace_context(data, fallback_keys=("trace_id", "event_id", "cmd_id"))

        gh_uid = _extract_gh_uid(topic)
        zone_uid = _extract_zone_uid(topic)
        node_uid = _extract_node_uid(topic)
        channel = _extract_channel_from_topic(topic)

        event_code_raw = data.get("event_code") or data.get("event") or data.get("type") or "node_event"
        event_code = str(event_code_raw).strip()
        if not event_code:
            event_code = "node_event"
        event_type = normalize_node_event_type(event_code)

        zone_id = await resolve_zone_id_for_node_event(zone_uid, node_uid)
        if not zone_id:
            logger.warning(
                "[NODE_EVENT] Could not resolve zone_id for event, skipping: gh_uid=%s zone_uid=%s node_uid=%s channel=%s event_code=%s",
                gh_uid,
                zone_uid,
                node_uid,
                channel,
                event_code,
            )
            NODE_EVENT_ERROR.labels(reason="zone_not_resolved").inc()
            return

        details = normalize_node_event_payload(
            topic=topic,
            gh_uid=gh_uid,
            zone_uid=zone_uid,
            node_uid=node_uid,
            channel=channel,
            event_code=event_code,
            data=data,
        )
        inserted = await create_zone_event(zone_id, event_type, details)
        if inserted:
            await notify_zone_event_ingested(
                zone_id=zone_id,
                event_type=event_type,
                payload=build_node_event_notify_payload(
                    channel=channel,
                    event_type=event_type,
                    payload=details,
                ),
            )

        channel_normalized = str(channel or "").strip().lower()
        if channel_normalized == "storage_state":
            await _maybe_persist_irr_state_snapshot(
                zone_id=zone_id,
                topic=topic,
                gh_uid=gh_uid,
                zone_uid=zone_uid,
                node_uid=node_uid,
                channel=channel,
                event_code=event_code,
                data=data,
                details=details,
            )

        metric_event_code = metric_event_code_label(event_type)
        NODE_EVENT_RECEIVED.labels(event_code=metric_event_code).inc()
        if metric_event_code == NODE_EVENT_METRIC_FALLBACK:
            NODE_EVENT_UNKNOWN.inc()

        logger.info(
            "[NODE_EVENT] Stored zone event: zone_id=%s node_uid=%s channel=%s event_type=%s",
            zone_id,
            node_uid,
            channel,
            event_type,
        )
    except Exception:
        NODE_EVENT_ERROR.labels(reason="handler_exception").inc()
        logger.exception("[NODE_EVENT] Unexpected error while handling event topic %s", topic)
    finally:
        clear_trace_id()


async def _maybe_persist_irr_state_snapshot(
    *,
    zone_id: int,
    topic: str,
    gh_uid,
    zone_uid,
    node_uid,
    channel,
    event_code: str,
    data: dict,
    details: dict,
) -> None:
    snapshot = details.get("snapshot") if isinstance(details.get("snapshot"), dict) else None
    if snapshot is None:
        return

    snapshot_payload = {
        "source": "node_event_storage_state",
        "topic": topic,
        "gh_uid": gh_uid,
        "zone_uid": zone_uid,
        "node_uid": node_uid,
        "channel": channel,
        "event_code": event_code,
        "cmd_id": str(data.get("cmd_id") or "").strip() or None,
        "response_ts": data.get("ts"),
        "snapshot": snapshot,
    }
    snapshot_payload = {k: v for k, v in snapshot_payload.items() if v is not None}
    await create_zone_event(zone_id, IRR_STATE_SNAPSHOT_EVENT_TYPE, snapshot_payload)
