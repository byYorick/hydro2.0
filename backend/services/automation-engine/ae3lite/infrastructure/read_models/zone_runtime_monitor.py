"""Запросы live runtime monitor для выполнения cycle_start в AE3-Lite."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from common.db import get_pool

logger = logging.getLogger(__name__)


class PgZoneRuntimeMonitor:
    """Читает свежую телеметрию и snapshot'ы irr-state во время выполнения AE3."""

    def _normalize_timestamp(self, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        normalized = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
        return normalized.replace(microsecond=0)

    def _normalize_labels(self, labels: Sequence[str]) -> list[str]:
        result: list[str] = []
        for item in labels:
            normalized = str(item or "").strip().lower()
            if normalized:
                result.append(normalized)
        return result

    def _age_sec(self, sample_ts: Optional[datetime]) -> Optional[float]:
        if sample_ts is None:
            return None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        normalized = sample_ts.astimezone(timezone.utc).replace(tzinfo=None) if sample_ts.tzinfo else sample_ts
        return max(0.0, (now - normalized).total_seconds())

    def _resolve_zone_event_payload(self, row: Mapping[str, Any]) -> Mapping[str, Any]:
        for field_name in ("details", "payload_json", "payload"):
            value = row.get(field_name)
            if isinstance(value, Mapping):
                return value
        logger.warning(
            "AE3 zone runtime monitor: zone_event payload is not a mapping row_id=%s event_type=%s",
            row.get("id"),
            row.get("event_type"),
        )
        return {}

    def _coerce_optional_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if float(value) == 1.0:
                return True
            if float(value) == 0.0:
                return False
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return None

    def _payload_field(self, payload: Mapping[str, Any], key: str) -> Any:
        value = payload.get(key)
        if value is not None:
            return value
        nested = payload.get("payload")
        if isinstance(nested, Mapping):
            return nested.get(key)
        return None

    def _level_snapshot_aliases(self, label: str) -> tuple[str, ...]:
        normalized = str(label or "").strip().lower()
        aliases = {normalized}
        if normalized.startswith("level_"):
            suffix = normalized[len("level_"):]
            parts = suffix.split("_")
            if len(parts) >= 2:
                aliases.add("_".join((parts[0], "level", *parts[1:])))
        parts = normalized.split("_")
        if len(parts) >= 3 and parts[1] == "level":
            aliases.add("_".join(("level", parts[0], *parts[2:])))
        return tuple(alias for alias in aliases if alias)

    def _extract_level_state_from_event(
        self,
        *,
        payload: Mapping[str, Any],
        labels: Sequence[str],
    ) -> tuple[str, bool] | None:
        event_channel = str(self._payload_field(payload, "channel") or "").strip().lower()
        event_state = self._coerce_optional_bool(self._payload_field(payload, "state"))
        normalized_labels = self._normalize_labels(labels)
        if event_channel and event_state is not None:
            for label in normalized_labels:
                if event_channel in self._level_snapshot_aliases(label):
                    return event_channel, event_state

        snapshot = self._payload_field(payload, "snapshot")
        if not isinstance(snapshot, Mapping):
            return None
        normalized_snapshot = {
            str(key or "").strip().lower(): value
            for key, value in snapshot.items()
            if str(key or "").strip()
        }
        for label in normalized_labels:
            for alias in self._level_snapshot_aliases(label):
                if alias not in normalized_snapshot:
                    continue
                snapshot_state = self._coerce_optional_bool(normalized_snapshot.get(alias))
                if snapshot_state is not None:
                    return alias, snapshot_state
        return None

    async def read_latest_level_switch_event(
        self,
        *,
        zone_id: int,
        sensor_labels: Sequence[str],
        max_age_sec: int,
        allow_initial_event: bool = False,
    ) -> Mapping[str, Any] | None:
        labels = self._normalize_labels(sensor_labels)
        if not labels:
            return None

        pool = await get_pool()
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
            payload = self._resolve_zone_event_payload(row)
            initial = self._coerce_optional_bool(self._payload_field(payload, "initial"))
            if initial is True and not allow_initial_event:
                continue
            lookup = self._extract_level_state_from_event(payload=payload, labels=labels)
            if lookup is None:
                continue
            resolved_label, is_triggered = lookup
            created_at = row.get("created_at")
            age_sec = self._age_sec(created_at)
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
                "channel": self._payload_field(payload, "channel"),
                "snapshot": self._payload_field(payload, "snapshot"),
            }
        return None

    def _prefer_event_over_telemetry(
        self,
        *,
        telemetry_level: Mapping[str, Any],
        event_level: Mapping[str, Any] | None,
        allow_if_telemetry_fresh: bool,
    ) -> Mapping[str, Any] | None:
        if event_level is None:
            return None
        if not telemetry_level["has_level"] or telemetry_level["is_stale"]:
            return event_level
        if not allow_if_telemetry_fresh:
            return None

        telemetry_ts = telemetry_level.get("sample_ts")
        event_ts = event_level.get("sample_ts")
        if isinstance(event_ts, datetime) and isinstance(telemetry_ts, datetime) and event_ts >= telemetry_ts:
            return event_level
        return None

    async def _read_metric_sensor(self, *, zone_id: int, sensor_type: str) -> Mapping[str, Any] | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT
                    s.id AS sensor_id,
                    s.label AS sensor_label,
                    tl.last_value AS value,
                    COALESCE(tl.last_ts, tl.updated_at) AS sample_ts
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
        labels = self._normalize_labels(sensor_labels)
        if not labels:
            return {"has_level": False, "is_stale": False, "is_triggered": False, "expected_labels": []}

        pool = await get_pool()
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
            return (
                event_level
                or initial_event_level
                or {"has_level": False, "is_stale": False, "is_triggered": False, "expected_labels": labels}
            )

        raw_level = row.get("level")
        try:
            level = float(raw_level) if raw_level is not None else None
        except (TypeError, ValueError):
            level = None
        sample_ts = row.get("sample_ts")
        age_sec = self._age_sec(sample_ts)
        is_stale = bool(level is not None and ((age_sec or 0.0) > max(0, int(telemetry_max_age_sec))))
        telemetry_level = {
            "sensor_id": row.get("sensor_id"),
            "sensor_label": row.get("sensor_label"),
            "level": level,
            "sample_ts": sample_ts,
            "sample_age_sec": age_sec,
            "has_level": level is not None,
            "is_stale": is_stale,
            "is_triggered": bool(level is not None and level >= float(threshold)),
            "expected_labels": labels,
            "source": "telemetry_last",
        }
        if event_level is None:
            preferred_initial = self._prefer_event_over_telemetry(
                telemetry_level=telemetry_level,
                event_level=initial_event_level,
                allow_if_telemetry_fresh=bool(allow_initial_event),
            )
            if preferred_initial is not None:
                return preferred_initial
            return telemetry_level

        preferred_event = self._prefer_event_over_telemetry(
            telemetry_level=telemetry_level,
            event_level=event_level,
            allow_if_telemetry_fresh=True,
        )
        if preferred_event is not None:
            return preferred_event

        preferred_initial = self._prefer_event_over_telemetry(
            telemetry_level=telemetry_level,
            event_level=initial_event_level,
            allow_if_telemetry_fresh=bool(allow_initial_event),
        )
        if preferred_initial is not None:
            return preferred_initial
        return telemetry_level

    async def read_metric(self, *, zone_id: int, sensor_type: str, telemetry_max_age_sec: int) -> Mapping[str, Any]:
        row = await self._read_metric_sensor(zone_id=zone_id, sensor_type=sensor_type)
        if row is None:
            return {"has_value": False, "is_stale": False, "value": None}

        raw_value = row.get("value")
        try:
            value = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            value = None
        sample_ts = row.get("sample_ts")
        age_sec = self._age_sec(sample_ts)
        is_stale = bool(value is not None and ((age_sec or 0.0) > max(0, int(telemetry_max_age_sec))))
        return {
            "sensor_id": row.get("sensor_id"),
            "sensor_label": row.get("sensor_label"),
            "value": value,
            "sample_ts": sample_ts,
            "sample_age_sec": age_sec,
            "has_value": value is not None,
            "is_stale": is_stale,
        }

    async def read_metric_window(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        since_ts: datetime,
        telemetry_max_age_sec: int,
        limit: int = 64,
    ) -> Mapping[str, Any]:
        normalized_since_ts = self._normalize_timestamp(since_ts)
        sensor_row = await self._read_metric_sensor(zone_id=zone_id, sensor_type=sensor_type)
        if sensor_row is None:
            return {
                "has_sensor": False,
                "has_samples": False,
                "is_stale": False,
                "sensor_id": None,
                "sensor_label": None,
                "samples": (),
                "latest_sample_ts": None,
            }

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ts, value
                FROM (
                    SELECT ts, value, id
                    FROM telemetry_samples
                    WHERE sensor_id = $1
                      AND ts >= $2
                    ORDER BY ts DESC, id DESC
                    LIMIT $3
                ) recent
                ORDER BY ts ASC, id ASC
                """,
                int(sensor_row["sensor_id"]),
                normalized_since_ts,
                max(1, int(limit)),
            )

        samples: list[dict[str, Any]] = []
        latest_sample_ts: Optional[datetime] = None
        for row in rows:
            raw_value = row.get("value")
            try:
                value = float(raw_value) if raw_value is not None else None
            except (TypeError, ValueError):
                value = None
            ts = row.get("ts")
            latest_sample_ts = ts if ts is not None else latest_sample_ts
            if value is None:
                continue
            samples.append({"ts": ts, "value": value})

        if latest_sample_ts is None:
            latest_sample_ts = sensor_row.get("sample_ts")
        age_sec = self._age_sec(latest_sample_ts)
        is_stale = bool(latest_sample_ts is not None and ((age_sec or 0.0) > max(0, int(telemetry_max_age_sec))))
        return {
            "has_sensor": True,
            "has_samples": bool(samples),
            "is_stale": is_stale,
            "sensor_id": sensor_row.get("sensor_id"),
            "sensor_label": sensor_row.get("sensor_label"),
            "samples": tuple(samples),
            "latest_sample_ts": latest_sample_ts,
            "sample_age_sec": age_sec,
        }

    async def read_metric_windows(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        since_ts: datetime,
        telemetry_max_age_sec: int,
        limit_per_sensor: int = 64,
    ) -> Mapping[str, Any]:
        normalized_since_ts = self._normalize_timestamp(since_ts)
        pool = await get_pool()
        async with pool.acquire() as conn:
            sensor_rows = await conn.fetch(
                """
                SELECT
                    s.id AS sensor_id,
                    s.label AS sensor_label,
                    COALESCE(tl.last_ts, tl.updated_at) AS sample_ts
                FROM sensors s
                LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
                WHERE s.zone_id = $1
                  AND s.is_active = TRUE
                  AND s.type = $2
                ORDER BY s.id ASC
                """,
                zone_id,
                sensor_type,
            )

            sensor_windows: list[dict[str, Any]] = []
            latest_sample_ts: Optional[datetime] = None
            for sensor_row in sensor_rows:
                rows = await conn.fetch(
                    """
                    SELECT ts, value
                    FROM (
                        SELECT ts, value, id
                        FROM telemetry_samples
                        WHERE sensor_id = $1
                          AND ts >= $2
                        ORDER BY ts DESC, id DESC
                        LIMIT $3
                    ) recent
                    ORDER BY ts ASC, id ASC
                    """,
                    int(sensor_row["sensor_id"]),
                    normalized_since_ts,
                    max(1, int(limit_per_sensor)),
                )
                samples: list[dict[str, Any]] = []
                sensor_latest_ts = sensor_row.get("sample_ts")
                for row in rows:
                    raw_value = row.get("value")
                    try:
                        value = float(raw_value) if raw_value is not None else None
                    except (TypeError, ValueError):
                        value = None
                    ts = row.get("ts")
                    if ts is not None:
                        sensor_latest_ts = ts
                    if value is None:
                        continue
                    samples.append({"ts": ts, "value": value})

                if sensor_latest_ts is not None and (latest_sample_ts is None or sensor_latest_ts > latest_sample_ts):
                    latest_sample_ts = sensor_latest_ts

                sensor_age_sec = self._age_sec(sensor_latest_ts)
                sensor_windows.append(
                    {
                        "sensor_id": sensor_row.get("sensor_id"),
                        "sensor_label": sensor_row.get("sensor_label"),
                        "samples": tuple(samples),
                        "latest_sample_ts": sensor_latest_ts,
                        "sample_age_sec": sensor_age_sec,
                        "is_stale": bool(
                            sensor_latest_ts is not None
                            and ((sensor_age_sec or 0.0) > max(0, int(telemetry_max_age_sec)))
                        ),
                    }
                )

        age_sec = self._age_sec(latest_sample_ts)
        return {
            "has_sensors": bool(sensor_windows),
            "sensor_windows": tuple(sensor_windows),
            "latest_sample_ts": latest_sample_ts,
            "sample_age_sec": age_sec,
            "is_stale": bool(latest_sample_ts is not None and ((age_sec or 0.0) > max(0, int(telemetry_max_age_sec)))),
        }

    async def read_latest_irr_state(
        self,
        *,
        zone_id: int,
        max_age_sec: int,
        expected_cmd_id: str | None = None,
    ) -> Mapping[str, Any]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    payload_json,
                    details,
                    created_at,
                    COALESCE(details->>'cmd_id', payload_json->>'cmd_id') AS snapshot_cmd_id
                FROM zone_events
                WHERE zone_id = $1
                  AND type = 'IRR_STATE_SNAPSHOT'
                  AND ($2::text IS NULL OR COALESCE(details->>'cmd_id', payload_json->>'cmd_id') = $2)
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                zone_id,
                expected_cmd_id,
            )
        if row is None:
            return {
                "has_snapshot": False,
                "is_stale": False,
                "snapshot": None,
                "cmd_id": expected_cmd_id,
            }

        payload = self._resolve_zone_event_payload(row)
        snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), Mapping) else None
        age_sec = self._age_sec(row.get("created_at"))
        is_stale = bool((age_sec or 0.0) > max(0, int(max_age_sec)))
        return {
            "has_snapshot": isinstance(snapshot, Mapping),
            "is_stale": is_stale,
            "snapshot": dict(snapshot) if isinstance(snapshot, Mapping) else None,
            "sample_age_sec": age_sec,
            "created_at": row.get("created_at"),
            "cmd_id": str(row.get("snapshot_cmd_id") or "").strip() or None,
        }

    async def read_latest_zone_event(
        self,
        *,
        zone_id: int,
        event_types: Sequence[str],
        max_age_sec: int,
        since_ts: datetime | None = None,
        channel: str | None = None,
    ) -> Mapping[str, Any] | None:
        normalized_event_types = [
            str(item or "").strip().upper()
            for item in event_types
            if str(item or "").strip()
        ]
        if not normalized_event_types:
            return None
        normalized_since_ts = self._normalize_timestamp(since_ts)
        normalized_channel = str(channel or "").strip().lower() or None

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, type, payload_json, details, created_at
                FROM zone_events
                WHERE zone_id = $1
                  AND type = ANY($2::text[])
                  AND created_at >= NOW() - ($3::int * INTERVAL '1 second')
                  AND ($4::timestamp IS NULL OR created_at >= $4)
                  AND (
                    $5::text IS NULL
                    OR LOWER(TRIM(COALESCE(details->>'channel', payload_json->>'channel', ''))) = $5
                  )
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                zone_id,
                normalized_event_types,
                max(1, int(max_age_sec)),
                normalized_since_ts,
                normalized_channel,
            )
        if row is None:
            return None

        payload = self._resolve_zone_event_payload(row)
        age_sec = self._age_sec(row.get("created_at"))
        return {
            "event_id": row.get("id"),
            "event_type": str(row.get("type") or "").strip().upper(),
            "payload": dict(payload) if isinstance(payload, Mapping) else {},
            "created_at": row.get("created_at"),
            "sample_age_sec": age_sec,
            "is_stale": bool((age_sec or 0.0) > max(0, int(max_age_sec))),
        }
