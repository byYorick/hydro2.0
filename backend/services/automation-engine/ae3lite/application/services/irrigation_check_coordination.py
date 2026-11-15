"""IrrigationCheckHandler coordination: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import _utc_naive_dt
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError


@dataclass(frozen=True)
class IrrigationCheckCoordinationPorts:
    stale_recheck_delay_sec: Callable[[], Any]
    checkpoint: Callable[[], Any]
    deadline_reached: Callable[[], Any]
    handle_control_mode_flow_path_interrupt: Callable[[], Any]
    load_irrigation_nutrient_baseline: Callable[..., Awaitable[Any]]
    maybe_stop_continuous_pump_after_duration: Callable[..., Awaitable[Any]]
    probe_irr_state: Callable[[], Any]
    probe_irr_state_with_backoff: Callable[[], Any]
    probe_snapshot_context: Callable[[], Any]
    probe_snapshot_correction_fields: Callable[[], Any]
    read_level: Callable[[], Any]
    read_recent_storage_event: Callable[[], Any]
    recent_solution_low_event_confirms_active_low: Callable[..., Any]
    reconcile_recent_emergency_stop: Callable[[], Any]
    record_deadline_target_outcome: Callable[[], Any]
    require_runtime_plan: Callable[[], Any]
    resolve_expected_irrigation_state: Callable[..., Any]
    runtime_config: Callable[[], Any]
    solution_min_low_outcome: Callable[..., Awaitable[Any]]
    target_outcome_on_deadline: Callable[[], Any]
    targets_reached: Callable[[], Any]
    global_irrigation_correction_entered: Callable[..., Any]
    global_irrigation_duration: Callable[..., Any]
    global_logger: Callable[..., Any]
    global_create_zone_event: Callable[..., Any]


class IrrigationCheckCoordination:
    def __init__(self, ports: IrrigationCheckCoordinationPorts) -> None:
        self._ports = ports

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        plan = await self._ports.checkpoint()(task=task, plan=plan, now=now)
        runtime = self._ports.require_runtime_plan()(plan=plan)
        control_mode = str(getattr(task.workflow, "control_mode", "") or "auto").strip().lower()
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "")
        topology = str(getattr(task, "topology", "") or "")
        deadline = task.workflow.stage_deadline_at
        if deadline is None:
            raise TaskExecutionError(
                "irrigation_check_deadline_unconfigured",
                "Отсутствует stage_deadline_at для irrigation_check; "
                "задайте duration_sec или stage_timeout_sec в irrigation_execution.",
            )
        # Deprecated schema block: only max_setup_replays is still used
        # (solution_min → setup replay). Chemistry recovery stages are gone.
        recovery = runtime.irrigation_recovery
        solution_min_guard_enabled = bool(runtime.irrigation_safety.stop_on_solution_min)
        expected_irrigation_state = self._ports.resolve_expected_irrigation_state(
            task=task,
            plan=plan,
            runtime=runtime,
            now=now,
        )
        recent_storage_event = await self._ports.read_recent_storage_event()(
            task=task,
            event_types=("IRRIGATION_SOLUTION_LOW", "EMERGENCY_STOP_ACTIVATED"),
            max_age_sec=86400,  # config-literal: one-day storage-event replay window
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
            self._ports.global_irrigation_duration().labels(topology=topology, stop_reason=stop_reason).observe(
                max(0.0, duration)
            )

        if pending_manual_step == "irrigation_stop":
            target_snapshot = await self._ports.target_outcome_on_deadline()(
                task=task,
                plan=plan,
                now=now,
                runtime=runtime,
            )
            await self._ports.record_deadline_target_outcome()(
                task=task,
                snapshot=target_snapshot,
                reason="manual_irrigation_stop",
            )
            _observe_duration("manual")
            return StageOutcome(kind="transition", next_stage="irrigation_stop_to_ready")

        duration_cap_outcome = await self._ports.maybe_stop_continuous_pump_after_duration(
            task=task,
            plan=plan,
            runtime=runtime,
            now=now,
            observe_duration=_observe_duration,
        )
        if duration_cap_outcome is not None:
            return duration_cap_outcome

        if self._ports.deadline_reached()(now=now, deadline=deadline):
            target_snapshot = await self._ports.target_outcome_on_deadline()(
                task=task,
                plan=plan,
                now=now,
                runtime=runtime,
            )
            await self._ports.record_deadline_target_outcome()(
                task=task,
                snapshot=target_snapshot,
            )
            _observe_duration("ready")
            return StageOutcome(kind="transition", next_stage="irrigation_stop_to_ready")

        probe_verified = False
        if recent_event_type == "IRRIGATION_SOLUTION_LOW" and solution_min_guard_enabled:
            if self._ports.recent_solution_low_event_confirms_active_low(
                event=recent_storage_event,
                expected=expected_irrigation_state,
            ):
                return await self._ports.solution_min_low_outcome(
                    task=task,
                    topology=topology,
                    recovery=recovery,
                    now=now,
                    observe_duration=_observe_duration,
                    source="node_event",
                )
            try:
                await self._ports.probe_irr_state()(
                    task=task,
                    plan=plan,
                    now=now,
                    expected=expected_irrigation_state,
                )
                probe_verified = True
            except TaskExecutionError:
                return await self._ports.solution_min_low_outcome(
                    task=task,
                    topology=topology,
                    recovery=recovery,
                    now=now,
                    observe_duration=_observe_duration,
                    source="node_event",
                )
            self._ports.global_logger().info(
                "irrigation_check: игнорирую stale IRRIGATION_SOLUTION_LOW event zone_id=%s task_id=%s",
                task.zone_id,
                getattr(task, "id", None),
            )
        if recent_event_type == "EMERGENCY_STOP_ACTIVATED":
            await self._ports.reconcile_recent_emergency_stop()(
                task=task,
                plan=plan,
                now=now,
                expected=expected_irrigation_state,
            )

        if not probe_verified:
            probe_exhausted_stage = "irrigation_stop_to_ready"
            probe_outcome = await self._ports.probe_irr_state_with_backoff()(
                task=task,
                plan=plan,
                now=now,
                expected=expected_irrigation_state,
                poll_delay_sec=int(runtime.level_poll_interval_sec),
                exhausted_outcome=StageOutcome(
                    kind="transition",
                    next_stage=probe_exhausted_stage,
                ),
            )
            if probe_outcome is not None:
                if probe_outcome.next_stage == "irrigation_stop_to_ready":
                    target_snapshot = await self._ports.target_outcome_on_deadline()(
                        task=task,
                        plan=plan,
                        now=now,
                        runtime=runtime,
                    )
                    await self._ports.record_deadline_target_outcome()(
                        task=task,
                        snapshot=target_snapshot,
                        reason="irrigation_probe_exhausted",
                    )
                return probe_outcome

        flow_hold = await self._ports.handle_control_mode_flow_path_interrupt()(
            task=task,
            plan=plan,
            now=now,
            control_mode=control_mode,
        )
        if flow_hold is not None:
            return flow_hold

        if solution_min_guard_enabled:
            solution_min = await self._ports.read_level()(
                task=task,
                zone_id=task.zone_id,
                labels=runtime.solution_min_sensor_labels,
                threshold=runtime.level_switch_on_threshold,
                telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
                unavailable_error="two_tank_solution_min_level_unavailable",
                stale_error="two_tank_solution_min_level_stale",
                stale_recheck_delay_sec=self._ports.stale_recheck_delay_sec(),
                prefer_probe_snapshot=True,
            )
            if not solution_min["is_triggered"]:
                return await self._ports.solution_min_low_outcome(
                    task=task,
                    topology=topology,
                    recovery=recovery,
                    now=now,
                    observe_duration=_observe_duration,
                    source="sensor",
                )

        execution = runtime.irrigation_execution
        correction_enabled = bool(execution.correction_during_irrigation)
        if correction_enabled:
            stage_retry_count = int(getattr(task.workflow, "stage_retry_count", 0) or 0)
            if stage_retry_count <= 0 and not await self._ports.targets_reached()(
                task=task, plan=plan, now=now, runtime=runtime
            ):
                correction_cfg = self._ports.runtime_config().correction_config_for_task(task=task, runtime=runtime)
                ec_max_attempts = self._ports.runtime_config().required_correction_int(
                    correction_cfg=correction_cfg,
                    key="max_ec_correction_attempts",
                )
                ph_max_attempts = self._ports.runtime_config().required_correction_int(
                    correction_cfg=correction_cfg,
                    key="max_ph_correction_attempts",
                )
                ec_component = str(getattr(execution, "irrigation_ec_component", None) or "none").strip().lower()
                if ec_component not in {"calcium", "npk"}:
                    ec_component = "none"

                if ec_component == "none":
                    pipeline_phase = "irrigation_ph"
                    active_component = "ph"
                    allow_ec_attempts = 0
                    ec_pid_frozen = True
                else:
                    pipeline_phase = f"irrigation_{ec_component}"
                    active_component = ec_component
                    allow_ec_attempts = ec_max_attempts
                    ec_pid_frozen = False
                (
                    component_targets_json,
                    baseline_id,
                    water_ec,
                    water_ph,
                    nutrient_budget,
                ) = await self._ports.load_irrigation_nutrient_baseline(task=task)

                corr = CorrectionState.build_default(
                    corr_step="corr_check",
                    max_attempts=max(allow_ec_attempts, ph_max_attempts) or ph_max_attempts,
                    ec_max_attempts=allow_ec_attempts,
                    ph_max_attempts=ph_max_attempts,
                    activated_here=False,  # irrigation_start already ran sensor_mode_activate
                    stabilization_sec=self._ports.runtime_config().required_correction_int(
                        correction_cfg=correction_cfg,
                        key="stabilization_sec",
                    ),
                    return_stage_success=stage_def.on_corr_success or "irrigation_check",
                    return_stage_fail=stage_def.on_corr_fail or "irrigation_check",
                )
                corr = replace(
                    corr,
                    **self._ports.probe_snapshot_correction_fields()(task=task),
                    pipeline_phase=pipeline_phase,
                    active_component=active_component,
                    ec_pid_frozen=ec_pid_frozen,
                    component_targets_json=component_targets_json,
                    baseline_id=baseline_id,
                    water_ec=water_ec,
                    water_ph=water_ph,
                    nutrient_budget=nutrient_budget,
                )
                self._ports.global_irrigation_correction_entered().labels(topology=topology).inc()
                try:
                    details = {
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "stage": "irrigation_check",
                        "current_stage": "irrigation_check",
                        "workflow_phase": str(getattr(task.workflow, "workflow_phase", "") or ""),
                        "topology": topology,
                        "irrigation_ec_component": ec_component,
                        "pipeline_phase": pipeline_phase,
                    }
                    snapshot_ctx = self._ports.probe_snapshot_context()(task=task)
                    if isinstance(snapshot_ctx, Mapping):
                        snapshot_event_id = snapshot_ctx.get("snapshot_event_id")
                        if snapshot_event_id is not None:
                            details.setdefault("caused_by_event_id", snapshot_event_id)
                        details.update(snapshot_ctx)
                    await self._ports.global_create_zone_event(
                        int(task.zone_id),
                        "IRRIGATION_CORRECTION_STARTED",
                        with_runtime_event_contract(details),
                    )
                except Exception:
                    self._ports.global_logger().warning(
                        "AE3 не смог записать IRRIGATION_CORRECTION_STARTED zone_id=%s task_id=%s",
                        int(getattr(task, "zone_id", 0) or 0),
                        int(getattr(task, "id", 0) or 0),
                        exc_info=True,
                    )
                return StageOutcome(kind="enter_correction", correction=corr, task_override=task)

        return StageOutcome(kind="poll", due_delay_sec=int(runtime.level_poll_interval_sec))
