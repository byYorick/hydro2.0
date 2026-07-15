"""Runtime-драйвер AE3-Lite v1 с конкурентным drain."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from datetime import datetime, timezone as _tz
from typing import Any, Callable, Optional

from ae3lite.domain.errors import TaskClaimRollbackError
from ae3lite.application.use_cases.execute_task import (
    TASK_EXECUTION_LEASE_LOST_CANCEL_MSG,
    TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
)
from ae3lite.infrastructure.log_context import log_context_scope
from ae3lite.infrastructure.metrics import (
    ACTIVE_TASKS,
    CLAIM_ROLLBACK_FAILED,
    DRAIN_CRASHES,
    INTENT_SYNC_FAILED,
    LEASE_HEARTBEAT_FAILED,
    RECONCILE_CONSECUTIVE_ERRORS,
    TASK_EXECUTION_CRASHED,
    TICK_DURATION,
    TICK_ERRORS,
    ZONE_LEASE_LOST,
    ZONE_LEASE_RELEASE_FAILED,
)
from common.infra_alerts import send_infra_alert, send_infra_resolved_alert


class Ae3RuntimeWorker:
    """Обрабатывает pending-задачи AE3 и выполняет startup recovery."""

    def __init__(
        self,
        *,
        owner: str,
        claim_next_task_use_case: Any,
        idle_poll_interval_sec: float,
        execute_task_use_case: Any,
        startup_recovery_use_case: Any,
        waiting_command_reconcile_use_case: Any | None = None,
        task_repository: Any | None = None,
        command_repository: Any | None = None,
        zone_lease_repository: Any,
        zone_intent_repository: Any,
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
        self._owner = str(owner or "ae3-runtime").strip() or "ae3-runtime"
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
            float(
                stale_task_reconcile_interval_sec
                if stale_task_reconcile_interval_sec is not None
                else 60.0
            ),
        )
        self._last_stale_task_reconcile_monotonic: float | None = None
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
        self._reconcile_consecutive_errors = 0
        self._pending_health_cache: tuple[float, bool] | None = None
        # Условный resolve lease_release_failed: без spam на каждый finish.
        # known-fail → resolve сразу; иначе opportunistic после warm-up, не чаще TTL.
        self._lease_release_fail_zones: set[int] = set()
        self._lease_release_resolve_attempt_at: dict[int, datetime] = {}
        self._lease_release_resolve_ttl_sec = max(0, int(lease_release_resolve_ttl_sec))
        self._lease_release_resolve_started_monotonic = time.monotonic()

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
        now = self._now_fn()
        from ae3lite.greenhouse_climate.recovery import recover_stale_greenhouse_automation

        await recover_stale_greenhouse_automation(now=now)
        result = await self._startup_recovery_use_case.run(now=now)
        terminal_outcomes = getattr(result, "terminal_outcomes", ()) or ()
        for outcome in terminal_outcomes:
            intent_id = int(getattr(outcome, "intent_id", 0) or 0)
            if intent_id <= 0:
                continue
            await self._safe_mark_intent_terminal_result(
                intent_id=intent_id,
                now=now,
                success=bool(getattr(outcome, "success", False)),
                error_code=getattr(outcome, "error_code", None),
                error_message=getattr(outcome, "error_message", None),
                task_id=int(getattr(outcome, "task_id", 0) or 0) or None,
            )
        self._ensure_waiting_command_reconcile_loop()
        return result

    async def shutdown(self, *, grace_sec: float | None = None) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        effective_grace = max(0.0, float(grace_sec if grace_sec is not None else self._shutdown_grace_sec))
        self._active_shutdown_grace_sec = effective_grace
        self._pending_kicks = 0
        self._log_debug("AE3 runtime shutdown started: grace_sec=%.3f", effective_grace)
        self._cancel_wake_task()
        self._reconcile_wake.set()
        reconcile_loop = self._reconcile_loop_task
        if reconcile_loop is not None and not reconcile_loop.done():
            reconcile_loop.cancel()
            with suppress(asyncio.CancelledError):
                await reconcile_loop
            self._reconcile_loop_task = None

        drain = self._drain_task
        if drain is not None and not drain.done():
            drain_timeout = effective_grace + 5.0
            try:
                await asyncio.wait_for(drain, timeout=drain_timeout)
            except asyncio.TimeoutError:
                self._logger.warning(
                    "AE3 runtime shutdown: drain did not finish within %.1fs, cancelling",
                    drain_timeout,
                )
                drain.cancel()
                with suppress(asyncio.CancelledError):
                    await drain

        released = await self._release_unpublished_claims_for_owner()
        if released > 0:
            self._log_debug("AE3 runtime shutdown: released %s unpublished claims", released)

    def _ensure_waiting_command_reconcile_loop(self) -> None:
        if self._shutting_down:
            return
        if (
            self._waiting_command_reconcile_use_case is None
            and self._stale_task_reconcile_use_case is None
            and self._orphan_intent_reconcile_use_case is None
        ):
            return
        if self._reconcile_loop_task is not None and not self._reconcile_loop_task.done():
            return
        self._reconcile_loop_task = self._spawn_background_task_fn(
            self._waiting_command_reconcile_loop(),
            task_name="ae3lite_waiting_command_reconcile",
        )

    async def _waiting_command_reconcile_loop(self) -> None:
        while not self._shutting_down:
            try:
                await self._run_waiting_command_reconcile_once()
                await self._maybe_run_stale_task_reconcile_once()
                await self._maybe_run_orphan_intent_reconcile_once()
                await self._maybe_refresh_active_task_age_metrics_once()
                self._reconcile_consecutive_errors = 0
                RECONCILE_CONSECUTIVE_ERRORS.set(0)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._reconcile_consecutive_errors += 1
                RECONCILE_CONSECUTIVE_ERRORS.set(self._reconcile_consecutive_errors)
                self._logger.warning(
                    "AE3 waiting_command reconcile loop failed: owner=%s consecutive_errors=%s",
                    self._owner,
                    self._reconcile_consecutive_errors,
                    exc_info=True,
                )
            if self._shutting_down:
                break
            if self._reconcile_consecutive_errors >= 3:
                exponent = self._reconcile_consecutive_errors - 2
                sleep_sec = min(2**exponent, 30.0)
                self._log_debug(
                    "AE3 reconcile backoff sleep: owner=%s consecutive_errors=%s sleep_sec=%.1f",
                    self._owner,
                    self._reconcile_consecutive_errors,
                    sleep_sec,
                )
                try:
                    await asyncio.wait_for(self._reconcile_wake.wait(), timeout=sleep_sec)
                except asyncio.TimeoutError:
                    pass
                self._reconcile_wake.clear()
                continue
            try:
                await asyncio.wait_for(
                    self._reconcile_wake.wait(),
                    timeout=self._reconcile_poll_interval_sec,
                )
            except asyncio.TimeoutError:
                pass
            self._reconcile_wake.clear()

    async def _run_waiting_command_reconcile_once(self) -> None:
        if self._waiting_command_reconcile_use_case is None:
            return
        result = await self._waiting_command_reconcile_use_case.run(
            now=self._now_fn(),
            worker_owner=self._owner,
            inflight_task_ids=frozenset(
                int(getattr(task, "id", 0) or 0)
                for task in self._inflight_automation_tasks.values()
                if int(getattr(task, "id", 0) or 0) > 0
            ),
        )
        terminal_outcomes = getattr(result, "terminal_outcomes", ()) or ()
        for outcome in terminal_outcomes:
            intent_id = int(getattr(outcome, "intent_id", 0) or 0)
            if intent_id <= 0:
                continue
            await self._safe_mark_intent_terminal_result(
                intent_id=intent_id,
                now=self._now_fn(),
                success=bool(getattr(outcome, "success", False)),
                error_code=getattr(outcome, "error_code", None),
                error_message=getattr(outcome, "error_message", None),
                task_id=int(getattr(outcome, "task_id", 0) or 0) or None,
            )
        if bool(getattr(result, "kick_needed", False)) and not self._shutting_down:
            self._pending_kicks += 1
            drain = self._drain_task
            if drain is None or drain.done():
                self._spawn_drain_task()
            else:
                self._arm_respawn_on_done(drain)

    async def _maybe_run_stale_task_reconcile_once(self) -> None:
        if self._stale_task_reconcile_use_case is None:
            return
        now_mono = time.monotonic()
        if self._last_stale_task_reconcile_monotonic is not None:
            elapsed = now_mono - self._last_stale_task_reconcile_monotonic
            if elapsed < self._stale_task_reconcile_interval_sec:
                return
        self._last_stale_task_reconcile_monotonic = now_mono
        result = await self._stale_task_reconcile_use_case.run(
            now=self._now_fn(),
            owner=self._owner,
            inflight_task_ids=frozenset(
                int(getattr(task, "id", 0) or 0)
                for task in self._inflight_automation_tasks.values()
                if int(getattr(task, "id", 0) or 0) > 0
            ),
        )
        if bool(getattr(result, "kick_needed", False)) and not self._shutting_down:
            self._pending_kicks += 1
            drain = self._drain_task
            if drain is None or drain.done():
                self._spawn_drain_task()
            else:
                self._arm_respawn_on_done(drain)

    async def _maybe_run_orphan_intent_reconcile_once(self) -> None:
        if self._orphan_intent_reconcile_use_case is None:
            return
        now_mono = time.monotonic()
        if self._last_orphan_intent_reconcile_monotonic is not None:
            elapsed = now_mono - self._last_orphan_intent_reconcile_monotonic
            if elapsed < self._orphan_intent_reconcile_interval_sec:
                return
        self._last_orphan_intent_reconcile_monotonic = now_mono
        result = await self._orphan_intent_reconcile_use_case.run(
            now=self._now_fn(),
            sync_terminal_fn=self._sync_orphan_intent_terminal,
        )
        reconciled = int(getattr(result, "reconciled_intents", 0) or 0)
        if reconciled > 0:
            self._log_debug(
                "AE3 orphan intent reconcile: reconciled=%s scanned=%s failed=%s owner=%s",
                reconciled,
                getattr(result, "scanned_intents", 0),
                getattr(result, "failed_intents", 0),
                self._owner,
            )

    async def _maybe_refresh_active_task_age_metrics_once(self) -> None:
        if self._task_repository is None:
            return
        refresh = getattr(self._task_repository, "refresh_active_task_age_metrics", None)
        if not callable(refresh):
            return
        now_mono = time.monotonic()
        if self._last_active_task_age_metrics_monotonic is not None:
            elapsed = now_mono - self._last_active_task_age_metrics_monotonic
            if elapsed < self._active_task_age_metrics_interval_sec:
                return
        self._last_active_task_age_metrics_monotonic = now_mono
        try:
            await refresh(now=self._now_fn())
        except Exception:
            self._logger.warning(
                "AE3 reconcile: failed to refresh active task age metrics: owner=%s",
                self._owner,
                exc_info=True,
            )

    async def _drain_pending_tasks(self) -> None:
        self._log_debug("AE3 runtime drain started")
        drain_ok = False
        drain_reason = "worker_unexpected_exit"
        inflight: set[asyncio.Task] = set()
        try:
            while not self._shutting_down:
                while not self._shutting_down and len(inflight) < self._max_parallel_tasks:
                    claimed = await self._claim_next_task_safe()
                    if claimed is None:
                        break

                    self._pending_kicks = 0
                    task, _lease = claimed
                    self._log_debug("AE3 runtime claimed task: task_id=%s zone_id=%s", task.id, task.zone_id)
                    worker_task = asyncio.create_task(
                        self._execute_claimed_task_safe(task=task),
                        name=f"ae3lite_claimed_task:{task.id}",
                    )
                    inflight.add(worker_task)
                    self._inflight_automation_tasks[worker_task] = task

                if inflight:
                    done, _pending = await asyncio.wait(
                        inflight,
                        timeout=0.0,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not done:
                        await asyncio.sleep(0.01)
                        continue
                    for done_task in done:
                        inflight.discard(done_task)
                        self._inflight_automation_tasks.pop(done_task, None)
                        await self._await_inflight_task_result(done_task)
                    continue

                if self._shutting_down:
                    break

                claimed = await self._claim_next_task_safe()
                if claimed is None:
                    if self._pending_kicks > 0:
                        self._log_debug("AE3 runtime drain retrying after deferred kick")
                        self._pending_kicks = 0
                        continue
                    if await self._schedule_wake_for_next_pending():
                        self._log_debug("AE3 runtime drain sleeping until next due task")
                        drain_ok = True
                        drain_reason = "sleeping"
                        return
                    self._log_debug("AE3 runtime drain idle: no pending tasks")
                    drain_ok = True
                    drain_reason = "idle"
                    return
                self._pending_kicks = 0
                task, _lease = claimed
                self._log_debug("AE3 runtime claimed task: task_id=%s zone_id=%s", task.id, task.zone_id)
                worker_task = asyncio.create_task(
                    self._execute_claimed_task_safe(task=task),
                    name=f"ae3lite_claimed_task:{task.id}",
                )
                inflight.add(worker_task)
                self._inflight_automation_tasks[worker_task] = task

            if inflight:
                await self._finalize_inflight_on_shutdown(inflight)
            drain_ok = True
            drain_reason = "shutdown"
        except asyncio.CancelledError:
            if inflight:
                await self._finalize_inflight_on_shutdown(inflight, cancel_pending=True)
            drain_reason = "worker_cancelled"
            raise
        except Exception as exc:
            if inflight:
                await self._finalize_inflight_on_shutdown(inflight, cancel_pending=True)
            drain_reason = f"worker_crashed:{type(exc).__name__}"
            raise
        finally:
            self._last_drain_exit_ok = drain_ok
            self._last_drain_exit_reason = drain_reason

    async def _claim_next_task_safe(self) -> tuple[Any, Any] | None:
        try:
            return await self._claim_next_task_use_case.run(owner=self._owner, now=self._now_fn())
        except TaskClaimRollbackError as exc:
            CLAIM_ROLLBACK_FAILED.inc()
            self._logger.error(
                "AE3 claim rollback failed after zone lease conflict; "
                "task escalated via fail_for_recovery when possible: owner=%s error=%s",
                self._owner,
                exc,
            )
            return None

    async def _await_inflight_task_result(self, done_task: asyncio.Task) -> None:
        try:
            await done_task
        except asyncio.CancelledError:
            raise
        except Exception:
            # Per-task isolation: _execute_claimed_task_safe не пробрасывает ошибки выполнения.
            self._log_debug(
                "AE3 runtime ignored inflight task exception after safe wrapper: task_name=%s",
                done_task.get_name(),
            )

    async def _execute_claimed_task_safe(self, *, task: Any) -> None:
        trace_id = self._task_trace_id(task)
        context_kwargs: dict[str, Any] = {
            "task_id": getattr(task, "id", None),
            "zone_id": getattr(task, "zone_id", None),
        }
        if trace_id:
            context_kwargs["trace_id"] = trace_id
        with log_context_scope(**context_kwargs):
            try:
                await self._execute_claimed_task(task=task)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error_name = type(exc).__name__
                TASK_EXECUTION_CRASHED.labels(error=error_name).inc()
                self._logger.error(
                    "AE3 task execution crashed in worker wrapper: zone_id=%s task_id=%s owner=%s error_type=%s",
                    getattr(task, "zone_id", None),
                    getattr(task, "id", None),
                    self._owner,
                    error_name,
                    exc_info=True,
                )
                await self._fail_task_after_execution_crash(task=task, exc=exc)

    @staticmethod
    def _task_trace_id(task: Any) -> str | None:
        intent_meta = getattr(task, "intent_meta", None)
        if not isinstance(intent_meta, dict):
            return None
        trace_id = str(intent_meta.get("trace_id") or "").strip()
        return trace_id or None

    async def _fail_task_after_execution_crash(self, *, task: Any, exc: Exception) -> None:
        error_message = str(exc).strip() or type(exc).__name__
        task_id = int(getattr(task, "id", 0) or 0)
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        if task_id > 0 and self._task_repository is not None:
            fail_for_recovery = getattr(self._task_repository, "fail_for_recovery", None)
            if callable(fail_for_recovery):
                try:
                    await fail_for_recovery(
                        task_id=task_id,
                        error_code="ae3_task_execution_crashed",
                        error_message=error_message,
                        now=self._now_fn(),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._logger.warning(
                        "AE3 runtime не смог перевести задачу в failed после crash: zone_id=%s task_id=%s owner=%s",
                        zone_id,
                        task_id,
                        self._owner,
                        exc_info=True,
                    )
        intent_id = int(getattr(task, "intent_id", 0) or 0)
        if intent_id > 0:
            await self._safe_mark_intent_terminal_result(
                intent_id=intent_id,
                now=self._now_fn(),
                success=False,
                error_code="ae3_task_execution_crashed",
                error_message=error_message,
                task_id=task_id or None,
                zone_id=zone_id or None,
            )
        if zone_id > 0:
            try:
                released = await self._zone_lease_repository.release(zone_id=zone_id, owner=self._owner)
                if not released:
                    await asyncio.sleep(0.05)
                    await self._zone_lease_repository.release(zone_id=zone_id, owner=self._owner)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.warning(
                    "AE3 runtime не смог освободить lease после crash: zone_id=%s task_id=%s owner=%s",
                    zone_id,
                    task_id,
                    self._owner,
                    exc_info=True,
                )

    async def _drain_supervisor(self) -> None:
        backoff_sec = 1.0
        while not self._shutting_down:
            try:
                await self._drain_pending_tasks()
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                DRAIN_CRASHES.inc()
                self._logger.error(
                    "AE3 drain supervisor caught crash: owner=%s backoff_sec=%.1f",
                    self._owner,
                    backoff_sec,
                    exc_info=True,
                )
                if self._shutting_down:
                    break
                await asyncio.sleep(backoff_sec)
                backoff_sec = min(backoff_sec * 2.0, 60.0)

    async def _execute_claimed_task(self, *, task: Any) -> None:
        intent_id = int(task.intent_id or 0)
        if intent_id > 0:
            if not await self._safe_mark_intent_running(
                intent_id=intent_id,
                task_id=int(task.id),
                zone_id=int(task.zone_id),
            ):
                await self._abort_task_after_intent_sync_failure(task=task, intent_id=intent_id)
                return

        lease_lost_event = asyncio.Event()
        heartbeat_task = self._spawn_background_task_fn(
            self._lease_heartbeat(zone_id=task.zone_id, lease_lost_event=lease_lost_event),
            task_name="ae3lite_lease_heartbeat",
        )
        final_task = task
        timed_out = False
        ACTIVE_TASKS.labels(topology=task.topology).inc()
        try:
            with TICK_DURATION.time():
                execution_task = asyncio.create_task(
                    self._execute_task_use_case.run(task=task, now=self._now_fn()),
                    name=f"ae3lite_execute_task:{task.id}",
                )
                lease_wait_task = asyncio.create_task(
                    lease_lost_event.wait(),
                    name=f"ae3lite_lease_wait:{task.id}",
                )
                try:
                    done, _pending = await asyncio.wait(
                        {execution_task, lease_wait_task},
                        timeout=float(self._max_task_execution_sec),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if execution_task in done:
                        final_task = await execution_task
                    elif lease_wait_task in done and lease_lost_event.is_set():
                        execution_task.cancel(TASK_EXECUTION_LEASE_LOST_CANCEL_MSG)
                        try:
                            final_task = await execution_task
                        except asyncio.CancelledError:
                            final_task = None
                        TICK_ERRORS.labels(error_type="LeaseLost").inc()
                        self._logger.error(
                            "AE3 task execution cancelled after lease loss: zone_id=%s task_id=%s",
                            task.zone_id,
                            task.id,
                        )
                    else:
                        timed_out = True
                        execution_task.cancel(TASK_EXECUTION_TIMEOUT_CANCEL_MSG)
                        try:
                            final_task = await execution_task
                        except asyncio.CancelledError:
                            final_task = None
                        TICK_ERRORS.labels(error_type="TimeoutError").inc()
                        self._logger.error(
                            "AE3 task execution timeout: zone_id=%s task_id=%s timeout_sec=%s",
                            task.zone_id,
                            task.id,
                            self._max_task_execution_sec,
                        )
                except asyncio.CancelledError:
                    lease_wait_task.cancel()
                    execution_task.cancel()
                    raise
                finally:
                    lease_wait_task.cancel()
        except Exception as exc:
            TICK_ERRORS.labels(error_type=type(exc).__name__).inc()
            raise
        finally:
            ACTIVE_TASKS.labels(topology=task.topology).dec()
            cancel = getattr(heartbeat_task, "cancel", None)
            if callable(cancel):
                cancel()
            if lease_lost_event.is_set():
                self._logger.warning(
                    "AE3 runtime task finished after lease was lost: zone_id=%s task_id=%s",
                    task.zone_id,
                    task.id,
                )
            released = await self._zone_lease_repository.release(zone_id=task.zone_id, owner=self._owner)
            if not released:
                await asyncio.sleep(0.05)
                released = await self._zone_lease_repository.release(zone_id=task.zone_id, owner=self._owner)
            if released:
                await self._maybe_resolve_zone_lease_release_alert(task=task, reason="released")
            else:
                lease_after_release = await self._zone_lease_repository.get(zone_id=task.zone_id)
                if lease_after_release is None:
                    # Lease уже снят — не ошибка; resolve только known-fail / TTL opportunistic.
                    self._log_debug(
                        "AE3 runtime lease already absent during release: zone_id=%s owner=%s task_id=%s",
                        task.zone_id,
                        self._owner,
                        task.id,
                    )
                    await self._maybe_resolve_zone_lease_release_alert(
                        task=task, reason="already_absent"
                    )
                elif lease_after_release.owner != self._owner:
                    self._log_debug(
                        "AE3 runtime lease owned by another worker after task finish: zone_id=%s owner=%s task_id=%s lease_owner=%s",
                        task.zone_id,
                        self._owner,
                        task.id,
                        lease_after_release.owner,
                    )
                    await self._maybe_resolve_zone_lease_release_alert(
                        task=task, reason="foreign_owner"
                    )
                else:
                    self._logger.warning(
                        "AE3 runtime failed to release zone lease: zone_id=%s owner=%s task_id=%s",
                        task.zone_id,
                        self._owner,
                        task.id,
                    )
                    ZONE_LEASE_RELEASE_FAILED.labels(zone_id=str(task.zone_id)).inc()
                    try:
                        sent = await send_infra_alert(
                            code="ae3_zone_lease_release_failed",
                            alert_type="AE3 Zone Lease Release Failed",
                            message="Не удалось освободить lease зоны после завершения задачи.",
                            severity="error",
                            zone_id=int(task.zone_id),
                            service="automation-engine",
                            component="worker:lease",
                            details={
                                "task_id": int(task.id),
                                "owner": self._owner,
                                "topology": str(getattr(task, "topology", "")),
                                "message": "Не удалось освободить lease зоны после завершения задачи: зона могла остаться заблокированной.",
                            },
                        )
                        if sent:
                            self._lease_release_fail_zones.add(int(task.zone_id))
                    except Exception:
                        self._logger.warning(
                            "AE3 не смог отправить alert lease_release_failed zone_id=%s",
                            task.zone_id,
                            exc_info=True,
                        )

        if timed_out:
            if intent_id > 0:
                if final_task is not None and not getattr(final_task, "is_active", True):
                    await self._safe_mark_intent_terminal(task=final_task, intent_id=intent_id)
                else:
                    await self._safe_mark_intent_terminal_result(
                        intent_id=intent_id,
                        now=self._now_fn(),
                        success=False,
                        error_code="task_execution_timeout",
                        error_message=f"Выполнение задачи превысило timeout {self._max_task_execution_sec} с",
                        task_id=int(task.id),
                        zone_id=int(task.zone_id),
                    )
            self._log_debug("AE3 runtime продолжает drain после задачи с превышенным timeout: task_id=%s", task.id)
            return

        if lease_lost_event.is_set():
            if intent_id > 0:
                if final_task is not None and not getattr(final_task, "is_active", True):
                    await self._safe_mark_intent_terminal(task=final_task, intent_id=intent_id)
                else:
                    await self._safe_mark_intent_terminal_result(
                        intent_id=intent_id,
                        now=self._now_fn(),
                        success=False,
                        error_code=TASK_EXECUTION_LEASE_LOST_CANCEL_MSG,
                        error_message="Во время выполнения задачи был потерян lease зоны",
                        task_id=int(task.id),
                        zone_id=int(task.zone_id),
                    )
            self._log_debug("AE3 runtime продолжает drain после потери lease: task_id=%s", task.id)
            return

        if intent_id > 0 and final_task is not None and not final_task.is_active:
            await self._safe_mark_intent_terminal(task=final_task, intent_id=intent_id)

    def _should_resolve_zone_lease_release_alert(self, *, zone_id: int) -> bool:
        """Resolve только при known-fail или редком TTL opportunistic (stuck после restart)."""
        if zone_id in self._lease_release_fail_zones:
            return True
        ttl = self._lease_release_resolve_ttl_sec
        if ttl <= 0:
            return False
        warm_up = time.monotonic() - self._lease_release_resolve_started_monotonic
        if warm_up < float(ttl):
            return False
        last = self._lease_release_resolve_attempt_at.get(zone_id)
        if last is None:
            return True
        try:
            age_sec = (self._now_fn() - last).total_seconds()
        except Exception:
            return True
        return age_sec >= float(ttl)

    async def _maybe_resolve_zone_lease_release_alert(self, *, task: Any, reason: str) -> None:
        zone_id = int(task.zone_id)
        if not self._should_resolve_zone_lease_release_alert(zone_id=zone_id):
            self._log_debug(
                "AE3 skip lease_release resolve: zone_id=%s reason=%s known_fail=%s",
                zone_id,
                reason,
                zone_id in self._lease_release_fail_zones,
            )
            return
        await self._resolve_zone_lease_release_alert(task=task, reason=reason)

    async def _resolve_zone_lease_release_alert(self, *, task: Any, reason: str = "released") -> None:
        zone_id = int(task.zone_id)
        now = self._now_fn()
        try:
            await send_infra_resolved_alert(
                code="ae3_zone_lease_release_failed",
                alert_type="AE3 Zone Lease Release Failed",
                message="После завершения задачи lease зоны больше не присутствует.",
                zone_id=zone_id,
                service="automation-engine",
                component="worker:lease",
                details={
                    "task_id": int(task.id),
                    "owner": self._owner,
                    "topology": str(getattr(task, "topology", "")),
                    "reason": reason,
                    "message": "После завершения задачи lease зоны больше не присутствует.",
                },
            )
            self._lease_release_fail_zones.discard(zone_id)
            self._lease_release_resolve_attempt_at[zone_id] = now
        except Exception:
            self._logger.warning(
                "AE3 не смог отправить alert lease_release_resolved zone_id=%s",
                task.zone_id,
                exc_info=True,
            )

    async def _extend_lease_with_transient_retry(self, *, zone_id: int) -> bool:
        """Продлевает lease с retry на transient DB-ошибки."""
        max_attempts = 1 + self._lease_heartbeat_transient_retries
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                return bool(
                    await self._zone_lease_repository.extend(
                        zone_id=zone_id,
                        owner=self._owner,
                        now=self._now_fn(),
                        lease_ttl_sec=self._lease_ttl_sec,
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt + 1 >= max_attempts:
                    self._logger.warning(
                        "AE3 lease heartbeat: extend failed after transient retries zone_id=%s owner=%s",
                        zone_id,
                        self._owner,
                        exc_info=True,
                    )
                    return False
        if last_exc is not None:
            return False
        return False

    async def _signal_lease_lost_from_heartbeat(
        self,
        *,
        zone_id: int,
        lease_lost_event: asyncio.Event,
        consecutive_failures: int,
    ) -> None:
        self._logger.error(
            "AE3 lease heartbeat: failed to extend lease for zone_id=%s owner=%s after %s attempts — "
            "signaling lease_lost; in-flight task execution will be cancelled",
            zone_id,
            self._owner,
            consecutive_failures,
        )
        ZONE_LEASE_LOST.labels(zone_id=str(zone_id)).inc()
        lease_lost_event.set()
        try:
            await send_infra_alert(
                code="ae3_zone_lease_lost",
                alert_type="AE3 Zone Lease Lost",
                message=(
                    "Heartbeat zone lease не смог продлить lease; worker помечает lease_lost "
                    "и отменяет выполняющуюся задачу для этой зоны."
                ),
                severity="critical",
                zone_id=int(zone_id),
                service="automation-engine",
                component="worker:heartbeat",
                details={
                    "owner": self._owner,
                    "consecutive_failures": consecutive_failures,
                    "message": "Heartbeat zone lease не смог продлить lease: зона могла быть перехвачена или зависнуть.",
                },
            )
        except Exception:
            self._logger.warning(
                "AE3 не смог отправить alert lease_lost zone_id=%s",
                zone_id,
                exc_info=True,
            )

    async def _lease_heartbeat(self, *, zone_id: int, lease_lost_event: asyncio.Event) -> None:
        """Периодически продлевает zone lease во время выполнения задачи.

        Heartbeat срабатывает примерно каждые 1/3 от TTL. После
        ``lease_heartbeat_max_failures`` подряд неудачных extend (с учётом
        transient retry) сигнализирует lease_lost и завершается.
        """
        interval = max(10.0, self._lease_ttl_sec / 3.0)
        consecutive_failures = 0
        while True:
            await asyncio.sleep(interval)
            try:
                extended = await self._extend_lease_with_transient_retry(zone_id=zone_id)
                if extended:
                    consecutive_failures = 0
                    self._log_debug("AE3 lease heartbeat extended: zone_id=%s owner=%s", zone_id, self._owner)
                    continue

                consecutive_failures += 1
                LEASE_HEARTBEAT_FAILED.labels(zone_id=str(zone_id)).inc()
                if consecutive_failures < self._lease_heartbeat_max_failures:
                    continue

                await self._signal_lease_lost_from_heartbeat(
                    zone_id=zone_id,
                    lease_lost_event=lease_lost_event,
                    consecutive_failures=consecutive_failures,
                )
                break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._logger.warning(
                    "AE3 lease heartbeat error: zone_id=%s owner=%s error_type=%s",
                    zone_id,
                    self._owner,
                    type(exc).__name__,
                    exc_info=True,
                )
                consecutive_failures += 1
                LEASE_HEARTBEAT_FAILED.labels(zone_id=str(zone_id)).inc()
                if consecutive_failures < self._lease_heartbeat_max_failures:
                    continue

                await self._signal_lease_lost_from_heartbeat(
                    zone_id=zone_id,
                    lease_lost_event=lease_lost_event,
                    consecutive_failures=consecutive_failures,
                )
                break

    async def _abort_task_after_intent_sync_failure(self, *, task: Any, intent_id: int) -> None:
        error_code = "ae3_intent_sync_failed"
        error_message = (
            f"Не удалось синхронизировать intent {intent_id} в running после исчерпания retry"
        )
        task_id = int(getattr(task, "id", 0) or 0)
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        if task_id > 0 and self._task_repository is not None:
            fail_for_recovery = getattr(self._task_repository, "fail_for_recovery", None)
            if callable(fail_for_recovery):
                try:
                    await fail_for_recovery(
                        task_id=task_id,
                        error_code=error_code,
                        error_message=error_message,
                        now=self._now_fn(),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._logger.warning(
                        "AE3 runtime не смог перевести задачу в failed после intent sync failure: "
                        "zone_id=%s task_id=%s owner=%s",
                        zone_id,
                        task_id,
                        self._owner,
                        exc_info=True,
                    )
        await self._safe_mark_intent_terminal_result(
            intent_id=intent_id,
            now=self._now_fn(),
            success=False,
            error_code=error_code,
            error_message=error_message,
            task_id=task_id or None,
            zone_id=zone_id or None,
        )
        if zone_id > 0:
            try:
                released = await self._zone_lease_repository.release(zone_id=zone_id, owner=self._owner)
                if not released:
                    await asyncio.sleep(0.05)
                    await self._zone_lease_repository.release(zone_id=zone_id, owner=self._owner)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.warning(
                    "AE3 runtime не смог освободить lease после intent sync failure: "
                    "zone_id=%s task_id=%s owner=%s",
                    zone_id,
                    task_id,
                    self._owner,
                    exc_info=True,
                )

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
        normalized_zone_id = int(zone_id or 0)
        normalized_task_id = int(task_id or 0)
        try:
            await send_infra_alert(
                code="ae3_intent_sync_failed",
                alert_type="AE3 Intent Sync Failed",
                message=(
                    f"Не удалось синхронизировать intent ({operation}) после исчерпания retry."
                ),
                severity="error",
                zone_id=normalized_zone_id if normalized_zone_id > 0 else None,
                service="automation-engine",
                component="worker:intent_sync",
                intent_id=intent_id,
                details={
                    "operation": operation,
                    "intent_id": intent_id,
                    "task_id": normalized_task_id if normalized_task_id > 0 else None,
                    "zone_id": normalized_zone_id if normalized_zone_id > 0 else None,
                    "success": success,
                    "error_code": error_code,
                    "error_message": error_message,
                    "owner": self._owner,
                    "message": (
                        "Task и intent рассинхронизированы: ae_task terminal, intent остаётся active. "
                        "Фоновый orphan-intent janitor продолжит retry."
                    ),
                },
            )
        except Exception:
            self._logger.warning(
                "AE3 не смог отправить alert intent_sync_failed intent_id=%s operation=%s",
                intent_id,
                operation,
                exc_info=True,
            )

    async def _resolve_intent_sync_failed_alert(
        self,
        *,
        intent_id: int,
        task_id: int | None = None,
        zone_id: int | None = None,
    ) -> None:
        normalized_zone_id = int(zone_id or 0)
        normalized_task_id = int(task_id or 0)
        try:
            await send_infra_resolved_alert(
                code="ae3_intent_sync_failed",
                alert_type="AE3 Intent Sync Failed",
                message="Intent успешно синхронизирован в terminal после retry/janitor.",
                zone_id=normalized_zone_id if normalized_zone_id > 0 else None,
                service="automation-engine",
                component="worker:intent_sync",
                intent_id=intent_id,
                details={
                    "intent_id": intent_id,
                    "task_id": normalized_task_id if normalized_task_id > 0 else None,
                    "zone_id": normalized_zone_id if normalized_zone_id > 0 else None,
                    "owner": self._owner,
                    "message": "Intent успешно синхронизирован в terminal после retry/janitor.",
                },
            )
        except Exception:
            self._logger.warning(
                "AE3 не смог отправить alert intent_sync_resolved intent_id=%s",
                intent_id,
                exc_info=True,
            )

    async def _safe_mark_intent_running(self, *, intent_id: int, task_id: int | None = None, zone_id: int | None = None) -> bool:
        max_attempts = 1 + self._intent_sync_max_retries
        for attempt in range(max_attempts):
            try:
                await self._zone_intent_repository.mark_running(intent_id=intent_id, now=self._now_fn())
                return True
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt + 1 >= max_attempts:
                    INTENT_SYNC_FAILED.labels(operation="mark_running").inc()
                    self._logger.warning(
                        "AE3 runtime не смог перевести intent в running: intent_id=%s",
                        intent_id,
                        exc_info=True,
                    )
                    await self._notify_intent_sync_exhausted(
                        operation="mark_running",
                        intent_id=intent_id,
                        task_id=task_id,
                        zone_id=zone_id,
                    )
                    return False
        return False

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
        max_attempts = 1 + self._intent_sync_max_retries
        for attempt in range(max_attempts):
            try:
                await self._zone_intent_repository.mark_terminal(
                    intent_id=intent_id,
                    now=now,
                    success=success,
                    error_code=error_code,
                    error_message=error_message,
                )
                return True
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt + 1 >= max_attempts:
                    INTENT_SYNC_FAILED.labels(operation="mark_terminal").inc()
                    self._logger.warning(
                        "AE3 runtime не смог перевести intent в terminal: intent_id=%s task_id=%s zone_id=%s",
                        intent_id,
                        task_id,
                        zone_id,
                        exc_info=True,
                    )
                    await self._notify_intent_sync_exhausted(
                        operation="mark_terminal",
                        intent_id=intent_id,
                        task_id=task_id,
                        zone_id=zone_id,
                        success=success,
                        error_code=error_code,
                        error_message=error_message,
                    )
                    return False
        return False

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
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def _task_loop(self, task: Any) -> Optional[asyncio.AbstractEventLoop]:
        get_loop = getattr(task, "get_loop", None)
        if not callable(get_loop):
            return None
        try:
            return get_loop()
        except (RuntimeError, AttributeError):
            return None

    def _spawn_drain_task(self) -> Any:
        if self._shutting_down:
            self._log_debug("AE3 runtime drain spawn skipped: worker shutting down")
            return self._drain_task
        self._log_debug("AE3 runtime spawning drain task")
        task = self._spawn_background_task_fn(
            self._drain_supervisor(),
            task_name="ae3lite_runtime_worker",
        )
        self._drain_task = task
        self._respawn_guard_task = None
        return task

    async def _finalize_inflight_on_shutdown(
        self,
        inflight: set[asyncio.Task],
        *,
        cancel_pending: bool = False,
    ) -> None:
        if not inflight:
            return
        grace = (
            self._active_shutdown_grace_sec
            if self._active_shutdown_grace_sec is not None
            else self._shutdown_grace_sec
        )
        if grace > 0.0 and not cancel_pending:
            _done, still_pending = await asyncio.wait(inflight, timeout=grace)
            if still_pending:
                for pending_task in still_pending:
                    pending_task.cancel()
                await asyncio.gather(*still_pending, return_exceptions=True)
        else:
            for pending_task in list(inflight):
                pending_task.cancel()
            await asyncio.gather(*inflight, return_exceptions=True)

        for worker_task in list(inflight):
            automation_task = self._inflight_automation_tasks.pop(worker_task, None)
            if automation_task is not None:
                await self._maybe_release_unpublished_claim(automation_task)
        inflight.clear()

    async def _maybe_release_unpublished_claim(self, task: Any) -> bool:
        if self._task_repository is None:
            return False
        task_id = int(getattr(task, "id", 0) or 0)
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        if task_id <= 0:
            return False

        requeue_fn = getattr(self._task_repository, "requeue_unpublished_execution", None)
        if callable(requeue_fn):
            requeued = await requeue_fn(task_id=task_id, owner=self._owner, now=self._now_fn())
            if requeued is None:
                return False
            if zone_id > 0:
                await self._zone_lease_repository.release(zone_id=zone_id, owner=self._owner)
            self._log_debug(
                "AE3 runtime shutdown requeued unpublished execution: task_id=%s zone_id=%s",
                task_id,
                zone_id,
            )
            return True

        if self._command_repository is None:
            return False
        current = await self._task_repository.get_by_id(task_id=task_id)
        if current is None or str(getattr(current, "status", "")) != "claimed":
            return False
        ae_cmd = await self._command_repository.get_latest_for_task(task_id=task_id)
        if ae_cmd is not None:
            return False
        released = await self._task_repository.release_claim(
            task_id=task_id,
            owner=self._owner,
            now=self._now_fn(),
        )
        if released and zone_id > 0:
            await self._zone_lease_repository.release(zone_id=zone_id, owner=self._owner)
        if released:
            self._log_debug(
                "AE3 runtime shutdown released unpublished claim: task_id=%s zone_id=%s",
                task_id,
                getattr(current, "zone_id", None),
            )
        return bool(released)

    async def _release_unpublished_claims_for_owner(self) -> int:
        if self._task_repository is None:
            return 0
        list_unpublished = getattr(self._task_repository, "list_unpublished_execution_by_owner", None)
        if callable(list_unpublished):
            claimed_tasks = await list_unpublished(owner=self._owner)
        else:
            list_claimed = getattr(self._task_repository, "list_claimed_by_owner", None)
            if not callable(list_claimed):
                return 0
            claimed_tasks = await list_claimed(owner=self._owner)
        released = 0
        for task in claimed_tasks:
            if await self._maybe_release_unpublished_claim(task):
                released += 1
        return released

    async def _schedule_wake_for_next_pending(self) -> bool:
        if self._shutting_down:
            return False
        getter = getattr(self._claim_next_task_use_case, "next_pending_due_at", None)
        if not callable(getter):
            return False
        next_due_at = await getter()
        if next_due_at is None:
            return False

        now = self._now_fn()
        # Нормализовать обе метки к UTC-aware, чтобы избежать неверных сравнений,
        # когда одна дата tz-aware, а другая naive. Простое replace(tzinfo=None)
        # убирает tzinfo без конвертации и может тихо исказить время.
        next_due_utc = (
            next_due_at.astimezone(_tz.utc)
            if next_due_at.tzinfo is not None
            else next_due_at.replace(tzinfo=_tz.utc)
        )
        now_utc = (
            now.astimezone(_tz.utc)
            if now.tzinfo is not None
            else now.replace(tzinfo=_tz.utc)
        )

        delay = (next_due_utc - now_utc).total_seconds()
        if delay <= 0:
            delay = self._idle_poll_interval_sec
        self._log_debug(
            "AE3 runtime scheduled wake: owner=%s due_in_sec=%.3f next_due_at=%s",
            self._owner,
            delay,
            next_due_at,
        )
        self._arm_wake_task(delay=delay)
        return True

    def _arm_wake_task(self, *, delay: float) -> None:
        wake_handle = self._wake_handle
        if wake_handle is not None and not wake_handle.cancelled():
            return
        if self._wake_task is not None and not self._wake_task.done():
            return

        loop = self._current_loop()
        if loop is None:
            return

        def _wake_callback() -> None:
            if self._wake_handle is not wake_handle_ref:
                return
            self._wake_handle = None
            if self._shutting_down:
                self._log_debug("AE3 runtime wake skipped: worker shutting down")
                return
            if self._drain_task is not None and not self._drain_task.done():
                self._log_debug(
                    "AE3 runtime wake skipped: owner=%s active_drain_task=%s",
                    self._owner,
                    self._drain_task,
                )
                self._pending_kicks += 1
                self._arm_respawn_on_done(self._drain_task)
                return
            self._log_debug(
                "AE3 runtime wake firing: owner=%s delay_sec=%.3f",
                self._owner,
                delay,
            )
            self._spawn_drain_task()

        wake_handle_ref = loop.call_later(max(0.0, delay), _wake_callback)
        self._wake_handle = wake_handle_ref
        self._wake_task = None

    def _cancel_wake_task(self) -> None:
        wake_handle = self._wake_handle
        if wake_handle is not None:
            wake_handle.cancel()
            self._wake_handle = None
        wake_task = self._wake_task
        if wake_task is None or wake_task.done():
            self._wake_task = None
            return
        cancel = getattr(wake_task, "cancel", None)
        if callable(cancel):
            cancel()
        self._wake_task = None

    def _arm_respawn_on_done(self, task: Any) -> None:
        if self._respawn_guard_task is task:
            return
        self._respawn_guard_task = task

        def _on_done(done_task: Any) -> None:
            if self._respawn_guard_task is not done_task:
                return
            self._respawn_guard_task = None
            current_task = self._drain_task
            if current_task is not done_task and current_task is not None and not current_task.done():
                return
            if self._pending_kicks <= 0 or self._shutting_down:
                return
            self._log_debug("AE3 runtime respawning drain task after deferred kick")
            self._spawn_drain_task()

        add_done_callback = getattr(task, "add_done_callback", None)
        if callable(add_done_callback):
            add_done_callback(_on_done)

    async def drain_health(self) -> tuple[bool, str]:
        """Возвращает `(ok, reason)` для readiness-probe."""
        drain = self._drain_task
        if drain is not None and not drain.done():
            return True, self._owner

        if drain is None or drain.done():
            if await self._has_due_pending_cached():
                return False, "drain_dead_with_pending"

        if drain is None:
            return self._last_drain_exit_ok, self._last_drain_exit_reason
        if drain.cancelled():
            return False, "worker_cancelled"
        try:
            exc = drain.exception()
        except Exception:
            return False, "worker_exception_unknown"
        if exc is not None:
            return False, f"worker_crashed:{type(exc).__name__}"
        return self._last_drain_exit_ok, self._last_drain_exit_reason

    async def _has_due_pending_cached(self) -> bool:
        now_mono = time.monotonic()
        cached = self._pending_health_cache
        if cached is not None and (now_mono - cached[0]) < 5.0:
            return cached[1]

        has_due_pending = await self._has_due_pending()
        self._pending_health_cache = (now_mono, has_due_pending)
        return has_due_pending

    async def _has_due_pending(self) -> bool:
        getter = getattr(self._claim_next_task_use_case, "next_pending_due_at", None)
        if not callable(getter):
            return False
        next_due_at = await getter()
        if next_due_at is None:
            return False

        now = self._now_fn()
        next_due_utc = (
            next_due_at.astimezone(_tz.utc)
            if next_due_at.tzinfo is not None
            else next_due_at.replace(tzinfo=_tz.utc)
        )
        now_utc = (
            now.astimezone(_tz.utc)
            if now.tzinfo is not None
            else now.replace(tzinfo=_tz.utc)
        )
        return next_due_utc <= now_utc

    def _log_debug(self, message: str, *args: Any) -> None:
        debug = getattr(self._logger, "debug", None)
        if callable(debug):
            debug(message, *args)
