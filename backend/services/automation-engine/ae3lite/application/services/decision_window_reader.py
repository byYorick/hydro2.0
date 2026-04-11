"""DecisionWindowReader — чтение и валидация decision window для correction cycle.

Extracted from ``CorrectionHandler`` as part of the God-Object decomposition
(audit finding B1). Owns the async read-and-validate pipeline for PH/EC
telemetry windows used by ``corr_check``:

    runtime_monitor → read_metric_window → summarize → DecisionWindowResult

This is *not* a pure domain service — it has an async dependency on
``runtime_monitor`` — so it lives under ``application/services``, not
``domain/services``. The summarize/since_ts math is delegated to the shared
``telemetry_window_summary`` utility so BaseStageHandler and DecisionWindowReader
cannot silently drift (audit finding C2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.telemetry_window_summary import (
    decision_window_since_ts,
    summarize_window,
)


_DEFAULT_DECISION_RETRY_SEC: float = 30.0


@dataclass(frozen=True)
class DecisionWindowResult:
    """Structured outcome of one decision-window read.

    When ``ready`` is True the handler trusts ``value`` as the stabilised
    median of the window and proceeds to build a dose plan. When ``ready``
    is False the remaining fields carry the diagnostic context the handler
    logs into ``CORRECTION_SKIPPED_WINDOW_NOT_READY`` events.
    """

    ready: bool
    value: Optional[float] = None
    sample_count: Optional[int] = None
    slope: Optional[float] = None
    reason: Optional[str] = None
    latest_sample_ts: Optional[datetime] = None
    since_ts: Optional[datetime] = None
    window_min_samples: Optional[int] = None
    telemetry_period_sec: Optional[int] = None

    def as_payload(self) -> dict[str, Any]:
        """Shape matching what the handler previously stuffed into event payloads."""
        if self.ready:
            return {
                "ready": True,
                "value": self.value,
                "sample_count": self.sample_count,
                "slope": self.slope,
            }
        return {
            "ready": False,
            "reason": self.reason,
            "sample_count": self.sample_count,
            "slope": self.slope,
            "latest_sample_ts": self.latest_sample_ts,
            "since_ts": self.since_ts,
            "window_min_samples": self.window_min_samples,
            "telemetry_period_sec": self.telemetry_period_sec,
        }


class DecisionWindowReader:
    """Async reader for PH/EC decision windows during correction cycles."""

    def __init__(self, *, runtime_monitor: Any) -> None:
        self._runtime_monitor = runtime_monitor

    async def read(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        telemetry_max_age_sec: int,
        config: Mapping[str, Any],
        now: datetime,
    ) -> DecisionWindowResult:
        """Read one decision window; raises on stale telemetry (parity with legacy handler).

        The raised ``TaskExecutionError("corr_telemetry_stale", ...)`` matches
        the pre-refactor behavior so the handler's existing retry-delay branch
        continues to fire unchanged.
        """
        since_ts = decision_window_since_ts(now=now, config=config)
        window = await self._runtime_monitor.read_metric_window(
            zone_id=zone_id,
            sensor_type=sensor_type,
            since_ts=since_ts,
            telemetry_max_age_sec=telemetry_max_age_sec,
        )
        if not window["has_sensor"] or window["is_stale"]:
            raise TaskExecutionError(
                "corr_telemetry_stale",
                f"{sensor_type} telemetry stale/unavailable during correction check",
            )
        window_min_samples = int(config["window_min_samples"])
        telemetry_period_sec = int(config["telemetry_period_sec"])
        summary = summarize_window(
            samples=window["samples"],
            window_min_samples=window_min_samples,
            stability_max_slope=float(config["stability_max_slope"]),
        )
        if not summary["ready"]:
            return DecisionWindowResult(
                ready=False,
                reason=str(summary.get("reason") or "unknown"),
                sample_count=int(len(window["samples"])),
                slope=summary.get("slope"),
                latest_sample_ts=window.get("latest_sample_ts"),
                since_ts=since_ts,
                window_min_samples=window_min_samples,
                telemetry_period_sec=telemetry_period_sec,
            )
        return DecisionWindowResult(
            ready=True,
            value=float(summary["value"]),
            sample_count=int(summary["sample_count"]),
            slope=float(summary["slope"]) if summary.get("slope") is not None else None,
        )

    # ── Public helpers the handler still calls ─────────────────────

    @staticmethod
    def format_error(*, ph: DecisionWindowResult, ec: DecisionWindowResult) -> str:
        """Human-readable diagnostic for ``CORRECTION_SKIPPED_WINDOW_NOT_READY``."""
        details: list[str] = []
        for sensor_type, metric in (("PH", ph), ("EC", ec)):
            if metric.ready:
                continue
            parts = [f"{sensor_type}={metric.reason or 'unknown'}"]
            if metric.sample_count is not None:
                parts.append(f"samples={metric.sample_count}")
            if metric.slope is not None:
                parts.append(f"slope={float(metric.slope):.4f}")
            details.append(",".join(parts))
        reason = "; ".join(details) if details else "decision window unavailable"
        return f"Correction decision window not ready: {reason}"

    @staticmethod
    def retry_delay_sec(
        *,
        correction_cfg: Mapping[str, Any],
        ph: DecisionWindowResult,
        ec: DecisionWindowResult,
    ) -> float:
        """Pick retry delay for the not-ready branch.

        Uses ``decision_window_retry_sec`` from config as the upper bound, but
        shortens it if we can compute when the next missing sample is due (so
        we don't block waiting 30s for a sample arriving in 4s).
        """
        retry_delay_sec = _correction_retry_delay_sec(
            correction_cfg=correction_cfg,
            key="decision_window_retry_sec",
            default=_DEFAULT_DECISION_RETRY_SEC,
        )
        starvation_delays = [
            DecisionWindowReader._missing_sample_delay_sec(metric=metric)
            for metric in (ph, ec)
        ]
        starvation_delays = [delay for delay in starvation_delays if delay is not None]
        if starvation_delays:
            return min(retry_delay_sec, max(starvation_delays))
        return retry_delay_sec

    # ── Private helpers ────────────────────────────────────────────

    @staticmethod
    def _missing_sample_delay_sec(*, metric: DecisionWindowResult) -> Optional[float]:
        if (metric.reason or "").strip().lower() != "insufficient_samples":
            return None
        if (
            metric.sample_count is None
            or metric.window_min_samples is None
        ):
            return None
        telemetry_period_sec = (
            float(metric.telemetry_period_sec)
            if metric.telemetry_period_sec
            else 1.0
        )
        missing_samples = max(1, metric.window_min_samples - metric.sample_count)
        return max(1.0, telemetry_period_sec * missing_samples)


def _correction_retry_delay_sec(
    *,
    correction_cfg: Mapping[str, Any],
    key: str,
    default: float,
) -> float:
    raw = correction_cfg.get(key)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default
