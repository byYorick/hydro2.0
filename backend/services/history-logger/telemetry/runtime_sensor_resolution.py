"""runtime sensor resolution: explicit dependencies and invocation data."""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from telemetry.runtime_records import PgTransportError, TelemetryBatchResult


@dataclass(frozen=True)
class RuntimeSensorResolutionPorts:
    telemetry_dropped: Callable[..., Any]
    telemetry_pg_write_failed: Callable[..., Any]
    append_dead_entry: Callable[..., Any]
    build_sensor_label: Callable[..., Any]
    create_sensors_per_item: Callable[..., Any]
    filter_existing_sensor_ids: Callable[..., Any]
    infer_sensor_scope: Callable[..., Any]
    infer_sensor_type: Callable[..., Any]
    is_pg_transport_error: Callable[..., Any]
    is_sensor_fk_error: Callable[..., Any]
    node_cache: Callable[..., Any]
    sensor_cache: Callable[..., Any]
    sensor_cache_get: Callable[..., Any]
    sensor_cache_set: Callable[..., Any]
    set_cache_last_update: Callable[..., Any]
    zone_cache: Callable[..., Any]
    zone_greenhouse_cache: Callable[..., Any]
    fetch: Callable[..., Any]
    logger: Callable[..., Any]


class RuntimeSensorResolution:
    def __init__(self, ports: RuntimeSensorResolutionPorts) -> None:
        self._ports = ports

    async def resolve_batch_sensors(self, *, resolved_samples: Any, result: TelemetryBatchResult) -> list[dict]:
        missing_sensor_keys: set[tuple[int, Optional[int], str, str]] = set()
        for item in resolved_samples:
            sample = item["sample"]
            sensor_type = self._ports.infer_sensor_type(sample.metric_type)
            sensor_label = self._ports.build_sensor_label(sample.metric_type, sample.channel, sensor_type)
            sensor_key = (item["zone_id"], item["node_id"], sensor_type, sensor_label)
            item["sensor_key"] = sensor_key
            item["sensor_type"] = sensor_type
            item["sensor_label"] = sensor_label
            if self._ports.sensor_cache_get(sensor_key) is None:
                missing_sensor_keys.add(sensor_key)

        if missing_sensor_keys:
            zone_ids = list({key[0] for key in missing_sensor_keys})
            node_ids = list({key[1] for key in missing_sensor_keys if key[1] is not None})
            existing_rows = []
            if zone_ids:
                if node_ids:
                    existing_rows = await self._ports.fetch(
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
                    existing_rows = await self._ports.fetch(
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
                    self._ports.sensor_cache_set(sensor_key, sensor_id)

            to_create = [key for key in missing_sensor_keys if self._ports.sensor_cache_get(key) is None]
            if to_create:
                values_list = []
                params_list = []
                param_index = 1
                for zone_id, node_id, sensor_type, sensor_label in to_create:
                    greenhouse_id = self._ports.zone_greenhouse_cache().get(zone_id)
                    if greenhouse_id is None:
                        self._ports.logger().warning(
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
                            self._ports.infer_sensor_scope(sensor_type, sensor_label),
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
                    created_rows: list = []
                    try:
                        created_rows = await self._ports.fetch(query, *params_list)
                    except Exception as e:
                        if self._ports.is_sensor_fk_error(e):
                            self._ports.logger().warning(
                                "Sensor FK violation detected during sensor upsert, clearing caches",
                                extra={"error": str(e)},
                            )
                            self._ports.sensor_cache().clear()
                            self._ports.zone_cache().clear()
                            self._ports.node_cache().clear()
                            self._ports.zone_greenhouse_cache().clear()
                            self._ports.set_cache_last_update(0.0)
                            await self._ports.create_sensors_per_item(to_create)
                        elif self._ports.is_pg_transport_error(e):
                            raise PgTransportError(str(e)) from e
                        else:
                            self._ports.telemetry_pg_write_failed().labels(stage="sensors").inc()
                            self._ports.logger().error(
                                "Batch sensor upsert failed, retrying per-item",
                                extra={"error": str(e)},
                                exc_info=True,
                            )
                            await self._ports.create_sensors_per_item(to_create)
                    for row in created_rows:
                        zone_id = row.get("zone_id")
                        sensor_type = row.get("type")
                        sensor_label = row.get("label")
                        sensor_id = row.get("id")
                        if zone_id is not None and sensor_type and sensor_label and sensor_id is not None:
                            sensor_key = (
                                zone_id,
                                row.get("node_id"),
                                sensor_type,
                                sensor_label,
                            )
                            self._ports.sensor_cache_set(sensor_key, sensor_id)

        resolved_with_sensor: list[dict] = []
        for item in resolved_samples:
            sensor_id = self._ports.sensor_cache_get(item["sensor_key"])
            if sensor_id is None:
                self._ports.logger().warning(
                    "Sensor not resolved for telemetry sample",
                    extra={
                        "zone_id": item["zone_id"],
                        "node_id": item["node_id"],
                        "metric_type": item["sample"].metric_type,
                        "channel": item["sample"].channel,
                    },
                )
                self._ports.telemetry_dropped().labels(reason="sensor_not_resolved").inc()
                self._ports.append_dead_entry(result, item.get("entry"))
                continue
            item["sensor_id"] = sensor_id
            resolved_with_sensor.append(item)

        if not resolved_with_sensor:
            return []

        unique_sensor_ids = sorted(
            {int(item["sensor_id"]) for item in resolved_with_sensor if item.get("sensor_id") is not None}
        )
        existing_sensor_ids = await self._ports.filter_existing_sensor_ids(unique_sensor_ids)
        if len(existing_sensor_ids) != len(unique_sensor_ids):
            stale_sensor_ids = sorted(set(unique_sensor_ids) - existing_sensor_ids)
            self._ports.logger().warning(
                "Dropping telemetry samples for stale sensor cache entries",
                extra={"stale_sensor_ids": stale_sensor_ids},
            )
            fresh_items: list[dict] = []
            for item in resolved_with_sensor:
                sensor_id = int(item["sensor_id"])
                if sensor_id in existing_sensor_ids:
                    fresh_items.append(item)
                    continue
                self._ports.sensor_cache().pop(item["sensor_key"], None)
                self._ports.telemetry_dropped().labels(reason="stale_sensor_cache").inc()
                self._ports.append_dead_entry(result, item.get("entry"))
            resolved_with_sensor = fresh_items

        if not resolved_with_sensor:
            return []
        return resolved_with_sensor

    async def create_sensors_per_item(self, to_create: list[tuple[int, Optional[int], str, str]]) -> None:
        for zone_id, node_id, sensor_type, sensor_label in to_create:
            greenhouse_id = self._ports.zone_greenhouse_cache().get(zone_id)
            if greenhouse_id is None:
                self._ports.logger().warning(
                    "Greenhouse not found for zone_id=%s, skipping sensor creation",
                    zone_id,
                )
                continue
            try:
                created_rows = await self._ports.fetch(
                    """
                    INSERT INTO sensors (
                        greenhouse_id, zone_id, node_id, scope, type, label, is_active,
                        created_at, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
                    ON CONFLICT (zone_id, node_id, scope, type, label)
                    DO UPDATE SET updated_at = EXCLUDED.updated_at
                    RETURNING id, zone_id, node_id, type, label
                    """,
                    greenhouse_id,
                    zone_id,
                    node_id,
                    self._ports.infer_sensor_scope(sensor_type, sensor_label),
                    sensor_type,
                    sensor_label,
                    True,
                )
            except Exception as e:
                if self._ports.is_pg_transport_error(e):
                    raise PgTransportError(str(e)) from e
                self._ports.logger().warning(
                    "Per-item sensor upsert failed",
                    extra={
                        "zone_id": zone_id,
                        "node_id": node_id,
                        "sensor_type": sensor_type,
                        "sensor_label": sensor_label,
                        "error": str(e),
                    },
                )
                continue
            for row in created_rows:
                row_zone_id = row.get("zone_id")
                row_sensor_type = row.get("type")
                row_sensor_label = row.get("label")
                sensor_id = row.get("id")
                if row_zone_id is not None and row_sensor_type and row_sensor_label and sensor_id is not None:
                    sensor_key = (
                        row_zone_id,
                        row.get("node_id"),
                        row_sensor_type,
                        row_sensor_label,
                    )
                    self._ports.sensor_cache_set(sensor_key, sensor_id)
