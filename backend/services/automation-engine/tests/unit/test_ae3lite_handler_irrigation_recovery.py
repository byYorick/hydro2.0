"""Post-irrigation chemistry recovery was removed — fail-closed contract tests."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ae3lite.application.handlers.irrigation_recovery import IrrigationRecoveryCheckHandler
from ae3lite.application.use_cases.workflow_router import WorkflowRouter
from ae3lite.domain.errors import TaskExecutionError


def test_irrigation_recovery_not_registered_in_router() -> None:
    assert "irrigation_recovery" not in WorkflowRouter.HANDLER_MAP
    assert not any("irrigation_recovery" in key for key in WorkflowRouter.HANDLER_MAP)


@pytest.mark.asyncio
async def test_irrigation_recovery_handler_fail_closed() -> None:
    handler = IrrigationRecoveryCheckHandler(runtime_monitor=object(), command_gateway=object())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(
            task=SimpleNamespace(id=1, zone_id=7, current_stage="irrigation_recovery_check"),
            plan=SimpleNamespace(),
            stage_def=SimpleNamespace(),
            now=now,
        )
    assert exc_info.value.code == "irrigation_recovery_removed"
