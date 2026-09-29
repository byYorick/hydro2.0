"""Метки успешных кадров полива из zone_events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ae4.domain.planting import LightIntegralCursor, PhaseTargets, ShotMark
from ae4.domain.water_demand import count_successful_shots_in_active_span
from common.db import create_zone_event, execute, fetch

_SHOT_EVENT_TYPE = "AE4_IRRIGATION_SHOT"
_CURSOR_EVENT_TYPE = "AE4_LIGHT_INTEGRAL_CURSOR"


def _as_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc)
    return value.replace(tzinfo=timezone.utc)


async def load_shot_marks(
    *,
    zone_id: int,
    phase_id: int,
    now: datetime,
    timezone_name: str,
    phase: PhaseTargets,
) -> tuple[ShotMark | None, datetime | None, bool, int]:
    """last_shot, last_planned_shot_at, extra_used, успешные кадры текущего окна."""
    rows = await fetch(
        """
        SELECT payload_json, created_at
        FROM zone_events
        WHERE zone_id = $1
          AND type = $2
        ORDER BY created_at DESC, id DESC
        LIMIT 200
        """,
        zone_id,
        _SHOT_EVENT_TYPE,
    )
    last_shot: ShotMark | None = None
    last_planned: datetime | None = None
    shot_times: list[datetime] = []
    for row in rows:
        payload = row.get("payload_json")
        if not isinstance(payload, Mapping):
            continue
        if int(payload.get("phase_id") or 0) != int(phase_id):
            continue
        kind = str(payload.get("kind") or "").strip()
        if kind not in {"planned", "extra"}:
            continue
        at = _as_utc(row.get("created_at"))
        if at is None:
            continue
        duration_sec = int(payload.get("duration_sec") or 0)
        shot_times.append(at)
        if last_shot is None:
            last_shot = ShotMark(
                at=at,
                kind=kind,
                phase_id=phase_id,
                duration_sec=duration_sec,
            )
        if kind == "planned" and last_planned is None:
            last_planned = at

    extra_used = False
    if last_shot is not None and last_shot.kind == "extra":
        extra_used = True
    successful = count_successful_shots_in_active_span(
        shot_times=shot_times,
        phase=phase,
        now=now,
        timezone_name=timezone_name,
    )
    return last_shot, last_planned, extra_used, successful


async def record_successful_shot(
    *,
    zone_id: int,
    grow_cycle_id: int,
    phase_id: int,
    kind: str,
    duration_sec: int,
    reason_code: str,
) -> None:
    await create_zone_event(
        zone_id,
        _SHOT_EVENT_TYPE,
        {
            "grow_cycle_id": grow_cycle_id,
            "phase_id": phase_id,
            "kind": kind,
            "duration_sec": duration_sec,
            "reason_code": reason_code,
            "planned": kind == "planned",
            "extra": kind == "extra",
        },
    )


def _parse_cursor_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _as_utc(parsed)


async def load_light_integral_cursor(
    *,
    zone_id: int,
    phase_id: int,
    phase_started_at: datetime,
    unit: str | None,
) -> LightIntegralCursor:
    """Курсор фазы. Чужая фаза или пустая запись — старт с started_at, сумма 0."""
    rows = await fetch(
        """
        SELECT payload_json
        FROM zone_events
        WHERE zone_id = $1
          AND type = $2
        ORDER BY id DESC
        LIMIT 1
        """,
        zone_id,
        _CURSOR_EVENT_TYPE,
    )
    fresh = LightIntegralCursor(
        accumulated=0.0,
        last_accounted_ts=phase_started_at,
        unit=unit,
        status="ok",
        last_value=None,
    )
    if not rows:
        return fresh
    payload = rows[0].get("payload_json")
    if not isinstance(payload, Mapping):
        return fresh
    if int(payload.get("phase_id") or 0) != int(phase_id):
        return fresh
    status = str(payload.get("status") or "ok").strip()
    if status not in {"ok", "unseen"}:
        status = "unseen"
    accumulated = payload.get("accumulated")
    try:
        accumulated_f = float(accumulated) if accumulated is not None else 0.0
    except (TypeError, ValueError):
        accumulated_f = 0.0
    last_value = payload.get("last_value")
    try:
        last_value_f = float(last_value) if last_value is not None else None
    except (TypeError, ValueError):
        last_value_f = None
    accounted = _parse_cursor_ts(payload.get("last_accounted_ts")) or phase_started_at
    raw_unit = payload.get("unit")
    cursor_unit = raw_unit if isinstance(raw_unit, str) and raw_unit.strip() else unit
    return LightIntegralCursor(
        accumulated=accumulated_f,
        last_accounted_ts=accounted,
        unit=cursor_unit,
        status=status,
        last_value=last_value_f,
    )


async def save_light_integral_cursor(
    *,
    zone_id: int,
    phase_id: int,
    cursor: LightIntegralCursor,
) -> None:
    """Одна строка на зону и фазу: тик обновляет курсор, а не пишет событие каждый раз."""
    accounted = cursor.last_accounted_ts
    payload = {
        "phase_id": int(phase_id),
        "accumulated": float(cursor.accumulated),
        "last_accounted_ts": accounted.isoformat() if isinstance(accounted, datetime) else None,
        "unit": cursor.unit,
        "status": cursor.status,
        "last_value": cursor.last_value,
    }
    rows = await fetch(
        """
        SELECT id
        FROM zone_events
        WHERE zone_id = $1
          AND type = $2
          AND (payload_json->>'phase_id') = $3
        ORDER BY id DESC
        LIMIT 1
        """,
        zone_id,
        _CURSOR_EVENT_TYPE,
        str(int(phase_id)),
    )
    if rows:
        await execute(
            """
            UPDATE zone_events
            SET payload_json = $2
            WHERE id = $1
            """,
            int(rows[0]["id"]),
            payload,
        )
        return
    await execute(
        """
        INSERT INTO zone_events (zone_id, type, payload_json, created_at)
        VALUES ($1, $2, $3, NOW())
        """,
        zone_id,
        _CURSOR_EVENT_TYPE,
        payload,
    )


__all__ = [
    "load_light_integral_cursor",
    "load_shot_marks",
    "record_successful_shot",
    "save_light_integral_cursor",
]
