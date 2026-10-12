"""Shared pure telemetry-window summarization for AE3-Lite handlers.

Extracted as part of the God-Object decomposition (audit finding C2):
the same median/slope-stability gate was duplicated in three places
(``BaseStageHandler._summarize_metric_window``,
``BaseStageHandler._decision_window_since_ts``, and
``DecisionWindowReader._summarize``). Consolidating them here:

* removes DRY violation (single point of truth)
* makes the gate unit-testable in isolation
* lets ``DecisionWindowReader`` drop its private copy so the two paths
  cannot silently drift

Pure module-level functions, no class wrapper — the logic is stateless and
Python-idiomatic as plain utilities.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any, Mapping


# Handler ``now`` is captured before the SQL read, so a sample committed while
# the query is running can legitimately be a fraction of a second newer.  Two
# seconds cover that race without accepting a device clock that is materially
# ahead of the automation runtime.
MAX_WINDOW_FUTURE_SKEW_SEC = 2.0


def summarize_window(
    *,
    samples: Any,
    window_min_samples: int,
    stability_max_slope: float,
) -> dict[str, Any]:
    """Median-and-slope gate for a telemetry window.

    Returns a dict with ``ready: True`` + ``value / sample_count / slope``
    when the window has enough samples and the drift slope is below
    ``stability_max_slope``. Otherwise ``ready: False`` with a ``reason``
    string and (for unstable) the computed slope.

    Reasons:
        insufficient_samples — fewer sample rows than window_min_samples
        insufficient_values  — rows present but lacking "value" field
        unstable             — |slope| > stability_max_slope

    The function does not raise; callers decide what to do with a not-ready
    result (retry, log, fail).
    """
    sample_list = list(samples) if isinstance(samples, (list, tuple)) else []
    if len(sample_list) < window_min_samples:
        return {"ready": False, "reason": "insufficient_samples"}
    values = [
        float(item["value"]) for item in sample_list if item.get("value") is not None
    ]
    if len(values) < window_min_samples:
        return {"ready": False, "reason": "insufficient_values"}
    first_ts = sample_list[0].get("ts")
    last_ts = sample_list[-1].get("ts")
    slope = 0.0
    if (
        isinstance(first_ts, datetime)
        and isinstance(last_ts, datetime)
        and last_ts > first_ts
    ):
        dt = max(1.0, (last_ts - first_ts).total_seconds())
        slope = (
            float(sample_list[-1]["value"]) - float(sample_list[0]["value"])
        ) / dt
    if abs(slope) > stability_max_slope:
        return {"ready": False, "reason": "unstable", "slope": slope}
    return {
        "ready": True,
        "value": float(median(values)),
        "sample_count": len(values),
        "slope": slope,
    }


def validate_window_timing(
    *,
    samples: Any,
    minimum_span_sec: float,
    not_after: datetime,
    sample_period_sec: float = 0.0,
    max_future_skew_sec: float = MAX_WINDOW_FUTURE_SKEW_SEC,
) -> dict[str, Any]:
    """Validate wall-clock coverage of a telemetry decision window.

    Sample count alone is insufficient: a reconnect/buffer flush may deliver
    several values with identical or tightly clustered timestamps.  Such a
    batch must not satisfy an 8-second decision window and trigger a chemical
    dose.  The check also rejects samples materially ahead of handler time;
    otherwise future device timestamps look permanently fresh and can stretch
    the apparent window.
    """
    sample_list = list(samples) if isinstance(samples, (list, tuple)) else []
    timestamps = [
        _to_utc_naive(item.get("ts"))
        for item in sample_list
        if item.get("value") is not None and isinstance(item.get("ts"), datetime)
    ]
    if len(timestamps) < 2:
        return {
            "ready": False,
            "reason": "invalid_timestamps",
            "window_span_sec": None,
        }

    earliest = min(timestamps)
    latest = max(timestamps)
    normalized_end = _to_utc_naive(not_after)
    future_by_sec = (latest - normalized_end).total_seconds()
    if future_by_sec > max(0.0, float(max_future_skew_sec)):
        return {
            "ready": False,
            "reason": "sample_in_future",
            "window_span_sec": max(0.0, (latest - earliest).total_seconds()),
            "future_by_sec": future_by_sec,
        }

    sample_span_sec = max(0.0, (latest - earliest).total_seconds())
    # N periodic samples represent N acquisition intervals even though the
    # distance between the first and last timestamps is only (N-1) periods.
    coverage_sec = sample_span_sec + max(0.0, float(sample_period_sec))
    if coverage_sec + 1e-9 < max(0.0, float(minimum_span_sec)):
        return {
            "ready": False,
            "reason": "insufficient_window_span",
            "window_span_sec": coverage_sec,
            "sample_span_sec": sample_span_sec,
        }
    return {
        "ready": True,
        "window_span_sec": coverage_sec,
        "sample_span_sec": sample_span_sec,
    }


def decision_window_since_ts(
    *, now: datetime, config: Mapping[str, Any],
) -> datetime:
    """Compute the ``since_ts`` lookback for a decision window read.

    Adds one ``telemetry_period_sec`` of slack on top of ``decision_window_sec``
    so a late-but-still-fresh sample does not collapse a 3-sample window into
    2 samples on real hardware. Mirrors the legacy inline formula.
    """
    lookback_sec = int(config["decision_window_sec"]) + int(
        config.get("telemetry_period_sec", 0) or 0
    )
    return now - timedelta(seconds=max(1, lookback_sec))


def _to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
