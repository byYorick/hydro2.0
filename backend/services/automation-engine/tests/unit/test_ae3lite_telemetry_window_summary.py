"""Unit-тесты для telemetry_window_summary utility (C2 DRY fix).

Locks in the median / slope-stability gate contract so the single point of
truth cannot silently drift across handlers and services that depend on it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ae3lite.domain.services.telemetry_window_summary import (
    decision_window_since_ts,
    summarize_window,
)


def _sample(ts: datetime, value: float) -> dict:
    return {"ts": ts, "value": value}


# ── summarize_window ────────────────────────────────────────────────


def test_summarize_returns_median_for_stable_window() -> None:
    now = datetime(2026, 3, 10, 12, 0, 0)
    samples = [
        _sample(now - timedelta(seconds=20), 2.00),
        _sample(now - timedelta(seconds=10), 2.02),
        _sample(now, 2.01),
    ]
    result = summarize_window(
        samples=samples,
        window_min_samples=3,
        stability_max_slope=0.05,
    )
    assert result["ready"] is True
    assert result["value"] == pytest.approx(2.01)  # median of [2.00, 2.02, 2.01]
    assert result["sample_count"] == 3
    # Slope = (2.01 - 2.00) / 20s = 0.0005 — below stability.
    assert abs(result["slope"]) < 0.05


def test_summarize_rejects_window_below_min_samples() -> None:
    result = summarize_window(
        samples=[_sample(datetime(2026, 3, 10), 2.0)],
        window_min_samples=3,
        stability_max_slope=0.05,
    )
    assert result["ready"] is False
    assert result["reason"] == "insufficient_samples"


def test_summarize_rejects_rows_without_value_field() -> None:
    """Rows present but with missing values → insufficient_values."""
    now = datetime(2026, 3, 10, 12, 0, 0)
    samples = [
        {"ts": now - timedelta(seconds=10), "value": None},
        {"ts": now - timedelta(seconds=5), "value": None},
        {"ts": now},  # no value key at all
    ]
    result = summarize_window(
        samples=samples,
        window_min_samples=3,
        stability_max_slope=0.05,
    )
    assert result["ready"] is False
    assert result["reason"] == "insufficient_values"


def test_summarize_detects_unstable_slope() -> None:
    now = datetime(2026, 3, 10, 12, 0, 0)
    samples = [
        _sample(now - timedelta(seconds=20), 2.00),
        _sample(now - timedelta(seconds=10), 2.50),
        _sample(now, 3.00),
    ]
    result = summarize_window(
        samples=samples,
        window_min_samples=3,
        stability_max_slope=0.01,
    )
    assert result["ready"] is False
    assert result["reason"] == "unstable"
    # Slope = 1.0 / 20s = 0.05, well above 0.01.
    assert abs(result["slope"]) > 0.01


def test_summarize_handles_equal_timestamps_as_flat_slope() -> None:
    """If first_ts == last_ts, slope must remain 0 (no division by zero)."""
    now = datetime(2026, 3, 10, 12, 0, 0)
    samples = [_sample(now, 2.0), _sample(now, 2.5), _sample(now, 2.1)]
    result = summarize_window(
        samples=samples,
        window_min_samples=3,
        stability_max_slope=0.05,
    )
    assert result["ready"] is True
    assert result["slope"] == 0.0
    assert result["value"] == pytest.approx(2.1)


def test_summarize_accepts_tuple_input() -> None:
    """Tuple samples should behave identically to list input."""
    now = datetime(2026, 3, 10, 12, 0, 0)
    samples = (
        _sample(now - timedelta(seconds=10), 2.0),
        _sample(now - timedelta(seconds=5), 2.01),
        _sample(now, 2.02),
    )
    result = summarize_window(
        samples=samples,
        window_min_samples=3,
        stability_max_slope=0.05,
    )
    assert result["ready"] is True
    assert result["sample_count"] == 3


def test_summarize_rejects_non_iterable_samples() -> None:
    """Garbage input must not crash — empty window = insufficient_samples."""
    result = summarize_window(
        samples=None,  # type: ignore[arg-type]
        window_min_samples=3,
        stability_max_slope=0.05,
    )
    assert result["ready"] is False
    assert result["reason"] == "insufficient_samples"


# ── decision_window_since_ts ────────────────────────────────────────


def test_since_ts_subtracts_window_plus_telemetry_slack() -> None:
    now = datetime(2026, 3, 10, 12, 0, 0)
    result = decision_window_since_ts(
        now=now,
        config={"decision_window_sec": 30, "telemetry_period_sec": 5},
    )
    # Lookback = 30 + 5 = 35s.
    assert result == now - timedelta(seconds=35)


def test_since_ts_handles_missing_telemetry_period() -> None:
    """telemetry_period_sec absent → slack = 0."""
    now = datetime(2026, 3, 10, 12, 0, 0)
    result = decision_window_since_ts(
        now=now,
        config={"decision_window_sec": 30},
    )
    assert result == now - timedelta(seconds=30)


def test_since_ts_floors_at_one_second() -> None:
    """Even with zero window, return at least 1s lookback to avoid edge-case zero-width query."""
    now = datetime(2026, 3, 10, 12, 0, 0)
    result = decision_window_since_ts(
        now=now,
        config={"decision_window_sec": 0, "telemetry_period_sec": 0},
    )
    assert result == now - timedelta(seconds=1)
