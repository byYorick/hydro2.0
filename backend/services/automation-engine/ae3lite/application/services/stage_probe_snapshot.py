"""Stage component: probe snapshot. Explicit ports; no handler dependency."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from ae3lite.application.level_monitor import level_snapshot_aliases

_logger = logging.getLogger("ae3lite.application.handlers.base")


@dataclass(frozen=True)
class StageProbeSnapshotPorts:
    runtime_config: Callable[[], Any]


class StageProbeSnapshot:
    def __init__(self, ports: StageProbeSnapshotPorts) -> None:
        self._ports = ports
        self.last_probe_state: dict[str, Any] | None = None

    def remember_probe_state(self, *, task: Any, state: Mapping[str, Any]) -> None:
        snapshot = state.get("snapshot")
        stored_snapshot = dict(snapshot) if isinstance(snapshot, Mapping) else None
        self.last_probe_state = {
            "zone_id": int(getattr(task, "zone_id", 0) or 0),
            "task_id": int(getattr(task, "id", 0) or 0),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "state": {
                "has_snapshot": bool(state.get("has_snapshot")),
                "is_stale": bool(state.get("is_stale")),
                "snapshot": stored_snapshot,
                "sample_age_sec": state.get("sample_age_sec"),
                "created_at": state.get("created_at"),
                "cmd_id": state.get("cmd_id"),
                "event_id": state.get("event_id"),
            },
        }

    def probe_state_for_task(self, *, task: Any) -> Mapping[str, Any] | None:
        probe_ctx = self.last_probe_state
        if not isinstance(probe_ctx, Mapping):
            return None
        if int(probe_ctx.get("zone_id", 0) or 0) != int(getattr(task, "zone_id", 0) or 0):
            return None
        if int(probe_ctx.get("task_id", 0) or 0) != int(getattr(task, "id", 0) or 0):
            return None
        if str(probe_ctx.get("stage", "") or "") != str(getattr(task, "current_stage", "") or ""):
            return None
        state = probe_ctx.get("state")
        return state if isinstance(state, Mapping) else None

    def probe_snapshot_context(self, *, task: Any) -> Mapping[str, Any] | None:
        state = self.probe_state_for_task(task=task)
        if not isinstance(state, Mapping):
            return None
        if not bool(state.get("has_snapshot")) or bool(state.get("is_stale")):
            return None

        event_id_raw = state.get("event_id")
        try:
            event_id = int(event_id_raw) if event_id_raw is not None else None
        except (TypeError, ValueError):
            event_id = None

        created_at = state.get("created_at")
        created_at_iso = created_at.isoformat() if isinstance(created_at, datetime) else None
        cmd_id = str(state.get("cmd_id") or "").strip() or None

        context = {
            "snapshot_event_id": event_id if event_id and event_id > 0 else None,
            "snapshot_created_at": created_at_iso,
            "snapshot_cmd_id": cmd_id,
            "snapshot_source_event_type": "IRR_STATE_SNAPSHOT",
        }
        return {key: value for key, value in context.items() if value is not None}

    def probe_snapshot_correction_fields(self, *, task: Any) -> Mapping[str, Any]:
        state = self.probe_state_for_task(task=task)
        if not isinstance(state, Mapping):
            return {}
        if not bool(state.get("has_snapshot")) or bool(state.get("is_stale")):
            return {}

        event_id_raw = state.get("event_id")
        try:
            event_id = int(event_id_raw) if event_id_raw is not None else None
        except (TypeError, ValueError):
            event_id = None

        created_at = state.get("created_at")
        cmd_id = str(state.get("cmd_id") or "").strip() or None
        fields = {
            "snapshot_event_id": event_id if event_id and event_id > 0 else None,
            "snapshot_created_at": created_at if isinstance(created_at, datetime) else None,
            "snapshot_cmd_id": cmd_id,
            "snapshot_source_event_type": "IRR_STATE_SNAPSHOT",
        }
        return {key: value for key, value in fields.items() if value is not None}

    def read_probe_level_snapshot(
        self,
        *,
        task: Any,
        labels: Sequence[str],
        threshold: float,
        telemetry_max_age_sec: int,
    ) -> Mapping[str, Any] | None:
        state = self.probe_state_for_task(task=task)
        if not isinstance(state, Mapping):
            return None
        if not bool(state.get("has_snapshot")) or bool(state.get("is_stale")):
            return None
        snapshot = state.get("snapshot")
        if not isinstance(snapshot, Mapping):
            return None
        age_sec = self._ports.runtime_config().coerce_float(state.get("sample_age_sec"))
        if age_sec is not None and age_sec > max(0, int(telemetry_max_age_sec)):
            return None
        lookup = self.lookup_level_value_in_probe_snapshot(snapshot=snapshot, labels=labels)
        if lookup is None:
            return None
        resolved_label, is_triggered = lookup
        sample_ts = state.get("created_at")
        return {
            "sensor_label": resolved_label,
            "level": 1.0 if is_triggered else 0.0,
            "sample_ts": sample_ts,
            "sample_age_sec": age_sec,
            "has_level": True,
            "is_stale": False,
            "is_triggered": is_triggered,
            "expected_labels": list(labels),
            "source": "irr_state_snapshot",
        }

    def lookup_level_value_in_probe_snapshot(
        self,
        *,
        snapshot: Mapping[str, Any],
        labels: Sequence[str],
    ) -> tuple[str, bool] | None:
        normalized_snapshot = {
            str(key or "").strip().lower(): value for key, value in snapshot.items() if str(key or "").strip()
        }
        for label in labels:
            normalized_label = str(label or "").strip().lower()
            if normalized_label == "":
                continue
            aliases = self.level_snapshot_aliases(normalized_label)
            for alias in aliases:
                if alias not in normalized_snapshot:
                    continue
                coerced_value = self.coerce_probe_level_switch_value(normalized_snapshot[alias])
                if coerced_value is None:
                    continue
                return alias, coerced_value
        return None

    def level_snapshot_aliases(self, label: str) -> tuple[str, ...]:
        return level_snapshot_aliases(label)

    def coerce_probe_level_switch_value(self, value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value) != 0.0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "on", "yes"}:
                return True
            if normalized in {"0", "false", "off", "no"}:
                return False
        return None
