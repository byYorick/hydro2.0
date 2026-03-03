import asyncio
from datetime import datetime, timezone

import pytest

from ae2lite.api_zone_task_loader import load_latest_zone_task


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_load_latest_zone_task_prefers_db_terminal_for_same_task_id_when_memory_is_active():
    scheduler_tasks = {
        "st-1": {
            "task_id": "st-1",
            "zone_id": 9,
            "task_type": "diagnostics",
            "status": "running",
            "created_at": _dt("2026-03-03T13:20:05Z"),
            "updated_at": _dt("2026-03-03T13:20:05Z"),
        }
    }
    lock = asyncio.Lock()

    async def _cleanup(_now: datetime) -> None:
        return None

    async def _fetch(_query: str, _zone_id: int):
        return [
            {
                "task_name": "ae_scheduler_task_st-1",
                "created_at": _dt("2026-03-03T13:22:10Z"),
                "details": {
                    "task_id": "st-1",
                    "zone_id": 9,
                    "task_type": "diagnostics",
                    "status": "failed",
                    "updated_at": "2026-03-03T13:22:10",
                    "error_code": "command_timeout",
                },
            }
        ]

    result = await load_latest_zone_task(
        9,
        scheduler_tasks_lock=lock,
        scheduler_tasks=scheduler_tasks,
        cleanup_scheduler_tasks_locked_fn=_cleanup,
        fetch_fn=_fetch,
        logger=pytest,
    )

    assert result is not None
    assert result["task_id"] == "st-1"
    assert result["status"] == "failed"
    assert scheduler_tasks["st-1"]["status"] == "failed"


@pytest.mark.asyncio
async def test_load_latest_zone_task_from_db_collapses_same_task_id_to_latest_status():
    scheduler_tasks = {}
    lock = asyncio.Lock()

    async def _cleanup(_now: datetime) -> None:
        return None

    async def _fetch(_query: str, _zone_id: int):
        return [
            {
                "task_name": "ae_scheduler_task_st-22",
                "created_at": _dt("2026-03-03T13:22:10Z"),
                "details": {
                    "task_id": "st-22",
                    "zone_id": 9,
                    "task_type": "diagnostics",
                    "status": "failed",
                    "updated_at": "2026-03-03T13:22:10",
                },
            },
            {
                "task_name": "ae_scheduler_task_st-22",
                "created_at": _dt("2026-03-03T13:20:05Z"),
                "details": {
                    "task_id": "st-22",
                    "zone_id": 9,
                    "task_type": "diagnostics",
                    "status": "running",
                    "updated_at": "2026-03-03T13:20:05",
                },
            },
        ]

    result = await load_latest_zone_task(
        9,
        scheduler_tasks_lock=lock,
        scheduler_tasks=scheduler_tasks,
        cleanup_scheduler_tasks_locked_fn=_cleanup,
        fetch_fn=_fetch,
        logger=pytest,
    )

    assert result is not None
    assert result["task_id"] == "st-22"
    assert result["status"] == "failed"
