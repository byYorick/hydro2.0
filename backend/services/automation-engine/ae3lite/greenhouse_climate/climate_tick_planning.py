"""climate tick planning: explicit dependencies and invocation data."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from ae3lite.greenhouse_climate.climate_tick_records import ClimateTickPlan
from ae3lite.greenhouse_climate.decision_engine import ClimateDecision
from ae3lite.infrastructure.clients import HistoryLoggerClient


@dataclass(frozen=True)
class ClimateTickPlanningPorts:
    greenhouse_climate_rain_clamp_total: Callable[..., Any]
    greenhouse_climate_sensor_stale_total: Callable[..., Any]
    greenhouse_climate_wind_clamp_total: Callable[..., Any]
    load_greenhouse_timezone: Callable[..., Any]
    load_manual_override: Callable[..., Any]
    load_vents: Callable[..., Any]
    resolve_target_policy: Callable[..., Any]
    schedule_day_for_greenhouse: Callable[..., Any]
    sensor_snapshot: Callable[..., Any]
    spread_alerts: Callable[..., Any]
    unique_alert_codes: Callable[..., Any]
    compute_climate_decision: Callable[..., Any]
    record_greenhouse_climate_crop_metrics: Callable[..., Any]


class ClimateTickPlanning:
    def __init__(self, ports: ClimateTickPlanningPorts) -> None:
        self._ports = ports

    async def plan_active_tick(
        self, *, greenhouse_id: int, execution: Mapping[str, Any], state: Mapping[str, Any], control_mode: str
    ) -> ClimateTickPlan:
        execution, policy_alerts = await self._ports.resolve_target_policy(greenhouse_id, execution)
        freshness = int(float(execution.get("sensor_freshness_sec") or 1200))
        snap = await self._ports.sensor_snapshot(greenhouse_id, freshness)
        vents = await self._ports.load_vents(greenhouse_id)
        override = await self._ports.load_manual_override(greenhouse_id)
        active_override_id = int(override.get("id")) if isinstance(override, dict) and override.get("id") else None

        now_ts = time.time()
        last_cmd_at = state.get("last_command_at")
        last_cmd_ts = None
        if isinstance(last_cmd_at, datetime):
            last = last_cmd_at if last_cmd_at.tzinfo else last_cmd_at.replace(tzinfo=timezone.utc)
            last_cmd_ts = last.timestamp()

        greenhouse_tz = await self._ports.load_greenhouse_timezone(greenhouse_id)
        schedule_day = self._ports.schedule_day_for_greenhouse(greenhouse_tz=greenhouse_tz, execution=execution)

        decision = self._ports.compute_climate_decision(
            execution=execution,
            control_mode=control_mode,
            manual_override=override,
            inside_temp_median=snap["inside_temp_median"],
            inside_temp_max=snap["inside_temp_max"],
            inside_rh_max=snap["inside_rh_max"],
            outside_temp=snap["outside_temp"],
            outside_humidity=snap["outside_humidity"],
            wind_speed=snap["wind_speed"],
            wind_direction_deg=snap["wind_direction_deg"],
            rain_detected=bool(snap["rain_detected"]),
            outside_light_lux=snap["outside_light_lux"],
            schedule_day=schedule_day,
            weather_fresh=bool(snap["weather_fresh"]),
            outside_light_fresh=bool((snap.get("outside_fresh") or {}).get("outside_light", False)),
            inside_fresh=bool(snap["inside_fresh"]),
            current_left_pct=int(state.get("left_position_pct") or 0),
            current_right_pct=int(state.get("right_position_pct") or 0),
            now_ts=now_ts,
            last_command_ts=last_cmd_ts,
        )
        self._ports.record_greenhouse_climate_crop_metrics(
            greenhouse_id=int(greenhouse_id),
            factors=decision.factors,
        )
        active_alerts = list(policy_alerts)
        active_alerts.extend(self._ports.spread_alerts(snap, execution))
        if not bool(snap["weather_fresh"]):
            active_alerts.append("GREENHOUSE_WEATHER_STATION_STALE")
            self._ports.greenhouse_climate_sensor_stale_total().labels(kind="weather").inc()
        if not bool(snap["inside_fresh"]):
            active_alerts.append("GREENHOUSE_INSIDE_CLIMATE_STALE")
            self._ports.greenhouse_climate_sensor_stale_total().labels(kind="inside").inc()
        if decision.emergency_overheat:
            active_alerts.append("GREENHOUSE_OVERHEAT_EMERGENCY")
        if "wind_clamp" in decision.decision_reason:
            active_alerts.append("GREENHOUSE_WIND_CLAMP_ACTIVE")
            self._ports.greenhouse_climate_wind_clamp_total().inc()
        if "rain_clamp" in decision.decision_reason:
            active_alerts.append("GREENHOUSE_RAIN_CLAMP_ACTIVE")
            self._ports.greenhouse_climate_rain_clamp_total().inc()
        active_alerts = self._ports.unique_alert_codes(active_alerts)

        if decision.emergency_overheat:
            interval = int(
                float(execution.get("emergency_decision_interval_sec") or execution.get("decision_interval_sec") or 900)
            )
        else:
            interval = int(float(execution.get("decision_interval_sec") or 900))
        next_tick_active = datetime.now(timezone.utc) + timedelta(seconds=interval)
        return ClimateTickPlan(execution, snap, vents, active_override_id, decision, active_alerts, next_tick_active)
