"""Пропуск нового полива по температуре раствора.

Один образец и один ``telemetry_last`` hold не доказывают: ряд
``telemetry_samples`` должен покрыть всё окно, без дыры больше порога
свежести. Отдельного stale для ``solution_temp_c`` в AE нет — 600 с.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from ae3lite.domain.services.metric_window_validator import usable_decision_quality

REASON_SOLUTION_TEMP_UNAVAILABLE = "solution_temp_unavailable"
REASON_SOLUTION_TEMP_OUT_OF_BAND = "solution_temp_out_of_band"
REASON_SOLUTION_TEMP_HOT_WARN = "solution_temp_hot_warn"
REASON_SOLUTION_TEMP_HOT_STOP = "solution_temp_hot_stop"
REASON_SOLUTION_TEMP_BLOCKED_TOO_LONG = "solution_temp_irrigation_blocked_too_long"

# Безопасные пороги горячего раствора, если фаза включила контроль и задала пару.
DEFAULT_SOLUTION_TEMP_WARN_C = 26.0
DEFAULT_SOLUTION_TEMP_STOP_C = 32.0
DEFAULT_MAX_TEMP_SKIP_PAUSE_SEC = 90 * 60

TEMPERATURE_BLOCK_REASONS = frozenset(
    {
        REASON_SOLUTION_TEMP_HOT_STOP,
        REASON_SOLUTION_TEMP_OUT_OF_BAND,
    }
)

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
    blocks_irrigation: bool = True


@dataclass(frozen=True)
class TempSkipBudget:
    pause_sec: float | None
    exceeded: bool


def solution_temp_gate_active(
    *,
    required: bool,
    min_c: float | None,
    max_c: float | None,
    warn_c: float | None = None,
    stop_c: float | None = None,
) -> bool:
    if not required:
        return False
    if warn_c is not None or stop_c is not None:
        return True
    return min_c is not None and max_c is not None


def evaluate_solution_temp_hold(
    *,
    min_c: float | None,
    max_c: float | None,
    hold_sec: int,
    stale_sec: int,
    now: datetime,
    reading: Mapping[str, Any] | None,
    warn_c: float | None = None,
    stop_c: float | None = None,
) -> SolutionTempSkip | None:
    """``None`` — не блокировать. Иначе предупреждение или успешный skip, не fail.

    Нет свежей точки — полив не пропускается.
    Выше warn (по умолчанию 26 °C) — только предупреждение.
    На stop и выше (по умолчанию 32 °C) при полном окне — skip нового полива.
    Комфортный ``max_c`` сам по себе полив не режет. Ниже ``min_c`` на всём окне — skip.
    """
    now_naive = _as_naive_utc(now)
    hold = max(0, int(hold_sec))
    stale = max(0, int(stale_sec))
    window_start = now_naive - timedelta(seconds=hold)
    last_point = _parse_point(_mapping_or_none(None if reading is None else reading.get("telemetry_last")))
    if last_point is not None and last_point[0] > now_naive + timedelta(seconds=2):
        last_point = None
    raw_samples = None if reading is None else reading.get("samples")
    samples = _parse_samples(raw_samples)
    input_count = len(raw_samples) if isinstance(raw_samples, (list, tuple)) else 0
    invalid_samples = input_count - len(samples) + int((reading or {}).get("invalid_samples") or 0)
    history_truncated = bool((reading or {}).get("history_truncated"))
    anchors = [point for point in samples if point[0] < window_start]
    window_samples = ([anchors[-1]] if anchors else []) + [
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
            blocks_irrigation=False,
        )

    latest_c = _latest_value(last_point=last_point, samples=window_samples)
    effective_warn = warn_c
    effective_stop = stop_c
    if effective_warn is None and effective_stop is None and min_c is not None and max_c is not None:
        effective_warn = DEFAULT_SOLUTION_TEMP_WARN_C
        effective_stop = DEFAULT_SOLUTION_TEMP_STOP_C
    if effective_warn is None and effective_stop is None:
        return None
    return _evaluate_hot_thresholds(
        min_c=min_c,
        max_c=max_c,
        warn_c=effective_warn,
        stop_c=effective_stop,
        hold=hold,
        stale=stale,
        now=now_naive,
        window_start=window_start,
        window_samples=window_samples,
        latest_c=latest_c,
        invalid_samples=invalid_samples,
        history_truncated=history_truncated,
    )


def _evaluate_hot_thresholds(
    *,
    min_c: float | None,
    max_c: float | None,
    warn_c: float | None,
    stop_c: float | None,
    hold: int,
    stale: int,
    now: datetime,
    window_start: datetime,
    window_samples: Sequence[tuple[datetime, float]],
    latest_c: float | None,
    invalid_samples: int = 0,
    history_truncated: bool = False,
) -> SolutionTempSkip | None:
    stop_edge = None if stop_c is None else float(stop_c)
    warn_edge = None if warn_c is None else float(warn_c)
    if warn_edge is not None and stop_edge is not None and warn_edge >= stop_edge:
        warn_edge = None
    covered = (
        not invalid_samples
        and not history_truncated
        and _window_covered(
            window_samples,
            window_start=window_start,
            now=now,
            stale_sec=stale,
        )
    )
    values = [value for _, value in window_samples]
    details = _details(
        min_c=min_c,
        max_c=max_c,
        hold_sec=hold,
        stale_sec=stale,
        samples=len(window_samples),
        latest_c=latest_c,
    )
    details.update(
        {
            "hold_covered": bool(covered),
            "invalid_samples": invalid_samples,
            "history_truncated": history_truncated,
            "observed_span_sec": (window_samples[-1][0] - window_samples[0][0]).total_seconds()
            if window_samples
            else 0,
        }
    )
    if warn_edge is not None:
        details["warn_c"] = warn_edge
    if stop_edge is not None:
        details["stop_c"] = stop_edge

    if (
        min_c is not None
        and latest_c is not None
        and latest_c < float(min_c)
        and covered
        and values
        and all(value < float(min_c) for value in values)
    ):
        return SolutionTempSkip(
            reason_code=REASON_SOLUTION_TEMP_OUT_OF_BAND,
            details=details,
            blocks_irrigation=True,
        )
    if (
        stop_edge is not None
        and latest_c is not None
        and latest_c >= stop_edge
        and covered
        and values
        and all(value >= stop_edge for value in values)
    ):
        return SolutionTempSkip(
            reason_code=REASON_SOLUTION_TEMP_HOT_STOP,
            details=details,
            blocks_irrigation=True,
        )
    if warn_edge is not None and latest_c is not None and latest_c > warn_edge:
        return SolutionTempSkip(
            reason_code=REASON_SOLUTION_TEMP_HOT_WARN,
            details=details,
            blocks_irrigation=False,
        )
    return None


def irrigation_block_pause_sec(
    rows: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
) -> float | None:
    """Секунды с последнего успешного полива или с начала температурной блокировки.

    ``None`` — истории нет, паузу ещё нельзя считать долгой.
    """
    now_naive = _as_naive_utc(now)
    if now_naive is None:
        return None
    oldest_block: datetime | None = None
    for row in rows:
        stage = str(row.get("current_stage") or "").strip()
        reason = str(row.get("irrigation_decision_reason_code") or "").strip()
        updated = _as_naive_utc(row.get("updated_at"))
        if stage == "completed_run":
            if updated is None:
                return None
            return max(0.0, (now_naive - updated).total_seconds())
        if stage == "completed_skip" and reason in TEMPERATURE_BLOCK_REASONS:
            if updated is not None:
                oldest_block = updated
            continue
        break
    if oldest_block is None:
        return None
    return max(0.0, (now_naive - oldest_block).total_seconds())


def assess_temp_skip_budget(
    *,
    pause_sec: float | None,
    max_pause_sec: int,
) -> TempSkipBudget:
    exceeded = pause_sec is not None and float(pause_sec) >= float(max_pause_sec)
    return TempSkipBudget(pause_sec=pause_sec, exceeded=exceeded)


def _details(
    *,
    min_c: float | None,
    max_c: float | None,
    hold_sec: int,
    stale_sec: int,
    samples: int,
    latest_c: float | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "min_c": None if min_c is None else float(min_c),
        "max_c": None if max_c is None else float(max_c),
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
    if last_ts <= first_ts or (last_ts - first_ts) < (now - window_start):
        return False
    stale = float(stale_sec)
    if first_ts > window_start or (window_start - first_ts).total_seconds() > stale:
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
    if raw_point is None or not usable_decision_quality(
        quality=raw_point.get("quality"), metadata=raw_point.get("metadata")
    ):
        return None
    ts = _as_naive_utc(raw_point.get("ts"))
    if ts is None:
        return None
    raw = raw_point.get("value")
    if isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return (ts, value) if math.isfinite(value) else None


def _mapping_or_none(raw_value: Any) -> Mapping[str, Any] | None:
    return raw_value if isinstance(raw_value, Mapping) else None


def _as_naive_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
