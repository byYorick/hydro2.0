"""climate tick targets: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from ae3lite.domain.services.greenhouse_clock import canonical_timezone_name, greenhouse_local


@dataclass(frozen=True)
class ClimateTickTargetsPorts:
    as_float: Callable[..., Any]
    greenhouse_targets: Callable[..., Any]
    fetch: Callable[..., Any]


class ClimateTickTargets:
    def __init__(self, ports: ClimateTickTargetsPorts) -> None:
        self._ports = ports

    async def load_greenhouse_timezone(self, greenhouse_id: int) -> str:
        rows = await self._ports.fetch(
            "SELECT timezone FROM greenhouses WHERE id = $1 LIMIT 1",
            greenhouse_id,
        )
        raw = rows[0].get("timezone") if rows else None
        return canonical_timezone_name(raw if isinstance(raw, str) else None)

    def schedule_day_for_greenhouse(
        self,
        *,
        greenhouse_tz: str,
        execution: Mapping[str, Any],
        now: datetime | None = None,
    ) -> bool:
        moment = now if now is not None else datetime.now(timezone.utc)
        now_local = greenhouse_local(moment, greenhouse_tz)

        def _parse_hhmm(value: Any, default: str) -> tuple[int, int]:
            raw = str(value or default).strip()
            try:
                hh, mm = raw.split(":", 1)
                h = max(0, min(23, int(hh)))
                m = max(0, min(59, int(mm)))
                return h, m
            except (TypeError, ValueError):
                dh, dm = default.split(":", 1)
                return int(dh), int(dm)

        schedule = execution.get("day_schedule") if isinstance(execution.get("day_schedule"), Mapping) else {}
        if schedule:
            start_h, start_m = _parse_hhmm(schedule.get("start_local"), "08:00")
            end_h, end_m = _parse_hhmm(schedule.get("end_local"), "20:00")
        else:
            start_h = max(0, min(23, int(float(execution.get("day_start_hour") or 8))))
            end_h_raw = max(0, min(24, int(float(execution.get("day_end_hour") or 20))))
            end_h = 23 if end_h_raw == 24 else end_h_raw
            start_m = 0
            end_m = 59 if end_h_raw == 24 else 0

        current_min = now_local.hour * 60 + now_local.minute
        start_min = start_h * 60 + start_m
        end_min = end_h * 60 + end_m
        if start_min == end_min:
            return True
        if start_min < end_min:
            return start_min <= current_min < end_min
        return current_min >= start_min or current_min < end_min

    def greenhouse_targets(self, execution: Mapping[str, Any]) -> dict[str, float]:
        raw = execution.get("greenhouse_targets")
        if not isinstance(raw, Mapping):
            raise ValueError("greenhouse_targets is required for greenhouse climate runtime")
        required = ("temp_min_c", "temp_max_c", "humidity_min_pct", "humidity_max_pct")
        out: dict[str, float] = {}
        for key in required:
            value = self._ports.as_float(raw.get(key))
            if value is None:
                raise ValueError(f"greenhouse_targets.{key} is required")
            out[key] = value
        if out["temp_min_c"] > out["temp_max_c"]:
            raise ValueError("greenhouse_targets temp_min_c must be <= temp_max_c")
        if out["humidity_min_pct"] > out["humidity_max_pct"]:
            raise ValueError("greenhouse_targets humidity_min_pct must be <= humidity_max_pct")
        for key in ("vpd_min_kpa", "vpd_max_kpa"):
            value = self._ports.as_float(raw.get(key))
            if value is not None:
                out[key] = value
        return out

    async def resolve_target_policy(
        self, greenhouse_id: int, execution: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        """Resolve V1 target policy into execution.greenhouse_targets.

        Phase snapshots currently store climate as single target columns. For policy
        modes, V1 treats those as the upper ventilation thresholds and keeps the
        greenhouse-level lower bounds from the fallback policy.
        """
        base_targets = self._ports.greenhouse_targets(execution)
        policy = str(execution.get("target_policy") or "greenhouse_targets").strip().lower()
        alerts: list[str] = []
        resolved = dict(execution)

        if policy == "greenhouse_targets":
            resolved["greenhouse_targets"] = base_targets
            return resolved, alerts

        if policy == "primary_zone":
            primary_zone_id = int(self._ports.as_float(execution.get("primary_zone_id")) or 0)
            rows = await self._ports.fetch(
                """
                SELECT gcp.temp_air_target, gcp.humidity_target
                FROM grow_cycles gc
                JOIN zones z ON z.id = gc.zone_id
                JOIN grow_cycle_phases gcp ON gcp.id = gc.current_phase_id
                WHERE gc.greenhouse_id = $1
                  AND gc.zone_id = $2
                  AND z.greenhouse_id = $1
                  AND gc.status IN ('RUNNING', 'ACTIVE')
                ORDER BY gc.id DESC
                LIMIT 1
                """,
                greenhouse_id,
                primary_zone_id,
            )
            if not rows:
                alerts.append("GREENHOUSE_TARGET_POLICY_INVALID")
                resolved["greenhouse_targets"] = base_targets
                return resolved, alerts
            temp_target = self._ports.as_float(rows[0].get("temp_air_target"))
            humidity_target = self._ports.as_float(rows[0].get("humidity_target"))
            if temp_target is None or humidity_target is None:
                alerts.append("GREENHOUSE_TARGET_POLICY_INVALID")
                resolved["greenhouse_targets"] = base_targets
                return resolved, alerts
            resolved["greenhouse_targets"] = {
                **base_targets,
                "temp_max_c": temp_target,
                "humidity_max_pct": humidity_target,
            }
            return resolved, alerts

        if policy == "active_zones_strictest":
            rows = await self._ports.fetch(
                """
                SELECT gcp.temp_air_target, gcp.humidity_target, gcp.extensions
                FROM grow_cycles gc
                JOIN zones z ON z.id = gc.zone_id
                JOIN grow_cycle_phases gcp ON gcp.id = gc.current_phase_id
                WHERE gc.greenhouse_id = $1
                  AND z.greenhouse_id = $1
                  AND gc.status IN ('RUNNING', 'ACTIVE')
                  AND gcp.temp_air_target IS NOT NULL
                  AND gcp.humidity_target IS NOT NULL
                """,
                greenhouse_id,
            )
            if not rows:
                alerts.append("GREENHOUSE_TARGET_POLICY_INVALID")
                resolved["greenhouse_targets"] = base_targets
                return resolved, alerts
            temp_max = min(float(row["temp_air_target"]) for row in rows)
            humidity_max = min(float(row["humidity_target"]) for row in rows)
            temp_mins: list[float] = [float(base_targets["temp_min_c"])]
            humidity_mins: list[float] = [float(base_targets["humidity_min_pct"])]
            for row in rows:
                extensions = row.get("extensions")
                if not isinstance(extensions, Mapping):
                    continue
                climate = extensions.get("climate")
                if not isinstance(climate, Mapping):
                    continue
                zone_temp_min = self._ports.as_float(climate.get("temp_min_c") or climate.get("temp_air_min"))
                zone_humidity_min = self._ports.as_float(climate.get("humidity_min_pct") or climate.get("humidity_min"))
                if zone_temp_min is not None:
                    temp_mins.append(float(zone_temp_min))
                if zone_humidity_min is not None:
                    humidity_mins.append(float(zone_humidity_min))
            temp_min = max(temp_mins)
            humidity_min = max(humidity_mins)
            if temp_min > temp_max or humidity_min > humidity_max:
                alerts.append("GREENHOUSE_TARGET_CONFLICT")
                resolved["greenhouse_targets"] = base_targets
                return resolved, alerts
            resolved["greenhouse_targets"] = {
                **base_targets,
                "temp_min_c": temp_min,
                "temp_max_c": temp_max,
                "humidity_min_pct": humidity_min,
                "humidity_max_pct": humidity_max,
            }
            return resolved, alerts

        alerts.append("GREENHOUSE_TARGET_POLICY_INVALID")
        resolved["greenhouse_targets"] = base_targets
        return resolved, alerts
