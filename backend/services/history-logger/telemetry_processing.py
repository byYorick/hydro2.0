import asyncio
import logging
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

import state
from common.db import create_zone_event, execute, fetch
from common.env import get_settings
from common.redis_queue import TelemetryQueueItem
from common.utils.time import utcnow
from metrics import (
    DATABASE_ERRORS,
    LARAVEL_API_DURATION,
    REALTIME_DROPPED_UPDATES,
    REALTIME_FLUSH_LATENCY_MS,
    REALTIME_QUEUE_LEN,
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
_zone_greenhouse_cache: dict[int, int] = {}
_sensor_cache: "OrderedDict[tuple[int, Optional[int], str, str], int]" = OrderedDict()
_sensor_cache_max_size = int(os.getenv("SENSOR_CACHE_MAX_SIZE", "5000"))
_cache_last_update = 0.0
_cache_ttl = 60.0

# Backoff состояние для telemetry broadcast
_broadcast_error_count = 0
_broadcast_last_error_time: Optional[float] = None
_broadcast_backoff_until: Optional[float] = None

_realtime_updates: "OrderedDict[tuple, dict]" = OrderedDict()
_realtime_lock = asyncio.Lock()


def _normalize_metric_type(metric_type: str) -> str:
    return (metric_type or "").strip().upper()


def _infer_sensor_type(metric_type: str) -> str:
    normalized = _normalize_metric_type(metric_type)
    valid_types = {
        "PH",
        "EC",
        "TEMPERATURE",
        "HUMIDITY",
        "CO2",
        "LIGHT_INTENSITY",
        "WATER_LEVEL",
        "FLOW_RATE",
        "PUMP_CURRENT",
        "SOIL_MOISTURE",
        "PRESSURE",
        "WIND_SPEED",
        "WIND_DIRECTION",
        "OTHER",
    }
    if normalized in valid_types:
        return normalized
    return "OTHER"


def _build_sensor_label(metric_type: str, channel: Optional[str], sensor_type: str) -> str:
    if channel:
        return channel
    if metric_type:
        return metric_type
    return sensor_type


def _normalize_ts_for_db(sample_ts: Optional[datetime]) -> datetime:
    ts_value = sample_ts or utcnow()
    if getattr(ts_value, "tzinfo", None):
        return ts_value.astimezone(timezone.utc).replace(tzinfo=None)
    return ts_value.replace(tzinfo=None)


def _sensor_cache_touch(key: tuple[int, Optional[int], str, str]) -> None:
    if hasattr(_sensor_cache, "move_to_end"):
        _sensor_cache.move_to_end(key)


def _sensor_cache_pop_oldest() -> None:
    try:
        _sensor_cache.popitem(last=False)
        return
    except TypeError:
        pass
    try:
        oldest_key = next(iter(_sensor_cache))
    except StopIteration:
        return
    del _sensor_cache[oldest_key]


def _sensor_cache_get(key: tuple[int, Optional[int], str, str]) -> Optional[int]:
    sensor_id = _sensor_cache.get(key)
    if sensor_id is not None:
        _sensor_cache_touch(key)
    return sensor_id


def _sensor_cache_set(key: tuple[int, Optional[int], str, str], sensor_id: int) -> None:
    _sensor_cache[key] = sensor_id
    _sensor_cache_touch(key)
    if _sensor_cache_max_size <= 0:
        return
    while len(_sensor_cache) > _sensor_cache_max_size:
        _sensor_cache_pop_oldest()


def _get_telemetry_queue():
    return state.telemetry_queue


def _shutdown_event():
    return state.shutdown_event


def _to_timestamp_ms(timestamp: Optional[datetime]) -> int:
    if timestamp is None:
        return int(time.time() * 1000)

    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp_utc = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp_utc = timestamp
        return int(timestamp_utc.timestamp() * 1000)

    return int(timestamp * 1000)


def _build_realtime_key(
    sensor_id: Optional[int],
    zone_id: int,
    node_id: Optional[int],
    metric_type: str,
    channel: Optional[str],
) -> tuple:
    if sensor_id is not None:
        return ("sensor", sensor_id)
    return ("legacy", zone_id, node_id or 0, metric_type or "", channel or "")


def _build_realtime_key_from_update(update: dict) -> tuple:
    return (
        "legacy",
        int(update.get("zone_id") or 0),
        int(update.get("node_id") or 0),
        str(update.get("metric_type") or ""),
        str(update.get("channel") or ""),
    )


async def _enqueue_realtime_update(key: tuple, update: dict) -> None:
    s = get_settings()
    async with _realtime_lock:
        _realtime_updates[key] = update
        _realtime_updates.move_to_end(key)

        max_size = getattr(s, "realtime_queue_max_size", 0)
        if max_size > 0 and len(_realtime_updates) > max_size:
            _realtime_updates.popitem(last=False)
            REALTIME_DROPPED_UPDATES.labels(reason="queue_full").inc()

        REALTIME_QUEUE_LEN.set(len(_realtime_updates))


async def _pop_realtime_updates(limit: int) -> list[dict]:
    async with _realtime_lock:
        if not _realtime_updates:
            return []

        count = min(limit, len(_realtime_updates))
        updates = []
        for _ in range(count):
            _, update = _realtime_updates.popitem(last=False)
            updates.append(update)

        REALTIME_QUEUE_LEN.set(len(_realtime_updates))
        return updates


async def _requeue_realtime_updates(updates: list[dict]) -> None:
    s = get_settings()
    async with _realtime_lock:
        for update in updates:
            key = _build_realtime_key_from_update(update)
            _realtime_updates[key] = update
            _realtime_updates.move_to_end(key)

            max_size = getattr(s, "realtime_queue_max_size", 0)
            if max_size > 0 and len(_realtime_updates) > max_size:
                _realtime_updates.popitem(last=False)
                REALTIME_DROPPED_UPDATES.labels(reason="queue_full").inc()

        REALTIME_QUEUE_LEN.set(len(_realtime_updates))


def _broadcast_in_backoff(current_time: float) -> bool:
    return _broadcast_backoff_until is not None and current_time < _broadcast_backoff_until


async def _broadcast_telemetry_batch_to_laravel(updates: list[dict]) -> bool:
    """
    Отправляет batched realtime updates в Laravel.
    """
    global _broadcast_error_count, _broadcast_last_error_time, _broadcast_backoff_until

    if _shutdown_event().is_set():
        logger.debug("[BROADCAST] Shutdown in progress, skipping telemetry batch broadcast")
        return False

    current_time = time.time()
    if _broadcast_in_backoff(current_time):
        logger.debug(
            "[BROADCAST] In backoff mode, skipping batch broadcast. "
            f"Backoff until: {_broadcast_backoff_until:.2f}, current: {current_time:.2f}, "
            f"error_count: {_broadcast_error_count}"
        )
        return False

    s = get_settings()
    laravel_url = s.laravel_api_url if hasattr(s, "laravel_api_url") else None
    ingest_token = (
        s.history_logger_api_token
        if hasattr(s, "history_logger_api_token") and s.history_logger_api_token
        else (s.ingest_token if hasattr(s, "ingest_token") and s.ingest_token else None)
    )

    if not laravel_url:
        logger.warning(
            "[BROADCAST] Laravel API URL not configured, skipping telemetry batch broadcast."
        )
        return True

    if not ingest_token:
        logger.warning(
            "[BROADCAST] Ingest token not configured, skipping telemetry batch broadcast."
        )
        return True

    logger.info(
        "[BROADCAST] Sending telemetry batch: updates=%s, url=%s",
        len(updates),
        laravel_url,
    )

    try:
        from common.http_client_pool import make_request

        api_start = time.time()
        response = await make_request(
            "post",
            f"{laravel_url}/api/internal/realtime/telemetry-batch",
            endpoint="telemetry_broadcast_batch",
            json={"updates": updates},
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
            return True

        _broadcast_error_count += 1
        _broadcast_last_error_time = current_time
        backoff_delay = _calculate_broadcast_backoff(_broadcast_error_count)
        _broadcast_backoff_until = current_time + backoff_delay

        logger.warning(
            "[BROADCAST] Failed to broadcast telemetry batch: status=%s, error_count=%s, backoff=%.2fs",
            response.status_code,
            _broadcast_error_count,
            backoff_delay,
            extra={
                "status_code": response.status_code,
                "response": response.text[:200],
                "error_count": _broadcast_error_count,
                "backoff_seconds": backoff_delay,
            },
        )
        return False
    except (httpx.TimeoutException, httpx.RequestError, httpx.NetworkError) as e:
        _broadcast_error_count += 1
        _broadcast_last_error_time = current_time
        backoff_delay = _calculate_broadcast_backoff(_broadcast_error_count)
        _broadcast_backoff_until = current_time + backoff_delay

        logger.warning(
            "[BROADCAST] Network error broadcasting telemetry batch: %s, error_count=%s, backoff=%.2fs",
            e,
            _broadcast_error_count,
            backoff_delay,
            extra={
                "error_count": _broadcast_error_count,
                "backoff_seconds": backoff_delay,
            },
        )
        return False
    except Exception as e:
        _broadcast_error_count += 1
        _broadcast_last_error_time = current_time
        backoff_delay = _calculate_broadcast_backoff(_broadcast_error_count)
        _broadcast_backoff_until = current_time + backoff_delay

        logger.warning(
            "[BROADCAST] Error broadcasting telemetry batch: %s, error_count=%s, backoff=%.2fs",
            e,
            _broadcast_error_count,
            backoff_delay,
            extra={
                "error_count": _broadcast_error_count,
                "backoff_seconds": backoff_delay,
            },
            exc_info=True,
        )
        return False


async def _flush_realtime_updates(force: bool = False) -> None:
    s = get_settings()

    if not force and _broadcast_in_backoff(time.time()):
        return

    updates = await _pop_realtime_updates(
        getattr(s, "realtime_batch_max_updates", 200)
    )
    if not updates:
        return

    flush_start = time.time()
    success = await _broadcast_telemetry_batch_to_laravel(updates)
    REALTIME_FLUSH_LATENCY_MS.observe((time.time() - flush_start) * 1000)

    if not success and not force:
        await _requeue_realtime_updates(updates)


async def process_realtime_queue() -> None:
    """
    Фоновая задача для batched realtime telemetry.
    """
    s = get_settings()
    logger.info("Starting realtime telemetry broadcaster")

    while not _shutdown_event().is_set():
        try:
            await _flush_realtime_updates()
            await asyncio.sleep(getattr(s, "realtime_flush_ms", 500) / 1000)
        except Exception as e:
            logger.error("Error in realtime telemetry broadcaster: %s", e, exc_info=True)
            await asyncio.sleep(s.queue_error_retry_delay_sec)

    logger.info("Realtime telemetry broadcaster shutting down, flushing remaining updates...")
    await _flush_realtime_updates(force=True)
    logger.info("Realtime telemetry broadcaster stopped")

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
            SELECT z.id, z.uid, g.uid as gh_uid, g.id as greenhouse_id
            FROM zones z
            JOIN greenhouses g ON g.id = z.greenhouse_id
            """
        )
        _zone_cache.clear()
        _zone_greenhouse_cache.clear()
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
            greenhouse_id = zone.get("greenhouse_id")
            if greenhouse_id is not None:
                _zone_greenhouse_cache[zone_id] = greenhouse_id

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

    resolved_samples: list[dict] = []
    zone_ids_for_greenhouse: set[int] = set()

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

        resolved_samples.append(
            {
                "sample": sample,
                "zone_id": zone_id,
                "node_id": node_id,
            }
        )
        zone_ids_for_greenhouse.add(zone_id)

    if not resolved_samples:
        return

    missing_zone_ids = [
        zone_id
        for zone_id in zone_ids_for_greenhouse
        if zone_id not in _zone_greenhouse_cache
    ]
    if missing_zone_ids:
        zone_rows = await fetch(
            """
            SELECT id, greenhouse_id
            FROM zones
            WHERE id = ANY($1)
            """,
            missing_zone_ids,
        )
        for zone in zone_rows:
            zone_id = zone.get("id")
            greenhouse_id = zone.get("greenhouse_id")
            if zone_id is not None and greenhouse_id is not None:
                _zone_greenhouse_cache[zone_id] = greenhouse_id

    missing_sensor_keys: set[tuple[int, Optional[int], str, str]] = set()
    for item in resolved_samples:
        sample = item["sample"]
        sensor_type = _infer_sensor_type(sample.metric_type)
        sensor_label = _build_sensor_label(sample.metric_type, sample.channel, sensor_type)
        sensor_key = (item["zone_id"], item["node_id"], sensor_type, sensor_label)
        item["sensor_key"] = sensor_key
        item["sensor_type"] = sensor_type
        item["sensor_label"] = sensor_label
        if _sensor_cache_get(sensor_key) is None:
            missing_sensor_keys.add(sensor_key)

    if missing_sensor_keys:
        zone_ids = list({key[0] for key in missing_sensor_keys})
        node_ids = list({key[1] for key in missing_sensor_keys if key[1] is not None})
        existing_rows = []
        if zone_ids:
            if node_ids:
                existing_rows = await fetch(
                    """
                    SELECT id, zone_id, node_id, type, label
                    FROM sensors
                    WHERE zone_id = ANY($1)
                      AND (node_id = ANY($2) OR node_id IS NULL)
                    """,
                    zone_ids,
                    node_ids,
                )
            else:
                existing_rows = await fetch(
                    """
                    SELECT id, zone_id, node_id, type, label
                    FROM sensors
                    WHERE zone_id = ANY($1)
                      AND node_id IS NULL
                    """,
                    zone_ids,
                )

        for row in existing_rows:
            zone_id = row.get("zone_id")
            sensor_type = row.get("type")
            sensor_label = row.get("label")
            sensor_id = row.get("id")
            if zone_id is not None and sensor_type and sensor_label and sensor_id is not None:
                sensor_key = (zone_id, row.get("node_id"), sensor_type, sensor_label)
                _sensor_cache_set(sensor_key, sensor_id)

        to_create = [
            key for key in missing_sensor_keys if _sensor_cache_get(key) is None
        ]
        if to_create:
            values_list = []
            params_list = []
            param_index = 1
            for zone_id, node_id, sensor_type, sensor_label in to_create:
                greenhouse_id = _zone_greenhouse_cache.get(zone_id)
                if greenhouse_id is None:
                    logger.warning(
                        "Greenhouse not found for zone_id=%s, skipping sensor creation",
                        zone_id,
                    )
                    continue
                values_list.append(
                    f"(${param_index}, ${param_index + 1}, ${param_index + 2}, ${param_index + 3}, "
                    f"${param_index + 4}, ${param_index + 5}, ${param_index + 6}, NOW(), NOW())"
                )
                params_list.extend(
                    [
                        greenhouse_id,
                        zone_id,
                        node_id,
                        "inside",
                        sensor_type,
                        sensor_label,
                        True,
                    ]
                )
                param_index += 7

            if values_list:
                query = f"""
                    INSERT INTO sensors (
                        greenhouse_id, zone_id, node_id, scope, type, label, is_active,
                        created_at, updated_at
                    )
                    VALUES {', '.join(values_list)}
                    ON CONFLICT (zone_id, node_id, scope, type, label)
                    DO UPDATE SET
                        updated_at = EXCLUDED.updated_at
                    RETURNING id, zone_id, node_id, type, label
                """
                created_rows = await fetch(query, *params_list)
                for row in created_rows:
                    zone_id = row.get("zone_id")
                    sensor_type = row.get("type")
                    sensor_label = row.get("label")
                    sensor_id = row.get("id")
                    if (
                        zone_id is not None
                        and sensor_type
                        and sensor_label
                        and sensor_id is not None
                    ):
                        sensor_key = (
                            zone_id,
                            row.get("node_id"),
                            sensor_type,
                            sensor_label,
                        )
                        _sensor_cache_set(sensor_key, sensor_id)

    resolved_with_sensor: list[dict] = []
    for item in resolved_samples:
        sensor_id = _sensor_cache_get(item["sensor_key"])
        if sensor_id is None:
            logger.warning(
                "Sensor not resolved for telemetry sample",
                extra={
                    "zone_id": item["zone_id"],
                    "node_id": item["node_id"],
                    "metric_type": item["sample"].metric_type,
                    "channel": item["sample"].channel,
                },
            )
            TELEMETRY_DROPPED.labels(reason="sensor_not_resolved").inc()
            continue
        item["sensor_id"] = sensor_id
        resolved_with_sensor.append(item)

    if not resolved_with_sensor:
        return

    broadcast_groups: dict[
        tuple[int, str, Optional[int], Optional[str]], list[dict]
    ] = {}
    for item in resolved_with_sensor:
        sample = item["sample"]
        key = (item["zone_id"], sample.metric_type, item["node_id"], sample.channel)
        broadcast_groups.setdefault(key, []).append(item)

    telemetry_last_updates: dict[int, dict] = {}
    for item in resolved_with_sensor:
        sample = item["sample"]
        sensor_id = item["sensor_id"]
        sample_ts = _normalize_ts_for_db(sample.ts)
        existing_ts = telemetry_last_updates.get(sensor_id, {}).get("ts")
        if existing_ts is None or sample_ts > existing_ts:
            telemetry_last_updates[sensor_id] = {
                "value": sample.value,
                "ts": sample_ts,
                "quality": "GOOD",
                "updated_at": sample_ts,
            }

    if telemetry_last_updates:
        try:
            values_list = []
            params_list = []
            param_index = 1
            for sensor_id, update_data in telemetry_last_updates.items():
                values_list.append(
                    f"(${param_index}, ${param_index + 1}, ${param_index + 2}, "
                    f"${param_index + 3}, ${param_index + 4})"
                )
                params_list.extend(
                    [
                        sensor_id,
                        update_data["value"],
                        update_data["ts"],
                        update_data["quality"],
                        update_data["updated_at"],
                    ]
                )
                param_index += 5

            if values_list:
                query = f"""
                    INSERT INTO telemetry_last (
                        sensor_id, last_value, last_ts, last_quality, updated_at
                    )
                    VALUES {', '.join(values_list)}
                    ON CONFLICT (sensor_id)
                    DO UPDATE SET
                        last_value = EXCLUDED.last_value,
                        last_ts = EXCLUDED.last_ts,
                        last_quality = EXCLUDED.last_quality,
                        updated_at = EXCLUDED.updated_at
                """
                await execute(query, *params_list)
                logger.debug(
                    "Batch upserted %s telemetry_last records",
                    len(telemetry_last_updates),
                )
        except Exception as e:
            logger.error(f"Failed to batch upsert telemetry_last: {e}", exc_info=True)
            for sensor_id, update_data in telemetry_last_updates.items():
                try:
                    await execute(
                        """
                        INSERT INTO telemetry_last (
                            sensor_id, last_value, last_ts, last_quality, updated_at
                        )
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (sensor_id)
                        DO UPDATE SET
                            last_value = EXCLUDED.last_value,
                            last_ts = EXCLUDED.last_ts,
                            last_quality = EXCLUDED.last_quality,
                            updated_at = EXCLUDED.updated_at
                        """,
                        sensor_id,
                        update_data["value"],
                        update_data["ts"],
                        update_data["quality"],
                        update_data["updated_at"],
                    )
                except Exception as e2:
                    logger.error(
                        "Failed to upsert telemetry_last for sensor_id=%s: %s",
                        sensor_id,
                        e2,
                    )

    processed_count = 0
    values_list = []
    params_list = []
    param_index = 1
    for item in resolved_with_sensor:
        sample = item["sample"]
        metadata = {
            "metric_type": sample.metric_type,
            "channel": sample.channel,
            "node_uid": sample.node_uid,
        }
        if sample.raw is not None:
            metadata["raw"] = sample.raw
        if metadata and not metadata.get("channel"):
            metadata.pop("channel", None)
        if metadata and not metadata.get("node_uid"):
            metadata.pop("node_uid", None)
        values_list.append(
            f"(${param_index}, ${param_index + 1}, ${param_index + 2}, "
            f"${param_index + 3}, ${param_index + 4}, ${param_index + 5})"
        )
        params_list.extend(
            [
                item["sensor_id"],
                _normalize_ts_for_db(sample.ts),
                item["zone_id"],
                sample.value,
                "GOOD",
                metadata or None,
            ]
        )
        param_index += 6

    if values_list:
        query = f"""
            INSERT INTO telemetry_samples (
                sensor_id, ts, zone_id, value, quality, metadata
            )
            VALUES {', '.join(values_list)}
        """
        try:
            await execute(query, *params_list)
            processed_count = len(resolved_with_sensor)
            logger.info(
                "[TELEMETRY] Written: count=%s, unique_sensors=%s",
                processed_count,
                len(telemetry_last_updates),
            )
        except Exception as e:
            error_type = type(e).__name__
            DATABASE_ERRORS.labels(error_type=error_type).inc()
            logger.error(
                "Failed to insert telemetry batch",
                extra={
                    "error_type": error_type,
                    "error": str(e),
                    "samples_count": len(resolved_with_sensor),
                },
                exc_info=True,
            )

    for (zone_id, metric_type, node_id, channel), group_items in broadcast_groups.items():
        if not group_items:
            continue

        latest_item = max(
            group_items,
            key=lambda item: item["sample"].ts
            if item["sample"].ts
            else datetime.min.replace(tzinfo=None),
        )
        latest_sample = latest_item["sample"]

        if not zone_id or not node_id or _shutdown_event().is_set():
            REALTIME_DROPPED_UPDATES.labels(reason="missing_zone_or_node").inc()
            continue

        update = {
            "zone_id": zone_id,
            "node_id": node_id,
            "channel": channel or None,
            "metric_type": metric_type,
            "value": latest_sample.value,
            "timestamp": _to_timestamp_ms(latest_sample.ts),
        }
        realtime_key = _build_realtime_key(
            latest_item.get("sensor_id"),
            zone_id,
            node_id,
            metric_type,
            channel,
        )
        await _enqueue_realtime_update(realtime_key, update)

    processing_duration = time.time() - start_time
    TELEMETRY_PROCESSING_DURATION.observe(processing_duration)
    TELEM_PROCESSED.inc(processed_count)
    TELEM_BATCH_SIZE.observe(processed_count)


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
