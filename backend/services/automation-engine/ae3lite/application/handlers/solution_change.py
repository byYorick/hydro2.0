"""Solution change handlers: operator gates и drain-подконтур (semi-auto v1, этап D.1)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import STAGE_DEADLINE_EXCEEDED
from common.biz_alerts import send_biz_alert
from common.db import create_zone_event

_logger = logging.getLogger(__name__)

_GATE_CONFIRM_BY_STAGE = {
    "await_operator_drain_confirm": "solution_drain_confirm",
    "await_operator_refill_confirm": "solution_refill_confirm",
}


class SolutionChangeOperatorGateHandler(BaseStageHandler):
    """Ожидание operator confirm на gate-stages await_operator_* (G1/G2)."""

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        runtime = self._require_runtime_plan(plan=plan)
        stage_name = str(getattr(stage_def, "name", "") or "").strip()
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "").strip()

        abort = await self._check_solution_change_abort(task=task, pending_manual_step=pending_manual_step)
        if abort is not None:
            return abort

        confirm_step = _GATE_CONFIRM_BY_STAGE.get(stage_name)
        if confirm_step and pending_manual_step == confirm_step:
            next_stage = {
                "await_operator_drain_confirm": "solution_drain_start",
                "await_operator_refill_confirm": "prepare_recirculation_start",
            }.get(stage_name)
            if next_stage:
                try:
                    await create_zone_event(
                        int(task.zone_id),
                        "SOLUTION_CHANGE_GATE_PASSED",
                        {
                            "task_id": int(getattr(task, "id", 0) or 0),
                            "zone_id": int(getattr(task, "zone_id", 0) or 0),
                            "stage": stage_name,
                            "manual_step": confirm_step,
                        },
                    )
                except Exception:
                    _logger.warning(
                        "solution_change_gate: не удалось записать SOLUTION_CHANGE_GATE_PASSED zone_id=%s",
                        getattr(task, "zone_id", None),
                        exc_info=True,
                    )
                return StageOutcome(kind="transition", next_stage=next_stage)

        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            _logger.warning(
                "solution_change_gate: operator confirm timeout stage=%s zone_id=%s",
                stage_name,
                task.zone_id,
            )
            STAGE_DEADLINE_EXCEEDED.labels(
                topology=str(getattr(task, "topology", "") or ""),
                stage=stage_name,
            ).inc()
            return StageOutcome(kind="transition", next_stage="solution_change_operator_timeout_stop")

        return StageOutcome(
            kind="poll",
            due_delay_sec=int(runtime.level_poll_interval_sec),
        )


class SolutionDrainCheckHandler(BaseStageHandler):
    """Poll-loop слива: уровень solution_min, fail-safe и дедлайн."""

    _STALE_RECHECK_DELAY_SEC = 0.25

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        runtime = self._require_runtime_plan(plan=plan)
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "").strip()

        abort = await self._check_solution_change_abort(task=task, pending_manual_step=pending_manual_step)
        if abort is not None:
            return abort

        try:
            await self._probe_irr_state(
                task=task,
                plan=plan,
                now=now,
                expected={"valve_drain": True},
            )
        except TaskExecutionError as exc:
            if exc.code == "irr_state_mismatch":
                solution_min = await self._read_level(
                    task=task,
                    zone_id=task.zone_id,
                    labels=runtime.solution_min_sensor_labels,
                    threshold=runtime.level_switch_on_threshold,
                    telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
                    unavailable_error="two_tank_solution_min_level_unavailable",
                    stale_error="two_tank_solution_min_level_stale",
                    stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
                    prefer_probe_snapshot=True,
                )
                if not solution_min["is_triggered"]:
                    _logger.info(
                        "solution_drain_check: probe mismatch, но бак раствора уже опустошён; переход к clean_fill zone_id=%s",
                        task.zone_id,
                    )
                    return StageOutcome(kind="transition", next_stage="solution_drain_stop_to_clean_fill")
            raise

        solution_min = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime.solution_min_sensor_labels,
            threshold=runtime.level_switch_on_threshold,
            telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
            unavailable_error="two_tank_solution_min_level_unavailable",
            stale_error="two_tank_solution_min_level_stale",
            stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
            prefer_probe_snapshot=True,
        )
        if not solution_min["is_triggered"]:
            _logger.info(
                "solution_drain_check: бак раствора опустошён, переход к clean_fill zone_id=%s",
                task.zone_id,
            )
            return StageOutcome(kind="transition", next_stage="solution_drain_stop_to_clean_fill")

        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            _logger.warning(
                "solution_drain_check: дедлайн превышен zone_id=%s",
                task.zone_id,
            )
            STAGE_DEADLINE_EXCEEDED.labels(
                topology=str(getattr(task, "topology", "") or ""),
                stage="solution_drain_check",
            ).inc()
            try:
                await send_biz_alert(
                    code="biz_solution_drain_timeout",
                    alert_type="AE3 Solution Drain Timeout",
                    message="Превышено время слива бака раствора при подмене.",
                    severity="warning",
                    zone_id=int(task.zone_id),
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "topology": str(getattr(task, "topology", "") or ""),
                        "stage": "solution_drain_check",
                        "component": "handler:solution_drain_check",
                    },
                    scope_parts=("stage:solution_drain_check",),
                )
            except Exception:
                _logger.warning(
                    "Не удалось отправить alert biz_solution_drain_timeout zone_id=%s",
                    task.zone_id,
                    exc_info=True,
                )
            return StageOutcome(kind="transition", next_stage="solution_drain_timeout_stop")

        return StageOutcome(
            kind="poll",
            due_delay_sec=int(runtime.level_poll_interval_sec),
        )


class SolutionChangeCompleteHandler(BaseStageHandler):
    """Завершает task solution_change после complete_ready."""

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        try:
            await create_zone_event(
                int(task.zone_id),
                "SOLUTION_CHANGE_COMPLETED",
                {
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "zone_id": int(getattr(task, "zone_id", 0) or 0),
                    "stage": "complete_ready",
                },
            )
        except Exception:
            _logger.warning(
                "solution_change_complete: не удалось записать SOLUTION_CHANGE_COMPLETED zone_id=%s",
                getattr(task, "zone_id", None),
                exc_info=True,
            )
        return StageOutcome(kind="complete")
