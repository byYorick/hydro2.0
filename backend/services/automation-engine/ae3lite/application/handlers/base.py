"""Базовый handler с общими операциями probe, sensor и level."""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, Mapping, Optional, Sequence

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.config.schema import RuntimePlan
from ae3lite.application.services.correction_pipeline import irrigation_component_budget_guard
from ae3lite.application.services.stage_runtime_config import StageRuntimeConfig, _MISSING_CONFIG
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError
from ae3lite.application.level_monitor import level_snapshot_aliases
from ae3lite.domain.services.metric_window_validator import (
    decision_window_bounds_reason,
    sensor_value_in_bounds,
)
from ae3lite.domain.services.correction_planner import CorrectionPlanner
from ae3lite.domain.services.telemetry_window_summary import (
    decision_window_since_ts as _telemetry_decision_window_since_ts,
    summarize_window as _telemetry_summarize_window,
    validate_window_timing as _validate_telemetry_window_timing,
)
from ae3lite.infrastructure.metrics import (
    EMERGENCY_STOP_RECONCILE,
    FAIL_SAFE_TRANSITION,
    IRR_PROBE_DEFERRED,
    IRR_PROBE_STREAK_EXHAUSTED,
    NODE_REBOOT_DETECTED,
)
from ae3lite.hydraulics.failure_report import note_upward_report
from common.db import create_zone_event
from common.service_logs import send_service_log


_logger = logging.getLogger(__name__)


from ae3lite.application.services.stage_timing import _utc_naive_dt


from ae3lite.application.services.stage_checkpoint import StageCheckpoint, StageCheckpointPorts
from ae3lite.application.services.stage_command_boundary import StageCommandBoundary, StageCommandBoundaryPorts
from ae3lite.application.services.stage_flow_safety import StageFlowSafety, StageFlowSafetyPorts
from ae3lite.application.services.stage_probe_snapshot import StageProbeSnapshot, StageProbeSnapshotPorts
from ae3lite.application.services.stage_level_reader import StageLevelReader, StageLevelReaderPorts
from ae3lite.application.services.stage_timing import StageTiming, StageTimingPorts
from ae3lite.application.services.stage_readiness import StageReadiness, StageReadinessPorts
from ae3lite.application.services.stage_metric_window import StageMetricWindow, StageMetricWindowPorts
from ae3lite.application.services.stage_probe_runner import StageProbeRunner, StageProbeRunnerPorts
from ae3lite.application.services.stage_probe_backoff import StageProbeBackoff, StageProbeBackoffPorts
from ae3lite.application.services.stage_probe_observability import StageProbeObservability, StageProbeObservabilityPorts
from ae3lite.application.services.stage_deadline_outcome import StageDeadlineOutcome, StageDeadlineOutcomePorts


class BaseStageHandler:
    """Предоставляет переиспользуемые helper'ы чтения сенсоров для check-handler'ов.

    Подклассы реализуют ``run()`` и возвращают :class:`StageOutcome`.
    """

    _IRR_STATE_PROBE_RETRY_COUNT = 1
    _IRR_STATE_PROBE_RETRY_DELAY_SEC = 0.5
    _IRR_PROBE_FAILURE_STREAK_LIMIT = 5
    _IRR_PROBE_NODE_UNREACHABLE_HEARTBEAT_AGE_SEC = 30.0

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        command_gateway: Any,
        task_repository: Any = None,
        live_reload_enabled: bool = False,
    ) -> None:
        self._runtime_config = StageRuntimeConfig()
        self._runtime_monitor = runtime_monitor
        self._command_gateway = command_gateway
        self._task_repository = task_repository
        self._reconciled_estop_event_ids: set[int] = set()
        # Phase 5: live-mode checkpoint toggle. Default False → handler tests
        # that don't wire a real DB pool see no live-reload noise. Production
        # `WorkflowRouter` enables it when constructing handlers.
        self._live_reload_enabled = live_reload_enabled
        self._stage_checkpoint = StageCheckpoint(
            StageCheckpointPorts(
                live_reload_enabled=lambda: self._live_reload_enabled,
                create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            )
        )
        self._stage_command_boundary = StageCommandBoundary(
            StageCommandBoundaryPorts(
                remap_execution_error=lambda *args, **kwargs: self._remap_execution_error(*args, **kwargs),
                command_gateway=lambda: self._command_gateway,
                extract_irr_probe_node_uid=lambda *args, **kwargs: self._extract_irr_probe_node_uid(*args, **kwargs),
                runtime_monitor=lambda: self._runtime_monitor,
            )
        )
        self._stage_flow_safety = StageFlowSafety(
            StageFlowSafetyPorts(
                require_runtime_plan=lambda *args, **kwargs: self._require_runtime_plan(*args, **kwargs),
                run_command_batch_checked=lambda *args, **kwargs: self._run_command_batch_checked(*args, **kwargs),
                probe_irr_state=lambda *args, **kwargs: self._probe_irr_state(*args, **kwargs),
                read_level=lambda *args, **kwargs: self._read_level(*args, **kwargs),
                runtime_config=lambda: self._runtime_config,
                runtime_monitor=lambda: self._runtime_monitor,
                stage_entered_at=lambda *args, **kwargs: self._stage_entered_at(*args, **kwargs),
                create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            )
        )
        self._stage_probe_snapshot = StageProbeSnapshot(
            StageProbeSnapshotPorts(
                runtime_config=lambda: self._runtime_config,
            )
        )
        self._stage_level_reader = StageLevelReader(
            StageLevelReaderPorts(
                raise_execution_error=lambda *args, **kwargs: self._raise_execution_error(*args, **kwargs),
                read_probe_level_snapshot=lambda *args, **kwargs: self._read_probe_level_snapshot(*args, **kwargs),
                runtime_monitor=lambda: self._runtime_monitor,
            )
        )
        self._stage_timing = StageTiming(
            StageTimingPorts(
                irr_state_probe_retry_count=lambda: self._IRR_STATE_PROBE_RETRY_COUNT,
                irr_state_probe_retry_delay_sec=lambda: self._IRR_STATE_PROBE_RETRY_DELAY_SEC,
                runtime_config=lambda: self._runtime_config,
            )
        )
        self._stage_readiness = StageReadiness(
            StageReadinessPorts(
                read_target_metric_window=lambda *args, **kwargs: self._read_target_metric_window(*args, **kwargs),
                require_runtime_plan=lambda *args, **kwargs: self._require_runtime_plan(*args, **kwargs),
                runtime_config=lambda: self._runtime_config,
            )
        )
        self._stage_metric_window = StageMetricWindow(
            StageMetricWindowPorts(
                runtime_monitor=lambda: self._runtime_monitor,
            )
        )
        self._stage_probe_runner = StageProbeRunner(
            StageProbeRunnerPorts(
                irr_probe_node_unreachable_heartbeat_age_sec=lambda: self._IRR_PROBE_NODE_UNREACHABLE_HEARTBEAT_AGE_SEC,
                irr_state_probe_retry_count=lambda: self._IRR_STATE_PROBE_RETRY_COUNT,
                irr_state_probe_retry_delay_sec=lambda: self._IRR_STATE_PROBE_RETRY_DELAY_SEC,
                log_probe_failure_event=lambda *args, **kwargs: self._log_probe_failure_event(*args, **kwargs),
                maybe_emit_node_reboot_event=lambda *args, **kwargs: self._maybe_emit_node_reboot_event(
                    *args, **kwargs
                ),
                raise_execution_error=lambda *args, **kwargs: self._raise_execution_error(*args, **kwargs),
                remember_probe_state=lambda *args, **kwargs: self._remember_probe_state(*args, **kwargs),
                require_runtime_plan=lambda *args, **kwargs: self._require_runtime_plan(*args, **kwargs),
                run_command_batch_checked=lambda *args, **kwargs: self._run_command_batch_checked(*args, **kwargs),
                runtime_config=lambda: self._runtime_config,
                runtime_monitor=lambda: self._runtime_monitor,
            )
        )
        self._stage_probe_backoff = StageProbeBackoff(
            StageProbeBackoffPorts(
                irr_probe_failure_streak_limit=lambda: self._IRR_PROBE_FAILURE_STREAK_LIMIT,
                irr_probe_node_unreachable_heartbeat_age_sec=lambda: self._IRR_PROBE_NODE_UNREACHABLE_HEARTBEAT_AGE_SEC,
                extract_irr_probe_node_uid=lambda *args, **kwargs: self._extract_irr_probe_node_uid(*args, **kwargs),
                probe_irr_state=lambda *args, **kwargs: self._probe_irr_state(*args, **kwargs),
                runtime_monitor=lambda: self._runtime_monitor,
                task_repository=lambda: self._task_repository,
                create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            )
        )
        self._stage_probe_observability = StageProbeObservability(
            StageProbeObservabilityPorts(
                extract_irr_probe_node_uid=lambda *args, **kwargs: self._extract_irr_probe_node_uid(*args, **kwargs),
                runtime_monitor=lambda: self._runtime_monitor,
                create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            )
        )
        self._stage_deadline_outcome = StageDeadlineOutcome(
            StageDeadlineOutcomePorts(
                target_outcome_snapshot=lambda *args, **kwargs: self._target_outcome_snapshot(*args, **kwargs),
                create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            )
        )

    @property
    def _last_probe_state(self) -> dict[str, Any] | None:
        return self._stage_probe_snapshot.last_probe_state

    @_last_probe_state.setter
    def _last_probe_state(self, value: dict[str, Any] | None) -> None:
        self._stage_probe_snapshot.last_probe_state = value

    _first_command_node_uid = staticmethod(StageCommandBoundary.first_command_node_uid)

    async def _remap_execution_error(
        self,
        *,
        task: Any,
        error_code: str,
        error_message: str,
        node_uid: str | None = None,
        plan: Any = None,
    ) -> tuple[str, str]:
        return await self._stage_command_boundary.remap_execution_error(
            task=task, error_code=error_code, error_message=error_message, node_uid=node_uid, plan=plan
        )

    async def _raise_execution_error(
        self,
        *,
        task: Any,
        error_code: str,
        error_message: str,
        node_uid: str | None = None,
        plan: Any = None,
        deadline_kind: str | None = None,
    ) -> None:
        return await self._stage_command_boundary.raise_execution_error(
            task=task,
            error_code=error_code,
            error_message=error_message,
            node_uid=node_uid,
            plan=plan,
            deadline_kind=deadline_kind,
        )

    async def _ensure_command_targets_online(
        self,
        *,
        task: Any,
        commands: Sequence[Any],
    ) -> None:
        return await self._stage_command_boundary.ensure_command_targets_online(task=task, commands=commands)

    async def _run_command_batch_checked(
        self,
        *,
        task: Any,
        commands: Sequence[Any],
        now: datetime,
        track_task_state: bool = True,
    ) -> Mapping[str, Any]:
        return await self._stage_command_boundary.run_command_batch_checked(
            task=task, commands=commands, now=now, track_task_state=track_task_state
        )

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        raise NotImplementedError

    async def _checkpoint(self, *, task: Any, plan: Any, now: datetime) -> Any:
        return await self._stage_checkpoint.checkpoint(task=task, plan=plan, now=now)

    def _deadline_reached(self, *, now: datetime, deadline: datetime | None) -> bool:
        return self._stage_timing.deadline_reached(now=now, deadline=deadline)

    async def _handle_control_mode_flow_path_interrupt(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        control_mode: str,
        reason: str = "control_mode_manual",
    ) -> StageOutcome | None:
        return await self._stage_flow_safety.handle_control_mode_flow_path_interrupt(
            task=task, plan=plan, now=now, control_mode=control_mode, reason=reason
        )

    async def _ensure_flow_path_stopped(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        stage: str,
        reason: str,
    ) -> Any:
        return await self._stage_flow_safety.ensure_flow_path_stopped(
            task=task, plan=plan, now=now, stage=stage, reason=reason
        )

    def _stage_entered_at(self, *, task: Any) -> datetime | None:
        return self._stage_timing.stage_entered_at(task=task)

    def _stage_elapsed_ms(self, *, task: Any, now: datetime) -> int:
        return self._stage_timing.stage_elapsed_ms(task=task, now=now)

    def _remaining_stage_time_sec(self, *, now: datetime, deadline: datetime | None) -> float | None:
        return self._stage_timing.remaining_stage_time_sec(now=now, deadline=deadline)

    def _require_runtime_plan(self, *, plan: Any) -> RuntimePlan:
        return self._stage_timing.require_runtime_plan(plan=plan)

    def _irr_probe_deadline_budget_sec(self, *, runtime: RuntimePlan) -> float:
        # На реальном test-node roundtrip команды и состояния может занимать несколько секунд.
        # Если запускать новый IRR probe слишком близко к дедлайну stage, команда
        # может упасть уже на polling после дедлайна, а не пойти по ожидаемому stage path.
        return self._stage_timing.irr_probe_deadline_budget_sec(runtime=runtime)

    def _deadline_too_close_for_irr_probe(
        self,
        *,
        now: datetime,
        deadline: datetime | None,
        runtime: RuntimePlan,
    ) -> bool:
        return self._stage_timing.deadline_too_close_for_irr_probe(now=now, deadline=deadline, runtime=runtime)

    async def _read_recent_storage_event(
        self,
        *,
        task: Any,
        event_types: Sequence[str],
        max_age_sec: int = 3600,  # config-literal: default recent-event lookup window
    ) -> Mapping[str, Any] | None:
        return await self._stage_flow_safety.read_recent_storage_event(
            task=task, event_types=event_types, max_age_sec=max_age_sec
        )

    def _storage_event_payload(self, event: Mapping[str, Any] | None) -> Mapping[str, Any]:
        return self._stage_flow_safety.storage_event_payload(event=event)

    def _task_topology(self, *, task: Any) -> str:
        return self._stage_flow_safety.task_topology(task=task)

    def _task_stage(self, *, task: Any) -> str:
        return self._stage_flow_safety.task_stage(task=task)

    def _observe_fail_safe_transition(
        self,
        *,
        task: Any,
        reason: str,
        source: str,
        next_stage: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        return self._stage_flow_safety.observe_fail_safe_transition(
            task=task, reason=reason, source=source, next_stage=next_stage, details=details
        )

    async def _reconcile_recent_emergency_stop(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        expected: Mapping[str, bool],
    ) -> None:
        return await self._stage_flow_safety.reconcile_recent_emergency_stop(
            task=task, plan=plan, now=now, expected=expected
        )

    # ── Probe IRR state (hardware safety check) ─────────────────────

    async def _probe_irr_state(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        expected: Mapping[str, bool],
    ) -> None:
        return await self._stage_probe_runner.probe_irr_state(task=task, plan=plan, now=now, expected=expected)

    async def _ensure_irr_probe_node_online(self, *, task: Any, plan: Any) -> None:
        return await self._stage_probe_runner.ensure_irr_probe_node_online(task=task, plan=plan)

    async def _irr_probe_node_is_offline(self, *, task: Any, plan: Any) -> bool:
        return await self._stage_probe_runner.irr_probe_node_is_offline(task=task, plan=plan)

    async def _offline_failure_for_irr_probe(self, *, task: Any, plan: Any) -> Any:
        return await self._stage_probe_runner.offline_failure_for_irr_probe(task=task, plan=plan)

    _is_solution_fill_terminal_snapshot = staticmethod(StageProbeRunner.is_solution_fill_terminal_snapshot)

    _is_node_reboot_pattern = staticmethod(StageProbeObservability.is_node_reboot_pattern)

    async def _maybe_emit_node_reboot_event(
        self,
        *,
        task: Any,
        plan: Any,
        expected: Mapping[str, bool],
        snapshot: Mapping[str, Any],
    ) -> None:
        return await self._stage_probe_observability.maybe_emit_node_reboot_event(
            task=task, plan=plan, expected=expected, snapshot=snapshot
        )

    def _extract_irr_probe_node_uid(self, *, plan: Any) -> str | None:
        return self._stage_probe_runner.extract_irr_probe_node_uid(plan=plan)

    async def _probe_irr_state_with_backoff(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        expected: Mapping[str, bool],
        poll_delay_sec: int,
        exhausted_outcome: Any,
    ) -> StageOutcome | None:
        return await self._stage_probe_backoff.probe_irr_state_with_backoff(
            task=task,
            plan=plan,
            now=now,
            expected=expected,
            poll_delay_sec=poll_delay_sec,
            exhausted_outcome=exhausted_outcome,
        )

    async def _handle_probe_deferred(
        self,
        *,
        task: Any,
        reason: str,
        expected: Mapping[str, bool],
        node_uid: str | None,
        liveness: Mapping[str, Any] | None,
        poll_delay_sec: int,
        exhausted_outcome: Any,
    ) -> StageOutcome:
        return await self._stage_probe_backoff.handle_probe_deferred(
            task=task,
            reason=reason,
            expected=expected,
            node_uid=node_uid,
            liveness=liveness,
            poll_delay_sec=poll_delay_sec,
            exhausted_outcome=exhausted_outcome,
        )

    def _classify_probe_failure_reason(
        self,
        *,
        state: Mapping[str, Any],
        expected: Mapping[str, bool],
        expected_cmd_id: str | None = None,
    ) -> str:
        return self._stage_probe_runner.classify_probe_failure_reason(
            state=state, expected=expected, expected_cmd_id=expected_cmd_id
        )

    async def _read_probe_state_with_retry(
        self,
        *,
        task: Any,
        runtime: RuntimePlan,
        expected: Mapping[str, bool],
        expected_cmd_id: str | None = None,
    ) -> Mapping[str, Any]:
        return await self._stage_probe_runner.read_probe_state_with_retry(
            task=task, runtime=runtime, expected=expected, expected_cmd_id=expected_cmd_id
        )

    def _probe_state_needs_retry(
        self,
        *,
        state: Mapping[str, Any],
        expected: Mapping[str, bool],
        expected_cmd_id: str | None = None,
    ) -> bool:
        return self._stage_probe_runner.probe_state_needs_retry(
            state=state, expected=expected, expected_cmd_id=expected_cmd_id
        )

    def _extract_probe_cmd_id(self, *, result: Mapping[str, Any]) -> str | None:
        return self._stage_probe_runner.extract_probe_cmd_id(result=result)

    async def _log_probe_failure_event(
        self,
        *,
        task: Any,
        expected: Mapping[str, bool],
        expected_cmd_id: str | None,
        state: Mapping[str, Any],
        reason: str,
    ) -> None:
        return await self._stage_probe_observability.log_probe_failure_event(
            task=task, expected=expected, expected_cmd_id=expected_cmd_id, state=state, reason=reason
        )

    # ── Level switch reading ────────────────────────────────────────

    def _remember_probe_state(self, *, task: Any, state: Mapping[str, Any]) -> None:
        return self._stage_probe_snapshot.remember_probe_state(task=task, state=state)

    def _probe_state_for_task(self, *, task: Any) -> Mapping[str, Any] | None:
        return self._stage_probe_snapshot.probe_state_for_task(task=task)

    def _probe_snapshot_context(self, *, task: Any) -> Mapping[str, Any] | None:
        return self._stage_probe_snapshot.probe_snapshot_context(task=task)

    def _probe_snapshot_correction_fields(self, *, task: Any) -> Mapping[str, Any]:
        return self._stage_probe_snapshot.probe_snapshot_correction_fields(task=task)

    def _read_probe_level_snapshot(
        self,
        *,
        task: Any,
        labels: Sequence[str],
        threshold: float,
        telemetry_max_age_sec: int,
    ) -> Mapping[str, Any] | None:
        return self._stage_probe_snapshot.read_probe_level_snapshot(
            task=task, labels=labels, threshold=threshold, telemetry_max_age_sec=telemetry_max_age_sec
        )

    def _lookup_level_value_in_probe_snapshot(
        self,
        *,
        snapshot: Mapping[str, Any],
        labels: Sequence[str],
    ) -> tuple[str, bool] | None:
        return self._stage_probe_snapshot.lookup_level_value_in_probe_snapshot(snapshot=snapshot, labels=labels)

    def _level_snapshot_aliases(self, label: str) -> tuple[str, ...]:
        return self._stage_probe_snapshot.level_snapshot_aliases(label=label)

    def _coerce_probe_level_switch_value(self, value: Any) -> bool | None:
        return self._stage_probe_snapshot.coerce_probe_level_switch_value(value=value)

    async def _read_level(
        self,
        *,
        task: Any,
        zone_id: int,
        labels: Sequence[str],
        threshold: float,
        telemetry_max_age_sec: int,
        unavailable_error: str,
        stale_error: str,
        stale_recheck_delay_sec: float | None = None,
        prefer_probe_snapshot: bool = False,
        allow_stale_if_untriggered: bool = False,
    ) -> Mapping[str, Any]:
        return await self._stage_level_reader.read_level(
            task=task,
            zone_id=zone_id,
            labels=labels,
            threshold=threshold,
            telemetry_max_age_sec=telemetry_max_age_sec,
            unavailable_error=unavailable_error,
            stale_error=stale_error,
            stale_recheck_delay_sec=stale_recheck_delay_sec,
            prefer_probe_snapshot=prefer_probe_snapshot,
            allow_stale_if_untriggered=allow_stale_if_untriggered,
        )

    def _should_use_probe_level(
        self,
        *,
        probe_level: Mapping[str, Any],
        runtime_level: Mapping[str, Any],
    ) -> bool:
        return self._stage_level_reader.should_use_probe_level(probe_level=probe_level, runtime_level=runtime_level)

    def _log_level_state(
        self,
        *,
        task: Any,
        labels: Sequence[str],
        level: Mapping[str, Any],
        telemetry_max_age_sec: int,
        reason: str,
        log_method: Any = _logger.warning,
    ) -> None:
        return self._stage_level_reader.log_level_state(
            task=task,
            labels=labels,
            level=level,
            telemetry_max_age_sec=telemetry_max_age_sec,
            reason=reason,
            log_method=log_method,
        )

    # ── PH/EC target evaluation ─────────────────────────────────────

    async def _targets_reached_on_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> bool:
        return await self._stage_deadline_outcome.targets_reached_on_deadline(
            task=task, plan=plan, now=now, runtime=runtime
        )

    async def _target_outcome_on_deadline(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> Mapping[str, Any]:
        return await self._stage_deadline_outcome.target_outcome_on_deadline(
            task=task, plan=plan, now=now, runtime=runtime
        )

    async def _record_deadline_target_outcome(
        self,
        *,
        task: Any,
        snapshot: Mapping[str, Any],
        reason: str = "stage_deadline",
    ) -> None:
        return await self._stage_deadline_outcome.record_deadline_target_outcome(
            task=task, snapshot=snapshot, reason=reason
        )

    async def _targets_reached(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> bool:
        return await self._stage_readiness.targets_reached(task=task, plan=plan, now=now, runtime=runtime)

    async def _target_outcome_snapshot(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> Mapping[str, Any]:
        # Phase 5: accept hot-swapped runtime override.
        return await self._stage_readiness.target_outcome_snapshot(task=task, plan=plan, now=now, runtime=runtime)

    def _irrigation_ec_dosing_block_reason(
        self,
        *,
        corr: Any,
        ec_component: str,
        current_ec: float | None,
        full_target_ec: float,
        correction_cfg: Mapping[str, Any],
        pid_configs: Mapping[str, Any],
    ) -> str | None:
        return self._stage_readiness.irrigation_ec_dosing_block_reason(
            corr=corr,
            ec_component=ec_component,
            current_ec=current_ec,
            full_target_ec=full_target_ec,
            correction_cfg=correction_cfg,
            pid_configs=pid_configs,
        )

    _apply_ec_dosing_block = staticmethod(StageReadiness.apply_ec_dosing_block)

    async def _workflow_ready_reached(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> bool:
        # Phase 5: accept hot-swapped runtime from handler. Falls back to
        # plan.runtime when caller didn't opt into live-mode reassignment.
        return await self._stage_readiness.workflow_ready_reached(task=task, plan=plan, now=now, runtime=runtime)

    def _recirc_pipeline_open(self, task: Any) -> bool:
        return self._stage_readiness.recirc_pipeline_open(task=task)

    def _workflow_ready_values_match(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
    ) -> bool:
        return self._stage_readiness.workflow_ready_values_match(
            task=task, runtime=runtime, current_ph=current_ph, current_ec=current_ec
        )

    def _phase_ready_values_match(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
    ) -> bool:
        return self._stage_readiness.phase_ready_values_match(
            task=task, runtime=runtime, current_ph=current_ph, current_ec=current_ec
        )

    def _irrigation_band_values_match(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
    ) -> bool:
        return self._stage_readiness.irrigation_band_values_match(
            task=task, runtime=runtime, current_ph=current_ph, current_ec=current_ec
        )

    def _irrigation_ready_short_circuit(
        self,
        *,
        task: Any,
        runtime: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
    ) -> bool:
        return self._stage_readiness.irrigation_ready_short_circuit(
            task=task, runtime=runtime, current_ph=current_ph, current_ec=current_ec
        )

    async def _finish_ready_or_irrigation_short_circuit(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> bool:
        return await self._stage_readiness.finish_ready_or_irrigation_short_circuit(
            task=task, plan=plan, now=now, runtime=runtime
        )

    def _value_matches_ready_band(
        self,
        *,
        current: float,
        target: float,
        tolerance_pct: float,
        explicit_min: float | None,
        explicit_max: float | None,
    ) -> bool:
        return self._stage_readiness.value_matches_ready_band(
            current=current,
            target=target,
            tolerance_pct=tolerance_pct,
            explicit_min=explicit_min,
            explicit_max=explicit_max,
        )

    async def _read_target_metric_window(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        telemetry_max_age_sec: int,
        config: Mapping[str, Any],
        unavailable_error: str,
        stale_error: str,
        now: datetime,
    ) -> Mapping[str, Any]:
        return await self._stage_metric_window.read_target_metric_window(
            zone_id=zone_id,
            sensor_type=sensor_type,
            telemetry_max_age_sec=telemetry_max_age_sec,
            config=config,
            unavailable_error=unavailable_error,
            stale_error=stale_error,
            now=now,
        )

    _sensor_value_in_bounds = staticmethod(StageMetricWindow.sensor_value_in_bounds)

    def _decision_window_since_ts(self, *, now: datetime, config: Mapping[str, Any]) -> datetime:
        return self._stage_metric_window.decision_window_since_ts(now=now, config=config)

    def _summarize_metric_window(
        self,
        *,
        samples: Any,
        window_min_samples: int,
        stability_max_slope: float,
    ) -> dict[str, Any]:
        return self._stage_metric_window.summarize_metric_window(
            samples=samples, window_min_samples=window_min_samples, stability_max_slope=stability_max_slope
        )

    # ── Per-phase EC target (NPK share для подготовки) ────────────

    # ── Day/Night helpers ────────────────────────────────────────────

    async def _check_solution_change_abort(
        self,
        *,
        task: Any,
        pending_manual_step: str,
    ) -> StageOutcome | None:
        return await self._stage_flow_safety.check_solution_change_abort(
            task=task, pending_manual_step=pending_manual_step
        )

    # ── Sensor consistency check (max=1, min=0 → error) ────────────

    async def _check_sensor_consistency(
        self,
        *,
        task: Any,
        runtime: Any,
        min_labels_key: str,
        min_unavailable_error: str,
        min_stale_error: str,
        stale_recheck_delay_sec: float | None = None,
        prefer_probe_snapshot: bool = False,
    ) -> None:
        return await self._stage_flow_safety.check_sensor_consistency(
            task=task,
            runtime=runtime,
            min_labels_key=min_labels_key,
            min_unavailable_error=min_unavailable_error,
            min_stale_error=min_stale_error,
            stale_recheck_delay_sec=stale_recheck_delay_sec,
            prefer_probe_snapshot=prefer_probe_snapshot,
        )
