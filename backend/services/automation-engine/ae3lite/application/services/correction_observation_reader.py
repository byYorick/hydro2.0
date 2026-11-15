"""Read and validate post-dose observation windows without changing workflow state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.services.correction_event_logger import CorrectionEventLogger
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.metric_window_validator import decision_window_bounds_reason
from ae3lite.domain.services.telemetry_window_summary import validate_window_timing
from ae3lite.infrastructure.metrics import CORRECTION_OBSERVE_OUT_OF_BOUNDS


@dataclass(frozen=True)
class ObservationWindow:
    """Immutable result of ``_read_observation_window_or_interrupt``.

    Packs the ready telemetry window samples plus all the context needed
    by the finalize step (baseline, dose timing, observation config, and
    the previous PID entry). Avoids an eight-item tuple return and lets
    the finalize helper take a single argument.
    """

    samples: Any
    summary_value: float
    baseline_value: float
    last_dose_at: datetime
    observe_cfg: Mapping[str, Any]
    pid_entry: Mapping[str, Any]
    process_cfg: Mapping[str, Any]


@dataclass(frozen=True)
class ObservationRetry:
    """The handler must route this delay through its stage deadline guard."""

    due_delay_sec: float


class CorrectionObservationReader:
    """Owns telemetry validation and diagnostics, with no PID or command writes."""

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        summarize_window_fn: Callable[..., Mapping[str, Any]],
        log_event_fn: Callable[..., Awaitable[None]],
        logger: Any,
    ) -> None:
        self._runtime_monitor = runtime_monitor
        self._summarize_window = summarize_window_fn
        self._log_event = log_event_fn
        self._logger = logger

    async def read(
        self,
        *,
        task: Any,
        corr: Any,
        now: datetime,
        pid_type: str,
        sensor_type: str,
        telemetry_max_age_sec: int,
        pid_entry: Mapping[str, Any],
        observe_cfg: Mapping[str, Any],
        process_cfg: Mapping[str, Any],
        stale_retry_delay_fn: Callable[[], float],
    ) -> ObservationWindow | ObservationRetry:
        last_dose_at = pid_entry.get("last_dose_at")
        baseline_value = pid_entry.get("last_measured_value")
        if not isinstance(last_dose_at, datetime) or baseline_value is None:
            raise TaskExecutionError(
                "corr_observation_baseline_missing",
                f"Для окна наблюдения {pid_type} отсутствует baseline",
            )

        observation_started_at = last_dose_at + timedelta(
            seconds=int(observe_cfg["transport_delay_sec"]),
        )
        window = await self._runtime_monitor.read_metric_window(
            zone_id=task.zone_id,
            sensor_type=sensor_type,
            since_ts=observation_started_at,
            telemetry_max_age_sec=int(telemetry_max_age_sec),
        )
        if not window["has_sensor"] or window["is_stale"]:
            retry_delay_sec = stale_retry_delay_fn()
            await self._log_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_FRESHNESS",
                task=task,
                corr=corr,
                payload={
                    "pid_type": pid_type,
                    "sensor_type": sensor_type,
                    "sensor_scope": "observe_window",
                    "reason": f"Телеметрия {sensor_type} устарела или недоступна во время окна наблюдения",
                    "retry_after_sec": retry_delay_sec,
                    "telemetry_max_age_sec": int(telemetry_max_age_sec),
                },
            )
            self._logger.warning(
                "zone %s: телеметрия %s устарела или недоступна во время observation window; "
                "повтор через %.1f с (task_id=%s correction_window_id=%s)",
                task.zone_id,
                sensor_type,
                retry_delay_sec,
                getattr(task, "id", None),
                CorrectionEventLogger.correction_window_id(task=task),
            )
            return ObservationRetry(due_delay_sec=retry_delay_sec)

        summary = self._summarize_window(
            samples=window["samples"],
            window_min_samples=int(observe_cfg["window_min_samples"]),
            stability_max_slope=float(observe_cfg["stability_max_slope"]),
        )
        if not summary["ready"]:
            reason = str(summary.get("reason") or "").strip().lower()
            # insufficient_samples во время observe_poll — штатное накопление окна
            # (poll 2с, min_samples 3 → несколько тиков). Не пишем zone_event на каждый
            # тик: иначе UI/логи засыпает CORRECTION_SKIPPED_WINDOW_NOT_READY.
            if reason != "insufficient_samples":
                await self._log_event(
                    zone_id=task.zone_id,
                    event_type="CORRECTION_SKIPPED_WINDOW_NOT_READY",
                    task=task,
                    corr=corr,
                    payload={
                        "pid_type": pid_type,
                        "sensor_type": sensor_type,
                        "sensor_scope": "observe_window",
                        "reason": summary.get("reason"),
                        "sample_count": len(window["samples"])
                        if isinstance(window.get("samples"), (list, tuple))
                        else None,
                        "slope": summary.get("slope"),
                        "retry_after_sec": int(observe_cfg["observe_poll_sec"]),
                        "window_min_samples": int(observe_cfg["window_min_samples"]),
                        "stability_max_slope": float(observe_cfg["stability_max_slope"]),
                    },
                )
            else:
                self._logger.debug(
                    "zone %s: observe window accumulating samples sensor=%s count=%s min=%s (task_id=%s)",
                    task.zone_id,
                    sensor_type,
                    len(window["samples"]) if isinstance(window.get("samples"), (list, tuple)) else None,
                    int(observe_cfg["window_min_samples"]),
                    getattr(task, "id", None),
                )
            return ObservationRetry(due_delay_sec=int(observe_cfg["observe_poll_sec"]))

        bounds_reason = decision_window_bounds_reason(
            sensor_type=sensor_type,
            value=summary["value"],
        )
        if bounds_reason is not None:
            self._logger.warning(
                "zone %s: observe window value out of sanity bounds sensor_type=%s value=%s "
                "(task_id=%s correction_window_id=%s)",
                task.zone_id,
                sensor_type,
                summary["value"],
                getattr(task, "id", None),
                CorrectionEventLogger.correction_window_id(task=task),
            )
            CORRECTION_OBSERVE_OUT_OF_BOUNDS.inc()
            await self._log_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_WINDOW_NOT_READY",
                task=task,
                corr=corr,
                payload={
                    "pid_type": pid_type,
                    "sensor_type": sensor_type,
                    "sensor_scope": "observe_window",
                    "reason": bounds_reason,
                    "observed_value": summary["value"],
                    "retry_after_sec": int(observe_cfg["observe_poll_sec"]),
                    "window_min_samples": int(observe_cfg["window_min_samples"]),
                    "stability_max_slope": float(observe_cfg["stability_max_slope"]),
                },
            )
            return ObservationRetry(due_delay_sec=int(observe_cfg["observe_poll_sec"]))

        timing = validate_window_timing(
            samples=window["samples"],
            minimum_span_sec=float(observe_cfg["decision_window_sec"]),
            not_after=now,
            sample_period_sec=float(observe_cfg["telemetry_period_sec"]),
        )
        if not timing["ready"]:
            reason = str(timing.get("reason") or "invalid_window_timing")
            # A short window is the normal accumulation path after hold.  A
            # future-dated/invalid timestamp is exceptional and remains
            # visible as a zone event.
            if reason != "insufficient_window_span":
                await self._log_event(
                    zone_id=task.zone_id,
                    event_type="CORRECTION_SKIPPED_WINDOW_NOT_READY",
                    task=task,
                    corr=corr,
                    payload={
                        "pid_type": pid_type,
                        "sensor_type": sensor_type,
                        "sensor_scope": "observe_window",
                        "reason": reason,
                        "retry_after_sec": int(observe_cfg["observe_poll_sec"]),
                        "decision_window_sec": int(observe_cfg["decision_window_sec"]),
                        "window_span_sec": timing.get("window_span_sec"),
                    },
                )
            else:
                self._logger.debug(
                    "zone %s: observe window span %.3fs is shorter than required %ss sensor=%s task_id=%s",
                    task.zone_id,
                    float(timing.get("window_span_sec") or 0.0),
                    int(observe_cfg["decision_window_sec"]),
                    sensor_type,
                    getattr(task, "id", None),
                )
            return ObservationRetry(due_delay_sec=int(observe_cfg["observe_poll_sec"]))

        return ObservationWindow(
            samples=window["samples"],
            summary_value=float(summary["value"]),
            baseline_value=float(baseline_value),
            last_dose_at=last_dose_at,
            observe_cfg=observe_cfg,
            pid_entry=pid_entry,
            process_cfg=process_cfg,
        )
