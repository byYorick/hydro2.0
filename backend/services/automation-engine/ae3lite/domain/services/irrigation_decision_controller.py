"""Extensible irrigation decision-controller registry for AE3-Lite."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Mapping, Protocol, Sequence

from ae3lite.config.schema import RuntimePlan


@dataclass(frozen=True)
class IrrigationDecision:
    outcome: str
    reason_code: str
    degraded: bool = False
    details: dict[str, Any] | None = None


class IrrigationDecisionStrategy(Protocol):
    async def evaluate(
        self,
        *,
        zone_id: int,
        runtime_monitor: Any,
        runtime: RuntimePlan,
        requested_duration_sec: int | None,
        now: datetime,
    ) -> IrrigationDecision:
        ...


class TaskDecisionStrategy:
    async def evaluate(
        self,
        *,
        zone_id: int,
        runtime_monitor: Any,
        runtime: RuntimePlan,
        requested_duration_sec: int | None,
        now: datetime,
    ) -> IrrigationDecision:
        return IrrigationDecision(
            outcome="run",
            reason_code="irrigation_task_strategy_run",
            degraded=False,
            details={"requested_duration_sec": requested_duration_sec},
        )


class SmartSoilDecisionStrategy:
    @staticmethod
    def _resolve_day_profile(*, now: datetime, day_start_time: str | None, day_hours: float | None) -> tuple[bool, bool]:
        if not day_start_time or day_hours is None:
            return True, False

        raw = str(day_start_time).strip()
        if not raw:
            return True, False

        parts = raw.split(":")
        if len(parts) < 2:
            return False, True

        try:
            start_h = int(parts[0])
            start_m = int(parts[1])
        except ValueError:
            return False, True

        if start_h < 0 or start_h > 23 or start_m < 0 or start_m > 59:
            return False, True

        try:
            hours = float(day_hours)
        except (TypeError, ValueError):
            return False, True

        if hours <= 0:
            return False, False
        if hours >= 24:
            return True, False

        start_min = start_h * 60 + start_m
        end_min = (start_min + int(round(hours * 60))) % (24 * 60)
        now_min = now.hour * 60 + now.minute

        if start_min == end_min:
            return False, True
        if start_min < end_min:
            return start_min <= now_min < end_min, False
        return now_min >= start_min or now_min < end_min, False

    @staticmethod
    def _resolve_target_band(
        *,
        soil_target: Any,
        now: datetime,
    ) -> tuple[float | None, float | None, dict[str, Any]]:
        target_min = _to_float(getattr(soil_target, "min", None))
        target_max = _to_float(getattr(soil_target, "max", None))
        if target_min is not None and target_max is not None:
            return target_min, target_max, {"mode": "band"}

        day = _to_float(getattr(soil_target, "day", None))
        night = _to_float(getattr(soil_target, "night", None))
        if day is None and night is None:
            return None, None, {"mode": "missing"}

        day_start_time = str(getattr(soil_target, "day_start_time", "") or "").strip() or None
        day_hours = _to_float(getattr(soil_target, "day_hours", None))
        is_day, invalid_schedule = SmartSoilDecisionStrategy._resolve_day_profile(
            now=now,
            day_start_time=day_start_time,
            day_hours=day_hours,
        )
        active_profile = "day" if is_day else "night"
        active_target = day if active_profile == "day" else night
        if active_target is None:
            active_target = night if active_profile == "day" else day

        return (
            active_target,
            active_target,
            {
                "mode": "curve",
                "active_profile": active_profile,
                "day_start_time": day_start_time,
                "day_hours": day_hours,
                "schedule_invalid": invalid_schedule,
            },
        )

    async def evaluate(
        self,
        *,
        zone_id: int,
        runtime_monitor: Any,
        runtime: RuntimePlan,
        requested_duration_sec: int | None,
        now: datetime,
    ) -> IrrigationDecision:
        config = runtime.irrigation_decision.config
        lookback_sec = int(config.lookback_sec)
        stale_after_sec = int(config.stale_after_sec)
        min_samples = int(config.min_samples)
        hysteresis_pct = float(config.hysteresis_pct)
        spread_threshold_pct = float(config.spread_alert_threshold_pct)
        soil_target = runtime.soil_moisture_target
        target_min, target_max, target_meta = self._resolve_target_band(soil_target=soil_target, now=now)

        if target_min is None or target_max is None:
            return IrrigationDecision(
                outcome="degraded_run",
                reason_code="smart_soil_target_missing",
                degraded=True,
            )

        sensor_data = await runtime_monitor.read_metric_windows(
            zone_id=zone_id,
            sensor_type="SOIL_MOISTURE",
            since_ts=now - timedelta(seconds=max(1, lookback_sec)),
            telemetry_max_age_sec=stale_after_sec,
        )
        sensor_windows = sensor_data.get("sensor_windows") if isinstance(sensor_data.get("sensor_windows"), Sequence) else ()
        per_sensor_values: list[float] = []
        total_samples = 0
        stale = bool(sensor_data.get("is_stale"))
        for sensor in sensor_windows:
            if not isinstance(sensor, Mapping):
                continue
            stale = stale or bool(sensor.get("is_stale"))
            samples = sensor.get("samples") if isinstance(sensor.get("samples"), Sequence) else ()
            values = [_to_float(sample.get("value")) for sample in samples if isinstance(sample, Mapping)]
            values = [value for value in values if value is not None]
            total_samples += len(values)
            if values:
                per_sensor_values.append(float(mean(values)))

        if not per_sensor_values or stale:
            return IrrigationDecision(
                outcome="degraded_run",
                reason_code="smart_soil_telemetry_missing_or_stale",
                degraded=True,
                details={"samples": total_samples, "sensor_count": len(per_sensor_values)},
            )

        zone_average = float(mean(per_sensor_values))
        spread_pct = max(per_sensor_values) - min(per_sensor_values) if len(per_sensor_values) > 1 else 0.0
        degraded = bool(total_samples < min_samples or target_meta.get("schedule_invalid"))
        details = {
            "zone_average_pct": zone_average,
            "sensor_count": len(per_sensor_values),
            "samples": total_samples,
            "spread_pct": spread_pct,
            "spread_alert": spread_pct > spread_threshold_pct,
            "requested_duration_sec": requested_duration_sec,
            "target_mode": target_meta.get("mode"),
            "target_profile": target_meta.get("active_profile"),
            "min_samples_required": min_samples,
            "insufficient_samples": degraded,
            "schedule_invalid": bool(target_meta.get("schedule_invalid")),
        }

        # Even with insufficient samples we still decide run/skip, but mark degraded.
        reason_prefix = "smart_soil_degraded_" if degraded else "smart_soil_"

        if zone_average < (target_min - hysteresis_pct):
            return IrrigationDecision(
                outcome="run",
                reason_code=f"{reason_prefix}below_min",
                degraded=degraded,
                details=details,
            )

        if zone_average > (target_max + hysteresis_pct):
            return IrrigationDecision(
                outcome="skip",
                reason_code=f"{reason_prefix}above_max",
                degraded=degraded,
                details=details,
            )

        return IrrigationDecision(
            outcome="skip",
            reason_code=f"{reason_prefix}within_band",
            degraded=degraded,
            details=details,
        )


class IrrigationDecisionController:
    def __init__(self) -> None:
        self._strategies: dict[str, IrrigationDecisionStrategy] = {
            "task": TaskDecisionStrategy(),
            "smart_soil_v1": SmartSoilDecisionStrategy(),
        }

    async def evaluate(
        self,
        *,
        zone_id: int,
        runtime_monitor: Any,
        runtime: RuntimePlan,
        mode: str,
        requested_duration_sec: int | None,
        now: datetime,
    ) -> IrrigationDecision:
        if str(mode or "").strip().lower() == "force":
            return IrrigationDecision(
                outcome="run",
                reason_code="irrigation_force_mode",
                details={"requested_duration_sec": requested_duration_sec},
            )

        strategy_name = str(runtime.irrigation_decision.strategy or "task").strip().lower() or "task"
        strategy = self._strategies.get(strategy_name)
        if strategy is None:
            return IrrigationDecision(
                outcome="fail",
                reason_code="irrigation_decision_strategy_unknown",
                details={"strategy": strategy_name},
            )

        return await strategy.evaluate(
            zone_id=zone_id,
            runtime_monitor=runtime_monitor,
            runtime=runtime,
            requested_duration_sec=requested_duration_sec,
            now=now,
        )


def _to_float(raw_value: Any) -> float | None:
    try:
        return float(raw_value) if raw_value is not None else None
    except (TypeError, ValueError):
        return None
