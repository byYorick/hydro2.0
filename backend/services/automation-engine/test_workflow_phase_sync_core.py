"""Unit tests for application.workflow_phase_sync_core helpers."""

import asyncio
from unittest.mock import AsyncMock, Mock

from application.workflow_phase_sync_core import sync_zone_workflow_phase_core


def _base_kwargs():
    return {
        "zone_id": 1,
        "task_type": "irrigation",
        "payload": {"workflow": "cycle_start"},
        "result": {"decision": "run", "reason_code": "ok", "success": True},
        "context": {"task_id": "st-1"},
        "logger_obj": Mock(),
        "workflow_state_persist_enabled": True,
        "workflow_state_persist_failed": False,
        "extract_workflow_hint_fn": lambda *_: "cycle_start",
        "normalize_workflow_phase_fn": lambda value: value,
        "resolve_workflow_stage_for_state_sync_fn": lambda **_: "cycle_start",
        "build_workflow_state_payload_fn": lambda **_: {"state": "ok"},
        "zone_service": None,
        "send_infra_alert_fn": AsyncMock(),
    }


def test_sync_zone_workflow_phase_core_skips_when_no_phase():
    kwargs = _base_kwargs()
    kwargs["derive_workflow_phase_fn"] = lambda **_: None
    kwargs["workflow_state_store_set_fn"] = AsyncMock()

    persist_failed = asyncio.run(sync_zone_workflow_phase_core(**kwargs))

    assert persist_failed is False
    kwargs["workflow_state_store_set_fn"].assert_not_awaited()


def test_sync_zone_workflow_phase_core_marks_persist_failed_on_store_error():
    kwargs = _base_kwargs()
    kwargs["derive_workflow_phase_fn"] = lambda **_: "tank_filling"
    kwargs["workflow_state_store_set_fn"] = AsyncMock(side_effect=RuntimeError("db down"))
    kwargs["send_infra_alert_fn"] = AsyncMock(return_value=True)

    persist_failed = asyncio.run(sync_zone_workflow_phase_core(**kwargs))

    assert persist_failed is True
    kwargs["send_infra_alert_fn"].assert_awaited_once()


def test_sync_zone_workflow_phase_core_calls_zone_service_update_method():
    kwargs = _base_kwargs()
    kwargs["derive_workflow_phase_fn"] = lambda **_: "irrigating"
    kwargs["workflow_state_store_set_fn"] = AsyncMock(return_value=None)
    zone_service = Mock()
    zone_service.update_workflow_phase = AsyncMock(return_value=None)
    kwargs["zone_service"] = zone_service

    persist_failed = asyncio.run(sync_zone_workflow_phase_core(**kwargs))

    assert persist_failed is False
    zone_service.update_workflow_phase.assert_awaited_once()
