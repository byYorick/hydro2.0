"""PR7: manual_hold transitions для irrigation_check handler."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ae3_preflight_helpers import patch_fetch_zone_nodes_diagnostics
from _test_support_runtime_plan import make_runtime_plan
from ae3lite.application.handlers.irrigation_check import IrrigationCheckHandler


NOW = datetime(2026, 7, 6, 9, 0, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(hours=1)

_IRR_ACTIVE = {
    "has_snapshot": True,
    "is_stale": False,
    "snapshot": {
        "valve_solution_supply": True,
        "valve_irrigation": True,
        "pump_main": True,
    },
}
_IRR_OFF = {
    "has_snapshot": True,
    "is_stale": False,
    "snapshot": {
        "valve_solution_supply": False,
        "valve_irrigation": False,
        "pump_main": False,
    },
}


@pytest.fixture(autouse=True)
def _noop_flow_path_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ae3lite.application.handlers.flow_path_guard.create_zone_event",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "ae3lite.application.handlers.flow_path_guard.send_biz_alert",
        AsyncMock(return_value=None),
    )


@pytest.fixture(autouse=True)
def _ae3_online_zone_nodes_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_fetch_zone_nodes_diagnostics(monkeypatch)


class _Monitor:
    def __init__(self, *, irr_states: list[dict], irr_state: dict) -> None:
        self._irr_states = list(irr_states)
        self._irr_state = irr_state

    async def read_latest_irr_state(self, **_kw: Any) -> dict:
        if self._irr_states:
            return self._irr_states.pop(0)
        return self._irr_state


class _Gateway:
    async def run_batch(self, **_kw: Any) -> dict:
        return {"success": True, "error_code": None, "error_message": None}


class _TaskRepo:
    async def reset_irr_probe_failure_streak(self, *, task_id: int) -> None:
        return None


def _plan(*, named: dict[str, tuple[str, ...]] | None = None) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        runtime=make_runtime_plan(
            level_poll_interval_sec=10,
            irrigation_safety={"stop_on_solution_min": False},
        ),
        named_plans={
            "irr_state_probe": ("probe_cmd",),
            **(named or {}),
        },
    )


@pytest.mark.asyncio
async def test_manual_irrigation_check_enters_manual_hold() -> None:
    from types import SimpleNamespace

    handler = IrrigationCheckHandler(
        runtime_monitor=_Monitor(irr_states=[dict(_IRR_ACTIVE)], irr_state=_IRR_OFF),
        command_gateway=_Gateway(),
        task_repository=_TaskRepo(),
    )
    task = SimpleNamespace(
        id=3,
        zone_id=30,
        topology="two_tank",
        current_stage="irrigation_check",
        workflow=SimpleNamespace(
            control_mode="manual",
            pending_manual_step=None,
            stage_deadline_at=FUTURE,
            stage_entered_at=NOW,
        ),
    )
    plan = _plan(
        named={
            "irrigation_stop": ("stop_cmd",),
            "sensor_mode_deactivate": ("deact_cmd",),
        }
    )
    outcome = await handler.run(task=task, plan=plan, stage_def=SimpleNamespace(), now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "manual_hold"
    assert outcome.flow_hold_return_stage == "irrigation_check"
