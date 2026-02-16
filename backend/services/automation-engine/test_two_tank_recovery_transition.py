"""Unit tests for application.two_tank_recovery_transition helpers."""

import asyncio
from unittest.mock import AsyncMock

from application.two_tank_recovery_transition import (
    try_start_two_tank_irrigation_recovery_from_irrigation_failure,
)


def test_try_start_two_tank_irrigation_recovery_returns_none_on_success():
    result = asyncio.run(
        try_start_two_tank_irrigation_recovery_from_irrigation_failure(
            zone_id=1,
            payload={},
            context={},
            result={"success": True},
            allowed_error_codes=("command_timeout",),
            reason_online_correction_failed="online_correction_failed",
            reason_tank_to_tank_correction_started="tank_to_tank_correction_started",
            build_two_tank_runtime_payload_fn=lambda _: {},
            resolve_two_tank_runtime_config_fn=lambda _: {},
            emit_task_event_fn=AsyncMock(),
            start_two_tank_irrigation_recovery_fn=AsyncMock(),
        )
    )
    assert result is None


def test_try_start_two_tank_irrigation_recovery_returns_none_on_unsupported_error():
    result = asyncio.run(
        try_start_two_tank_irrigation_recovery_from_irrigation_failure(
            zone_id=1,
            payload={},
            context={},
            result={"success": False, "error_code": "unknown_error"},
            allowed_error_codes=("command_timeout",),
            reason_online_correction_failed="online_correction_failed",
            reason_tank_to_tank_correction_started="tank_to_tank_correction_started",
            build_two_tank_runtime_payload_fn=lambda _: {},
            resolve_two_tank_runtime_config_fn=lambda _: {},
            emit_task_event_fn=AsyncMock(),
            start_two_tank_irrigation_recovery_fn=AsyncMock(),
        )
    )
    assert result is None


def test_try_start_two_tank_irrigation_recovery_starts_recovery_and_enriches_result():
    emit_task_event = AsyncMock(return_value=None)
    start_recovery = AsyncMock(return_value={"success": True})
    previous_result = {"success": False, "error_code": "command_timeout"}

    result = asyncio.run(
        try_start_two_tank_irrigation_recovery_from_irrigation_failure(
            zone_id=5,
            payload={"k": "v"},
            context={"task_id": "st-5"},
            result=previous_result,
            allowed_error_codes=("command_timeout",),
            reason_online_correction_failed="online_correction_failed",
            reason_tank_to_tank_correction_started="tank_to_tank_correction_started",
            build_two_tank_runtime_payload_fn=lambda payload: {**payload, "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}},
            resolve_two_tank_runtime_config_fn=lambda _: {"poll_interval_sec": 60},
            emit_task_event_fn=emit_task_event,
            start_two_tank_irrigation_recovery_fn=start_recovery,
        )
    )

    assert result is not None
    assert result["success"] is True
    assert result["task_type"] == "irrigation"
    assert result["online_correction_error_code"] == "command_timeout"
    emit_task_event.assert_awaited_once()
    start_recovery.assert_awaited_once()
