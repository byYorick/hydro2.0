"""MQTT → Redis queue ingress для телеметрии.

``handle_telemetry`` — entry point для MQTT сообщения: валидирует payload,
нормализует timestamp, пушит в Redis очередь (``state.telemetry_queue``).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import state
from common.redis_queue import TelemetryQueueItem
from common.trace_context import clear_trace_id, set_trace_id_from_payload
from common.utils.time import utcnow
from metrics import (
    REDIS_OPERATION_DURATION,
    TELEM_RECEIVED,
    TELEMETRY_DROPPED,
)
from models import TelemetryPayloadModel
from utils import (
    _extract_channel_from_topic,
    _extract_gh_uid,
    _extract_node_uid,
    _extract_zone_uid,
    _filter_raw_data,
    _parse_json,
)

from .anomaly_alerts import emit_telemetry_anomaly_alert

logger = logging.getLogger(__name__)

REDIS_PUSH_MAX_RETRIES = 3
REDIS_PUSH_RETRY_BACKOFF_BASE = 2


def _telemetry_queue():
    return state.telemetry_queue


async def push_with_retry(
    queue_item: TelemetryQueueItem, max_retries: int = REDIS_PUSH_MAX_RETRIES
) -> bool:
    """Push в Redis queue с retry + exponential backoff."""
    if not _telemetry_queue():
        return False

    for attempt in range(max_retries):
        try:
            success = await _telemetry_queue().push(queue_item)
            if success:
                if attempt > 0:
                    logger.info(
                        f"Successfully pushed to Redis queue after {attempt + 1} attempts"
                    )
                return True

            if attempt == 0:
                logger.warning(
                    "Redis queue full, cannot push telemetry: "
                    f"node_uid={queue_item.node_uid}, metric_type={queue_item.metric_type}"
                )
            return False

        except Exception as e:
            if attempt < max_retries - 1:
                backoff_seconds = REDIS_PUSH_RETRY_BACKOFF_BASE**attempt
                logger.warning(
                    "Failed to push to Redis queue "
                    f"(attempt {attempt + 1}/{max_retries}), retrying in {backoff_seconds}s: {e}"
                )
                await asyncio.sleep(backoff_seconds)
            else:
                logger.error(
                    f"Failed to push to Redis queue after {max_retries} attempts: {e}",
                    exc_info=True,
                )
                return False

    return False


async def handle_telemetry(topic: str, payload: bytes) -> None:
    """MQTT telemetry entry point: parse → validate → normalize ts → push в Redis."""
    try:
        data = _parse_json(payload)
        if not data:
            logger.warning(f"[TELEMETRY] Failed to parse JSON from topic: {topic}")
            return

        if isinstance(data, dict):
            set_trace_id_from_payload(data, fallback_generate=False)

        if isinstance(data, dict) and "timestamp" in data and "ts" not in data:
            logger.warning(
                "Legacy telemetry format without ts field, dropping message",
                extra={"topic": topic, "payload_keys": list(data.keys())},
            )
            TELEMETRY_DROPPED.labels(reason="legacy_timestamp").inc()
            return

        try:
            validated_data = TelemetryPayloadModel(**data)
        except Exception as e:
            logger.warning(
                "Invalid telemetry payload",
                extra={
                    "error": str(e),
                    "topic": topic,
                    "payload_keys": list(data.keys()) if isinstance(data, dict) else None,
                    "payload_size": len(payload),
                },
            )
            TELEMETRY_DROPPED.labels(reason="validation_failed").inc()
            return

        TELEM_RECEIVED.inc()

        gh_uid = _extract_gh_uid(topic)
        zone_uid = _extract_zone_uid(topic)
        node_uid = _extract_node_uid(topic)
        channel = _extract_channel_from_topic(topic)

        if not zone_uid and validated_data.zone_uid:
            zone_uid = validated_data.zone_uid
        if not node_uid and validated_data.node_uid:
            node_uid = validated_data.node_uid

        ts = await _normalize_device_timestamp(
            raw_ts=validated_data.ts,
            topic=topic,
            gh_uid=gh_uid,
            zone_uid=zone_uid,
            node_uid=node_uid,
            metric_type=validated_data.metric_type,
        )

        metric_type = validated_data.metric_type
        if not metric_type:
            logger.warning(
                "Missing metric_type in telemetry payload",
                extra={
                    "topic": topic,
                    "node_uid": node_uid,
                    "zone_uid": zone_uid,
                    "payload_keys": list(data.keys()) if isinstance(data, dict) else None,
                },
            )
            TELEMETRY_DROPPED.labels(reason="missing_metric_type").inc()
            return

        channel_name = validated_data.channel or channel
        filtered_raw = _filter_raw_data(data)

        queue_item = TelemetryQueueItem(
            node_uid=node_uid or "",
            zone_uid=zone_uid,
            gh_uid=gh_uid,
            metric_type=metric_type,
            value=validated_data.value,
            ts=ts,
            raw=filtered_raw,
            channel=channel_name,
            enqueued_at=utcnow(),
        )

        logger.info(
            f"[TELEMETRY] Received: node={node_uid}, metric={metric_type}, value={validated_data.value}"
        )

        if _telemetry_queue():
            start_time = time.time()
            success = await push_with_retry(queue_item)
            redis_duration = time.time() - start_time
            REDIS_OPERATION_DURATION.observe(redis_duration)

            if not success:
                logger.warning(
                    f"[TELEMETRY] Failed to push to queue: node={node_uid}, metric={metric_type}"
                )
                TELEMETRY_DROPPED.labels(reason="queue_push_failed").inc()
                logger.error(
                    "Failed to push telemetry to queue after retries, dropping message",
                    extra={
                        "node_uid": node_uid,
                        "zone_uid": zone_uid,
                        "metric_type": queue_item.metric_type,
                        "topic": topic,
                    },
                )
        else:
            logger.error(
                f"[TELEMETRY] Queue not initialized: node={node_uid}, metric={metric_type}"
            )
            TELEMETRY_DROPPED.labels(reason="queue_not_initialized").inc()
            logger.error(
                "Telemetry queue not initialized, dropping message",
                extra={
                    "node_uid": node_uid,
                    "zone_uid": zone_uid,
                    "metric_type": metric_type,
                    "topic": topic,
                },
            )
    finally:
        clear_trace_id()


async def _normalize_device_timestamp(
    *,
    raw_ts,
    topic: str,
    gh_uid,
    zone_uid,
    node_uid,
    metric_type,
):
    """Normalise device-provided timestamp: сек/мс/ISO → UTC datetime.

    При skew / below-min-valid шлём throttled anomaly alert и fallback на server time.
    """
    MIN_VALID_TIMESTAMP = 1_000_000_000
    MAX_TIMESTAMP_DRIFT_SEC = 300
    server_timestamp = time.time()
    server_time = datetime.fromtimestamp(server_timestamp, timezone.utc)

    if isinstance(raw_ts, str):
        stripped_ts = raw_ts.strip()
        try:
            if stripped_ts.replace(".", "", 1).isdigit():
                raw_ts = float(stripped_ts)
        except Exception:
            pass

    ts = None
    if raw_ts:
        try:
            if isinstance(raw_ts, (int, float)):
                ts_value = float(raw_ts)
                if ts_value > 1_000_000_000_000:
                    ts_value = ts_value / 1000.0
                if ts_value >= MIN_VALID_TIMESTAMP:
                    drift = ts_value - server_timestamp
                    if drift > MAX_TIMESTAMP_DRIFT_SEC:
                        logger.warning(
                            "Timestamp from device is skewed (drift too large), using server time",
                            extra={
                                "device_ts": ts_value,
                                "server_ts": server_timestamp,
                                "drift_sec": drift,
                                "max_drift_sec": MAX_TIMESTAMP_DRIFT_SEC,
                                "topic": topic,
                                "node_uid": node_uid,
                                "zone_uid": zone_uid,
                            },
                        )
                        await emit_telemetry_anomaly_alert(
                            code="infra_telemetry_timestamp_skew",
                            message="Telemetry timestamp is too far in the future, fallback to server time",
                            gh_uid=gh_uid,
                            zone_uid=zone_uid,
                            node_uid=node_uid,
                            channel=None,
                            metric_type=metric_type,
                            details={
                                "device_ts": ts_value,
                                "server_ts": server_timestamp,
                                "drift_sec": drift,
                                "max_drift_sec": MAX_TIMESTAMP_DRIFT_SEC,
                                "topic": topic,
                            },
                        )
                        ts = server_time
                    else:
                        if drift < -MAX_TIMESTAMP_DRIFT_SEC:
                            logger.warning(
                                "Timestamp from device is older than expected, preserving for freshness checks",
                                extra={
                                    "device_ts": ts_value,
                                    "server_ts": server_timestamp,
                                    "drift_sec": drift,
                                    "max_drift_sec": MAX_TIMESTAMP_DRIFT_SEC,
                                    "topic": topic,
                                    "node_uid": node_uid,
                                    "zone_uid": zone_uid,
                                },
                            )
                        ts = datetime.fromtimestamp(ts_value)
                else:
                    logger.warning(
                        "Invalid timestamp from firmware (likely uptime), using server time",
                        extra={
                            "ts": ts_value,
                            "topic": topic,
                            "node_uid": node_uid,
                            "zone_uid": zone_uid,
                        },
                    )
                    await emit_telemetry_anomaly_alert(
                        code="infra_telemetry_invalid_timestamp",
                        message="Telemetry timestamp from device is invalid, fallback to server time",
                        gh_uid=gh_uid,
                        zone_uid=zone_uid,
                        node_uid=node_uid,
                        channel=None,
                        metric_type=metric_type,
                        details={
                            "device_ts": ts_value,
                            "topic": topic,
                            "reason": "numeric_timestamp_below_min_valid",
                        },
                    )
            elif isinstance(raw_ts, str):
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                ts_timestamp = ts.timestamp()
                if ts_timestamp < MIN_VALID_TIMESTAMP:
                    logger.warning(
                        "Invalid timestamp from firmware (likely uptime), using server time",
                        extra={
                            "ts": ts_timestamp,
                            "topic": topic,
                            "node_uid": node_uid,
                            "zone_uid": zone_uid,
                        },
                    )
                    await emit_telemetry_anomaly_alert(
                        code="infra_telemetry_invalid_timestamp",
                        message="Telemetry timestamp from device is invalid, fallback to server time",
                        gh_uid=gh_uid,
                        zone_uid=zone_uid,
                        node_uid=node_uid,
                        channel=None,
                        metric_type=metric_type,
                        details={
                            "device_ts": ts_timestamp,
                            "topic": topic,
                            "reason": "iso_timestamp_below_min_valid",
                        },
                    )
                    ts = None
                else:
                    drift = ts_timestamp - server_timestamp
                    if drift > MAX_TIMESTAMP_DRIFT_SEC:
                        logger.warning(
                            "Timestamp from device is skewed (drift too large), using server time",
                            extra={
                                "device_ts": ts_timestamp,
                                "server_ts": server_timestamp,
                                "drift_sec": drift,
                                "max_drift_sec": MAX_TIMESTAMP_DRIFT_SEC,
                                "topic": topic,
                                "node_uid": node_uid,
                                "zone_uid": zone_uid,
                            },
                        )
                        await emit_telemetry_anomaly_alert(
                            code="infra_telemetry_timestamp_skew",
                            message="Telemetry timestamp is too far in the future, fallback to server time",
                            gh_uid=gh_uid,
                            zone_uid=zone_uid,
                            node_uid=node_uid,
                            channel=None,
                            metric_type=metric_type,
                            details={
                                "device_ts": ts_timestamp,
                                "server_ts": server_timestamp,
                                "drift_sec": drift,
                                "max_drift_sec": MAX_TIMESTAMP_DRIFT_SEC,
                                "topic": topic,
                            },
                        )
                        ts = None
                    elif drift < -MAX_TIMESTAMP_DRIFT_SEC:
                        logger.warning(
                            "Timestamp from device is older than expected (string), preserving for freshness checks",
                            extra={
                                "device_ts": ts_timestamp,
                                "server_ts": server_timestamp,
                                "drift_sec": drift,
                                "max_drift_sec": MAX_TIMESTAMP_DRIFT_SEC,
                                "topic": topic,
                                "node_uid": node_uid,
                                "zone_uid": zone_uid,
                            },
                        )
        except Exception as e:
            logger.warning(
                "Failed to parse timestamp, using server time",
                extra={
                    "ts": raw_ts,
                    "error": str(e),
                    "topic": topic,
                    "node_uid": node_uid,
                    "zone_uid": zone_uid,
                },
            )
            await emit_telemetry_anomaly_alert(
                code="infra_telemetry_timestamp_parse_failed",
                message="Failed to parse telemetry timestamp, fallback to server time",
                gh_uid=gh_uid,
                zone_uid=zone_uid,
                node_uid=node_uid,
                channel=None,
                metric_type=metric_type,
                details={"topic": topic, "raw_ts": raw_ts, "error": str(e)},
            )

    if ts is None:
        ts = server_time
    return ts
