"""climate tick configuration: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ClimateTickConfigurationPorts:
    pass


class ClimateTickConfiguration:
    def __init__(self, ports: ClimateTickConfigurationPorts) -> None:
        self._ports = ports

    def parse_bundle(self, config: Mapping[str, Any] | None) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
        if not isinstance(config, dict):
            return {}, None, {}
        gh = config.get("greenhouse")
        if not isinstance(gh, dict):
            return {}, None, {}
        lp = gh.get("logic_profile")
        if not isinstance(lp, dict):
            return {}, None, {}
        mode = lp.get("active_mode")
        active_mode = str(mode).strip().lower() if isinstance(mode, str) else None
        if active_mode not in {"setup", "working"}:
            return {}, None, {}
        prof = lp.get("profiles", {}).get(active_mode)
        if not isinstance(prof, dict):
            return {}, active_mode, {}
        sub = prof.get("subsystems") or {}
        climate = sub.get("climate") if isinstance(sub, dict) else None
        if not isinstance(climate, dict):
            return {}, active_mode, {}
        return climate, active_mode, lp

    def as_float(self, value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def is_truthy_sensor_value(self, value: float) -> bool:
        return value >= 0.5
