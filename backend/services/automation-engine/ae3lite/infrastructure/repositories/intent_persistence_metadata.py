"""PgZoneIntentRepository metadata: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ae3lite.domain.errors import TaskCreateError
from ae3lite.domain.intent_metadata import IntentMetadata


@dataclass(frozen=True)
class IntentPersistenceMetadataPorts:
    pass


class IntentPersistenceMetadata:
    def __init__(self, ports: IntentPersistenceMetadataPorts) -> None:
        self._ports = ports

    def extract_intent_metadata(
        self,
        *,
        source: str,
        intent_row: Mapping[str, Any],
    ) -> IntentMetadata:
        """Строит IntentMetadata из типизированных колонок zone_automation_intents."""
        topology = str(intent_row.get("topology") or "").strip().lower()
        if not topology:
            _raw_id = intent_row.get("id")
            _intent_id = int(_raw_id) if _raw_id is not None else None
            raise TaskCreateError(
                "start_cycle_intent_topology_missing",
                f"У intent {_intent_id if _intent_id is not None else '<unknown>'} отсутствует topology",
                details={"intent_id": _intent_id},
            )

        task_type = str(intent_row.get("task_type") or "cycle_start").strip().lower()
        intent_type = str(intent_row.get("intent_type") or "").strip().lower() or None
        _raw_id = intent_row.get("id")
        intent_id = int(_raw_id) if _raw_id is not None else None

        is_irrigation = task_type == "irrigation_start"
        is_lighting_tick = task_type == "lighting_tick"
        is_solution_topup = task_type == "solution_topup"
        is_solution_change = task_type == "solution_change"

        if is_lighting_tick:
            current_stage = "apply"
            workflow_phase = "ready"
            topology = "lighting_tick"
        elif is_solution_topup:
            current_stage = "solution_topup_guard"
            workflow_phase = "ready"
        elif is_solution_change:
            current_stage = "await_operator_drain_confirm"
            workflow_phase = "ready"
        elif is_irrigation:
            current_stage = "await_ready"
            workflow_phase = "ready"
        else:
            current_stage = "startup"
            workflow_phase = "idle"

        irrig_mode_raw = str(intent_row.get("irrigation_mode") or "").strip().lower()
        irrig_mode = irrig_mode_raw if irrig_mode_raw in {"normal", "force"} else ("normal" if is_irrigation else None)

        irrig_dur = intent_row.get("irrigation_requested_duration_sec")
        if irrig_dur is not None:
            try:
                irrig_dur = max(1, int(irrig_dur))
            except (TypeError, ValueError):
                irrig_dur = None

        intent_payload: dict[str, Any] = {}
        if is_lighting_tick:
            payload_raw = intent_row.get("payload")
            if isinstance(payload_raw, Mapping):
                desired_state = str(payload_raw.get("desired_state") or "").strip().lower()
                if desired_state in {"on", "off"}:
                    intent_payload["desired_state"] = desired_state
                brightness_pct = payload_raw.get("brightness_pct")
                if brightness_pct is None:
                    brightness_pct = payload_raw.get("brightness")
                if brightness_pct is not None:
                    try:
                        intent_payload["brightness_pct"] = max(0, min(100, int(brightness_pct)))
                    except (TypeError, ValueError):
                        pass
        if is_solution_topup:
            payload_raw = intent_row.get("payload")
            if isinstance(payload_raw, Mapping):
                mode = str(payload_raw.get("mode") or "").strip().lower()
                if mode in {"normal", "force"}:
                    intent_payload["mode"] = mode
                trigger = str(payload_raw.get("trigger") or "").strip()
                if trigger:
                    intent_payload["trigger"] = trigger
        if is_solution_change:
            payload_raw = intent_row.get("payload")
            if isinstance(payload_raw, Mapping):
                trigger = str(payload_raw.get("trigger") or "").strip()
                if trigger:
                    intent_payload["trigger"] = trigger

        return IntentMetadata(
            task_type=task_type,
            current_stage=current_stage,
            workflow_phase=workflow_phase,
            topology=topology,
            intent_source=str(intent_row.get("intent_source") or source or "").strip() or "laravel_scheduler",
            intent_trigger=intent_type or "start_cycle_api",
            intent_id=intent_id,
            intent_meta={
                "intent_type": intent_type,
                "intent_retry_count": int(intent_row.get("retry_count") or 0),
                "intent_zone_id": (lambda v: int(v) if v is not None else None)(intent_row.get("zone_id")),
                "intent_payload": intent_payload,
            },
            irrigation_mode=irrig_mode if is_irrigation else None,
            irrigation_requested_duration_sec=irrig_dur if is_irrigation else None,
        )
