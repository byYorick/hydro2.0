"""runtime outcomes: explicit dependencies and invocation data."""

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Set

import asyncpg

from common.redis_queue import QueueEntry
from telemetry.runtime_records import TelemetryBatchResult


@dataclass(frozen=True)
class RuntimeOutcomesPorts:
    should_emit_warning: Callable[..., Any]
    tracked_entry_ids: Callable[..., Any]
    warning_throttle_last_sent: Callable[..., Any]
    warning_throttle_sec: Callable[..., Any]
    logger: Callable[..., Any]


class RuntimeOutcomes:
    def __init__(self, ports: RuntimeOutcomesPorts) -> None:
        self._ports = ports

    def tracked_entry_ids(self, result: TelemetryBatchResult) -> Set[int]:
        return {id(entry) for entry in result.entries_to_dead + result.entries_to_requeue}

    def append_dead_entry(self, result: TelemetryBatchResult, entry: Optional[QueueEntry]) -> None:
        if entry is None or id(entry) in self._ports.tracked_entry_ids(result):
            return
        result.entries_to_dead.append(entry)

    def append_requeue_entry(self, result: TelemetryBatchResult, entry: Optional[QueueEntry]) -> None:
        if entry is None:
            return
        tracked = self._ports.tracked_entry_ids(result)
        if id(entry) in tracked:
            return
        result.entries_to_requeue.append(entry)

    def item_is_writable(self, item: dict, tracked_ids: Set[int]) -> bool:
        entry = item.get("entry")
        if entry is None:
            return True
        return id(entry) not in tracked_ids

    def items_for_sensor(self, items: list[dict], sensor_id: int) -> list[dict]:
        return [item for item in items if int(item["sensor_id"]) == int(sensor_id)]

    def is_pg_transport_error(self, exc: Exception) -> bool:
        if isinstance(exc, (asyncpg.PostgresConnectionError, ConnectionError, OSError)):
            return True
        sqlstate = getattr(exc, "sqlstate", None)
        return sqlstate in {"08000", "08003", "08006", "08001", "08004", "57P01", "57P02", "57P03"}

    def persist_quality_for_sample(self, sample: Any) -> str:
        """Map in-memory STUB marker to DB-allowed quality; stub stays in metadata."""
        if bool(getattr(sample, "stub", False)):
            return "UNCERTAIN"
        return "GOOD"

    def should_emit_warning(self, key: tuple[str, str, str, str], now_ts: Optional[float]) -> bool:
        now = now_ts if now_ts is not None else time.time()
        last = self._ports.warning_throttle_last_sent().get(key)
        if last is None or (now - last) >= self._ports.warning_throttle_sec():
            self._ports.warning_throttle_last_sent()[key] = now
            return True
        return False

    def log_warning_throttled(self, *, key: tuple[str, str, str, str], message: str, extra: Optional[dict]) -> None:
        if self._ports.should_emit_warning(key):
            self._ports.logger().warning(message, extra=extra)
        else:
            self._ports.logger().debug(message, extra=extra)
