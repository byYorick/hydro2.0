"""Unit-тесты deferred hardware verify после correction interrupt."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.application.services.correction_interrupt_safety import (
    CorrectionInterruptPendingCheck,
    build_pending_check_from_task,
    evaluate_correction_interrupt_safety,
    flow_snapshot_is_safe,
    is_dose_correction_step,
)

NOW = datetime(2026, 7, 22, 5, 20, tzinfo=timezone.utc)


def test_is_dose_correction_step() -> None:
    assert is_dose_correction_step("corr_dose_ec") is True
    assert is_dose_correction_step("corr_wait_ph") is True
    assert is_dose_correction_step("corr_check") is False


def test_flow_snapshot_is_safe_for_irrigation_check() -> None:
    assert flow_snapshot_is_safe(
        stage="irrigation_check",
        snapshot={
            "valve_solution_supply": False,
            "valve_irrigation": False,
            "pump_main": False,
        },
    )
    assert not flow_snapshot_is_safe(
        stage="irrigation_check",
        snapshot={
            "valve_solution_supply": False,
            "valve_irrigation": True,
            "pump_main": False,
        },
    )


def test_build_pending_check_from_task() -> None:
    task = SimpleNamespace(
        id=2,
        zone_id=1,
        task_type="irrigation_start",
        topology="two_tank_drip_substrate_trays",
        current_stage="irrigation_check",
        workflow_phase="irrigating",
        irrigation_mode="normal",
        irrigation_requested_duration_sec=300,
        intent_id=8,
        correction=SimpleNamespace(corr_step="corr_dose_ec"),
    )
    check = build_pending_check_from_task(task=task, now=NOW, verify_grace_sec=60)
    assert check is not None
    assert check.task_id == 2
    assert check.deadline_at == NOW + timedelta(seconds=60)
    assert check.corr_step == "corr_dose_ec"


@pytest.mark.asyncio
async def test_evaluate_safe_when_nodes_online_and_off_snapshot(monkeypatch) -> None:
    check = CorrectionInterruptPendingCheck(
        zone_id=1,
        task_id=2,
        task_type="irrigation_start",
        topology="two_tank_drip_substrate_trays",
        stage="irrigation_check",
        corr_step="corr_dose_ec",
        workflow_phase="irrigating",
        recovery_source="startup_recovery",
        deadline_at=NOW + timedelta(seconds=60),
    )
    runtime_monitor = SimpleNamespace(
        read_latest_irr_state=AsyncMock(
            return_value={
                "has_snapshot": True,
                "is_stale": False,
                "snapshot": {
                    "valve_solution_supply": False,
                    "valve_irrigation": False,
                    "pump_main": False,
                },
            }
        )
    )

    async def _no_active(*, zone_id: int) -> bool:
        return False

    async def _nodes_ok(*, zone_id: int, required_types=()):
        return True, ()

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.zone_has_active_ae_task",
        _no_active,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.required_nodes_online",
        _nodes_ok,
    )

    verdict = await evaluate_correction_interrupt_safety(
        check=check,
        now=NOW,
        runtime_monitor=runtime_monitor,
    )
    assert verdict.status == "safe"
    assert verdict.reason == "irr_state_off_confirmed"


@pytest.mark.asyncio
async def test_evaluate_pending_while_waiting_nodes(monkeypatch) -> None:
    check = CorrectionInterruptPendingCheck(
        zone_id=1,
        task_id=2,
        task_type="irrigation_start",
        topology="two_tank_drip_substrate_trays",
        stage="irrigation_check",
        corr_step="corr_dose_ec",
        workflow_phase="irrigating",
        recovery_source="startup_recovery",
        deadline_at=NOW + timedelta(seconds=60),
    )
    runtime_monitor = SimpleNamespace(read_latest_irr_state=AsyncMock())

    async def _no_active(*, zone_id: int) -> bool:
        return False

    async def _nodes_offline(*, zone_id: int, required_types=()):
        return False, ("irrig",)

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.zone_has_active_ae_task",
        _no_active,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.required_nodes_online",
        _nodes_offline,
    )

    verdict = await evaluate_correction_interrupt_safety(
        check=check,
        now=NOW,
        runtime_monitor=runtime_monitor,
    )
    assert verdict.status == "pending"
    assert "waiting_nodes" in verdict.reason


@pytest.mark.asyncio
async def test_evaluate_safe_when_ready_and_stale_snapshot(monkeypatch) -> None:
    """После complete_ready snapshot часто stale с mid-recirc pump_main=true — не escalate."""
    check = CorrectionInterruptPendingCheck(
        zone_id=1,
        task_id=2,
        task_type="irrigation_start",
        topology="two_tank_drip_substrate_trays",
        stage="irrigation_check",
        corr_step="corr_dose_ec",
        workflow_phase="irrigating",
        recovery_source="startup_recovery",
        deadline_at=NOW + timedelta(seconds=60),
    )
    runtime_monitor = SimpleNamespace(
        read_latest_irr_state=AsyncMock(
            return_value={
                "has_snapshot": True,
                "is_stale": True,
                "snapshot": {"pump_main": True, "valve_irrigation": True},
            }
        )
    )

    async def _no_active(*, zone_id: int) -> bool:
        return False

    async def _nodes_ok(*, zone_id: int, required_types=()):
        return True, ()

    async def _ready(*, zone_id: int):
        return "ready"

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.zone_has_active_ae_task",
        _no_active,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.required_nodes_online",
        _nodes_ok,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.read_workflow_phase",
        _ready,
    )

    verdict = await evaluate_correction_interrupt_safety(
        check=check,
        now=NOW,
        runtime_monitor=runtime_monitor,
    )
    assert verdict.status == "safe"
    assert "ready" in verdict.reason


@pytest.mark.asyncio
async def test_evaluate_unsafe_after_grace_when_actuators_on(monkeypatch) -> None:
    check = CorrectionInterruptPendingCheck(
        zone_id=1,
        task_id=2,
        task_type="irrigation_start",
        topology="two_tank_drip_substrate_trays",
        stage="irrigation_check",
        corr_step="corr_dose_ec",
        workflow_phase="irrigating",
        recovery_source="startup_recovery",
        deadline_at=NOW - timedelta(seconds=1),
    )
    runtime_monitor = SimpleNamespace(
        read_latest_irr_state=AsyncMock(
            return_value={
                "has_snapshot": True,
                "is_stale": False,
                "snapshot": {
                    "valve_solution_supply": False,
                    "valve_irrigation": True,
                    "pump_main": True,
                },
            }
        )
    )

    async def _no_active(*, zone_id: int) -> bool:
        return False

    async def _nodes_ok(*, zone_id: int, required_types=()):
        return True, ()

    async def _irrigating(*, zone_id: int):
        return "irrigating"

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.zone_has_active_ae_task",
        _no_active,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.required_nodes_online",
        _nodes_ok,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.read_workflow_phase",
        _irrigating,
    )

    verdict = await evaluate_correction_interrupt_safety(
        check=check,
        now=NOW,
        runtime_monitor=runtime_monitor,
    )
    assert verdict.status == "unsafe"
    assert verdict.reason == "irr_state_actuators_active_after_grace"
