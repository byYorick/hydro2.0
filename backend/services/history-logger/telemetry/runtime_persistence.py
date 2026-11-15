"""runtime persistence: explicit dependencies and invocation data."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict

from telemetry.runtime_records import PgTransportError, TelemetryBatchResult


@dataclass(frozen=True)
class RuntimePersistencePorts:
    database_errors: Callable[..., Any]
    simulation_telemetry_events_enabled: Callable[..., Any]
    simulation_telemetry_event_interval_sec: Callable[..., Any]
    telemetry_pg_write_failed: Callable[..., Any]
    telemetry_samples_join_mismatch: Callable[..., Any]
    append_dead_entry: Callable[..., Any]
    append_requeue_entry: Callable[..., Any]
    build_telemetry_last_updates: Callable[..., Any]
    handle_samples_join_mismatch: Callable[..., Any]
    insert_telemetry_sample_item: Callable[..., Any]
    is_pg_transport_error: Callable[..., Any]
    is_sensor_fk_error: Callable[..., Any]
    item_is_writable: Callable[..., Any]
    items_for_sensor: Callable[..., Any]
    normalize_ts_for_db: Callable[..., Any]
    persist_quality_for_sample: Callable[..., Any]
    sensor_cache: Callable[..., Any]
    tracked_entry_ids: Callable[..., Any]
    ts_key: Callable[..., Any]
    upsert_telemetry_last_batch: Callable[..., Any]
    upsert_telemetry_last_for_sensor: Callable[..., Any]
    datetime: Callable[..., Any]
    execute: Callable[..., Any]
    fetch: Callable[..., Any]
    logger: Callable[..., Any]
    record_simulation_event_throttled: Callable[..., Any]
    timedelta: Callable[..., Any]


class RuntimePersistence:
    def __init__(self, ports: RuntimePersistencePorts) -> None:
        self._ports = ports

    async def insert_telemetry_sample_item(self, item: dict, result: TelemetryBatchResult) -> bool:
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

        entry = item.get("entry")
        try:
            await self._ports.execute(
                """
                WITH written AS (INSERT INTO telemetry_samples (
                    sensor_id, ts, zone_id, value, quality, metadata
                )
                SELECT $1, $2, $3, $4, $5, $6
                FROM sensors s
                WHERE s.id = $1
                  AND s.zone_id = $3
                RETURNING sensor_id, ts, value, quality)
                INSERT INTO telemetry_last (sensor_id, last_value, last_ts, last_quality, updated_at)
                SELECT sensor_id, value, ts, quality, NOW() FROM written
                ON CONFLICT (sensor_id) DO UPDATE SET
                    last_value=EXCLUDED.last_value, last_ts=EXCLUDED.last_ts,
                    last_quality=EXCLUDED.last_quality, updated_at=EXCLUDED.updated_at
                WHERE EXCLUDED.last_ts > telemetry_last.last_ts
                """,
                int(item["sensor_id"]),
                self._ports.normalize_ts_for_db(sample.ts),
                int(item["zone_id"]) if item["zone_id"] is not None else None,
                sample.value,
                "GOOD",
                metadata or None,
            )
            return True
        except Exception as e:
            self._ports.telemetry_pg_write_failed().labels(stage="samples").inc()
            if self._ports.is_pg_transport_error(e):
                raise PgTransportError(str(e)) from e
            if self._ports.is_sensor_fk_error(e):
                self._ports.sensor_cache().pop(item.get("sensor_key"), None)
                self._ports.append_dead_entry(result, entry)
                self._ports.logger().warning(
                    "Per-item telemetry_samples FK violation, moving queue entry to dead-list",
                    extra={
                        "sensor_id": item.get("sensor_id"),
                        "zone_id": item.get("zone_id"),
                        "error": str(e),
                    },
                )
                return False
            self._ports.append_requeue_entry(result, entry)
            self._ports.logger().error(
                "Per-item telemetry_samples insert failed, scheduling requeue",
                extra={
                    "sensor_id": item.get("sensor_id"),
                    "zone_id": item.get("zone_id"),
                    "error": str(e),
                },
                exc_info=True,
            )
            return False

    async def upsert_telemetry_last_for_sensor(
        self,
        sensor_id: int,
        update_data: dict,
        items: list[dict],
        result: TelemetryBatchResult,
        *,
        samples_committed: bool,
    ) -> bool:
        try:
            await self._ports.execute(
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
                WHERE EXCLUDED.last_ts > telemetry_last.last_ts
                """,
                sensor_id,
                update_data["value"],
                update_data["ts"],
                update_data["quality"],
                update_data["updated_at"],
            )
            return True
        except Exception as e:
            self._ports.telemetry_pg_write_failed().labels(stage="last").inc()
            if self._ports.is_pg_transport_error(e):
                if samples_committed:
                    self._ports.logger().error(
                        "telemetry_last upsert failed after samples commit; not requeueing",
                        extra={"sensor_id": sensor_id, "error": str(e)},
                        exc_info=True,
                    )
                    return False
                raise PgTransportError(str(e)) from e
            affected_items = self._ports.items_for_sensor(items, sensor_id)
            if self._ports.is_sensor_fk_error(e):
                self._ports.sensor_cache().clear()
                if not samples_committed:
                    for affected in affected_items:
                        self._ports.append_dead_entry(result, affected.get("entry"))
                self._ports.logger().warning(
                    "Per-item telemetry_last FK violation",
                    extra={"sensor_id": sensor_id, "error": str(e)},
                )
                return False
            if not samples_committed:
                for affected in affected_items:
                    self._ports.append_requeue_entry(result, affected.get("entry"))
            self._ports.logger().error(
                "Per-item telemetry_last upsert failed",
                extra={"sensor_id": sensor_id, "error": str(e), "samples_committed": samples_committed},
                exc_info=True,
            )
            return False

    def build_telemetry_last_updates(self, items: list[dict]) -> dict[int, dict]:
        telemetry_last_updates: dict[int, dict] = {}
        for item in items:
            sample = item["sample"]
            sensor_id = int(item["sensor_id"])
            sample_ts = self._ports.normalize_ts_for_db(sample.ts)
            existing_ts = telemetry_last_updates.get(sensor_id, {}).get("ts")
            if existing_ts is None or sample_ts > existing_ts:
                sample_quality = self._ports.persist_quality_for_sample(sample)
                telemetry_last_updates[sensor_id] = {
                    "value": sample.value,
                    "ts": sample_ts,
                    "quality": sample_quality,
                    "updated_at": sample_ts,
                }
        return telemetry_last_updates

    async def upsert_telemetry_last_batch(
        self,
        telemetry_last_updates: dict[int, dict],
        items: list[dict],
        result: TelemetryBatchResult,
        *,
        samples_committed: bool,
    ) -> None:
        if not telemetry_last_updates:
            return

        sensor_ids: list[int] = []
        last_values: list[float] = []
        last_ts_values: list[self._ports.datetime] = []
        last_quality_values: list[str] = []
        updated_at_values: list[self._ports.datetime] = []
        for sensor_id, update_data in telemetry_last_updates.items():
            sensor_ids.append(sensor_id)
            last_values.append(update_data["value"])
            last_ts_values.append(update_data["ts"])
            last_quality_values.append(update_data["quality"])
            updated_at_values.append(update_data["updated_at"])

        if not sensor_ids:
            return

        query = """
            WITH incoming AS (
                SELECT *
                FROM UNNEST(
                    $1::bigint[],
                    $2::double precision[],
                    $3::timestamp[],
                    $4::text[],
                    $5::timestamp[]
                ) AS t(sensor_id, last_value, last_ts, last_quality, updated_at)
            ),
            existing AS (
                SELECT i.sensor_id, i.last_value, i.last_ts, i.last_quality, i.updated_at
                FROM incoming i
                JOIN sensors s ON s.id = i.sensor_id
            )
            INSERT INTO telemetry_last (
                sensor_id, last_value, last_ts, last_quality, updated_at
            )
            SELECT sensor_id, last_value, last_ts, last_quality, updated_at
            FROM existing
            ON CONFLICT (sensor_id)
            DO UPDATE SET
                last_value = EXCLUDED.last_value,
                last_ts = EXCLUDED.last_ts,
                last_quality = EXCLUDED.last_quality,
                updated_at = EXCLUDED.updated_at
            WHERE EXCLUDED.last_ts > telemetry_last.last_ts
        """
        try:
            await self._ports.execute(
                query,
                sensor_ids,
                last_values,
                last_ts_values,
                last_quality_values,
                updated_at_values,
            )
            self._ports.logger().debug(
                "Batch upserted %s telemetry_last records",
                len(telemetry_last_updates),
            )
        except Exception as e:
            if self._ports.is_pg_transport_error(e) and not samples_committed:
                raise PgTransportError(str(e)) from e
            self._ports.telemetry_pg_write_failed().labels(stage="last").inc()
            self._ports.logger().error(
                "Failed to batch upsert telemetry_last",
                extra={"error": str(e), "samples_committed": samples_committed},
                exc_info=True,
            )
            for sensor_id, update_data in telemetry_last_updates.items():
                await self._ports.upsert_telemetry_last_for_sensor(
                    sensor_id,
                    update_data,
                    items,
                    result,
                    samples_committed=samples_committed,
                )

    def ts_key(self, ts_value: datetime) -> datetime:
        normalized = self._ports.normalize_ts_for_db(ts_value)
        rounded = normalized.replace(microsecond=0)
        # PostgreSQL breaks half-second ties away from its 2000-01-01 epoch.
        if normalized.microsecond > 500000 or (
            normalized.microsecond == 500000 and normalized >= self._ports.datetime(2000, 1, 1)
        ):
            rounded += self._ports.timedelta(seconds=1)
        return rounded

    def handle_samples_join_mismatch(
        self,
        writable_items: list[dict],
        sensor_ids: list[int],
        sample_ts_values: list[datetime],
        returned_rows: list[dict],
        result: TelemetryBatchResult,
    ) -> list[dict]:
        returned_keys = {
            (int(row["sensor_id"]), self._ports.ts_key(row["ts"]))
            for row in returned_rows
            if row.get("sensor_id") is not None and row.get("ts") is not None
        }
        written_items: list[dict] = []
        for idx, item in enumerate(writable_items):
            expected_key = (int(sensor_ids[idx]), self._ports.ts_key(sample_ts_values[idx]))
            if expected_key in returned_keys:
                written_items.append(item)
                continue
            self._ports.telemetry_samples_join_mismatch().inc()
            self._ports.append_requeue_entry(result, item.get("entry"))
            self._ports.logger().warning(
                "telemetry_samples JOIN mismatch, scheduling requeue",
                extra={
                    "sensor_id": sensor_ids[idx],
                    "zone_id": item.get("zone_id"),
                    "metric_type": getattr(item.get("sample"), "metric_type", None),
                },
            )
        return written_items

    async def persist_batch_samples(self, *, resolved_with_sensor: Any, result: TelemetryBatchResult) -> Any:
        telemetry_last_updates = self._ports.build_telemetry_last_updates(resolved_with_sensor)

        tracked_ids = self._ports.tracked_entry_ids(result)
        writable_items = [item for item in resolved_with_sensor if self._ports.item_is_writable(item, tracked_ids)]

        processed_count = 0
        written_items: list[dict] = []
        sensor_ids: list[int] = []
        sample_ts_values: list[self._ports.datetime] = []
        zone_ids: list[int | None] = []
        sample_values: list[float] = []
        qualities: list[str] = []
        metadata_values: list[dict | None] = []
        for item in writable_items:
            sample = item["sample"]
            metadata = {
                "metric_type": sample.metric_type,
                "channel": sample.channel,
                "node_uid": sample.node_uid,
            }
            if bool(getattr(sample, "stub", False)):
                metadata["stub"] = True
            if sample.raw is not None:
                metadata["raw"] = sample.raw
            if metadata and not metadata.get("channel"):
                metadata.pop("channel", None)
            if metadata and not metadata.get("node_uid"):
                metadata.pop("node_uid", None)
            sensor_ids.append(int(item["sensor_id"]))
            sample_ts_values.append(self._ports.normalize_ts_for_db(sample.ts))
            zone_ids.append(int(item["zone_id"]) if item["zone_id"] is not None else None)
            sample_values.append(sample.value)
            qualities.append(self._ports.persist_quality_for_sample(sample))
            metadata_values.append(metadata or None)

        if sensor_ids:
            query = """
                WITH incoming (sensor_id, ts, zone_id, value, quality, metadata) AS (
                    SELECT *
                    FROM UNNEST(
                        $1::bigint[],
                        $2::timestamp[],
                        $3::bigint[],
                        $4::double precision[],
                        $5::text[],
                        $6::jsonb[]
                    ) AS t(sensor_id, ts, zone_id, value, quality, metadata)
                ), written AS (
                INSERT INTO telemetry_samples (
                    sensor_id, ts, zone_id, value, quality, metadata
                )
                SELECT
                    incoming.sensor_id,
                    incoming.ts,
                    incoming.zone_id,
                    incoming.value,
                    incoming.quality,
                    incoming.metadata
                FROM incoming
                JOIN sensors s
                  ON s.id = incoming.sensor_id
                 AND s.zone_id = incoming.zone_id
                RETURNING sensor_id, ts, value, quality
                ), projected AS (
                    INSERT INTO telemetry_last (sensor_id, last_value, last_ts, last_quality, updated_at)
                    SELECT DISTINCT ON (sensor_id) sensor_id, value, ts, quality, NOW()
                    FROM written ORDER BY sensor_id, ts DESC
                    ON CONFLICT (sensor_id) DO UPDATE SET
                        last_value=EXCLUDED.last_value, last_ts=EXCLUDED.last_ts,
                        last_quality=EXCLUDED.last_quality, updated_at=EXCLUDED.updated_at
                    WHERE EXCLUDED.last_ts > telemetry_last.last_ts
                    RETURNING sensor_id
                ) SELECT sensor_id, ts FROM written
            """
            try:
                returned_rows = await self._ports.fetch(
                    query,
                    sensor_ids,
                    sample_ts_values,
                    zone_ids,
                    sample_values,
                    qualities,
                    metadata_values,
                )
                written_items = self._ports.handle_samples_join_mismatch(
                    writable_items,
                    sensor_ids,
                    sample_ts_values,
                    returned_rows,
                    result,
                )
                processed_count = len(written_items)
                self._ports.logger().info(
                    "[TELEMETRY] Written: count=%s, unique_sensors=%s",
                    processed_count,
                    len({int(item["sensor_id"]) for item in written_items}),
                )
                if processed_count > 0 and self._ports.simulation_telemetry_events_enabled():
                    zone_stats: Dict[int, Dict[str, object]] = {}
                    for item in written_items:
                        zone_id = item.get("zone_id")
                        if zone_id is None:
                            continue
                        sample = item.get("sample")
                        metric_type = getattr(sample, "metric_type", None)
                        channel = getattr(sample, "channel", None)
                        stats = zone_stats.setdefault(zone_id, {"count": 0, "metrics": set(), "channels": set()})
                        stats["count"] = int(stats["count"]) + 1
                        if metric_type:
                            stats["metrics"].add(metric_type)
                        if channel:
                            stats["channels"].add(channel)

                    for zone_id, stats in zone_stats.items():
                        await self._ports.record_simulation_event_throttled(
                            zone_id,
                            service="history-logger",
                            stage="telemetry",
                            status="received",
                            message="Телеметрия принята",
                            payload={
                                "samples": stats["count"],
                                "metrics": sorted(stats["metrics"]),
                                "channels": sorted(stats["channels"]),
                            },
                            min_interval_seconds=self._ports.simulation_telemetry_event_interval_sec(),
                            throttle_key=f"telemetry:{zone_id}",
                        )
            except Exception as e:
                error_type = type(e).__name__
                self._ports.database_errors().labels(error_type=error_type).inc()
                if self._ports.is_pg_transport_error(e):
                    raise PgTransportError(str(e)) from e
                self._ports.logger().error(
                    "Failed to insert telemetry batch, retrying per-item",
                    extra={
                        "error_type": error_type,
                        "error": str(e),
                        "samples_count": len(writable_items),
                    },
                    exc_info=True,
                )
                if self._ports.is_sensor_fk_error(e):
                    self._ports.sensor_cache().clear()
                for item in writable_items:
                    if await self._ports.insert_telemetry_sample_item(item, result):
                        written_items.append(item)
                        processed_count += 1

        if written_items:
            written_sensor_ids = {int(item["sensor_id"]) for item in written_items}
            last_updates_for_written = {
                sensor_id: update_data
                for sensor_id, update_data in telemetry_last_updates.items()
                if sensor_id in written_sensor_ids
            }
            await self._ports.upsert_telemetry_last_batch(
                last_updates_for_written,
                resolved_with_sensor,
                result,
                samples_committed=True,
            )
        return written_items, processed_count
