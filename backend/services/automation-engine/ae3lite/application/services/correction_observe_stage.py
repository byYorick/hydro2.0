"""Correction observe stage: explicit collaborators, per-call task context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services import correction_observation_finalizer as observation_finalizer
from ae3lite.application.services.correction_observation_reader import (
    ObservationRetry,
    ObservationWindow,
)
from ae3lite.application.services.correction_shared import _pid_entry_or_none
from ae3lite.domain.entities.workflow_state import CorrectionState


@dataclass(frozen=True)
class CorrectionObserveStagePorts:
    correction_config: Callable[..., Any]
    correction_retry_delay_sec: Callable[..., Any]
    enter_correction_after_delay_or_interrupt: Callable[..., Any]
    log_correction_event: Callable[..., Awaitable[Any]]
    no_effect_limit_reached: Callable[..., Awaitable[Any]]
    normalize_timestamp: Callable[..., Any]
    observation_analyzer: Callable[[], Any]
    observation_window_reader: Callable[[], Any]
    pid_state: Callable[[], Any]
    require_runtime_plan: Callable[[], Any]
    runtime_config: Callable[[], Any]
    should_reset_attempt_counters_on_reaction: Callable[..., Any]


class CorrectionObserveStage:
    def __init__(self, ports: CorrectionObserveStagePorts) -> None:
        self._ports = ports

    async def run_wait_observe(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        pid_type: str,
        sensor_type: str,
    ) -> StageOutcome:
        corr_wait_until = self._ports.normalize_timestamp(corr.wait_until)
        normalized_now = self._ports.normalize_timestamp(now)
        if corr_wait_until is not None and normalized_now < corr_wait_until:
            return self._ports.enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=max(1.0, (corr_wait_until - normalized_now).total_seconds()),
            )

        window_or_interrupt = await self.read_observation_window_or_interrupt(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            pid_type=pid_type,
            sensor_type=sensor_type,
        )
        if isinstance(window_or_interrupt, StageOutcome):
            return window_or_interrupt
        return await self.finalize_observation_result(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            pid_type=pid_type,
            sensor_type=sensor_type,
            window=window_or_interrupt,
        )

    async def read_observation_window_or_interrupt(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        pid_type: str,
        sensor_type: str,
    ) -> ObservationWindow | StageOutcome:
        """Fetch and validate the post-dose observation window.

        Pipeline (any step may short-circuit with a StageOutcome):
          1. Resolve the prior PID entry, baseline value and last_dose_at.
             Missing baseline is a fail-closed config error.
          2. Read the telemetry window starting at ``last_dose_at + transport_delay``.
          3. Stale / no sensor → ``CORRECTION_SKIPPED_FRESHNESS`` + retry.
          4. Summarize (median + slope stability) → ``CORRECTION_SKIPPED_WINDOW_NOT_READY``
             + retry if not stabilised.

        Returns an ``ObservationWindow`` with everything the finalize helper
        needs, otherwise a ``StageOutcome`` the orchestrator returns as-is.
        """
        runtime = self._ports.require_runtime_plan()(plan=plan)
        correction_cfg = self._ports.correction_config(plan=plan, task=task)
        process_cfg = self._ports.runtime_config().process_cfg_for_task(task=task, runtime=runtime)
        pid_state = runtime.pid_state if isinstance(runtime.pid_state, Mapping) else {}
        pid_entry = _pid_entry_or_none(pid_state, pid_type) or {}
        observe_cfg = self._ports.runtime_config().observation_config(
            kind=pid_type,
            correction_cfg=correction_cfg,
            process_cfg=process_cfg,
            pid_entry=pid_entry,
        )
        result = await self._ports.observation_window_reader().read(
            task=task,
            corr=corr,
            now=now,
            pid_type=pid_type,
            sensor_type=sensor_type,
            telemetry_max_age_sec=runtime.telemetry_max_age_sec,
            pid_entry=pid_entry,
            observe_cfg=observe_cfg,
            process_cfg=process_cfg,
            stale_retry_delay_fn=lambda: self._ports.correction_retry_delay_sec(
                correction_cfg=correction_cfg,
                key="telemetry_stale_retry_sec",
            ),
        )
        if isinstance(result, ObservationRetry):
            return self._ports.enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                due_delay_sec=result.due_delay_sec,
            )
        return result

    async def finalize_observation_result(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        pid_type: str,
        sensor_type: str,
        window: ObservationWindow,
    ) -> StageOutcome:
        """Analyze a ready observation window and schedule the next step.

        Pipeline:
          1. Compute directional/peak/learning effects via ObservationAnalyzer.
          2. Derive ``is_no_effect`` and increment the consecutive counter.
          3. Log ``CORRECTION_OBSERVATION_EVALUATED``.
          4. Persist the updated PID state (measured value + adaptive stats).
          5. Preserve EC feedforward_bias until the next pH dose consumes it.
          6. If the no-effect limit is reached → ``_no_effect_limit_reached``.
          7. Otherwise: bump attempt counters (or reset on reaction), build
             the next correction state preserving the opposite-direction
             pending dose, and return ``enter_correction`` pointing back
             at ``corr_check``.
        """
        evaluation = observation_finalizer.evaluate_observation(
            corr=corr,
            pid_type=pid_type,
            sensor_type=sensor_type,
            window=window,
            phase_key=self._ports.runtime_config().runtime_phase_key(task=task),
            analyzer=self._ports.observation_analyzer(),
        )
        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="CORRECTION_OBSERVATION_EVALUATED",
            task=task,
            corr=corr,
            payload=evaluation.event_payload,
        )
        runtime = plan.runtime
        target_ph = float(self._ports.runtime_config().effective_ph_target(task=task, runtime=runtime))
        target_ec = float(self._ports.runtime_config().effective_ec_target(task=task, runtime=runtime))
        await self._ports.pid_state().persist(
            zone_id=task.zone_id,
            now=now,
            updates=observation_finalizer.build_observation_pid_update(
                corr=corr,
                pid_type=pid_type,
                window=window,
                evaluation=evaluation,
                now=now,
                target_ph=target_ph,
                target_ec=target_ec,
                analyzer=self._ports.observation_analyzer(),
            ),
        )
        # Preserve EC→pH bias until the next pH dose consumes it.
        if evaluation.next_no_effect_count >= int(window.observe_cfg["no_effect_limit"]):
            return await self._ports.no_effect_limit_reached(
                task=task,
                plan=plan,
                corr=corr,
                pid_type=pid_type,
                baseline_value=window.baseline_value,
                observed_value=window.summary_value,
                expected_effect=evaluation.expected_effect,
                actual_effect=float(evaluation.response.peak_effect),
                threshold_effect=evaluation.threshold_effect,
                no_effect_limit=int(window.observe_cfg["no_effect_limit"]),
            )
        next_corr = observation_finalizer.correction_after_observation(
            corr=corr,
            pid_type=pid_type,
            is_no_effect=evaluation.is_no_effect,
            reset_attempt_counters=(
                not evaluation.is_no_effect and self._ports.should_reset_attempt_counters_on_reaction(task=task)
            ),
        )
        return StageOutcome(kind="enter_correction", correction=next_corr)
