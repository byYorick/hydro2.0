"""Unit tests for irrigation actuation mode helpers."""

from __future__ import annotations

from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.services.irrigation_actuation import (
    irrigation_start_uses_set_relay_pump,
    irrigation_start_uses_timed_run_pump,
)


class _PlanStub:
    def __init__(self, commands: tuple[PlannedCommand, ...]):
        self.named_plans = {"irrigation_start": commands}


def test_irrigation_start_uses_timed_run_pump() -> None:
    plan = _PlanStub(
        (
            PlannedCommand(
                step_no=1,
                node_uid="nd-irrig-1",
                channel="pump_main",
                payload={"cmd": "run_pump", "params": {"duration_ms": 120_000}},
            ),
        ),
    )

    assert irrigation_start_uses_timed_run_pump(plan) is True
    assert irrigation_start_uses_set_relay_pump(plan) is False


def test_irrigation_start_uses_set_relay_pump() -> None:
    plan = _PlanStub(
        (
            PlannedCommand(
                step_no=1,
                node_uid="nd-irrig-1",
                channel="pump_main",
                payload={"cmd": "set_relay", "params": {"state": True}},
            ),
        ),
    )

    assert irrigation_start_uses_timed_run_pump(plan) is False
    assert irrigation_start_uses_set_relay_pump(plan) is True
