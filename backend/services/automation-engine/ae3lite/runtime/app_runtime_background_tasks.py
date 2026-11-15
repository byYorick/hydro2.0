"""app runtime background tasks: explicit dependencies and invocation data."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ae3lite.runtime.app_runtime_records import BackgroundTaskLimitError


@dataclass(frozen=True)
class AppRuntimeBackgroundTasksPorts:
    background_tasks_size_limit: Callable[..., Any]
    close_coro: Callable[..., Any]
    logger: Callable[..., Any]
    send_infra_exception_alert: Callable[..., Any]


class AppRuntimeBackgroundTasks:
    def __init__(self, ports: AppRuntimeBackgroundTasksPorts) -> None:
        self._ports = ports

    async def drain_background_tasks(self, background_tasks: set[asyncio.Task], timeout_sec: float) -> None:
        pending = [task for task in background_tasks if not task.done()]
        if not pending:
            return

        for task in pending:
            task.cancel()

        try:
            await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=timeout_sec)
        except asyncio.TimeoutError:
            self._ports.logger().warning(
                "Превышено время ожидания завершения фоновых задач AE3: pending=%s", len(pending)
            )
        finally:
            background_tasks.difference_update(pending)

    def close_coro(self, coro: Any) -> None:
        close = getattr(coro, "close", None)
        if callable(close):
            close()

    def spawn_background_task(
        self,
        coro: Any,
        *,
        task_name: str,
        background_tasks: set[asyncio.Task],
        zone_id: Optional[int],
        task_id: Optional[str],
        task_type: Optional[str],
    ) -> asyncio.Task:
        completed_tasks = {task for task in background_tasks if task.done()}
        if completed_tasks:
            background_tasks.difference_update(completed_tasks)
        active_count = len(background_tasks)
        if active_count >= self._ports.background_tasks_size_limit():
            self._ports.logger().error(
                "AE3 background_tasks limit exceeded: limit=%s active=%s task_name=%s; rejecting spawn to fail closed",
                self._ports.background_tasks_size_limit(),
                active_count,
                task_name,
            )
            self._ports.close_coro(coro)
            raise BackgroundTaskLimitError(
                f"ae3_background_task_limit_exceeded: task_name={task_name} active={active_count} limit={self._ports.background_tasks_size_limit()}"
            )
        task = asyncio.create_task(coro, name=str(task_name))
        background_tasks.add(task)

        def _on_done(done_task: asyncio.Task) -> None:
            background_tasks.discard(done_task)
            if done_task.cancelled():
                return
            try:
                exc = done_task.exception()
            except Exception as callback_exc:
                self._ports.logger().error(
                    "Не удалось проверить результат фоновой задачи AE3: task_name=%s error=%s",
                    task_name,
                    callback_exc,
                    exc_info=True,
                )
                return
            if exc is None:
                return

            self._ports.logger().error(
                "AE3 background task crashed: task_name=%s zone_id=%s task_id=%s task_type=%s error=%s",
                task_name,
                zone_id,
                task_id,
                task_type,
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )

            async def _send_alert() -> None:
                await self._ports.send_infra_exception_alert(
                    error=exc,
                    code="ae3_background_task_crashed",
                    alert_type="AE3 Background Task Crashed",
                    severity="error",
                    zone_id=zone_id,
                    service="automation-engine",
                    component=f"background:{task_name}",
                    details={
                        "task_id": task_id,
                        "task_type": task_type,
                        "zone_id": zone_id,
                    },
                )

            try:
                asyncio.create_task(_send_alert())
            except Exception:
                self._ports.logger().warning(
                    "Не удалось запланировать alert для аварийно завершившейся фоновой задачи AE3: task_name=%s",
                    task_name,
                    exc_info=True,
                )

        task.add_done_callback(_on_done)
        return task
