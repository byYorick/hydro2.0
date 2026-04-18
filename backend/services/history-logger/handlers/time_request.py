"""``handle_time_request``: ответ на ``hydro/time/request`` payload'ом с unix_ts сервера."""

from __future__ import annotations

import logging
import uuid

from common.mqtt import get_mqtt_client
from common.trace_context import clear_trace_id
from common.utils.time import utcnow
from utils import _parse_json

from ._shared import apply_trace_context

logger = logging.getLogger(__name__)


async def handle_time_request(topic: str, payload: bytes) -> None:
    """Публикует ``time_response`` на ``hydro/time/response`` broadcast-топик."""
    try:
        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[TIME_REQUEST] Invalid JSON in time_request from topic {topic}")
            return

        apply_trace_context(data)

        server_time = int(utcnow().timestamp())
        mqtt = await get_mqtt_client()

        broadcast_topic = "hydro/time/response"
        response_payload = {
            "message_type": "time_response",
            "unix_ts": server_time,
            "server_time": server_time,
        }
        _ = f"time_sync_{uuid.uuid4().hex[:8]}"  # reserved cmd_id pattern for future use

        mqtt._client.publish_json(broadcast_topic, response_payload, qos=1, retain=False)
        logger.info(
            "[TIME_REQUEST] Sent time response: server_time=%s, topic=%s",
            server_time,
            broadcast_topic,
        )
    except Exception as e:
        logger.error(
            f"[TIME_REQUEST] Unexpected error processing time_request: {e}",
            exc_info=True,
        )
    finally:
        clear_trace_id()
