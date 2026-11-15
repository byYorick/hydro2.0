"""Ae3RuntimeWorker reconcile policy: explicit collaborators and invocation context."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ae3lite.runtime.worker_runtime_state import WorkerRuntimeState


@dataclass(frozen=True)
class WorkerRuntimeReconcilePolicyPorts:
    active_task_age_metrics_interval_sec: Callable[[], Any]
    arm_respawn_on_done: Callable[..., Any]
    log_debug: Callable[..., Any]
    logger: Callable[[], Any]
    now_fn: Callable[..., Any]
    orphan_intent_reconcile_interval_sec: Callable[[], Any]
    orphan_intent_reconcile_use_case: Callable[[], Any]
    owner: Callable[[], Any]
    reconcile_loop: Callable[[], Any]
    safe_mark_intent_terminal_result: Callable[..., Awaitable[Any]]
    spawn_background_task_fn: Callable[..., Any]
    spawn_drain_task: Callable[..., Any]
    stale_task_reconcile_interval_sec: Callable[[], Any]
    stale_task_reconcile_use_case: Callable[[], Any]
    startup_recovery_use_case: Callable[[], Any]
    sync_orphan_intent_terminal: Callable[..., Awaitable[Any]]
    task_repository: Callable[[], Any]
    waiting_command_reconcile_use_case: Callable[[], Any]


class WorkerRuntimeReconcilePolicy:
    def __init__(self, ports: WorkerRuntimeReconcilePolicyPorts, state: WorkerRuntimeState) -> None:
        self._ports = ports
        self._state = state

    def ensure_waiting_command_reconcile_loop(self) -> None:
        if self._state.shutting_down:
            return
        if (
            self._ports.waiting_command_reconcile_use_case() is None
            and self._ports.stale_task_reconcile_use_case() is None
            and self._ports.orphan_intent_reconcile_use_case() is None
            and not callable(getattr(self._ports.startup_recovery_use_case(), "reconcile_terminal_commands", None))
        ):
            return
        if self._state.reconcile_loop_task is not None and not self._state.reconcile_loop_task.done():
            return
        self._state.reconcile_loop_task = self._ports.spawn_background_task_fn(
            self.waiting_command_reconcile_loop(),
            task_name="ae3lite_waiting_command_reconcile",
        )

    async def waiting_command_reconcile_loop(self) -> None:
        await self._ports.reconcile_loop().run()

    async def maybe_run_terminal_command_reconcile_once(self) -> None:
        repair = getattr(self._ports.startup_recovery_use_case(), "reconcile_terminal_commands", None)
        if not callable(repair):
            return
        now_mono = time.monotonic()
        last = self._state.last_terminal_command_reconcile_monotonic
        if last is not None and now_mono - last < self._ports.stale_task_reconcile_interval_sec():
            return
        await repair(now=self._ports.now_fn())
        self._state.last_terminal_command_reconcile_monotonic = now_mono

    async def run_waiting_command_reconcile_once(self) -> None:
        if self._ports.waiting_command_reconcile_use_case() is None:
            return
        result = await self._ports.waiting_command_reconcile_use_case().run(
            now=self._ports.now_fn(),
            worker_owner=self._ports.owner(),
            inflight_task_ids=frozenset(
                int(getattr(task, "id", 0) or 0)
                for task in self._state.inflight_automation_tasks.values()
                if int(getattr(task, "id", 0) or 0) > 0
            ),
        )
        terminal_outcomes = getattr(result, "terminal_outcomes", ()) or ()
        for outcome in terminal_outcomes:
            intent_id = int(getattr(outcome, "intent_id", 0) or 0)
            if intent_id <= 0:
                continue
            await self._ports.safe_mark_intent_terminal_result(
                intent_id=intent_id,
                now=self._ports.now_fn(),
                success=bool(getattr(outcome, "success", False)),
                error_code=getattr(outcome, "error_code", None),
                error_message=getattr(outcome, "error_message", None),
                task_id=int(getattr(outcome, "task_id", 0) or 0) or None,
            )
        if bool(getattr(result, "kick_needed", False)) and not self._state.shutting_down:
            self._state.pending_kicks += 1
            drain = self._state.drain_task
            if drain is None or drain.done():
                self._ports.spawn_drain_task()
            else:
                self._ports.arm_respawn_on_done(drain)

    async def maybe_run_stale_task_reconcile_once(self) -> None:
        if self._ports.stale_task_reconcile_use_case() is None:
            return
        now_mono = time.monotonic()
        if self._state.last_stale_task_reconcile_monotonic is not None:
            elapsed = now_mono - self._state.last_stale_task_reconcile_monotonic
            if elapsed < self._ports.stale_task_reconcile_interval_sec():
                return
        self._state.last_stale_task_reconcile_monotonic = now_mono
        result = await self._ports.stale_task_reconcile_use_case().run(
            now=self._ports.now_fn(),
            owner=self._ports.owner(),
            inflight_task_ids=frozenset(
                int(getattr(task, "id", 0) or 0)
                for task in self._state.inflight_automation_tasks.values()
                if int(getattr(task, "id", 0) or 0) > 0
            ),
        )
        if bool(getattr(result, "kick_needed", False)) and not self._state.shutting_down:
            self._state.pending_kicks += 1
            drain = self._state.drain_task
            if drain is None or drain.done():
                self._ports.spawn_drain_task()
            else:
                self._ports.arm_respawn_on_done(drain)

    async def maybe_run_orphan_intent_reconcile_once(self) -> None:
        if self._ports.orphan_intent_reconcile_use_case() is None:
            return
        now_mono = time.monotonic()
        if self._state.last_orphan_intent_reconcile_monotonic is not None:
            elapsed = now_mono - self._state.last_orphan_intent_reconcile_monotonic
            if elapsed < self._ports.orphan_intent_reconcile_interval_sec():
                return
        self._state.last_orphan_intent_reconcile_monotonic = now_mono
        result = await self._ports.orphan_intent_reconcile_use_case().run(
            now=self._ports.now_fn(),
            sync_terminal_fn=self._ports.sync_orphan_intent_terminal,
        )
        reconciled = int(getattr(result, "reconciled_intents", 0) or 0)
        if reconciled > 0:
            self._ports.log_debug(
                "AE3 orphan intent reconcile: reconciled=%s scanned=%s failed=%s owner=%s",
                reconciled,
                getattr(result, "scanned_intents", 0),
                getattr(result, "failed_intents", 0),
                self._ports.owner(),
            )

    async def maybe_refresh_active_task_age_metrics_once(self) -> None:
        if self._ports.task_repository() is None:
            return
        refresh = getattr(self._ports.task_repository(), "refresh_active_task_age_metrics", None)
        if not callable(refresh):
            return
        now_mono = time.monotonic()
        if self._state.last_active_task_age_metrics_monotonic is not None:
            elapsed = now_mono - self._state.last_active_task_age_metrics_monotonic
            if elapsed < self._ports.active_task_age_metrics_interval_sec():
                return
        self._state.last_active_task_age_metrics_monotonic = now_mono
        try:
            await refresh(now=self._ports.now_fn())
        except Exception:
            self._ports.logger().warning(
                "AE3 reconcile: failed to refresh active task age metrics: owner=%s",
                self._ports.owner(),
                exc_info=True,
            )
