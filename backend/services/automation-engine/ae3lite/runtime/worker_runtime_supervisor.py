"""Ae3RuntimeWorker supervisor: explicit collaborators and invocation context."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import timezone as _tz
from typing import Any, Awaitable, Callable, Optional

from ae3lite.domain.errors import TaskClaimRollbackError
from ae3lite.infrastructure.metrics import (
    CLAIM_ROLLBACK_FAILED,
    DRAIN_CRASHES,
)
from ae3lite.runtime.worker_runtime_state import WorkerRuntimeState


@dataclass(frozen=True)
class WorkerRuntimeSupervisorPorts:
    claim_next_task_use_case: Callable[[], Any]
    drain_pending_tasks: Callable[..., Awaitable[Any]]
    execute_claimed_task_safe: Callable[..., Awaitable[Any]]
    finalize_inflight_on_shutdown: Callable[..., Awaitable[Any]]
    idle_poll_interval_sec: Callable[[], Any]
    log_debug: Callable[..., Any]
    logger: Callable[[], Any]
    max_parallel_tasks: Callable[[], Any]
    now_fn: Callable[..., Any]
    owner: Callable[[], Any]
    process_run_id: Callable[[], Any]
    spawn_background_task_fn: Callable[..., Any]


class WorkerRuntimeSupervisor:
    def __init__(self, ports: WorkerRuntimeSupervisorPorts, state: WorkerRuntimeState) -> None:
        self._ports = ports
        self._state = state

    async def drain_pending_tasks(self) -> None:
        self._ports.log_debug("AE3 runtime drain started")
        drain_ok = False
        drain_reason = "worker_unexpected_exit"
        inflight: set[asyncio.Task] = set()
        try:
            while not self._state.shutting_down:
                while not self._state.shutting_down and len(inflight) < self._ports.max_parallel_tasks():
                    claimed = await self.claim_next_task_safe()
                    if claimed is None:
                        break

                    self._state.pending_kicks = 0
                    task, _lease = claimed
                    self._ports.log_debug("AE3 runtime claimed task: task_id=%s zone_id=%s", task.id, task.zone_id)
                    worker_task = asyncio.create_task(
                        self._ports.execute_claimed_task_safe(task=task),
                        name=f"ae3lite_claimed_task:{task.id}",
                    )
                    inflight.add(worker_task)
                    self._state.inflight_automation_tasks[worker_task] = task

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
                        self._state.inflight_automation_tasks.pop(done_task, None)
                        await self.await_inflight_task_result(done_task)
                    continue

                if self._state.shutting_down:
                    break

                claimed = await self.claim_next_task_safe()
                if claimed is None:
                    if self._state.pending_kicks > 0:
                        self._ports.log_debug("AE3 runtime drain retrying after deferred kick")
                        self._state.pending_kicks = 0
                        continue
                    if await self.schedule_wake_for_next_pending():
                        self._ports.log_debug("AE3 runtime drain sleeping until next due task")
                        drain_ok = True
                        drain_reason = "sleeping"
                        return
                    self._ports.log_debug("AE3 runtime drain idle: no pending tasks")
                    drain_ok = True
                    drain_reason = "idle"
                    return
                self._state.pending_kicks = 0
                task, _lease = claimed
                self._ports.log_debug("AE3 runtime claimed task: task_id=%s zone_id=%s", task.id, task.zone_id)
                worker_task = asyncio.create_task(
                    self._ports.execute_claimed_task_safe(task=task),
                    name=f"ae3lite_claimed_task:{task.id}",
                )
                inflight.add(worker_task)
                self._state.inflight_automation_tasks[worker_task] = task

            if inflight:
                await self._ports.finalize_inflight_on_shutdown(inflight)
            drain_ok = True
            drain_reason = "shutdown"
        except asyncio.CancelledError:
            if inflight:
                await self._ports.finalize_inflight_on_shutdown(inflight, cancel_pending=True)
            drain_reason = "worker_cancelled"
            raise
        except Exception as exc:
            if inflight:
                await self._ports.finalize_inflight_on_shutdown(inflight, cancel_pending=True)
            drain_reason = f"worker_crashed:{type(exc).__name__}"
            raise
        finally:
            self._state.last_drain_exit_ok = drain_ok
            self._state.last_drain_exit_reason = drain_reason

    async def claim_next_task_safe(self) -> tuple[Any, Any] | None:
        try:
            return await self._ports.claim_next_task_use_case().run(
                owner=self._ports.owner(),
                now=self._ports.now_fn(),
                process_run_id=self._ports.process_run_id(),
            )
        except TaskClaimRollbackError as exc:
            CLAIM_ROLLBACK_FAILED.inc()
            self._ports.logger().error(
                "AE3 claim rollback failed after zone lease conflict; "
                "task escalated via fail_for_recovery when possible: owner=%s error=%s",
                self._ports.owner(),
                exc,
            )
            return None

    async def await_inflight_task_result(self, done_task: asyncio.Task) -> None:
        try:
            await done_task
        except asyncio.CancelledError:
            raise
        except Exception:
            # Per-task isolation: _execute_claimed_task_safe не пробрасывает ошибки выполнения.
            self._ports.log_debug(
                "AE3 runtime ignored inflight task exception after safe wrapper: task_name=%s",
                done_task.get_name(),
            )

    async def drain_supervisor(self) -> None:
        backoff_sec = 1.0
        while not self._state.shutting_down:
            try:
                await self._ports.drain_pending_tasks()
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                DRAIN_CRASHES.inc()
                self._ports.logger().error(
                    "AE3 drain supervisor caught crash: owner=%s backoff_sec=%.1f",
                    self._ports.owner(),
                    backoff_sec,
                    exc_info=True,
                )
                if self._state.shutting_down:
                    break
                await asyncio.sleep(backoff_sec)
                backoff_sec = min(backoff_sec * 2.0, 60.0)

    def current_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def task_loop(self, task: Any) -> Optional[asyncio.AbstractEventLoop]:
        get_loop = getattr(task, "get_loop", None)
        if not callable(get_loop):
            return None
        try:
            return get_loop()
        except (RuntimeError, AttributeError):
            return None

    def spawn_drain_task(self) -> Any:
        if self._state.shutting_down:
            self._ports.log_debug("AE3 runtime drain spawn skipped: worker shutting down")
            return self._state.drain_task
        self._ports.log_debug("AE3 runtime spawning drain task")
        task = self._ports.spawn_background_task_fn(
            self.drain_supervisor(),
            task_name="ae3lite_runtime_worker",
        )
        self._state.drain_task = task
        self._state.respawn_guard_task = None
        return task

    async def schedule_wake_for_next_pending(self) -> bool:
        if self._state.shutting_down:
            return False
        getter = getattr(self._ports.claim_next_task_use_case(), "next_pending_due_at", None)
        if not callable(getter):
            return False
        next_due_at = await getter()
        if next_due_at is None:
            return False

        now = self._ports.now_fn()
        # Нормализовать обе метки к UTC-aware, чтобы избежать неверных сравнений,
        # когда одна дата tz-aware, а другая naive. Простое replace(tzinfo=None)
        # убирает tzinfo без конвертации и может тихо исказить время.
        next_due_utc = (
            next_due_at.astimezone(_tz.utc) if next_due_at.tzinfo is not None else next_due_at.replace(tzinfo=_tz.utc)
        )
        now_utc = now.astimezone(_tz.utc) if now.tzinfo is not None else now.replace(tzinfo=_tz.utc)

        delay = (next_due_utc - now_utc).total_seconds()
        if delay <= 0:
            delay = self._ports.idle_poll_interval_sec()
        self._ports.log_debug(
            "AE3 runtime scheduled wake: owner=%s due_in_sec=%.3f next_due_at=%s",
            self._ports.owner(),
            delay,
            next_due_at,
        )
        self.arm_wake_task(delay=delay)
        return True

    def arm_wake_task(self, *, delay: float) -> None:
        wake_handle = self._state.wake_handle
        if wake_handle is not None and not wake_handle.cancelled():
            return
        if self._state.wake_task is not None and not self._state.wake_task.done():
            return

        loop = self.current_loop()
        if loop is None:
            return

        def _wake_callback() -> None:
            if self._state.wake_handle is not wake_handle_ref:
                return
            self._state.wake_handle = None
            if self._state.shutting_down:
                self._ports.log_debug("AE3 runtime wake skipped: worker shutting down")
                return
            if self._state.drain_task is not None and not self._state.drain_task.done():
                self._ports.log_debug(
                    "AE3 runtime wake skipped: owner=%s active_drain_task=%s",
                    self._ports.owner(),
                    self._state.drain_task,
                )
                self._state.pending_kicks += 1
                self.arm_respawn_on_done(self._state.drain_task)
                return
            self._ports.log_debug(
                "AE3 runtime wake firing: owner=%s delay_sec=%.3f",
                self._ports.owner(),
                delay,
            )
            self.spawn_drain_task()

        wake_handle_ref = loop.call_later(max(0.0, delay), _wake_callback)
        self._state.wake_handle = wake_handle_ref
        self._state.wake_task = None

    def cancel_wake_task(self) -> None:
        wake_handle = self._state.wake_handle
        if wake_handle is not None:
            wake_handle.cancel()
            self._state.wake_handle = None
        wake_task = self._state.wake_task
        if wake_task is None or wake_task.done():
            self._state.wake_task = None
            return
        cancel = getattr(wake_task, "cancel", None)
        if callable(cancel):
            cancel()
        self._state.wake_task = None

    def arm_respawn_on_done(self, task: Any) -> None:
        if self._state.respawn_guard_task is task:
            return
        self._state.respawn_guard_task = task

        def _on_done(done_task: Any) -> None:
            if self._state.respawn_guard_task is not done_task:
                return
            self._state.respawn_guard_task = None
            current_task = self._state.drain_task
            if current_task is not done_task and current_task is not None and not current_task.done():
                return
            if self._state.pending_kicks <= 0 or self._state.shutting_down:
                return
            self._ports.log_debug("AE3 runtime respawning drain task after deferred kick")
            self.spawn_drain_task()

        add_done_callback = getattr(task, "add_done_callback", None)
        if callable(add_done_callback):
            add_done_callback(_on_done)

    async def drain_health(self) -> tuple[bool, str]:
        """Возвращает `(ok, reason)` для readiness-probe."""
        drain = self._state.drain_task
        if drain is not None and not drain.done():
            return True, self._ports.owner()

        if drain is None or drain.done():
            if await self.has_due_pending_cached():
                return False, "drain_dead_with_pending"

        if drain is None:
            return self._state.last_drain_exit_ok, self._state.last_drain_exit_reason
        if drain.cancelled():
            return False, "worker_cancelled"
        try:
            exc = drain.exception()
        except Exception:
            return False, "worker_exception_unknown"
        if exc is not None:
            return False, f"worker_crashed:{type(exc).__name__}"
        return self._state.last_drain_exit_ok, self._state.last_drain_exit_reason

    async def has_due_pending_cached(self) -> bool:
        now_mono = time.monotonic()
        cached = self._state.pending_health_cache
        if cached is not None and (now_mono - cached[0]) < 5.0:
            return cached[1]

        has_due_pending = await self.has_due_pending()
        self._state.pending_health_cache = (now_mono, has_due_pending)
        return has_due_pending

    async def has_due_pending(self) -> bool:
        getter = getattr(self._ports.claim_next_task_use_case(), "next_pending_due_at", None)
        if not callable(getter):
            return False
        next_due_at = await getter()
        if next_due_at is None:
            return False

        now = self._ports.now_fn()
        next_due_utc = (
            next_due_at.astimezone(_tz.utc) if next_due_at.tzinfo is not None else next_due_at.replace(tzinfo=_tz.utc)
        )
        now_utc = now.astimezone(_tz.utc) if now.tzinfo is not None else now.replace(tzinfo=_tz.utc)
        return next_due_utc <= now_utc
