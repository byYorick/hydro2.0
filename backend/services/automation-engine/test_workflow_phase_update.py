"""Unit tests for application.workflow_phase_update helpers."""

from unittest.mock import AsyncMock, Mock

import pytest

from application.workflow_phase_update import update_zone_workflow_phase


@pytest.mark.asyncio
async def test_update_zone_workflow_phase_prefers_zone_service_update():
    zone_service = Mock()
    zone_service.update_workflow_phase = AsyncMock(return_value=None)
    create_event = AsyncMock(return_value=True)

    phase = await update_zone_workflow_phase(
        zone_id=1,
        workflow_phase="tank_filling",
        context={},
        workflow_stage="startup",
        reason_code="ok",
        source="scheduler_task_executor",
        zone_service=zone_service,
        workflow_phase_event_type="WORKFLOW_PHASE_UPDATED",
        normalize_workflow_phase_fn=lambda x: str(x),
        normalize_workflow_stage_fn=lambda x: str(x),
        create_zone_event_safe_fn=create_event,
        log_warning=Mock(),
    )

    assert phase == "tank_filling"
    zone_service.update_workflow_phase.assert_awaited_once()
    create_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_zone_workflow_phase_falls_back_to_event():
    zone_service = Mock()
    zone_service.update_workflow_phase = AsyncMock(side_effect=RuntimeError("fail"))
    create_event = AsyncMock(return_value=True)

    phase = await update_zone_workflow_phase(
        zone_id=2,
        workflow_phase="ready",
        context={"task_id": "st-2", "correlation_id": "corr-2"},
        workflow_stage=None,
        reason_code=None,
        source="scheduler_task_executor",
        zone_service=zone_service,
        workflow_phase_event_type="WORKFLOW_PHASE_UPDATED",
        normalize_workflow_phase_fn=lambda x: str(x),
        normalize_workflow_stage_fn=lambda x: str(x or ""),
        create_zone_event_safe_fn=create_event,
        log_warning=Mock(),
    )

    assert phase == "ready"
    create_event.assert_awaited_once()
