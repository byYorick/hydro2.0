from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from ae3lite.application.use_cases import FinalizeTaskUseCase
from ae3lite.domain.entities import AutomationTask


def _build_task(*, status: str = "running") -> AutomationTask:
    now = datetime.now(timezone.utc)
    return AutomationTask.from_row({
        "id": 11, "zone_id": 5, "task_type": "cycle_start", "status": status,
        "idempotency_key": "task-11", "scheduled_for": now, "due_at": now,
        "claimed_by": "worker-a", "claimed_at": now,
        "error_code": None, "error_message": None,
        "created_at": now, "updated_at": now, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "startup", "workflow_phase": "idle",
        "stage_deadline_at": None, "stage_retry_count": 0, "stage_entered_at": None,
        "clean_fill_cycle": 0, "corr_step": None,
    })


@pytest.mark.asyncio
async def test_finalize_task_complete_uses_repository_transition() -> None:
    task = _build_task()
    completed_task = replace(task, status="completed", completed_at=task.updated_at)

    class _Repo:
        async def mark_completed(self, **kwargs):
            assert kwargs["task_id"] == task.id
            assert kwargs["owner"] == "worker-a"
            return completed_task

    use_case = FinalizeTaskUseCase(task_repository=_Repo())

    result = await use_case.complete(task=task, owner="worker-a", now=task.updated_at)

    assert result.status == "completed"


@pytest.mark.asyncio
async def test_finalize_task_fail_closed_returns_synthetic_terminal_when_row_missing() -> None:
    task = _build_task()

    class _Repo:
        async def mark_failed(self, **kwargs):
            assert kwargs["task_id"] == task.id
            return None

        async def get_by_id(self, **kwargs):
            assert kwargs["task_id"] == task.id
            return None

    use_case = FinalizeTaskUseCase(task_repository=_Repo())

    result = await use_case.fail_closed(
        task=task,
        owner="worker-a",
        error_code="ae3_task_execution_failed",
        error_message="boom",
        now=task.updated_at,
    )

    assert result.status == "failed"
    assert result.error_code == "ae3_task_execution_failed"
    assert result.error_message == "boom"
