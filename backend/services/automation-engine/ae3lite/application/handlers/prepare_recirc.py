"""PrepareRecircCheckHandler: target'ы, дедлайн и вход в коррекцию."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.workflow_state import CorrectionState

_logger = logging.getLogger(__name__)


class PrepareRecircCheckHandler(BaseStageHandler):
    """Обрабатывает ``prepare_recirculation_check``: probe, target'ы и коррекцию.

    Исходы:
    1. Target'ы достигнуты → ``prepare_recirculation_stop_to_ready``
    2. Target'ы не достигнуты → вход в цикл коррекции
    3. Дедлайн превышен → ``prepare_recirculation_window_exhausted``
    """

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        new_runtime = await self._checkpoint(task=task, plan=plan, now=now)
        if new_runtime is not plan.runtime:
            plan = replace(plan, runtime=new_runtime)
        runtime = plan.runtime
        control_mode = str(getattr(task.workflow, "control_mode", "") or "auto").strip().lower()
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "")
        fail_safe_guards = runtime["fail_safe_guards"]
        solution_min_guard_enabled = bool(fail_safe_guards["recirculation_stop_on_solution_min"])

        # Fail-fast перед новой probe-командой. Иначе stage, у которого уже
        # закончилось время, может опубликовать новый storage_state request и упасть
        # на command polling вместо перехода по ожидаемому path window_exhausted.
        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            _logger.info(
                "prepare_recirculation_check: дедлайн превышен, окно исчерпывается zone_id=%s retry=%s",
                task.zone_id, task.workflow.stage_retry_count + 1,
            )
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=task.workflow.stage_retry_count + 1,
            )
        if self._deadline_too_close_for_irr_probe(now=now, deadline=deadline, runtime=runtime):
            _logger.info(
                "prepare_recirculation_check: оставшееся время stage меньше бюджета IRR probe, "
                "окно исчерпывается zone_id=%s retry=%s",
                task.zone_id,
                task.workflow.stage_retry_count + 1,
            )
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=task.workflow.stage_retry_count + 1,
            )

        recent_storage_event = await self._read_recent_storage_event(
            task=task,
            event_types=("RECIRCULATION_SOLUTION_LOW", "EMERGENCY_STOP_ACTIVATED"),
            max_age_sec=86400,
        )
        recent_event_type = str((recent_storage_event or {}).get("event_type") or "").strip().upper()
        if recent_event_type == "RECIRCULATION_SOLUTION_LOW" and solution_min_guard_enabled:
            self._observe_fail_safe_transition(
                task=task,
                reason="recirculation_solution_low",
                source="node_event",
                next_stage="prepare_recirculation_solution_low_stop",
            )
            return StageOutcome(kind="transition", next_stage="prepare_recirculation_solution_low_stop")
        if recent_event_type == "EMERGENCY_STOP_ACTIVATED":
            await self._reconcile_recent_emergency_stop(
                task=task,
                plan=plan,
                now=now,
                expected={
                    "valve_solution_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
            )

        probe_outcome = await self._probe_irr_state_with_backoff(
            task=task, plan=plan, now=now,
            expected={
                "valve_solution_supply": True,
                "valve_solution_fill": True,
                "pump_main": True,
            },
            poll_delay_sec=int(runtime["level_poll_interval_sec"]),
            exhausted_outcome=StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_window_exhausted",
                stage_retry_count=task.workflow.stage_retry_count + 1,
            ),
        )
        if probe_outcome is not None:
            return probe_outcome

        if pending_manual_step == "prepare_recirculation_stop":
            _logger.info("prepare_recirculation_check: запрошена ручная остановка zone_id=%s", task.zone_id)
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_stop_to_ready",
            )
        if control_mode == "manual":
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime["level_poll_interval_sec"]),
            )

        if solution_min_guard_enabled:
            solution_min = await self._read_level(
                task=task,
                zone_id=task.zone_id,
                labels=runtime["solution_min_sensor_labels"],
                threshold=runtime["level_switch_on_threshold"],
                telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
                unavailable_error="two_tank_solution_min_level_unavailable",
                stale_error="two_tank_solution_min_level_stale",
                prefer_probe_snapshot=True,
            )
            if not solution_min["is_triggered"]:
                self._observe_fail_safe_transition(
                    task=task,
                    reason="recirculation_solution_low",
                    source="sensor",
                    next_stage="prepare_recirculation_solution_low_stop",
                )
                return StageOutcome(kind="transition", next_stage="prepare_recirculation_solution_low_stop")

        if await self._workflow_ready_reached(task=task, plan=plan, now=now, runtime=runtime):
            _logger.debug("prepare_recirculation_check: цели достигнуты zone_id=%s", task.zone_id)
            return StageOutcome(
                kind="transition",
                next_stage="prepare_recirculation_stop_to_ready",
            )

        # Target'ы не достигнуты: вход в коррекцию.
        _logger.info("prepare_recirculation_check: цели не достигнуты, переход в correction zone_id=%s", task.zone_id)
        # Сенсоры уже активны: их включил prepare_recirculation_start → sensor_mode_activate.
        corr = self._build_correction_state(
            task=task,
            runtime=runtime,
            sensors_already_active=True,
            return_stage_success=stage_def.on_corr_success or "prepare_recirculation_stop_to_ready",
            return_stage_fail=stage_def.on_corr_fail or "prepare_recirculation_window_exhausted",
        )
        return StageOutcome(kind="enter_correction", correction=corr)

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
        ec_max_attempts = self._required_correction_int(
            correction_cfg=correction_cfg,
            key="max_ec_correction_attempts",
        )
        ph_max_attempts = self._required_correction_int(
            correction_cfg=correction_cfg,
            key="max_ph_correction_attempts",
        )
        per_pid_attempt_limit = max(ec_max_attempts, ph_max_attempts)
        overall_attempt_limit = self._required_correction_int(
            correction_cfg=correction_cfg,
            key="prepare_recirculation_max_correction_attempts",
        )
        corr = CorrectionState.build_default(
            corr_step="corr_check" if sensors_already_active else "corr_activate",
            max_attempts=min(overall_attempt_limit, per_pid_attempt_limit),
            ec_max_attempts=ec_max_attempts,
            ph_max_attempts=ph_max_attempts,
            activated_here=not sensors_already_active,
            stabilization_sec=self._required_correction_int(
                correction_cfg=correction_cfg,
                key="stabilization_sec",
            ),
            return_stage_success=return_stage_success,
            return_stage_fail=return_stage_fail,
        )
        return replace(corr, **self._probe_snapshot_correction_fields(task=task))
