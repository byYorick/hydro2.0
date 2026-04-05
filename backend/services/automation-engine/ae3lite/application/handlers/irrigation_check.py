"""Handler runtime-проверок во время полива."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import (
    IRRIGATION_CORRECTION_ENTERED,
    IRRIGATION_DURATION,
    IRRIGATION_REPLAY,
    IRRIGATION_SOLUTION_MIN,
)
from common.biz_alerts import send_biz_alert
from common.db import create_zone_event


_logger = logging.getLogger(__name__)


class IrrigationCheckHandler(BaseStageHandler):
    def __init__(self, *, runtime_monitor: Any, command_gateway: Any, task_repository: Any) -> None:
        super().__init__(runtime_monitor=runtime_monitor, command_gateway=command_gateway)
        self._task_repository = task_repository

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        runtime = plan.runtime if hasattr(plan, "runtime") else {}
        control_mode = str(getattr(task.workflow, "control_mode", "") or "auto").strip().lower()
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "")
        topology = str(getattr(task, "topology", "") or "")
        deadline = task.workflow.stage_deadline_at

        def _observe_duration(stop_reason: str) -> None:
            entered = getattr(task.workflow, "stage_entered_at", None)
            if isinstance(entered, datetime):
                now_cmp = now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo is not None else now
                entered_cmp = entered.astimezone(timezone.utc).replace(tzinfo=None) if entered.tzinfo is not None else entered
                duration = (now_cmp - entered_cmp).total_seconds()
                IRRIGATION_DURATION.labels(topology=topology, stop_reason=stop_reason).observe(max(0.0, duration))

        if pending_manual_step == "irrigation_stop":
            _observe_duration("manual")
            return StageOutcome(kind="transition", next_stage="irrigation_stop_to_ready")

        if self._deadline_reached(now=now, deadline=deadline):
            if await self._targets_reached(task=task, plan=plan, now=now):
                _observe_duration("ready")
                return StageOutcome(kind="transition", next_stage="irrigation_stop_to_ready")
            _observe_duration("recovery")
            return StageOutcome(kind="transition", next_stage="irrigation_stop_to_recovery")

        await self._probe_irr_state(
            task=task,
            plan=plan,
            now=now,
            expected={
                "valve_solution_supply": True,
                "valve_irrigation": True,
                "pump_main": True,
            },
        )

        if control_mode == "manual":
            return StageOutcome(kind="poll", due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)))

        safety = runtime.get("irrigation_safety") if isinstance(runtime.get("irrigation_safety"), dict) else {}
        recovery = runtime.get("irrigation_recovery") if isinstance(runtime.get("irrigation_recovery"), dict) else {}
        if bool(safety.get("stop_on_solution_min", True)):
            solution_min = await self._read_level(
                task=task,
                zone_id=task.zone_id,
                labels=runtime["solution_min_sensor_labels"],
                threshold=runtime["level_switch_on_threshold"],
                telemetry_max_age_sec=int(runtime["telemetry_max_age_sec"]),
                unavailable_error="two_tank_solution_min_level_unavailable",
                stale_error="two_tank_solution_min_level_stale",
            )
            if solution_min["is_triggered"]:
                IRRIGATION_SOLUTION_MIN.labels(topology=topology).inc()
                try:
                    await create_zone_event(
                        int(task.zone_id),
                        "IRRIGATION_SOLUTION_MIN_DETECTED",
                        {
                            "task_id": int(getattr(task, "id", 0) or 0),
                            "stage": "irrigation_check",
                            "topology": topology,
                        },
                    )
                except Exception:
                    _logger.warning(
                        "AE3 не смог записать IRRIGATION_SOLUTION_MIN_DETECTED zone_id=%s task_id=%s",
                        int(getattr(task, "zone_id", 0) or 0),
                        int(getattr(task, "id", 0) or 0),
                        exc_info=True,
                    )
                try:
                    await send_biz_alert(
                        code="biz_irrigation_solution_min",
                        alert_type="AE3 Irrigation Solution Min",
                        message="Во время полива сработал нижний датчик уровня раствора.",
                        severity="warning",
                        zone_id=int(task.zone_id),
                        details={
                            "task_id": int(getattr(task, "id", 0) or 0),
                            "topology": topology,
                            "stage": "irrigation_check",
                            "irrigation_replay_count": int(getattr(task, "irrigation_replay_count", 0) or 0),
                        },
                        scope_parts=("stage:irrigation_check",),
                    )
                except Exception:
                    _logger.warning(
                        "AE3 не смог отправить alert biz_irrigation_solution_min zone_id=%s task_id=%s",
                        int(getattr(task, "zone_id", 0) or 0),
                        int(getattr(task, "id", 0) or 0),
                        exc_info=True,
                    )
                max_replays = int(recovery.get("max_setup_replays") or 0)
                next_replay_count = int(getattr(task, "irrigation_replay_count", 0) or 0) + 1
                if next_replay_count > max_replays:
                    try:
                        await send_biz_alert(
                            code="biz_irrigation_replay_exhausted",
                            alert_type="AE3 Irrigation Replay Exhausted",
                            message="Исчерпан бюджет повторов после повторных срабатываний нижнего уровня раствора.",
                            severity="error",
                            zone_id=int(task.zone_id),
                            details={
                                "task_id": int(getattr(task, "id", 0) or 0),
                                "topology": topology,
                                "stage": "irrigation_check",
                                "next_replay_count": next_replay_count,
                                "max_setup_replays": max_replays,
                            },
                            scope_parts=("stage:irrigation_check",),
                        )
                    except Exception:
                        _logger.warning(
                            "AE3 не смог отправить alert biz_irrigation_replay_exhausted zone_id=%s task_id=%s",
                            int(getattr(task, "zone_id", 0) or 0),
                            int(getattr(task, "id", 0) or 0),
                            exc_info=True,
                        )
                    return StageOutcome(
                        kind="fail",
                        error_code="irrigation_solution_min_replay_exhausted",
                        error_message="Нижний уровень раствора снова сработал после исчерпания бюджета повторов setup",
                    )
                updated = await self._task_repository.update_irrigation_runtime(
                    task_id=int(task.id),
                    owner=str(task.claimed_by or ""),
                    now=now,
                    irrigation_replay_count=next_replay_count,
                )
                if updated is None:
                    raise TaskExecutionError("irrigation_replay_persist_failed", "Не удалось сохранить счётчик повторов полива")
                IRRIGATION_REPLAY.labels(topology=topology).inc()
                _observe_duration("setup")
                return StageOutcome(kind="transition", next_stage="irrigation_stop_to_setup")

        execution = (
            runtime.get("irrigation_execution")
            if isinstance(runtime.get("irrigation_execution"), dict)
            else {}
        )
        correction_enabled = bool(execution.get("correction_during_irrigation", True))
        if correction_enabled:
            stage_retry_count = int(getattr(task.workflow, "stage_retry_count", 0) or 0)
            if stage_retry_count <= 0 and not await self._targets_reached(task=task, plan=plan, now=now):
                correction_cfg = self._correction_config_for_task(task=task, runtime=runtime)
                ec_max_attempts = int(correction_cfg.get("max_ec_correction_attempts", 5))
                ph_max_attempts = int(correction_cfg.get("max_ph_correction_attempts", 5))
                corr = CorrectionState(
                    corr_step="corr_check",
                    attempt=0,
                    max_attempts=max(ec_max_attempts, ph_max_attempts),
                    ec_attempt=0,
                    ec_max_attempts=ec_max_attempts,
                    ph_attempt=0,
                    ph_max_attempts=ph_max_attempts,
                    activated_here=False,  # irrigation_start already ran sensor_mode_activate
                    stabilization_sec=int(correction_cfg.get("stabilization_sec", 60)),
                    return_stage_success=stage_def.on_corr_success or "irrigation_check",
                    return_stage_fail=stage_def.on_corr_fail or "irrigation_check",
                    outcome_success=None,
                    needs_ec=False,
                    ec_node_uid=None,
                    ec_channel=None,
                    ec_duration_ms=None,
                    needs_ph_up=False,
                    needs_ph_down=False,
                    ph_node_uid=None,
                    ph_channel=None,
                    ph_duration_ms=None,
                    wait_until=None,
                    limit_policy_logged=False,
                )
                IRRIGATION_CORRECTION_ENTERED.labels(topology=topology).inc()
                try:
                    await create_zone_event(
                        int(task.zone_id),
                        "IRRIGATION_CORRECTION_STARTED",
                        {
                            "task_id": int(getattr(task, "id", 0) or 0),
                            "stage": "irrigation_check",
                            "topology": topology,
                        },
                    )
                except Exception:
                    _logger.warning(
                        "AE3 не смог записать IRRIGATION_CORRECTION_STARTED zone_id=%s task_id=%s",
                        int(getattr(task, "zone_id", 0) or 0),
                        int(getattr(task, "id", 0) or 0),
                        exc_info=True,
                    )
                return StageOutcome(kind="enter_correction", correction=corr)

        return StageOutcome(kind="poll", due_delay_sec=int(runtime.get("level_poll_interval_sec", 10)))
