"""CorrectionHandler — 8-step PH/EC correction state machine.

Replaces CorrectionExecutor v1 by reading/writing explicit CorrectionState
fields instead of payload JSONB keys.

Protocol (per CORRECTION_CYCLE_SPEC.md):
  1. corr_activate   — activate PH/EC sensor nodes
  2. corr_wait_stable — wait for sensor stabilization
  3. corr_check      — read PH/EC observation window, decide: done / dose EC / dose PH / give up
  4. corr_dose_ec    — issue EC dose pulse
  5. corr_wait_ec    — hold + observe EC response window
  6. corr_dose_ph    — issue PH dose pulse
  7. corr_wait_ph    — hold + observe PH response window, then bump attempt → corr_check
  8. corr_deactivate — deactivate sensor nodes, return to parent stage
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional, Sequence

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.handlers.base import BaseStageHandler, _utc_naive_dt
from ae3lite.application.level_monitor import (
    coarse_solution_tank_level_percent,
    solution_tank_has_solution,
)
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.application.services.correction_alert_service import CorrectionAlertService
from ae3lite.application.services import correction_dose_accounting as dose_accounting
from ae3lite.application.services import correction_observation_finalizer as observation_finalizer
from ae3lite.application.services.correction_pid_state import CorrectionPidState
from ae3lite.application.services.correction_ec_dose_executor import (
    CorrectionEcDoseExecutor,
    parse_ec_dose_sequence,
)
from ae3lite.application.services.correction_event_logger import CorrectionEventLogger
from ae3lite.application.services.decision_window_reader import (
    DecisionWindowReader,
    DecisionWindowResult,
)
from ae3lite.application.services.correction_observation_reader import (
    CorrectionObservationReader,
    ObservationRetry,
    ObservationWindow,
)
from ae3lite.application.services.sensor_mode_controller import SensorModeController
from ae3lite.application.services.correction_pipeline import (
    irrigation_component_budget_guard,
    maybe_advance_pipeline,
    pipeline_dose_flags,
    recipe_ec_band_reached,
    should_dilute,
    step_targets_reached,
)
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import ALERT_BLOCK_SNAPSHOT_CMD_PREFIX, CorrectionState
from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError, TaskExecutionError
from ae3lite.domain.services.correction_dose_routing import route_dose_plan
from ae3lite.domain.services.ec_batch_failure import describe_partial_ec_failure
from ae3lite.domain.services.correction_planner import (
    CorrectionPlanner,
    DosePlan,
    _next_pid_state,
)
from ae3lite.domain.services.correction_transition_policy import (
    CorrectionTransitionPolicy,
)
from ae3lite.domain.services.metric_window_validator import (
    SENSOR_OUT_OF_BOUNDS_REASON,
)
from ae3lite.domain.services.observation_analyzer import ObservationAnalyzer
from ae3lite.domain.services.pid_output_event import build_pid_output_detail
from ae3lite.infrastructure.log_context import log_context_scope
from ae3lite.infrastructure.metrics import (
    CORRECTION_ATTEMPT,
    CORRECTION_CAP_IGNORED,
    CORRECTION_CONTROL_MODE_BLOCKED,
    CORRECTION_DOSE_CLAMPED,
    CORRECTION_EC_BATCH_PARTIAL_FAILURE,
    CORRECTION_PUMP_CALIBRATION_MIRROR_MISMATCH,
    CORRECTION_ESTOP_INTERRUPT,
    CORRECTION_EXHAUSTED,
    CORRECTION_NO_EFFECT,
    CORRECTION_OBSERVE_OUT_OF_BOUNDS,
)
from ae3lite.hydraulics.failure_report import note_upward_report
from common.db import create_zone_event
from common.utils.time import utcnow_naive as _utcnow


# Sub-second polling micro-delay used by `_read_level()` for stale-recheck.
# This is NOT a business config parameter — it is a telemetry-poll cadence
# (250 ms) chosen to balance CPU load with responsiveness when sensor data
# is freshly stale. Does NOT belong in `zone.correction` schema.


# Retry cadence while corrections are blocked by an active alert (operational backoff).


from ae3lite.application.services.correction_shared import (
    _logger,
    _MeasurementSnapshot,
    _STALE_RECHECK_DELAY_SEC,
    _AE_CORRECTION_ALERT_BLOCK_MAX_RETRIES,
    _ALERT_BLOCK_RETRY_DELAY_SEC,
    _ALERT_BLOCK_SNAPSHOT_PREFIX,
    _DEFAULT_DILUTE_PULSE_SEC,
    _DEFAULT_DILUTE_SETTLE_SEC,
    _alert_block_retry_count,
    _clear_alert_block_marker,
    _pid_entry_or_none,
)
from ae3lite.application.services.correction_lifecycle import CorrectionLifecycle, CorrectionLifecyclePorts
from ae3lite.application.services.correction_fill_boundary import CorrectionFillBoundary, CorrectionFillBoundaryPorts
from ae3lite.application.services.correction_check import CorrectionCheck, CorrectionCheckPorts
from ae3lite.application.services.correction_measurements import CorrectionMeasurements, CorrectionMeasurementsPorts
from ae3lite.application.services.correction_decision_routing import (
    CorrectionDecisionRouting,
    CorrectionDecisionRoutingPorts,
)
from ae3lite.application.services.correction_dose_stages import CorrectionDoseStages, CorrectionDoseStagesPorts
from ae3lite.application.services.correction_dilution import CorrectionDilution, CorrectionDilutionPorts
from ae3lite.application.services.correction_interrupts import CorrectionInterrupts, CorrectionInterruptsPorts
from ae3lite.application.services.correction_readiness import CorrectionReadiness, CorrectionReadinessPorts
from ae3lite.application.services.correction_diagnostics import CorrectionDiagnostics, CorrectionDiagnosticsPorts
from ae3lite.application.services.correction_limits import CorrectionLimits, CorrectionLimitsPorts
from ae3lite.application.services.correction_observe_stage import CorrectionObserveStage, CorrectionObserveStagePorts
from ae3lite.application.services.correction_runtime_context import (
    CorrectionRuntimeContext,
    CorrectionRuntimeContextPorts,
)


class CorrectionHandler(BaseStageHandler):
    """Handles all ``corr_*`` steps within the correction state machine."""

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        command_gateway: Any,
        planner: Optional[CorrectionPlanner] = None,
        pid_state_repository: Any = None,
        observation_analyzer: Optional[ObservationAnalyzer] = None,
        decision_window_reader: Optional[DecisionWindowReader] = None,
        observation_window_reader: Optional[CorrectionObservationReader] = None,
        transition_policy: Optional[CorrectionTransitionPolicy] = None,
        event_logger: Optional[CorrectionEventLogger] = None,
        sensor_mode_controller: Optional[SensorModeController] = None,
        alert_service: Optional[CorrectionAlertService] = None,
        ec_dose_executor: Optional[CorrectionEcDoseExecutor] = None,
        live_reload_enabled: bool = False,
        completion_clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        super().__init__(
            runtime_monitor=runtime_monitor,
            command_gateway=command_gateway,
            live_reload_enabled=live_reload_enabled,
        )
        self._planner = planner or CorrectionPlanner()
        self._observation_analyzer = observation_analyzer or ObservationAnalyzer()
        self._decision_window_reader = decision_window_reader or DecisionWindowReader(runtime_monitor=runtime_monitor)
        self._observation_window_reader = observation_window_reader or CorrectionObservationReader(
            runtime_monitor=runtime_monitor,
            summarize_window_fn=lambda **kwargs: self._summarize_metric_window(**kwargs),
            log_event_fn=lambda **kwargs: self._log_correction_event(**kwargs),
            logger=_logger,
        )
        self._transition_policy = transition_policy or CorrectionTransitionPolicy()
        self._completion_clock = completion_clock or _utcnow
        # Wrap create_zone_event in a lambda that resolves the symbol lazily
        # from this module's globals. Existing handler tests monkeypatch
        # ``ae3lite.application.handlers.correction.create_zone_event`` to
        # capture event payloads; a direct capture of the module-level symbol
        # at __init__ time would hide those patches from the logger.
        self._event_logger = event_logger or CorrectionEventLogger(
            create_event_fn=lambda zone_id, event_type, payload: create_zone_event(
                zone_id,
                event_type,
                payload,
            ),
            probe_snapshot_context_fn=self._probe_snapshot_context,
        )
        self._pid_state = CorrectionPidState(repository=pid_state_repository, event_logger=self._event_logger)
        self._sensor_mode_controller = sensor_mode_controller or SensorModeController(
            command_gateway=command_gateway,
            event_logger=self._event_logger,
            completion_clock=self._completion_clock,
        )
        # Отчёт кладётся в буфер тика. Наружу его отправляет исполнитель.
        self._alert_service = alert_service or CorrectionAlertService(
            alert_sink_fn=lambda **kwargs: note_upward_report(**kwargs),
        )
        self._ec_dose_executor = ec_dose_executor or CorrectionEcDoseExecutor(
            dispatch_fn=lambda **kwargs: self._dispatch_ec_batch(**kwargs),
            partial_failure_fn=lambda **kwargs: self._maybe_fail_ec_batch_partial(**kwargs),
            raise_error_fn=lambda **kwargs: self._raise_execution_error(**kwargs),
            calibration_fn=lambda **kwargs: self._ml_per_sec_for_ec_item(**kwargs),
            feedback_fn=lambda **kwargs: self._resolve_dose_outcome(**kwargs),
            first_node_uid_fn=lambda commands: self._first_command_node_uid(commands),
        )
        self._correction_lifecycle = CorrectionLifecycle(
            CorrectionLifecyclePorts(
                completion_clock=lambda *args, **kwargs: self._completion_clock(*args, **kwargs),
                enter_correction_after_delay_or_interrupt=lambda *args, **kwargs: (
                    self._enter_correction_after_delay_or_interrupt(*args, **kwargs)
                ),
                run_command_batch_checked=lambda: self._run_command_batch_checked,
                run_wait_observe=lambda *args, **kwargs: self._run_wait_observe(*args, **kwargs),
                sensor_mode_controller=lambda: self._sensor_mode_controller,
            )
        )
        self._correction_fill_boundary = CorrectionFillBoundary(
            CorrectionFillBoundaryPorts(
                check_sensor_consistency=lambda: self._check_sensor_consistency,
                log_correction_event=lambda *args, **kwargs: self._log_correction_event(*args, **kwargs),
                read_level=lambda: self._read_level,
                read_recent_storage_event=lambda: self._read_recent_storage_event,
                readiness_event_payload=lambda *args, **kwargs: self._readiness_event_payload(*args, **kwargs),
                require_runtime_plan=lambda: self._require_runtime_plan,
                resolve_correction_readiness_flags=lambda *args, **kwargs: self._resolve_correction_readiness_flags(
                    *args, **kwargs
                ),
            )
        )
        self._correction_check = CorrectionCheck(
            CorrectionCheckPorts(
                alert_block_max_retries=lambda: _AE_CORRECTION_ALERT_BLOCK_MAX_RETRIES,
                check_no_effect_block=lambda *args, **kwargs: self._check_no_effect_block(*args, **kwargs),
                correction_config=lambda *args, **kwargs: self._correction_config(*args, **kwargs),
                correction_exhausted=lambda *args, **kwargs: self._correction_exhausted(*args, **kwargs),
                enforce_attempt_caps=lambda *args, **kwargs: self._enforce_attempt_caps(*args, **kwargs),
                finalize_dose_plan_routing=lambda *args, **kwargs: self._finalize_dose_plan_routing(*args, **kwargs),
                interrupt_for_control_mode_dosing=lambda *args, **kwargs: self._interrupt_for_control_mode_dosing(
                    *args, **kwargs
                ),
                irrigation_ready_short_circuit=lambda: self._irrigation_ready_short_circuit,
                log_attempt_cap_ignored=lambda *args, **kwargs: self._log_attempt_cap_ignored(*args, **kwargs),
                log_correction_event=lambda *args, **kwargs: self._log_correction_event(*args, **kwargs),
                pid_state=lambda: self._pid_state,
                planner=lambda: self._planner,
                read_measurements_or_interrupt=lambda *args, **kwargs: self._read_measurements_or_interrupt(
                    *args, **kwargs
                ),
                require_runtime_plan=lambda: self._require_runtime_plan,
                reset_ec_pid_for_pipeline=lambda *args, **kwargs: self._reset_ec_pid_for_pipeline(*args, **kwargs),
                resolve_actuators=lambda *args, **kwargs: self._resolve_actuators(*args, **kwargs),
                runtime_config=lambda: self._runtime_config,
                should_log_limit_policy=lambda *args, **kwargs: self._should_log_limit_policy(*args, **kwargs),
                transition_to_deactivate_or_return=lambda *args, **kwargs: self._transition_to_deactivate_or_return(
                    *args, **kwargs
                ),
            )
        )
        self._correction_measurements = CorrectionMeasurements(
            CorrectionMeasurementsPorts(
                correction_retry_delay_sec=lambda *args, **kwargs: self._correction_retry_delay_sec(*args, **kwargs),
                decision_window_reader=lambda: self._decision_window_reader,
                enter_correction_after_delay_or_interrupt=lambda *args, **kwargs: (
                    self._enter_correction_after_delay_or_interrupt(*args, **kwargs)
                ),
                freeze_pid_integral_clock=lambda *args, **kwargs: self._freeze_pid_integral_clock(*args, **kwargs),
                log_correction_event=lambda *args, **kwargs: self._log_correction_event(*args, **kwargs),
                maybe_reactivate_sensor_mode_after_empty_window=lambda *args, **kwargs: (
                    self._maybe_reactivate_sensor_mode_after_empty_window(*args, **kwargs)
                ),
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                observe_fail_safe_transition=lambda: self._observe_fail_safe_transition,
                pid_state=lambda: self._pid_state,
                read_level=lambda: self._read_level,
                runtime_config=lambda: self._runtime_config,
                serialize_metric_ts=lambda *args, **kwargs: self._serialize_metric_ts(*args, **kwargs),
                stage_elapsed_ms=lambda: self._stage_elapsed_ms,
                workflow_ready_values_match=lambda: self._workflow_ready_values_match,
            )
        )
        self._correction_decision_routing = CorrectionDecisionRouting(
            CorrectionDecisionRoutingPorts(
                correction_config=lambda *args, **kwargs: self._correction_config(*args, **kwargs),
                correction_exhausted=lambda *args, **kwargs: self._correction_exhausted(*args, **kwargs),
                correction_retry_delay_sec=lambda *args, **kwargs: self._correction_retry_delay_sec(*args, **kwargs),
                enter_correction_after_delay_or_interrupt=lambda *args, **kwargs: (
                    self._enter_correction_after_delay_or_interrupt(*args, **kwargs)
                ),
                interrupt_for_control_mode_dosing=lambda *args, **kwargs: self._interrupt_for_control_mode_dosing(
                    *args, **kwargs
                ),
                log_attempt_cap_ignored=lambda *args, **kwargs: self._log_attempt_cap_ignored(*args, **kwargs),
                log_correction_event=lambda *args, **kwargs: self._log_correction_event(*args, **kwargs),
                maybe_emit_pid_output_zone_event=lambda *args, **kwargs: self._maybe_emit_pid_output_zone_event(
                    *args, **kwargs
                ),
                pid_state=lambda: self._pid_state,
                planner=lambda: self._planner,
                readiness_event_payload=lambda *args, **kwargs: self._readiness_event_payload(*args, **kwargs),
                recirc_pipeline_open=lambda: self._recirc_pipeline_open,
                record_dose_clamp_metrics=lambda *args, **kwargs: self._record_dose_clamp_metrics(*args, **kwargs),
                record_dual_calibration_mismatch_observability=lambda *args, **kwargs: (
                    self._record_dual_calibration_mismatch_observability(*args, **kwargs)
                ),
                runtime_config=lambda: self._runtime_config,
                transition_to_deactivate_or_return=lambda *args, **kwargs: self._transition_to_deactivate_or_return(
                    *args, **kwargs
                ),
            )
        )
        self._correction_dose_stages = CorrectionDoseStages(
            CorrectionDoseStagesPorts(
                completion_anchored_window=lambda *args, **kwargs: self._completion_anchored_window(*args, **kwargs),
                correction_config=lambda *args, **kwargs: self._correction_config(*args, **kwargs),
                dose_accounting_context=lambda *args, **kwargs: self._dose_accounting_context(*args, **kwargs),
                ec_dose_executor=lambda: self._ec_dose_executor,
                ensure_sensor_mode_active_for_dosing=lambda *args, **kwargs: self._ensure_sensor_mode_active_for_dosing(
                    *args, **kwargs
                ),
                enter_correction_after_delay_or_interrupt=lambda *args, **kwargs: (
                    self._enter_correction_after_delay_or_interrupt(*args, **kwargs)
                ),
                interrupt_for_control_mode_dosing=lambda *args, **kwargs: self._interrupt_for_control_mode_dosing(
                    *args, **kwargs
                ),
                log_correction_event=lambda *args, **kwargs: self._log_correction_event(*args, **kwargs),
                mark_accounted_dose_commands=lambda *args, **kwargs: self._mark_accounted_dose_commands(
                    *args, **kwargs
                ),
                ml_per_sec_for_actuator=lambda *args, **kwargs: self._ml_per_sec_for_actuator(*args, **kwargs),
                ml_per_sec_for_ec_item=lambda *args, **kwargs: self._ml_per_sec_for_ec_item(*args, **kwargs),
                observation_analyzer=lambda: self._observation_analyzer,
                observe_seq=lambda *args, **kwargs: self._observe_seq(*args, **kwargs),
                pid_state=lambda: self._pid_state,
                require_runtime_plan=lambda: self._require_runtime_plan,
                resolve_actuators=lambda *args, **kwargs: self._resolve_actuators(*args, **kwargs),
                resolve_dose_outcome=lambda *args, **kwargs: self._resolve_dose_outcome(*args, **kwargs),
                run_command_batch_checked=lambda: self._run_command_batch_checked,
                runtime_config=lambda: self._runtime_config,
                create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            )
        )
        self._correction_dilution = CorrectionDilution(
            CorrectionDilutionPorts(
                completion_anchored_window=lambda *args, **kwargs: self._completion_anchored_window(*args, **kwargs),
                enter_correction_after_delay_or_interrupt=lambda *args, **kwargs: (
                    self._enter_correction_after_delay_or_interrupt(*args, **kwargs)
                ),
                log_correction_event=lambda *args, **kwargs: self._log_correction_event(*args, **kwargs),
                pid_state=lambda: self._pid_state,
                read_level=lambda: self._read_level,
                require_runtime_plan=lambda: self._require_runtime_plan,
                run_command_batch_checked=lambda: self._run_command_batch_checked,
            )
        )
        self._correction_interrupts = CorrectionInterrupts(
            CorrectionInterruptsPorts(
                deadline_reached=lambda: self._deadline_reached,
                deadline_too_close_for_irr_probe=lambda: self._deadline_too_close_for_irr_probe,
                handle_control_mode_flow_path_interrupt=lambda: self._handle_control_mode_flow_path_interrupt,
                irr_probe_deadline_budget_sec=lambda: self._irr_probe_deadline_budget_sec,
                log_correction_event=lambda *args, **kwargs: self._log_correction_event(*args, **kwargs),
                probe_irr_state=lambda: self._probe_irr_state,
                read_recent_storage_event=lambda: self._read_recent_storage_event,
                reconciled_estop_event_ids=lambda: self._reconciled_estop_event_ids,
                record_deadline_target_outcome=lambda: self._record_deadline_target_outcome,
                remaining_stage_time_sec=lambda: self._remaining_stage_time_sec,
                require_runtime_plan=lambda: self._require_runtime_plan,
                target_outcome_on_deadline=lambda: self._target_outcome_on_deadline,
                transition_policy=lambda: self._transition_policy,
            )
        )
        self._correction_readiness = CorrectionReadiness(
            CorrectionReadinessPorts(
                irrigation_ready_short_circuit=lambda: self._irrigation_ready_short_circuit,
                planner=lambda: self._planner,
                read_target_metric_window=lambda: self._read_target_metric_window,
                require_runtime_plan=lambda: self._require_runtime_plan,
                runtime_config=lambda: self._runtime_config,
                workflow_ready_values_match=lambda: self._workflow_ready_values_match,
            )
        )
        self._correction_diagnostics = CorrectionDiagnostics(
            CorrectionDiagnosticsPorts(
                log_correction_event=lambda *args, **kwargs: self._log_correction_event(*args, **kwargs),
                create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
                datetime_type=lambda: datetime,
            )
        )
        self._correction_limits = CorrectionLimits(
            CorrectionLimitsPorts(
                alert_service=lambda: self._alert_service,
                log_correction_event=lambda *args, **kwargs: self._log_correction_event(*args, **kwargs),
                require_runtime_plan=lambda: self._require_runtime_plan,
                runtime_config=lambda: self._runtime_config,
                transition_policy=lambda: self._transition_policy,
                transition_to_deactivate_or_return=lambda *args, **kwargs: self._transition_to_deactivate_or_return(
                    *args, **kwargs
                ),
            )
        )
        self._correction_observe_stage = CorrectionObserveStage(
            CorrectionObserveStagePorts(
                correction_config=lambda *args, **kwargs: self._correction_config(*args, **kwargs),
                correction_retry_delay_sec=lambda *args, **kwargs: self._correction_retry_delay_sec(*args, **kwargs),
                enter_correction_after_delay_or_interrupt=lambda *args, **kwargs: (
                    self._enter_correction_after_delay_or_interrupt(*args, **kwargs)
                ),
                log_correction_event=lambda *args, **kwargs: self._log_correction_event(*args, **kwargs),
                no_effect_limit_reached=lambda *args, **kwargs: self._no_effect_limit_reached(*args, **kwargs),
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                observation_analyzer=lambda: self._observation_analyzer,
                observation_window_reader=lambda: self._observation_window_reader,
                pid_state=lambda: self._pid_state,
                require_runtime_plan=lambda: self._require_runtime_plan,
                runtime_config=lambda: self._runtime_config,
                should_reset_attempt_counters_on_reaction=lambda *args, **kwargs: (
                    self._should_reset_attempt_counters_on_reaction(*args, **kwargs)
                ),
            )
        )
        self._correction_runtime_context = CorrectionRuntimeContext(
            CorrectionRuntimeContextPorts(
                require_runtime_plan=lambda: self._require_runtime_plan,
                runtime_config=lambda: self._runtime_config,
            )
        )

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        corr = task.correction
        if corr is None:
            raise TaskExecutionError(
                "corr_state_missing",
                f"У задачи {task.id} активен correction stage, но correction state отсутствует",
            )

        window_id = CorrectionEventLogger.correction_window_id(task=task)
        with log_context_scope(
            zone_id=task.zone_id,
            task_id=getattr(task, "id", None),
            correction_window_id=window_id,
        ):
            return await self._run_correction_stage(
                task=task,
                plan=plan,
                stage_def=stage_def,
                now=now,
                corr=corr,
            )

    async def _run_correction_stage(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
        corr: CorrectionState,
    ) -> StageOutcome:
        # Phase 5.5: live-mode hot-swap. If zone is in `live` and revision
        # advanced, `_checkpoint` returns a fresh `CommandPlan` (otherwise
        # returns the existing one). Every `_run_*` step and helper that reads
        # `plan.runtime` or `plan.named_plans` transparently sees refreshed
        # config without changing their signatures.
        plan = await self._checkpoint(task=task, plan=plan, now=now)

        solution_fill_completion_outcome = await self._interrupt_for_solution_fill_completion(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
        )
        if solution_fill_completion_outcome is not None:
            return solution_fill_completion_outcome

        deadline_outcome = await self._interrupt_for_stage_deadline(task=task, plan=plan, corr=corr, now=now)
        if deadline_outcome is not None:
            return deadline_outcome

        estop_outcome = await self._interrupt_for_emergency_stop(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
        )
        if estop_outcome is not None:
            return estop_outcome

        step = corr.corr_step
        if step not in {"corr_activate", "corr_wait_stable", "corr_deactivate", "corr_done"}:
            imminent_probe_outcome = self._interrupt_for_imminent_flow_probe_deadline(
                task=task,
                plan=plan,
                now=now,
            )
            if imminent_probe_outcome is not None:
                return imminent_probe_outcome
            try:
                await self._assert_flow_path_active(task=task, plan=plan, now=now)
            except TaskExecutionError as exc:
                raced_completion_outcome = await self._interrupt_for_raced_solution_fill_completion(
                    task=task,
                    plan=plan,
                    corr=corr,
                    now=now,
                    exc=exc,
                )
                if raced_completion_outcome is not None:
                    return raced_completion_outcome
                raise
        try:
            if step == "corr_activate":
                return await self._run_activate(task=task, plan=plan, corr=corr, now=now)
            if step == "corr_wait_stable":
                return self._run_wait_stable(task=task, plan=plan, corr=corr, now=now)
            if step == "corr_check":
                return await self._run_check(task=task, plan=plan, corr=corr, now=now)
            if step == "corr_dose_ec":
                return await self._run_dose_ec(task=task, plan=plan, corr=corr, now=now)
            if step == "corr_wait_ec":
                return await self._run_wait_ec(task=task, plan=plan, corr=corr, now=now)
            if step == "corr_dose_ph":
                return await self._run_dose_ph(task=task, plan=plan, corr=corr, now=now)
            if step == "corr_wait_ph":
                return await self._run_wait_ph(task=task, plan=plan, corr=corr, now=now)
            if step == "corr_dilute_pulse":
                return await self._run_dilute_pulse(task=task, plan=plan, corr=corr, now=now)
            if step == "corr_dilute_settle":
                return await self._run_dilute_settle(task=task, plan=plan, corr=corr, now=now)
            if step == "corr_deactivate":
                return await self._run_deactivate(task=task, plan=plan, corr=corr, now=now)
            if step == "corr_done":
                return self._run_done(corr=corr)
        except TaskExecutionError as exc:
            deadline_outcome = await self._interrupt_after_command_admission_failure(
                task=task,
                plan=plan,
                corr=corr,
                now=now,
                exc=exc,
            )
            if deadline_outcome is not None:
                return deadline_outcome
            raise

        raise TaskExecutionError(
            "ae3_unknown_corr_step",
            f"Неизвестный correction step={step!r}",
        )

    # ── Step handlers ───────────────────────────────────────────────

    async def _run_activate(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return await self._correction_lifecycle.run_activate(task=task, plan=plan, corr=corr, now=now)

    def _run_wait_stable(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return self._correction_lifecycle.run_wait_stable(task=task, plan=plan, corr=corr, now=now)

    async def _interrupt_for_solution_fill_completion(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome | None:
        return await self._correction_fill_boundary.interrupt_for_solution_fill_completion(
            task=task, plan=plan, corr=corr, now=now
        )

    _solution_fill_completion_next_stage = staticmethod(CorrectionFillBoundary.solution_fill_completion_next_stage)

    async def _solution_fill_completion_outcome(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return await self._correction_fill_boundary.solution_fill_completion_outcome(
            task=task, plan=plan, corr=corr, now=now
        )

    async def _interrupt_for_raced_solution_fill_completion(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        exc: TaskExecutionError,
    ) -> StageOutcome | None:
        return await self._correction_fill_boundary.interrupt_for_raced_solution_fill_completion(
            task=task, plan=plan, corr=corr, now=now, exc=exc
        )

    async def _run_check(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return await self._correction_check.run_check(task=task, plan=plan, corr=corr, now=now)

    # ── _run_check helpers (B1 decomposition) ──────────────────────────

    async def _freeze_pid_integral_clock(
        self,
        *,
        task: Any,
        pid_state: Mapping[str, Any],
        now: datetime,
    ) -> None:
        return await self._correction_check.freeze_pid_integral_clock(task=task, pid_state=pid_state, now=now)

    async def _read_measurements_or_interrupt(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        runtime: Mapping[str, Any],
        correction_cfg: Mapping[str, Any],
        process_cfg: Mapping[str, Any],
        pid_state: Mapping[str, Any],
        target_ph: float,
        target_ec: float,
        max_age: int,
    ) -> _MeasurementSnapshot | StageOutcome:
        return await self._correction_measurements.read_measurements_or_interrupt(
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

    async def _finalize_dose_plan_routing(
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
        return await self._correction_decision_routing.finalize_dose_plan_routing(
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

    async def _dispatch_ec_batch(
        self,
        *,
        task: Any,
        commands: Sequence[PlannedCommand],
        now: datetime,
        checked: bool,
    ) -> Mapping[str, Any]:
        if checked:
            return await self._run_command_batch_checked(task=task, commands=commands, now=now)
        await self._ensure_command_targets_online(task=task, commands=commands)
        return await self._command_gateway.run_batch(task=task, commands=commands, now=now)

    async def _run_dose_ec(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return await self._correction_dose_stages.run_dose_ec(task=task, plan=plan, corr=corr, now=now)

    async def _run_wait_ec(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return await self._correction_lifecycle.run_wait_ec(task=task, plan=plan, corr=corr, now=now)

    async def _run_dose_ph(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return await self._correction_dose_stages.run_dose_ph(task=task, plan=plan, corr=corr, now=now)

    async def _run_wait_ph(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return await self._correction_lifecycle.run_wait_ph(task=task, plan=plan, corr=corr, now=now)

    async def _run_deactivate(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return await self._correction_lifecycle.run_deactivate(task=task, plan=plan, corr=corr, now=now)

    async def _run_dilute_pulse(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return await self._correction_dilution.run_dilute_pulse(task=task, plan=plan, corr=corr, now=now)

    async def _run_dilute_settle(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        return await self._correction_dilution.run_dilute_settle(task=task, plan=plan, corr=corr, now=now)

    async def _reset_ec_pid_for_pipeline(
        self,
        *,
        task: Any,
        corr: CorrectionState,
        reason: str,
        now: datetime,
    ) -> None:
        return await self._correction_dilution.reset_ec_pid_for_pipeline(task=task, corr=corr, reason=reason, now=now)

    def _run_done(self, *, corr: CorrectionState) -> StageOutcome:
        return self._correction_lifecycle.run_done(corr=corr)

    async def _interrupt_for_emergency_stop(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome | None:
        return await self._correction_interrupts.interrupt_for_emergency_stop(task=task, plan=plan, corr=corr, now=now)

    async def _interrupt_for_control_mode_dosing(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
    ) -> StageOutcome | None:
        return await self._correction_interrupts.interrupt_for_control_mode_dosing(task=task, plan=plan, now=now)

    _readiness_event_payload = staticmethod(CorrectionReadiness.readiness_event_payload)

    async def _resolve_correction_readiness_flags(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> tuple[bool, bool] | None:
        return await self._correction_readiness.resolve_correction_readiness_flags(
            task=task, plan=plan, now=now, runtime=runtime
        )

    _record_dose_clamp_metrics = staticmethod(CorrectionDiagnostics.record_dose_clamp_metrics)

    async def _record_dual_calibration_mismatch_observability(
        self,
        *,
        task: Any,
        corr: CorrectionState,
        dose_plan: DosePlan,
    ) -> None:
        return await self._correction_diagnostics.record_dual_calibration_mismatch_observability(
            task=task, corr=corr, dose_plan=dose_plan
        )

    def _resolve_dose_completed_at(self) -> datetime:
        return self._correction_lifecycle.resolve_dose_completed_at()

    def _completion_anchored_window(
        self,
        *,
        now: datetime,
        wait_sec: float,
    ) -> tuple[datetime, datetime, float]:
        return self._correction_lifecycle.completion_anchored_window(now=now, wait_sec=wait_sec)

    # ── Helpers ─────────────────────────────────────────────────────

    async def _ensure_sensor_mode_active_for_dosing(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        failed_node_uid: str | None,
        failed_channel: str | None,
        retry_cmd: str,
    ) -> Any:
        return await self._correction_lifecycle.ensure_sensor_mode_active_for_dosing(
            task=task,
            plan=plan,
            corr=corr,
            now=now,
            failed_node_uid=failed_node_uid,
            failed_channel=failed_channel,
            retry_cmd=retry_cmd,
        )

    async def _assert_flow_path_active(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        return await self._correction_interrupts.assert_flow_path_active(task=task, plan=plan, now=now)

    def _expected_flow_path_state(self, *, current_stage: str) -> Mapping[str, bool] | None:
        return self._correction_interrupts.expected_flow_path_state(current_stage=current_stage)

    async def _maybe_reactivate_sensor_mode_after_empty_window(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        ph: DecisionWindowResult,
        ec: DecisionWindowResult,
    ) -> StageOutcome | None:
        return await self._correction_lifecycle.maybe_reactivate_sensor_mode_after_empty_window(
            task=task, plan=plan, corr=corr, now=now, ph=ph, ec=ec
        )

    def _transition_to_deactivate_or_return(
        self,
        *,
        corr: CorrectionState,
        success: bool,
    ) -> StageOutcome:
        return self._correction_interrupts.transition_to_deactivate_or_return(corr=corr, success=success)

    async def _maybe_fail_ec_batch_partial(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        seq: Sequence[Mapping[str, Any]],
        mode: str,
        failed_index: int,
        error_code: str,
        error_message: str,
        batch_result: Mapping[str, Any] | None,
    ) -> StageOutcome | None:
        """CORRECTION_CYCLE_SPEC §6.2 MVP: detect partial EC batch failure.

        When steps ``0..N-1`` already succeeded and step ``N`` fails, emit
        ``EC_BATCH_PARTIAL_FAILURE``, mark the correction window failed, and
        do **not** treat EC target as reached. Auto-enqueue of post-irrigation
        chemistry recovery is intentionally out of scope (stages removed).
        """
        failure = describe_partial_ec_failure(
            seq=seq,
            mode=mode,
            failed_index=failed_index,
            error_code=error_code,
            batch_result=batch_result,
        )
        if failure is None:
            return None
        idx = failure.failed_index
        successful = failure.successful_components
        failed_component = failure.failed_component
        remaining = failure.remaining_components
        failed_item = failure.failed_item

        runtime = self._require_runtime_plan(plan=plan)
        current_ec = await self._pid_state.read_measurement_for_event(
            zone_id=task.zone_id,
            pid_type="ec",
        )
        payload = {
            "successful_components": successful,
            "failed_component": failed_component,
            "remaining_components": remaining,
            "failed_index": idx,
            "mode": mode,
            "status": "degraded",
            "error_code": error_code,
            "error_message": error_message,
            "target_ec": self._runtime_config.effective_ec_target(task=task, runtime=runtime),
            "current_ec": current_ec,
            "node_uid": str(failed_item.get("node_uid") or "").strip() or None,
            "channel": str(failed_item.get("channel") or "").strip() or None,
            "ec_component": corr.ec_component,
            "source": "correction_handler",
        }
        await self._log_correction_event(
            zone_id=task.zone_id,
            event_type="EC_BATCH_PARTIAL_FAILURE",
            task=task,
            corr=corr,
            payload=payload,
        )
        CORRECTION_EC_BATCH_PARTIAL_FAILURE.labels(mode=mode).inc()
        _logger.warning(
            "EC batch partial failure zone=%s mode=%s failed=%s successful=%s remaining=%s code=%s",
            getattr(task, "zone_id", None),
            mode,
            failed_component,
            successful,
            remaining,
            error_code,
        )
        # Keep index at the failed step for observability; do not advance.
        next_corr = replace(corr, ec_current_seq_index=idx)
        outcome = self._transition_to_deactivate_or_return(corr=next_corr, success=False)
        result_task = (batch_result or {}).get("task")
        if result_task is not None and result_task is not task:
            return replace(outcome, task_override=result_task)
        return outcome

    async def _correction_exhausted(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
    ) -> StageOutcome:
        return await self._correction_limits.correction_exhausted(task=task, plan=plan, corr=corr)

    async def _interrupt_for_stage_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome | None:
        return await self._correction_interrupts.interrupt_for_stage_deadline(task=task, plan=plan, corr=corr, now=now)

    async def _interrupt_after_command_admission_failure(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        exc: TaskExecutionError,
    ) -> StageOutcome | None:
        return await self._correction_interrupts.interrupt_after_command_admission_failure(
            task=task, plan=plan, corr=corr, now=now, exc=exc
        )

    async def _stage_deadline_transition_outcome(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        completion_reason: str = "stage_deadline",
    ) -> StageOutcome | None:
        return await self._correction_interrupts.stage_deadline_transition_outcome(
            task=task, plan=plan, corr=corr, now=now, completion_reason=completion_reason
        )

    def _interrupt_for_imminent_flow_probe_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
    ) -> StageOutcome | None:
        return self._correction_interrupts.interrupt_for_imminent_flow_probe_deadline(task=task, plan=plan, now=now)

    def _enter_correction_after_delay_or_interrupt(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        due_delay_sec: float,
        task_override: Any | None = None,
    ) -> StageOutcome:
        return self._correction_interrupts.enter_correction_after_delay_or_interrupt(
            task=task, plan=plan, corr=corr, now=now, due_delay_sec=due_delay_sec, task_override=task_override
        )

    def _interrupt_for_imminent_retry_then_probe_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        due_delay_sec: float,
        task_override: Any | None = None,
    ) -> StageOutcome | None:
        return self._correction_interrupts.interrupt_for_imminent_retry_then_probe_deadline(
            task=task, plan=plan, now=now, due_delay_sec=due_delay_sec, task_override=task_override
        )

    def _enforce_attempt_caps(self, *, task: Any) -> bool:
        return self._correction_limits.enforce_attempt_caps(task=task)

    def _check_no_effect_block(
        self,
        *,
        task: Any,
        correction_cfg: Mapping[str, Any],
        process_cfg: Mapping[str, Any],
        pid_state: Mapping[str, Any],
    ) -> Optional[dict[str, Any]]:
        return self._correction_limits.check_no_effect_block(
            task=task, correction_cfg=correction_cfg, process_cfg=process_cfg, pid_state=pid_state
        )

    def _should_reset_attempt_counters_on_reaction(self, *, task: Any) -> bool:
        # Попытки считаются только для последовательных no-effect циклов.
        # Любая наблюдаемая реакция должна сбрасывать окно попыток, независимо от stage.
        return self._correction_limits.should_reset_attempt_counters_on_reaction(task=task)

    def _should_log_limit_policy(self, *, task: Any, corr: CorrectionState) -> bool:
        return self._correction_limits.should_log_limit_policy(task=task, corr=corr)

    async def _log_attempt_cap_ignored(
        self,
        *,
        task: Any,
        corr: CorrectionState,
        cap_type: str,
        current_value: int,
        limit_value: int,
    ) -> None:
        return await self._correction_limits.log_attempt_cap_ignored(
            task=task, corr=corr, cap_type=cap_type, current_value=current_value, limit_value=limit_value
        )

    def _serialize_metric_ts(self, value: Any) -> str | None:
        return self._correction_diagnostics.serialize_metric_ts(value=value)

    async def _run_wait_observe(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        pid_type: str,
        sensor_type: str,
    ) -> StageOutcome:
        return await self._correction_observe_stage.run_wait_observe(
            task=task, plan=plan, corr=corr, now=now, pid_type=pid_type, sensor_type=sensor_type
        )

    # ── _run_wait_observe helpers (B1 decomposition) ───────────────────

    async def _read_observation_window_or_interrupt(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        pid_type: str,
        sensor_type: str,
    ) -> ObservationWindow | StageOutcome:
        return await self._correction_observe_stage.read_observation_window_or_interrupt(
            task=task, plan=plan, corr=corr, now=now, pid_type=pid_type, sensor_type=sensor_type
        )

    async def _finalize_observation_result(
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
        return await self._correction_observe_stage.finalize_observation_result(
            task=task, plan=plan, corr=corr, now=now, pid_type=pid_type, sensor_type=sensor_type, window=window
        )

    def _expected_cross_coupling_ph(self, *, corr: CorrectionState, process_cfg: Mapping[str, Any]) -> float:
        return self._correction_dose_stages.expected_cross_coupling_ph(corr=corr, process_cfg=process_cfg)

    async def _no_effect_limit_reached(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        pid_type: str,
        baseline_value: float,
        observed_value: float,
        expected_effect: float,
        actual_effect: float,
        threshold_effect: float,
        no_effect_limit: int,
    ) -> StageOutcome:
        return await self._correction_limits.no_effect_limit_reached(
            task=task,
            plan=plan,
            corr=corr,
            pid_type=pid_type,
            baseline_value=baseline_value,
            observed_value=observed_value,
            expected_effect=expected_effect,
            actual_effect=actual_effect,
            threshold_effect=threshold_effect,
            no_effect_limit=no_effect_limit,
        )

    async def _log_correction_event(
        self,
        *,
        zone_id: int,
        event_type: str,
        task: Any | None = None,
        corr: CorrectionState | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        await self._event_logger.log(
            zone_id=zone_id,
            event_type=event_type,
            task=task,
            corr=corr,
            payload=payload,
        )

    def _observe_seq(self, *, corr: CorrectionState, pid_type: str, after_dose: bool = False) -> int | None:
        return CorrectionEventLogger.observe_seq(
            corr=corr,
            pid_type=pid_type,
            after_dose=after_dose,
        )

    def _correction_config(self, *, plan: Any, task: Any) -> Mapping[str, Any]:
        return self._correction_runtime_context.correction_config(plan=plan, task=task)

    def _resolve_actuators(self, *, runtime: Mapping[str, Any], task: Any, plan: Any) -> dict:
        return self._correction_runtime_context.resolve_actuators(runtime=runtime, task=task, plan=plan)

    def _ml_per_sec_for_actuator(self, actuator: Any) -> float:
        return dose_accounting.ml_per_sec_for_actuator(actuator)

    def _ml_per_sec_for_ec_item(self, *, actuators: Mapping[str, Any], item: Mapping[str, Any]) -> float:
        return dose_accounting.ml_per_sec_for_ec_item(actuators=actuators, item=item)

    def _dose_accounting_context(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        pid_type: str,
    ) -> Mapping[str, Any]:
        return self._correction_runtime_context.dose_accounting_context(
            task=task, plan=plan, corr=corr, pid_type=pid_type
        )

    async def _mark_accounted_dose_commands(
        self,
        *,
        batch_result: Mapping[str, Any],
        now: datetime,
    ) -> None:
        if getattr(self._pid_state, "_repository", None) is None:
            return
        repository = getattr(self._command_gateway, "_command_repository", None)
        await dose_accounting.mark_accounted_dose_commands(
            batch_result=batch_result,
            now=now,
            mark_dose_accounted=getattr(repository, "mark_dose_accounted", None),
            logger=_logger,
        )

    def _resolve_dose_outcome(
        self,
        *,
        planned_ml: float,
        planned_duration_ms: int,
        ml_per_sec: float,
        batch_result: Mapping[str, Any],
        status_index: int = 0,
    ) -> tuple[float, int, bool]:
        return dose_accounting.resolve_dose_outcome(
            planned_ml=planned_ml,
            planned_duration_ms=planned_duration_ms,
            ml_per_sec=ml_per_sec,
            batch_result=batch_result,
            status_index=status_index,
        )

    async def _maybe_emit_pid_output_zone_event(
        self,
        *,
        zone_id: int,
        corr_step: str,
        dose_plan: DosePlan,
        pid_state_before: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
        target_ph: float,
        target_ec: float,
        now: datetime,
    ) -> None:
        return await self._correction_diagnostics.maybe_emit_pid_output_zone_event(
            zone_id=zone_id,
            corr_step=corr_step,
            dose_plan=dose_plan,
            pid_state_before=pid_state_before,
            current_ph=current_ph,
            current_ec=current_ec,
            target_ph=target_ph,
            target_ec=target_ec,
            now=now,
        )

    def _normalize_timestamp(self, value: datetime | None) -> datetime | None:
        return self._correction_lifecycle.normalize_timestamp(value=value)

    def _correction_retry_delay_sec(
        self,
        *,
        correction_cfg: Any,
        key: str,
    ) -> float:
        return self._correction_runtime_context.correction_retry_delay_sec(correction_cfg=correction_cfg, key=key)
