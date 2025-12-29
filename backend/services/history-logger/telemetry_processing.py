import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

import state
from common.db import create_zone_event, execute, fetch, upsert_telemetry_last
from common.env import get_settings
from common.redis_queue import TelemetryQueueItem
from common.utils.time import utcnow
from metrics import (
    DATABASE_ERRORS,
    LARAVEL_API_DURATION,
    REDIS_OPERATION_DURATION,
    TELEM_BATCH_SIZE,
    TELEM_PROCESSED,
    TELEM_RECEIVED,
    TELEMETRY_DROPPED,
    TELEMETRY_PROCESSING_DURATION,
    TELEMETRY_QUEUE_AGE,
)
from models import TelemetryPayloadModel, TelemetrySampleModel
from utils import (
    MAX_PAYLOAD_SIZE,
    _calculate_broadcast_backoff,
    _extract_channel_from_topic,
    _extract_gh_uid,
    _extract_node_uid,
    _extract_zone_uid,
    extract_zone_id_from_uid,
    _filter_raw_data,
    _parse_json,
)

logger = logging.getLogger(__name__)

# Конфигурация retry логики для Redis
REDIS_PUSH_MAX_RETRIES = 3
REDIS_PUSH_RETRY_BACKOFF_BASE = 2

# Глобальный кеш для резолва zone_id и node_id (с TTL refresh)
_zone_cache: dict[tuple[str, Optional[str]], int] = {}
_node_cache: dict[tuple[str, Optional[str]], tuple[int, Optional[int]]] = {}
_cache_last_update = 0.0
_cache_ttl = 60.0

# Backoff состояние для telemetry broadcast
_broadcast_error_count = 0
_broadcast_last_error_time: Optional[float] = None
_broadcast_backoff_until: Optional[float] = None


def _get_telemetry_queue():
    return state.telemetry_queue


def _shutdown_event():
    return state.shutdown_event


async def _push_with_retry(
    queue_item: TelemetryQueueItem, max_retries: int = REDIS_PUSH_MAX_RETRIES
) -> bool:
    """
    Добавить элемент в Redis queue с retry логикой и exponential backoff.
    """
    if not _get_telemetry_queue():
        return False

    for attempt in range(max_retries):
        try:
            success = await _get_telemetry_queue().push(queue_item)
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
    """
    Обработчик телеметрии из MQTT.
    Добавляет данные в Redis queue для последующей обработки.
    """
    data = _parse_json(payload)
    if not data:
        logger.warning(f"[TELEMETRY] Failed to parse JSON from topic: {topic}")
        return

    if isinstance(data, dict) and "timestamp" in data and "ts" not in data:
        logger.warning(
            "Legacy telemetry format without ts field, dropping message",
            extra={
                "topic": topic,
                "payload_keys": list(data.keys()),
            },
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

    MIN_VALID_TIMESTAMP = 1_000_000_000
    MAX_TIMESTAMP_DRIFT_SEC = 300
    server_timestamp = time.time()
    server_time = datetime.utcfromtimestamp(server_timestamp)

    raw_ts = validated_data.ts
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
                    "ts": validated_data.ts,
                    "error": str(e),
                    "topic": topic,
                    "node_uid": node_uid,
                    "zone_uid": zone_uid,
                },
            )

    if ts is None:
        ts = server_time

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

    if _get_telemetry_queue():
        start_time = time.time()
        success = await _push_with_retry(queue_item)
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


async def refresh_caches() -> None:
    """Обновить кеши zone_id и node_id."""
    global _zone_cache, _node_cache, _cache_last_update

    try:
        zones = await fetch(
            """
            SELECT z.id, z.uid, g.uid as gh_uid
            FROM zones z
            JOIN greenhouses g ON g.id = z.greenhouse_id
            """
        )
        _zone_cache.clear()
        for zone in zones:
            zone_uid = zone.get("uid")
            zone_id = zone.get("id")
            if not zone_uid or zone_id is None:
                continue
            gh_uid = zone.get("gh_uid")
            key = (zone_uid, gh_uid)
            _zone_cache[key] = zone_id
            if (zone_uid, None) not in _zone_cache:
                _zone_cache[(zone_uid, None)] = zone_id

        nodes = await fetch(
            """
            SELECT n.id, n.uid, n.zone_id, g.uid as gh_uid
            FROM nodes n
            LEFT JOIN zones z ON z.id = n.zone_id
            LEFT JOIN greenhouses g ON g.id = z.greenhouse_id
            """
        )
        _node_cache.clear()
        for node in nodes:
            node_uid = node.get("uid")
            node_id = node.get("id")
            if not node_uid or node_id is None:
                continue
            gh_uid = node.get("gh_uid")
            zone_id = node.get("zone_id")
            key = (node_uid, gh_uid)
            _node_cache[key] = (node_id, zone_id)
            if (node_uid, None) not in _node_cache:
                _node_cache[(node_uid, None)] = (node_id, zone_id)

        _cache_last_update = time.time()
        logger.info(
            f"Cache refreshed: {len(_zone_cache)} zone entries, {len(_node_cache)} node entries"
        )
    except Exception as e:
        logger.error(f"Failed to refresh caches: {e}", exc_info=True)


async def process_telemetry_batch(samples: List[TelemetrySampleModel]) -> None:
    """Обработать батч телеметрии и записать в БД."""
    if not samples:
        return

    start_time = time.time()
    s = get_settings()
    max_age_minutes = float(os.getenv("TELEMETRY_MAX_AGE_MINUTES", "30"))
    max_age_seconds = max_age_minutes * 60

    global _cache_last_update, _cache_ttl
    current_time = time.time()
    if current_time - _cache_last_update > _cache_ttl:
        await refresh_caches()

    zone_uid_to_id: dict[tuple[str, Optional[str]], int] = {}

    zone_gh_pairs = list(
        set(
            (sample.zone_uid, sample.gh_uid)
            for sample in samples
            if sample.zone_uid
        )
    )

    if zone_gh_pairs:
        missing_zones = []
        for zone_uid, gh_uid in zone_gh_pairs:
            key = (zone_uid, gh_uid)
            if key in _zone_cache:
                zone_uid_to_id[key] = _zone_cache[key]
            else:
                fallback_key = (zone_uid, None)
                if fallback_key in _zone_cache:
                    zone_uid_to_id[key] = _zone_cache[fallback_key]
                else:
                    missing_zones.append((zone_uid, gh_uid))

        if missing_zones:
            zones_with_gh = [(z, g) for z, g in missing_zones if g]
            zones_without_gh = [(z, g) for z, g in missing_zones if not g]

            if zones_with_gh:
                zone_uids = [z for z, _ in zones_with_gh]
                gh_uids = [g for _, g in zones_with_gh]
                zone_rows = await fetch(
                    """
                    SELECT z.id, z.uid, g.uid as gh_uid
                    FROM zones z
                    JOIN greenhouses g ON g.id = z.greenhouse_id
                    WHERE (z.uid, g.uid) IN (SELECT unnest($1::text[]), unnest($2::text[]))
                    """,
                    zone_uids,
                    gh_uids,
                )

                for zone in zone_rows:
                    zone_uid = zone.get("uid")
                    zone_id = zone.get("id")
                    if not zone_uid or zone_id is None:
                        continue
                    gh_uid = zone.get("gh_uid")
                    key = (zone_uid, gh_uid)
                    zone_uid_to_id[key] = zone_id
                    _zone_cache[key] = zone_id

            if zones_without_gh:
                zone_uids = [z for z, _ in zones_without_gh]
                zone_rows = await fetch(
                    """
                    SELECT id, uid
                    FROM zones
                    WHERE uid = ANY($1)
                    """,
                    zone_uids,
                )

                for zone in zone_rows:
                    zone_uid = zone.get("uid")
                    zone_id = zone.get("id")
                    if not zone_uid or zone_id is None:
                        continue
                    key = (zone_uid, None)
                    zone_uid_to_id[key] = zone_id
                    _zone_cache[key] = zone_id

        for zone_uid, gh_uid in zone_gh_pairs:
            if (zone_uid, gh_uid) not in zone_uid_to_id:
                if (zone_uid, None) not in zone_uid_to_id:
                    logger.warning(
                        f"Zone not found: zone_uid={zone_uid}, gh_uid={gh_uid}",
                        extra={"zone_uid": zone_uid, "gh_uid": gh_uid},
                    )

    node_uid_to_info: dict[tuple[str, Optional[str]], tuple[int, Optional[int]]] = {}

    node_gh_pairs = list(
        set((s.node_uid, s.gh_uid) for s in samples if s.node_uid)
    )

    if node_gh_pairs:
        missing_nodes = []
        for node_uid, gh_uid in node_gh_pairs:
            key = (node_uid, gh_uid)
            if key in _node_cache:
                node_uid_to_info[key] = _node_cache[key]
            else:
                fallback_key = (node_uid, None)
                if fallback_key in _node_cache:
                    node_uid_to_info[key] = _node_cache[fallback_key]
                else:
                    missing_nodes.append((node_uid, gh_uid))

        if missing_nodes:
            nodes_with_gh = [(n, g) for n, g in missing_nodes if g]
            nodes_without_gh = [(n, g) for n, g in missing_nodes if not g]

            if nodes_with_gh:
                node_uids = [n for n, _ in nodes_with_gh]
                gh_uids = [g for _, g in nodes_with_gh]
                node_rows = await fetch(
                    """
                    SELECT n.id, n.uid, n.zone_id, g.uid as gh_uid
                    FROM nodes n
                    LEFT JOIN zones z ON z.id = n.zone_id
                    LEFT JOIN greenhouses g ON g.id = z.greenhouse_id
                    WHERE (n.uid, COALESCE(g.uid, '')) IN (
                        SELECT unnest($1::text[]), unnest($2::text[])
                    )
                    """,
                    node_uids,
                    gh_uids,
                )

                for node in node_rows:
                    node_uid = node.get("uid")
                    node_id = node.get("id")
                    if not node_uid or node_id is None:
                        continue
                    gh_uid = node.get("gh_uid")
                    zone_id = node.get("zone_id")
                    key = (node_uid, gh_uid)
                    node_uid_to_info[key] = (node_id, zone_id)
                    _node_cache[key] = (node_id, zone_id)

            if nodes_without_gh:
                node_uids = [n for n, _ in nodes_without_gh]
                node_rows = await fetch(
                    """
                    SELECT id, uid, zone_id
                    FROM nodes
                    WHERE uid = ANY($1)
                    """,
                    node_uids,
                )

                for node in node_rows:
                    node_uid = node.get("uid")
                    node_id = node.get("id")
                    if not node_uid or node_id is None:
                        continue
                    zone_id = node.get("zone_id")
                    key = (node_uid, None)
                    node_uid_to_info[key] = (node_id, zone_id)
                    _node_cache[key] = (node_id, zone_id)

        for node_uid, gh_uid in node_gh_pairs:
            if (node_uid, gh_uid) not in node_uid_to_info:
                if (node_uid, None) not in node_uid_to_info:
                    if not gh_uid:
                        logger.warning(
                            "gh_uid not provided for node_uid=%s, using simple node_id resolution "
                            "(may cause conflicts in multi-greenhouse setup)",
                            node_uid,
                            extra={"node_uid": node_uid},
                        )
                    logger.warning(
                        "Node not found: node_uid=%s, gh_uid=%s",
                        node_uid,
                        gh_uid,
                        extra={"node_uid": node_uid, "gh_uid": gh_uid},
                    )

    grouped: dict[tuple[int, str, Optional[int], Optional[str]], list[TelemetrySampleModel]] = {}

    for sample in samples:
        zone_id = sample.zone_id if sample.zone_id is not None else None
        if zone_id is None and sample.zone_uid:
            zone_id = zone_uid_to_id.get((sample.zone_uid, sample.gh_uid))
            if zone_id is None and sample.gh_uid:
                zone_id = zone_uid_to_id.get((sample.zone_uid, None))
        if zone_id is None and sample.zone_uid:
            zone_id = extract_zone_id_from_uid(sample.zone_uid)

        node_id = None
        node_zone_id = None
        if sample.node_uid:
            node_info = node_uid_to_info.get((sample.node_uid, sample.gh_uid))
            if node_info is None and sample.gh_uid:
                node_info = node_uid_to_info.get((sample.node_uid, None))

            if node_info:
                node_id, node_zone_id = node_info

        if zone_id is None:
            if not sample.zone_uid:
                logger.warning(
                    "Skipping sample: zone_uid missing",
                    extra={
                        "zone_uid": sample.zone_uid,
                        "node_uid": sample.node_uid,
                        "metric_type": sample.metric_type,
                    },
                )
            else:
                logger.warning(
                    "Skipping sample: zone_id not found for zone_uid",
                    extra={
                        "zone_uid": sample.zone_uid,
                        "node_uid": sample.node_uid,
                        "metric_type": sample.metric_type,
                        "zone_uid_format_valid": sample.zone_uid.startswith("zn-")
                        if sample.zone_uid
                        else False,
                    },
                )
            TELEMETRY_DROPPED.labels(reason="zone_id_not_found").inc()
            continue

        if node_id and node_zone_id is not None:
            if node_zone_id != zone_id:
                logger.warning(
                    "Security: node_uid does not belong to zone_id, dropping sample",
                    extra={
                        "node_uid": sample.node_uid,
                        "node_id": node_id,
                        "node_zone_id": node_zone_id,
                        "requested_zone_id": zone_id,
                        "zone_uid": sample.zone_uid,
                        "gh_uid": sample.gh_uid,
                        "metric_type": sample.metric_type,
                    },
                )
                TELEMETRY_DROPPED.labels(reason="node_zone_mismatch").inc()
                continue

        sample_ts = sample.ts
        if sample_ts:
            if getattr(sample_ts, "tzinfo", None):
                sample_ts = sample_ts.astimezone(timezone.utc)
            else:
                sample_ts = sample_ts.replace(tzinfo=timezone.utc)
            age_seconds = (utcnow() - sample_ts).total_seconds()
            if age_seconds > max_age_seconds:
                try:
                    await create_zone_event(
                        zone_id,
                        "TELEMETRY_STALE",
                        {
                            "metric_type": sample.metric_type,
                            "age_minutes": age_seconds / 60,
                            "max_age_minutes": max_age_minutes,
                            "node_uid": sample.node_uid,
                            "channel": sample.channel,
                        },
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to create TELEMETRY_STALE event: {e}",
                        exc_info=True,
                    )

        key = (zone_id, sample.metric_type, node_id, sample.channel)
        grouped.setdefault(key, []).append(sample)

    telemetry_last_updates: dict[tuple[int, str], dict] = {}
    for (zone_id, metric_type, node_id, channel), group_samples in grouped.items():
        if not group_samples:
            continue
        latest_sample = max(
            group_samples,
            key=lambda s: s.ts if s.ts else datetime.min.replace(tzinfo=None),
        )
        key = (zone_id, metric_type)
        existing_ts = telemetry_last_updates.get(key, {}).get("ts") or datetime.min.replace(
            tzinfo=None
        )
        new_ts = latest_sample.ts or datetime.min.replace(tzinfo=None)
        if key not in telemetry_last_updates or new_ts > existing_ts:
            telemetry_last_updates[key] = {
                "node_id": node_id,
                "channel": channel,
                "value": latest_sample.value,
                "ts": latest_sample.ts,
            }

    if telemetry_last_updates:
        try:
            values_list = []
            params_list = []
            param_index = 1

            for (zone_id, metric_type), update_data in telemetry_last_updates.items():
                node_id = update_data["node_id"] if update_data["node_id"] is not None else -1
                channel = update_data["channel"]
                value = update_data["value"]
                sample_ts = update_data.get("ts")
                if sample_ts and getattr(sample_ts, "tzinfo", None):
                    sample_ts = sample_ts.astimezone(timezone.utc).replace(tzinfo=None)
                if not sample_ts:
                    sample_ts = utcnow()

                values_list.append(
                    f"(${param_index}, ${param_index + 1}, ${param_index + 2}, ${param_index + 3}, ${param_index + 4}, ${param_index + 5})"
                )
                params_list.extend(
                    [zone_id, node_id, metric_type, channel, value, sample_ts]
                )
                param_index += 6

            if values_list:
                query = f"""
                    INSERT INTO telemetry_last (zone_id, node_id, metric_type, channel, value, updated_at)
                    VALUES {', '.join(values_list)}
                    ON CONFLICT (zone_id, node_id, metric_type)
                    DO UPDATE SET
                        channel = EXCLUDED.channel,
                        value = EXCLUDED.value,
                        updated_at = EXCLUDED.updated_at
                """
                await execute(query, *params_list)
                logger.debug(
                    f"Batch upserted {len(telemetry_last_updates)} telemetry_last records"
                )
        except Exception as e:
            logger.error(f"Failed to batch upsert telemetry_last: {e}", exc_info=True)
            for (zone_id, metric_type), update_data in telemetry_last_updates.items():
                try:
                    await upsert_telemetry_last(
                        zone_id,
                        metric_type,
                        update_data["node_id"],
                        update_data["channel"],
                        update_data["value"],
                        update_data.get("ts"),
                    )
                except Exception as e2:
                    logger.error(
                        "Failed to upsert telemetry_last for zone_id=%s, metric_type=%s: %s",
                        zone_id,
                        metric_type,
                        e2,
                    )

    processed_count = 0
    for (zone_id, metric_type, node_id, channel), group_samples in grouped.items():
        logger.info(
            f"[BROADCAST] Processing group: zone_id={zone_id}, node_id={node_id}, "
            f"metric={metric_type}, samples={len(group_samples)}"
        )
        values_list = []
        params_list = []
        param_index = 1

        for sample in group_samples:
            ts = sample.ts or utcnow()
            value = sample.value

            values_list.append(
                f"(${param_index}, ${param_index + 1}, ${param_index + 2}, ${param_index + 3}, ${param_index + 4}, ${param_index + 5})"
            )
            params_list.extend([zone_id, node_id, metric_type, channel, value, ts])
            param_index += 6

        if values_list:
            query = f"""
                INSERT INTO telemetry_samples (zone_id, node_id, metric_type, channel, value, ts)
                VALUES {', '.join(values_list)}
            """
            try:
                await execute(query, *params_list)
                processed_count += len(group_samples)
                logger.info(
                    f"[TELEMETRY] Written: zone_id={zone_id}, node_id={node_id}, metric={metric_type}, count={len(group_samples)}"
                )
            except Exception as e:
                error_type = type(e).__name__
                DATABASE_ERRORS.labels(error_type=error_type).inc()
                logger.error(
                    "Failed to insert telemetry batch",
                    extra={
                        "error_type": error_type,
                        "error": str(e),
                        "zone_id": zone_id,
                        "metric_type": metric_type,
                        "samples_count": len(group_samples),
                    },
                    exc_info=True,
                )

        if group_samples:
            latest_sample = max(
                group_samples,
                key=lambda s: s.ts if s.ts else datetime.min.replace(tzinfo=None),
            )
            logger.info(
                f"[BROADCAST] After upsert: node_id={node_id}, shutdown={_shutdown_event().is_set()}, group_samples={len(group_samples)}"
            )
            if node_id and not _shutdown_event().is_set():
                logger.info(
                    f"[BROADCAST] Scheduling broadcast for node_id={node_id}, metric={metric_type}, value={latest_sample.value}"
                )
                try:
                    task = asyncio.create_task(
                        _broadcast_telemetry_to_laravel(
                            node_id=node_id,
                            channel=channel or "",
                            metric_type=metric_type,
                            value=latest_sample.value,
                            timestamp=latest_sample.ts or utcnow(),
                        )
                    )

                    def log_task_error(t):
                        try:
                            if t.done() and t.exception():
                                exc = t.exception()
                                if not isinstance(
                                    exc, (httpx.TimeoutException, httpx.RequestError)
                                ):
                                    logger.warning(
                                        f"[BROADCAST] Unhandled exception in broadcast task: {exc}",
                                        exc_info=True,
                                    )
                        except Exception:
                            pass

                    task.add_done_callback(log_task_error)
                except RuntimeError as e:
                    logger.debug(
                        f"[BROADCAST] Cannot create task (event loop may be closed): {e}"
                    )
                except Exception as e:
                    logger.warning(
                        f"[BROADCAST] Failed to create broadcast task: {e}",
                        exc_info=True,
                    )

    processing_duration = time.time() - start_time
    TELEMETRY_PROCESSING_DURATION.observe(processing_duration)
    TELEM_PROCESSED.inc(processed_count)
    TELEM_BATCH_SIZE.observe(processed_count)


async def _broadcast_telemetry_to_laravel(
    node_id: int,
    channel: str,
    metric_type: str,
    value: float,
    timestamp: datetime,
) -> None:
    """
    Вызывает Laravel API для broadcast телеметрии.
    """
    global _broadcast_error_count, _broadcast_last_error_time, _broadcast_backoff_until

    if _shutdown_event().is_set():
        logger.debug("[BROADCAST] Shutdown in progress, skipping telemetry broadcast")
        return

    current_time = time.time()
    if _broadcast_backoff_until is not None and current_time < _broadcast_backoff_until:
        logger.debug(
            "[BROADCAST] In backoff mode, skipping broadcast. "
            f"Backoff until: {_broadcast_backoff_until:.2f}, current: {current_time:.2f}, "
            f"error_count: {_broadcast_error_count}"
        )
        return

    s = get_settings()
    laravel_url = s.laravel_api_url if hasattr(s, "laravel_api_url") else None
    ingest_token = (
        s.history_logger_api_token
        if hasattr(s, "history_logger_api_token") and s.history_logger_api_token
        else (s.ingest_token if hasattr(s, "ingest_token") and s.ingest_token else None)
    )

    if not laravel_url:
        logger.warning(
            "[BROADCAST] Laravel API URL not configured, skipping telemetry broadcast. "
            "Set LARAVEL_API_URL environment variable."
        )
        return

    if not ingest_token:
        logger.warning(
            "[BROADCAST] Ingest token not configured, skipping telemetry broadcast. "
            "Set HISTORY_LOGGER_API_TOKEN or PY_INGEST_TOKEN environment variable."
        )
        return

    logger.info(
        f"[BROADCAST] Starting broadcast: node_id={node_id}, metric={metric_type}, url={laravel_url}"
    )

    try:
        if isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                timestamp_utc = timestamp.replace(tzinfo=timezone.utc)
                timestamp_ms = int(timestamp_utc.timestamp() * 1000)
            else:
                timestamp_ms = int(timestamp.timestamp() * 1000)
        else:
            timestamp_ms = int(timestamp * 1000)

        api_data = {
            "node_id": node_id,
            "channel": channel,
            "metric_type": metric_type,
            "value": value,
            "timestamp": timestamp_ms,
        }

        if _shutdown_event().is_set():
            logger.debug("[BROADCAST] Shutdown in progress, skipping HTTP request")
            return

        from common.http_client_pool import make_request

        api_start = time.time()
        response = await make_request(
            "post",
            f"{laravel_url}/api/python/broadcast/telemetry",
            endpoint="telemetry_broadcast",
            json=api_data,
            headers={
                "Authorization": f"Bearer {ingest_token}",
                "Content-Type": "application/json",
            },
        )
        api_duration = time.time() - api_start
        LARAVEL_API_DURATION.observe(api_duration)

        if response.status_code == 200:
            if _broadcast_error_count > 0:
                logger.info(
                    "[BROADCAST] Success after %s errors, resetting error count and backoff",
                    _broadcast_error_count,
                )
            _broadcast_error_count = 0
            _broadcast_backoff_until = None
            logger.info(
                f"[BROADCAST] Telemetry broadcasted successfully: node_id={node_id}, metric={metric_type}, value={value}"
            )
        else:
            _broadcast_error_count += 1
            _broadcast_last_error_time = current_time
            backoff_delay = _calculate_broadcast_backoff(_broadcast_error_count)
            _broadcast_backoff_until = current_time + backoff_delay

            logger.warning(
                "[BROADCAST] Failed to broadcast telemetry: status=%s, error_count=%s, backoff=%.2fs",
                response.status_code,
                _broadcast_error_count,
                backoff_delay,
                extra={
                    "node_id": node_id,
                    "metric_type": metric_type,
                    "status_code": response.status_code,
                    "response": response.text[:200],
                    "error_count": _broadcast_error_count,
                    "backoff_seconds": backoff_delay,
                },
            )
    except (httpx.TimeoutException, httpx.RequestError, httpx.NetworkError) as e:
        _broadcast_error_count += 1
        _broadcast_last_error_time = current_time
        backoff_delay = _calculate_broadcast_backoff(_broadcast_error_count)
        _broadcast_backoff_until = current_time + backoff_delay

        logger.warning(
            "[BROADCAST] Network error broadcasting telemetry: %s, error_count=%s, backoff=%.2fs",
            e,
            _broadcast_error_count,
            backoff_delay,
            extra={
                "node_id": node_id,
                "error_count": _broadcast_error_count,
                "backoff_seconds": backoff_delay,
            },
        )
    except Exception as e:
        _broadcast_error_count += 1
        _broadcast_last_error_time = current_time
        backoff_delay = _calculate_broadcast_backoff(_broadcast_error_count)
        _broadcast_backoff_until = current_time + backoff_delay

        logger.warning(
            "[BROADCAST] Error broadcasting telemetry: %s, error_count=%s, backoff=%.2fs",
            e,
            _broadcast_error_count,
            backoff_delay,
            extra={
                "node_id": node_id,
                "error_count": _broadcast_error_count,
                "backoff_seconds": backoff_delay,
            },
            exc_info=True,
        )


async def process_telemetry_queue() -> None:
    """
    Фоновая задача для обработки очереди телеметрии из Redis.
    """
    s = get_settings()
    last_flush = utcnow()

    logger.info("Starting telemetry queue processor")

    while not _shutdown_event().is_set():
        try:
            queue_start_time = time.time()
            queue_size = await _get_telemetry_queue().size()
            queue_duration = time.time() - queue_start_time
            REDIS_OPERATION_DURATION.observe(queue_duration)

            queue_age_start_time = time.time()
            queue_age = await _get_telemetry_queue().get_oldest_age_seconds()
            queue_age_duration = time.time() - queue_age_start_time
            REDIS_OPERATION_DURATION.observe(queue_age_duration)

            if queue_age is not None:
                TELEMETRY_QUEUE_AGE.set(queue_age)
            else:
                TELEMETRY_QUEUE_AGE.set(0.0)

            time_since_flush = (utcnow() - last_flush).total_seconds() * 1000

            should_flush = queue_size >= s.telemetry_batch_size or (
                time_since_flush >= s.telemetry_flush_ms and queue_size > 0
            )

            if should_flush:
                batch_size = min(s.telemetry_batch_size, queue_size)
                queue_items = await _get_telemetry_queue().pop_batch(batch_size)

                if queue_items:
                    samples = []
                    for item in queue_items:
                        sample = TelemetrySampleModel(
                            node_uid=item.node_uid,
                            zone_uid=item.zone_uid,
                            zone_id=None,
                            gh_uid=getattr(item, "gh_uid", None),
                            metric_type=item.metric_type,
                            value=item.value,
                            ts=item.ts,
                            raw=item.raw,
                            channel=item.channel,
                        )
                        samples.append(sample)

                    await process_telemetry_batch(samples)
                    last_flush = utcnow()

            await asyncio.sleep(s.queue_check_interval_sec)

        except Exception as e:
            logger.error(f"Error in telemetry queue processor: {e}", exc_info=True)
            await asyncio.sleep(s.queue_error_retry_delay_sec)

    logger.info(
        "Shutting down telemetry queue processor, processing remaining items..."
    )
    remaining_items = await _get_telemetry_queue().pop_batch(
        s.telemetry_batch_size * s.final_batch_multiplier
    )
    if remaining_items:
        samples = []
        for item in remaining_items:
            sample = TelemetrySampleModel(
                node_uid=item.node_uid,
                zone_uid=item.zone_uid,
                zone_id=None,
                gh_uid=getattr(item, "gh_uid", None),
                metric_type=item.metric_type,
                value=item.value,
                ts=item.ts,
                raw=item.raw,
                channel=item.channel,
            )
            samples.append(sample)
        await process_telemetry_batch(samples)
    logger.info("Telemetry queue processor stopped")
