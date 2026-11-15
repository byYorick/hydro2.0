"""Выполняет одну claimed-задачу AE3-Lite до следующего безопасного состояния."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import logging
import os
from datetime import timezone
from datetime import datetime
from datetime import timedelta
from typing import Any, Mapping

from ae3lite.application.services.correction_interrupt_safety import (
    FAIL_SAFE_SHUTDOWN_CHANNELS as _FAIL_SAFE_SHUTDOWN_CHANNELS,
)
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.config.schema import RuntimePlan
from ae3lite.application.services.task_failed_alert import emit_task_failed_alert
from ae3lite.application.use_cases.finalize_task import FinalizeTaskUseCase
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.infrastructure.metrics import (
    FLOW_STOP_FAILED,
    TASK_RUNNING_TRANSITION_MISSED,
    inc_observability_write_failed,
)
from ae3lite.hydraulics.failure_report import publish_upward_reports
from common.db import create_zone_event, fetch
from common.infra_alerts import send_infra_alert
from common.biz_alerts import send_biz_alert
from common.service_logs import send_service_log
from ae3lite.domain.claim_fence import claim_generation, claim_owner, same_claim_token
from ae3lite.domain.errors import (
    ErrorCodes,
    PlannerConfigurationError,
    SnapshotBuildError,
    TaskFinalizeError,
    TaskExecutionError,
    TaskTerminalStateReached,
)
from ae3lite.domain.task_deadline import ensure_overall_deadline_active


from ae3lite.application.services.task_execution_shared import (
    logger,
    TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
    TASK_EXECUTION_LEASE_LOST_CANCEL_MSG,
    TASK_EXECUTION_OVERALL_DEADLINE_CANCEL_MSG,
    NODE_STALE_ONLINE_THRESHOLD_SEC,
    SNAPSHOT_TRANSIENT_RETRY_SEC,
    SNAPSHOT_TRANSIENT_MAX_STAGE_AGE_SEC,
    NODE_PERSISTENT_DEAD_SEC,
    SNAPSHOT_RETRY_SCHEDULED_CODE,
    SNAPSHOT_RETRY_EXHAUSTED_CODE,
    COMMAND_SEND_RETRY_SEC,
    COMMAND_SEND_MAX_STAGE_AGE_SEC,
    COMMAND_SEND_RETRY_SCHEDULED_CODE,
    COMMAND_SEND_RETRY_EXHAUSTED_CODE,
)

from ae3lite.application.services.task_execution_pipeline import TaskExecutionPipeline, TaskExecutionPipelinePorts
from ae3lite.application.services.task_execution_snapshot_retry import (
    TaskExecutionSnapshotRetry,
    TaskExecutionSnapshotRetryPorts,
)
from ae3lite.application.services.task_execution_preflight import TaskExecutionPreflight, TaskExecutionPreflightPorts
from ae3lite.application.services.task_execution_decision_snapshot import (
    TaskExecutionDecisionSnapshot,
    TaskExecutionDecisionSnapshotPorts,
)
from ae3lite.application.services.task_execution_readiness import TaskExecutionReadiness, TaskExecutionReadinessPorts
from ae3lite.application.services.task_execution_failure_diagnostics import (
    TaskExecutionFailureDiagnostics,
    TaskExecutionFailureDiagnosticsPorts,
)
from ae3lite.application.services.task_execution_failure_completion import (
    TaskExecutionFailureCompletion,
    TaskExecutionFailureCompletionPorts,
)
from ae3lite.application.services.task_execution_shutdown import TaskExecutionShutdown, TaskExecutionShutdownPorts


class ExecuteTaskUseCase:
    """Выполняет один stage AE3 cycle_start и возвращает terminal-задачу или безопасно requeue'нутую."""

    # Тот же объект, что correction_interrupt_safety.FAIL_SAFE_SHUTDOWN_CHANNELS.
    FAIL_SAFE_SHUTDOWN_CHANNELS = _FAIL_SAFE_SHUTDOWN_CHANNELS

    def __init__(
        self,
        *,
        task_repository: Any,
        zone_snapshot_read_model: Any,
        planner: Any,
        command_gateway: Any,
        workflow_router: Any,
        workflow_repository: Any | None = None,
        correction_authority_repository: Any | None = None,
        alert_repository: Any | None = None,
        command_repository: Any | None = None,
        finalize_task_use_case: Any | None = None,
    ) -> None:
        self._task_repository = task_repository
        self._zone_snapshot_read_model = zone_snapshot_read_model
        self._planner = planner
        self._command_gateway = command_gateway
        self._workflow_router = workflow_router
        self._workflow_repository = workflow_repository
        self._correction_authority_repository = correction_authority_repository
        self._alert_repository = alert_repository
        self._command_repository = command_repository
        self._finalize_task_use_case = finalize_task_use_case or FinalizeTaskUseCase(task_repository=task_repository)
        self._failure_states: OrderedDict[tuple[int, str, int], dict[str, Any]] = OrderedDict()
        self._task_execution_pipeline = TaskExecutionPipeline(
            TaskExecutionPipelinePorts(
                apply_terminal_task_side_effects=lambda *args, **kwargs: self._apply_terminal_task_side_effects(
                    *args, **kwargs
                ),
                clear_failure_guards=lambda *args, **kwargs: self._clear_failure_guards(*args, **kwargs),
                command_gateway=lambda: self._command_gateway,
                emit_start_readiness_confirmed=lambda *args, **kwargs: self._emit_start_readiness_confirmed(
                    *args, **kwargs
                ),
                emit_start_readiness_failed=lambda *args, **kwargs: self._emit_start_readiness_failed(*args, **kwargs),
                emit_task_completed_event=lambda *args, **kwargs: self._emit_task_completed_event(*args, **kwargs),
                extract_irrig_node_uid=lambda *args, **kwargs: self._extract_irrig_node_uid(*args, **kwargs),
                fail_closed=lambda *args, **kwargs: self._fail_closed(*args, **kwargs),
                finalize_task_use_case=lambda: self._finalize_task_use_case,
                is_lease_lost_cancellation=lambda *args, **kwargs: self._is_lease_lost_cancellation(*args, **kwargs),
                is_overall_deadline_cancellation=lambda *args, **kwargs: self._is_overall_deadline_cancellation(
                    *args, **kwargs
                ),
                is_timeout_cancellation=lambda *args, **kwargs: self._is_timeout_cancellation(*args, **kwargs),
                load_terminal_task_or_none=lambda *args, **kwargs: self._load_terminal_task_or_none(*args, **kwargs),
                lock_irrigation_decision_snapshot_if_needed=lambda *args, **kwargs: (
                    self._lock_irrigation_decision_snapshot_if_needed(*args, **kwargs)
                ),
                mark_correction_config_applied_if_needed=lambda *args, **kwargs: (
                    self._mark_correction_config_applied_if_needed(*args, **kwargs)
                ),
                planner=lambda: self._planner,
                preflight_required_nodes_online=lambda *args, **kwargs: self._preflight_required_nodes_online(
                    *args, **kwargs
                ),
                resolve_offline_failure_instead_of_guard=lambda *args, **kwargs: (
                    self._resolve_offline_failure_instead_of_guard(*args, **kwargs)
                ),
                retry_transient_command_send_failure=lambda *args, **kwargs: self._retry_transient_command_send_failure(
                    *args, **kwargs
                ),
                retry_transient_snapshot_gap=lambda *args, **kwargs: self._retry_transient_snapshot_gap(
                    *args, **kwargs
                ),
                shutdown_terminal_flow_if_needed=lambda *args, **kwargs: self._shutdown_terminal_flow_if_needed(
                    *args, **kwargs
                ),
                task_repository=lambda: self._task_repository,
                verify_topology_required_node_types=lambda *args, **kwargs: self._verify_topology_required_node_types(
                    *args, **kwargs
                ),
                workflow_router=lambda: self._workflow_router,
                zone_snapshot_read_model=lambda: self._zone_snapshot_read_model,
                complete_execution_failure=lambda *args, **kwargs: self.complete_execution_failure(*args, **kwargs),
                global_publish_upward_reports=lambda *args, **kwargs: publish_upward_reports(*args, **kwargs),
            )
        )
        self._task_execution_snapshot_retry = TaskExecutionSnapshotRetry(
            TaskExecutionSnapshotRetryPorts(
                task_repository=lambda: self._task_repository,
                complete_execution_failure=lambda *args, **kwargs: self.complete_execution_failure(*args, **kwargs),
                global_create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
                global_send_infra_alert=lambda *args, **kwargs: send_infra_alert(*args, **kwargs),
            )
        )
        self._task_execution_preflight = TaskExecutionPreflight(
            TaskExecutionPreflightPorts(
                workflow_router=lambda: self._workflow_router,
            )
        )
        self._task_execution_decision_snapshot = TaskExecutionDecisionSnapshot(
            TaskExecutionDecisionSnapshotPorts(
                correction_authority_repository=lambda: self._correction_authority_repository,
                task_repository=lambda: self._task_repository,
                global_create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
                global_send_service_log=lambda *args, **kwargs: send_service_log(*args, **kwargs),
            )
        )
        self._task_execution_readiness = TaskExecutionReadiness(
            TaskExecutionReadinessPorts(
                latest_chemistry_diagnostics=lambda *args, **kwargs: self._latest_chemistry_diagnostics(
                    *args, **kwargs
                ),
                global_create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
                global_send_service_log=lambda *args, **kwargs: send_service_log(*args, **kwargs),
            )
        )
        self._task_execution_failure_diagnostics = TaskExecutionFailureDiagnostics(
            TaskExecutionFailureDiagnosticsPorts(
                command_repository=lambda: self._command_repository,
                global_fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
            )
        )
        self._task_execution_failure_completion = TaskExecutionFailureCompletion(
            TaskExecutionFailureCompletionPorts(
                alert_repository=lambda: self._alert_repository,
                build_failure_observability_details=lambda *args, **kwargs: self._build_failure_observability_details(
                    *args, **kwargs
                ),
                failure_states=lambda: self._failure_states,
                finalize_task_use_case=lambda: self._finalize_task_use_case,
                shutdown_once=lambda *args, **kwargs: self._shutdown_once(*args, **kwargs),
                sync_workflow_failure_state=lambda *args, **kwargs: self._sync_workflow_failure_state(*args, **kwargs),
                task_repository=lambda: self._task_repository,
                workflow_repository=lambda: self._workflow_repository,
                global_create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
                global_publish_upward_reports=lambda *args, **kwargs: publish_upward_reports(*args, **kwargs),
            )
        )
        self._task_execution_shutdown = TaskExecutionShutdown(
            TaskExecutionShutdownPorts(
                attempt_fail_safe_shutdown=lambda *args, **kwargs: self._attempt_fail_safe_shutdown(*args, **kwargs),
                command_gateway=lambda: self._command_gateway,
                failure_state=lambda *args, **kwargs: self._failure_state(*args, **kwargs),
                task_repository=lambda: self._task_repository,
                global_send_biz_alert=lambda *args, **kwargs: send_biz_alert(*args, **kwargs),
            )
        )

    async def run(self, *, task: Any, now: datetime) -> Any:
        return await self._task_execution_pipeline.run(task=task, now=now)

    async def _emit_task_completed_event(self, *, task: Any) -> None:
        return await self._task_execution_readiness.emit_task_completed_event(task=task)

    async def _latest_chemistry_diagnostics(self, *, task: Any) -> Mapping[str, Any] | None:
        return await self._task_execution_failure_diagnostics.latest_chemistry_diagnostics(task=task)

    async def _retry_transient_command_send_failure(
        self,
        *,
        task: Any,
        owner: str,
        error: TaskExecutionError,
        now: datetime,
        snapshot: Any = None,
        plan: Any = None,
    ) -> Any | None:
        return await self._task_execution_snapshot_retry.retry_transient_command_send_failure(
            task=task, owner=owner, error=error, now=now, snapshot=snapshot, plan=plan
        )

    async def _retry_transient_snapshot_gap(
        self,
        *,
        task: Any,
        owner: str,
        error: SnapshotBuildError,
        now: datetime,
    ) -> Any | None:
        return await self._task_execution_snapshot_retry.retry_transient_snapshot_gap(
            task=task, owner=owner, error=error, now=now
        )

    def _is_transient_snapshot_gap(self, *, task: Any, error_code: str) -> bool:
        return self._task_execution_snapshot_retry.is_transient_snapshot_gap(task=task, error_code=error_code)

    async def _preflight_required_nodes_online(self, *, task: Any) -> None:
        return await self._task_execution_preflight.preflight_required_nodes_online(task=task)

    def _extract_irrig_node_uid(self, snapshot: Any) -> str | None:
        return self._task_execution_preflight.extract_irrig_node_uid(snapshot=snapshot)

    async def _resolve_offline_failure_instead_of_guard(
        self,
        *,
        task: Any,
        original_error_code: str,
        original_error_message: str = "",
        node_uid: str | None = None,
    ) -> Any | None:
        return await self._task_execution_preflight.resolve_offline_failure_instead_of_guard(
            task=task,
            original_error_code=original_error_code,
            original_error_message=original_error_message,
            node_uid=node_uid,
        )

    def _verify_topology_required_node_types(self, *, task: Any, snapshot: Any) -> None:
        return self._task_execution_preflight.verify_topology_required_node_types(task=task, snapshot=snapshot)

    def _stage_age_sec(self, *, stage_entered_at: datetime | None, now: datetime) -> int:
        return self._task_execution_snapshot_retry.stage_age_sec(stage_entered_at=stage_entered_at, now=now)

    async def _emit_snapshot_retry_observability(
        self,
        *,
        task: Any,
        now: datetime,
        event_type: str,
        alert_code: str,
        alert_message: str,
        severity: str,
        details: Mapping[str, Any],
    ) -> None:
        return await self._task_execution_snapshot_retry.emit_snapshot_retry_observability(
            task=task,
            now=now,
            event_type=event_type,
            alert_code=alert_code,
            alert_message=alert_message,
            severity=severity,
            details=details,
        )

    async def _emit_start_readiness_confirmed(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
    ) -> None:
        return await self._task_execution_readiness.emit_start_readiness_confirmed(
            task=task, snapshot=snapshot, plan=plan
        )

    async def _lock_irrigation_decision_snapshot_if_needed(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        owner: str,
        now: datetime,
        emit_observability: bool = False,
    ) -> Any:
        return await self._task_execution_decision_snapshot.lock_irrigation_decision_snapshot_if_needed(
            task=task, snapshot=snapshot, plan=plan, owner=owner, now=now, emit_observability=emit_observability
        )

    async def _emit_irrigation_decision_snapshot_locked(
        self,
        *,
        task: Any,
        snapshot: Any,
        strategy: str | None,
        bundle_revision: str | None,
        config_mapping: Mapping[str, Any] | None,
    ) -> None:
        return await self._task_execution_decision_snapshot.emit_irrigation_decision_snapshot_locked(
            task=task,
            snapshot=snapshot,
            strategy=strategy,
            bundle_revision=bundle_revision,
            config_mapping=config_mapping,
        )

    def _emit_start_readiness_failed(
        self,
        *,
        task: Any,
        snapshot: Any,
        error_code: str,
        error: Exception,
    ) -> None:
        return self._task_execution_readiness.emit_start_readiness_failed(
            task=task, snapshot=snapshot, error_code=error_code, error=error
        )

    def _build_start_readiness_details(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
    ) -> dict[str, Any]:
        return self._task_execution_readiness.build_start_readiness_details(task=task, snapshot=snapshot, plan=plan)

    def _build_start_failure_details(
        self,
        *,
        task: Any,
        snapshot: Any,
        error_code: str,
        error: Exception,
    ) -> dict[str, Any]:
        return self._task_execution_readiness.build_start_failure_details(
            task=task, snapshot=snapshot, error_code=error_code, error=error
        )

    def _extract_phase_target(self, *, phase_targets: Any, key: str) -> float | None:
        return self._task_execution_readiness.extract_phase_target(phase_targets=phase_targets, key=key)

    async def _fail_closed(
        self,
        *,
        task: Any,
        owner: str,
        error_code: str,
        error_message: str,
        now: datetime,
        extra_details: Mapping[str, Any] | None = None,
        upward_reports: tuple[Any, ...] = (),
    ) -> Any:
        return await self._task_execution_failure_completion.fail_closed(
            task=task,
            owner=owner,
            error_code=error_code,
            error_message=error_message,
            now=now,
            extra_details=extra_details,
            upward_reports=upward_reports,
        )

    async def _apply_terminal_task_side_effects(self, *, task: Any, now: datetime) -> None:
        return await self._task_execution_failure_completion.apply_terminal_task_side_effects(task=task, now=now)

    async def _sync_workflow_failure_state(
        self,
        *,
        task: Any,
        now: datetime,
        fail_closed: bool = False,
    ) -> None:
        return await self._task_execution_failure_completion.sync_workflow_failure_state(
            task=task, now=now, fail_closed=fail_closed
        )

    async def _task_still_exists(self, *, task: Any) -> bool:
        return await self._task_execution_failure_completion.task_still_exists(task=task)

    async def _emit_task_failed_alert(
        self,
        *,
        task: Any,
        error_code: str,
        error_message: str,
        now: datetime,
        extra_details: Mapping[str, Any] | None = None,
    ) -> None:
        return await self._task_execution_failure_completion.emit_task_failed_alert(
            task=task, error_code=error_code, error_message=error_message, now=now, extra_details=extra_details
        )

    async def _build_failure_observability_details(
        self,
        *,
        task: Any,
        error_code: str,
        now: datetime,
    ) -> dict[str, Any]:
        return await self._task_execution_failure_diagnostics.build_failure_observability_details(
            task=task, error_code=error_code, now=now
        )

    def _compose_timeout_details(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        payload: Mapping[str, Any],
        legacy_command: Mapping[str, Any] | None,
        node_context: Mapping[str, Any] | None,
        now: datetime,
    ) -> dict[str, Any] | None:
        return self._task_execution_failure_diagnostics.compose_timeout_details(
            task=task,
            ae_command=ae_command,
            payload=payload,
            legacy_command=legacy_command,
            node_context=node_context,
            now=now,
        )

    def _is_startup_probe_timeout(self, *, task: Any, timeout_details: Mapping[str, Any]) -> bool:
        return self._task_execution_failure_diagnostics.is_startup_probe_timeout(
            task=task, timeout_details=timeout_details
        )

    def _failure_key(self, task: Any) -> tuple[int, str, int]:
        return self._task_execution_failure_completion.failure_key(task=task)

    def _failure_state(self, task: Any) -> dict[str, Any]:
        return self._task_execution_failure_completion.failure_state(task=task)

    def _clear_failure_guards(self, task: Any) -> None:
        return self._task_execution_failure_completion.clear_failure_guards(task=task)

    def is_guarded_task_cancellation(self, exc: BaseException) -> bool:
        return self._task_execution_failure_completion.is_guarded_task_cancellation(exc=exc)

    async def complete_execution_failure(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
        owner: str,
        error_code: str,
        error_message: str,
        extra_details: Mapping[str, Any] | None = None,
        upward_reports: tuple[Any, ...] = (),
    ) -> Any:
        return await self._task_execution_failure_completion.complete_execution_failure(
            task=task,
            snapshot=snapshot,
            plan=plan,
            now=now,
            owner=owner,
            error_code=error_code,
            error_message=error_message,
            extra_details=extra_details,
            upward_reports=upward_reports,
        )

    async def _shutdown_once(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        return await self._task_execution_shutdown.shutdown_once(task=task, snapshot=snapshot, plan=plan, now=now)

    async def _shutdown_terminal_flow_if_needed(
        self,
        *,
        terminal_task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        return await self._task_execution_shutdown.shutdown_terminal_flow_if_needed(
            terminal_task=terminal_task, snapshot=snapshot, plan=plan, now=now
        )

    async def _attempt_fail_safe_shutdown(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        return await self._task_execution_shutdown.attempt_fail_safe_shutdown(
            task=task, snapshot=snapshot, plan=plan, now=now
        )

    async def _emit_fail_safe_shutdown_alert(
        self,
        *,
        task: Any,
        reason: str,
        error_code: str,
    ) -> None:
        return await self._task_execution_shutdown.emit_fail_safe_shutdown_alert(
            task=task, reason=reason, error_code=error_code
        )

    def _log_skip_fail_safe_shutdown(self, *, task: Any, reason: str) -> None:
        return self._task_execution_shutdown.log_skip_fail_safe_shutdown(task=task, reason=reason)

    async def _mark_correction_config_applied_if_needed(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        return await self._task_execution_decision_snapshot.mark_correction_config_applied_if_needed(
            task=task, snapshot=snapshot, plan=plan, now=now
        )

    def _is_timeout_cancellation(self, exc: asyncio.CancelledError) -> bool:
        return self._task_execution_failure_completion.is_timeout_cancellation(exc=exc)

    def _is_lease_lost_cancellation(self, exc: asyncio.CancelledError) -> bool:
        return self._task_execution_failure_completion.is_lease_lost_cancellation(exc=exc)

    def _is_overall_deadline_cancellation(self, exc: asyncio.CancelledError) -> bool:
        return self._task_execution_failure_completion.is_overall_deadline_cancellation(exc=exc)

    async def _load_terminal_task_or_none(self, *, task_id: int, fallback_task: Any) -> Any | None:
        return await self._task_execution_failure_completion.load_terminal_task_or_none(
            task_id=task_id, fallback_task=fallback_task
        )
