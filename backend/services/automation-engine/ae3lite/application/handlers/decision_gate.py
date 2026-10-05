"""Decision gate для задач полива."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.irrigation_decision_controller import IrrigationDecision
from ae3lite.domain.services.solution_temp_irrigation_guard import (
    DEFAULT_SOLUTION_TEMP_STALE_SEC,
    evaluate_solution_temp_hold,
    solution_temp_gate_active,
)
from ae3lite.infrastructure.metrics import (
    CROP_IRRIGATION_BLOCKED,
    IRRIGATION_DECISION,
    inc_observability_write_failed,
)
from ae3lite.hydraulics.failure_report import note_upward_report
from common.db import create_zone_event


_logger = logging.getLogger(__name__)


def _irrigation_decision_alert_dedupe_key(*, outcome: str, zone_id: int, reason_code: str) -> str:
    """Стабильный dedupe_key без task_id, чтобы Laravel/alert ingest не плодил дубли на частых skip/degraded."""
    rc = str(reason_code or "").strip() or "unknown"
    return f"ae3_irrigation_decision|{outcome}|z{int(zone_id)}|{rc}"


_QUIET_SUCCESS_SKIP_REASONS = frozenset({
    "smart_soil_target_missing",
    "smart_soil_telemetry_missing_or_stale",
    "solution_temp_unavailable",
    "solution_temp_out_of_band",
})


def _task_already_blocking_skip(task: Any) -> bool:
    """Повторный poll читает колонки уже записанного blocking skip."""
    outcome = str(getattr(task, "irrigation_decision_outcome", "") or "").strip()
    reason = str(getattr(task, "irrigation_decision_reason_code", "") or "").strip()
    return outcome == "skip" and reason in _QUIET_SUCCESS_SKIP_REASONS


def _record_blocking_irrigation_skip(*, task: Any, decision: Any) -> None:
    reason = str(getattr(decision, "reason_code", "") or "").strip()
    if str(getattr(decision, "outcome", "") or "") != "skip":
        return
    if reason not in _QUIET_SUCCESS_SKIP_REASONS or _task_already_blocking_skip(task):
        return
    CROP_IRRIGATION_BLOCKED.labels(reason=reason).inc()


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
        decision = await self._apply_solution_temp_gate(
            decision=decision,
            task=task,
            runtime=runtime,
            now=now,
        )
        updated = await self._task_repository.update_irrigation_runtime(
            task_id=int(task.id),
            owner=owner,
            now=now,
            irrigation_decision_strategy=str(runtime.irrigation_decision.strategy or ""),
            irrigation_decision_outcome=decision.outcome,
            irrigation_decision_reason_code=decision.reason_code,
            claim_generation=int(getattr(task, "claim_generation", 0) or 0),
            irrigation_decision_degraded=decision.degraded,
        )
        if updated is None:
            raise TaskExecutionError("irrigation_decision_persist_failed", "Не удалось сохранить решение по поливу")

        IRRIGATION_DECISION.labels(
            topology=str(getattr(task, "topology", "") or ""),
            strategy=str(runtime.irrigation_decision.strategy or ""),
            outcome=str(decision.outcome or ""),
        ).inc()
        _record_blocking_irrigation_skip(task=task, decision=decision)

        await self._emit_irrigation_decision_event(
            task=updated,
            plan=plan,
            decision=decision,
        )

        try:
            reason_code = str(getattr(decision, "reason_code", "") or "")
            if decision.outcome == "skip" and reason_code not in _QUIET_SUCCESS_SKIP_REASONS:
                await note_upward_report(
                    code="biz_irrigation_decision_skip",
                    alert_type="AE3 Irrigation Decision Skip",
                    message="Decision-controller полива решил пропустить запуск.",
                    severity="info",
                    zone_id=int(task.zone_id),
                    dedupe_key=_irrigation_decision_alert_dedupe_key(
                        outcome="skip",
                        zone_id=int(task.zone_id),
                        reason_code=reason_code,
                    ),
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "topology": str(getattr(task, "topology", "") or ""),
                        "stage": "decision_gate",
                        "strategy": str(runtime.irrigation_decision.strategy or ""),
                        "bundle_revision": str(runtime.bundle_revision or ""),
                        "reason_code": reason_code,
                        "degraded": bool(getattr(decision, "degraded", False)),
                    },
                    scope_parts=("stage:decision_gate",),
                )
            if decision.outcome == "degraded_run":
                await note_upward_report(
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
                await note_upward_report(
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
            inc_observability_write_failed(kind="biz_alert")
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

    async def _apply_solution_temp_gate(
        self,
        *,
        decision: Any,
        task: Any,
        runtime: Any,
        now: datetime,
    ) -> Any:
        """После стратегии G1 и до irrigation_start. Итог один, дозу не отменяет."""
        if str(getattr(decision, "outcome", "") or "") == "fail":
            return decision
        health = getattr(runtime, "solution_health", None)
        required = bool(getattr(health, "required", False))
        min_c = getattr(health, "min_c", None)
        max_c = getattr(health, "max_c", None)
        if not solution_temp_gate_active(required=required, min_c=min_c, max_c=max_c):
            return decision

        hold_sec = int(getattr(health, "breach_hold_sec", DEFAULT_SOLUTION_TEMP_STALE_SEC) or DEFAULT_SOLUTION_TEMP_STALE_SEC)
        try:
            reading = await self._runtime_monitor.read_solution_temp_window(
                zone_id=int(task.zone_id),
                since_ts=now - timedelta(seconds=hold_sec),
                until_ts=now,
            )
        except Exception:
            _logger.warning(
                "AE3 solution temp gate не прочитал telemetry zone_id=%s task_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                exc_info=True,
            )
            reading = None

        verdict = evaluate_solution_temp_hold(
            min_c=float(min_c),
            max_c=float(max_c),
            hold_sec=hold_sec,
            stale_sec=DEFAULT_SOLUTION_TEMP_STALE_SEC,
            now=now,
            reading=reading if isinstance(reading, Mapping) else None,
        )
        if verdict is None:
            return decision
        return IrrigationDecision(
            outcome="skip",
            reason_code=verdict.reason_code,
            degraded=False,
            details=verdict.details,
        )

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
            inc_observability_write_failed(kind="zone_event")
            _logger.warning(
                "AE3 не смог записать IRRIGATION_DECISION_EVALUATED zone_id=%s task_id=%s outcome=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                str(getattr(decision, "outcome", "") or ""),
                exc_info=True,
            )
