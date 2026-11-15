"""Stage component: deadline outcome. Explicit ports; no handler dependency."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.hydraulics.failure_report import note_upward_report

_logger = logging.getLogger("ae3lite.application.handlers.base")


@dataclass(frozen=True)
class StageDeadlineOutcomePorts:
    target_outcome_snapshot: Callable[..., Awaitable[Any]]
    create_zone_event: Callable[..., Awaitable[Any]]


class StageDeadlineOutcome:
    def __init__(self, ports: StageDeadlineOutcomePorts) -> None:
        self._ports = ports

    async def targets_reached_on_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> bool:
        """Deadline-safe target check: stale/unavailable telemetry → not reached."""
        snapshot = await self.target_outcome_on_deadline(
            task=task,
            plan=plan,
            now=now,
            runtime=runtime,
        )
        return snapshot["chemistry_outcome"] == "targets_achieved"

    async def target_outcome_on_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> Mapping[str, Any]:
        """Return a fail-closed, diagnostic target snapshot for a stage deadline."""
        try:
            return await self._ports.target_outcome_snapshot(
                task=task,
                plan=plan,
                now=now,
                runtime=runtime,
            )
        except TaskExecutionError as exc:
            return {
                "chemistry_outcome": "unknown",
                "targets_reached": None,
                "reason": str(getattr(exc, "code", "") or "target_snapshot_unavailable"),
                "error_message": str(exc),
            }
        except Exception as exc:
            _logger.warning(
                "AE3 target snapshot failed zone_id=%s task_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                exc_info=True,
            )
            return {
                "chemistry_outcome": "unknown",
                "targets_reached": None,
                "reason": "target_snapshot_evaluation_failed",
                "error_message": str(exc),
            }

    async def record_deadline_target_outcome(
        self,
        *,
        task: Any,
        snapshot: Mapping[str, Any],
        reason: str = "stage_deadline",
    ) -> None:
        """Persist the chemistry result independently from hydraulic completion."""
        outcome = str(snapshot.get("chemistry_outcome") or "unknown")
        event_type = {
            "targets_achieved": "CORRECTION_COMPLETE",
            "targets_not_achieved": "CORRECTION_TARGETS_NOT_ACHIEVED",
        }.get(outcome, "CORRECTION_TARGET_OUTCOME_UNKNOWN")
        details = {
            "task_id": int(getattr(task, "id", 0) or 0),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "topology": str(getattr(task, "topology", "") or ""),
            "completion_reason": reason,
            **dict(snapshot),
        }
        try:
            await self._ports.create_zone_event(
                int(getattr(task, "zone_id", 0) or 0),
                event_type,
                with_runtime_event_contract(details),
            )
        except Exception:
            _logger.warning(
                "AE3 could not persist deadline chemistry outcome zone_id=%s task_id=%s outcome=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                outcome,
                exc_info=True,
            )

        if outcome == "targets_achieved":
            return
        unknown = outcome == "unknown"
        await note_upward_report(
            code=(
                "biz_ae3_correction_target_outcome_unknown" if unknown else "biz_ae3_correction_targets_not_achieved"
            ),
            message=(
                "Не удалось подтвердить итоговые pH/EC на дедлайне коррекции"
                if unknown
                else "Целевые pH/EC не достигнуты к завершению коррекции"
            ),
            severity="error" if unknown else "warning",
            zone_id=int(getattr(task, "zone_id", 0) or 0),
            alert_type="automation",
            dedupe_key=(f"ae3:chemistry-outcome:{int(getattr(task, 'id', 0) or 0)}:{outcome}"),
            details=details,
            scope_parts=(str(int(getattr(task, "id", 0) or 0)), outcome),
        )
