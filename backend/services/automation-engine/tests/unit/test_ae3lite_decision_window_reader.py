"""Unit-тесты для DecisionWindowReader (extracted from CorrectionHandler, B1).

Pure application service exercised with a fake runtime_monitor — no DB,
no handler, no event logging. Covers:

* stable → ready True
* unstable slope → ready False, reason="unstable"
* too few samples → ready False, reason="insufficient_samples"
* missing sensor / stale → TaskExecutionError("corr_telemetry_stale")
* retry_delay_sec shortened by starvation-based estimate
* format_error, since_ts slack

The handler end-to-end suites (test_ae3lite_correction_handler.py) are the
regression net for the handler integration path; this file locks the reader
contract in isolation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

import pytest

from ae3lite.application.services.decision_window_reader import (
    DecisionWindowReader,
    DecisionWindowResult,
)
from ae3lite.domain.errors import TaskExecutionError


class _FakeRuntimeMonitor:
    """Minimal stand-in for RuntimeMonitor used by the reader."""

    def __init__(self, window: Mapping[str, Any]) -> None:
        self._window = window
        self.calls: list[dict[str, Any]] = []

    async def read_metric_window(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        since_ts: datetime,
        telemetry_max_age_sec: int,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "zone_id": zone_id,
                "sensor_type": sensor_type,
                "since_ts": since_ts,
                "telemetry_max_age_sec": telemetry_max_age_sec,
            }
        )
        return self._window


def _sample(ts: datetime, value: float) -> dict:
    return {"ts": ts, "value": value}


def _cfg(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "window_min_samples": 3,
        "stability_max_slope": 0.05,
        "decision_window_sec": 30,
        "telemetry_period_sec": 5,
    }
    base.update(overrides)
    return base


# ── Happy path ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_ready_true_when_window_is_stable() -> None:
    now = datetime(2026, 3, 10, 12, 0, 0)
    samples = [
        _sample(now - timedelta(seconds=30), 2.00),
        _sample(now - timedelta(seconds=20), 2.01),
        _sample(now - timedelta(seconds=10), 2.02),
    ]
    monitor = _FakeRuntimeMonitor(
        {
            "has_sensor": True,
            "is_stale": False,
            "samples": samples,
            "latest_sample_ts": samples[-1]["ts"],
        }
    )
    reader = DecisionWindowReader(runtime_monitor=monitor)

    result = await reader.read(
        zone_id=447,
        sensor_type="EC",
        telemetry_max_age_sec=60,
        config=_cfg(),
        now=now,
    )

    assert result.ready is True
    assert result.value == pytest.approx(2.01)  # median of [2.00, 2.01, 2.02]
    assert result.sample_count == 3
    # Slope = (2.02 - 2.00) / 20s = 0.001 — well below stability_max_slope=0.05.
    assert result.slope == pytest.approx(0.001, rel=1e-3)
    # Since_ts lookback = decision_window_sec (30) + telemetry_period_sec (5) = 35s slack.
    assert monitor.calls[0]["since_ts"] == now - timedelta(seconds=35)


@pytest.mark.asyncio
async def test_read_ready_false_when_slope_exceeds_stability() -> None:
    """Drifting sensor → unstable, no value returned."""
    now = datetime(2026, 3, 10, 12, 0, 0)
    samples = [
        _sample(now - timedelta(seconds=30), 2.00),
        _sample(now - timedelta(seconds=15), 2.50),
        _sample(now, 3.00),
    ]
    monitor = _FakeRuntimeMonitor(
        {
            "has_sensor": True,
            "is_stale": False,
            "samples": samples,
            "latest_sample_ts": samples[-1]["ts"],
        }
    )
    reader = DecisionWindowReader(runtime_monitor=monitor)

    result = await reader.read(
        zone_id=447,
        sensor_type="EC",
        telemetry_max_age_sec=60,
        config=_cfg(stability_max_slope=0.01),
        now=now,
    )
    assert result.ready is False
    assert result.reason == "unstable"
    assert result.slope is not None
    assert abs(result.slope) > 0.01


@pytest.mark.asyncio
async def test_read_ready_false_when_samples_below_minimum() -> None:
    now = datetime(2026, 3, 10, 12, 0, 0)
    samples = [_sample(now - timedelta(seconds=5), 2.0)]  # only 1 sample
    monitor = _FakeRuntimeMonitor(
        {
            "has_sensor": True,
            "is_stale": False,
            "samples": samples,
            "latest_sample_ts": samples[-1]["ts"],
        }
    )
    reader = DecisionWindowReader(runtime_monitor=monitor)

    result = await reader.read(
        zone_id=447,
        sensor_type="PH",
        telemetry_max_age_sec=60,
        config=_cfg(window_min_samples=3),
        now=now,
    )
    assert result.ready is False
    assert result.reason == "insufficient_samples"
    assert result.sample_count == 1
    assert result.window_min_samples == 3
    assert result.telemetry_period_sec == 5


# ── Failure modes ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_raises_when_sensor_missing() -> None:
    monitor = _FakeRuntimeMonitor(
        {"has_sensor": False, "is_stale": False, "samples": []}
    )
    reader = DecisionWindowReader(runtime_monitor=monitor)

    with pytest.raises(TaskExecutionError) as excinfo:
        await reader.read(
            zone_id=447,
            sensor_type="PH",
            telemetry_max_age_sec=60,
            config=_cfg(),
            now=datetime(2026, 3, 10, 12, 0, 0),
        )
    assert excinfo.value.code == "corr_telemetry_stale"


@pytest.mark.asyncio
async def test_read_raises_when_telemetry_is_stale() -> None:
    monitor = _FakeRuntimeMonitor(
        {"has_sensor": True, "is_stale": True, "samples": []}
    )
    reader = DecisionWindowReader(runtime_monitor=monitor)

    with pytest.raises(TaskExecutionError) as excinfo:
        await reader.read(
            zone_id=447,
            sensor_type="EC",
            telemetry_max_age_sec=60,
            config=_cfg(),
            now=datetime(2026, 3, 10, 12, 0, 0),
        )
    assert excinfo.value.code == "corr_telemetry_stale"


# ── format_error ────────────────────────────────────────────────────


def test_format_error_skips_ready_channels() -> None:
    ready_ph = DecisionWindowResult(
        ready=True, value=6.0, sample_count=3, slope=0.001
    )
    bad_ec = DecisionWindowResult(
        ready=False,
        reason="insufficient_samples",
        sample_count=1,
        window_min_samples=3,
    )
    msg = DecisionWindowReader.format_error(ph=ready_ph, ec=bad_ec)
    assert "PH=" not in msg
    assert "EC=insufficient_samples" in msg
    assert "samples=1" in msg


def test_format_error_handles_both_not_ready() -> None:
    bad_ph = DecisionWindowResult(ready=False, reason="unstable", slope=0.123)
    bad_ec = DecisionWindowResult(
        ready=False, reason="insufficient_samples", sample_count=0
    )
    msg = DecisionWindowReader.format_error(ph=bad_ph, ec=bad_ec)
    assert "PH=unstable" in msg
    assert "slope=0.1230" in msg
    assert "EC=insufficient_samples" in msg


# ── retry_delay_sec ─────────────────────────────────────────────────


def test_retry_delay_sec_defaults_to_config_when_no_starvation() -> None:
    both_unstable = DecisionWindowResult(ready=False, reason="unstable", slope=0.5)
    delay = DecisionWindowReader.retry_delay_sec(
        correction_cfg={"decision_window_retry_sec": 30.0},
        ph=both_unstable,
        ec=both_unstable,
    )
    assert delay == 30.0


def test_retry_delay_sec_shortened_by_missing_sample_estimate() -> None:
    """If EC needs 2 more samples at 5s interval, delay caps at 10s."""
    ph_ok = DecisionWindowResult(ready=True, value=6.0)
    ec_starving = DecisionWindowResult(
        ready=False,
        reason="insufficient_samples",
        sample_count=1,
        window_min_samples=3,
        telemetry_period_sec=5,
    )
    delay = DecisionWindowReader.retry_delay_sec(
        correction_cfg={"decision_window_retry_sec": 30.0},
        ph=ph_ok,
        ec=ec_starving,
    )
    # missing = 3 - 1 = 2 samples; 2 * 5s = 10s; min(30, 10) = 10s.
    assert delay == 10.0


def test_retry_delay_sec_falls_back_to_default_on_bad_config() -> None:
    bad = DecisionWindowResult(ready=False, reason="unstable")
    delay = DecisionWindowReader.retry_delay_sec(
        correction_cfg={"decision_window_retry_sec": "not-a-number"},
        ph=bad,
        ec=bad,
    )
    assert delay == 30.0  # module default


# ── DecisionWindowResult.as_payload ─────────────────────────────────


def test_as_payload_ready_result_omits_diagnostic_fields() -> None:
    result = DecisionWindowResult(ready=True, value=6.0, sample_count=3, slope=0.001)
    payload = result.as_payload()
    assert payload["ready"] is True
    assert payload["value"] == 6.0
    assert "latest_sample_ts" not in payload


def test_as_payload_not_ready_result_carries_diagnostics() -> None:
    ts = datetime(2026, 3, 10, 12, 0, 0)
    result = DecisionWindowResult(
        ready=False,
        reason="insufficient_samples",
        sample_count=1,
        window_min_samples=3,
        telemetry_period_sec=5,
        latest_sample_ts=ts,
        since_ts=ts - timedelta(seconds=30),
    )
    payload = result.as_payload()
    assert payload["ready"] is False
    assert payload["reason"] == "insufficient_samples"
    assert payload["latest_sample_ts"] == ts
