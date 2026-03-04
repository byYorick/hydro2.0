from __future__ import annotations

import logging

import pytest

from executor.workflow_phase_update import update_zone_workflow_phase


class _ZoneServiceStub:
    def __init__(self, phase: str):
        self._phase = phase
        self.update_calls = 0

    def _get_zone_state(self, _zone_id: int):
        return {"workflow_phase": self._phase}

    async def update_workflow_phase(self, **_kwargs):
        self.update_calls += 1


@pytest.mark.asyncio
async def test_update_zone_workflow_phase_skips_same_phase_transition(caplog):
    zone_service = _ZoneServiceStub("tank_recirc")
    create_event_calls = []
    validate_calls = []

    async def _create_zone_event_safe(**kwargs):
        create_event_calls.append(kwargs)
        return True

    def _validate_phase_transition(*_args, **_kwargs):
        validate_calls.append((_args, _kwargs))
        return True

    with caplog.at_level(logging.DEBUG, logger="executor.workflow_phase_update"):
        result = await update_zone_workflow_phase(
            zone_id=10,
            workflow_phase="tank_recirc",
            context={},
            workflow_stage=None,
            reason_code=None,
            source="test",
            zone_service=zone_service,
            workflow_phase_event_type="WORKFLOW_PHASE_UPDATED",
            normalize_workflow_phase_fn=lambda value: str(value or "").strip().lower(),
            normalize_workflow_stage_fn=lambda value: str(value or "").strip().lower(),
            validate_phase_transition_fn=_validate_phase_transition,
            create_zone_event_safe_fn=_create_zone_event_safe,
            log_warning=lambda *_args, **_kwargs: None,
        )

    assert result == "tank_recirc"
    assert zone_service.update_calls == 0
    assert create_event_calls == []
    assert validate_calls == []
    assert "workflow phase already at tank_recirc, skipping transition" in caplog.text
