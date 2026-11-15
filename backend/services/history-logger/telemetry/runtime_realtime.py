"""runtime realtime: explicit dependencies and invocation data."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from telemetry.runtime_records import TelemetryBatchResult


@dataclass(frozen=True)
class RuntimeRealtimePorts:
    laravel_api_duration: Callable[..., Any]
    realtime_dropped_updates: Callable[..., Any]
    realtime_flush_latency_ms: Callable[..., Any]
    realtime_queue_len: Callable[..., Any]
    broadcast_backoff_until: Callable[..., Any]
    broadcast_error_count: Callable[..., Any]
    broadcast_in_backoff: Callable[..., Any]
    broadcast_telemetry_batch_to_laravel: Callable[..., Any]
    build_realtime_key: Callable[..., Any]
    build_realtime_key_from_update: Callable[..., Any]
    calculate_broadcast_backoff: Callable[..., Any]
    enqueue_realtime_update: Callable[..., Any]
    flush_realtime_updates: Callable[..., Any]
    item_is_writable: Callable[..., Any]
    pop_realtime_updates: Callable[..., Any]
    realtime_lock: Callable[..., Any]
    realtime_updates: Callable[..., Any]
    requeue_realtime_updates: Callable[..., Any]
    set_broadcast_backoff_until: Callable[..., Any]
    set_broadcast_error_count: Callable[..., Any]
    set_broadcast_last_error_time: Callable[..., Any]
    shutdown_event: Callable[..., Any]
    to_timestamp_ms: Callable[..., Any]
    tracked_entry_ids: Callable[..., Any]
    datetime: Callable[..., Any]
    get_settings: Callable[..., Any]
    logger: Callable[..., Any]


class RuntimeRealtime:
    def __init__(self, ports: RuntimeRealtimePorts) -> None:
        self._ports = ports

    async def enqueue_realtime_update(self, key: tuple, update: dict) -> None:
        s = self._ports.get_settings()
        async with self._ports.realtime_lock():
            self._ports.realtime_updates()[key] = update
            self._ports.realtime_updates().move_to_end(key)

            max_size = getattr(s, "realtime_queue_max_size", 0)
            if max_size > 0 and len(self._ports.realtime_updates()) > max_size:
                self._ports.realtime_updates().popitem(last=False)
                self._ports.realtime_dropped_updates().labels(reason="queue_full").inc()

            self._ports.realtime_queue_len().set(len(self._ports.realtime_updates()))

    async def pop_realtime_updates(self, limit: int) -> list[dict]:
        async with self._ports.realtime_lock():
            if not self._ports.realtime_updates():
                return []

            count = min(limit, len(self._ports.realtime_updates()))
            updates = []
            for _ in range(count):
                _, update = self._ports.realtime_updates().popitem(last=False)
                updates.append(update)

            self._ports.realtime_queue_len().set(len(self._ports.realtime_updates()))
            return updates

    async def requeue_realtime_updates(self, updates: list[dict]) -> None:
        s = self._ports.get_settings()
        async with self._ports.realtime_lock():
            for update in updates:
                key = self._ports.build_realtime_key_from_update(update)
                self._ports.realtime_updates()[key] = update
                self._ports.realtime_updates().move_to_end(key)

                max_size = getattr(s, "realtime_queue_max_size", 0)
                if max_size > 0 and len(self._ports.realtime_updates()) > max_size:
                    self._ports.realtime_updates().popitem(last=False)
                    self._ports.realtime_dropped_updates().labels(reason="queue_full").inc()

            self._ports.realtime_queue_len().set(len(self._ports.realtime_updates()))

    def broadcast_in_backoff(self, current_time: float) -> bool:
        return (
            self._ports.broadcast_backoff_until() is not None and current_time < self._ports.broadcast_backoff_until()
        )

    async def broadcast_telemetry_batch_to_laravel(self, updates: list[dict]) -> bool:
        """
        Отправляет batched realtime updates в Laravel.
        """

        if self._ports.shutdown_event().is_set():
            self._ports.logger().debug("[BROADCAST] Shutdown in progress, skipping telemetry batch broadcast")
            return False

        current_time = time.time()
        if self._ports.broadcast_in_backoff(current_time):
            self._ports.logger().debug(
                "[BROADCAST] In backoff mode, skipping batch broadcast. "
                f"Backoff until: {self._ports.broadcast_backoff_until():.2f}, current: {current_time:.2f}, "
                f"error_count: {self._ports.broadcast_error_count()}"
            )
            return False

        s = self._ports.get_settings()
        laravel_url = s.laravel_api_url if hasattr(s, "laravel_api_url") else None
        ingest_token = (
            s.history_logger_api_token
            if hasattr(s, "history_logger_api_token") and s.history_logger_api_token
            else (s.ingest_token if hasattr(s, "ingest_token") and s.ingest_token else None)
        )

        if not laravel_url:
            self._ports.logger().warning(
                "[BROADCAST] Laravel API URL not configured, skipping telemetry batch broadcast."
            )
            return True

        if not ingest_token:
            self._ports.logger().warning("[BROADCAST] Ingest token not configured, skipping telemetry batch broadcast.")
            return True

        self._ports.logger().info(
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
            self._ports.laravel_api_duration().observe(api_duration)

            if response.status_code == 200:
                if self._ports.broadcast_error_count() > 0:
                    self._ports.logger().info(
                        "[BROADCAST] Success after %s errors, resetting error count and backoff",
                        self._ports.broadcast_error_count(),
                    )
                self._ports.set_broadcast_error_count(0)
                self._ports.set_broadcast_backoff_until(None)
                return True

            self._ports.set_broadcast_error_count(self._ports.broadcast_error_count() + 1)
            self._ports.set_broadcast_last_error_time(current_time)
            backoff_delay = self._ports.calculate_broadcast_backoff(self._ports.broadcast_error_count())
            self._ports.set_broadcast_backoff_until(current_time + backoff_delay)

            self._ports.logger().warning(
                "[BROADCAST] Failed to broadcast telemetry batch: status=%s, error_count=%s, backoff=%.2fs",
                response.status_code,
                self._ports.broadcast_error_count(),
                backoff_delay,
                extra={
                    "status_code": response.status_code,
                    "response": response.text[:200],
                    "error_count": self._ports.broadcast_error_count(),
                    "backoff_seconds": backoff_delay,
                },
            )
            return False
        except (httpx.TimeoutException, httpx.RequestError, httpx.NetworkError) as e:
            self._ports.set_broadcast_error_count(self._ports.broadcast_error_count() + 1)
            self._ports.set_broadcast_last_error_time(current_time)
            backoff_delay = self._ports.calculate_broadcast_backoff(self._ports.broadcast_error_count())
            self._ports.set_broadcast_backoff_until(current_time + backoff_delay)

            self._ports.logger().warning(
                "[BROADCAST] Network error broadcasting telemetry batch: %s, error_count=%s, backoff=%.2fs",
                e,
                self._ports.broadcast_error_count(),
                backoff_delay,
                extra={
                    "error_count": self._ports.broadcast_error_count(),
                    "backoff_seconds": backoff_delay,
                },
            )
            return False
        except Exception as e:
            self._ports.set_broadcast_error_count(self._ports.broadcast_error_count() + 1)
            self._ports.set_broadcast_last_error_time(current_time)
            backoff_delay = self._ports.calculate_broadcast_backoff(self._ports.broadcast_error_count())
            self._ports.set_broadcast_backoff_until(current_time + backoff_delay)

            self._ports.logger().warning(
                "[BROADCAST] Error broadcasting telemetry batch: %s, error_count=%s, backoff=%.2fs",
                e,
                self._ports.broadcast_error_count(),
                backoff_delay,
                extra={
                    "error_count": self._ports.broadcast_error_count(),
                    "backoff_seconds": backoff_delay,
                },
                exc_info=True,
            )
            return False

    async def flush_realtime_updates(self, force: bool) -> None:
        s = self._ports.get_settings()

        if not force and self._ports.broadcast_in_backoff(time.time()):
            return

        updates = await self._ports.pop_realtime_updates(getattr(s, "realtime_batch_max_updates", 200))
        if not updates:
            return

        flush_start = time.time()
        success = await self._ports.broadcast_telemetry_batch_to_laravel(updates)
        self._ports.realtime_flush_latency_ms().observe((time.time() - flush_start) * 1000)

        if not success and not force:
            await self._ports.requeue_realtime_updates(updates)

    async def process_realtime_queue(self) -> None:
        """
        Фоновая задача для batched realtime telemetry.
        """
        s = self._ports.get_settings()
        self._ports.logger().info("Starting realtime telemetry broadcaster")

        while not self._ports.shutdown_event().is_set():
            try:
                await self._ports.flush_realtime_updates()
                await asyncio.sleep(getattr(s, "realtime_flush_ms", 500) / 1000)
            except Exception as e:
                self._ports.logger().error("Error in realtime telemetry broadcaster: %s", e, exc_info=True)
                await asyncio.sleep(s.queue_error_retry_delay_sec)

        self._ports.logger().info("Realtime telemetry broadcaster shutting down, flushing remaining updates...")
        await self._ports.flush_realtime_updates(force=True)
        self._ports.logger().info("Realtime telemetry broadcaster stopped")

    async def enqueue_committed_realtime(
        self, *, broadcast_groups: Any, result: TelemetryBatchResult, written_items: Any
    ) -> None:
        tracked_ids = self._ports.tracked_entry_ids(result)
        written_item_ids = {id(item) for item in written_items}
        for (zone_id, metric_type, node_id, channel), group_items in broadcast_groups.items():
            writable_group_items = [
                item
                for item in group_items
                if id(item) in written_item_ids and self._ports.item_is_writable(item, tracked_ids)
            ]
            if not writable_group_items:
                continue

            latest_item = max(
                writable_group_items,
                key=lambda item: (
                    item["sample"].ts if item["sample"].ts else self._ports.datetime.min.replace(tzinfo=None)
                ),
            )
            latest_sample = latest_item["sample"]

            if not zone_id or not node_id or self._ports.shutdown_event().is_set():
                self._ports.realtime_dropped_updates().labels(reason="missing_zone_or_node").inc()
                continue

            update = {
                "zone_id": zone_id,
                "node_id": node_id,
                "channel": channel or None,
                "metric_type": metric_type,
                "value": latest_sample.value,
                "timestamp": self._ports.to_timestamp_ms(latest_sample.ts),
            }
            realtime_key = self._ports.build_realtime_key(
                latest_item.get("sensor_id"),
                zone_id,
                node_id,
                metric_type,
                channel,
            )
            await self._ports.enqueue_realtime_update(realtime_key, update)
