from __future__ import annotations

import pytest

from domain.workflows.two_tank_deps import TwoTankDeps
from domain.workflows.two_tank_startup_start_branch import handle_two_tank_startup_initial


class _StartupBranchExecutorStub:
    def __init__(self, *, clean_levels: list[dict]) -> None:
        self._clean_levels = [dict(item) for item in clean_levels]
        self.read_calls = 0
        self.events: list[dict] = []

    async def _read_level_switch(self, **_kwargs):
        self.read_calls += 1
        if self._clean_levels:
            return dict(self._clean_levels.pop(0))
        return {
            "sensor_id": None,
            "sensor_label": None,
            "level": None,
            "sample_ts": None,
            "sample_age_sec": None,
            "is_stale": False,
            "has_level": False,
            "is_triggered": False,
            "expected_labels": ["level_clean_max", "clean_max"],
            "available_sensor_labels": [],
            "level_source": "none",
        }

    async def _emit_task_event(self, **kwargs):
        self.events.append(dict(kwargs))

    def _telemetry_freshness_enforce(self) -> bool:
        return True

    async def _start_two_tank_clean_fill(self, **_kwargs):
        return {
            "success": True,
            "mode": "two_tank_clean_fill_started",
            "workflow": "startup",
            "reason_code": "clean_fill_started",
        }

    async def _start_two_tank_solution_fill(self, **_kwargs):
        raise AssertionError("unexpected call")


def _runtime_cfg(*, retries: int, retry_delay_sec: float) -> dict:
    return {
        "clean_max_labels": ["level_clean_max", "clean_max"],
        "clean_min_labels": ["level_clean_min", "clean_min"],
        "level_switch_on_threshold": 0.5,
        "startup_clean_level_retry_attempts": retries,
        "startup_clean_level_retry_delay_sec": retry_delay_sec,
    }


def _build_deps(executor: _StartupBranchExecutorStub, zone_id: int = 445) -> TwoTankDeps:
    return TwoTankDeps(
        zone_id=zone_id,
        read_level_switch=executor._read_level_switch,
        emit_task_event=executor._emit_task_event,
        telemetry_freshness_enforce=executor._telemetry_freshness_enforce,
        start_two_tank_clean_fill=executor._start_two_tank_clean_fill,
        start_two_tank_solution_fill=executor._start_two_tank_solution_fill,
    )


@pytest.mark.asyncio
async def test_startup_initial_retries_until_clean_level_available(monkeypatch):
    executor = _StartupBranchExecutorStub(
        clean_levels=[
            {
                "sensor_id": None,
                "sensor_label": None,
                "level": None,
                "sample_ts": None,
                "sample_age_sec": None,
                "is_stale": False,
                "has_level": False,
                "is_triggered": False,
                "expected_labels": ["level_clean_max", "clean_max"],
                "available_sensor_labels": [],
                "level_source": "none",
            },
            {
                "sensor_id": 148,
                "sensor_label": "level_clean_max",
                "level": 1.0,
                "sample_ts": "2026-03-03T18:11:07",
                "sample_age_sec": 0.3,
                "is_stale": False,
                "has_level": True,
                "is_triggered": False,
                "expected_labels": ["level_clean_max", "clean_max"],
                "available_sensor_labels": ["level_clean_max"],
                "level_source": "telemetry_last",
            },
        ]
    )
    deps = _build_deps(executor)

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("domain.workflows.two_tank_startup_start_branch.asyncio.sleep", _no_sleep)

    result = await handle_two_tank_startup_initial(
        deps,
        payload={},
        context={"task_id": "tt-startup-1"},
        runtime_cfg=_runtime_cfg(retries=6, retry_delay_sec=1.0),
        workflow="startup",
    )

    assert result["success"] is True
    assert result["mode"] == "two_tank_clean_fill_started"
    assert executor.read_calls == 2
    assert len(executor.events) == 1
    assert executor.events[0]["event_type"] == "TANK_LEVEL_CHECKED"


@pytest.mark.asyncio
async def test_startup_initial_fails_after_retry_budget_exhausted(monkeypatch):
    executor = _StartupBranchExecutorStub(
        clean_levels=[
            {
                "sensor_id": None,
                "sensor_label": None,
                "level": None,
                "sample_ts": None,
                "sample_age_sec": None,
                "is_stale": False,
                "has_level": False,
                "is_triggered": False,
                "expected_labels": ["level_clean_max", "clean_max"],
                "available_sensor_labels": [],
                "level_source": "none",
            }
        ]
    )
    deps = _build_deps(executor)

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("domain.workflows.two_tank_startup_start_branch.asyncio.sleep", _no_sleep)

    result = await handle_two_tank_startup_initial(
        deps,
        payload={},
        context={"task_id": "tt-startup-2"},
        runtime_cfg=_runtime_cfg(retries=2, retry_delay_sec=1.0),
        workflow="startup",
    )

    assert result["success"] is False
    assert result["mode"] == "two_tank_clean_level_unavailable"
    assert result["reason_code"] == "sensor_level_unavailable"
    assert result["startup_retry_attempts"] == 2
    assert result["startup_retry_delay_sec"] == 1.0
    assert executor.read_calls == 3
