"""PgZoneSnapshotReadModel pump calibration: explicit collaborators and invocation context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional


@dataclass(frozen=True)
class ZoneSnapshotPumpCalibrationPorts:
    to_float: Callable[..., Any]
    to_int: Callable[..., Any]


class ZoneSnapshotPumpCalibration:
    def __init__(self, ports: ZoneSnapshotPumpCalibrationPorts) -> None:
        self._ports = ports

    def extract_pump_calibration(
        self,
        row: Mapping[str, Any],
        *,
        pump_calibration_policy: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        result: Dict[str, Any] = {}
        if isinstance(pump_calibration_policy, Mapping):
            result.update(
                {
                    "min_dose_ms": pump_calibration_policy.get("min_dose_ms"),
                    "max_dose_ms": pump_calibration_policy.get("max_dose_ms"),
                    "ml_per_sec_min": self._ports.to_float(pump_calibration_policy.get("ml_per_sec_min")),
                    "ml_per_sec_max": self._ports.to_float(pump_calibration_policy.get("ml_per_sec_max")),
                }
            )

        if row.get("calibration_ml_per_sec") is not None:
            result.update(
                {
                    "ml_per_sec": self._ports.to_float(row.get("calibration_ml_per_sec")),
                    "k_ms_per_ml_l": self._ports.to_float(row.get("calibration_k_ms_per_ml_l")),
                    "component": row.get("calibration_component"),
                    "source": row.get("calibration_source"),
                    "quality_score": self._ports.to_float(row.get("calibration_quality_score")),
                    "sample_count": int(row.get("calibration_sample_count") or 0),
                    "valid_from": row.get("calibration_valid_from"),
                }
            )

        channel_config = row.get("channel_config")
        if isinstance(channel_config, str):
            try:
                channel_config = json.loads(channel_config)
            except json.JSONDecodeError:
                channel_config = None
        if isinstance(channel_config, Mapping):
            node_ml_per_second = self._ports.to_float(channel_config.get("ml_per_second"))
            if node_ml_per_second is not None and node_ml_per_second > 0:
                result["node_ml_per_second"] = node_ml_per_second
            safe_limits = channel_config.get("safe_limits")
            if isinstance(safe_limits, Mapping):
                node_max_duration_ms = self._ports.to_int(safe_limits.get("max_duration_ms"))
                if node_max_duration_ms is not None and node_max_duration_ms > 0:
                    result["max_duration_ms"] = node_max_duration_ms
                    result["node_max_dose_ms"] = node_max_duration_ms

        return result or None

    def merge_pump_calibration_policy(
        self,
        correction_config: Mapping[str, Any],
        pump_calibration_policy: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        merged = dict(correction_config)
        if not isinstance(pump_calibration_policy, Mapping):
            return merged

        pump_calibration = merged.get("pump_calibration")
        pump_calibration_dict = dict(pump_calibration) if isinstance(pump_calibration, Mapping) else {}
        for key in (
            "min_dose_ms",
            "max_dose_ms",
            "ml_per_sec_min",
            "ml_per_sec_max",
            "ml_per_sec_mismatch_pct",
            "ml_per_sec_mismatch_fail_closed",
        ):
            if key in pump_calibration_policy and pump_calibration_policy.get(key) is not None:
                pump_calibration_dict[key] = pump_calibration_policy.get(key)
        merged["pump_calibration"] = pump_calibration_dict
        return merged
