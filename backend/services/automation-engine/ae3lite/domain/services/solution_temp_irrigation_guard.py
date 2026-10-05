"""Пропуск нового полива по температуре раствора.

Один образец и один ``telemetry_last`` hold не доказывают: ряд
``telemetry_samples`` должен покрыть всё окно, без дыры больше порога
свежести. Отдельного stale для ``solution_temp_c`` в AE нет — 600 с.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

REASON_SOLUTION_TEMP_UNAVAILABLE = "solution_temp_unavailable"
REASON_SOLUTION_TEMP_OUT_OF_BAND = "solution_temp_out_of_band"

# Канал history-logger: solution_temp_c и уже принятые алиасы.
SOLUTION_TEMP_CHANNEL_LABELS: tuple[str, ...] = (
    "solution_temp_c",
    "temp_solution",
    "solution_temp",
)

# Нет готового порога свежести этого канала. telemetry_max_age_sec — pH/EC.
DEFAULT_SOLUTION_TEMP_STALE_SEC = 600


@dataclass(frozen=True)
class SolutionTempSkip:
    reason_code: str
    details: dict[str, Any]


def solution_temp_gate_active(
    *,
    required: bool,
    min_c: float | None,
    max_c: float | None,
) -> bool:
    return bool(required) and min_c is not None and max_c is not None


def evaluate_solution_temp_hold(
    *,
    min_c: float,
    max_c: float,
    hold_sec: int,
    stale_sec: int,
    now: datetime,
    reading: Mapping[str, Any] | None,
) -> SolutionTempSkip | None:
    """``None`` — не блокировать. Иначе успешный skip, не fail."""
    now_naive = _as_naive_utc(now)
    hold = max(0, int(hold_sec))
    stale = max(0, int(stale_sec))
    window_start = now_naive - timedelta(seconds=hold)
    last_point = _parse_point(_mapping_or_none(None if reading is None else reading.get("telemetry_last")))
    samples = _parse_samples(None if reading is None else reading.get("samples"))
    window_samples = [
        point for point in samples if window_start <= point[0] <= now_naive
    ]

    if not _has_fresh_point(
        last_point=last_point,
        samples=window_samples,
        now=now_naive,
        stale_sec=stale,
    ):
        return SolutionTempSkip(
            reason_code=REASON_SOLUTION_TEMP_UNAVAILABLE,
            details=_details(
                min_c=min_c,
                max_c=max_c,
                hold_sec=hold,
                stale_sec=stale,
                samples=len(window_samples),
                latest_c=None,
            ),
        )

    latest_c = _latest_value(last_point=last_point, samples=window_samples)
    if _in_band(latest_c, min_c=min_c, max_c=max_c):
        return None
    if any(_in_band(value, min_c=min_c, max_c=max_c) for _, value in window_samples):
        return None
    if not _window_covered(
        window_samples,
        window_start=window_start,
        now=now_naive,
        stale_sec=stale,
    ):
        return None

    return SolutionTempSkip(
        reason_code=REASON_SOLUTION_TEMP_OUT_OF_BAND,
        details=_details(
            min_c=min_c,
            max_c=max_c,
            hold_sec=hold,
            stale_sec=stale,
            samples=len(window_samples),
            latest_c=latest_c,
        ),
    )


def _details(
    *,
    min_c: float,
    max_c: float,
    hold_sec: int,
    stale_sec: int,
    samples: int,
    latest_c: float | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "min_c": float(min_c),
        "max_c": float(max_c),
        "hold_sec": int(hold_sec),
        "stale_sec": int(stale_sec),
        "samples": int(samples),
    }
    if latest_c is not None:
        payload["latest_c"] = float(latest_c)
    return payload


def _window_covered(
    samples: Sequence[tuple[datetime, float]],
    *,
    window_start: datetime,
    now: datetime,
    stale_sec: int,
) -> bool:
    # Одна метка времени не закрывает hold, даже если stale >= длине окна.
    if len(samples) < 2:
        return False
    first_ts = samples[0][0]
    last_ts = samples[-1][0]
    if last_ts <= first_ts:
        return False
    stale = float(stale_sec)
    if (first_ts - window_start).total_seconds() > stale:
        return False
    if (now - last_ts).total_seconds() > stale:
        return False
    for (prev_ts, _), (next_ts, _) in zip(samples, samples[1:]):
        if (next_ts - prev_ts).total_seconds() > stale:
            return False
    return True


def _has_fresh_point(
    *,
    last_point: tuple[datetime, float] | None,
    samples: Sequence[tuple[datetime, float]],
    now: datetime,
    stale_sec: int,
) -> bool:
    latest_ts: datetime | None = None
    if last_point is not None:
        latest_ts = last_point[0]
    for ts, _value in samples:
        if latest_ts is None or ts > latest_ts:
            latest_ts = ts
    if latest_ts is None:
        return False
    return (now - latest_ts).total_seconds() <= float(stale_sec)


def _latest_value(
    *,
    last_point: tuple[datetime, float] | None,
    samples: Sequence[tuple[datetime, float]],
) -> float | None:
    chosen_ts: datetime | None = None
    chosen_value: float | None = None
    if last_point is not None:
        chosen_ts, chosen_value = last_point
    for ts, value in samples:
        if chosen_ts is None or ts >= chosen_ts:
            chosen_ts = ts
            chosen_value = value
    return chosen_value


def _in_band(value: float | None, *, min_c: float, max_c: float) -> bool:
    if value is None:
        return False
    return float(min_c) <= float(value) <= float(max_c)


def _parse_samples(raw_samples: Any) -> list[tuple[datetime, float]]:
    if not isinstance(raw_samples, Sequence) or isinstance(raw_samples, (str, bytes)):
        return []
    points: list[tuple[datetime, float]] = []
    for item in raw_samples:
        parsed = _parse_point(item if isinstance(item, Mapping) else None)
        if parsed is not None:
            points.append(parsed)
    points.sort(key=lambda point: point[0])
    return points


def _parse_point(raw_point: Mapping[str, Any] | None) -> tuple[datetime, float] | None:
    if raw_point is None:
        return None
    ts = _as_naive_utc(raw_point.get("ts"))
    if ts is None:
        return None
    try:
        value = float(raw_point.get("value"))
    except (TypeError, ValueError):
        return None
    return ts, value


def _mapping_or_none(raw_value: Any) -> Mapping[str, Any] | None:
    return raw_value if isinstance(raw_value, Mapping) else None


def _as_naive_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
