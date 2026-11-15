"""GetZoneAutomationStateUseCase timeline: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.services.zone_state_shared import (
    _IDLE_NODE_EVENT_LOOKBACK_SEC,
    _LEVEL_CHANNEL_LABELS,
    _NODE_EVENT_LABELS,
    _TRANSITION_EVENT_MAP,
)


@dataclass(frozen=True)
class ZoneStateTimelinePorts:
    fetch_recent_node_runtime_events: Callable[..., Awaitable[Any]]
    normalize_utc_naive: Callable[..., Any]
    now: Callable[..., Any]


class ZoneStateTimeline:
    def __init__(self, ports: ZoneStateTimelinePorts) -> None:
        self._ports = ports

    def build_node_runtime_timeline_event(self, row: Mapping[str, Any]) -> dict[str, Any] | None:
        event_type = str(row.get("type") or "").strip().upper()
        payload = row.get("payload")
        payload_map = payload if isinstance(payload, Mapping) else {}
        ts = row.get("created_at")

        if event_type == "LEVEL_SWITCH_CHANGED":
            channel = str(payload_map.get("channel") or "").strip().lower()
            state = payload_map.get("state")
            initial = payload_map.get("initial")
            channel_label = _LEVEL_CHANNEL_LABELS.get(channel, channel or "датчик уровня")
            normalized_state = (
                state if isinstance(state, bool) else str(state).strip().lower() in {"1", "true", "yes", "on"}
            )
            normalized_initial = (
                initial if isinstance(initial, bool) else str(initial).strip().lower() in {"1", "true", "yes", "on"}
            )
            state_label = "сработал" if normalized_state else "отпущен"
            prefix = "Начальное состояние ноды" if normalized_initial else "Сигнал датчика"
            label = f"{prefix}: {channel_label} {state_label}"
        else:
            label = _NODE_EVENT_LABELS.get(event_type, event_type)

        return {
            "event": event_type,
            "label": label,
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "active": False,
            "source": "node_event",
        }

    async def build_timeline(
        self,
        *,
        zone_id: int,
        transitions: list[dict],
        since_ts: datetime | None,
    ) -> list[dict]:
        events = []
        for t in transitions:
            from_s = str(t.get("from_stage") or "")
            to_s = str(t.get("to_stage") or "")
            key = (from_s, to_s)
            event_code, label = _TRANSITION_EVENT_MAP.get(key, (f"{from_s}→{to_s}", f"{from_s} → {to_s}"))
            ts = t.get("triggered_at")
            events.append(
                {
                    "event": event_code,
                    "label": label,
                    "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    "active": False,
                    "source": "transition",
                }
            )
        events.extend(await self._ports.fetch_recent_node_runtime_events(zone_id=zone_id, since_ts=since_ts))
        events.sort(key=lambda item: str(item.get("timestamp") or ""))
        # Пометить последнее событие как активное
        if events:
            events[-1]["active"] = True
        return events

    def timeline_since(self, *, task: Any | None) -> datetime | None:
        if task is None:
            return None
        for field_name in ("created_at", "updated_at"):
            value = getattr(task, field_name, None)
            if isinstance(value, datetime):
                return self._ports.normalize_utc_naive(value)
        workflow = getattr(task, "workflow", None)
        entered = getattr(workflow, "stage_entered_at", None)
        if isinstance(entered, datetime):
            return self._ports.normalize_utc_naive(entered)
        return None

    def timeline_since_workflow(self, *, workflow_state: Any | None) -> datetime | None:
        if workflow_state is None:
            return self.idle_timeline_since()
        for field_name in ("updated_at", "started_at"):
            value = getattr(workflow_state, field_name, None)
            if isinstance(value, datetime):
                return self._ports.normalize_utc_naive(value)
        return self.idle_timeline_since()

    def idle_timeline_since(self) -> datetime:
        return self._ports.now() - timedelta(seconds=_IDLE_NODE_EVENT_LOOKBACK_SEC)
