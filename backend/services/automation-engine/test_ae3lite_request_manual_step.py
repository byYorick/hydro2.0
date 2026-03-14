from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ae3lite.application.use_cases.request_manual_step import RequestManualStepUseCase
from ae3lite.domain.entities.workflow_state import WorkflowState
from ae3lite.domain.errors import ManualControlError


NOW = datetime(2026, 3, 14, 15, 10, 0, tzinfo=timezone.utc)


class _TaskRepository:
    def __init__(self, task: object | None = None) -> None:
        self._task = task
        self.calls: list[dict[str, object]] = []

    async def get_active_for_zone(self, *, zone_id: int) -> object | None:
        return self._task

    async def set_pending_manual_step(self, *, task_id: int, manual_step: str, now: datetime) -> object | None:
        self.calls.append({"task_id": task_id, "manual_step": manual_step, "now": now})
        if self._task is None:
            return None
        workflow = self._task.workflow
        updated_workflow = WorkflowState(
            current_stage=workflow.current_stage,
            workflow_phase=workflow.workflow_phase,
            stage_deadline_at=workflow.stage_deadline_at,
            stage_retry_count=workflow.stage_retry_count,
            stage_entered_at=workflow.stage_entered_at,
            clean_fill_cycle=workflow.clean_fill_cycle,
            control_mode=workflow.control_mode,
            pending_manual_step=manual_step,
        )
        return SimpleNamespace(id=task_id, workflow=updated_workflow)


def _task(*, stage: str = "startup") -> object:
    return SimpleNamespace(
        id=321,
        workflow=WorkflowState(
            current_stage=stage,
            workflow_phase="tank_filling" if stage != "startup" else "idle",
            stage_deadline_at=None,
            stage_retry_count=0,
            stage_entered_at=NOW.replace(tzinfo=None),
            clean_fill_cycle=1,
            control_mode="manual",
            pending_manual_step=None,
        ),
    )


async def test_request_manual_step_returns_numeric_task_id() -> None:
    repo = _TaskRepository(_task(stage="clean_fill_check"))

    async def fetch_fn(_query: str, *_args: object) -> list[dict[str, object]]:
        return [{"control_mode": "manual"}]

    result = await RequestManualStepUseCase(
        task_repository=repo,
        fetch_fn=fetch_fn,
    ).run(zone_id=7, manual_step="clean_fill_stop", now=NOW)

    assert result["task_id"] == "321"
    assert result["pending_manual_step"] == "clean_fill_stop"
    assert repo.calls[0]["manual_step"] == "clean_fill_stop"


async def test_request_manual_step_rejects_auto_mode() -> None:
    async def fetch_fn(_query: str, *_args: object) -> list[dict[str, object]]:
        return [{"control_mode": "auto"}]

    with pytest.raises(ManualControlError) as exc_info:
        await RequestManualStepUseCase(
            task_repository=_TaskRepository(_task()),
            fetch_fn=fetch_fn,
        ).run(zone_id=7, manual_step="clean_fill_start", now=NOW)

    assert exc_info.value.code == "manual_step_forbidden_in_auto_mode"
    assert exc_info.value.status_code == 409


async def test_request_manual_step_rejects_invalid_stage_step_pair() -> None:
    async def fetch_fn(_query: str, *_args: object) -> list[dict[str, object]]:
        return [{"control_mode": "manual"}]

    with pytest.raises(ManualControlError) as exc_info:
        await RequestManualStepUseCase(
            task_repository=_TaskRepository(_task(stage="prepare_recirculation_check")),
            fetch_fn=fetch_fn,
        ).run(zone_id=7, manual_step="clean_fill_stop", now=NOW)

    assert exc_info.value.code == "manual_step_not_allowed_for_stage"
    assert exc_info.value.status_code == 422
