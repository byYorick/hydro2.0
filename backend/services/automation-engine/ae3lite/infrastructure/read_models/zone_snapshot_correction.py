"""PgZoneSnapshotReadModel correction: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

from ae3lite.domain.services.phase_utils import normalize_phase_key
from ae3lite.infrastructure.read_models.zone_snapshot_values_policy import ZoneSnapshotValuesPolicy


@dataclass(frozen=True)
class ZoneSnapshotCorrectionPorts:
    as_mapping: Callable[..., Any]
    to_float: Callable[..., Any]


class ZoneSnapshotCorrection:
    def __init__(self, ports: ZoneSnapshotCorrectionPorts) -> None:
        self._ports = ports

    def resolve_ec_component_policy(self, execution: Mapping[str, Any]) -> Dict[str, Any]:
        correction = execution.get("correction")
        if not isinstance(correction, Mapping):
            return {}
        policy = correction.get("ec_component_policy")
        if not isinstance(policy, Mapping):
            return {}
        result: Dict[str, Any] = {}
        for phase, phase_policy in policy.items():
            if isinstance(phase_policy, Mapping):
                result[str(phase).strip()] = dict(phase_policy)
        return result

    def build_correction_config(self, row: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        version = row.get("version")
        try:
            version_int = int(version)
        except (TypeError, ValueError):
            return None
        resolved = row.get("resolved_config")
        result: Dict[str, Any] = dict(resolved) if isinstance(resolved, Mapping) else {}
        meta = result.get("meta")
        result["meta"] = dict(meta) if isinstance(meta, dict) else {}
        result["meta"]["version"] = version_int
        phase_overrides = row.get("phase_overrides")
        if isinstance(phase_overrides, Mapping):
            result["meta"]["phase_overrides"] = dict(phase_overrides)
        return result

    def build_process_calibrations(self, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for row in rows:
            if not row.get("is_active", True):
                continue
            mode = normalize_phase_key(row.get("mode"))
            if not mode or mode in result:
                continue
            meta = self._ports.as_mapping(row.get("meta"))
            entry: Dict[str, Any] = {
                "ec_gain_per_ml": self._ports.to_float(row.get("ec_gain_per_ml")),
                "ph_up_gain_per_ml": self._ports.to_float(row.get("ph_up_gain_per_ml")),
                "ph_down_gain_per_ml": self._ports.to_float(row.get("ph_down_gain_per_ml")),
                "ph_per_ec_ml": self._ports.to_float(row.get("ph_per_ec_ml")),
                "ec_per_ph_ml": self._ports.to_float(row.get("ec_per_ph_ml")),
                "transport_delay_sec": int(row.get("transport_delay_sec") or 0),
                "settle_sec": int(row.get("settle_sec") or 0),
                "confidence": self._ports.to_float(row.get("confidence")),
                "source": row.get("source"),
                "valid_from": row.get("valid_from"),
                "valid_to": row.get("valid_to"),
                "meta": meta if meta is not None else {},
                "updated_at": row.get("updated_at"),
            }
            gains = self.ec_component_gains_from_source(row)
            if gains is not None:
                entry["ec_component_gains"] = gains
            result[mode] = entry
        return result

    @staticmethod
    def ec_component_gains_from_source(source):
        return ZoneSnapshotValuesPolicy.component_gains_from_source(source)

    def build_pid_configs(self, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for row in rows:
            pid_type = str(row.get("type") or "").strip().lower()
            if not pid_type:
                continue
            result[pid_type] = {
                "config": row.get("config"),
                "updated_at": row.get("updated_at"),
            }
        return result
