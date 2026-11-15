"""PgZoneRuntimeMonitor levels: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ae3lite.domain.level_switch_semantics import confirmed_level_switch, newer_level_sample


@dataclass(frozen=True)
class RuntimeMonitorLevelsPorts:
    age_sec: Callable[..., Any]
    coerce_optional_bool: Callable[..., Any]
    extract_level_state_from_event: Callable[..., Any]
    normalize_labels: Callable[..., Any]
    payload_field: Callable[..., Any]
    prefer_event_over_telemetry: Callable[..., Any]
    resolve_zone_event_payload: Callable[..., Any]
    global_get_pool: Callable[..., Any]


class RuntimeMonitorLevels:
    def __init__(self, ports: RuntimeMonitorLevelsPorts) -> None:
        self._ports = ports

    async def read_latest_level_switch_event(
        self,
        *,
        zone_id: int,
        sensor_labels: Sequence[str],
        max_age_sec: int,
        allow_initial_event: bool = False,
    ) -> Mapping[str, Any] | None:
        labels = self._ports.normalize_labels(sensor_labels)
        if not labels:
            return None

        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, payload_json, details, created_at
                FROM zone_events
                WHERE zone_id = $1
                  AND type = 'LEVEL_SWITCH_CHANGED'
                  AND created_at >= NOW() - ($2::int * INTERVAL '1 second')
                ORDER BY created_at DESC, id DESC
                LIMIT 24
                """,
                zone_id,
                max(1, int(max_age_sec)),
            )

        for row in rows:
            payload = self._ports.resolve_zone_event_payload(row)
            initial = self._ports.coerce_optional_bool(self._ports.payload_field(payload, "initial"))
            if initial is True and not allow_initial_event:
                continue
            lookup = self._ports.extract_level_state_from_event(payload=payload, labels=labels)
            if lookup is None:
                continue
            resolved_label, is_triggered = lookup
            created_at = row.get("created_at")
            age_sec = self._ports.age_sec(created_at)
            return {
                "event_id": row.get("id"),
                "sensor_label": resolved_label,
                "level": 1.0 if is_triggered else 0.0,
                "sample_ts": created_at,
                "sample_age_sec": age_sec,
                "has_level": True,
                "is_stale": bool((age_sec or 0.0) > max(0, int(max_age_sec))),
                "is_triggered": is_triggered,
                "expected_labels": labels,
                "source": "zone_event_level_switch",
                "is_initial_event": bool(initial),
                "channel": self._ports.payload_field(payload, "channel"),
                "snapshot": self._ports.payload_field(payload, "snapshot"),
            }
        return None

    async def read_metric_sensor(self, *, zone_id: int, sensor_type: str) -> Mapping[str, Any] | None:
        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT
                    s.id AS sensor_id,
                    s.label AS sensor_label,
                    tl.last_value AS value,
                    COALESCE(tl.last_ts, tl.updated_at) AS sample_ts,
                    tl.last_quality AS last_quality
                FROM sensors s
                LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
                WHERE s.zone_id = $1
                  AND s.is_active = TRUE
                  AND s.type = $2
                ORDER BY COALESCE(tl.last_ts, tl.updated_at) DESC NULLS LAST, s.id DESC
                LIMIT 1
                """,
                zone_id,
                sensor_type,
            )

    async def read_level_switch(
        self,
        *,
        zone_id: int,
        sensor_labels: Sequence[str],
        threshold: float,
        telemetry_max_age_sec: int,
        allow_initial_event: bool = False,
        allow_initial_event_fallback: bool = False,
    ) -> Mapping[str, Any]:
        labels = self._ports.normalize_labels(sensor_labels)
        if not labels:
            return {"has_level": False, "is_stale": False, "is_triggered": False, "expected_labels": []}

        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    s.id AS sensor_id,
                    s.label AS sensor_label,
                    COALESCE(tl.last_value, ts_fallback.value) AS level,
                    COALESCE(tl.last_ts, tl.updated_at, ts_fallback.ts) AS sample_ts
                FROM sensors s
                LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
                LEFT JOIN LATERAL (
                    SELECT ts, value
                    FROM telemetry_samples t
                    WHERE t.sensor_id = s.id
                    ORDER BY t.ts DESC, t.id DESC
                    LIMIT 1
                ) ts_fallback ON TRUE
                WHERE s.zone_id = $1
                  AND s.is_active = TRUE
                  AND s.type IN ('WATER_LEVEL', 'WATER_LEVEL_SWITCH')
                  AND LOWER(TRIM(COALESCE(s.label, ''))) = ANY($2::text[])
                ORDER BY COALESCE(tl.last_ts, tl.updated_at, ts_fallback.ts) DESC NULLS LAST, s.id DESC
                LIMIT 1
                """,
                zone_id,
                labels,
            )
        event_level = await self.read_latest_level_switch_event(
            zone_id=zone_id,
            sensor_labels=labels,
            max_age_sec=telemetry_max_age_sec,
            allow_initial_event=False,
        )
        initial_event_level: Mapping[str, Any] | None = None
        if allow_initial_event or allow_initial_event_fallback:
            initial_event_level = await self.read_latest_level_switch_event(
                zone_id=zone_id,
                sensor_labels=labels,
                max_age_sec=telemetry_max_age_sec,
                allow_initial_event=True,
            )
            if initial_event_level is not None and not bool(initial_event_level.get("is_initial_event")):
                initial_event_level = None

        if row is None:
            chosen = newer_level_sample(event_level, initial_event_level)
            return chosen or {"has_level": False, "is_stale": False, "is_triggered": False, "expected_labels": labels}

        raw_level = row.get("level")
        try:
            level = float(raw_level) if raw_level is not None else None
        except (TypeError, ValueError):
            level = None
        sample_ts = row.get("sample_ts")
        age_sec = self._ports.age_sec(sample_ts)
        has_level, is_triggered = confirmed_level_switch(value=level, threshold=float(threshold))
        is_stale = bool(has_level and ((age_sec or 0.0) > max(0, int(telemetry_max_age_sec))))
        telemetry_level = {
            "sensor_id": row.get("sensor_id"),
            "sensor_label": row.get("sensor_label"),
            "level": level,
            "sample_ts": sample_ts,
            "sample_age_sec": age_sec,
            "has_level": has_level,
            "is_stale": is_stale,
            "is_triggered": is_triggered,
            "expected_labels": labels,
            "source": "telemetry_last",
        }
        # Stale или небинарная телеметрия не должна затирать более новый initial.
        if not has_level or is_stale:
            chosen = newer_level_sample(event_level, initial_event_level)
            if chosen is not None:
                return chosen
            return telemetry_level
        if event_level is None:
            preferred_initial = self._ports.prefer_event_over_telemetry(
                telemetry_level=telemetry_level,
                event_level=initial_event_level,
                allow_if_telemetry_fresh=bool(allow_initial_event),
            )
            if preferred_initial is not None:
                return preferred_initial
            return telemetry_level

        preferred_event = self._ports.prefer_event_over_telemetry(
            telemetry_level=telemetry_level,
            event_level=event_level,
            allow_if_telemetry_fresh=True,
        )
        if preferred_event is not None:
            return preferred_event

        preferred_initial = self._ports.prefer_event_over_telemetry(
            telemetry_level=telemetry_level,
            event_level=initial_event_level,
            allow_if_telemetry_fresh=bool(allow_initial_event),
        )
        if preferred_initial is not None:
            return preferred_initial
        return telemetry_level
