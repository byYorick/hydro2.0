from __future__ import annotations

from datetime import datetime

import pytest

from ae3lite.application.use_cases.startup_recovery import StartupRecoveryUseCase
from ae3lite.infrastructure.metrics import STARTUP_RECOVERY_RUN, STARTUP_RECOVERY_TASK


class _LeaseRepoStub:
    async def release_expired(self, *, now: datetime) -> int:
        return 0


class _TaskRepoStub:
    async def list_for_startup_recovery(self) -> list[object]:
        return [object(), object(), object()]

    async def fetch_pending_with_idle_zone_workflow_rows(self) -> list[dict]:
        return []


@pytest.mark.asyncio
async def test_startup_recovery_records_pass_and_task_outcome_metrics(monkeypatch) -> None:
    before_runs = STARTUP_RECOVERY_RUN._value.get()
    before_completed = STARTUP_RECOVERY_TASK.labels(outcome="completed")._value.get()
    before_failed = STARTUP_RECOVERY_TASK.labels(outcome="failed")._value.get()
    before_recovered = STARTUP_RECOVERY_TASK.labels(outcome="recovered_waiting_command")._value.get()

    use_case = StartupRecoveryUseCase(
        task_repository=_TaskRepoStub(),
        lease_repository=_LeaseRepoStub(),
        command_gateway=object(),
    )

    outcomes = iter(
        [
            ("completed", None),
            ("failed", None),
            ("recovered_waiting_command", None),
        ]
    )

    async def _recover_task(*, task: object, now: datetime) -> tuple[str, None]:
        return next(outcomes)

    monkeypatch.setattr(use_case, "_recover_task", _recover_task)

    result = await use_case.run(now=datetime(2026, 4, 4, 12, 0, 0))

    assert result.scanned_tasks == 3
    assert result.completed_tasks == 1
    assert result.failed_tasks == 1
    assert result.waiting_command_tasks == 1
    assert result.recovered_waiting_command_tasks == 1
    assert STARTUP_RECOVERY_RUN._value.get() == before_runs + 1
    assert STARTUP_RECOVERY_TASK.labels(outcome="completed")._value.get() == before_completed + 1
    assert STARTUP_RECOVERY_TASK.labels(outcome="failed")._value.get() == before_failed + 1
    assert (
        STARTUP_RECOVERY_TASK.labels(outcome="recovered_waiting_command")._value.get()
        == before_recovered + 1
    )
