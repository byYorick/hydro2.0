"""Тесты атомарного выделения step_no для ae_commands."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ae3lite.infrastructure.repositories import PgAeCommandRepository, PgAutomationTaskRepository
from common.db import fetch

from test_ae3lite_startup_recovery_integration import (
    _cleanup,
    _insert_greenhouse,
    _insert_task,
    _insert_zone,
)


@pytest.mark.asyncio
async def test_allocate_and_create_pending_assigns_monotonic_steps_under_concurrency() -> None:
    prefix = f"ae3-cmd-alloc-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    command_repo = PgAeCommandRepository()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(prefix, greenhouse_id=greenhouse_id)
        task_id = await _insert_task(
            zone_id,
            prefix=prefix,
            task_status="running",
            now=now,
            topology="two_tank_drip_substrate_trays",
            current_stage="solution_fill_check",
            workflow_phase="tank_filling",
        )

        async def _allocate(step_suffix: int) -> tuple[int, int, bool] | None:
            return await command_repo.allocate_and_create_pending(
                task_id=task_id,
                zone_id=zone_id,
                node_uid=f"nd-{step_suffix}",
                channel="pump_main",
                payload={"cmd": "dose", "params": {"ml": 1.0}},
                now=now,
                planner_step=f"solution_fill_check:{step_suffix}",
            )

        results = await asyncio.gather(_allocate(1), _allocate(2), _allocate(3))
        assert all(result is not None for result in results)
        step_numbers = sorted(
            step_no for result in results if result is not None for (_, step_no, _) in (result,)
        )
        assert step_numbers == [1, 2, 3]

        rows = await fetch(
            """
            SELECT step_no
            FROM ae_commands
            WHERE task_id = $1
            ORDER BY step_no ASC
            """,
            task_id,
        )
        assert [int(row["step_no"]) for row in rows] == [1, 2, 3]
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_allocate_and_create_pending_returns_none_when_task_missing() -> None:
    command_repo = PgAeCommandRepository()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await command_repo.allocate_and_create_pending(
        task_id=9_999_999,
        zone_id=1,
        node_uid="missing-node",
        channel="pump_main",
        payload={"cmd": "dose", "params": {"ml": 1.0}},
        now=now,
    )
    assert result is None
