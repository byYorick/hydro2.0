from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from ae3lite.application.use_cases.get_zone_control_state import GetZoneControlStateUseCase
from ae3lite.domain.entities.workflow_state import WorkflowState


NOW = datetime(2026, 3, 14, 15, 0, 0, tzinfo=timezone.utc)


class _TaskRepository:
    def __init__(self, task: object | None = None) -> None:
        self._task = task

    async def get_active_for_zone(self, *, zone_id: int) -> object | None:
        return self._task


class _WorkflowRepository:
    def __init__(self, workflow_state: object | None = None) -> None:
        self._workflow_state = workflow_state

    async def get(self, *, zone_id: int) -> object | None:
        return self._workflow_state


async def test_control_state_returns_generic_manual_steps_for_solution_fill() -> None:
    task = SimpleNamespace(
        workflow=WorkflowState(
            current_stage="solution_fill_check",
            workflow_phase="tank_filling",
            stage_deadline_at=None,
            stage_retry_count=0,
            stage_entered_at=NOW.replace(tzinfo=None),
            clean_fill_cycle=1,
            control_mode="manual",
            pending_manual_step="solution_fill_stop",
        )
    )

    async def fetch_fn(_query: str, *_args: object) -> list[dict[str, object]]:
        return [{"control_mode": "manual"}]

    result = await GetZoneControlStateUseCase(
        task_repository=_TaskRepository(task),
        fetch_fn=fetch_fn,
    ).run(zone_id=7)

    assert result["control_mode"] == "manual"
    assert result["available_modes"] == ["auto", "semi", "manual"]
    assert result["allowed_manual_steps"] == ["solution_fill_stop"]
    assert result["pending_manual_step"] == "solution_fill_stop"


async def test_control_state_hides_manual_steps_in_auto_mode() -> None:
    task = SimpleNamespace(
        workflow=WorkflowState(
            current_stage="clean_fill_check",
            workflow_phase="tank_filling",
            stage_deadline_at=None,
            stage_retry_count=0,
            stage_entered_at=NOW.replace(tzinfo=None),
            clean_fill_cycle=1,
            control_mode="auto",
            pending_manual_step=None,
        )
    )

    async def fetch_fn(_query: str, *_args: object) -> list[dict[str, object]]:
        return [{"control_mode": "auto"}]

    result = await GetZoneControlStateUseCase(
        task_repository=_TaskRepository(task),
        fetch_fn=fetch_fn,
    ).run(zone_id=7)

    assert result["control_mode"] == "auto"
    assert result["allowed_manual_steps"] == []


async def test_control_state_returns_irrigation_stop_for_irrigation_stage() -> None:
    task = SimpleNamespace(
        workflow=WorkflowState(
            current_stage="irrigation_check",
            workflow_phase="irrigating",
            stage_deadline_at=None,
            stage_retry_count=0,
            stage_entered_at=NOW.replace(tzinfo=None),
            clean_fill_cycle=1,
            control_mode="manual",
            pending_manual_step="irrigation_stop",
        )
    )

    async def fetch_fn(_query: str, *_args: object) -> list[dict[str, object]]:
        return [{"control_mode": "manual"}]

    result = await GetZoneControlStateUseCase(
        task_repository=_TaskRepository(task),
        fetch_fn=fetch_fn,
    ).run(zone_id=7)

    assert result["allowed_manual_steps"] == ["irrigation_stop"]
    assert result["pending_manual_step"] == "irrigation_stop"


async def test_control_state_falls_back_to_zone_workflow_state_when_no_active_task() -> None:
    workflow_state = SimpleNamespace(
        workflow_phase="ready",
        payload={"ae3_cycle_start_stage": "completed_run"},
    )

    async def fetch_fn(_query: str, *_args: object) -> list[dict[str, object]]:
        return [{"control_mode": "manual"}]

    result = await GetZoneControlStateUseCase(
        task_repository=_TaskRepository(None),
        workflow_repository=_WorkflowRepository(workflow_state),
        fetch_fn=fetch_fn,
    ).run(zone_id=7)

    assert result["control_mode"] == "manual"
    assert result["workflow_phase"] == "ready"
    assert result["current_stage"] == "completed_run"
    assert result["allowed_manual_steps"] == []
    assert result["pending_manual_step"] is None


async def test_control_state_ignores_stale_zone_workflow_state_when_last_task_is_newer() -> None:
    workflow_state = SimpleNamespace(
        workflow_phase="ready",
        scheduler_task_id="42",
        updated_at=datetime(2026, 3, 14, 15, 0, 0, tzinfo=timezone.utc),
        payload={"ae3_cycle_start_stage": "completed_run"},
    )
    last_task = SimpleNamespace(
        id=42,
        is_active=False,
        updated_at=datetime(2026, 3, 14, 15, 1, 0, tzinfo=timezone.utc),
    )

    class _TaskRepositoryWithLast(_TaskRepository):
        async def get_last_for_zone(self, *, zone_id: int) -> object | None:
            return last_task

    async def fetch_fn(_query: str, *_args: object) -> list[dict[str, object]]:
        return [{"control_mode": "manual"}]

    result = await GetZoneControlStateUseCase(
        task_repository=_TaskRepositoryWithLast(None),
        workflow_repository=_WorkflowRepository(workflow_state),
        fetch_fn=fetch_fn,
    ).run(zone_id=7)

    assert result["workflow_phase"] is None
    assert result["current_stage"] is None
    assert result["allowed_manual_steps"] == []
