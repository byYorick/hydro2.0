from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest

from domain.models.decision_models import DecisionOutcome
from domain.policies.two_tank_safety_config import TwoTankSafetyConfig
from domain.workflows.two_tank_core import execute_two_tank_startup_workflow_core
from domain.workflows.two_tank_deps import TwoTankDeps


def _decision() -> DecisionOutcome:
    return DecisionOutcome(
        action_required=True,
        decision="run",
        reason_code="diagnostics_required",
        reason="Требуется выполнить задачу по расписанию",
    )


def _runtime_cfg() -> Dict[str, Any]:
    return {
        "required_node_types": ["irrig"],
        "clean_fill_timeout_sec": 600,
        "solution_fill_timeout_sec": 900,
        "prepare_recirculation_timeout_sec": 600,
        "irrigation_recovery_timeout_sec": 600,
        "poll_interval_sec": 60,
        "clean_max_labels": ["level_clean_max"],
        "clean_min_labels": ["level_clean_min"],
        "solution_max_labels": ["level_solution_max"],
        "solution_min_labels": ["level_solution_min"],
        "level_switch_on_threshold": 0.5,
        "startup_clean_level_retry_attempts": 0,
        "startup_clean_level_retry_delay_sec": 0.0,
        "target_ph": 5.8,
        "target_ec_prepare": 1.2,
        "prepare_tolerance": {"ec_pct": 25.0, "ph_pct": 5.0},
        "commands": {
            "clean_fill_stop": [],
            "solution_fill_stop": [],
        },
    }


@pytest.mark.asyncio
async def test_startup_resumes_solution_fill_check_from_zone_workflow_state() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start_called = False

    async def _fetch(query: str, *_args: Any):
        if "FROM zone_workflow_state" in query:
            return [
                {
                    "workflow_phase": "tank_filling",
                    "updated_at": now - timedelta(seconds=5),
                    "payload": {
                        "workflow": "startup",
                        "solution_fill_started_at": (now - timedelta(seconds=30)).isoformat(),
                        "solution_fill_timeout_at": (now + timedelta(minutes=5)).isoformat(),
                    },
                }
            ]
        return []

    async def _unexpected_start_solution_fill(**_kwargs: Any) -> Dict[str, Any]:
        nonlocal start_called
        start_called = True
        return {"success": True}

    deps = TwoTankDeps(
        zone_id=4,
        fetch_fn=_fetch,
        normalize_two_tank_workflow=lambda _payload: "startup",
        extract_topology=lambda payload: str(payload.get("topology") or "").strip().lower(),
        resolve_two_tank_runtime_config=lambda _payload: _runtime_cfg(),
        emit_task_event=lambda **_kwargs: _as_async_none(),
        update_zone_workflow_phase=lambda **_kwargs: _as_async_none(),
        check_required_nodes_online=lambda *_args, **_kwargs: _as_async_value({"missing_types": []}),
        find_zone_event_since=lambda **_kwargs: _as_async_value(None),
        read_level_switch=lambda **_kwargs: _as_async_value(
            {
                "has_level": False,
                "is_triggered": False,
                "is_stale": False,
                "expected_labels": ["level_solution_max"],
                "available_sensor_labels": [],
                "level_source": "none",
            }
        ),
        start_two_tank_solution_fill=_unexpected_start_solution_fill,
        telemetry_freshness_enforce=lambda: False,
        safety_config=TwoTankSafetyConfig(
            pump_interlock=False,
            stop_confirmation_required=False,
            irr_state_validation=False,
        ),
    )

    result = await execute_two_tank_startup_workflow_core(
        deps,
        payload={"workflow": "startup", "topology": "two_tank_drip_substrate_trays"},
        context={"task_id": "tt-resume-1"},
        decision=_decision(),
    )

    assert start_called is False
    assert result["workflow"] == "solution_fill_check"
    assert result["mode"] == "two_tank_solution_level_unavailable"


@pytest.mark.asyncio
async def test_startup_does_not_resume_from_stale_workflow_state() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    clean_fill_started = False

    async def _fetch(query: str, *_args: Any):
        if "FROM zone_workflow_state" in query:
            return [
                {
                    "workflow_phase": "tank_filling",
                    "updated_at": now - timedelta(hours=4),
                    "payload": {
                        "workflow": "solution_fill_check",
                        "solution_fill_started_at": (now - timedelta(hours=4)).isoformat(),
                        "solution_fill_timeout_at": (now - timedelta(hours=3)).isoformat(),
                    },
                }
            ]
        return []

    async def _start_two_tank_clean_fill(**_kwargs: Any) -> Dict[str, Any]:
        nonlocal clean_fill_started
        clean_fill_started = True
        return {
            "success": True,
            "mode": "two_tank_clean_fill_in_progress",
            "workflow": "startup",
            "reason_code": "clean_fill_started",
            "reason": "ok",
        }

    deps = TwoTankDeps(
        zone_id=4,
        fetch_fn=_fetch,
        normalize_two_tank_workflow=lambda _payload: "startup",
        extract_topology=lambda payload: str(payload.get("topology") or "").strip().lower(),
        resolve_two_tank_runtime_config=lambda _payload: _runtime_cfg(),
        emit_task_event=lambda **_kwargs: _as_async_none(),
        update_zone_workflow_phase=lambda **_kwargs: _as_async_none(),
        check_required_nodes_online=lambda *_args, **_kwargs: _as_async_value({"missing_types": []}),
        read_level_switch=lambda **_kwargs: _as_async_value(
            {
                "has_level": True,
                "is_triggered": False,
                "is_stale": False,
                "sensor_id": 1,
                "sensor_label": "level_clean_max",
                "level": 0.0,
                "sample_ts": now.isoformat(),
                "sample_age_sec": 0.0,
            }
        ),
        start_two_tank_clean_fill=_start_two_tank_clean_fill,
        telemetry_freshness_enforce=lambda: False,
        safety_config=TwoTankSafetyConfig(
            pump_interlock=False,
            stop_confirmation_required=False,
            irr_state_validation=False,
        ),
    )

    result = await execute_two_tank_startup_workflow_core(
        deps,
        payload={"workflow": "startup", "topology": "two_tank_drip_substrate_trays"},
        context={"task_id": "tt-resume-2"},
        decision=_decision(),
    )

    assert clean_fill_started is True
    assert result["mode"] == "two_tank_clean_fill_in_progress"
    assert result["workflow"] == "startup"


async def _as_async_none() -> None:
    return None


async def _as_async_value(value: Any) -> Any:
    return value
