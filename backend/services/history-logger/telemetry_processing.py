from telemetry.dependencies import (
    bind_dependencies as bind_telemetry_dependencies,
    snapshot as telemetry_dependency_snapshot,
)
import asyncio
import logging
import os
import time as time
from collections import OrderedDict
from dataclasses import dataclass as dataclass, field as field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict as Dict, List, Optional, Set

import asyncpg as asyncpg
import httpx as httpx

import state as state
from common.db import create_zone_event, execute, fetch
from common.env import get_settings
from common.infra_alerts import send_infra_alert, send_infra_resolved_alert
from common.simulation_events import record_simulation_event_throttled
from common.redis_queue import PopBatchResult, QueueEntry, TelemetryQueueItem as TelemetryQueueItem
from common.utils.time import utcnow
from common.trace_context import clear_trace_id as clear_trace_id, set_trace_id_from_payload as set_trace_id_from_payload
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
    TELEMETRY_DEAD_LIST_SIZE,
    TELEMETRY_PG_WRITE_FAILED,
    TELEMETRY_PROCESSING_DURATION,
    TELEMETRY_PROCESSING_RECLAIMED,
    TELEMETRY_PROCESSING_SIZE,
    TELEMETRY_PROCESSING_STUCK,
    TELEMETRY_QUEUE_AGE,
    TELEMETRY_REQUEUE_DUPLICATE_RISK,
    TELEMETRY_SAMPLES_JOIN_MISMATCH,
)
from models import TelemetryPayloadModel as TelemetryPayloadModel, TelemetrySampleModel
from telemetry.anomaly_alerts import (
    emit_telemetry_anomaly_alert as _emit_telemetry_anomaly_alert,
    emit_telemetry_anomaly_resolved_alert as _emit_telemetry_anomaly_resolved_alert,
)
from telemetry import anomaly_alerts as telemetry_anomaly_module
from telemetry.ingress import (
    REDIS_PUSH_MAX_RETRIES as REDIS_PUSH_MAX_RETRIES,
    REDIS_PUSH_RETRY_BACKOFF_BASE as REDIS_PUSH_RETRY_BACKOFF_BASE,
    handle_telemetry as _handle_telemetry_impl,
    push_with_retry as _push_with_retry,
)
from telemetry.helpers import (
    build_anomaly_throttle_key as _build_anomaly_throttle_key,  # noqa: F401 - legacy facade re-export
    build_realtime_key as _build_realtime_key,
    build_realtime_key_from_update as _build_realtime_key_from_update,
    build_sensor_label as _build_sensor_label,
    effective_anomaly_throttle_sec as _effective_anomaly_throttle_sec,  # noqa: F401 - legacy facade re-export
    filter_existing_sensor_ids as _filter_existing_sensor_ids,
    infer_sensor_scope as _infer_sensor_scope,
    infer_sensor_type as _infer_sensor_type,
    is_sensor_fk_error as _is_sensor_fk_error,
    is_temp_namespace as _is_temp_namespace,
    normalize_metric_type as _normalize_metric_type,  # noqa: F401 - legacy facade re-export
    normalize_ts_for_db as _normalize_ts_for_db,
    parse_node_info as _parse_node_info,
    to_timestamp_ms as _to_timestamp_ms,
)
from telemetry import helpers as telemetry_helpers_module  # noqa: F401 - legacy facade re-export
from utils import (
    MAX_PAYLOAD_SIZE as MAX_PAYLOAD_SIZE,
    _calculate_broadcast_backoff,
    _extract_channel_from_topic as _extract_channel_from_topic,
    _extract_gh_uid as _extract_gh_uid,
    _extract_node_uid as _extract_node_uid,
    _extract_zone_uid as _extract_zone_uid,
    _filter_raw_data as _filter_raw_data,
    _parse_json as _parse_json,
)

logger = logging.getLogger(__name__)


from telemetry.runtime_records import PgTransportError as PgTransportError, TelemetryBatchResult
from telemetry.runtime_batch import RuntimeBatch, RuntimeBatchPorts


def _runtime_batch() -> RuntimeBatch:
    dependencies = telemetry_dependency_snapshot(
        {
            'TELEMETRY_PROCESSING_DURATION': TELEMETRY_PROCESSING_DURATION,
            'TELEM_BATCH_SIZE': TELEM_BATCH_SIZE,
            'TELEM_PROCESSED': TELEM_PROCESSED,
            'get_settings': get_settings,
        }
    )
    return RuntimeBatch(
        RuntimeBatchPorts(
            telemetry_processing_duration=lambda: dependencies.TELEMETRY_PROCESSING_DURATION,
            telem_batch_size=lambda: dependencies.TELEM_BATCH_SIZE,
            telem_processed=lambda: dependencies.TELEM_PROCESSED,
            cache_last_update=lambda: _cache_last_update,
            cache_ttl=lambda: _cache_ttl,
            enqueue_committed_realtime=lambda *args, **kwargs: _enqueue_committed_realtime(*args, **kwargs),
            evaluate_solution_temp_thresholds=lambda *args, **kwargs: _evaluate_solution_temp_thresholds(
                *args, **kwargs
            ),
            normalize_batch_samples=lambda *args, **kwargs: _normalize_batch_samples(*args, **kwargs),
            persist_batch_samples=lambda *args, **kwargs: _persist_batch_samples(*args, **kwargs),
            recover_batch_assignments=lambda *args, **kwargs: _recover_batch_assignments(*args, **kwargs),
            resolve_batch_nodes=lambda *args, **kwargs: _resolve_batch_nodes(*args, **kwargs),
            resolve_batch_sensors=lambda *args, **kwargs: _resolve_batch_sensors(*args, **kwargs),
            resolve_batch_zones=lambda *args, **kwargs: _resolve_batch_zones(*args, **kwargs),
            get_settings=dependencies.get_settings,
            refresh_caches=lambda *args, **kwargs: refresh_caches(*args, **kwargs),
        )
    )


from telemetry.runtime_zone_resolution import RuntimeZoneResolution, RuntimeZoneResolutionPorts


def _runtime_zone_resolution() -> RuntimeZoneResolution:
    dependencies = telemetry_dependency_snapshot(
        {
            '_emit_telemetry_anomaly_alert': _emit_telemetry_anomaly_alert,
            '_is_temp_namespace': _is_temp_namespace,
            'fetch': fetch,
            'logger': logger,
        }
    )
    return RuntimeZoneResolution(
        RuntimeZoneResolutionPorts(
            emit_telemetry_anomaly_alert=dependencies._emit_telemetry_anomaly_alert,
            is_temp_namespace=dependencies._is_temp_namespace,
            log_warning_throttled=lambda *args, **kwargs: _log_warning_throttled(*args, **kwargs),
            zone_cache=lambda: _zone_cache,
            fetch=dependencies.fetch,
            logger=lambda: dependencies.logger,
        )
    )


from telemetry.runtime_node_resolution import RuntimeNodeResolution, RuntimeNodeResolutionPorts


def _runtime_node_resolution() -> RuntimeNodeResolution:
    dependencies = telemetry_dependency_snapshot(
        {
            '_emit_telemetry_anomaly_alert': _emit_telemetry_anomaly_alert,
            '_emit_telemetry_anomaly_resolved_alert': _emit_telemetry_anomaly_resolved_alert,
            '_is_temp_namespace': _is_temp_namespace,
            'fetch': fetch,
            'logger': logger,
        }
    )
    return RuntimeNodeResolution(
        RuntimeNodeResolutionPorts(
            emit_telemetry_anomaly_alert=dependencies._emit_telemetry_anomaly_alert,
            emit_telemetry_anomaly_resolved_alert=dependencies._emit_telemetry_anomaly_resolved_alert,
            is_temp_namespace=dependencies._is_temp_namespace,
            log_warning_throttled=lambda *args, **kwargs: _log_warning_throttled(*args, **kwargs),
            node_cache=lambda: _node_cache,
            node_unassigned_last_seen=lambda: _node_unassigned_last_seen,
            node_unassigned_recovery_grace_sec=lambda: _node_unassigned_recovery_grace_sec,
            prewarm_stale_node_assignments=lambda *args, **kwargs: _prewarm_stale_node_assignments(*args, **kwargs),
            zone_greenhouse_cache=lambda: _zone_greenhouse_cache,
            fetch=dependencies.fetch,
            logger=lambda: dependencies.logger,
        )
    )


from telemetry.runtime_normalization import RuntimeNormalization, RuntimeNormalizationPorts


def _runtime_normalization() -> RuntimeNormalization:
    dependencies = telemetry_dependency_snapshot(
        {
            'TELEMETRY_DROPPED': TELEMETRY_DROPPED,
            '_emit_telemetry_anomaly_alert': _emit_telemetry_anomaly_alert,
            '_is_temp_namespace': _is_temp_namespace,
            '_parse_node_info': _parse_node_info,
            'create_zone_event': create_zone_event,
            'fetch': fetch,
            'logger': logger,
            'timezone': timezone,
            'utcnow': utcnow,
        }
    )
    return RuntimeNormalization(
        RuntimeNormalizationPorts(
            telemetry_dropped=lambda: dependencies.TELEMETRY_DROPPED,
            emit_telemetry_anomaly_alert=dependencies._emit_telemetry_anomaly_alert,
            is_temp_namespace=dependencies._is_temp_namespace,
            log_warning_throttled=lambda *args, **kwargs: _log_warning_throttled(*args, **kwargs),
            node_cache=lambda: _node_cache,
            node_unassigned_last_seen=lambda: _node_unassigned_last_seen,
            parse_node_info=dependencies._parse_node_info,
            create_zone_event=dependencies.create_zone_event,
            fetch=dependencies.fetch,
            logger=lambda: dependencies.logger,
            timezone=dependencies.timezone,
            utcnow=dependencies.utcnow,
        )
    )


from telemetry.runtime_sensor_resolution import RuntimeSensorResolution, RuntimeSensorResolutionPorts


def _runtime_sensor_resolution() -> RuntimeSensorResolution:
    dependencies = telemetry_dependency_snapshot(
        {
            'TELEMETRY_DROPPED': TELEMETRY_DROPPED,
            'TELEMETRY_PG_WRITE_FAILED': TELEMETRY_PG_WRITE_FAILED,
            '_build_sensor_label': _build_sensor_label,
            '_filter_existing_sensor_ids': _filter_existing_sensor_ids,
            '_infer_sensor_scope': _infer_sensor_scope,
            '_infer_sensor_type': _infer_sensor_type,
            '_is_sensor_fk_error': _is_sensor_fk_error,
            'fetch': fetch,
            'logger': logger,
        }
    )
    return RuntimeSensorResolution(
        RuntimeSensorResolutionPorts(
            telemetry_dropped=lambda: dependencies.TELEMETRY_DROPPED,
            telemetry_pg_write_failed=lambda: dependencies.TELEMETRY_PG_WRITE_FAILED,
            append_dead_entry=lambda *args, **kwargs: _append_dead_entry(*args, **kwargs),
            build_sensor_label=dependencies._build_sensor_label,
            create_sensors_per_item=lambda *args, **kwargs: _create_sensors_per_item(*args, **kwargs),
            filter_existing_sensor_ids=dependencies._filter_existing_sensor_ids,
            infer_sensor_scope=dependencies._infer_sensor_scope,
            infer_sensor_type=dependencies._infer_sensor_type,
            is_pg_transport_error=lambda *args, **kwargs: _is_pg_transport_error(*args, **kwargs),
            is_sensor_fk_error=dependencies._is_sensor_fk_error,
            node_cache=lambda: _node_cache,
            sensor_cache=lambda: _sensor_cache,
            sensor_cache_get=lambda *args, **kwargs: _sensor_cache_get(*args, **kwargs),
            sensor_cache_set=lambda *args, **kwargs: _sensor_cache_set(*args, **kwargs),
            set_cache_last_update=lambda *args, **kwargs: _set_cache_last_update(*args, **kwargs),
            zone_cache=lambda: _zone_cache,
            zone_greenhouse_cache=lambda: _zone_greenhouse_cache,
            fetch=dependencies.fetch,
            logger=lambda: dependencies.logger,
        )
    )


from telemetry.runtime_cache import RuntimeCache, RuntimeCachePorts


def _runtime_cache() -> RuntimeCache:
    dependencies = telemetry_dependency_snapshot(
        {'_parse_node_info': _parse_node_info, 'fetch': fetch, 'logger': logger}
    )
    return RuntimeCache(
        RuntimeCachePorts(
            node_cache=lambda: _node_cache,
            parse_node_info=dependencies._parse_node_info,
            sensor_cache=lambda: _sensor_cache,
            sensor_cache_max_size=lambda: _sensor_cache_max_size,
            sensor_cache_pop_oldest=lambda *args, **kwargs: _sensor_cache_pop_oldest(*args, **kwargs),
            sensor_cache_touch=lambda *args, **kwargs: _sensor_cache_touch(*args, **kwargs),
            set_cache_last_update=lambda *args, **kwargs: _set_cache_last_update(*args, **kwargs),
            store_node_cache_entry=lambda *args, **kwargs: _store_node_cache_entry(*args, **kwargs),
            zone_cache=lambda: _zone_cache,
            zone_greenhouse_cache=lambda: _zone_greenhouse_cache,
            fetch=dependencies.fetch,
            logger=lambda: dependencies.logger,
            refresh_node_cache_for_uid=lambda *args, **kwargs: refresh_node_cache_for_uid(*args, **kwargs),
        )
    )


from telemetry.runtime_persistence import RuntimePersistence, RuntimePersistencePorts


def _runtime_persistence() -> RuntimePersistence:
    dependencies = telemetry_dependency_snapshot(
        {
            'DATABASE_ERRORS': DATABASE_ERRORS,
            'TELEMETRY_PG_WRITE_FAILED': TELEMETRY_PG_WRITE_FAILED,
            'TELEMETRY_SAMPLES_JOIN_MISMATCH': TELEMETRY_SAMPLES_JOIN_MISMATCH,
            '_is_sensor_fk_error': _is_sensor_fk_error,
            '_normalize_ts_for_db': _normalize_ts_for_db,
            'datetime': datetime,
            'execute': execute,
            'fetch': fetch,
            'logger': logger,
            'record_simulation_event_throttled': record_simulation_event_throttled,
            'timedelta': timedelta,
        }
    )
    return RuntimePersistence(
        RuntimePersistencePorts(
            database_errors=lambda: dependencies.DATABASE_ERRORS,
            simulation_telemetry_events_enabled=lambda: SIMULATION_TELEMETRY_EVENTS_ENABLED,
            simulation_telemetry_event_interval_sec=lambda: SIMULATION_TELEMETRY_EVENT_INTERVAL_SEC,
            telemetry_pg_write_failed=lambda: dependencies.TELEMETRY_PG_WRITE_FAILED,
            telemetry_samples_join_mismatch=lambda: dependencies.TELEMETRY_SAMPLES_JOIN_MISMATCH,
            append_dead_entry=lambda *args, **kwargs: _append_dead_entry(*args, **kwargs),
            append_requeue_entry=lambda *args, **kwargs: _append_requeue_entry(*args, **kwargs),
            build_telemetry_last_updates=lambda *args, **kwargs: _build_telemetry_last_updates(*args, **kwargs),
            handle_samples_join_mismatch=lambda *args, **kwargs: _handle_samples_join_mismatch(*args, **kwargs),
            insert_telemetry_sample_item=lambda *args, **kwargs: _insert_telemetry_sample_item(*args, **kwargs),
            is_pg_transport_error=lambda *args, **kwargs: _is_pg_transport_error(*args, **kwargs),
            is_sensor_fk_error=dependencies._is_sensor_fk_error,
            item_is_writable=lambda *args, **kwargs: _item_is_writable(*args, **kwargs),
            items_for_sensor=lambda *args, **kwargs: _items_for_sensor(*args, **kwargs),
            normalize_ts_for_db=dependencies._normalize_ts_for_db,
            persist_quality_for_sample=lambda *args, **kwargs: _persist_quality_for_sample(*args, **kwargs),
            sensor_cache=lambda: _sensor_cache,
            tracked_entry_ids=lambda *args, **kwargs: _tracked_entry_ids(*args, **kwargs),
            ts_key=lambda *args, **kwargs: _ts_key(*args, **kwargs),
            upsert_telemetry_last_batch=lambda *args, **kwargs: _upsert_telemetry_last_batch(*args, **kwargs),
            upsert_telemetry_last_for_sensor=lambda *args, **kwargs: _upsert_telemetry_last_for_sensor(*args, **kwargs),
            datetime=dependencies.datetime,
            execute=dependencies.execute,
            fetch=dependencies.fetch,
            logger=lambda: dependencies.logger,
            record_simulation_event_throttled=dependencies.record_simulation_event_throttled,
            timedelta=dependencies.timedelta,
        )
    )


from telemetry.runtime_realtime import RuntimeRealtime, RuntimeRealtimePorts


def _runtime_realtime() -> RuntimeRealtime:
    dependencies = telemetry_dependency_snapshot(
        {
            'LARAVEL_API_DURATION': LARAVEL_API_DURATION,
            'REALTIME_DROPPED_UPDATES': REALTIME_DROPPED_UPDATES,
            'REALTIME_FLUSH_LATENCY_MS': REALTIME_FLUSH_LATENCY_MS,
            'REALTIME_QUEUE_LEN': REALTIME_QUEUE_LEN,
            '_build_realtime_key': _build_realtime_key,
            '_build_realtime_key_from_update': _build_realtime_key_from_update,
            '_calculate_broadcast_backoff': _calculate_broadcast_backoff,
            '_to_timestamp_ms': _to_timestamp_ms,
            'datetime': datetime,
            'get_settings': get_settings,
            'logger': logger,
        }
    )
    return RuntimeRealtime(
        RuntimeRealtimePorts(
            laravel_api_duration=lambda: dependencies.LARAVEL_API_DURATION,
            realtime_dropped_updates=lambda: dependencies.REALTIME_DROPPED_UPDATES,
            realtime_flush_latency_ms=lambda: dependencies.REALTIME_FLUSH_LATENCY_MS,
            realtime_queue_len=lambda: dependencies.REALTIME_QUEUE_LEN,
            broadcast_backoff_until=lambda: _broadcast_backoff_until,
            broadcast_error_count=lambda: _broadcast_error_count,
            broadcast_in_backoff=lambda *args, **kwargs: _broadcast_in_backoff(*args, **kwargs),
            broadcast_telemetry_batch_to_laravel=lambda *args, **kwargs: _broadcast_telemetry_batch_to_laravel(
                *args, **kwargs
            ),
            build_realtime_key=dependencies._build_realtime_key,
            build_realtime_key_from_update=dependencies._build_realtime_key_from_update,
            calculate_broadcast_backoff=dependencies._calculate_broadcast_backoff,
            enqueue_realtime_update=lambda *args, **kwargs: _enqueue_realtime_update(*args, **kwargs),
            flush_realtime_updates=lambda *args, **kwargs: _flush_realtime_updates(*args, **kwargs),
            item_is_writable=lambda *args, **kwargs: _item_is_writable(*args, **kwargs),
            pop_realtime_updates=lambda *args, **kwargs: _pop_realtime_updates(*args, **kwargs),
            realtime_lock=lambda: _realtime_lock,
            realtime_updates=lambda: _realtime_updates,
            requeue_realtime_updates=lambda *args, **kwargs: _requeue_realtime_updates(*args, **kwargs),
            set_broadcast_backoff_until=lambda *args, **kwargs: _set_broadcast_backoff_until(*args, **kwargs),
            set_broadcast_error_count=lambda *args, **kwargs: _set_broadcast_error_count(*args, **kwargs),
            set_broadcast_last_error_time=lambda *args, **kwargs: _set_broadcast_last_error_time(*args, **kwargs),
            shutdown_event=lambda *args, **kwargs: _shutdown_event(*args, **kwargs),
            to_timestamp_ms=dependencies._to_timestamp_ms,
            tracked_entry_ids=lambda *args, **kwargs: _tracked_entry_ids(*args, **kwargs),
            datetime=dependencies.datetime,
            get_settings=dependencies.get_settings,
            logger=lambda: dependencies.logger,
        )
    )


from telemetry.runtime_queue_consumer import RuntimeQueueConsumer, RuntimeQueueConsumerPorts


def _runtime_queue_consumer() -> RuntimeQueueConsumer:
    dependencies = telemetry_dependency_snapshot(
        {
            'REDIS_OPERATION_DURATION': REDIS_OPERATION_DURATION,
            'TELEMETRY_DEAD_LIST_SIZE': TELEMETRY_DEAD_LIST_SIZE,
            'TELEMETRY_PROCESSING_RECLAIMED': TELEMETRY_PROCESSING_RECLAIMED,
            'TELEMETRY_PROCESSING_SIZE': TELEMETRY_PROCESSING_SIZE,
            'TELEMETRY_PROCESSING_STUCK': TELEMETRY_PROCESSING_STUCK,
            'TELEMETRY_QUEUE_AGE': TELEMETRY_QUEUE_AGE,
            'TELEMETRY_REQUEUE_DUPLICATE_RISK': TELEMETRY_REQUEUE_DUPLICATE_RISK,
            'get_settings': get_settings,
            'logger': logger,
            'utcnow': utcnow,
        }
    )
    return RuntimeQueueConsumer(
        RuntimeQueueConsumerPorts(
            process_telemetry_batch=lambda *args, **kwargs: process_telemetry_batch(*args, **kwargs),
            redis_operation_duration=lambda: dependencies.REDIS_OPERATION_DURATION,
            telemetry_dead_list_size=lambda: dependencies.TELEMETRY_DEAD_LIST_SIZE,
            telemetry_processing_reclaimed=lambda: dependencies.TELEMETRY_PROCESSING_RECLAIMED,
            telemetry_processing_size=lambda: dependencies.TELEMETRY_PROCESSING_SIZE,
            telemetry_processing_stuck=lambda: dependencies.TELEMETRY_PROCESSING_STUCK,
            telemetry_queue_age=lambda: dependencies.TELEMETRY_QUEUE_AGE,
            telemetry_requeue_duplicate_risk=lambda: dependencies.TELEMETRY_REQUEUE_DUPLICATE_RISK,
            drain_telemetry_queue_on_shutdown=lambda *args, **kwargs: _drain_telemetry_queue_on_shutdown(
                *args, **kwargs
            ),
            finalize_queue_batch=lambda *args, **kwargs: _finalize_queue_batch(*args, **kwargs),
            get_telemetry_queue=lambda *args, **kwargs: _get_telemetry_queue(*args, **kwargs),
            handle_pop_batch=lambda *args, **kwargs: _handle_pop_batch(*args, **kwargs),
            queue_entries_to_samples=lambda *args, **kwargs: _queue_entries_to_samples(*args, **kwargs),
            shutdown_event=lambda *args, **kwargs: _shutdown_event(*args, **kwargs),
            get_settings=dependencies.get_settings,
            logger=lambda: dependencies.logger,
            utcnow=dependencies.utcnow,
        )
    )


from telemetry.runtime_outcomes import RuntimeOutcomes, RuntimeOutcomesPorts


def _runtime_outcomes() -> RuntimeOutcomes:
    dependencies = telemetry_dependency_snapshot({'logger': logger})
    return RuntimeOutcomes(
        RuntimeOutcomesPorts(
            should_emit_warning=lambda *args, **kwargs: _should_emit_warning(*args, **kwargs),
            tracked_entry_ids=lambda *args, **kwargs: _tracked_entry_ids(*args, **kwargs),
            warning_throttle_last_sent=lambda: _warning_throttle_last_sent,
            warning_throttle_sec=lambda: _warning_throttle_sec,
            logger=lambda: dependencies.logger,
        )
    )


from telemetry.runtime_thresholds import RuntimeThresholds, RuntimeThresholdsPorts


def _runtime_thresholds() -> RuntimeThresholds:
    dependencies = telemetry_dependency_snapshot({'_normalize_ts_for_db': _normalize_ts_for_db, 'logger': logger})
    return RuntimeThresholds(
        RuntimeThresholdsPorts(
            normalize_ts_for_db=dependencies._normalize_ts_for_db,
            logger=lambda: dependencies.logger,
        )
    )


def _set_broadcast_backoff_until(value: Any) -> None:
    global _broadcast_backoff_until
    _broadcast_backoff_until = value


def _set_broadcast_error_count(value: Any) -> None:
    global _broadcast_error_count
    _broadcast_error_count = value


def _set_broadcast_last_error_time(value: Any) -> None:
    global _broadcast_last_error_time
    _broadcast_last_error_time = value


def _set_cache_last_update(value: Any) -> None:
    global _cache_last_update
    _cache_last_update = value


def _tracked_entry_ids(result: TelemetryBatchResult) -> Set[int]:
    return _runtime_outcomes().tracked_entry_ids(result=result)


def _append_dead_entry(result: TelemetryBatchResult, entry: Optional[QueueEntry]) -> None:
    return _runtime_outcomes().append_dead_entry(result=result, entry=entry)


def _append_requeue_entry(result: TelemetryBatchResult, entry: Optional[QueueEntry]) -> None:
    return _runtime_outcomes().append_requeue_entry(result=result, entry=entry)


def _item_is_writable(item: dict, tracked_ids: Set[int]) -> bool:
    return _runtime_outcomes().item_is_writable(item=item, tracked_ids=tracked_ids)


def _items_for_sensor(items: list[dict], sensor_id: int) -> list[dict]:
    return _runtime_outcomes().items_for_sensor(items=items, sensor_id=sensor_id)


def _is_pg_transport_error(exc: Exception) -> bool:
    return _runtime_outcomes().is_pg_transport_error(exc=exc)


def _persist_quality_for_sample(sample: Any) -> str:
    return _runtime_outcomes().persist_quality_for_sample(sample=sample)


_anomaly_alert_last_sent = telemetry_anomaly_module._anomaly_alert_last_sent
_anomaly_resolved_last_sent = telemetry_anomaly_module._anomaly_resolved_last_sent


def _telemetry_dependencies():
    return telemetry_dependency_snapshot(
        {
            'fetch': fetch,
            'send_infra_alert': send_infra_alert,
            'send_infra_resolved_alert': send_infra_resolved_alert,
            'TELEM_RECEIVED': TELEM_RECEIVED,
            'TELEMETRY_DROPPED': TELEMETRY_DROPPED,
            'REDIS_OPERATION_DURATION': REDIS_OPERATION_DURATION,
            'logger': logger,
            'push_with_retry': _push_with_retry,
        }
    )


async def handle_telemetry(topic: str, payload: bytes, *, durable: bool = False) -> None:
    with bind_telemetry_dependencies(**_telemetry_dependencies().values):
        await _handle_telemetry_impl(topic, payload, durable=durable)


SIMULATION_TELEMETRY_EVENTS_ENABLED = os.getenv("SIMULATION_TELEMETRY_EVENTS", "0") in (
    "1",
    "true",
    "True",
    "yes",
    "Yes",
)
SIMULATION_TELEMETRY_EVENT_INTERVAL_SEC = float(os.getenv("SIMULATION_TELEMETRY_EVENT_INTERVAL_SEC", "10"))

# Глобальный кеш для резолва zone_id и node_id (с TTL refresh)
_zone_cache: dict[tuple[str, Optional[str]], int] = {}
_node_cache: dict[
    tuple[str, Optional[str]],
    tuple[int, Optional[int], Optional[int]] | tuple[int, Optional[int]],
] = {}
_zone_greenhouse_cache: dict[int, int] = {}
_sensor_cache: "OrderedDict[tuple[int, Optional[int], str, str], int]" = OrderedDict()
_sensor_cache_max_size = int(os.getenv("SENSOR_CACHE_MAX_SIZE", "5000"))
_cache_last_update = 0.0
_cache_ttl = 60.0

_node_unassigned_last_seen: dict[tuple[int, str], float] = {}
_node_unassigned_recovery_grace_sec = float(os.getenv("TELEMETRY_NODE_UNASSIGNED_RECOVERY_GRACE_SEC", "5"))
_warning_throttle_last_sent: dict[tuple[str, str, str, str], float] = {}
_warning_throttle_sec = float(os.getenv("TELEMETRY_WARNING_THROTTLE_SEC", "30"))

# Backoff состояние для telemetry broadcast
_broadcast_error_count = 0
_broadcast_last_error_time: Optional[float] = None
_broadcast_backoff_until: Optional[float] = None

_realtime_updates: "OrderedDict[tuple, dict]" = OrderedDict()
_realtime_lock = asyncio.Lock()


def _sensor_cache_touch(key: tuple[int, Optional[int], str, str]) -> None:
    return _runtime_cache().sensor_cache_touch(key=key)


def _sensor_cache_pop_oldest() -> None:
    return _runtime_cache().sensor_cache_pop_oldest()


def _sensor_cache_get(key: tuple[int, Optional[int], str, str]) -> Optional[int]:
    return _runtime_cache().sensor_cache_get(key=key)


def _sensor_cache_set(key: tuple[int, Optional[int], str, str], sensor_id: int) -> None:
    return _runtime_cache().sensor_cache_set(key=key, sensor_id=sensor_id)


def _get_telemetry_queue():
    return _runtime_queue_consumer().get_telemetry_queue()


def _shutdown_event():
    return _runtime_queue_consumer().shutdown_event()


def _should_emit_warning(
    key: tuple[str, str, str, str],
    now_ts: Optional[float] = None,
) -> bool:
    return _runtime_outcomes().should_emit_warning(key=key, now_ts=now_ts)


def _log_warning_throttled(
    *,
    key: tuple[str, str, str, str],
    message: str,
    extra: Optional[dict] = None,
) -> None:
    return _runtime_outcomes().log_warning_throttled(key=key, message=message, extra=extra)


async def _enqueue_realtime_update(key: tuple, update: dict) -> None:
    return await _runtime_realtime().enqueue_realtime_update(key=key, update=update)


async def _pop_realtime_updates(limit: int) -> list[dict]:
    return await _runtime_realtime().pop_realtime_updates(limit=limit)


async def _requeue_realtime_updates(updates: list[dict]) -> None:
    return await _runtime_realtime().requeue_realtime_updates(updates=updates)


def _broadcast_in_backoff(current_time: float) -> bool:
    return _runtime_realtime().broadcast_in_backoff(current_time=current_time)


async def _broadcast_telemetry_batch_to_laravel(updates: list[dict]) -> bool:
    return await _runtime_realtime().broadcast_telemetry_batch_to_laravel(updates=updates)


async def _flush_realtime_updates(force: bool = False) -> None:
    return await _runtime_realtime().flush_realtime_updates(force=force)


async def process_realtime_queue() -> None:
    return await _runtime_realtime().process_realtime_queue()


def _store_node_cache_entry(
    *,
    node_uid: str,
    gh_uid: Optional[str],
    node_id: int,
    zone_id: Optional[int],
    pending_zone_id: Optional[int],
) -> None:
    return _runtime_cache().store_node_cache_entry(
        node_uid=node_uid, gh_uid=gh_uid, node_id=node_id, zone_id=zone_id, pending_zone_id=pending_zone_id
    )


async def refresh_node_cache_for_uid(node_uid: str) -> bool:
    return await _runtime_cache().refresh_node_cache_for_uid(node_uid=node_uid)


async def _prewarm_stale_node_assignments(
    node_uid_to_info: dict[
        tuple[str, Optional[str]],
        tuple[int, Optional[int], Optional[int]] | tuple[int, Optional[int]],
    ],
    node_gh_pairs: list[tuple[str, Optional[str]]],
) -> None:
    return await _runtime_cache().prewarm_stale_node_assignments(
        node_uid_to_info=node_uid_to_info, node_gh_pairs=node_gh_pairs
    )


async def refresh_caches() -> None:
    return await _runtime_cache().refresh_caches()


async def _create_sensors_per_item(
    to_create: list[tuple[int, Optional[int], str, str]],
) -> None:
    return await _runtime_sensor_resolution().create_sensors_per_item(to_create=to_create)


async def _insert_telemetry_sample_item(
    item: dict,
    result: TelemetryBatchResult,
) -> bool:
    return await _runtime_persistence().insert_telemetry_sample_item(item=item, result=result)


async def _upsert_telemetry_last_for_sensor(
    sensor_id: int,
    update_data: dict,
    items: list[dict],
    result: TelemetryBatchResult,
    *,
    samples_committed: bool = False,
) -> bool:
    return await _runtime_persistence().upsert_telemetry_last_for_sensor(
        sensor_id=sensor_id, update_data=update_data, items=items, result=result, samples_committed=samples_committed
    )


def _build_telemetry_last_updates(items: list[dict]) -> dict[int, dict]:
    return _runtime_persistence().build_telemetry_last_updates(items=items)


async def _upsert_telemetry_last_batch(
    telemetry_last_updates: dict[int, dict],
    items: list[dict],
    result: TelemetryBatchResult,
    *,
    samples_committed: bool,
) -> None:
    return await _runtime_persistence().upsert_telemetry_last_batch(
        telemetry_last_updates=telemetry_last_updates, items=items, result=result, samples_committed=samples_committed
    )


def _ts_key(ts_value: datetime) -> datetime:
    # Laravel's timestamp columns use precision 0. PostgreSQL rounds fractions
    # when storing them, so RETURNING ts can differ from the input after a
    # successful INSERT. Comparing full precision falsely retries committed rows.
    return _runtime_persistence().ts_key(ts_value=ts_value)


def _handle_samples_join_mismatch(
    writable_items: list[dict],
    sensor_ids: list[int],
    sample_ts_values: list[datetime],
    returned_rows: list[dict],
    result: TelemetryBatchResult,
) -> list[dict]:
    return _runtime_persistence().handle_samples_join_mismatch(
        writable_items=writable_items,
        sensor_ids=sensor_ids,
        sample_ts_values=sample_ts_values,
        returned_rows=returned_rows,
        result=result,
    )


async def process_telemetry_batch(
    samples: List[TelemetrySampleModel],
    entries: Optional[List[QueueEntry]] = None,
) -> TelemetryBatchResult:
    with bind_telemetry_dependencies(**_telemetry_dependencies().values):
        return await _process_telemetry_batch_impl(samples, entries=entries)


async def _resolve_batch_zones(*, samples: List[TelemetrySampleModel]) -> Any:
    return await _runtime_zone_resolution().resolve_batch_zones(samples=samples)


async def _resolve_batch_nodes(*, samples: List[TelemetrySampleModel]) -> Any:
    return await _runtime_node_resolution().resolve_batch_nodes(samples=samples)


async def _normalize_batch_samples(
    *,
    entries: Optional[List[QueueEntry]],
    max_age_minutes: float,
    max_age_seconds: float,
    node_info_source: Any,
    node_uid_to_info: Any,
    samples: List[TelemetrySampleModel],
    zone_uid_to_id: Any,
) -> Any:
    return await _runtime_normalization().normalize_batch_samples(
        entries=entries,
        max_age_minutes=max_age_minutes,
        max_age_seconds=max_age_seconds,
        node_info_source=node_info_source,
        node_uid_to_info=node_uid_to_info,
        samples=samples,
        zone_uid_to_id=zone_uid_to_id,
    )


async def _recover_batch_assignments(
    *, node_unassigned_detected_in_batch: Any, node_unassigned_recovery_candidates: Any, zone_ids_for_greenhouse: Any
) -> None:
    return await _runtime_node_resolution().recover_batch_assignments(
        node_unassigned_detected_in_batch=node_unassigned_detected_in_batch,
        node_unassigned_recovery_candidates=node_unassigned_recovery_candidates,
        zone_ids_for_greenhouse=zone_ids_for_greenhouse,
    )


async def _resolve_batch_sensors(*, resolved_samples: Any, result: TelemetryBatchResult) -> list[dict]:
    return await _runtime_sensor_resolution().resolve_batch_sensors(resolved_samples=resolved_samples, result=result)


async def _persist_batch_samples(*, resolved_with_sensor: Any, result: TelemetryBatchResult) -> Any:
    return await _runtime_persistence().persist_batch_samples(resolved_with_sensor=resolved_with_sensor, result=result)


async def _enqueue_committed_realtime(
    *, broadcast_groups: Any, result: TelemetryBatchResult, written_items: Any
) -> None:
    return await _runtime_realtime().enqueue_committed_realtime(
        broadcast_groups=broadcast_groups, result=result, written_items=written_items
    )


async def _evaluate_solution_temp_thresholds(*, written_items: Any) -> None:
    return await _runtime_thresholds().evaluate_solution_temp_thresholds(written_items=written_items)


async def _process_telemetry_batch_impl(
    samples: List[TelemetrySampleModel],
    entries: Optional[List[QueueEntry]] = None,
) -> TelemetryBatchResult:
    return await _runtime_batch().process_telemetry_batch_impl(samples=samples, entries=entries)


def _queue_entries_to_samples(entries: List[QueueEntry]) -> List[TelemetrySampleModel]:
    return _runtime_queue_consumer().queue_entries_to_samples(entries=entries)


async def _finalize_queue_batch(
    queue,
    pop: PopBatchResult,
    batch_result: TelemetryBatchResult,
) -> None:
    return await _runtime_queue_consumer().finalize_queue_batch(queue=queue, pop=pop, batch_result=batch_result)


async def _handle_pop_batch(pop: PopBatchResult) -> None:
    return await _runtime_queue_consumer().handle_pop_batch(pop=pop)


async def _drain_telemetry_queue_on_shutdown() -> None:
    return await _runtime_queue_consumer().drain_telemetry_queue_on_shutdown()


async def process_telemetry_queue() -> None:
    return await _runtime_queue_consumer().process_telemetry_queue()
