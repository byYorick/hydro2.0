"""Преобразует строки legacy scheduler intent в канонические метаданные задач AE3-Lite v2."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Mapping, Optional

from ae3lite.domain.errors import TaskCreateError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntentMetadata:
    """Извлечённые метаданные intent для создания задачи."""

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
    """Адаптер совместимости между legacy ``zone_automation_intents`` и AE3 v2."""

    DEFAULT_TRIGGER = "start_cycle_api"

    def extract_intent_metadata(
        self,
        *,
        source: str,
        intent_row: Mapping[str, Any],
    ) -> IntentMetadata:
        """Извлекает структурированные метаданные intent из legacy-строки."""
        payload = intent_row.get("payload")
        intent_payload = dict(payload) if isinstance(payload, Mapping) else {}
        _raw_id = intent_row.get("id")
        intent_id = int(_raw_id) if _raw_id is not None else None
        intent_type = str(intent_row.get("intent_type") or "").strip().lower() or None
        raw_topology = intent_payload.get("topology")
        if raw_topology is None:
            raw_topology = intent_row.get("topology")
        topology = str(raw_topology or "").strip().lower()
        if not topology:
            logger.error(
                "AE3 legacy intent mapper отклонил intent без topology: intent_id=%s",
                intent_id,
            )
            raise TaskCreateError(
                "start_cycle_intent_topology_missing",
                f"У intent {intent_id if intent_id is not None else '<unknown>'} отсутствует topology",
                details={"intent_id": intent_id},
            )
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
        is_lighting_tick = requested_task_type == "lighting_tick" or intent_type in {"lighting_tick", "lighting"}

        if is_lighting_tick:
            return IntentMetadata(
                task_type="lighting_tick",
                current_stage="apply",
                workflow_phase="ready",
                topology="lighting_tick",
                intent_source=str(source or "").strip() or "laravel_scheduler",
                intent_trigger=intent_type or self.DEFAULT_TRIGGER,
                intent_id=intent_id,
                intent_meta={
                    "intent_type": intent_type,
                    "intent_retry_count": int(intent_row.get("retry_count") or 0),
                    "intent_zone_id": (lambda v: int(v) if v is not None else None)(intent_row.get("zone_id")),
                    "intent_payload": intent_payload,
                },
                irrigation_mode=None,
                irrigation_requested_duration_sec=None,
            )

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

    # Алиас обратной совместимости для v1 code path, пока они не удалены
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
