"""Decision gate for irrigation tasks."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import IRRIGATION_DECISION
from common.biz_alerts import send_biz_alert


_logger = logging.getLogger(__name__)


def _irrigation_decision_alert_dedupe_key(*, outcome: str, zone_id: int, reason_code: str) -> str:
    """Стабильный dedupe_key без task_id, чтобы Laravel/alert ingest не плодил дубли на частых skip/degraded."""
    rc = str(reason_code or "").strip() or "unknown"
    return f"ae3_irrigation_decision|{outcome}|z{int(zone_id)}|{rc}"


class DecisionGateHandler(BaseStageHandler):
    def __init__(self, *, runtime_monitor: Any, command_gateway: Any, task_repository: Any, decision_controller: Any) -> None:
        super().__init__(runtime_monitor=runtime_monitor, command_gateway=command_gateway)
        self._task_repository = task_repository
        self._decision_controller = decision_controller

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        owner = str(getattr(task, "claimed_by", "") or "")
        decision = await self._decision_controller.evaluate(
            zone_id=int(task.zone_id),
            runtime_monitor=self._runtime_monitor,
            runtime=plan.runtime if hasattr(plan, "runtime") else {},
            mode=str(getattr(task, "irrigation_mode", None) or "normal"),
            requested_duration_sec=getattr(task, "irrigation_requested_duration_sec", None),
            now=now,
        )
        updated = await self._task_repository.update_irrigation_runtime(
            task_id=int(task.id),
            owner=owner,
            now=now,
            irrigation_decision_strategy=str(
                ((plan.runtime or {}).get("irrigation_decision") or {}).get("strategy")
            ),
            irrigation_decision_outcome=decision.outcome,
            irrigation_decision_reason_code=decision.reason_code,
            irrigation_decision_degraded=decision.degraded,
        )
        if updated is None:
            raise TaskExecutionError("irrigation_decision_persist_failed", "Unable to persist irrigation decision")

        IRRIGATION_DECISION.labels(
            topology=str(getattr(task, "topology", "") or ""),
            strategy=str(((plan.runtime or {}).get("irrigation_decision") or {}).get("strategy") or ""),
            outcome=str(decision.outcome or ""),
        ).inc()

        try:
            if decision.outcome == "skip":
                await send_biz_alert(
                    code="biz_irrigation_decision_skip",
                    alert_type="AE3 Irrigation Decision Skip",
                    message="Irrigation decision-controller decided to skip irrigation.",
                    severity="info",
                    zone_id=int(task.zone_id),
                    dedupe_key=_irrigation_decision_alert_dedupe_key(
                        outcome="skip",
                        zone_id=int(task.zone_id),
                        reason_code=str(getattr(decision, "reason_code", "") or ""),
                    ),
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "topology": str(getattr(task, "topology", "") or ""),
                        "stage": "decision_gate",
                        "strategy": str(((plan.runtime or {}).get("irrigation_decision") or {}).get("strategy") or ""),
                        "bundle_revision": str((plan.runtime or {}).get("bundle_revision") or ""),
                        "reason_code": str(getattr(decision, "reason_code", "") or ""),
                        "degraded": bool(getattr(decision, "degraded", False)),
                    },
                    scope_parts=("stage:decision_gate",),
                )
            if decision.outcome == "degraded_run":
                await send_biz_alert(
                    code="biz_irrigation_decision_degraded",
                    alert_type="AE3 Irrigation Decision Degraded",
                    message="Irrigation decision-controller allowed degraded irrigation run.",
                    severity="warning",
                    zone_id=int(task.zone_id),
                    dedupe_key=_irrigation_decision_alert_dedupe_key(
                        outcome="degraded_run",
                        zone_id=int(task.zone_id),
                        reason_code=str(getattr(decision, "reason_code", "") or ""),
                    ),
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "topology": str(getattr(task, "topology", "") or ""),
                        "stage": "decision_gate",
                        "strategy": str(((plan.runtime or {}).get("irrigation_decision") or {}).get("strategy") or ""),
                        "bundle_revision": str((plan.runtime or {}).get("bundle_revision") or ""),
                        "reason_code": str(getattr(decision, "reason_code", "") or ""),
                        "degraded": True,
                    },
                    scope_parts=("stage:decision_gate",),
                )
            if decision.outcome == "fail":
                await send_biz_alert(
                    code="biz_irrigation_decision_fail",
                    alert_type="AE3 Irrigation Decision Fail",
                    message="Irrigation decision-controller returned fail.",
                    severity="error",
                    zone_id=int(task.zone_id),
                    dedupe_key=_irrigation_decision_alert_dedupe_key(
                        outcome="fail",
                        zone_id=int(task.zone_id),
                        reason_code=str(getattr(decision, "reason_code", "") or ""),
                    ),
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "topology": str(getattr(task, "topology", "") or ""),
                        "stage": "decision_gate",
                        "strategy": str(((plan.runtime or {}).get("irrigation_decision") or {}).get("strategy") or ""),
                        "bundle_revision": str((plan.runtime or {}).get("bundle_revision") or ""),
                        "error_code": str(getattr(decision, "reason_code", "") or ""),
                        "reason_code": str(getattr(decision, "reason_code", "") or ""),
                        "degraded": bool(getattr(decision, "degraded", False)),
                    },
                    scope_parts=("stage:decision_gate",),
                )
        except Exception:
            _logger.warning(
                "AE3 failed to emit irrigation decision alert zone_id=%s task_id=%s outcome=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                str(getattr(decision, "outcome", "") or ""),
                exc_info=True,
            )

        if decision.outcome == "skip":
            return StageOutcome(kind="transition", next_stage="completed_skip")
        if decision.outcome == "fail":
            return StageOutcome(
                kind="fail",
                error_code=decision.reason_code,
                error_message="Irrigation decision-controller returned fail",
            )
        return StageOutcome(kind="transition", next_stage="irrigation_start")
