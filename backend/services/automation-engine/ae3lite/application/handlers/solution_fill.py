"""SolutionFillCheckHandler: in-flow correction во время заполнения бака раствора."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import STAGE_DEADLINE_EXCEEDED
from common.biz_alerts import send_biz_alert

_logger = logging.getLogger(__name__)


class SolutionFillCheckHandler(BaseStageHandler):
    """Обрабатывает ``solution_fill_check``: окно заполнения и in-flow correction.

    Исходы:
    1. Бак полон и target'ы достигнуты → ``solution_fill_stop_to_ready``
    2. Бак полон, но target'ы не достигнуты → ``solution_fill_stop_to_prepare``
    3. Бак ещё заполняется и target'ы не достигнуты → коррекция внутри ``solution_fill_check``
    4. Бак ещё заполняется и target'ы достигнуты → ``poll``
    5. Дедлайн превышен → ``solution_fill_timeout_stop``
    """

    _STALE_RECHECK_DELAY_SEC = 0.25

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        runtime = plan.runtime
        control_mode = str(getattr(task.workflow, "control_mode", "") or "auto").strip().lower()
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "")
        fail_safe_guards = runtime.get("fail_safe_guards") if isinstance(runtime.get("fail_safe_guards"), dict) else {}
        recent_storage_event = await self._read_recent_storage_event(
            task=task,
            event_types=(
                "SOLUTION_FILL_SOURCE_EMPTY",
                "SOLUTION_FILL_LEAK_DETECTED",
                "SOLUTION_FILL_COMPLETED",
                "EMERGENCY_STOP_ACTIVATED",
            ),
            max_age_sec=86400,
        )
        recent_event_type = str((recent_storage_event or {}).get("event_type") or "").strip().upper()
        if recent_event_type == "SOLUTION_FILL_SOURCE_EMPTY":
            self._observe_fail_safe_transition(
                task=task,
                reason="solution_fill_source_empty",
                source="node_event",
                next_stage="solution_fill_source_empty_stop",
            )
            return StageOutcome(kind="transition", next_stage="solution_fill_source_empty_stop")
        if recent_event_type == "SOLUTION_FILL_LEAK_DETECTED":
            self._observe_fail_safe_transition(
                task=task,
                reason="solution_fill_leak_detected",
                source="node_event",
                next_stage="solution_fill_leak_stop",
            )
            return StageOutcome(kind="transition", next_stage="solution_fill_leak_stop")
        if recent_event_type == "EMERGENCY_STOP_ACTIVATED":
            await self._reconcile_recent_emergency_stop(
                task=task,
                plan=plan,
                now=now,
                expected={
                    "valve_clean_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
            )
        if recent_event_type == "SOLUTION_FILL_COMPLETED":
            return await self._completed_outcome(task=task, plan=plan, now=now)

        try:
            await self._probe_irr_state(
                task=task, plan=plan, now=now,
                expected={
                    "valve_clean_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
            )
        except TaskExecutionError as exc:
            if exc.code == "irr_state_mismatch":
                raced_completion_event = await self._read_recent_storage_event(
                    task=task,
                    event_types=("SOLUTION_FILL_COMPLETED",),
                    max_age_sec=86400,
                )
                raced_event_type = str((raced_completion_event or {}).get("event_type") or "").strip().upper()
                if raced_event_type == "SOLUTION_FILL_COMPLETED":
                    _logger.info(
                        "solution_fill_check: probe увидел уже выключенный fill-state, но node успела опубликовать completion; завершаем штатно zone_id=%s task_id=%s",
                        task.zone_id,
                        getattr(task, "id", None),
                    )
                    return await self._completed_outcome(task=task, plan=plan, now=now)
            raise

        if pending_manual_step == "solution_fill_stop":
            if await self._should_finish_to_ready(task=task, plan=plan, now=now):
                return StageOutcome(kind="transition", next_stage="solution_fill_stop_to_ready")
            return StageOutcome(kind="transition", next_stage="solution_fill_stop_to_prepare")
        if control_mode == "manual":
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)),
            )

        clean_min_check_delay_ms = int(fail_safe_guards.get("solution_fill_clean_min_check_delay_ms", 5000) or 0)
        if self._stage_elapsed_ms(task=task, now=now) >= max(0, clean_min_check_delay_ms):
            clean_min = await self._read_level(
                task=task,
                zone_id=task.zone_id,
                labels=runtime["clean_min_sensor_labels"],
                threshold=runtime["level_switch_on_threshold"],
                telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
                unavailable_error="two_tank_clean_min_level_unavailable",
                stale_error="two_tank_clean_min_level_stale",
                stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
                prefer_probe_snapshot=True,
            )
            if not clean_min["is_triggered"]:
                self._observe_fail_safe_transition(
                    task=task,
                    reason="solution_fill_source_empty",
                    source="sensor",
                    next_stage="solution_fill_source_empty_stop",
                )
                return StageOutcome(kind="transition", next_stage="solution_fill_source_empty_stop")

        solution_min_check_delay_ms = int(fail_safe_guards.get("solution_fill_solution_min_check_delay_ms", 15000) or 0)
        if self._stage_elapsed_ms(task=task, now=now) >= max(0, solution_min_check_delay_ms):
            solution_min = await self._read_level(
                task=task,
                zone_id=task.zone_id,
                labels=runtime["solution_min_sensor_labels"],
                threshold=runtime["level_switch_on_threshold"],
                telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
                unavailable_error="two_tank_solution_min_level_unavailable",
                stale_error="two_tank_solution_min_level_stale",
                stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
                prefer_probe_snapshot=True,
            )
            if not solution_min["is_triggered"]:
                self._observe_fail_safe_transition(
                    task=task,
                    reason="solution_fill_leak_detected",
                    source="sensor",
                    next_stage="solution_fill_leak_stop",
                )
                return StageOutcome(kind="transition", next_stage="solution_fill_leak_stop")

        solution_max = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime["solution_max_sensor_labels"],
            threshold=runtime["level_switch_on_threshold"],
            telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
            unavailable_error="two_tank_solution_level_unavailable",
            stale_error="two_tank_solution_level_stale",
            stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
            prefer_probe_snapshot=True,
        )

        if solution_max["is_triggered"]:
            return await self._completed_outcome(task=task, plan=plan, now=now)

        # Проверка дедлайна
        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            _logger.warning("solution_fill_check: дедлайн превышен, заполнение останавливается zone_id=%s", task.zone_id)
            STAGE_DEADLINE_EXCEEDED.labels(
                topology=str(getattr(task, "topology", "") or ""),
                stage="solution_fill_check",
            ).inc()
            try:
                await send_biz_alert(
                    code="biz_solution_fill_timeout",
                    alert_type="AE3 Solution Fill Timeout",
                    message="Превышено время заполнения бака раствором до завершения этапа.",
                    severity="warning",
                    zone_id=int(task.zone_id),
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "topology": str(getattr(task, "topology", "") or ""),
                        "stage": "solution_fill_check",
                        "component": "handler:solution_fill_check",
                        "message": "Превышено время заполнения бака раствором; проверьте клапан подачи раствора и насос.",
                    },
                    scope_parts=("stage:solution_fill_check",),
                )
            except Exception:
                # Audit F9: include full exception context so downstream debugging
                # of failed alert delivery isn't blocked by a message without
                # zone/task identification.
                _logger.warning(
                    "Не удалось отправить alert biz_solution_fill_timeout "
                    "zone_id=%s task_id=%s",
                    task.zone_id,
                    getattr(task, "id", None),
                    exc_info=True,
                )
            return StageOutcome(kind="transition", next_stage="solution_fill_timeout_stop")

        if await self._targets_reached(task=task, plan=plan, now=now):
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)),
            )

        if int(getattr(task.workflow, "stage_retry_count", 0) or 0) > 0:
            _logger.info(
                "solution_fill_check: in-flow correction уже исчерпана, заполнение продолжается без новой коррекции zone_id=%s retry_count=%s",
                task.zone_id,
                getattr(task.workflow, "stage_retry_count", 0),
            )
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)),
            )

        _logger.info(
            "solution_fill_check: заполнение продолжается, цели не достигнуты; вход в in-flow correction zone_id=%s",
            task.zone_id,
        )
        corr = self._build_correction_state(
            task=task,
            runtime=runtime,
            sensors_already_active=True,
            return_stage_success=stage_def.on_corr_success or "solution_fill_check",
            return_stage_fail=stage_def.on_corr_fail or "solution_fill_check",
        )
        return StageOutcome(kind="enter_correction", correction=corr)

    async def _should_finish_to_ready(self, *, task: Any, plan: Any, now: datetime) -> bool:
        runtime = plan.runtime
        solution_max = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime["solution_max_sensor_labels"],
            threshold=runtime["level_switch_on_threshold"],
            telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
            unavailable_error="two_tank_solution_level_unavailable",
            stale_error="two_tank_solution_level_stale",
            stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
            prefer_probe_snapshot=True,
        )
        if not solution_max["is_triggered"]:
            return False

        await self._check_sensor_consistency(
            task=task,
            runtime=runtime,
            min_labels_key="solution_min_sensor_labels",
            min_unavailable_error="two_tank_solution_min_level_unavailable",
            min_stale_error="two_tank_solution_min_level_stale",
            stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
            prefer_probe_snapshot=True,
        )
        return await self._workflow_ready_reached(task=task, plan=plan, now=now)

    async def _completed_outcome(self, *, task: Any, plan: Any, now: datetime) -> StageOutcome:
        runtime = plan.runtime
        await self._check_sensor_consistency(
            task=task,
            runtime=runtime,
            min_labels_key="solution_min_sensor_labels",
            min_unavailable_error="two_tank_solution_min_level_unavailable",
            min_stale_error="two_tank_solution_min_level_stale",
            stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
            prefer_probe_snapshot=True,
        )

        if await self._workflow_ready_reached(task=task, plan=plan, now=now):
            _logger.debug("solution_fill_check: цели достигнуты, заполнение останавливается zone_id=%s", task.zone_id)
            return StageOutcome(
                kind="transition",
                next_stage="solution_fill_stop_to_ready",
            )

        _logger.info(
            "solution_fill_check: бак заполнен, но цели не достигнуты; переход в prepare recirculation zone_id=%s",
            task.zone_id,
        )
        return StageOutcome(
            kind="transition",
            next_stage="solution_fill_stop_to_prepare",
        )

    def _build_correction_state(
        self,
        *,
        task: Any,
        runtime: Any,
        sensors_already_active: bool,
        return_stage_success: str,
        return_stage_fail: str,
    ) -> CorrectionState:
        correction_cfg = self._correction_config_for_task(task=task, runtime=runtime)
        ec_max_attempts = int(correction_cfg.get("max_ec_correction_attempts", 5))
        ph_max_attempts = int(correction_cfg.get("max_ph_correction_attempts", 5))
        corr = CorrectionState.build_default(
            corr_step="corr_check" if sensors_already_active else "corr_activate",
            max_attempts=max(ec_max_attempts, ph_max_attempts),
            ec_max_attempts=ec_max_attempts,
            ph_max_attempts=ph_max_attempts,
            activated_here=not sensors_already_active,
            stabilization_sec=int(correction_cfg.get("stabilization_sec", 60)),
            return_stage_success=return_stage_success,
            return_stage_fail=return_stage_fail,
        )
        return replace(corr, **self._probe_snapshot_correction_fields(task=task))
