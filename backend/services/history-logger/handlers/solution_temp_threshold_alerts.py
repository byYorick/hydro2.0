"""Пороговые бизнес-алерты температуры раствора (solution_temp_c)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from common.alert_publisher import AlertPublisher
from common.alerts import AlertCode, AlertSource
from common.db import fetch

from metrics import SOLUTION_TEMP_BREACH_ACTIVE

logger = logging.getLogger(__name__)

_SOLUTION_TEMP_CHANNELS = frozenset({"solution_temp_c", "temp_solution", "solution_temp"})
_DEFAULT_DELAY_MINUTES = max(1, int(os.getenv("SOLUTION_TEMP_ALERT_DELAY_MINUTES", "10")))
_publisher = AlertPublisher()
_breach_started_at: dict[int, dict[str, datetime]] = {}


@dataclass(frozen=True)
class SolutionTempThresholds:
    target: float | None
    min_c: float
    max_c: float


def is_solution_temp_channel(channel: str | None) -> bool:
    if not channel:
        return False

    return channel.strip().lower() in _SOLUTION_TEMP_CHANNELS


def _alert_delay_seconds() -> int:
    return _DEFAULT_DELAY_MINUTES * 60


def _normalize_ts(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_thresholds(row: Mapping[str, Any]) -> SolutionTempThresholds | None:
    target = row.get("solution_temp_target")
    min_raw = row.get("solution_temp_min")
    max_raw = row.get("solution_temp_max")

    if target is None and min_raw is None and max_raw is None:
        return None

    target_f = float(target) if target is not None else None
    min_c = float(min_raw) if min_raw is not None else target_f
    max_c = float(max_raw) if max_raw is not None else target_f

    if min_c is None or max_c is None:
        return None

    return SolutionTempThresholds(target=target_f, min_c=min_c, max_c=max_c)


async def _load_thresholds_for_zones(zone_ids: list[int]) -> dict[int, SolutionTempThresholds]:
    if not zone_ids:
        return {}

    rows = await fetch(
        """
        SELECT
            z.id AS zone_id,
            gcp.solution_temp_target,
            gcp.solution_temp_min,
            gcp.solution_temp_max
        FROM zones z
        JOIN grow_cycles gc
          ON gc.zone_id = z.id
         AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
        JOIN grow_cycle_phases gcp
          ON gcp.id = gc.current_phase_id
        WHERE z.id = ANY($1::bigint[])
        """,
        zone_ids,
    )

    thresholds: dict[int, SolutionTempThresholds] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        zone_id = row.get("zone_id")
        if zone_id is None:
            continue
        resolved = _resolve_thresholds(row)
        if resolved is not None:
            thresholds[int(zone_id)] = resolved

    return thresholds


def _set_breach_gauge(*, zone_id: int, direction: str, active: bool) -> None:
    try:
        SOLUTION_TEMP_BREACH_ACTIVE.labels(zone_id=str(zone_id), direction=direction).set(1 if active else 0)
    except Exception:
        logger.debug("solution_temp breach gauge update failed zone_id=%s", zone_id, exc_info=True)


async def _raise_alert(
    *,
    zone_id: int,
    code: str,
    alert_type: str,
    direction: str,
    value: float,
    thresholds: SolutionTempThresholds,
    sample_ts: datetime,
) -> None:
    dedupe_key = _publisher.build_dedupe_key(
        code=code,
        zone_id=zone_id,
        parts=(AlertSource.BIZ.value, f"solution_temp:{direction}"),
    )
    await _publisher.raise_active(
        zone_id=zone_id,
        source=AlertSource.BIZ.value,
        code=code,
        alert_type=alert_type,
        details={
            "metric": "solution_temp_c",
            "direction": direction,
            "value_c": value,
            "target_c": thresholds.target,
            "min_c": thresholds.min_c,
            "max_c": thresholds.max_c,
            "threshold_minutes": _DEFAULT_DELAY_MINUTES,
            "breach_started_at": sample_ts.isoformat(),
            "dedupe_key": dedupe_key,
        },
        dedupe_key=dedupe_key,
        scoped=True,
        severity="warning",
        ts_device=sample_ts.isoformat(),
    )
    _set_breach_gauge(zone_id=zone_id, direction=direction, active=True)
    logger.warning(
        "[SOLUTION_TEMP_ALERT] raised %s zone_id=%s value=%.2f min=%.2f max=%.2f",
        code,
        zone_id,
        value,
        thresholds.min_c,
        thresholds.max_c,
    )


async def _resolve_alert(*, zone_id: int, code: str, alert_type: str, direction: str) -> None:
    dedupe_key = _publisher.build_dedupe_key(
        code=code,
        zone_id=zone_id,
        parts=(AlertSource.BIZ.value, f"solution_temp:{direction}"),
    )
    await _publisher.resolve(
        zone_id=zone_id,
        source=AlertSource.BIZ.value,
        code=code,
        alert_type=alert_type,
        details={
            "metric": "solution_temp_c",
            "direction": direction,
            "resolved_reason": "back_in_band",
            "dedupe_key": dedupe_key,
        },
        dedupe_key=dedupe_key,
        scoped=True,
        severity="warning",
    )
    _set_breach_gauge(zone_id=zone_id, direction=direction, active=False)
    logger.info("[SOLUTION_TEMP_ALERT] resolved %s zone_id=%s", code, zone_id)


async def _evaluate_zone_sample(
    *,
    zone_id: int,
    value: float,
    sample_ts: datetime,
    thresholds: SolutionTempThresholds,
) -> None:
    state = _breach_started_at.setdefault(zone_id, {})
    delay_sec = _alert_delay_seconds()

    if value > thresholds.max_c:
        started = state.get("high")
        if started is None:
            state["high"] = sample_ts
        elif (sample_ts - started).total_seconds() >= delay_sec:
            await _raise_alert(
                zone_id=zone_id,
                code=AlertCode.BIZ_SOLUTION_TEMP_HIGH.value,
                alert_type="Solution Temp High",
                direction="high",
                value=value,
                thresholds=thresholds,
                sample_ts=started,
            )
    elif "high" in state:
        await _resolve_alert(
            zone_id=zone_id,
            code=AlertCode.BIZ_SOLUTION_TEMP_HIGH.value,
            alert_type="Solution Temp High",
            direction="high",
        )
        state.pop("high", None)

    if value < thresholds.min_c:
        started = state.get("low")
        if started is None:
            state["low"] = sample_ts
        elif (sample_ts - started).total_seconds() >= delay_sec:
            await _raise_alert(
                zone_id=zone_id,
                code=AlertCode.BIZ_SOLUTION_TEMP_LOW.value,
                alert_type="Solution Temp Low",
                direction="low",
                value=value,
                thresholds=thresholds,
                sample_ts=started,
            )
    elif "low" in state:
        await _resolve_alert(
            zone_id=zone_id,
            code=AlertCode.BIZ_SOLUTION_TEMP_LOW.value,
            alert_type="Solution Temp Low",
            direction="low",
        )
        state.pop("low", None)

    if not state:
        _breach_started_at.pop(zone_id, None)


async def process_solution_temp_telemetry_batch(items: list[Mapping[str, Any]]) -> None:
    """Проверяет пороги solution_temp_c после ingest телеметрии."""
    candidates: list[tuple[int, float, datetime]] = []
    for item in items:
        zone_id = item.get("zone_id")
        channel = item.get("channel")
        value = item.get("value")
        sample_ts = item.get("ts")
        if zone_id is None or value is None or sample_ts is None:
            continue
        if not is_solution_temp_channel(str(channel) if channel is not None else None):
            continue
        candidates.append((int(zone_id), float(value), _normalize_ts(sample_ts)))

    if not candidates:
        return

    zone_ids = sorted({zone_id for zone_id, _, _ in candidates})
    thresholds_by_zone = await _load_thresholds_for_zones(zone_ids)

    latest_by_zone: dict[int, tuple[float, datetime]] = {}
    for zone_id, value, sample_ts in candidates:
        existing = latest_by_zone.get(zone_id)
        if existing is None or sample_ts >= existing[1]:
            latest_by_zone[zone_id] = (value, sample_ts)

    for zone_id, (value, sample_ts) in latest_by_zone.items():
        thresholds = thresholds_by_zone.get(zone_id)
        if thresholds is None:
            continue
        try:
            await _evaluate_zone_sample(
                zone_id=zone_id,
                value=value,
                sample_ts=sample_ts,
                thresholds=thresholds,
            )
        except Exception:
            logger.error(
                "[SOLUTION_TEMP_ALERT] evaluation failed zone_id=%s value=%.2f",
                zone_id,
                value,
                exc_info=True,
            )


def reset_solution_temp_alert_state_for_tests() -> None:
    """Сбрасывает in-memory state (только для unit-тестов)."""
    _breach_started_at.clear()
