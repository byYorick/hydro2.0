"""Tests for required-node online recovery policy."""

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from services.zone_node_recovery import (
    derive_required_node_types,
    evaluate_required_nodes_recovery_gate,
)


def test_derive_required_node_types_maps_capabilities():
    required = derive_required_node_types(
        {
            "ph_control": True,
            "ec_control": True,
            "climate_control": True,
            "light_control": True,
            "irrigation_control": True,
            "recirculation": True,
        }
    )
    assert required == ["climate", "ec", "irrig", "light", "ph"]


@pytest.mark.asyncio
async def test_evaluate_required_nodes_recovery_gate_blocks_on_missing_nodes():
    zone_state = {}
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async def _check_required(_zone_id, _required_types):
        return {"online_counts": {"ec": 1}, "missing_types": ["ph"]}

    offline_signal = AsyncMock()
    recovered_signal = AsyncMock()

    ok = await evaluate_required_nodes_recovery_gate(
        zone_id=11,
        capabilities={"ph_control": True, "ec_control": True},
        zone_state=zone_state,
        check_required_nodes_online_fn=_check_required,
        emit_required_nodes_offline_signal_fn=offline_signal,
        emit_required_nodes_recovered_signal_fn=recovered_signal,
        utcnow_fn=lambda: now,
        throttle_seconds=120,
        logger=Mock(),
    )

    assert ok is False
    assert zone_state["required_nodes_offline_active"] is True
    assert zone_state["required_nodes_offline_missing_types"] == ["ph"]
    offline_signal.assert_awaited_once()
    recovered_signal.assert_not_awaited()


@pytest.mark.asyncio
async def test_evaluate_required_nodes_recovery_gate_emits_recovered_when_restored():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    zone_state = {
        "required_nodes_offline_active": True,
        "required_nodes_offline_missing_types": ["ph"],
        "required_nodes_offline_required_types": ["ph", "ec"],
        "required_nodes_offline_since": now - timedelta(minutes=5),
        "last_required_nodes_offline_report_at": now - timedelta(minutes=2),
    }

    async def _check_required(_zone_id, _required_types):
        return {"online_counts": {"ec": 1, "ph": 1}, "missing_types": []}

    offline_signal = AsyncMock()
    recovered_signal = AsyncMock()

    ok = await evaluate_required_nodes_recovery_gate(
        zone_id=12,
        capabilities={"ph_control": True, "ec_control": True},
        zone_state=zone_state,
        check_required_nodes_online_fn=_check_required,
        emit_required_nodes_offline_signal_fn=offline_signal,
        emit_required_nodes_recovered_signal_fn=recovered_signal,
        utcnow_fn=lambda: now,
        throttle_seconds=120,
        logger=Mock(),
    )

    assert ok is True
    assert zone_state["required_nodes_offline_active"] is False
    assert zone_state["required_nodes_offline_missing_types"] == []
    recovered_signal.assert_awaited_once()
    offline_signal.assert_not_awaited()


@pytest.mark.asyncio
async def test_evaluate_required_nodes_recovery_gate_throttles_repeated_offline_signal():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    zone_state = {
        "required_nodes_offline_active": True,
        "required_nodes_offline_missing_types": ["ph"],
        "required_nodes_offline_required_types": ["ph", "ec"],
        "required_nodes_offline_since": now - timedelta(minutes=3),
        "last_required_nodes_offline_report_at": now - timedelta(seconds=30),
    }

    async def _check_required(_zone_id, _required_types):
        return {"online_counts": {"ec": 1}, "missing_types": ["ph"]}

    offline_signal = AsyncMock()
    recovered_signal = AsyncMock()

    ok = await evaluate_required_nodes_recovery_gate(
        zone_id=13,
        capabilities={"ph_control": True, "ec_control": True},
        zone_state=zone_state,
        check_required_nodes_online_fn=_check_required,
        emit_required_nodes_offline_signal_fn=offline_signal,
        emit_required_nodes_recovered_signal_fn=recovered_signal,
        utcnow_fn=lambda: now,
        throttle_seconds=120,
        logger=Mock(),
    )

    assert ok is False
    offline_signal.assert_not_awaited()
    recovered_signal.assert_not_awaited()


@pytest.mark.asyncio
async def test_evaluate_required_nodes_recovery_gate_emits_when_missing_set_changed():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    zone_state = {
        "required_nodes_offline_active": True,
        "required_nodes_offline_missing_types": ["ph"],
        "required_nodes_offline_required_types": ["ph", "ec", "climate"],
        "required_nodes_offline_since": now - timedelta(minutes=3),
        "last_required_nodes_offline_report_at": now - timedelta(seconds=30),
    }

    async def _check_required(_zone_id, _required_types):
        return {"online_counts": {"ec": 1}, "missing_types": ["ph", "climate"]}

    offline_signal = AsyncMock()
    recovered_signal = AsyncMock()

    ok = await evaluate_required_nodes_recovery_gate(
        zone_id=14,
        capabilities={"ph_control": True, "ec_control": True, "climate_control": True},
        zone_state=zone_state,
        check_required_nodes_online_fn=_check_required,
        emit_required_nodes_offline_signal_fn=offline_signal,
        emit_required_nodes_recovered_signal_fn=recovered_signal,
        utcnow_fn=lambda: now,
        throttle_seconds=120,
        logger=Mock(),
    )

    assert ok is False
    offline_signal.assert_awaited_once()
    recovered_signal.assert_not_awaited()
