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

from datetime import datetime, timedelta
from statistics import median
from typing import Any, Mapping


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
