"""WorkflowRouter observability: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ae3lite.application.services.workflow_routing_shared import logger
from ae3lite.infrastructure.metrics import (
    STAGE_DURATION,
    inc_observability_write_failed,
)


@dataclass(frozen=True)
class WorkflowRoutingObservabilityPorts:
    irrigation_lifecycle_events: Callable[[], Any]
    normalize_utc_naive: Callable[..., Any]
    global_create_zone_event: Callable[..., Any]


class WorkflowRoutingObservability:
    def __init__(self, ports: WorkflowRoutingObservabilityPorts) -> None:
        self._ports = ports

    def record_stage_duration(self, *, task: Any, now: datetime) -> None:
        entered = task.workflow.stage_entered_at
        if entered is not None:
            now_cmp = self._ports.normalize_utc_naive(now)
            entered_cmp = self._ports.normalize_utc_naive(entered)
            duration = (now_cmp - entered_cmp).total_seconds()
            STAGE_DURATION.labels(
                topology=task.topology,
                stage=task.current_stage,
            ).observe(max(0, duration))

    async def safe_emit_irrigation_lifecycle_event(
        self,
        *,
        task: Any,
        from_stage: str | None,
        to_stage: str,
    ) -> None:
        key = (from_stage, to_stage)
        entry = self._ports.irrigation_lifecycle_events().get(key)
        if entry is None:
            return
        event_type, label = entry
        try:
            await self._ports.global_create_zone_event(
                int(task.zone_id),
                event_type,
                {
                    "task_id": task.id,
                    "from_stage": from_stage,
                    "to_stage": to_stage,
                    "label": label,
                },
            )
        except Exception:
            inc_observability_write_failed(kind="zone_event")
            logger.warning(
                "AE3 не смог записать %s zone_id=%s task_id=%s",
                event_type,
                task.zone_id,
                task.id,
                exc_info=True,
            )
