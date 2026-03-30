"""Maps legacy scheduler intent rows into canonical AE3-Lite v2 task metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class IntentMetadata:
    """Extracted intent metadata for task creation."""

    task_type: str
    current_stage: str
    workflow_phase: str
    topology: str
    intent_source: str
    intent_trigger: str
    intent_id: Optional[int]
    intent_meta: dict[str, Any]
    irrigation_mode: Optional[str] = None
    irrigation_requested_duration_sec: Optional[int] = None


class LegacyIntentMapper:
    """Compatibility adapter between legacy ``zone_automation_intents`` and AE3 v2."""

    DEFAULT_TRIGGER = "start_cycle_api"

    def extract_intent_metadata(
        self,
        *,
        source: str,
        intent_row: Mapping[str, Any],
    ) -> IntentMetadata:
        """Extract structured intent metadata from legacy intent row."""
        payload = intent_row.get("payload")
        intent_payload = dict(payload) if isinstance(payload, Mapping) else {}
        _raw_id = intent_row.get("id")
        intent_id = int(_raw_id) if _raw_id is not None else None
        intent_type = str(intent_row.get("intent_type") or "").strip().lower() or None
        topology = str(
            intent_payload.get("topology")
            or intent_row.get("topology")
            or "two_tank"
        ).strip().lower()
        requested_task_type = str(intent_payload.get("task_type") or "").strip().lower()
        requested_mode = str(intent_payload.get("mode") or "").strip().lower()
        requested_duration_raw = intent_payload.get("requested_duration_sec")
        requested_duration_sec = None
        if requested_duration_raw is not None:
            try:
                requested_duration_sec = max(1, int(requested_duration_raw))
            except (TypeError, ValueError):
                requested_duration_sec = None

        is_irrigation = requested_task_type == "irrigation_start" or intent_type in {"irrigate_once", "irrigation"}
        task_type = "irrigation_start" if is_irrigation else "cycle_start"
        current_stage = "await_ready" if is_irrigation else "startup"
        workflow_phase = "ready" if is_irrigation else "idle"

        return IntentMetadata(
            task_type=task_type,
            current_stage=current_stage,
            workflow_phase=workflow_phase,
            topology=topology,
            intent_source=str(source or "").strip() or "laravel_scheduler",
            intent_trigger=intent_type or self.DEFAULT_TRIGGER,
            intent_id=intent_id,
            intent_meta={
                "intent_type": intent_type,
                "intent_retry_count": int(intent_row.get("retry_count") or 0),
                "intent_zone_id": (lambda v: int(v) if v is not None else None)(intent_row.get("zone_id")),
                "intent_payload": intent_payload,
            },
            irrigation_mode=requested_mode if requested_mode in {"normal", "force"} else ("normal" if is_irrigation else None),
            irrigation_requested_duration_sec=requested_duration_sec,
        )

    # Backward-compat alias (used by v1 code paths until they are removed)
    def build_cycle_start_payload(
        self,
        *,
        zone_id: int,
        source: str,
        intent_row: Mapping[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = intent_row.get("payload")
        intent_payload = dict(payload) if isinstance(payload, Mapping) else {}
        intent_type = str(intent_row.get("intent_type") or "").strip().lower() or None
        return {
            "source": str(source or "").strip() or "laravel_scheduler",
            "trigger": intent_type or self.DEFAULT_TRIGGER,
            "workflow": "cycle_start",
            "intent_id": (lambda v: int(v) if v is not None else None)(intent_row.get("id")),
            "intent_type": intent_type,
            "intent_retry_count": int(intent_row.get("retry_count") or 0),
            "intent_zone_id": int(intent_row.get("zone_id") or zone_id),
            "idempotency_key": str(idempotency_key or "").strip(),
            "intent_payload": intent_payload,
        }
