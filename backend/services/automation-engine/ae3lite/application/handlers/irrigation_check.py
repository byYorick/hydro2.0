"""Handler runtime-проверок во время полива."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler, _utc_naive_dt
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
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
    _STALE_RECHECK_DELAY_SEC = 0.25

    def __init__(
        self, *,
        runtime_monitor: Any, command_gateway: Any, task_repository: Any,
        live_reload_enabled: bool = False,
    ) -> None:
        super().__init__(
            runtime_monitor=runtime_monitor,
            command_gateway=command_gateway,
            live_reload_enabled=live_reload_enabled,
        )
        self._task_repository = task_repository

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
        topology = str(getattr(task, "topology", "") or "")
        deadline = task.workflow.stage_deadline_at
        recovery = runtime.get("irrigation_recovery") or {}
        safety = runtime["irrigation_safety"]
        solution_min_guard_enabled = bool(safety["stop_on_solution_min"])
        expected_irrigation_state = {
            "valve_solution_supply": True,
            "valve_irrigation": True,
            "pump_main": True,
        }
        recent_storage_event = await self._read_recent_storage_event(
            task=task,
            event_types=("IRRIGATION_SOLUTION_LOW", "EMERGENCY_STOP_ACTIVATED"),
            max_age_sec=86400,
        )
        recent_event_type = str((recent_storage_event or {}).get("event_type") or "").strip().upper()

        def _observe_duration(stop_reason: str) -> None:
            # Audit F5: delegate tz normalization to the shared _utc_naive_dt
            # helper instead of repeating the inline astimezone+replace dance
            # twice. The helper handles tz-aware and tz-naive inputs uniformly,
            # and `max(0.0, duration)` guards against negative durations from
            # clock skew (prior tick after clock fix, tz-naive stage_entered_at
            # persisted with a different wall clock than `now`).
            entered = getattr(task.workflow, "stage_entered_at", None)
            if not isinstance(entered, datetime):
                return
            duration = (_utc_naive_dt(now) - _utc_naive_dt(entered)).total_seconds()
            IRRIGATION_DURATION.labels(topology=topology, stop_reason=stop_reason).observe(
                max(0.0, duration)
            )

        if pending_manual_step == "irrigation_stop":
            _observe_duration("manual")
            return StageOutcome(kind="transition", next_stage="irrigation_stop_to_ready")

        if self._deadline_reached(now=now, deadline=deadline):
            if await self._targets_reached(task=task, plan=plan, now=now, runtime=runtime):
                _observe_duration("ready")
                return StageOutcome(kind="transition", next_stage="irrigation_stop_to_ready")
            _observe_duration("recovery")
            return StageOutcome(kind="transition", next_stage="irrigation_stop_to_recovery")

        probe_verified = False
        if recent_event_type == "IRRIGATION_SOLUTION_LOW" and solution_min_guard_enabled:
            if self._recent_solution_low_event_confirms_active_low(
                event=recent_storage_event,
                expected=expected_irrigation_state,
            ):
                return await self._solution_min_low_outcome(
                    task=task,
                    topology=topology,
                    recovery=recovery,
                    now=now,
                    observe_duration=_observe_duration,
                    source="node_event",
                )
            try:
                await self._probe_irr_state(
                    task=task,
                    plan=plan,
                    now=now,
                    expected=expected_irrigation_state,
                )
                probe_verified = True
            except TaskExecutionError:
                return await self._solution_min_low_outcome(
                    task=task,
                    topology=topology,
                    recovery=recovery,
                    now=now,
                    observe_duration=_observe_duration,
                    source="node_event",
                )
            _logger.info(
                "irrigation_check: игнорирую stale IRRIGATION_SOLUTION_LOW event zone_id=%s task_id=%s",
                task.zone_id,
                getattr(task, "id", None),
            )
        if recent_event_type == "EMERGENCY_STOP_ACTIVATED":
            await self._reconcile_recent_emergency_stop(
                task=task,
                plan=plan,
                now=now,
                expected=expected_irrigation_state,
            )

        if not probe_verified:
            probe_outcome = await self._probe_irr_state_with_backoff(
                task=task,
                plan=plan,
                now=now,
                expected=expected_irrigation_state,
                poll_delay_sec=int(runtime["level_poll_interval_sec"]),
                exhausted_outcome=StageOutcome(
                    kind="transition",
                    next_stage="irrigation_stop_to_recovery",
                ),
            )
            if probe_outcome is not None:
                return probe_outcome

        if control_mode == "manual":
            return StageOutcome(kind="poll", due_delay_sec=int(runtime["level_poll_interval_sec"]))

        if solution_min_guard_enabled:
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
                return await self._solution_min_low_outcome(
                    task=task,
                    topology=topology,
                    recovery=recovery,
                    now=now,
                    observe_duration=_observe_duration,
                    source="sensor",
                )

        execution = runtime["irrigation_execution"]
        correction_enabled = bool(execution["correction_during_irrigation"])
        if correction_enabled:
            stage_retry_count = int(getattr(task.workflow, "stage_retry_count", 0) or 0)
            if stage_retry_count <= 0 and not await self._targets_reached(task=task, plan=plan, now=now, runtime=runtime):
                correction_cfg = self._correction_config_for_task(task=task, runtime=runtime)
                ec_max_attempts = int(correction_cfg.get("max_ec_correction_attempts", 5))
                ph_max_attempts = int(correction_cfg.get("max_ph_correction_attempts", 5))
                corr = CorrectionState.build_default(
                    corr_step="corr_check",
                    max_attempts=max(ec_max_attempts, ph_max_attempts),
                    ec_max_attempts=ec_max_attempts,
                    ph_max_attempts=ph_max_attempts,
                    activated_here=False,  # irrigation_start already ran sensor_mode_activate
                    stabilization_sec=int(correction_cfg.get("stabilization_sec", 60)),
                    return_stage_success=stage_def.on_corr_success or "irrigation_check",
                    return_stage_fail=stage_def.on_corr_fail or "irrigation_check",
                )
                corr = replace(corr, **self._probe_snapshot_correction_fields(task=task))
                IRRIGATION_CORRECTION_ENTERED.labels(topology=topology).inc()
                try:
                    details = {
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "stage": "irrigation_check",
                        "current_stage": "irrigation_check",
                        "workflow_phase": str(getattr(task.workflow, "workflow_phase", "") or ""),
                        "topology": topology,
                    }
                    snapshot_ctx = self._probe_snapshot_context(task=task)
                    if isinstance(snapshot_ctx, Mapping):
                        snapshot_event_id = snapshot_ctx.get("snapshot_event_id")
                        if snapshot_event_id is not None:
                            details.setdefault("caused_by_event_id", snapshot_event_id)
                        details.update(snapshot_ctx)
                    await create_zone_event(
                        int(task.zone_id),
                        "IRRIGATION_CORRECTION_STARTED",
                        with_runtime_event_contract(details),
                    )
                except Exception:
                    _logger.warning(
                        "AE3 не смог записать IRRIGATION_CORRECTION_STARTED zone_id=%s task_id=%s",
                        int(getattr(task, "zone_id", 0) or 0),
                        int(getattr(task, "id", 0) or 0),
                        exc_info=True,
                    )
                return StageOutcome(kind="enter_correction", correction=corr)

        return StageOutcome(kind="poll", due_delay_sec=int(runtime["level_poll_interval_sec"]))

    def _recent_solution_low_event_confirms_active_low(
        self,
        *,
        event: Mapping[str, Any] | None,
        expected: Mapping[str, bool],
    ) -> bool:
        """Decide whether a recorded storage event confirms an actively-low level.

        Audit F11: the fallback chain used for ``level_min_state`` is
        intentional, not redundant. Older MQTT event payloads wrote the
        level-switch flags into the top-level ``state`` key, newer ones moved
        them into the ``snapshot`` sub-dict. We prefer ``state`` because it
        reflects the instantaneous reading, and fall back to ``snapshot`` so
        events serialised by the legacy path still trigger the low-level
        branch. If neither carries the flag we treat it as "not confirmed"
        (the explicit ``False`` return below).
        """
        payload = self._storage_event_payload(event)
        snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), Mapping) else None
        state = payload.get("state") if isinstance(payload.get("state"), Mapping) else None
        if not isinstance(snapshot, Mapping):
            return False
        for key, value in expected.items():
            if key not in snapshot or bool(snapshot.get(key)) != bool(value):
                return False
        # Preferred source: live state block. Fallback: snapshot block.
        level_min_state = self._event_bool(state, ("level_solution_min", "solution_level_min"))
        if level_min_state is None:
            level_min_state = self._event_bool(snapshot, ("level_solution_min", "solution_level_min"))
        # runtime трактует low-condition как деактивированный нижний switch.
        # If neither payload shape carried the flag at all, level_min_state
        # remains None and we return False — "not confirmed".
        return level_min_state is False

    def _event_bool(
        self,
        mapping: Mapping[str, Any] | None,
        keys: tuple[str, ...],
    ) -> bool | None:
        if not isinstance(mapping, Mapping):
            return None
        for key in keys:
            if key in mapping:
                return bool(mapping.get(key))
        return None

    async def _solution_min_low_outcome(
        self,
        *,
        task: Any,
        topology: str,
        recovery: dict[str, Any],
        now: datetime,
        observe_duration: Any,
        source: str,
    ) -> StageOutcome:
        self._observe_fail_safe_transition(
            task=task,
            reason="irrigation_solution_low",
            source=source,
            next_stage="irrigation_stop_to_setup",
        )
        IRRIGATION_SOLUTION_MIN.labels(topology=topology).inc()
        # Audit F2 fix: compute and check the replay-budget BEFORE any alert or
        # event emission. Order of operations:
        #   1. Detect exhausted → persist+fail immediately
        #   2. Persist incremented counter
        #   3. Only then fire non-critical alerts and observability events
        # Previously alerts were sent before the counter was persisted, so a
        # mid-flow crash (after alert, before persist) would leave the task with
        # stale counter and re-enter the same branch on the next tick — a
        # runaway loop that manifested as repeated solution_min alerts without
        # the replay budget ever actually decrementing.
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

        # Persist the incremented counter BEFORE emitting observability. If the
        # persist fails we raise and never send alerts (repository error must
        # not be masked). If alerts later fail, the counter is already safely
        # recorded — next tick sees the updated value and will not loop.
        updated = await self._task_repository.update_irrigation_runtime(
            task_id=int(task.id),
            owner=str(task.claimed_by or ""),
            now=now,
            irrigation_replay_count=next_replay_count,
        )
        if updated is None:
            raise TaskExecutionError("irrigation_replay_persist_failed", "Не удалось сохранить счётчик повторов полива")

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
                    "irrigation_replay_count": next_replay_count,
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

        IRRIGATION_REPLAY.labels(topology=topology).inc()
        observe_duration("setup")
        return StageOutcome(
            kind="transition",
            next_stage="irrigation_stop_to_setup",
            task_override=updated,
        )
