"""Runtime-драйвер AE3-Lite v1 с конкурентным drain."""

from __future__ import annotations

import asyncio
import time
import types
import uuid
from contextlib import suppress
from datetime import datetime, timezone as _tz
from typing import Any, Callable, Optional

from ae3lite.domain.errors import TaskClaimRollbackError
from ae3lite.runtime import intent_sync, lease_heartbeat
from ae3lite.runtime.reconcile_loop import ReconcileLoop
from ae3lite.application.use_cases.execute_task import (
    TASK_EXECUTION_LEASE_LOST_CANCEL_MSG,
    TASK_EXECUTION_OVERALL_DEADLINE_CANCEL_MSG,
    TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
)
from ae3lite.infrastructure.log_context import log_context_scope
from ae3lite.domain.task_deadline import overall_deadline_remaining_sec
from ae3lite.infrastructure.metrics import (
    ACTIVE_TASKS,
    CLAIM_ROLLBACK_FAILED,
    DRAIN_CRASHES,
    TASK_EXECUTION_CRASHED,
    TICK_DURATION,
    TICK_ERRORS,
    ZONE_LEASE_RELEASE_FAILED,
)
from common.infra_alerts import send_infra_alert, send_infra_resolved_alert


from ae3lite.runtime.worker_runtime_state import WorkerRuntimeState
from ae3lite.runtime.worker_runtime_correction_recovery import (
    WorkerRuntimeCorrectionRecovery,
    WorkerRuntimeCorrectionRecoveryPorts,
)
from ae3lite.runtime.worker_runtime_reconcile_policy import (
    WorkerRuntimeReconcilePolicy,
    WorkerRuntimeReconcilePolicyPorts,
)
from ae3lite.runtime.worker_runtime_supervisor import WorkerRuntimeSupervisor, WorkerRuntimeSupervisorPorts
from ae3lite.runtime.worker_runtime_execution import WorkerRuntimeExecution, WorkerRuntimeExecutionPorts
from ae3lite.runtime.worker_runtime_lease_outcomes import WorkerRuntimeLeaseOutcomes, WorkerRuntimeLeaseOutcomesPorts
from ae3lite.runtime.worker_runtime_cleanup import WorkerRuntimeCleanup, WorkerRuntimeCleanupPorts


class Ae3RuntimeWorker:
    """Обрабатывает pending-задачи AE3 и выполняет startup recovery."""

    def __init__(
        self,
        *,
        owner: str,
        process_run_id: str = "",
        claim_next_task_use_case: Any,
        idle_poll_interval_sec: float,
        execute_task_use_case: Any,
        startup_recovery_use_case: Any,
        waiting_command_reconcile_use_case: Any | None = None,
        task_repository: Any | None = None,
        command_repository: Any | None = None,
        zone_lease_repository: Any,
        zone_intent_repository: Any,
        create_task_from_intent_use_case: Any | None = None,
        runtime_monitor: Any | None = None,
        command_gateway: Any | None = None,
        correction_interrupt_irr_state_max_age_sec: int = 90,
        correction_interrupt_replay_irrigation: bool = False,
        spawn_background_task_fn: Callable[..., Any],
        now_fn: Callable[[], datetime],
        logger: Any,
        lease_ttl_sec: int = 300,
        max_task_execution_sec: int = 900,
        max_parallel_tasks: int = 1,
        reconcile_poll_interval_sec: float | None = None,
        stale_task_reconcile_use_case: Any | None = None,
        stale_task_reconcile_interval_sec: float | None = None,
        orphan_intent_reconcile_use_case: Any | None = None,
        orphan_intent_reconcile_interval_sec: float | None = None,
        shutdown_grace_sec: float = 30.0,
        lease_heartbeat_max_failures: int = 3,
        lease_heartbeat_transient_retries: int = 1,
        intent_sync_max_retries: int = 2,
        lease_release_resolve_ttl_sec: int = 600,
    ) -> None:
        self._worker_runtime_state = WorkerRuntimeState()
        self._owner = str(owner or "ae3-runtime").strip() or "ae3-runtime"
        self._process_run_id = str(process_run_id or "").strip() or str(uuid.uuid4())
        self._claim_next_task_use_case = claim_next_task_use_case
        self._idle_poll_interval_sec = max(0.1, float(idle_poll_interval_sec))
        self._execute_task_use_case = execute_task_use_case
        self._startup_recovery_use_case = startup_recovery_use_case
        self._waiting_command_reconcile_use_case = waiting_command_reconcile_use_case
        self._stale_task_reconcile_use_case = stale_task_reconcile_use_case
        self._orphan_intent_reconcile_use_case = orphan_intent_reconcile_use_case
        self._task_repository = task_repository
        self._command_repository = command_repository
        self._zone_lease_repository = zone_lease_repository
        self._zone_intent_repository = zone_intent_repository
        self._create_task_from_intent_use_case = create_task_from_intent_use_case
        self._runtime_monitor = runtime_monitor
        self._command_gateway = command_gateway
        self._correction_interrupt_irr_state_max_age_sec = max(
            5,
            int(correction_interrupt_irr_state_max_age_sec),
        )
        self._correction_interrupt_replay_irrigation = bool(correction_interrupt_replay_irrigation)
        self._pending_correction_safety_checks: list[Any] = []
        self._spawn_background_task_fn = spawn_background_task_fn
        self._now_fn = now_fn
        self._logger = logger
        self._lease_ttl_sec = max(30, int(lease_ttl_sec))
        self._max_task_execution_sec = max_task_execution_sec
        self._max_parallel_tasks = max(1, int(max_parallel_tasks))
        self._reconcile_poll_interval_sec = max(
            0.1,
            float(reconcile_poll_interval_sec if reconcile_poll_interval_sec is not None else idle_poll_interval_sec),
        )
        self._stale_task_reconcile_interval_sec = max(
            1.0,
            float(stale_task_reconcile_interval_sec if stale_task_reconcile_interval_sec is not None else 60.0),
        )
        self._last_stale_task_reconcile_monotonic: float | None = None
        self._last_terminal_command_reconcile_monotonic: float | None = None
        self._orphan_intent_reconcile_interval_sec = max(
            1.0,
            float(
                orphan_intent_reconcile_interval_sec
                if orphan_intent_reconcile_interval_sec is not None
                else self._stale_task_reconcile_interval_sec
            ),
        )
        self._last_orphan_intent_reconcile_monotonic: float | None = None
        self._last_active_task_age_metrics_monotonic: float | None = None
        self._active_task_age_metrics_interval_sec = self._stale_task_reconcile_interval_sec
        self._drain_task: Optional[Any] = None
        self._pending_kicks = 0
        self._respawn_guard_task: Optional[Any] = None
        self._wake_task: Optional[Any] = None
        self._wake_handle: Optional[asyncio.Handle] = None
        self._last_drain_exit_ok = True
        self._last_drain_exit_reason = "idle"
        self._reconcile_loop_task: Optional[Any] = None
        self._reconcile_wake = asyncio.Event()
        self._shutting_down = False
        self._shutdown_grace_sec = max(0.0, float(shutdown_grace_sec))
        self._active_shutdown_grace_sec: float | None = None
        self._lease_heartbeat_max_failures = max(1, int(lease_heartbeat_max_failures))
        self._lease_heartbeat_transient_retries = max(0, int(lease_heartbeat_transient_retries))
        self._intent_sync_max_retries = max(0, int(intent_sync_max_retries))
        self._inflight_automation_tasks: dict[asyncio.Task, Any] = {}
        self._reconcile_loop = ReconcileLoop(
            steps=(
                lambda: self._run_waiting_command_reconcile_once(),
                lambda: self._maybe_run_terminal_command_reconcile_once(),
                lambda: self._maybe_run_correction_interrupt_safety_once(),
                lambda: self._maybe_run_stale_task_reconcile_once(),
                lambda: self._maybe_run_orphan_intent_reconcile_once(),
                lambda: self._maybe_refresh_active_task_age_metrics_once(),
            ),
            is_stopping=lambda: self._shutting_down,
            wake=self._reconcile_wake,
            poll_interval_sec=self._reconcile_poll_interval_sec,
            owner=self._owner,
            logger=self._logger,
            log_debug=self._log_debug,
        )
        self._pending_health_cache: tuple[float, bool] | None = None
        # Условный resolve lease_release_failed: без spam на каждый finish.
        # known-fail → resolve сразу; иначе opportunistic после warm-up, не чаще TTL.
        self._lease_release_fail_zones: set[int] = set()
        self._lease_release_resolve_attempt_at: dict[int, datetime] = {}
        self._lease_release_resolve_ttl_sec = max(0, int(lease_release_resolve_ttl_sec))
        self._lease_release_resolve_started_monotonic = time.monotonic()
        self._worker_runtime_correction_recovery = WorkerRuntimeCorrectionRecovery(
            WorkerRuntimeCorrectionRecoveryPorts(
                command_gateway=lambda: self._command_gateway,
                correction_interrupt_irr_state_max_age_sec=lambda: self._correction_interrupt_irr_state_max_age_sec,
                correction_interrupt_replay_irrigation=lambda: self._correction_interrupt_replay_irrigation,
                create_task_from_intent_use_case=lambda: self._create_task_from_intent_use_case,
                ensure_waiting_command_reconcile_loop=lambda *args, **kwargs: (
                    self._ensure_waiting_command_reconcile_loop(*args, **kwargs)
                ),
                logger=lambda: self._logger,
                now_fn=lambda *args, **kwargs: self._now_fn(*args, **kwargs),
                runtime_monitor=lambda: self._runtime_monitor,
                safe_mark_intent_terminal_result=lambda *args, **kwargs: self._safe_mark_intent_terminal_result(
                    *args, **kwargs
                ),
                startup_recovery_use_case=lambda: self._startup_recovery_use_case,
                task_repository=lambda: self._task_repository,
                zone_intent_repository=lambda: self._zone_intent_repository,
                kick=lambda *args, **kwargs: self.kick(*args, **kwargs),
                optional_safe_mark_intent_terminal_result=lambda: getattr(
                    self, '_safe_mark_intent_terminal_result', None
                ),
            ),
            self._worker_runtime_state,
        )
        self._worker_runtime_reconcile_policy = WorkerRuntimeReconcilePolicy(
            WorkerRuntimeReconcilePolicyPorts(
                active_task_age_metrics_interval_sec=lambda: self._active_task_age_metrics_interval_sec,
                arm_respawn_on_done=lambda *args, **kwargs: self._arm_respawn_on_done(*args, **kwargs),
                log_debug=lambda *args, **kwargs: self._log_debug(*args, **kwargs),
                logger=lambda: self._logger,
                now_fn=lambda *args, **kwargs: self._now_fn(*args, **kwargs),
                orphan_intent_reconcile_interval_sec=lambda: self._orphan_intent_reconcile_interval_sec,
                orphan_intent_reconcile_use_case=lambda: self._orphan_intent_reconcile_use_case,
                owner=lambda: self._owner,
                reconcile_loop=lambda: self._reconcile_loop,
                safe_mark_intent_terminal_result=lambda *args, **kwargs: self._safe_mark_intent_terminal_result(
                    *args, **kwargs
                ),
                spawn_background_task_fn=lambda *args, **kwargs: self._spawn_background_task_fn(*args, **kwargs),
                spawn_drain_task=lambda *args, **kwargs: self._spawn_drain_task(*args, **kwargs),
                stale_task_reconcile_interval_sec=lambda: self._stale_task_reconcile_interval_sec,
                stale_task_reconcile_use_case=lambda: self._stale_task_reconcile_use_case,
                startup_recovery_use_case=lambda: self._startup_recovery_use_case,
                sync_orphan_intent_terminal=lambda *args, **kwargs: self._sync_orphan_intent_terminal(*args, **kwargs),
                task_repository=lambda: self._task_repository,
                waiting_command_reconcile_use_case=lambda: self._waiting_command_reconcile_use_case,
            ),
            self._worker_runtime_state,
        )
        self._worker_runtime_supervisor = WorkerRuntimeSupervisor(
            WorkerRuntimeSupervisorPorts(
                claim_next_task_use_case=lambda: self._claim_next_task_use_case,
                drain_pending_tasks=lambda *args, **kwargs: self._drain_pending_tasks(*args, **kwargs),
                execute_claimed_task_safe=lambda *args, **kwargs: self._execute_claimed_task_safe(*args, **kwargs),
                finalize_inflight_on_shutdown=lambda *args, **kwargs: self._finalize_inflight_on_shutdown(
                    *args, **kwargs
                ),
                idle_poll_interval_sec=lambda: self._idle_poll_interval_sec,
                log_debug=lambda *args, **kwargs: self._log_debug(*args, **kwargs),
                logger=lambda: self._logger,
                max_parallel_tasks=lambda: self._max_parallel_tasks,
                now_fn=lambda *args, **kwargs: self._now_fn(*args, **kwargs),
                owner=lambda: self._owner,
                process_run_id=lambda: self._process_run_id,
                spawn_background_task_fn=lambda *args, **kwargs: self._spawn_background_task_fn(*args, **kwargs),
            ),
            self._worker_runtime_state,
        )
        self._worker_runtime_execution = WorkerRuntimeExecution(
            WorkerRuntimeExecutionPorts(
                abort_task_after_intent_sync_failure=lambda *args, **kwargs: self._abort_task_after_intent_sync_failure(
                    *args, **kwargs
                ),
                execute_task_use_case=lambda: self._execute_task_use_case,
                lease_heartbeat=lambda *args, **kwargs: self._lease_heartbeat(*args, **kwargs),
                log_debug=lambda *args, **kwargs: self._log_debug(*args, **kwargs),
                logger=lambda: self._logger,
                max_task_execution_sec=lambda: self._max_task_execution_sec,
                maybe_resolve_zone_lease_release_alert=lambda *args, **kwargs: (
                    self._maybe_resolve_zone_lease_release_alert(*args, **kwargs)
                ),
                now_fn=lambda *args, **kwargs: self._now_fn(*args, **kwargs),
                owner=lambda: self._owner,
                safe_mark_intent_running=lambda *args, **kwargs: self._safe_mark_intent_running(*args, **kwargs),
                safe_mark_intent_terminal=lambda *args, **kwargs: self._safe_mark_intent_terminal(*args, **kwargs),
                spawn_background_task_fn=lambda *args, **kwargs: self._spawn_background_task_fn(*args, **kwargs),
                task_repository=lambda: self._task_repository,
                zone_lease_repository=lambda: self._zone_lease_repository,
                global_send_infra_alert=lambda *args, **kwargs: send_infra_alert(*args, **kwargs),
            ),
            self._worker_runtime_state,
        )
        self._worker_runtime_lease_outcomes = WorkerRuntimeLeaseOutcomes(
            WorkerRuntimeLeaseOutcomesPorts(
                lease_release_resolve_started_monotonic=lambda: self._lease_release_resolve_started_monotonic,
                lease_release_resolve_ttl_sec=lambda: self._lease_release_resolve_ttl_sec,
                log_debug=lambda *args, **kwargs: self._log_debug(*args, **kwargs),
                logger=lambda: self._logger,
                now_fn=lambda *args, **kwargs: self._now_fn(*args, **kwargs),
                owner=lambda: self._owner,
                global_send_infra_resolved_alert=lambda *args, **kwargs: send_infra_resolved_alert(*args, **kwargs),
            ),
            self._worker_runtime_state,
        )
        self._worker_runtime_cleanup = WorkerRuntimeCleanup(
            WorkerRuntimeCleanupPorts(
                cancel_wake_task=lambda *args, **kwargs: self._cancel_wake_task(*args, **kwargs),
                claim_generation=lambda *args, **kwargs: self._claim_generation(*args, **kwargs),
                command_repository=lambda: self._command_repository,
                log_debug=lambda *args, **kwargs: self._log_debug(*args, **kwargs),
                logger=lambda: self._logger,
                now_fn=lambda *args, **kwargs: self._now_fn(*args, **kwargs),
                owner=lambda: self._owner,
                reconcile_wake=lambda: self._reconcile_wake,
                safe_mark_intent_terminal=lambda *args, **kwargs: self._safe_mark_intent_terminal(*args, **kwargs),
                shutdown_grace_sec=lambda: self._shutdown_grace_sec,
                task_repository=lambda: self._task_repository,
                zone_lease_repository=lambda: self._zone_lease_repository,
            ),
            self._worker_runtime_state,
        )

    def kick(self) -> Any:
        if self._shutting_down:
            self._log_debug("AE3 runtime kick ignored: worker shutting down")
            return self._drain_task
        self._pending_kicks += 1
        self._cancel_wake_task()
        self._ensure_waiting_command_reconcile_loop()
        self._reconcile_wake.set()
        self._log_debug(
            "AE3 runtime kick received: pending_kicks=%s has_drain_task=%s",
            self._pending_kicks,
            self._drain_task is not None,
        )
        current_loop = self._current_loop()
        if self._drain_task is not None and not self._drain_task.done():
            drain_loop = self._task_loop(self._drain_task)
            if current_loop is None or drain_loop is None or drain_loop is current_loop:
                self._arm_respawn_on_done(self._drain_task)
                self._log_debug("AE3 runtime reusing active drain task")
                return self._drain_task
            self._logger.warning(
                "AE3 runtime detected stale drain task on a different loop; respawning worker",
            )
        return self._spawn_drain_task()

    async def recover_on_startup(self) -> Any:
        return await self._worker_runtime_correction_recovery.recover_on_startup()

    def _enqueue_correction_safety_checks(self, checks: Any) -> int:
        return self._worker_runtime_correction_recovery.enqueue_correction_safety_checks(checks=checks)

    async def _reload_persisted_correction_safety_checks(self, *, now: datetime) -> int:
        return await self._worker_runtime_correction_recovery.reload_persisted_correction_safety_checks(now=now)

    async def shutdown(self, *, grace_sec: float | None = None) -> None:
        return await self._worker_runtime_cleanup.shutdown(grace_sec=grace_sec)

    def _ensure_waiting_command_reconcile_loop(self) -> None:
        return self._worker_runtime_reconcile_policy.ensure_waiting_command_reconcile_loop()

    async def _waiting_command_reconcile_loop(self) -> None:
        return await self._worker_runtime_reconcile_policy.waiting_command_reconcile_loop()

    async def _maybe_run_terminal_command_reconcile_once(self) -> None:
        return await self._worker_runtime_reconcile_policy.maybe_run_terminal_command_reconcile_once()

    async def _run_waiting_command_reconcile_once(self) -> None:
        return await self._worker_runtime_reconcile_policy.run_waiting_command_reconcile_once()

    async def _maybe_run_correction_interrupt_safety_once(self) -> None:
        return await self._worker_runtime_correction_recovery.maybe_run_correction_interrupt_safety_once()

    async def _handle_correction_interrupt_unsafe(
        self,
        *,
        check: Any,
        now: datetime,
        reason: str,
    ) -> None:
        return await self._worker_runtime_correction_recovery.handle_correction_interrupt_unsafe(
            check=check, now=now, reason=reason
        )

    async def _fail_irrigation_replay_intent(
        self,
        *,
        intent_id: int,
        zone_id: int,
        now: datetime,
        error_code: str,
        error_message: str,
    ) -> None:
        return await self._worker_runtime_correction_recovery.fail_irrigation_replay_intent(
            intent_id=intent_id, zone_id=zone_id, now=now, error_code=error_code, error_message=error_message
        )

    async def _replay_irrigation_after_correction_interrupt(
        self,
        *,
        check: Any,
        now: datetime,
    ) -> bool:
        return await self._worker_runtime_correction_recovery.replay_irrigation_after_correction_interrupt(
            check=check, now=now
        )

    async def _maybe_run_stale_task_reconcile_once(self) -> None:
        return await self._worker_runtime_reconcile_policy.maybe_run_stale_task_reconcile_once()

    async def _maybe_run_orphan_intent_reconcile_once(self) -> None:
        return await self._worker_runtime_reconcile_policy.maybe_run_orphan_intent_reconcile_once()

    async def _maybe_refresh_active_task_age_metrics_once(self) -> None:
        return await self._worker_runtime_reconcile_policy.maybe_refresh_active_task_age_metrics_once()

    async def _drain_pending_tasks(self) -> None:
        return await self._worker_runtime_supervisor.drain_pending_tasks()

    async def _claim_next_task_safe(self) -> tuple[Any, Any] | None:
        return await self._worker_runtime_supervisor.claim_next_task_safe()

    async def _await_inflight_task_result(self, done_task: asyncio.Task) -> None:
        return await self._worker_runtime_supervisor.await_inflight_task_result(done_task=done_task)

    async def _execute_claimed_task_safe(self, *, task: Any) -> None:
        return await self._worker_runtime_execution.execute_claimed_task_safe(task=task)

    _task_trace_id = staticmethod(WorkerRuntimeExecution.task_trace_id)

    _claim_generation = staticmethod(WorkerRuntimeExecution.claim_generation)

    def _is_guarded_task_cancellation(self, exc: BaseException) -> bool:
        return self._worker_runtime_execution.is_guarded_task_cancellation(exc=exc)

    async def _fail_task_after_execution_crash(self, *, task: Any, exc: BaseException) -> None:
        return await self._worker_runtime_execution.fail_task_after_execution_crash(task=task, exc=exc)

    async def _drain_supervisor(self) -> None:
        return await self._worker_runtime_supervisor.drain_supervisor()

    async def _execute_claimed_task(self, *, task: Any) -> None:
        return await self._worker_runtime_execution.execute_claimed_task(task=task)

    def _effective_task_timeout(self, *, task: Any, now: datetime) -> tuple[float, str]:
        return self._worker_runtime_execution.effective_task_timeout(task=task, now=now)

    def _should_resolve_zone_lease_release_alert(self, *, zone_id: int) -> bool:
        return self._worker_runtime_lease_outcomes.should_resolve_zone_lease_release_alert(zone_id=zone_id)

    async def _maybe_resolve_zone_lease_release_alert(self, *, task: Any, reason: str) -> None:
        return await self._worker_runtime_lease_outcomes.maybe_resolve_zone_lease_release_alert(
            task=task, reason=reason
        )

    async def _resolve_zone_lease_release_alert(self, *, task: Any, reason: str = "released") -> None:
        return await self._worker_runtime_lease_outcomes.resolve_zone_lease_release_alert(task=task, reason=reason)

    async def _extend_lease_with_transient_retry(
        self,
        *,
        zone_id: int,
        claim_generation: int,
    ) -> bool | None:
        return await lease_heartbeat.extend_lease_with_transient_retry(
            zone_id=zone_id,
            claim_generation=claim_generation,
            lease_repository=self._zone_lease_repository,
            owner=self._owner,
            now_fn=self._now_fn,
            lease_ttl_sec=self._lease_ttl_sec,
            transient_retries=self._lease_heartbeat_transient_retries,
            logger=self._logger,
        )

    async def _signal_lease_lost_from_heartbeat(
        self,
        *,
        zone_id: int,
        lease_lost_event: asyncio.Event,
        consecutive_failures: int,
    ) -> None:
        await lease_heartbeat.signal_lease_lost(
            zone_id=zone_id,
            lease_lost_event=lease_lost_event,
            consecutive_failures=consecutive_failures,
            owner=self._owner,
            logger=self._logger,
            send_alert=send_infra_alert,
        )

    async def _lease_heartbeat(
        self,
        *,
        zone_id: int,
        lease_lost_event: asyncio.Event,
        claim_generation: int,
    ) -> None:
        await lease_heartbeat.run_lease_heartbeat(
            zone_id=zone_id,
            lease_lost_event=lease_lost_event,
            claim_generation=claim_generation,
            owner=self._owner,
            lease_ttl_sec=self._lease_ttl_sec,
            max_failures=self._lease_heartbeat_max_failures,
            extend_lease=self._extend_lease_with_transient_retry,
            signal_lost=self._signal_lease_lost_from_heartbeat,
            logger=self._logger,
            log_debug=self._log_debug,
        )

    async def _abort_task_after_intent_sync_failure(self, *, task: Any, intent_id: int) -> None:
        return await self._worker_runtime_cleanup.abort_task_after_intent_sync_failure(task=task, intent_id=intent_id)

    async def _notify_intent_sync_exhausted(
        self,
        *,
        operation: str,
        intent_id: int,
        task_id: int | None = None,
        zone_id: int | None = None,
        success: bool | None = None,
        error_code: Any = None,
        error_message: Any = None,
    ) -> None:
        await intent_sync.notify_sync_exhausted(
            operation=operation,
            intent_id=intent_id,
            task_id=task_id,
            zone_id=zone_id,
            success=success,
            error_code=error_code,
            error_message=error_message,
            owner=self._owner,
            logger=self._logger,
            send_alert=send_infra_alert,
        )

    async def _resolve_intent_sync_failed_alert(
        self,
        *,
        intent_id: int,
        task_id: int | None = None,
        zone_id: int | None = None,
    ) -> None:
        await intent_sync.resolve_sync_failed_alert(
            intent_id=intent_id,
            task_id=task_id,
            zone_id=zone_id,
            owner=self._owner,
            logger=self._logger,
            send_resolved_alert=send_infra_resolved_alert,
        )

    async def _safe_mark_intent_running(
        self, *, intent_id: int, task_id: int | None = None, zone_id: int | None = None
    ) -> bool:
        return await intent_sync.mark_intent_running(
            intent_id=intent_id,
            task_id=task_id,
            zone_id=zone_id,
            intent_repository=self._zone_intent_repository,
            now_fn=self._now_fn,
            max_retries=self._intent_sync_max_retries,
            logger=self._logger,
            notify_exhausted=self._notify_intent_sync_exhausted,
        )

    async def _safe_mark_intent_terminal(self, *, task: Any, intent_id: int) -> bool:
        return await self._safe_mark_intent_terminal_result(
            intent_id=intent_id,
            now=self._now_fn(),
            success=str(task.status).strip().lower() == "completed",
            error_code=task.error_code,
            error_message=task.error_message,
            task_id=int(getattr(task, "id", 0) or 0) or None,
            zone_id=int(getattr(task, "zone_id", 0) or 0) or None,
        )

    async def _safe_mark_intent_terminal_result(
        self,
        *,
        intent_id: int,
        now: datetime,
        success: bool,
        error_code: Any,
        error_message: Any,
        task_id: int | None = None,
        zone_id: int | None = None,
    ) -> bool:
        return await intent_sync.mark_intent_terminal(
            intent_id=intent_id,
            now=now,
            success=success,
            error_code=error_code,
            error_message=error_message,
            task_id=task_id,
            zone_id=zone_id,
            intent_repository=self._zone_intent_repository,
            max_retries=self._intent_sync_max_retries,
            logger=self._logger,
            notify_exhausted=self._notify_intent_sync_exhausted,
        )

    async def _sync_orphan_intent_terminal(self, **kwargs: Any) -> bool:
        synced = await self._safe_mark_intent_terminal_result(**kwargs)
        if synced:
            await self._resolve_intent_sync_failed_alert(
                intent_id=int(kwargs.get("intent_id") or 0),
                task_id=kwargs.get("task_id"),
                zone_id=kwargs.get("zone_id"),
            )
        return synced

    def _current_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        return self._worker_runtime_supervisor.current_loop()

    def _task_loop(self, task: Any) -> Optional[asyncio.AbstractEventLoop]:
        return self._worker_runtime_supervisor.task_loop(task=task)

    def _spawn_drain_task(self) -> Any:
        return self._worker_runtime_supervisor.spawn_drain_task()

    async def _finalize_inflight_on_shutdown(
        self,
        inflight: set[asyncio.Task],
        *,
        cancel_pending: bool = False,
    ) -> None:
        return await self._worker_runtime_cleanup.finalize_inflight_on_shutdown(
            inflight=inflight, cancel_pending=cancel_pending
        )

    async def _maybe_release_unpublished_claim(self, task: Any) -> bool:
        return await self._worker_runtime_cleanup.maybe_release_unpublished_claim(task=task)

    async def _release_unpublished_claims_for_owner(self) -> int:
        return await self._worker_runtime_cleanup.release_unpublished_claims_for_owner()

    async def _schedule_wake_for_next_pending(self) -> bool:
        return await self._worker_runtime_supervisor.schedule_wake_for_next_pending()

    def _arm_wake_task(self, *, delay: float) -> None:
        return self._worker_runtime_supervisor.arm_wake_task(delay=delay)

    def _cancel_wake_task(self) -> None:
        return self._worker_runtime_supervisor.cancel_wake_task()

    def _arm_respawn_on_done(self, task: Any) -> None:
        return self._worker_runtime_supervisor.arm_respawn_on_done(task=task)

    async def drain_health(self) -> tuple[bool, str]:
        return await self._worker_runtime_supervisor.drain_health()

    async def _has_due_pending_cached(self) -> bool:
        return await self._worker_runtime_supervisor.has_due_pending_cached()

    async def _has_due_pending(self) -> bool:
        return await self._worker_runtime_supervisor.has_due_pending()

    def _log_debug(self, message: str, *args: Any) -> None:
        debug = getattr(self._logger, "debug", None)
        if callable(debug):
            debug(message, *args)

    @property
    def _active_shutdown_grace_sec(self):
        return self._worker_runtime_state.active_shutdown_grace_sec

    @_active_shutdown_grace_sec.setter
    def _active_shutdown_grace_sec(self, value):
        self._worker_runtime_state.active_shutdown_grace_sec = value

    @property
    def _drain_task(self):
        return self._worker_runtime_state.drain_task

    @_drain_task.setter
    def _drain_task(self, value):
        self._worker_runtime_state.drain_task = value

    @property
    def _inflight_automation_tasks(self):
        return self._worker_runtime_state.inflight_automation_tasks

    @_inflight_automation_tasks.setter
    def _inflight_automation_tasks(self, value):
        self._worker_runtime_state.inflight_automation_tasks = value

    @property
    def _last_active_task_age_metrics_monotonic(self):
        return self._worker_runtime_state.last_active_task_age_metrics_monotonic

    @_last_active_task_age_metrics_monotonic.setter
    def _last_active_task_age_metrics_monotonic(self, value):
        self._worker_runtime_state.last_active_task_age_metrics_monotonic = value

    @property
    def _last_drain_exit_ok(self):
        return self._worker_runtime_state.last_drain_exit_ok

    @_last_drain_exit_ok.setter
    def _last_drain_exit_ok(self, value):
        self._worker_runtime_state.last_drain_exit_ok = value

    @property
    def _last_drain_exit_reason(self):
        return self._worker_runtime_state.last_drain_exit_reason

    @_last_drain_exit_reason.setter
    def _last_drain_exit_reason(self, value):
        self._worker_runtime_state.last_drain_exit_reason = value

    @property
    def _last_orphan_intent_reconcile_monotonic(self):
        return self._worker_runtime_state.last_orphan_intent_reconcile_monotonic

    @_last_orphan_intent_reconcile_monotonic.setter
    def _last_orphan_intent_reconcile_monotonic(self, value):
        self._worker_runtime_state.last_orphan_intent_reconcile_monotonic = value

    @property
    def _last_stale_task_reconcile_monotonic(self):
        return self._worker_runtime_state.last_stale_task_reconcile_monotonic

    @_last_stale_task_reconcile_monotonic.setter
    def _last_stale_task_reconcile_monotonic(self, value):
        self._worker_runtime_state.last_stale_task_reconcile_monotonic = value

    @property
    def _last_terminal_command_reconcile_monotonic(self):
        return self._worker_runtime_state.last_terminal_command_reconcile_monotonic

    @_last_terminal_command_reconcile_monotonic.setter
    def _last_terminal_command_reconcile_monotonic(self, value):
        self._worker_runtime_state.last_terminal_command_reconcile_monotonic = value

    @property
    def _lease_release_fail_zones(self):
        return self._worker_runtime_state.lease_release_fail_zones

    @_lease_release_fail_zones.setter
    def _lease_release_fail_zones(self, value):
        self._worker_runtime_state.lease_release_fail_zones = value

    @property
    def _lease_release_resolve_attempt_at(self):
        return self._worker_runtime_state.lease_release_resolve_attempt_at

    @_lease_release_resolve_attempt_at.setter
    def _lease_release_resolve_attempt_at(self, value):
        self._worker_runtime_state.lease_release_resolve_attempt_at = value

    @property
    def _pending_correction_safety_checks(self):
        return self._worker_runtime_state.pending_correction_safety_checks

    @_pending_correction_safety_checks.setter
    def _pending_correction_safety_checks(self, value):
        self._worker_runtime_state.pending_correction_safety_checks = value

    @property
    def _pending_health_cache(self):
        return self._worker_runtime_state.pending_health_cache

    @_pending_health_cache.setter
    def _pending_health_cache(self, value):
        self._worker_runtime_state.pending_health_cache = value

    @property
    def _pending_kicks(self):
        return self._worker_runtime_state.pending_kicks

    @_pending_kicks.setter
    def _pending_kicks(self, value):
        self._worker_runtime_state.pending_kicks = value

    @property
    def _reconcile_loop_task(self):
        return self._worker_runtime_state.reconcile_loop_task

    @_reconcile_loop_task.setter
    def _reconcile_loop_task(self, value):
        self._worker_runtime_state.reconcile_loop_task = value

    @property
    def _respawn_guard_task(self):
        return self._worker_runtime_state.respawn_guard_task

    @_respawn_guard_task.setter
    def _respawn_guard_task(self, value):
        self._worker_runtime_state.respawn_guard_task = value

    @property
    def _shutting_down(self):
        return self._worker_runtime_state.shutting_down

    @_shutting_down.setter
    def _shutting_down(self, value):
        self._worker_runtime_state.shutting_down = value

    @property
    def _wake_handle(self):
        return self._worker_runtime_state.wake_handle

    @_wake_handle.setter
    def _wake_handle(self, value):
        self._worker_runtime_state.wake_handle = value

    @property
    def _wake_task(self):
        return self._worker_runtime_state.wake_task

    @_wake_task.setter
    def _wake_task(self, value):
        self._worker_runtime_state.wake_task = value
