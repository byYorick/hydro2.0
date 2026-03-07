"""Single-worker runtime driver for AE3-Lite v1."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable, Optional


class Ae3RuntimeWorker:
    """Drains pending AE3 tasks sequentially and performs startup recovery."""

    def __init__(
        self,
        *,
        owner: str,
        claim_next_task_use_case: Any,
        execute_task_use_case: Any,
        startup_recovery_use_case: Any,
        zone_lease_repository: Any,
        spawn_background_task_fn: Callable[..., Any],
        mark_intent_running_fn: Callable[..., Any],
        mark_intent_terminal_fn: Callable[..., Any],
        now_fn: Callable[[], datetime],
        logger: Any,
    ) -> None:
        self._owner = str(owner or "ae3-runtime").strip() or "ae3-runtime"
        self._claim_next_task_use_case = claim_next_task_use_case
        self._execute_task_use_case = execute_task_use_case
        self._startup_recovery_use_case = startup_recovery_use_case
        self._zone_lease_repository = zone_lease_repository
        self._spawn_background_task_fn = spawn_background_task_fn
        self._mark_intent_running_fn = mark_intent_running_fn
        self._mark_intent_terminal_fn = mark_intent_terminal_fn
        self._now_fn = now_fn
        self._logger = logger
        self._drain_task: Optional[Any] = None
        self._pending_kicks = 0
        self._respawn_guard_task: Optional[Any] = None

    def kick(self) -> Any:
        self._pending_kicks += 1
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
        while True:
            claimed = await self._claim_next_task_use_case.run(owner=self._owner, now=self._now_fn())
            if claimed is None:
                if self._pending_kicks > 0:
                    self._log_debug("AE3 runtime drain retrying after deferred kick")
                    self._pending_kicks = 0
                    continue
                self._log_debug("AE3 runtime drain idle: no pending tasks")
                return

            self._pending_kicks = 0
            task, _lease = claimed
            self._log_debug("AE3 runtime claimed task: task_id=%s zone_id=%s", task.id, task.zone_id)
            intent_id = int(task.intent_id or 0)
            if intent_id > 0:
                await self._safe_mark_intent_running(intent_id=intent_id)

            final_task = task
            try:
                final_task = await self._execute_task_use_case.run(task=task, now=self._now_fn())
            finally:
                released = await self._zone_lease_repository.release(zone_id=task.zone_id, owner=self._owner)
                if not released:
                    self._logger.warning(
                        "AE3 runtime failed to release zone lease: zone_id=%s owner=%s task_id=%s",
                        task.zone_id,
                        self._owner,
                        task.id,
                    )

            if intent_id > 0 and final_task is not None and not final_task.is_active:
                await self._safe_mark_intent_terminal(task=final_task, intent_id=intent_id)

    async def _safe_mark_intent_running(self, *, intent_id: int) -> None:
        try:
            await self._mark_intent_running_fn(intent_id=intent_id, now=self._now_fn())
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
        except Exception:
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

    def _log_debug(self, message: str, *args: Any) -> None:
        debug = getattr(self._logger, "debug", None)
        if callable(debug):
            debug(message, *args)
