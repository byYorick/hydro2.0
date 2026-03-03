from __future__ import annotations

import asyncio

import pytest

from infrastructure.zone_execution_lock import zone_execution_context


@pytest.mark.asyncio
async def test_zone_execution_context_serializes_same_zone() -> None:
    events: list[str] = []
    first_entered = asyncio.Event()

    async def _first() -> None:
        async with zone_execution_context(zone_id=101, task_type="diagnostics", workflow="startup"):
            events.append("first_enter")
            first_entered.set()
            await asyncio.sleep(0.05)
            events.append("first_exit")

    async def _second() -> None:
        await first_entered.wait()
        async with zone_execution_context(zone_id=101, task_type="diagnostics", workflow="startup"):
            events.append("second_enter")
            events.append("second_exit")

    await asyncio.gather(_first(), _second())

    assert events == ["first_enter", "first_exit", "second_enter", "second_exit"]


@pytest.mark.asyncio
async def test_zone_execution_context_allows_parallel_different_zones() -> None:
    release = asyncio.Event()
    both_started = asyncio.Event()
    started = 0

    async def _worker(zone_id: int) -> None:
        nonlocal started
        async with zone_execution_context(zone_id=zone_id, task_type="diagnostics", workflow="startup"):
            started += 1
            if started >= 2:
                both_started.set()
            await release.wait()

    first = asyncio.create_task(_worker(201))
    second = asyncio.create_task(_worker(202))

    await asyncio.wait_for(both_started.wait(), timeout=0.3)
    release.set()
    await asyncio.gather(first, second)
