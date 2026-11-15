"""PgZoneSnapshotReadModel bundle rows: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from ae3lite.infrastructure.read_models.zone_snapshot_values_policy import ZoneSnapshotValuesPolicy


@dataclass(frozen=True)
class ZoneSnapshotBundleRowsPorts:
    pass


class ZoneSnapshotBundleRows:
    def __init__(self, ports: ZoneSnapshotBundleRowsPorts) -> None:
        self._ports = ports

    @staticmethod
    def bundle_override_rows(cycle_bundle: Any) -> List[Mapping[str, Any]]:
        if not isinstance(cycle_bundle, Mapping):
            return []

        rows: List[Mapping[str, Any]] = []
        phase_overrides = cycle_bundle.get("phase_overrides")
        if isinstance(phase_overrides, Mapping):
            phase_map = {
                "irrigation_mode": ("irrigation.mode", "string"),
                "irrigation_interval_sec": ("irrigation.interval_sec", "integer"),
                "irrigation_duration_sec": ("irrigation.duration_sec", "integer"),
            }
            for legacy_key, value in phase_overrides.items():
                mapping = phase_map.get(str(legacy_key).strip())
                if mapping is None or value is None:
                    continue
                parameter, value_type = mapping
                rows.append({"parameter": parameter, "value_type": value_type, "value": value})

        manual_overrides = cycle_bundle.get("manual_overrides")
        if isinstance(manual_overrides, list):
            rows.extend(item for item in manual_overrides if isinstance(item, Mapping))

        return rows

    @staticmethod
    def bundle_pid_config_rows(zone_bundle: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        pid_bundle = zone_bundle.get("pid")
        if not isinstance(pid_bundle, Mapping):
            return []

        rows: List[Mapping[str, Any]] = []
        for pid_type in ("ec", "ph"):
            entry = pid_bundle.get(pid_type)
            if not isinstance(entry, Mapping):
                continue
            rows.append(
                {
                    "type": pid_type,
                    "config": entry.get("config"),
                    "updated_at": None,
                }
            )
        return rows

    @staticmethod
    def bundle_correction_config_row(zone_bundle: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        correction_bundle = zone_bundle.get("correction")
        if not isinstance(correction_bundle, Mapping):
            return None

        resolved = correction_bundle.get("resolved_config")
        version = 1
        if isinstance(resolved, Mapping):
            meta = resolved.get("meta")
            if isinstance(meta, Mapping):
                try:
                    version = int(meta.get("version") or version)
                except (TypeError, ValueError):
                    version = 1

        return {
            "version": version,
            "resolved_config": resolved if isinstance(resolved, Mapping) else {},
            "phase_overrides": correction_bundle.get("phase_overrides"),
        }

    @staticmethod
    def bundle_process_calibration_rows(zone_bundle: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        calibrations = zone_bundle.get("process_calibration")
        if not isinstance(calibrations, Mapping):
            return []

        rows: List[Mapping[str, Any]] = []
        for mode, payload in calibrations.items():
            if not isinstance(payload, Mapping):
                continue
            row: Dict[str, Any] = {
                "mode": mode,
                "ec_gain_per_ml": payload.get("ec_gain_per_ml"),
                "ph_up_gain_per_ml": payload.get("ph_up_gain_per_ml"),
                "ph_down_gain_per_ml": payload.get("ph_down_gain_per_ml"),
                "ph_per_ec_ml": payload.get("ph_per_ec_ml"),
                "ec_per_ph_ml": payload.get("ec_per_ph_ml"),
                "transport_delay_sec": payload.get("transport_delay_sec"),
                "settle_sec": payload.get("settle_sec"),
                "confidence": payload.get("confidence"),
                "source": payload.get("source"),
                "valid_from": payload.get("valid_from"),
                "valid_to": payload.get("valid_to"),
                "is_active": payload.get("is_active", True),
                "meta": payload.get("meta"),
                "updated_at": payload.get("updated_at"),
            }
            gains = ZoneSnapshotValuesPolicy.component_gains_from_source(payload)
            if gains is not None:
                row["ec_component_gains"] = gains
            rows.append(row)
        return rows
