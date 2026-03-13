from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress

import pytest

os.environ.setdefault("HISTORY_LOGGER_API_TOKEN", "test-token")

import ae3lite.runtime.app as runtime_app_module


@pytest.mark.asyncio
async def test_spawn_background_task_fails_closed_when_limit_is_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocker = asyncio.Event()
    existing_task = asyncio.create_task(blocker.wait(), name="existing-background-task")
    background_tasks = {existing_task}

    monkeypatch.setattr(runtime_app_module, "_BACKGROUND_TASKS_SIZE_LIMIT", 1)

    async def sample_coro() -> None:
        await asyncio.sleep(0)

    try:
        with pytest.raises(runtime_app_module.BackgroundTaskLimitError, match="ae3_background_task_limit_exceeded"):
            runtime_app_module._spawn_background_task(
                sample_coro(),
                task_name="overflow-task",
                background_tasks=background_tasks,
            )
        assert background_tasks == {existing_task}
    finally:
        existing_task.cancel()
        with suppress(asyncio.CancelledError):
            await existing_task


@pytest.mark.asyncio
async def test_intent_listener_callback_kicks_worker() -> None:
    kicks: list[str] = []

    class _Worker:
        def kick(self) -> None:
            kicks.append("kick")

    callback = runtime_app_module._build_intent_listener_callback(
        worker=_Worker(),
        logger=logging.getLogger("ae3-runtime-test"),
    )

    await callback({"intent_id": 11, "zone_id": 22, "status": "completed"})

    assert kicks == ["kick"]
