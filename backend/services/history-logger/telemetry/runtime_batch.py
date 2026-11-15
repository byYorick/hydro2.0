"""runtime batch: explicit dependencies and invocation data."""

import os
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from models import TelemetrySampleModel

from common.redis_queue import QueueEntry
from telemetry.runtime_records import TelemetryBatchResult


@dataclass(frozen=True)
class RuntimeBatchPorts:
    telemetry_processing_duration: Callable[..., Any]
    telem_batch_size: Callable[..., Any]
    telem_processed: Callable[..., Any]
    cache_last_update: Callable[..., Any]
    cache_ttl: Callable[..., Any]
    enqueue_committed_realtime: Callable[..., Any]
    evaluate_solution_temp_thresholds: Callable[..., Any]
    normalize_batch_samples: Callable[..., Any]
    persist_batch_samples: Callable[..., Any]
    recover_batch_assignments: Callable[..., Any]
    resolve_batch_nodes: Callable[..., Any]
    resolve_batch_sensors: Callable[..., Any]
    resolve_batch_zones: Callable[..., Any]
    get_settings: Callable[..., Any]
    refresh_caches: Callable[..., Any]


class RuntimeBatch:
    def __init__(self, ports: RuntimeBatchPorts) -> None:
        self._ports = ports

    async def process_telemetry_batch_impl(
        self, samples: List[TelemetrySampleModel], entries: Optional[List[QueueEntry]]
    ) -> TelemetryBatchResult:
        """Обработать батч телеметрии и записать в БД."""
        result = TelemetryBatchResult()
        if not samples:
            return result
        if entries is not None and len(entries) != len(samples):
            raise ValueError("entries length must match samples length")

        start_time = time.time()
        self._ports.get_settings()
        max_age_minutes = float(os.getenv("TELEMETRY_MAX_AGE_MINUTES", "30"))
        max_age_seconds = max_age_minutes * 60

        current_time = time.time()
        if current_time - self._ports.cache_last_update() > self._ports.cache_ttl():
            await self._ports.refresh_caches()

        zone_uid_to_id = await self._ports.resolve_batch_zones(samples=samples)

        node_uid_to_info, node_info_source = await self._ports.resolve_batch_nodes(samples=samples)

        (
            resolved_samples,
            node_unassigned_recovery_candidates,
            node_unassigned_detected_in_batch,
            zone_ids_for_greenhouse,
        ) = await self._ports.normalize_batch_samples(
            entries=entries,
            max_age_minutes=max_age_minutes,
            max_age_seconds=max_age_seconds,
            node_info_source=node_info_source,
            node_uid_to_info=node_uid_to_info,
            samples=samples,
            zone_uid_to_id=zone_uid_to_id,
        )

        if not resolved_samples:
            return result

        await self._ports.recover_batch_assignments(
            node_unassigned_detected_in_batch=node_unassigned_detected_in_batch,
            node_unassigned_recovery_candidates=node_unassigned_recovery_candidates,
            zone_ids_for_greenhouse=zone_ids_for_greenhouse,
        )

        resolved_with_sensor = await self._ports.resolve_batch_sensors(resolved_samples=resolved_samples, result=result)
        if not resolved_with_sensor:
            return result

        broadcast_groups: dict[tuple[int, str, Optional[int], Optional[str]], list[dict]] = {}
        for item in resolved_with_sensor:
            sample = item["sample"]
            key = (item["zone_id"], sample.metric_type, item["node_id"], sample.channel)
            broadcast_groups.setdefault(key, []).append(item)

        written_items, processed_count = await self._ports.persist_batch_samples(
            resolved_with_sensor=resolved_with_sensor, result=result
        )

        await self._ports.enqueue_committed_realtime(
            broadcast_groups=broadcast_groups, result=result, written_items=written_items
        )

        processing_duration = time.time() - start_time
        self._ports.telemetry_processing_duration().observe(processing_duration)
        result.processed_count = processed_count
        self._ports.telem_processed().inc(processed_count)
        self._ports.telem_batch_size().observe(processed_count)
        await self._ports.evaluate_solution_temp_thresholds(written_items=written_items)
        return result
