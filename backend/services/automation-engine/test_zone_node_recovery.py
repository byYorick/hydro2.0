from __future__ import annotations

import pytest

from services.resilience_contract import REASON_REQUIRED_NODES_RECOVERED
from services.zone_node_recovery import evaluate_required_nodes_recovery_gate


class _Logger:
    def debug(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_required_nodes_recovery_gate_cold_start_probes_resolved_once():
    recovered_calls = []

    async def check_required_nodes_online_fn(_zone_id, _required_types):
        return {
            "required_types": ["ec", "ph"],
            "online_counts": {"ec": 1, "ph": 1},
            "missing_types": [],
        }

    async def emit_required_nodes_offline_signal_fn(**_kwargs):
        raise AssertionError("unexpected offline signal")

    async def emit_required_nodes_recovered_signal_fn(**kwargs):
        recovered_calls.append(dict(kwargs))

    zone_state = {
        "required_nodes_offline_active": None,
        "required_nodes_offline_missing_types": [],
        "required_nodes_offline_required_types": [],
        "required_nodes_offline_since": None,
        "last_required_nodes_offline_report_at": None,
    }

    ok = await evaluate_required_nodes_recovery_gate(
        zone_id=6,
        capabilities={"ph_control": True, "ec_control": True},
        zone_state=zone_state,
        check_required_nodes_online_fn=check_required_nodes_online_fn,
        emit_required_nodes_offline_signal_fn=emit_required_nodes_offline_signal_fn,
        emit_required_nodes_recovered_signal_fn=emit_required_nodes_recovered_signal_fn,
        utcnow_fn=lambda: None,
        throttle_seconds=60,
        logger=_Logger(),
    )

    assert ok is True
    assert len(recovered_calls) == 1
    assert recovered_calls[0]["reason_code"] == REASON_REQUIRED_NODES_RECOVERED
    assert zone_state["required_nodes_offline_active"] is False
    assert zone_state["required_nodes_offline_missing_types"] == []
    assert zone_state["last_required_nodes_offline_report_at"] is None

    recovered_calls.clear()
    ok = await evaluate_required_nodes_recovery_gate(
        zone_id=6,
        capabilities={"ph_control": True, "ec_control": True},
        zone_state=zone_state,
        check_required_nodes_online_fn=check_required_nodes_online_fn,
        emit_required_nodes_offline_signal_fn=emit_required_nodes_offline_signal_fn,
        emit_required_nodes_recovered_signal_fn=emit_required_nodes_recovered_signal_fn,
        utcnow_fn=lambda: None,
        throttle_seconds=60,
        logger=_Logger(),
    )
    assert ok is True
    assert recovered_calls == []
