"""runtime queue consumer: explicit dependencies and invocation data."""

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, List

import state
from models import TelemetrySampleModel

from common.redis_queue import PopBatchResult, QueueEntry
from telemetry.runtime_records import PgTransportError, TelemetryBatchResult


@dataclass(frozen=True)
class RuntimeQueueConsumerPorts:
    process_telemetry_batch: Callable[..., Any]
    redis_operation_duration: Callable[..., Any]
    telemetry_dead_list_size: Callable[..., Any]
    telemetry_processing_reclaimed: Callable[..., Any]
    telemetry_processing_size: Callable[..., Any]
    telemetry_processing_stuck: Callable[..., Any]
    telemetry_queue_age: Callable[..., Any]
    telemetry_requeue_duplicate_risk: Callable[..., Any]
    drain_telemetry_queue_on_shutdown: Callable[..., Any]
    finalize_queue_batch: Callable[..., Any]
    get_telemetry_queue: Callable[..., Any]
    handle_pop_batch: Callable[..., Any]
    queue_entries_to_samples: Callable[..., Any]
    shutdown_event: Callable[..., Any]
    get_settings: Callable[..., Any]
    logger: Callable[..., Any]
    utcnow: Callable[..., Any]


class RuntimeQueueConsumer:
    def __init__(self, ports: RuntimeQueueConsumerPorts) -> None:
        self._ports = ports

    def get_telemetry_queue(self):
        return state.telemetry_queue

    def shutdown_event(self):
        return state.shutdown_event

    def queue_entries_to_samples(self, entries: List[QueueEntry]) -> List[TelemetrySampleModel]:
        samples: List[TelemetrySampleModel] = []
        for entry in entries:
            item = entry.item
            samples.append(
                TelemetrySampleModel(
                    node_uid=item.node_uid,
                    zone_uid=item.zone_uid,
                    zone_id=None,
                    gh_uid=getattr(item, "gh_uid", None),
                    metric_type=item.metric_type,
                    value=item.value,
                    ts=item.ts,
                    raw=item.raw,
                    channel=item.channel,
                    stub=bool(getattr(item, "stub", False)),
                )
            )
        return samples

    async def finalize_queue_batch(self, queue, pop: PopBatchResult, batch_result: TelemetryBatchResult) -> None:
        if batch_result.processed_count > 0 and batch_result.entries_to_requeue:
            self._ports.telemetry_requeue_duplicate_risk().inc(len(batch_result.entries_to_requeue))

        if batch_result.entries_to_dead:
            moved = await queue.move_entries_to_dead(
                batch_result.entries_to_dead,
                reason="fk_violation",
            )
            if moved != len(batch_result.entries_to_dead):
                self._ports.logger().warning(
                    "Incomplete dead-list move for telemetry batch",
                    extra={"expected": len(batch_result.entries_to_dead), "moved": moved},
                )
                self._ports.telemetry_processing_stuck().inc()

        if batch_result.entries_to_requeue:
            requeued = await queue.requeue_batch(batch_result.entries_to_requeue)
            if requeued != len(batch_result.entries_to_requeue):
                self._ports.logger().warning(
                    "Incomplete telemetry requeue; retrying once",
                    extra={
                        "expected": len(batch_result.entries_to_requeue),
                        "requeued": requeued,
                    },
                )
                requeued = await queue.requeue_batch(batch_result.entries_to_requeue)
                if requeued != len(batch_result.entries_to_requeue):
                    self._ports.telemetry_processing_stuck().inc()
                    self._ports.logger().error(
                        "Telemetry requeue still incomplete after retry",
                        extra={
                            "expected": len(batch_result.entries_to_requeue),
                            "requeued": requeued,
                        },
                    )

        entries_to_ack = batch_result.entries_to_ack(pop.entries)
        if entries_to_ack:
            raw_items = [entry.raw for entry in entries_to_ack]
            removed = await queue.ack_batch(raw_items)
            if removed != len(entries_to_ack):
                self._ports.logger().warning(
                    "Incomplete telemetry ack; retrying once",
                    extra={"expected": len(entries_to_ack), "removed": removed},
                )
                removed = await queue.ack_batch(raw_items)
                if removed != len(entries_to_ack):
                    self._ports.telemetry_processing_stuck().inc()
                    self._ports.logger().error(
                        "Telemetry ack still incomplete after retry",
                        extra={"expected": len(entries_to_ack), "removed": removed},
                    )

    async def handle_pop_batch(self, pop: PopBatchResult) -> None:
        if not pop.entries:
            return

        queue = self._ports.get_telemetry_queue()
        if queue is None:
            return

        samples = self._ports.queue_entries_to_samples(pop.entries)
        try:
            batch_result = await self._ports.process_telemetry_batch(samples, entries=pop.entries)
        except PgTransportError:
            if await queue.requeue_batch(pop.entries) != len(pop.entries):
                self._ports.telemetry_processing_stuck().inc()
            return

        await self._ports.finalize_queue_batch(queue, pop, batch_result)

    async def drain_telemetry_queue_on_shutdown(self) -> None:
        queue = self._ports.get_telemetry_queue()
        if queue is None:
            return

        settings = self._ports.get_settings()
        deadline = time.monotonic() + settings.telemetry_shutdown_drain_timeout_sec
        batch_size = max(1, int(settings.telemetry_batch_size))

        while time.monotonic() < deadline:
            pending = await queue.total_pending_size()
            if pending <= 0:
                break

            pop = await queue.pop_batch(batch_size)
            if not pop.entries:
                break

            await self._ports.handle_pop_batch(pop)

    async def process_telemetry_queue(self) -> None:
        """
        Фоновая задача для обработки очереди телеметрии из Redis.
        """
        s = self._ports.get_settings()
        last_flush = self._ports.utcnow()
        last_reclaim_at = time.monotonic()
        reclaim_interval_sec = float(os.getenv("TELEMETRY_PROCESSING_RECLAIM_INTERVAL_SEC", "60"))

        self._ports.logger().info("Starting telemetry queue processor")

        while not self._ports.shutdown_event().is_set():
            try:
                queue = self._ports.get_telemetry_queue()
                queue_start_time = time.time()
                queue_size = await queue.size()
                processing_size = await queue.processing_size()
                self._ports.telemetry_processing_size().set(processing_size)
                queue_duration = time.time() - queue_start_time
                self._ports.redis_operation_duration().observe(queue_duration)

                if processing_size > 0 and (time.monotonic() - last_reclaim_at) >= reclaim_interval_sec:
                    reclaimed = await queue.reclaim_processing()
                    last_reclaim_at = time.monotonic()
                    if reclaimed:
                        self._ports.telemetry_processing_reclaimed().inc(reclaimed)
                        self._ports.logger().warning(
                            "Reclaimed %s stale telemetry item(s) from processing list",
                            reclaimed,
                        )

                queue_age_start_time = time.time()
                queue_age = await queue.get_oldest_age_seconds()
                queue_age_duration = time.time() - queue_age_start_time
                self._ports.redis_operation_duration().observe(queue_age_duration)

                if queue_age is not None:
                    self._ports.telemetry_queue_age().set(queue_age)
                else:
                    self._ports.telemetry_queue_age().set(0.0)

                dead_list_size = await queue.dead_list_size()
                self._ports.telemetry_dead_list_size().set(dead_list_size)

                time_since_flush = (self._ports.utcnow() - last_flush).total_seconds() * 1000

                should_flush = queue_size >= s.telemetry_batch_size or (
                    time_since_flush >= s.telemetry_flush_ms and queue_size > 0
                )

                if should_flush:
                    batch_size = min(s.telemetry_batch_size, queue_size)
                    pop = await queue.pop_batch(batch_size)

                    if pop.entries:
                        await self._ports.handle_pop_batch(pop)
                        last_flush = self._ports.utcnow()

                await asyncio.sleep(s.queue_check_interval_sec)

            except Exception as e:
                self._ports.logger().error(f"Error in telemetry queue processor: {e}", exc_info=True)
                await asyncio.sleep(s.queue_error_retry_delay_sec)

        self._ports.logger().info("Shutting down telemetry queue processor, processing remaining items...")
        await self._ports.drain_telemetry_queue_on_shutdown()
        self._ports.logger().info("Telemetry queue processor stopped")
