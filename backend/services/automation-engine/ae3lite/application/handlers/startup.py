"""StartupHandler: probe hardware, чтение уровня чистого бака и маршрут в первый fill-stage."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError

logger = logging.getLogger(__name__)

class StartupHandler(BaseStageHandler):
    """Обрабатывает stage ``startup``: probe, проверка уровня и условная маршрутизация."""

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        try:
            await self._probe_irr_state(
                task=task, plan=plan, now=now, expected={"pump_main": False},
            )
        except TaskExecutionError as exc:
            if exc.code != "irr_state_mismatch" or "pump_main" not in str(exc):
                raise
            await self._run_startup_safety_stop(task=task, plan=plan, now=now)
            await self._probe_irr_state(
                task=task, plan=plan, now=now, expected={"pump_main": False},
            )
        # Successful probe — clear manual_to_auto reconcile flag (если был выставлен
        # SetControlModeUseCase). См. CONTROL_MODES_SPEC §6.3 / §9.7.
        await self._clear_manual_to_auto_reconcile_flag(task=task)
        runtime = self._require_runtime_plan(plan=plan)

        clean_max = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime.clean_max_sensor_labels,
            threshold=runtime.level_switch_on_threshold,
            telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
            unavailable_error="two_tank_clean_level_unavailable",
            stale_error="two_tank_clean_level_stale",
        )
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "")
        control_mode = str(getattr(task.workflow, "control_mode", "") or "auto").strip().lower()

        if control_mode in ("manual", "semi"):
            if clean_max["is_triggered"] and pending_manual_step == "solution_fill_start":
                await self._check_sensor_consistency(
                    task=task,
                    runtime=runtime,
                    min_labels_key="clean_min_sensor_labels",
                    min_unavailable_error="two_tank_clean_min_level_unavailable",
                    min_stale_error="two_tank_clean_min_level_stale",
                )
                return StageOutcome(kind="transition", next_stage="solution_fill_start")
            # (b) force: agronomist явно пропускает clean_max guard. Без sensor
            # consistency check — кнопка уже эквивалентна "я знаю что делаю".
            # См. CONTROL_MODES_SPEC §5.1.
            if pending_manual_step == "force_solution_fill_start" and control_mode == "manual":
                logger.warning(
                    "startup: force_solution_fill_start от agronomist в manual zone_id=%s clean_max_is_triggered=%s",
                    task.zone_id,
                    bool(clean_max["is_triggered"]),
                )
                return StageOutcome(kind="transition", next_stage="solution_fill_start")
            if not clean_max["is_triggered"] and pending_manual_step == "clean_fill_start":
                return StageOutcome(
                    kind="transition",
                    next_stage="clean_fill_start",
                    clean_fill_cycle=1,
                )
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime.level_poll_interval_sec),
            )

        if clean_max["is_triggered"]:
            # Бак чистой воды полон: проверить согласованность и перейти к solution fill
            await self._check_sensor_consistency(
                task=task,
                runtime=runtime,
                min_labels_key="clean_min_sensor_labels",
                min_unavailable_error="two_tank_clean_min_level_unavailable",
                min_stale_error="two_tank_clean_min_level_stale",
            )
            return StageOutcome(kind="transition", next_stage="solution_fill_start")

        # Бак чистой воды не заполнен: запустить цикл clean fill
        return StageOutcome(
            kind="transition",
            next_stage="clean_fill_start",
            clean_fill_cycle=1,
        )

    async def _run_startup_safety_stop(self, *, task: Any, plan: Any, now: datetime) -> None:
        safety_plan = tuple(plan.named_plans.get("solution_fill_stop", ()))
        if not safety_plan:
            safety_plan = tuple(plan.named_plans.get("clean_fill_stop", ()))
        if not safety_plan:
            raise TaskExecutionError(
                "irr_state_mismatch",
                "Состояние IRR-ноды по pump_main не совпало, и safety stop plan не настроен",
            )

        result = await self._command_gateway.run_batch(
            task=task,
            commands=safety_plan,
            now=now,
        )
        if not result["success"]:
            raise TaskExecutionError(
                str(result["error_code"]),
                str(result["error_message"]),
            )

    async def _clear_manual_to_auto_reconcile_flag(self, *, task: Any) -> None:
        """Очищает `zones.settings.manual_to_auto_reconcile_pending` после
        successful probe в startup. См. CONTROL_MODES_SPEC.md §6.3 / §9.7.

        Best-effort: если запись не удалась — не блокируем стартап, только
        warning. Флаг чисто диагностический (UI badge), он не управляет
        runtime поведением.
        """
        try:
            from common.db import execute  # local import to keep handler module light

            await execute(
                """
                UPDATE zones
                SET settings = COALESCE(settings, '{}'::jsonb) - 'manual_to_auto_reconcile_pending'
                                                              - 'manual_to_auto_reconcile_requested_at',
                    updated_at = NOW()
                WHERE id = $1
                  AND settings ? 'manual_to_auto_reconcile_pending'
                """,
                int(getattr(task, "zone_id", 0) or 0),
            )
        except Exception:
            logger.warning(
                "AE3 startup: не смог очистить manual_to_auto_reconcile_pending для zone_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                exc_info=True,
            )
