"""PgZoneSnapshotReadModel telemetry: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping

from ae3lite.domain.errors import ErrorCodes, SnapshotBuildError


@dataclass(frozen=True)
class ZoneSnapshotTelemetryPorts:
    normalize_timestamp: Callable[..., Any]
    to_float: Callable[..., Any]


class ZoneSnapshotTelemetry:
    def __init__(self, ports: ZoneSnapshotTelemetryPorts) -> None:
        self._ports = ports

    def build_telemetry_last(self, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        seen_sensor_types: dict[str, int] = {}
        for row in rows:
            sensor_type = str(row.get("sensor_type") or "").strip().lower()
            if not sensor_type:
                continue
            seen_sensor_types[sensor_type] = seen_sensor_types.get(sensor_type, 0) + 1
            if sensor_type in {"ph", "ec"} and seen_sensor_types[sensor_type] > 1:
                raise SnapshotBuildError(
                    f"В zone snapshot обнаружено несколько активных telemetry sensors для критического типа={sensor_type}",
                    code=ErrorCodes.AE3_SNAPSHOT_CONFLICTING_CONFIG_VALUES,
                )
            if sensor_type in result:
                continue
            result[sensor_type] = {
                "sensor_id": row.get("sensor_id"),
                "sensor_label": row.get("sensor_label"),
                "value": float(row["last_value"]) if row.get("last_value") is not None else None,
                "sample_ts": row.get("sample_ts"),
                "quality": row.get("last_quality"),
            }
        return result

    def build_pid_state(self, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for row in rows:
            pid_type = str(row.get("pid_type") or "").strip().lower()
            if not pid_type:
                continue
            result[pid_type] = {
                "integral": self._ports.to_float(row.get("integral")),
                "prev_error": self._ports.to_float(row.get("prev_error")),
                "prev_derivative": self._ports.to_float(row.get("prev_derivative")),
                "last_output_ms": int(row.get("last_output_ms") or 0),
                "last_dose_at": self._ports.normalize_timestamp(row.get("last_dose_at")),
                "hold_until": self._ports.normalize_timestamp(row.get("hold_until")),
                "last_measurement_at": self._ports.normalize_timestamp(row.get("last_measurement_at")),
                "last_measured_value": self._ports.to_float(row.get("last_measured_value")),
                "feedforward_bias": self._ports.to_float(row.get("feedforward_bias")),
                "no_effect_count": int(row.get("no_effect_count") or 0),
                "last_correction_kind": row.get("last_correction_kind"),
                "stats": row.get("stats"),
                "current_zone": row.get("current_zone"),
                "updated_at": self._ports.normalize_timestamp(row.get("updated_at")),
            }
        return result

    @staticmethod
    def build_no_actuators_diagnostics(
        *,
        zone_id: int,
        diag_rows: List[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """Собирает per-node breakdown для ``AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS``."""
        from ae3lite.domain.services.zone_node_availability import classify_zone_nodes

        return classify_zone_nodes(zone_id=zone_id, diag_rows=diag_rows)
