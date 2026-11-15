"""Correction check: explicit collaborators, per-call task context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.correction_component_budget import apply_component_budget
from ae3lite.application.services.correction_pipeline import (
    pipeline_dose_flags,
    recipe_ec_band_reached,
    should_dilute,
    step_targets_reached,
)
from ae3lite.application.services.correction_pipeline_completion import complete_pipeline_step
from ae3lite.application.services.correction_plan_request import CorrectionDoseRequest, build_checked_dose_plan
from ae3lite.application.services.correction_shared import (
    _ALERT_BLOCK_RETRY_DELAY_SEC,
    _ALERT_BLOCK_SNAPSHOT_PREFIX,
    _alert_block_retry_count,
    _clear_alert_block_marker,
)
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.correction_planner import (
    _next_pid_state,
)


@dataclass(frozen=True)
class CorrectionCheckPorts:
    alert_block_max_retries: Callable[[], int]
    check_no_effect_block: Callable[..., Any]
    correction_config: Callable[..., Any]
    correction_exhausted: Callable[..., Awaitable[Any]]
    enforce_attempt_caps: Callable[..., Any]
    finalize_dose_plan_routing: Callable[..., Awaitable[Any]]
    interrupt_for_control_mode_dosing: Callable[..., Awaitable[Any]]
    irrigation_ready_short_circuit: Callable[[], Any]
    log_attempt_cap_ignored: Callable[..., Awaitable[Any]]
    log_correction_event: Callable[..., Awaitable[Any]]
    pid_state: Callable[[], Any]
    planner: Callable[[], Any]
    read_measurements_or_interrupt: Callable[..., Awaitable[Any]]
    require_runtime_plan: Callable[[], Any]
    reset_ec_pid_for_pipeline: Callable[..., Awaitable[Any]]
    resolve_actuators: Callable[..., Any]
    runtime_config: Callable[[], Any]
    should_log_limit_policy: Callable[..., Any]
    transition_to_deactivate_or_return: Callable[..., Any]


class CorrectionCheck:
    def __init__(self, ports: CorrectionCheckPorts) -> None:
        self._ports = ports

    async def run_check(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        runtime = self._ports.require_runtime_plan()(plan=plan)
        max_age = int(runtime.telemetry_max_age_sec)

        target_ph = self._ports.runtime_config().effective_ph_target(task=task, runtime=runtime)
        target_ec = self._ports.runtime_config().effective_ec_target(task=task, runtime=runtime)
        target_ph_min = self._ports.runtime_config().effective_ph_min(task=task, runtime=runtime)
        target_ph_max = self._ports.runtime_config().effective_ph_max(task=task, runtime=runtime)
        target_ec_min = self._ports.runtime_config().effective_ec_min(task=task, runtime=runtime)
        target_ec_max = self._ports.runtime_config().effective_ec_max(task=task, runtime=runtime)
        tolerance = self._ports.runtime_config().prepare_tolerance_for_task(task=task, runtime=runtime)
        ph_tol_pct = self._ports.runtime_config().required_prepare_tolerance_pct(tolerance=tolerance, key="ph_pct")
        ec_tol_pct = self._ports.runtime_config().required_prepare_tolerance_pct(tolerance=tolerance, key="ec_pct")
        correction_cfg = self._ports.correction_config(plan=plan, task=task)
        process_cfg = self._ports.runtime_config().process_cfg_for_task(task=task, runtime=runtime)
        pid_state = runtime.pid_state if isinstance(runtime.pid_state, Mapping) else {}
        enforce_attempt_caps = self._ports.enforce_attempt_caps(task=task)

        # Safety gate: если active no-effect alert не позволяет коррекции
        # продолжаться (защита от дальнейшей деградации раствора при
        # конфигурационной проблеме — например, empty reagent bottle), skip
        # коррекцию. Разблокируется когда no_effect_count сбрасывается в 0 —
        # либо successful correction (auto-reset в этом же handler), либо
        # явный ack пользователя через admin endpoint.
        blocked = self._ports.check_no_effect_block(
            task=task,
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_state=pid_state,
        )
        if blocked is not None:
            retry_count = _alert_block_retry_count(corr) + 1
            if retry_count >= self._ports.alert_block_max_retries():
                raise TaskExecutionError(
                    "correction_blocked_by_no_effect_alert",
                    (
                        "Коррекция заблокирована активным no-effect alert: "
                        f"исчерпан лимит повторов ({self._ports.alert_block_max_retries()})"
                    ),
                )
            await self._ports.log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_BY_ALERT_BLOCK",
                task=task,
                corr=corr,
                payload={
                    **blocked,
                    "alert_block_retry": retry_count,
                    "alert_block_max_retries": self._ports.alert_block_max_retries(),
                },
            )
            return StageOutcome(
                kind="retry",
                due_delay_sec=_ALERT_BLOCK_RETRY_DELAY_SEC,
                correction=replace(
                    corr,
                    snapshot_cmd_id=f"{_ALERT_BLOCK_SNAPSHOT_PREFIX}{retry_count}",
                ),
            )

        corr = _clear_alert_block_marker(corr)

        if self._ports.should_log_limit_policy(task=task, corr=corr):
            await self._ports.log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_LIMIT_POLICY_APPLIED",
                task=task,
                corr=corr,
                payload={
                    "attempt_caps_enforced": False,
                    "stop_conditions": ["no_effect", "stage_timeout"],
                    "stage_timeout_sec": runtime.solution_fill_timeout_sec,
                    "policy": "fill_continuous_until_no_effect_or_timeout",
                },
            )
            corr = replace(corr, limit_policy_logged=True)

        measurement_or_interrupt = await self._ports.read_measurements_or_interrupt(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            runtime=runtime,
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_state=pid_state,
            target_ph=target_ph,
            target_ec=target_ec,
            max_age=max_age,
        )
        if isinstance(measurement_or_interrupt, StageOutcome):
            return measurement_or_interrupt
        measurement = measurement_or_interrupt
        current_ph = measurement.current_ph
        current_ec = measurement.current_ec
        workflow_ready = measurement.workflow_ready
        current_stage = measurement.current_stage

        dose_flags = pipeline_dose_flags(corr)
        budget_result = await apply_component_budget(
            task=task,
            corr=corr,
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=target_ph,
            target_ec=target_ec,
            runtime=runtime,
            correction_cfg=correction_cfg,
            current_stage=current_stage,
            planner=self._ports.planner(),
            log_event=self._ports.log_correction_event,
        )
        if isinstance(budget_result, StageOutcome):
            return budget_result
        target_ec = budget_result
        correction_targets_reached = self._ports.planner().is_within_tolerance(
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=target_ph,
            target_ec=target_ec,
            ph_tolerance_pct=ph_tol_pct,
            ec_tolerance_pct=ec_tol_pct,
            ph_min=target_ph_min,
            ph_max=target_ph_max,
            ec_min=target_ec_min,
            ec_max=target_ec_max,
            correction_config=correction_cfg,
            pid_configs=getattr(runtime, "pid_configs", {}),
            allow_ec=bool(dose_flags.get("allow_ec", True)),
            allow_ph=bool(dose_flags.get("allow_ph", True)),
        )

        pipeline_step_reached = step_targets_reached(
            corr=corr,
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=target_ph,
            target_ec=target_ec,
            ph_tol_pct=ph_tol_pct,
            ec_tol_pct=ec_tol_pct,
            correction_config=correction_cfg,
            pid_configs=getattr(runtime, "pid_configs", {}),
            planner=self._ports.planner(),
        )
        if pipeline_step_reached and not recipe_ec_band_reached(
            pipeline_phase=getattr(corr, "pipeline_phase", None),
            current_ec=current_ec,
            ec_min=self._ports.runtime_config().irrigation_ec_min(runtime=runtime),
            ec_max=self._ports.runtime_config().irrigation_ec_max(runtime=runtime),
        ):
            pipeline_step_reached = False
        # prepare: классика — оба условия (prepare-tolerance + phase-ready).
        # Short-circuit: irrigation-band и EC уже выше prepare-target (нет dose-down).
        irrigation_short_circuit = (
            self._ports.irrigation_ready_short_circuit()(
                task=task,
                runtime=runtime,
                current_ph=current_ph,
                current_ec=current_ec,
            )
            if current_stage == "prepare_recirculation_check"
            else False
        )
        # Pipeline-aware success: advance interleaved steps instead of exiting early.
        if getattr(corr, "pipeline_phase", None) and pipeline_step_reached:
            return await complete_pipeline_step(
                task=task,
                corr=corr,
                current_ph=current_ph,
                current_ec=current_ec,
                target_ph=target_ph,
                target_ec=target_ec,
                now=now,
                current_stage=current_stage,
                workflow_ready=workflow_ready,
                log_event=self._ports.log_correction_event,
                reset_ec_pid=self._ports.reset_ec_pid_for_pipeline,
                pid_state_service=self._ports.pid_state(),
                transition=self._ports.transition_to_deactivate_or_return,
            )

        success_reached = (
            irrigation_short_circuit or (correction_targets_reached and workflow_ready)
            if current_stage == "prepare_recirculation_check" and not getattr(corr, "pipeline_phase", None)
            else (correction_targets_reached if not getattr(corr, "pipeline_phase", None) else False)
        )
        if success_reached:
            await self._ports.log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_COMPLETE",
                task=task,
                corr=corr,
                payload={
                    "current_ph": current_ph,
                    "current_ec": current_ec,
                    "target_ph": target_ph,
                    "target_ec": target_ec,
                    "target_ph_min": target_ph_min,
                    "target_ph_max": target_ph_max,
                    "target_ec_min": target_ec_min,
                    "target_ec_max": target_ec_max,
                    "targets_in_tolerance": correction_targets_reached,
                    "workflow_ready": workflow_ready,
                },
            )
            # Auto-resolve: successful correction снимает "no-effect" состояние.
            # Сбрасываем no_effect_count в pid_state, чтобы следующий tick начался
            # с чистого листа. Сам business-alert остаётся в БД как history —
            # его resolves через notify-path после ack пользователя или через
            # AlertAutoResolver когда is_no_effect=false стабилизируется.
            await self._ports.pid_state().reset_no_effect_counts(
                task=task,
                corr=corr,
                context="CORRECTION_COMPLETE",
            )
            return self._ports.transition_to_deactivate_or_return(corr=corr, success=True)

        # Dilute-on-overshoot (recirc EC step only)
        if should_dilute(
            corr=corr,
            runtime=runtime,
            current_ec=current_ec,
            t_step=target_ec,
            current_stage=current_stage,
        ):
            dilute_corr = replace(
                corr,
                corr_step="corr_dilute_pulse",
                dilute_attempts=int(getattr(corr, "dilute_attempts", 0) or 0) + 1,
            )
            await self._ports.log_correction_event(
                zone_id=task.zone_id,
                event_type="RECIRC_DILUTE_STARTED",
                task=task,
                corr=dilute_corr,
                payload={
                    "current_ec": current_ec,
                    "t_step": target_ec,
                    "dilute_attempts": dilute_corr.dilute_attempts,
                },
            )
            return StageOutcome(kind="enter_correction", correction=dilute_corr, due_delay_sec=0)

        flow_hold = await self._ports.interrupt_for_control_mode_dosing(
            task=task,
            plan=plan,
            now=now,
        )
        if flow_hold is not None:
            return flow_hold

        if enforce_attempt_caps and corr.attempt >= corr.max_attempts:
            return await self._ports.correction_exhausted(task=task, plan=plan, corr=corr)
        if not enforce_attempt_caps and corr.attempt >= corr.max_attempts:
            await self._ports.log_attempt_cap_ignored(
                task=task,
                corr=corr,
                cap_type="overall",
                current_value=corr.attempt,
                limit_value=corr.max_attempts,
            )

        # Build dose plan. PlannerConfigurationError indicates a fail-closed
        # config issue (missing process gain, unsupported multi_sequential
        # permutation, calibration out of range, etc.) — translate it to a
        # correction-specific TaskExecutionError so execute_task maps it to
        # a typed failure instead of an anonymous Ae3LiteError surface.
        actuators = self._ports.resolve_actuators(runtime=runtime, task=task, plan=plan)
        dose_plan = await build_checked_dose_plan(
            request=CorrectionDoseRequest(
                task=task,
                corr=corr,
                current_ph=current_ph,
                current_ec=current_ec,
                target_ph=target_ph,
                target_ec=target_ec,
                now=now,
                runtime=runtime,
                ph_tol_pct=ph_tol_pct,
                ec_tol_pct=ec_tol_pct,
                target_ph_min=target_ph_min,
                target_ph_max=target_ph_max,
                target_ec_min=target_ec_min,
                target_ec_max=target_ec_max,
                correction_cfg=correction_cfg,
                pid_state=pid_state,
                dose_flags=dose_flags,
                actuators=actuators,
            ),
            planner=self._ports.planner(),
            runtime_config=self._ports.runtime_config(),
            log_event=self._ports.log_correction_event,
        )

        return await self._ports.finalize_dose_plan_routing(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            dose_plan=dose_plan,
            runtime=runtime,
            pid_state=pid_state,
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=target_ph,
            target_ec=target_ec,
            current_stage=current_stage,
            workflow_ready=workflow_ready,
            enforce_attempt_caps=enforce_attempt_caps,
        )

    async def freeze_pid_integral_clock(
        self,
        *,
        task: Any,
        pid_state: Mapping[str, Any],
        now: datetime,
    ) -> None:
        """Сдвинуть last_measurement_at без ΔI, пока окно решения не готово.

        Иначе первая доза после минут ожидания считает ``I += gap * dt`` за всё
        ожидание и упирается в max_integral.
        """
        if not isinstance(pid_state, Mapping):
            return
        updates: dict[str, Mapping[str, Any]] = {}
        for kind in ("ec", "ph"):
            entry = pid_state.get(kind)
            if not isinstance(entry, Mapping):
                continue
            try:
                gap = float(entry.get("prev_error") or 0.0)
                current = float(entry.get("last_measured_value") or 0.0)
            except (TypeError, ValueError):
                continue
            frozen = _next_pid_state(
                kind=kind,
                gap=gap,
                current_value=current,
                controller_cfg={},
                pid_entry=entry,
                now=now,
                accumulate_integral=False,
            )
            updates[kind] = {
                **dict(frozen),
                "integral": float(entry.get("integral") or 0.0),
            }
        if updates:
            await self._ports.pid_state().persist(zone_id=task.zone_id, now=now, updates=updates)
