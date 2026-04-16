"""Decision gate для задач полива."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import IRRIGATION_DECISION
from common.biz_alerts import send_biz_alert
from common.db import create_zone_event


_logger = logging.getLogger(__name__)


def _irrigation_decision_alert_dedupe_key(*, outcome: str, zone_id: int, reason_code: str) -> str:
    """Стабильный dedupe_key без task_id, чтобы Laravel/alert ingest не плодил дубли на частых skip/degraded."""
    rc = str(reason_code or "").strip() or "unknown"
    return f"ae3_irrigation_decision|{outcome}|z{int(zone_id)}|{rc}"


class DecisionGateHandler(BaseStageHandler):
    def __init__(
        self, *,
        runtime_monitor: Any, command_gateway: Any, task_repository: Any, decision_controller: Any,
        live_reload_enabled: bool = False,
    ) -> None:
        super().__init__(
            runtime_monitor=runtime_monitor,
            command_gateway=command_gateway,
            live_reload_enabled=live_reload_enabled,
        )
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
        runtime = self._require_runtime_plan(plan=plan)
        decision = await self._decision_controller.evaluate(
            zone_id=int(task.zone_id),
            runtime_monitor=self._runtime_monitor,
            runtime=runtime,
            mode=str(getattr(task, "irrigation_mode", None) or "normal"),
            requested_duration_sec=getattr(task, "irrigation_requested_duration_sec", None),
            now=now,
        )
        updated = await self._task_repository.update_irrigation_runtime(
            task_id=int(task.id),
            owner=owner,
            now=now,
            irrigation_decision_strategy=str(runtime.irrigation_decision.strategy or ""),
            irrigation_decision_outcome=decision.outcome,
            irrigation_decision_reason_code=decision.reason_code,
            irrigation_decision_degraded=decision.degraded,
        )
        if updated is None:
            raise TaskExecutionError("irrigation_decision_persist_failed", "Не удалось сохранить решение по поливу")

        IRRIGATION_DECISION.labels(
            topology=str(getattr(task, "topology", "") or ""),
            strategy=str(runtime.irrigation_decision.strategy or ""),
            outcome=str(decision.outcome or ""),
        ).inc()

        await self._emit_irrigation_decision_event(
            task=updated,
            plan=plan,
            decision=decision,
        )

        try:
            if decision.outcome == "skip":
                await send_biz_alert(
                    code="biz_irrigation_decision_skip",
                    alert_type="AE3 Irrigation Decision Skip",
                    message="Decision-controller полива решил пропустить запуск.",
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
                        "strategy": str(runtime.irrigation_decision.strategy or ""),
                        "bundle_revision": str(runtime.bundle_revision or ""),
                        "reason_code": str(getattr(decision, "reason_code", "") or ""),
                        "degraded": bool(getattr(decision, "degraded", False)),
                    },
                    scope_parts=("stage:decision_gate",),
                )
            if decision.outcome == "degraded_run":
                await send_biz_alert(
                    code="biz_irrigation_decision_degraded",
                    alert_type="AE3 Irrigation Decision Degraded",
                    message="Decision-controller полива разрешил деградированный запуск.",
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
                        "strategy": str(runtime.irrigation_decision.strategy or ""),
                        "bundle_revision": str(runtime.bundle_revision or ""),
                        "reason_code": str(getattr(decision, "reason_code", "") or ""),
                        "degraded": True,
                    },
                    scope_parts=("stage:decision_gate",),
                )
            if decision.outcome == "fail":
                await send_biz_alert(
                    code="biz_irrigation_decision_fail",
                    alert_type="AE3 Irrigation Decision Fail",
                    message="Decision-controller полива вернул отказ.",
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
                        "strategy": str(runtime.irrigation_decision.strategy or ""),
                        "bundle_revision": str(runtime.bundle_revision or ""),
                        "error_code": str(getattr(decision, "reason_code", "") or ""),
                        "reason_code": str(getattr(decision, "reason_code", "") or ""),
                        "degraded": bool(getattr(decision, "degraded", False)),
                    },
                    scope_parts=("stage:decision_gate",),
                )
        except Exception:
            _logger.warning(
                "AE3 не смог отправить alert по решению полива zone_id=%s task_id=%s outcome=%s",
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
                error_message="Decision-controller полива вернул отказ",
            )
        return StageOutcome(kind="transition", next_stage="irrigation_start")

    async def _emit_irrigation_decision_event(
        self,
        *,
        task: Any,
        plan: Any,
        decision: Any,
    ) -> None:
        runtime = self._require_runtime_plan(plan=plan)
        details = {
            "task_id": int(getattr(task, "id", 0) or 0),
            "zone_id": int(getattr(task, "zone_id", 0) or 0),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task, "workflow_phase", "") or ""),
            "topology": str(getattr(task, "topology", "") or ""),
            "strategy": str(runtime.irrigation_decision.strategy or getattr(task, "irrigation_decision_strategy", "") or ""),
            "bundle_revision": str((runtime.bundle_revision or getattr(task, "irrigation_bundle_revision", "") or "")).strip() or None,
            "outcome": str(getattr(decision, "outcome", "") or ""),
            "reason_code": str(getattr(decision, "reason_code", "") or ""),
            "degraded": bool(getattr(decision, "degraded", False)),
            "details": dict(getattr(decision, "details", {}) or {}) if isinstance(getattr(decision, "details", None), Mapping) else None,
        }
        payload = {key: value for key, value in details.items() if value is not None and value != ""}

        try:
            await create_zone_event(
                int(getattr(task, "zone_id", 0) or 0),
                "IRRIGATION_DECISION_EVALUATED",
                payload,
            )
        except Exception:
            _logger.warning(
                "AE3 не смог записать IRRIGATION_DECISION_EVALUATED zone_id=%s task_id=%s outcome=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                str(getattr(decision, "outcome", "") or ""),
                exc_info=True,
            )
