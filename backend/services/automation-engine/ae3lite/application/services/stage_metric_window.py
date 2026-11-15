"""Stage component: metric window. Explicit ports; no handler dependency."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.metric_window_validator import (
    decision_window_bounds_reason,
    sensor_value_in_bounds,
)
from ae3lite.domain.services.telemetry_window_summary import (
    decision_window_since_ts as _telemetry_decision_window_since_ts,
)
from ae3lite.domain.services.telemetry_window_summary import (
    summarize_window as _telemetry_summarize_window,
)
from ae3lite.domain.services.telemetry_window_summary import (
    validate_window_timing as _validate_telemetry_window_timing,
)

_logger = logging.getLogger("ae3lite.application.handlers.base")


@dataclass(frozen=True)
class StageMetricWindowPorts:
    runtime_monitor: Callable[[], Any]


class StageMetricWindow:
    def __init__(self, ports: StageMetricWindowPorts) -> None:
        self._ports = ports

    async def read_target_metric_window(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        telemetry_max_age_sec: int,
        config: Mapping[str, Any],
        unavailable_error: str,
        stale_error: str,
        now: datetime,
    ) -> Mapping[str, Any]:
        since_ts = self.decision_window_since_ts(now=now, config=config)
        window = await self._ports.runtime_monitor().read_metric_window(
            zone_id=zone_id,
            sensor_type=sensor_type,
            since_ts=since_ts,
            telemetry_max_age_sec=telemetry_max_age_sec,
        )
        if not window["has_sensor"]:
            raise TaskExecutionError(
                unavailable_error,
                f"Телеметрия {sensor_type} недоступна для оценки target",
            )
        if window["is_stale"]:
            raise TaskExecutionError(
                stale_error,
                f"Телеметрия {sensor_type} устарела для оценки target",
            )
        summary = self.summarize_metric_window(
            samples=window["samples"],
            window_min_samples=int(config["window_min_samples"]),
            stability_max_slope=float(config["stability_max_slope"]),
        )
        if not summary["ready"]:
            return {"ready": False, "reason": summary.get("reason")}
        bounds_reason = decision_window_bounds_reason(
            sensor_type=sensor_type,
            value=summary["value"],
        )
        if bounds_reason is not None:
            _logger.warning(
                "Sensor value out of sanity bounds: sensor_type=%s value=%s zone_id=%s",
                sensor_type,
                summary["value"],
                zone_id,
            )
            return {"ready": False, "reason": bounds_reason}
        timing = _validate_telemetry_window_timing(
            samples=window["samples"],
            minimum_span_sec=float(config["decision_window_sec"]),
            not_after=now,
            sample_period_sec=float(config["telemetry_period_sec"]),
        )
        if not timing["ready"]:
            return {
                "ready": False,
                "reason": timing.get("reason"),
                "window_span_sec": timing.get("window_span_sec"),
            }
        return {
            "ready": True,
            "value": summary["value"],
            "sample_count": summary["sample_count"],
            "slope": summary["slope"],
            "window_span_sec": timing.get("window_span_sec"),
        }

    @staticmethod
    def sensor_value_in_bounds(*, sensor_type: str, value: Any) -> bool:
        """Thin wrapper over ``metric_window_validator.sensor_value_in_bounds``."""
        return sensor_value_in_bounds(sensor_type=sensor_type, value=value)

    def decision_window_since_ts(self, *, now: datetime, config: Mapping[str, Any]) -> datetime:
        return _telemetry_decision_window_since_ts(now=now, config=config)

    def summarize_metric_window(
        self,
        *,
        samples: Any,
        window_min_samples: int,
        stability_max_slope: float,
    ) -> dict[str, Any]:
        return _telemetry_summarize_window(
            samples=samples,
            window_min_samples=window_min_samples,
            stability_max_slope=stability_max_slope,
        )
