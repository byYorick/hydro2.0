"""PgZoneRuntimeMonitor values: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from ae3lite.infrastructure.read_models.runtime_monitor_shared import logger


@dataclass(frozen=True)
class RuntimeMonitorValuesPorts:
    pass


class RuntimeMonitorValues:
    def __init__(self, ports: RuntimeMonitorValuesPorts) -> None:
        self._ports = ports

    def normalize_timestamp(self, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        normalized = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
        return normalized.replace(microsecond=0)

    def normalize_labels(self, labels: Sequence[str]) -> list[str]:
        result: list[str] = []
        for item in labels:
            normalized = str(item or "").strip().lower()
            if normalized:
                result.append(normalized)
        return result

    def age_sec(self, sample_ts: Optional[datetime]) -> Optional[float]:
        if sample_ts is None:
            return None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        normalized = sample_ts.astimezone(timezone.utc).replace(tzinfo=None) if sample_ts.tzinfo else sample_ts
        return max(0.0, (now - normalized).total_seconds())

    def resolve_zone_event_payload(self, row: Mapping[str, Any]) -> Mapping[str, Any]:
        for field_name in ("details", "payload_json", "payload"):
            value = row.get(field_name)
            if isinstance(value, Mapping):
                return value
        logger.warning(
            "AE3 zone runtime monitor: zone_event payload is not a mapping row_id=%s event_type=%s",
            row.get("id"),
            row.get("event_type"),
        )
        return {}

    def coerce_optional_bool(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if float(value) == 1.0:
                return True
            if float(value) == 0.0:
                return False
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return None

    def payload_field(self, payload: Mapping[str, Any], key: str) -> Any:
        value = payload.get(key)
        if value is not None:
            return value
        nested = payload.get("payload")
        if isinstance(nested, Mapping):
            return nested.get(key)
        return None

    def level_snapshot_aliases(self, label: str) -> tuple[str, ...]:
        normalized = str(label or "").strip().lower()
        aliases = {normalized}
        if normalized.startswith("level_"):
            suffix = normalized[len("level_") :]
            parts = suffix.split("_")
            if len(parts) >= 2:
                aliases.add("_".join((parts[0], "level", *parts[1:])))
        parts = normalized.split("_")
        if len(parts) >= 3 and parts[1] == "level":
            aliases.add("_".join(("level", parts[0], *parts[2:])))
        return tuple(alias for alias in aliases if alias)

    def extract_level_state_from_event(
        self,
        *,
        payload: Mapping[str, Any],
        labels: Sequence[str],
    ) -> tuple[str, bool] | None:
        event_channel = str(self.payload_field(payload, "channel") or "").strip().lower()
        event_state = self.coerce_optional_bool(self.payload_field(payload, "state"))
        normalized_labels = self.normalize_labels(labels)
        if event_channel and event_state is not None:
            for label in normalized_labels:
                if event_channel in self.level_snapshot_aliases(label):
                    return event_channel, event_state

        snapshot = self.payload_field(payload, "snapshot")
        if not isinstance(snapshot, Mapping):
            return None
        normalized_snapshot = {
            str(key or "").strip().lower(): value for key, value in snapshot.items() if str(key or "").strip()
        }
        for label in normalized_labels:
            for alias in self.level_snapshot_aliases(label):
                if alias not in normalized_snapshot:
                    continue
                snapshot_state = self.coerce_optional_bool(normalized_snapshot.get(alias))
                if snapshot_state is not None:
                    return alias, snapshot_state
        return None

    def prefer_event_over_telemetry(
        self,
        *,
        telemetry_level: Mapping[str, Any],
        event_level: Mapping[str, Any] | None,
        allow_if_telemetry_fresh: bool,
    ) -> Mapping[str, Any] | None:
        if event_level is None:
            return None
        if not telemetry_level["has_level"] or telemetry_level["is_stale"]:
            return event_level
        if not allow_if_telemetry_fresh:
            return None

        telemetry_ts = telemetry_level.get("sample_ts")
        event_ts = event_level.get("sample_ts")
        if isinstance(event_ts, datetime) and isinstance(telemetry_ts, datetime) and event_ts >= telemetry_ts:
            return event_level
        return None
