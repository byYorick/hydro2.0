"""DB query helpers for telemetry and workflow event reads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

FetchFn = Callable[..., Awaitable[Sequence[Dict[str, Any]]]]
ParseIsoFn = Callable[[str], Optional[datetime]]
CanonicalizeLabelFn = Callable[[Any], str]


def _normalize_sample_datetime(raw: Any, *, parse_iso_datetime: ParseIsoFn) -> Optional[datetime]:
    if isinstance(raw, datetime):
        sample_dt = raw
    elif isinstance(raw, str):
        sample_dt = parse_iso_datetime(raw)
    else:
        sample_dt = None

    if isinstance(sample_dt, datetime) and sample_dt.tzinfo is not None:
        sample_dt = sample_dt.astimezone(timezone.utc).replace(tzinfo=None)
    return sample_dt


async def read_level_switch(
    *,
    fetch_fn: FetchFn,
    parse_iso_datetime: ParseIsoFn,
    canonicalize_label: CanonicalizeLabelFn,
    zone_id: int,
    sensor_labels: Sequence[str],
    threshold: float,
    telemetry_max_age_sec: int,
) -> Dict[str, Any]:
    labels = [str(item).strip().lower() for item in sensor_labels if str(item).strip()]
    canonical_labels: List[str] = []
    for item in labels:
        canonical = canonicalize_label(item)
        if canonical:
            canonical_labels.append(canonical)
    if not labels:
        return {
            "sensor_id": None,
            "sensor_label": None,
            "level": None,
            "sample_ts": None,
            "sample_age_sec": None,
            "is_stale": False,
            "has_level": False,
            "is_triggered": False,
            "expected_labels": [],
            "available_sensor_labels": [],
            "level_source": "none",
        }

    rows = await fetch_fn(
        """
        SELECT
            s.id AS sensor_id,
            s.label AS sensor_label,
            COALESCE(tl.last_value, ts_fallback.value) AS level,
            COALESCE(tl.last_ts, tl.updated_at, ts_fallback.ts) AS sample_ts,
            CASE
                WHEN tl.last_value IS NOT NULL THEN 'telemetry_last'
                WHEN ts_fallback.value IS NOT NULL THEN 'telemetry_samples_fallback'
                ELSE 'none'
            END AS level_source
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
          AND s.type IN ('WATER_LEVEL', 'WATER_LEVEL_SWITCH')
          AND s.is_active = TRUE
          AND LOWER(TRIM(COALESCE(s.label, ''))) = ANY($2::text[])
        ORDER BY
            COALESCE(tl.last_ts, tl.updated_at, ts_fallback.ts) DESC NULLS LAST,
            s.id DESC
        LIMIT 1
        """,
        zone_id,
        labels,
    )
    matched_by = "exact"

    if not rows:
        candidate_rows = await fetch_fn(
            """
            SELECT
                s.id AS sensor_id,
                s.label AS sensor_label,
                COALESCE(tl.last_value, ts_fallback.value) AS level,
                COALESCE(tl.last_ts, tl.updated_at, ts_fallback.ts) AS sample_ts,
                CASE
                    WHEN tl.last_value IS NOT NULL THEN 'telemetry_last'
                    WHEN ts_fallback.value IS NOT NULL THEN 'telemetry_samples_fallback'
                    ELSE 'none'
                END AS level_source
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
              AND s.type IN ('WATER_LEVEL', 'WATER_LEVEL_SWITCH')
              AND s.is_active = TRUE
            ORDER BY
                COALESCE(tl.last_ts, tl.updated_at, ts_fallback.ts) DESC NULLS LAST,
                s.id DESC
            """,
            zone_id,
        )
        selected_row = None
        available_sensor_labels: List[str] = []
        for candidate in candidate_rows:
            label = str(candidate.get("sensor_label") or "").strip()
            if label:
                available_sensor_labels.append(label)
            canonical_label = canonicalize_label(label)
            if canonical_label and canonical_label in canonical_labels and selected_row is None:
                selected_row = candidate

        if selected_row is None:
            return {
                "sensor_id": None,
                "sensor_label": None,
                "level": None,
                "sample_ts": None,
                "sample_age_sec": None,
                "is_stale": False,
                "has_level": False,
                "is_triggered": False,
                "expected_labels": labels,
                "available_sensor_labels": available_sensor_labels,
                "level_source": "none",
            }

        rows = [selected_row]
        matched_by = "canonical"

    row = rows[0]
    raw_level = row.get("level")
    try:
        level = float(raw_level) if raw_level is not None else None
    except (TypeError, ValueError):
        level = None

    sample_dt = _normalize_sample_datetime(row.get("sample_ts"), parse_iso_datetime=parse_iso_datetime)
    sample_ts = sample_dt.isoformat() if isinstance(sample_dt, datetime) else None
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    sample_age_sec = max(0.0, (now_utc_naive - sample_dt).total_seconds()) if sample_dt else None
    has_level = level is not None
    is_stale = bool(has_level and (sample_dt is None or (sample_age_sec or 0.0) > telemetry_max_age_sec))

    return {
        "sensor_id": row.get("sensor_id"),
        "sensor_label": row.get("sensor_label"),
        "level": level,
        "sample_ts": sample_ts,
        "sample_age_sec": sample_age_sec,
        "is_stale": is_stale,
        "has_level": has_level,
        "is_triggered": bool(has_level and level >= threshold),
        "expected_labels": labels,
        "available_sensor_labels": [str(row.get("sensor_label") or "").strip()] if str(row.get("sensor_label") or "").strip() else [],
        "matched_by": matched_by,
        "level_source": str(row.get("level_source") or "none"),
    }


async def read_latest_metric(
    *,
    fetch_fn: FetchFn,
    parse_iso_datetime: ParseIsoFn,
    zone_id: int,
    sensor_type: str,
    telemetry_max_age_sec: int,
) -> Dict[str, Any]:
    rows = await fetch_fn(
        """
        SELECT
            s.id AS sensor_id,
            s.label AS sensor_label,
            tl.last_value AS value,
            COALESCE(tl.last_ts, tl.updated_at) AS sample_ts
        FROM sensors s
        LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
        WHERE s.zone_id = $1
          AND s.type = $2
          AND s.is_active = TRUE
        ORDER BY
            COALESCE(tl.last_ts, tl.updated_at) DESC NULLS LAST,
            s.id DESC
        LIMIT 1
        """,
        zone_id,
        sensor_type,
    )
    if not rows:
        return {
            "sensor_id": None,
            "sensor_label": None,
            "value": None,
            "sample_ts": None,
            "sample_age_sec": None,
            "is_stale": False,
            "has_value": False,
        }

    row = rows[0]
    raw_value = row.get("value")
    try:
        value = float(raw_value) if raw_value is not None else None
    except (TypeError, ValueError):
        value = None

    sample_dt = _normalize_sample_datetime(row.get("sample_ts"), parse_iso_datetime=parse_iso_datetime)
    sample_ts = sample_dt.isoformat() if isinstance(sample_dt, datetime) else None
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    sample_age_sec = max(0.0, (now_utc_naive - sample_dt).total_seconds()) if sample_dt else None
    has_value = value is not None
    is_stale = bool(has_value and (sample_dt is None or (sample_age_sec or 0.0) > telemetry_max_age_sec))
    return {
        "sensor_id": row.get("sensor_id"),
        "sensor_label": row.get("sensor_label"),
        "value": value,
        "sample_ts": sample_ts,
        "sample_age_sec": sample_age_sec,
        "is_stale": is_stale,
        "has_value": has_value,
    }


async def read_clean_tank_level(
    *,
    fetch_fn: FetchFn,
    parse_iso_datetime: ParseIsoFn,
    zone_id: int,
    threshold: float,
    telemetry_max_age_sec: int,
) -> Dict[str, Any]:
    rows = await fetch_fn(
        """
        SELECT
            s.id AS sensor_id,
            s.label AS sensor_label,
            tl.last_value AS level,
            COALESCE(tl.last_ts, tl.updated_at) AS sample_ts
        FROM sensors s
        LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
        WHERE s.zone_id = $1
          AND s.type = 'WATER_LEVEL'
          AND s.is_active = TRUE
        ORDER BY
            CASE
                WHEN LOWER(COALESCE(s.label, '')) LIKE '%clean%' THEN 0
                WHEN LOWER(COALESCE(s.label, '')) LIKE '%fresh%' THEN 0
                WHEN LOWER(COALESCE(s.label, '')) LIKE '%чист%' THEN 0
                WHEN LOWER(COALESCE(s.label, '')) LIKE '%drain%' THEN 2
                WHEN LOWER(COALESCE(s.label, '')) LIKE '%waste%' THEN 2
                WHEN LOWER(COALESCE(s.label, '')) LIKE '%слив%' THEN 2
                ELSE 1
            END ASC,
            COALESCE(tl.last_ts, tl.updated_at) DESC NULLS LAST,
            s.id DESC
        LIMIT 1
        """,
        zone_id,
    )
    if not rows:
        return {
            "sensor_id": None,
            "sensor_label": None,
            "level": None,
            "sample_ts": None,
            "sample_age_sec": None,
            "is_stale": False,
            "threshold": threshold,
            "has_level": False,
            "is_full": False,
        }

    row = rows[0]
    level_value = row.get("level")
    try:
        level = float(level_value) if level_value is not None else None
    except (TypeError, ValueError):
        level = None

    has_level = level is not None
    is_full = bool(has_level and level >= threshold)
    sample_dt = _normalize_sample_datetime(row.get("sample_ts"), parse_iso_datetime=parse_iso_datetime)
    sample_ts = sample_dt.isoformat() if isinstance(sample_dt, datetime) else None
    now_utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    sample_age_sec = max(0.0, (now_utc_naive - sample_dt).total_seconds()) if sample_dt else None
    is_stale = bool(has_level and (sample_dt is None or (sample_age_sec or 0.0) > telemetry_max_age_sec))
    return {
        "sensor_id": row.get("sensor_id"),
        "sensor_label": row.get("sensor_label"),
        "level": level,
        "sample_ts": sample_ts,
        "sample_age_sec": sample_age_sec,
        "is_stale": is_stale,
        "threshold": threshold,
        "has_level": has_level,
        "is_full": is_full,
    }


async def find_zone_event_since(
    *,
    fetch_fn: FetchFn,
    zone_id: int,
    event_types: Sequence[str],
    since: Optional[datetime],
) -> Optional[Dict[str, Any]]:
    normalized_types = [str(item).strip().upper() for item in event_types if str(item).strip()]
    if not normalized_types or since is None:
        return None

    rows = await fetch_fn(
        """
        SELECT id, type, created_at, payload_json AS details
        FROM zone_events
        WHERE zone_id = $1
          AND type = ANY($2::text[])
          AND created_at >= $3
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        zone_id,
        normalized_types,
        since,
    )
    if not rows:
        return None
    return dict(rows[0])


__all__ = [
    "find_zone_event_since",
    "read_clean_tank_level",
    "read_latest_metric",
    "read_level_switch",
]
