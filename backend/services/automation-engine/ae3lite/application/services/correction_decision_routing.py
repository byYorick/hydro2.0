"""Correction decision routing: explicit collaborators, per-call task context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.correction_pipeline import (
    pipeline_dose_flags,
)
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.services.correction_dose_routing import route_dose_plan
from ae3lite.domain.services.correction_planner import (
    DosePlan,
)
from ae3lite.infrastructure.metrics import (
    CORRECTION_DOSE_CLAMPED,
)


@dataclass(frozen=True)
class CorrectionDecisionRoutingPorts:
    correction_config: Callable[..., Any]
    correction_exhausted: Callable[..., Awaitable[Any]]
    correction_retry_delay_sec: Callable[..., Any]
    enter_correction_after_delay_or_interrupt: Callable[..., Any]
    interrupt_for_control_mode_dosing: Callable[..., Awaitable[Any]]
    log_attempt_cap_ignored: Callable[..., Awaitable[Any]]
    log_correction_event: Callable[..., Awaitable[Any]]
    maybe_emit_pid_output_zone_event: Callable[..., Awaitable[Any]]
    pid_state: Callable[[], Any]
    planner: Callable[[], Any]
    readiness_event_payload: Callable[..., Any]
    recirc_pipeline_open: Callable[[], Any]
    record_dose_clamp_metrics: Callable[..., Any]
    record_dual_calibration_mismatch_observability: Callable[..., Awaitable[Any]]
    runtime_config: Callable[[], Any]
    transition_to_deactivate_or_return: Callable[..., Any]


class CorrectionDecisionRouting:
    def __init__(self, ports: CorrectionDecisionRoutingPorts) -> None:
        self._ports = ports

    async def finalize_dose_plan_routing(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        dose_plan: DosePlan,
        runtime: Mapping[str, Any],
        pid_state: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
        target_ph: float,
        target_ec: float,
        current_stage: str,
        workflow_ready: bool,
        enforce_attempt_caps: bool,
    ) -> StageOutcome:
        """Route a built ``DosePlan`` into the next FSM step.

        Handles the post-planner tail of ``_run_check``:
        * control_mode / flow_hold gate (before any plan PID persist)
        * handle "no dose needed" (cooldown / true dead zone / discarded)
        * enforce per-direction attempt caps
        * save the dose plan into the correction state
        * decide priority (pending_ph / ec_first / ph_only)
        * persist PID I/D only for the controller about to dose
        * log ``CORRECTION_DECISION_MADE`` + emit ``PID_OUTPUT`` event
        * return the ``enter_correction`` StageOutcome

        Safety gates and PID persistence remain here; the pure route and
        correction snapshot are built by ``route_dose_plan``.
        """
        # Flow-hold / control_mode must win before committing plan integral.
        if dose_plan.needs_any:
            flow_hold = await self._ports.interrupt_for_control_mode_dosing(
                task=task,
                plan=plan,
                now=now,
            )
            if flow_hold is not None:
                return flow_hold

        if not dose_plan.needs_any and dose_plan.retry_after_sec:
            await self._ports.log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_COOLDOWN",
                task=task,
                corr=corr,
                payload={
                    "current_ph": current_ph,
                    "current_ec": current_ec,
                    "target_ph": target_ph,
                    "target_ec": target_ec,
                    "retry_after_sec": dose_plan.retry_after_sec,
                    "target_ph_min": runtime.target_ph_min,
                    "target_ph_max": runtime.target_ph_max,
                    "target_ec_min": self._ports.runtime_config().effective_ec_min(task=task, runtime=runtime),
                    "target_ec_max": self._ports.runtime_config().effective_ec_max(task=task, runtime=runtime),
                },
            )
            next_corr = replace(corr, corr_step="corr_check")
            return self._ports.enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=next_corr,
                now=now,
                due_delay_sec=dose_plan.retry_after_sec,
            )

        if not dose_plan.needs_any:
            if dose_plan.dose_discarded_reason:
                # Discard ≠ deadband: targets may still be out of tolerance.
                # Retry corr_check with backoff; count toward attempt exhaustion.
                # Do NOT emit CORRECTION_SKIPPED_DEAD_ZONE or success=True.
                await self._ports.log_correction_event(
                    zone_id=task.zone_id,
                    event_type="CORRECTION_SKIPPED_DOSE_DISCARDED",
                    task=task,
                    corr=corr,
                    payload={
                        "current_ph": current_ph,
                        "current_ec": current_ec,
                        "target_ph": target_ph,
                        "target_ec": target_ec,
                        "reason": dose_plan.dose_discarded_reason,
                        **(
                            dict(dose_plan.dose_discarded_details)
                            if isinstance(dose_plan.dose_discarded_details, Mapping)
                            else {}
                        ),
                        "target_ph_min": runtime.target_ph_min,
                        "target_ph_max": runtime.target_ph_max,
                        "target_ec_min": self._ports.runtime_config().effective_ec_min(task=task, runtime=runtime),
                        "target_ec_max": self._ports.runtime_config().effective_ec_max(task=task, runtime=runtime),
                    },
                )
                # Freeze measurement clock so retry does not inflate I via wall-clock dt.
                await self._ports.pid_state().touch_measurement_clock(
                    zone_id=task.zone_id,
                    now=now,
                    current_ph=current_ph,
                    current_ec=current_ec,
                )
                next_attempt = int(corr.attempt) + 1
                if enforce_attempt_caps and next_attempt >= corr.max_attempts:
                    return await self._ports.correction_exhausted(
                        task=task,
                        plan=plan,
                        corr=replace(corr, attempt=next_attempt),
                    )
                if not enforce_attempt_caps and next_attempt >= corr.max_attempts:
                    await self._ports.log_attempt_cap_ignored(
                        task=task,
                        corr=corr,
                        cap_type="overall",
                        current_value=next_attempt,
                        limit_value=corr.max_attempts,
                    )
                if current_stage == "prepare_recirculation_check" and not workflow_ready:
                    retry_delay_sec = int(runtime.level_poll_interval_sec)
                else:
                    retry_delay_sec = self._ports.correction_retry_delay_sec(
                        correction_cfg=self._ports.correction_config(plan=plan, task=task),
                        key="decision_window_retry_sec",
                    )
                next_corr = replace(corr, corr_step="corr_check", attempt=next_attempt)
                return self._ports.enter_correction_after_delay_or_interrupt(
                    task=task,
                    plan=plan,
                    corr=next_corr,
                    now=now,
                    due_delay_sec=retry_delay_sec,
                )

            # True deadband / within PID dead zone — not a discarded dose.
            # Открытый recirc-pipeline: deadband текущего шага (часто T_ca) не
            # закрывает рецепт. Шаг двигает maybe_advance_pipeline; здесь только retry.
            if current_stage == "prepare_recirculation_check" and (
                not workflow_ready or self._ports.recirc_pipeline_open()(task)
            ):
                next_corr = replace(corr, corr_step="corr_check")
                return self._ports.enter_correction_after_delay_or_interrupt(
                    task=task,
                    plan=plan,
                    corr=next_corr,
                    now=now,
                    due_delay_sec=int(runtime.level_poll_interval_sec),
                )
            await self._ports.log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_DEAD_ZONE",
                task=task,
                corr=corr,
                payload={
                    "current_ph": current_ph,
                    "current_ec": current_ec,
                    "target_ph": target_ph,
                    "target_ec": target_ec,
                    **(dict(dose_plan.dead_zone_details) if isinstance(dose_plan.dead_zone_details, Mapping) else {}),
                    "target_ph_min": runtime.target_ph_min,
                    "target_ph_max": runtime.target_ph_max,
                    "target_ec_min": self._ports.runtime_config().effective_ec_min(task=task, runtime=runtime),
                    "target_ec_max": self._ports.runtime_config().effective_ec_max(task=task, runtime=runtime),
                    **self._ports.readiness_event_payload(
                        targets_in_tolerance=self._ports.planner().is_within_tolerance(
                            current_ph=current_ph,
                            current_ec=current_ec,
                            target_ph=target_ph,
                            target_ec=target_ec,
                            ph_tolerance_pct=self._ports.runtime_config().required_prepare_tolerance_pct(
                                tolerance=self._ports.runtime_config().prepare_tolerance_for_task(
                                    task=task, runtime=runtime
                                ),
                                key="ph_pct",
                            ),
                            ec_tolerance_pct=self._ports.runtime_config().required_prepare_tolerance_pct(
                                tolerance=self._ports.runtime_config().prepare_tolerance_for_task(
                                    task=task, runtime=runtime
                                ),
                                key="ec_pct",
                            ),
                            ph_min=self._ports.runtime_config().effective_ph_min(task=task, runtime=runtime),
                            ph_max=self._ports.runtime_config().effective_ph_max(task=task, runtime=runtime),
                            ec_min=self._ports.runtime_config().effective_ec_min(task=task, runtime=runtime),
                            ec_max=self._ports.runtime_config().effective_ec_max(task=task, runtime=runtime),
                            correction_config=self._ports.correction_config(plan=plan, task=task),
                            pid_configs=getattr(runtime, "pid_configs", {}),
                            allow_ec=bool(pipeline_dose_flags(corr).get("allow_ec", True)),
                            allow_ph=bool(pipeline_dose_flags(corr).get("allow_ph", True)),
                        ),
                        workflow_ready=workflow_ready,
                    ),
                },
            )
            return self._ports.transition_to_deactivate_or_return(corr=corr, success=True)

        # Observability: true partial discard (component skipped) vs saturation clamp.
        if dose_plan.dose_discarded_reason:
            await self._ports.log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_SKIPPED_DOSE_DISCARDED",
                task=task,
                corr=corr,
                payload={
                    "current_ph": current_ph,
                    "current_ec": current_ec,
                    "target_ph": target_ph,
                    "target_ec": target_ec,
                    "reason": dose_plan.dose_discarded_reason,
                    "partial": True,
                    "needs_ec": dose_plan.needs_ec,
                    "needs_ph_up": dose_plan.needs_ph_up,
                    "needs_ph_down": dose_plan.needs_ph_down,
                    **(
                        dict(dose_plan.dose_discarded_details)
                        if isinstance(dose_plan.dose_discarded_details, Mapping)
                        else {}
                    ),
                    "target_ph_min": runtime.target_ph_min,
                    "target_ph_max": runtime.target_ph_max,
                    "target_ec_min": self._ports.runtime_config().effective_ec_min(task=task, runtime=runtime),
                    "target_ec_max": self._ports.runtime_config().effective_ec_max(task=task, runtime=runtime),
                },
            )
        elif dose_plan.dose_clamped_reason:
            # Clamp is successful routing with capped pulse — not a skip/discard.
            if dose_plan.needs_ec:
                CORRECTION_DOSE_CLAMPED.labels(pid_type="ec").inc()
            if dose_plan.needs_ph_up or dose_plan.needs_ph_down:
                CORRECTION_DOSE_CLAMPED.labels(pid_type="ph").inc()
            await self._ports.log_correction_event(
                zone_id=task.zone_id,
                event_type="CORRECTION_DOSE_CLAMPED",
                task=task,
                corr=corr,
                payload={
                    "current_ph": current_ph,
                    "current_ec": current_ec,
                    "target_ph": target_ph,
                    "target_ec": target_ec,
                    "reason": dose_plan.dose_clamped_reason,
                    "needs_ec": dose_plan.needs_ec,
                    "needs_ph_up": dose_plan.needs_ph_up,
                    "needs_ph_down": dose_plan.needs_ph_down,
                    **(
                        dict(dose_plan.dose_clamped_details)
                        if isinstance(dose_plan.dose_clamped_details, Mapping)
                        else {}
                    ),
                    "target_ph_min": runtime.target_ph_min,
                    "target_ph_max": runtime.target_ph_max,
                    "target_ec_min": self._ports.runtime_config().effective_ec_min(task=task, runtime=runtime),
                    "target_ec_max": self._ports.runtime_config().effective_ec_max(task=task, runtime=runtime),
                },
            )

        # Per-direction attempt cap enforcement (EC + pH separately).
        if enforce_attempt_caps:
            if dose_plan.needs_ec and corr.ec_attempt >= corr.ec_max_attempts:
                return await self._ports.correction_exhausted(task=task, plan=plan, corr=corr)
            if (dose_plan.needs_ph_up or dose_plan.needs_ph_down) and corr.ph_attempt >= corr.ph_max_attempts:
                return await self._ports.correction_exhausted(task=task, plan=plan, corr=corr)
        else:
            if dose_plan.needs_ec and corr.ec_attempt >= corr.ec_max_attempts:
                await self._ports.log_attempt_cap_ignored(
                    task=task,
                    corr=corr,
                    cap_type="ec",
                    current_value=corr.ec_attempt,
                    limit_value=corr.ec_max_attempts,
                )
            if (dose_plan.needs_ph_up or dose_plan.needs_ph_down) and corr.ph_attempt >= corr.ph_max_attempts:
                await self._ports.log_attempt_cap_ignored(
                    task=task,
                    corr=corr,
                    cap_type="ph",
                    current_value=corr.ph_attempt,
                    limit_value=corr.ph_max_attempts,
                )

        self._ports.record_dose_clamp_metrics(dose_plan)
        await self._ports.record_dual_calibration_mismatch_observability(
            task=task,
            corr=corr,
            dose_plan=dose_plan,
        )

        routing = route_dose_plan(corr=corr, dose_plan=dose_plan)
        if routing is None:
            return self._ports.transition_to_deactivate_or_return(corr=corr, success=True)
        next_corr = routing.correction
        selected_action = routing.selected_action
        decision_reason = routing.decision_reason

        # Persist PID plan updates only after dose routing is confirmed and not
        # flow-held. Dual EC+PH: commit I only for the controller about to dose;
        # peer gets measurement-clock touch only (integral freeze).
        await self._ports.pid_state().persist(
            zone_id=task.zone_id,
            updates=self._ports.pid_state().select_updates(
                dose_plan=dose_plan,
                selected_action=str(selected_action),
            ),
            now=now,
        )

        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_DECISION_MADE",
            task=task,
            corr=next_corr,
            payload={
                "selected_action": selected_action,
                "decision_reason": decision_reason,
                "current_ph": current_ph,
                "current_ec": current_ec,
                "target_ph": target_ph,
                "target_ec": target_ec,
                "target_ph_min": runtime.target_ph_min,
                "target_ph_max": runtime.target_ph_max,
                "target_ec_min": self._ports.runtime_config().effective_ec_min(task=task, runtime=runtime),
                "target_ec_max": self._ports.runtime_config().effective_ec_max(task=task, runtime=runtime),
                "needs_ec": dose_plan.needs_ec,
                "needs_ph_up": dose_plan.needs_ph_up,
                "needs_ph_down": dose_plan.needs_ph_down,
                "pending_ph_from_previous_step": bool(corr.needs_ph_up or corr.needs_ph_down),
                **(dict(dose_plan.dead_zone_details) if isinstance(dose_plan.dead_zone_details, Mapping) else {}),
            },
        )
        await self._ports.maybe_emit_pid_output_zone_event(
            zone_id=int(task.zone_id),
            corr_step=str(next_corr.corr_step),
            dose_plan=dose_plan,
            pid_state_before=pid_state,
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=target_ph,
            target_ec=target_ec,
            now=now,
        )
        return self._ports.enter_correction_after_delay_or_interrupt(
            task=task,
            plan=plan,
            corr=next_corr,
            now=now,
            due_delay_sec=0.0,
        )
