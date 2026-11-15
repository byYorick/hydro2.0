"""climate tick alerts: explicit dependencies and invocation data."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class ClimateTickAlertsPorts:
    greenhouse_climate_decision_duration_seconds: Callable[..., Any]
    greenhouse_climate_tick_total: Callable[..., Any]
    alert_publisher: Callable[..., Any]
    greenhouse_alert_codes: Callable[..., Any]
    alert_severity: Callable[..., Any]
    as_float: Callable[..., Any]
    unique_alert_codes: Callable[..., Any]
    logger: Callable[..., Any]


class ClimateTickAlerts:
    def __init__(self, ports: ClimateTickAlertsPorts) -> None:
        self._ports = ports

    def alert_severity(self, code: str) -> str:
        if code in {"GREENHOUSE_OVERHEAT_EMERGENCY", "GREENHOUSE_VENT_COMMAND_FAILED"}:
            return "critical"
        if code in {"GREENHOUSE_TARGET_CONFLICT", "GREENHOUSE_TARGET_POLICY_INVALID"}:
            return "error"
        return "warning"

    def unique_alert_codes(self, codes: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for code in codes:
            normalized = str(code or "").strip().upper()
            if normalized and normalized not in seen:
                out.append(normalized)
                seen.add(normalized)
        return out

    async def publish_greenhouse_alert_lifecycle(
        self, *, greenhouse_id: int, active_codes: list[str], details: Mapping[str, Any], alert_publisher: Any
    ) -> None:
        active_set = set(self._ports.unique_alert_codes(active_codes))
        publisher = alert_publisher or self._ports.alert_publisher()
        for code in sorted(self._ports.greenhouse_alert_codes()):
            payload = {
                "greenhouse_id": greenhouse_id,
                "component": "greenhouse_climate",
                "code": code,
                **dict(details),
            }
            dedupe_key = f"greenhouse_climate|greenhouse:{greenhouse_id}|code:{code.lower()}"
            try:
                if code in active_set:
                    await publisher.raise_active(
                        zone_id=None,
                        source="biz",
                        code=code,
                        alert_type="greenhouse_climate",
                        details={**payload, "dedupe_key": dedupe_key},
                        dedupe_key=dedupe_key,
                        scoped=True,
                        severity=self._ports.alert_severity(code),
                    )
                else:
                    await publisher.resolve(
                        zone_id=None,
                        source="biz",
                        code=code,
                        alert_type="greenhouse_climate",
                        details={**payload, "dedupe_key": dedupe_key},
                        dedupe_key=dedupe_key,
                        scoped=True,
                        severity=self._ports.alert_severity(code),
                    )
            except Exception:
                self._ports.logger().warning(
                    "greenhouse_climate_tick alert lifecycle publish failed gh=%s code=%s",
                    greenhouse_id,
                    code,
                    exc_info=True,
                )

    def record_tick_metric(self, start_monotonic: float, status: str) -> None:
        try:
            self._ports.greenhouse_climate_tick_total().labels(status=status).inc()
            self._ports.greenhouse_climate_decision_duration_seconds().observe(
                max(0.0, time.monotonic() - start_monotonic)
            )
        except Exception:
            self._ports.logger().debug("greenhouse climate metrics update failed", exc_info=True)

    def spread_alerts(self, snapshot: Mapping[str, Any], execution: Mapping[str, Any]) -> list[str]:
        temp_threshold = float(self._ports.as_float(execution.get("inside_temp_spread_alert_c")) or 4.0)
        rh_threshold = float(self._ports.as_float(execution.get("inside_rh_spread_alert_pct")) or 15.0)
        temp_spread = self._ports.as_float(snapshot.get("inside_temp_spread"))
        rh_spread = self._ports.as_float(snapshot.get("inside_rh_spread"))
        if (temp_spread is not None and temp_spread > temp_threshold) or (
            rh_spread is not None and rh_spread > rh_threshold
        ):
            return ["GREENHOUSE_CLIMATE_SENSOR_SPREAD_HIGH"]
        return []
