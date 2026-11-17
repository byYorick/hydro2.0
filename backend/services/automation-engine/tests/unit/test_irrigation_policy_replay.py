"""Replay representative observations without sending any actuator commands."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.handlers.decision_gate import DecisionGateHandler
from ae3lite.domain.services.irrigation_decision_controller import IrrigationDecision, IrrigationDecisionController


def _window(*values):
    return {"samples": [{"value": value} for value in values], "is_stale": False}


@pytest.mark.asyncio
async def test_dry_wet_sensor_loss_and_recovery_policy_replay():
    runtime = make_runtime_plan(
        irrigation_decision={"strategy": "smart_soil_v1", "config": {"min_samples": 3, "hysteresis_pct": 2}},
        soil_moisture_target={"min": 40, "max": 50},
    )
    frames = [
        ([_window(32, 34, 36)], False, "run", False),
        ([_window(52, 54, 56)], False, "skip", False),
        ([_window(42, 44, 46)], False, "skip", False),
        ([_window(31)], False, "run", True),
        ([_window(20, 21, 22), _window(50, 51, 52)], False, "run", True),
        ([_window(30, 31, 32), _window()], False, "skip", False),
        ([_window(30, 31, 32)], True, "skip", False),
        ([], False, "skip", False),
        ([_window(31, 33, 35)], False, "run", False),
        ([_window(38, 38, 38)], False, "skip", False),
    ]
    controller = IrrigationDecisionController()
    for index, (windows, stale, outcome, degraded) in enumerate(frames):
        monitor = SimpleNamespace(read_metric_windows=AsyncMock(return_value={
            "sensor_windows": windows, "is_stale": stale,
        }))
        result = await controller.evaluate(
            zone_id=7, runtime_monitor=monitor, runtime=runtime, mode="normal", requested_duration_sec=120,
            now=datetime(2026, 11, 16, 12) + timedelta(minutes=5 * index),
        )
        assert (result.outcome, result.degraded) == (outcome, degraded), f"Replay frame {index}"


@pytest.mark.asyncio
async def test_unavailable_temperature_keeps_soil_evidence_and_warning(monkeypatch):
    runtime = make_runtime_plan(solution_health={"required": True, "min_c": 18, "max_c": 24, "breach_hold_sec": 600})
    handler = DecisionGateHandler(
        runtime_monitor=SimpleNamespace(read_solution_temp_window=AsyncMock(return_value=None)),
        command_gateway=object(), task_repository=object(), decision_controller=object(),
    )
    monkeypatch.setattr(handler, "_emit_solution_sensor_alert", AsyncMock())
    result = await handler._apply_solution_temp_gate(
        decision=IrrigationDecision(outcome="run", reason_code="smart_soil_below_min", details={"zone_average_pct": 30}),
        task=SimpleNamespace(id=3, zone_id=7), runtime=runtime, now=datetime(2026, 11, 16, 12),
    )
    assert result.outcome == "run"
    assert result.details["zone_average_pct"] == 30
    assert result.details["solution_temp"]["reason_code"] == "solution_temp_unavailable"
    assert result.details["solution_temp"]["blocks_irrigation"] is False
