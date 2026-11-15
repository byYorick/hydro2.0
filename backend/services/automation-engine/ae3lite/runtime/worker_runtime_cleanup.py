"""Ae3RuntimeWorker cleanup: explicit collaborators and invocation context."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ae3lite.runtime.worker_runtime_state import WorkerRuntimeState


@dataclass(frozen=True)
class WorkerRuntimeCleanupPorts:
    cancel_wake_task: Callable[..., Any]
    claim_generation: Callable[..., Any]
    command_repository: Callable[[], Any]
    log_debug: Callable[..., Any]
    logger: Callable[[], Any]
    now_fn: Callable[..., Any]
    owner: Callable[[], Any]
    reconcile_wake: Callable[[], Any]
    safe_mark_intent_terminal: Callable[..., Awaitable[Any]]
    shutdown_grace_sec: Callable[[], Any]
    task_repository: Callable[[], Any]
    zone_lease_repository: Callable[[], Any]


class WorkerRuntimeCleanup:
    def __init__(self, ports: WorkerRuntimeCleanupPorts, state: WorkerRuntimeState) -> None:
        self._ports = ports
        self._state = state

    async def shutdown(self, *, grace_sec: float | None = None) -> None:
        if self._state.shutting_down:
            return
        self._state.shutting_down = True
        effective_grace = max(0.0, float(grace_sec if grace_sec is not None else self._ports.shutdown_grace_sec()))
        self._state.active_shutdown_grace_sec = effective_grace
        self._state.pending_kicks = 0
        self._ports.log_debug("AE3 runtime shutdown started: grace_sec=%.3f", effective_grace)
        self._ports.cancel_wake_task()
        self._ports.reconcile_wake().set()
        reconcile_loop = self._state.reconcile_loop_task
        if reconcile_loop is not None and not reconcile_loop.done():
            reconcile_loop.cancel()
            with suppress(asyncio.CancelledError):
                await reconcile_loop
            self._state.reconcile_loop_task = None

        drain = self._state.drain_task
        if drain is not None and not drain.done():
            drain_timeout = effective_grace + 5.0
            try:
                await asyncio.wait_for(drain, timeout=drain_timeout)
            except asyncio.TimeoutError:
                self._ports.logger().warning(
                    "AE3 runtime shutdown: drain did not finish within %.1fs, cancelling",
                    drain_timeout,
                )
                drain.cancel()
                with suppress(asyncio.CancelledError):
                    await drain

        released = await self.release_unpublished_claims_for_owner()
        if released > 0:
            self._ports.log_debug("AE3 runtime shutdown: released %s unpublished claims", released)

    async def finalize_inflight_on_shutdown(
        self,
        inflight: set[asyncio.Task],
        *,
        cancel_pending: bool = False,
    ) -> None:
        if not inflight:
            return
        grace = (
            self._state.active_shutdown_grace_sec
            if self._state.active_shutdown_grace_sec is not None
            else self._ports.shutdown_grace_sec()
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
            automation_task = self._state.inflight_automation_tasks.pop(worker_task, None)
            if automation_task is not None:
                await self.maybe_release_unpublished_claim(automation_task)
        inflight.clear()

    async def maybe_release_unpublished_claim(self, task: Any) -> bool:
        if self._ports.task_repository() is None:
            return False
        task_id = int(getattr(task, "id", 0) or 0)
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        if task_id <= 0:
            return False

        requeue_fn = getattr(self._ports.task_repository(), "requeue_unpublished_execution", None)
        if callable(requeue_fn):
            claim_generation = self._ports.claim_generation(task)
            requeued = await requeue_fn(
                task_id=task_id,
                owner=self._ports.owner(),
                now=self._ports.now_fn(),
                claim_generation=claim_generation,
            )
            if requeued is None:
                return False
            if zone_id > 0:
                await self._ports.zone_lease_repository().release(
                    zone_id=zone_id,
                    owner=self._ports.owner(),
                    claim_generation=claim_generation,
                )
            self._ports.log_debug(
                "AE3 runtime shutdown requeued unpublished execution: task_id=%s zone_id=%s",
                task_id,
                zone_id,
            )
            return True

        if self._ports.command_repository() is None:
            return False
        current = await self._ports.task_repository().get_by_id(task_id=task_id)
        if current is None or str(getattr(current, "status", "")) != "claimed":
            return False
        ae_cmd = await self._ports.command_repository().get_latest_for_task(task_id=task_id)
        if ae_cmd is not None:
            return False
        claim_generation = self._ports.claim_generation(current)
        released = await self._ports.task_repository().release_claim(
            task_id=task_id,
            owner=self._ports.owner(),
            now=self._ports.now_fn(),
            claim_generation=claim_generation,
        )
        if released and zone_id > 0:
            await self._ports.zone_lease_repository().release(
                zone_id=zone_id,
                owner=self._ports.owner(),
                claim_generation=claim_generation,
            )
        if released:
            self._ports.log_debug(
                "AE3 runtime shutdown released unpublished claim: task_id=%s zone_id=%s",
                task_id,
                getattr(current, "zone_id", None),
            )
        return bool(released)

    async def release_unpublished_claims_for_owner(self) -> int:
        if self._ports.task_repository() is None:
            return 0
        list_unpublished = getattr(self._ports.task_repository(), "list_unpublished_execution_by_owner", None)
        if callable(list_unpublished):
            claimed_tasks = await list_unpublished(owner=self._ports.owner())
        else:
            list_claimed = getattr(self._ports.task_repository(), "list_claimed_by_owner", None)
            if not callable(list_claimed):
                return 0
            claimed_tasks = await list_claimed(owner=self._ports.owner())
        released = 0
        for task in claimed_tasks:
            if await self.maybe_release_unpublished_claim(task):
                released += 1
        return released

    async def abort_task_after_intent_sync_failure(self, *, task: Any, intent_id: int) -> None:
        error_code = "ae3_intent_sync_failed"
        error_message = f"Не удалось синхронизировать intent {intent_id} в running после исчерпания retry"
        task_id = int(getattr(task, "id", 0) or 0)
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        failed_task = None
        if task_id > 0 and self._ports.task_repository() is not None:
            fail_for_recovery = getattr(self._ports.task_repository(), "fail_for_recovery", None)
            if callable(fail_for_recovery):
                try:
                    failed_task = await fail_for_recovery(
                        task_id=task_id,
                        error_code=error_code,
                        error_message=error_message,
                        now=self._ports.now_fn(),
                        owner=str(getattr(task, "claimed_by", None) or self._ports.owner()),
                        claim_generation=self._ports.claim_generation(task),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._ports.logger().warning(
                        "AE3 runtime не смог перевести задачу в failed после intent sync failure: "
                        "zone_id=%s task_id=%s owner=%s",
                        zone_id,
                        task_id,
                        self._ports.owner(),
                        exc_info=True,
                    )
        if failed_task is not None and not getattr(failed_task, "is_active", True):
            await self._ports.safe_mark_intent_terminal(task=failed_task, intent_id=intent_id)
        else:
            self._ports.logger().warning(
                "AE3 runtime left intent non-terminal after intent sync failure CAS miss: intent_id=%s task_id=%s",
                intent_id,
                task_id,
            )
        if zone_id > 0:
            try:
                released = await self._ports.zone_lease_repository().release(
                    zone_id=zone_id,
                    owner=self._ports.owner(),
                    claim_generation=self._ports.claim_generation(task),
                )
                if not released:
                    await asyncio.sleep(0.05)
                    await self._ports.zone_lease_repository().release(
                        zone_id=zone_id,
                        owner=self._ports.owner(),
                        claim_generation=self._ports.claim_generation(task),
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                self._ports.logger().warning(
                    "AE3 runtime не смог освободить lease после intent sync failure: zone_id=%s task_id=%s owner=%s",
                    zone_id,
                    task_id,
                    self._ports.owner(),
                    exc_info=True,
                )
