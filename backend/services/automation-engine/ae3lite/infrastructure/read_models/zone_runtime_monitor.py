"""Live runtime monitor queries for AE3-Lite cycle_start execution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from common.db import get_pool


class PgZoneRuntimeMonitor:
    """Reads fresh telemetry and irr-state snapshots during AE3 execution."""

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
        return {}

    async def read_level_switch(
        self,
        *,
        zone_id: int,
        sensor_labels: Sequence[str],
        threshold: float,
        telemetry_max_age_sec: int,
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
        if row is None:
            return {"has_level": False, "is_stale": False, "is_triggered": False, "expected_labels": labels}

        raw_level = row.get("level")
        try:
            level = float(raw_level) if raw_level is not None else None
        except (TypeError, ValueError):
            level = None
        sample_ts = row.get("sample_ts")
        age_sec = self._age_sec(sample_ts)
        is_stale = bool(level is not None and ((age_sec or 0.0) > max(0, int(telemetry_max_age_sec))))
        return {
            "sensor_id": row.get("sensor_id"),
            "sensor_label": row.get("sensor_label"),
            "level": level,
            "sample_ts": sample_ts,
            "sample_age_sec": age_sec,
            "has_level": level is not None,
            "is_stale": is_stale,
            "is_triggered": bool(level is not None and level >= float(threshold)),
            "expected_labels": labels,
        }

    async def read_metric(self, *, zone_id: int, sensor_type: str, telemetry_max_age_sec: int) -> Mapping[str, Any]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
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

    async def read_latest_irr_state(self, *, zone_id: int, max_age_sec: int) -> Mapping[str, Any]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT payload_json, details, created_at
                FROM zone_events
                WHERE zone_id = $1
                  AND type = 'IRR_STATE_SNAPSHOT'
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                zone_id,
            )
        if row is None:
            return {"has_snapshot": False, "is_stale": False, "snapshot": None}

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
        }
