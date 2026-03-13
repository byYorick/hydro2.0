"""Single-worker runtime driver for AE3-Lite v1."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone as _tz
from typing import Any, Callable, Optional

from ae3lite.application.use_cases.execute_task import TASK_EXECUTION_TIMEOUT_CANCEL_MSG
from ae3lite.infrastructure.metrics import ACTIVE_TASKS, TICK_DURATION, TICK_ERRORS, ZONE_LEASE_LOST, ZONE_LEASE_RELEASE_FAILED
from common.infra_alerts import send_infra_alert


class Ae3RuntimeWorker:
    """Drains pending AE3 tasks sequentially and performs startup recovery."""

    def __init__(
        self,
        *,
        owner: str,
        claim_next_task_use_case: Any,
        idle_poll_interval_sec: float,
        execute_task_use_case: Any,
        startup_recovery_use_case: Any,
        zone_lease_repository: Any,
        spawn_background_task_fn: Callable[..., Any],
        mark_intent_running_fn: Callable[..., Any],
        mark_intent_terminal_fn: Callable[..., Any],
        now_fn: Callable[[], datetime],
        logger: Any,
        lease_ttl_sec: int = 300,
        max_task_execution_sec: int = 900,
    ) -> None:
        self._owner = str(owner or "ae3-runtime").strip() or "ae3-runtime"
        self._claim_next_task_use_case = claim_next_task_use_case
        self._idle_poll_interval_sec = max(0.1, float(idle_poll_interval_sec))
        self._execute_task_use_case = execute_task_use_case
        self._startup_recovery_use_case = startup_recovery_use_case
        self._zone_lease_repository = zone_lease_repository
        self._spawn_background_task_fn = spawn_background_task_fn
        self._mark_intent_running_fn = mark_intent_running_fn
        self._mark_intent_terminal_fn = mark_intent_terminal_fn
        self._now_fn = now_fn
        self._logger = logger
        self._lease_ttl_sec = max(30, int(lease_ttl_sec))
        self._max_task_execution_sec = max_task_execution_sec
        self._drain_task: Optional[Any] = None
        self._pending_kicks = 0
        self._respawn_guard_task: Optional[Any] = None
        self._wake_task: Optional[Any] = None
        self._last_drain_exit_ok = True
        self._last_drain_exit_reason = "idle"

    def kick(self) -> Any:
        self._pending_kicks += 1
        self._cancel_wake_task()
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
            )
        return result

    async def _drain_pending_tasks(self) -> None:
        self._log_debug("AE3 runtime drain started")
        drain_ok = False
        drain_reason = "worker_unexpected_exit"
        try:
            while True:
                claimed = await self._claim_next_task_use_case.run(owner=self._owner, now=self._now_fn())
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
                intent_id = int(task.intent_id or 0)
                if intent_id > 0:
                    await self._safe_mark_intent_running(intent_id=intent_id)

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
                        try:
                            final_task = await asyncio.wait_for(
                                asyncio.shield(execution_task),
                                timeout=float(self._max_task_execution_sec),
                            )
                        except asyncio.TimeoutError:
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
                            execution_task.cancel()
                            raise
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
                        self._logger.warning(
                            "AE3 runtime failed to release zone lease: zone_id=%s owner=%s task_id=%s",
                            task.zone_id,
                            self._owner,
                            task.id,
                        )
                        ZONE_LEASE_RELEASE_FAILED.labels(zone_id=str(task.zone_id)).inc()
                        try:
                            await send_infra_alert(
                                code="ae3_zone_lease_release_failed",
                                alert_type="AE3 Zone Lease Release Failed",
                                severity="error",
                                zone_id=int(task.zone_id),
                                service="automation-engine",
                                component="worker:lease",
                                details={
                                    "task_id": int(task.id),
                                    "owner": self._owner,
                                    "topology": str(getattr(task, "topology", "")),
                                    "message": "Zone lease could not be released after task completion — zone may be locked.",
                                },
                            )
                        except Exception:
                            self._logger.warning(
                                "AE3 failed to send lease_release_failed alert zone_id=%s",
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
                                error_message=f"Task execution exceeded {self._max_task_execution_sec}s timeout",
                            )
                    self._log_debug("AE3 runtime continuing drain after timed out task: task_id=%s", task.id)
                    continue

                if intent_id > 0 and final_task is not None and not final_task.is_active:
                    await self._safe_mark_intent_terminal(task=final_task, intent_id=intent_id)
        except asyncio.CancelledError:
            drain_reason = "worker_cancelled"
            raise
        except Exception as exc:
            drain_reason = f"worker_crashed:{type(exc).__name__}"
            raise
        finally:
            self._last_drain_exit_ok = drain_ok
            self._last_drain_exit_reason = drain_reason

    async def _lease_heartbeat(self, *, zone_id: int, lease_lost_event: asyncio.Event) -> None:
        """Periodically extend zone lease while task is executing (heartbeat at 1/3 of TTL)."""
        interval = max(10.0, self._lease_ttl_sec / 3.0)
        while True:
            await asyncio.sleep(interval)
            try:
                extended = await self._zone_lease_repository.extend(
                    zone_id=zone_id,
                    owner=self._owner,
                    now=self._now_fn(),
                    lease_ttl_sec=self._lease_ttl_sec,
                )
                if extended:
                    self._log_debug("AE3 lease heartbeat extended: zone_id=%s owner=%s", zone_id, self._owner)
                else:
                    self._logger.error(
                        "AE3 lease heartbeat: lease lost for zone_id=%s owner=%s — task continues without lease",
                        zone_id,
                        self._owner,
                    )
                    ZONE_LEASE_LOST.labels(zone_id=str(zone_id)).inc()
                    lease_lost_event.set()
                    try:
                        await send_infra_alert(
                            code="ae3_zone_lease_lost",
                            alert_type="AE3 Zone Lease Lost",
                            severity="critical",
                            zone_id=int(zone_id),
                            service="automation-engine",
                            component="worker:heartbeat",
                            details={
                                "owner": self._owner,
                                "message": "Zone lease heartbeat failed to extend — zone may be hijacked or frozen.",
                            },
                        )
                    except Exception:
                        self._logger.warning(
                            "AE3 failed to send lease_lost alert zone_id=%s",
                            zone_id,
                            exc_info=True,
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

    async def _safe_mark_intent_running(self, *, intent_id: int) -> None:
        try:
            await self._mark_intent_running_fn(intent_id=intent_id, now=self._now_fn())
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.warning("AE3 runtime failed to mark intent running: intent_id=%s", intent_id, exc_info=True)

    async def _safe_mark_intent_terminal(self, *, task: Any, intent_id: int) -> None:
        await self._safe_mark_intent_terminal_result(
            intent_id=intent_id,
            now=self._now_fn(),
            success=str(task.status).strip().lower() == "completed",
            error_code=task.error_code,
            error_message=task.error_message,
        )

    async def _safe_mark_intent_terminal_result(
        self,
        *,
        intent_id: int,
        now: datetime,
        success: bool,
        error_code: Any,
        error_message: Any,
    ) -> None:
        try:
            await self._mark_intent_terminal_fn(
                intent_id=intent_id,
                now=now,
                success=success,
                error_code=error_code,
                error_message=error_message,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.warning("AE3 runtime failed to mark intent terminal: intent_id=%s", intent_id, exc_info=True)

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
        self._log_debug("AE3 runtime spawning drain task")
        task = self._spawn_background_task_fn(
            self._drain_pending_tasks(),
            task_name="ae3lite_runtime_worker",
        )
        self._drain_task = task
        self._respawn_guard_task = None
        return task

    async def _schedule_wake_for_next_pending(self) -> bool:
        getter = getattr(self._claim_next_task_use_case, "next_pending_due_at", None)
        if not callable(getter):
            return False
        next_due_at = await getter()
        if next_due_at is None:
            return False

        now = self._now_fn()
        # Normalize both to UTC-aware to avoid wrong comparisons when one is
        # tz-aware and the other is naive (replace(tzinfo=None) strips info
        # without converting, causing silent clock errors).
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
        if self._wake_task is not None and not self._wake_task.done():
            return

        async def _wake_after_delay() -> None:
            try:
                await asyncio.sleep(max(0.0, delay))
                if self._drain_task is not None and not self._drain_task.done():
                    self._log_debug(
                        "AE3 runtime wake skipped: owner=%s active_drain_task=%s",
                        self._owner,
                        self._drain_task,
                    )
                    return
                self._log_debug(
                    "AE3 runtime wake firing: owner=%s delay_sec=%.3f",
                    self._owner,
                    delay,
                )
                self._spawn_drain_task()
            finally:
                if self._wake_task is wake_task:
                    self._wake_task = None

        wake_task = self._spawn_background_task_fn(
            _wake_after_delay(),
            task_name="ae3lite_runtime_wake",
        )
        self._wake_task = wake_task

    def _cancel_wake_task(self) -> None:
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
            if self._pending_kicks <= 0:
                return
            self._log_debug("AE3 runtime respawning drain task after deferred kick")
            self._spawn_drain_task()

        add_done_callback = getattr(task, "add_done_callback", None)
        if callable(add_done_callback):
            add_done_callback(_on_done)

    def drain_health(self) -> tuple[bool, str]:
        """Return (ok, reason) for readiness probe."""
        drain = self._drain_task
        if drain is None:
            return self._last_drain_exit_ok, self._last_drain_exit_reason
        if not drain.done():
            return True, self._owner
        if drain.cancelled():
            return False, "worker_cancelled"
        try:
            exc = drain.exception()
        except Exception:
            return False, "worker_exception_unknown"
        if exc is not None:
            return False, f"worker_crashed:{type(exc).__name__}"
        return self._last_drain_exit_ok, self._last_drain_exit_reason

    def _log_debug(self, message: str, *args: Any) -> None:
        debug = getattr(self._logger, "debug", None)
        if callable(debug):
            debug(message, *args)
