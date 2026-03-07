"""Maps legacy scheduler intent rows into canonical AE3-Lite v2 task metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class IntentMetadata:
    """Extracted intent metadata for task creation."""

    topology: str
    intent_source: str
    intent_trigger: str
    intent_id: Optional[int]
    intent_meta: dict[str, Any]


class LegacyIntentMapper:
    """Compatibility adapter between legacy ``zone_automation_intents`` and AE3 v2."""

    def extract_intent_metadata(
        self,
        *,
        source: str,
        intent_row: Mapping[str, Any],
    ) -> IntentMetadata:
        """Extract structured intent metadata from legacy intent row."""
        payload = intent_row.get("payload")
        intent_payload = dict(payload) if isinstance(payload, Mapping) else {}
        intent_id = int(intent_row.get("id") or 0) or None
        topology = str(
            intent_payload.get("topology")
            or intent_row.get("topology")
            or "two_tank"
        ).strip().lower()

        return IntentMetadata(
            topology=topology,
            intent_source=str(source or "").strip() or "laravel_scheduler",
            intent_trigger="start_cycle_api",
            intent_id=intent_id,
            intent_meta={
                "intent_type": str(intent_row.get("intent_type") or "").strip().lower() or None,
                "intent_retry_count": int(intent_row.get("retry_count") or 0),
                "intent_zone_id": int(intent_row.get("zone_id") or 0) or None,
                "intent_payload": intent_payload,
            },
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
        return {
            "source": str(source or "").strip() or "laravel_scheduler",
            "trigger": "start_cycle_api",
            "workflow": "cycle_start",
            "intent_id": int(intent_row.get("id") or 0) or None,
            "intent_type": str(intent_row.get("intent_type") or "").strip().lower() or None,
            "intent_retry_count": int(intent_row.get("retry_count") or 0),
            "intent_zone_id": int(intent_row.get("zone_id") or zone_id),
            "idempotency_key": str(idempotency_key or "").strip(),
            "intent_payload": intent_payload,
        }
