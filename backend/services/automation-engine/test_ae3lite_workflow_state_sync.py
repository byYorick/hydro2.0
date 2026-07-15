"""Tests for CAS-safe zone_workflow_state sync helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ae3lite.domain.errors import Ae3LiteError, ErrorCodes, TaskExecutionError
from ae3lite.domain.services.workflow_state_sync import (
    WorkflowStateSyncError,
    upsert_workflow_phase_strict,
    upsert_workflow_phase_task_error,
)

NOW = datetime(2026, 7, 15, 8, 0, 0, tzinfo=timezone.utc)


class _WorkflowRepoStub:
    def __init__(self, *, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.calls = 0

    async def upsert_phase(self, **kwargs):
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise Ae3LiteError("zone_workflow_state CAS conflict on zone_id=1: concurrent modification detected")
        return kwargs


@pytest.mark.asyncio
async def test_upsert_workflow_phase_strict_retries_cas_then_succeeds() -> None:
    repo = _WorkflowRepoStub(fail_times=2)
    await upsert_workflow_phase_strict(
        repo,
        zone_id=1,
        workflow_phase="ready",
        payload={"ae3_cycle_start_stage": "await_ready"},
        scheduler_task_id="42",
        now=NOW,
    )
    assert repo.calls == 3


@pytest.mark.asyncio
async def test_upsert_workflow_phase_strict_raises_after_cas_exhaustion() -> None:
    repo = _WorkflowRepoStub(fail_times=5)
    with pytest.raises(WorkflowStateSyncError) as exc_info:
        await upsert_workflow_phase_strict(
            repo,
            zone_id=1,
            workflow_phase="ready",
            payload={},
            scheduler_task_id=None,
            now=NOW,
        )
    assert exc_info.value.code == ErrorCodes.AE3_WORKFLOW_STATE_SYNC_FAILED
    assert repo.calls == 3


@pytest.mark.asyncio
async def test_upsert_workflow_phase_task_error_maps_to_task_execution_error() -> None:
    repo = _WorkflowRepoStub(fail_times=5)
    with pytest.raises(TaskExecutionError) as exc_info:
        await upsert_workflow_phase_task_error(
            repo,
            zone_id=9,
            workflow_phase="tank_filling",
            payload={},
            scheduler_task_id="99",
            now=NOW,
        )
    assert exc_info.value.code == ErrorCodes.AE3_WORKFLOW_STATE_SYNC_FAILED
