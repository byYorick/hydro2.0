"""CreateTaskFromIntentUseCase payload: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class IntentTaskPayloadPorts:
    pass


class IntentTaskPayload:
    def __init__(self, ports: IntentTaskPayloadPorts) -> None:
        self._ports = ports

    def merge_solution_topup_intent_payload(
        self,
        *,
        intent_meta: dict[str, Any],
        solution_topup_mode: str | None,
        solution_topup_trigger: str | None,
    ) -> dict[str, Any]:
        merged = dict(intent_meta)
        payload = dict(merged.get("intent_payload") or {}) if isinstance(merged.get("intent_payload"), Mapping) else {}
        if solution_topup_mode is not None:
            normalized_mode = str(solution_topup_mode).strip().lower()
            if normalized_mode in {"normal", "force"}:
                payload["mode"] = normalized_mode
        if solution_topup_trigger is not None:
            trigger = str(solution_topup_trigger).strip()
            if trigger:
                payload["trigger"] = trigger
        merged["intent_payload"] = payload
        return merged

    def merge_lighting_tick_intent_payload(
        self,
        *,
        intent_meta: dict[str, Any],
        lighting_desired_state: str | None,
        lighting_brightness_pct: int | None,
    ) -> dict[str, Any]:
        merged = dict(intent_meta)
        payload = dict(merged.get("intent_payload") or {}) if isinstance(merged.get("intent_payload"), Mapping) else {}
        if lighting_desired_state is not None:
            normalized_state = str(lighting_desired_state).strip().lower()
            if normalized_state in {"on", "off"}:
                payload["desired_state"] = normalized_state
        if lighting_brightness_pct is not None:
            try:
                payload["brightness_pct"] = max(0, min(100, int(lighting_brightness_pct)))
            except (TypeError, ValueError):
                pass
        merged["intent_payload"] = payload
        return merged
