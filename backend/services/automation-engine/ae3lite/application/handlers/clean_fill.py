"""CleanFillCheckHandler: polling уровня, дедлайна и логики повторов."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.infrastructure.metrics import STAGE_DEADLINE_EXCEEDED
from common.biz_alerts import send_biz_alert

_logger = logging.getLogger(__name__)


class CleanFillCheckHandler(BaseStageHandler):
    """Обрабатывает ``clean_fill_check``: опрашивает датчик уровня, дедлайн и повторы.

    Возможные исходы:
    1. Бак полон → переход в ``clean_fill_stop_to_solution``
    2. Дедлайн превышен и повторы ещё доступны → переход в ``clean_fill_retry_stop``
    3. Дедлайн превышен и повторы исчерпаны → переход в ``clean_fill_timeout_stop``
    4. Заполнение ещё продолжается → ``poll`` с повторной постановкой в очередь
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

        if pending_manual_step == "clean_fill_stop":
            _logger.info("clean_fill_check: запрошена ручная остановка zone_id=%s", task.zone_id)
            return StageOutcome(kind="transition", next_stage="clean_fill_stop_to_solution")
        if control_mode == "manual":
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)),
            )

        clean_max = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime["clean_max_sensor_labels"],
            threshold=runtime["level_switch_on_threshold"],
            telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
            unavailable_error="two_tank_clean_level_unavailable",
            stale_error="two_tank_clean_level_stale",
            stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
        )

        if clean_max["is_triggered"]:
            # Бак полон: проверить согласованность датчиков
            await self._check_sensor_consistency(
                task=task,
                runtime=runtime,
                min_labels_key="clean_min_sensor_labels",
                min_unavailable_error="two_tank_clean_min_level_unavailable",
                min_stale_error="two_tank_clean_min_level_stale",
            )
            _logger.debug("clean_fill_check: бак чистой воды заполнен, выполняется переход zone_id=%s", task.zone_id)
            return StageOutcome(kind="transition", next_stage="clean_fill_stop_to_solution")

        # Проверка дедлайна
        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            cycle = max(1, task.workflow.clean_fill_cycle)
            retry_limit = 1 + int(runtime.get("clean_fill_retry_cycles", 0))
            if cycle < retry_limit:
                # Повтор: увеличить цикл, новый дедлайн выставит WorkflowRouter
                _logger.info(
                    "clean_fill_check: deadline exceeded, retrying cycle=%s/%s zone_id=%s",
                    cycle + 1, retry_limit, task.zone_id,
                )
                return StageOutcome(
                    kind="transition",
                    next_stage="clean_fill_retry_stop",
                    clean_fill_cycle=cycle + 1,
                )
            # Лимит повторов исчерпан: терминальный timeout
            _logger.warning(
                "clean_fill_check: deadline exceeded, max retries reached cycle=%s zone_id=%s",
                cycle, task.zone_id,
            )
            STAGE_DEADLINE_EXCEEDED.labels(
                topology=str(getattr(task, "topology", "") or ""),
                stage="clean_fill_check",
            ).inc()
            try:
                await send_biz_alert(
                    code="biz_clean_fill_timeout",
                    alert_type="AE3 Clean Fill Timeout",
                    message="Превышено время заполнения бака чистой водой после всех циклов повтора.",
                    severity="warning",
                    zone_id=int(task.zone_id),
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "cycle": cycle,
                        "stage": "clean_fill_check",
                        "component": "handler:clean_fill_check",
                        "retry_limit": retry_limit,
                        "message": "Превышено время заполнения бака чистой водой после всех циклов повтора; проверьте подачу воды.",
                    },
                    scope_parts=("stage:clean_fill_check",),
                )
            except Exception:
                    _logger.warning("Не удалось отправить alert clean_fill_timeout zone_id=%s", task.zone_id)
            return StageOutcome(kind="transition", next_stage="clean_fill_timeout_stop")

        # Заполнение ещё идёт: повторный poll
        return StageOutcome(
            kind="poll",
            due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)),
        )
