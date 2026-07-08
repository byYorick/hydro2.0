"""Solution topup handlers: автодолив бака раствора в фазе ready."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.application.level_monitor import solution_topup_need_active
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import STAGE_DEADLINE_EXCEEDED
from common.biz_alerts import send_biz_alert
from common.db import create_zone_event

_logger = logging.getLogger(__name__)


class SolutionTopupGuardHandler(BaseStageHandler):
    """Проверяет готовность зоны и необходимость долива перед стартом."""

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
        workflow_phase = str(
            getattr(runtime, "zone_workflow_phase", None)
            or getattr(task, "workflow_phase", "")
            or "",
        ).strip().lower()
        if workflow_phase not in {"ready"}:
            return StageOutcome(
                kind="fail",
                error_code="start_solution_topup_not_ready",
                error_message="Автодолив доступен только в workflow_phase=ready",
            )

        if not bool(getattr(runtime, "solution_topup_enabled", True)):
            return StageOutcome(kind="transition", next_stage="solution_topup_complete")

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
        solution_max = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime.solution_max_sensor_labels,
            threshold=runtime.level_switch_on_threshold,
            telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
            unavailable_error="two_tank_solution_level_unavailable",
            stale_error="two_tank_solution_level_stale",
            stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
            prefer_probe_snapshot=True,
        )

        if not solution_topup_need_active(
            solution_min_triggered=bool(solution_min.get("is_triggered")),
            solution_max_triggered=bool(solution_max.get("is_triggered")),
        ):
            return StageOutcome(kind="transition", next_stage="solution_topup_complete")

        mode = "normal"
        intent_meta = getattr(task, "intent_meta", None)
        if isinstance(intent_meta, Mapping):
            payload = intent_meta.get("intent_payload")
            if isinstance(payload, Mapping):
                mode = str(payload.get("mode") or "normal").strip().lower()
        if mode != "force":
            cooldown_sec = int(getattr(runtime, "solution_topup_cooldown_sec", 300) or 300)
            if await self._cooldown_active(task=task, now=now, cooldown_sec=max(0, cooldown_sec)):
                return StageOutcome(
                    kind="fail",
                    error_code="start_solution_topup_cooldown_active",
                    error_message="Cooldown после предыдущего solution_topup ещё не истёк",
                )

        return StageOutcome(kind="transition", next_stage="solution_topup_start")

    async def _cooldown_active(self, *, task: Any, now: datetime, cooldown_sec: int) -> bool:
        if cooldown_sec <= 0:
            return False
        from common.db import fetch

        rows = await fetch(
            """
            SELECT created_at
            FROM zone_events
            WHERE zone_id = $1
              AND type IN (
                    'SOLUTION_TOPUP_DONE',
                    'SOLUTION_TOPUP_TIMEOUT',
                    'SOLUTION_TOPUP_SOURCE_EMPTY',
                    'SOLUTION_TOPUP_LEAK_DETECTED'
              )
            ORDER BY created_at DESC
            LIMIT 1
            """,
            int(task.zone_id),
        )
        if not rows:
            return False
        created_at = rows[0].get("created_at")
        if not isinstance(created_at, datetime):
            return False
        anchor = created_at.replace(tzinfo=None) if created_at.tzinfo else created_at
        now_naive = now.replace(tzinfo=None) if now.tzinfo else now
        return anchor + timedelta(seconds=cooldown_sec) > now_naive


class SolutionTopupCheckHandler(BaseStageHandler):
    """Poll-loop долива: уровень, fail-safe и дедлайн (без in-flow correction)."""

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
        fail_safe_guards = runtime.fail_safe_guards
        recent_storage_event = await self._read_recent_storage_event(
            task=task,
            event_types=(
                "SOLUTION_TOPUP_SOURCE_EMPTY",
                "SOLUTION_TOPUP_LEAK_DETECTED",
                "SOLUTION_TOPUP_COMPLETED",
                "EMERGENCY_STOP_ACTIVATED",
            ),
            max_age_sec=86400,
        )
        recent_event_type = str((recent_storage_event or {}).get("event_type") or "").strip().upper()
        if recent_event_type == "SOLUTION_TOPUP_SOURCE_EMPTY":
            return StageOutcome(kind="transition", next_stage="solution_topup_source_empty_stop")
        if recent_event_type == "SOLUTION_TOPUP_LEAK_DETECTED":
            return StageOutcome(kind="transition", next_stage="solution_topup_leak_stop")
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
        if recent_event_type == "SOLUTION_TOPUP_COMPLETED":
            return StageOutcome(kind="transition", next_stage="solution_topup_stop")

        try:
            await self._probe_irr_state(
                task=task,
                plan=plan,
                now=now,
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
                    event_types=("SOLUTION_TOPUP_COMPLETED",),
                    max_age_sec=86400,
                )
                raced_event_type = str((raced_completion_event or {}).get("event_type") or "").strip().upper()
                if raced_event_type == "SOLUTION_TOPUP_COMPLETED":
                    return StageOutcome(kind="transition", next_stage="solution_topup_stop")
            raise

        clean_min_check_delay_ms = int(
            getattr(fail_safe_guards, "solution_topup_clean_min_check_delay_ms", None)
            or fail_safe_guards.solution_fill_clean_min_check_delay_ms
        )
        if self._stage_elapsed_ms(task=task, now=now) >= max(0, clean_min_check_delay_ms):
            clean_min = await self._read_level(
                task=task,
                zone_id=task.zone_id,
                labels=runtime.clean_min_sensor_labels,
                threshold=runtime.level_switch_on_threshold,
                telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
                unavailable_error="two_tank_clean_min_level_unavailable",
                stale_error="two_tank_clean_min_level_stale",
                stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
                prefer_probe_snapshot=True,
            )
            if not clean_min["is_triggered"]:
                self._observe_fail_safe_transition(
                    task=task,
                    reason="solution_topup_source_empty",
                    source="sensor",
                    next_stage="solution_topup_source_empty_stop",
                )
                return StageOutcome(kind="transition", next_stage="solution_topup_source_empty_stop")

        solution_min_check_delay_ms = int(
            getattr(fail_safe_guards, "solution_topup_solution_min_check_delay_ms", None)
            or fail_safe_guards.solution_fill_solution_min_check_delay_ms
        )
        if self._stage_elapsed_ms(task=task, now=now) >= max(0, solution_min_check_delay_ms):
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
                self._observe_fail_safe_transition(
                    task=task,
                    reason="solution_topup_leak_detected",
                    source="sensor",
                    next_stage="solution_topup_leak_stop",
                )
                return StageOutcome(kind="transition", next_stage="solution_topup_leak_stop")

        solution_max = await self._read_level(
            task=task,
            zone_id=task.zone_id,
            labels=runtime.solution_max_sensor_labels,
            threshold=runtime.level_switch_on_threshold,
            telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
            unavailable_error="two_tank_solution_level_unavailable",
            stale_error="two_tank_solution_level_stale",
            stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
            prefer_probe_snapshot=True,
        )
        if solution_max["is_triggered"]:
            await self._check_sensor_consistency(
                task=task,
                runtime=runtime,
                min_labels_key="solution_min_sensor_labels",
                min_unavailable_error="two_tank_solution_min_level_unavailable",
                min_stale_error="two_tank_solution_min_level_stale",
                stale_recheck_delay_sec=self._STALE_RECHECK_DELAY_SEC,
                prefer_probe_snapshot=True,
            )
            return StageOutcome(kind="transition", next_stage="solution_topup_stop")

        deadline = task.workflow.stage_deadline_at
        if self._deadline_reached(now=now, deadline=deadline):
            _logger.warning(
                "solution_topup_check: дедлайн превышен zone_id=%s",
                task.zone_id,
            )
            STAGE_DEADLINE_EXCEEDED.labels(
                topology=str(getattr(task, "topology", "") or ""),
                stage="solution_topup_check",
            ).inc()
            try:
                await send_biz_alert(
                    code="biz_solution_topup_timeout",
                    alert_type="AE3 Solution Topup Timeout",
                    message="Превышено время автодолива бака раствора.",
                    severity="warning",
                    zone_id=int(task.zone_id),
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "topology": str(getattr(task, "topology", "") or ""),
                        "stage": "solution_topup_check",
                        "component": "handler:solution_topup_check",
                    },
                    scope_parts=("stage:solution_topup_check",),
                )
            except Exception:
                _logger.warning(
                    "Не удалось отправить alert biz_solution_topup_timeout zone_id=%s task_id=%s",
                    task.zone_id,
                    getattr(task, "id", None),
                    exc_info=True,
                )
            return StageOutcome(kind="transition", next_stage="solution_topup_timeout_stop")

        return StageOutcome(
            kind="poll",
            due_delay_sec=int(runtime.level_poll_interval_sec),
        )


class SolutionTopupCompleteHandler(BaseStageHandler):
    """Завершает task после успешного долива и пишет SOLUTION_TOPUP_DONE."""

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
                "SOLUTION_TOPUP_DONE",
                {
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "zone_id": int(getattr(task, "zone_id", 0) or 0),
                    "stage": "solution_topup_complete",
                },
            )
        except Exception:
            _logger.warning(
                "solution_topup_complete: не удалось записать SOLUTION_TOPUP_DONE zone_id=%s",
                getattr(task, "zone_id", None),
                exc_info=True,
            )
        return StageOutcome(kind="complete")
