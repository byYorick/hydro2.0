from __future__ import annotations

from types import SimpleNamespace

import pytest

from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.two_tank_runtime_spec import resolve_two_tank_runtime


def _snapshot(
    *,
    correction: dict[str, object],
    startup: dict[str, object] | None = None,
    correction_config: dict[str, object] | None = None,
    prepare_tolerance: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        workflow_phase="tank_filling",
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {
                "irr_state_wait_timeout_sec": 4.5,
                **(startup or {}),
            },
            "prepare_tolerance": dict(prepare_tolerance or {}),
            "correction": correction,
        },
        targets={},
        correction_config=correction_config,
    )


def test_resolve_target_bound_handles_zero_value() -> None:
    """ec_min=0.0 must NOT be ignored (falsy value != absent value)."""
    runtime = resolve_two_tank_runtime(
        _snapshot(correction={})
    )
    # Override snapshot to include explicit zero bounds
    import types
    snap = types.SimpleNamespace(
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "ec_min": 0.0,
            "ph_min": 0.0,
            "startup": {},
            "correction": {},
        },
        targets={},
    )
    runtime = resolve_two_tank_runtime(snap)
    # 0.0 is a valid bound and must be preserved (not replaced by fallback=target)
    assert runtime["target_ec_min"] == 0.0
    assert runtime["target_ph_min"] == 0.0


def test_resolve_two_tank_runtime_uses_split_retry_contract() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={
                "max_ec_correction_attempts": 3,
                "max_ph_correction_attempts": 4,
                "prepare_recirculation_max_attempts": 2,
                "prepare_recirculation_max_correction_attempts": 11,
            }
        )
    )

    assert runtime["correction"]["max_ec_correction_attempts"] == 3
    assert runtime["correction"]["max_ph_correction_attempts"] == 4
    assert runtime["correction"]["prepare_recirculation_max_attempts"] == 2
    assert runtime["correction"]["prepare_recirculation_max_correction_attempts"] == 11
    assert runtime["irr_state_wait_timeout_sec"] == 4.5


def test_resolve_two_tank_runtime_accepts_timeout_equal_to_mix_plus_stabilization() -> None:
    """timeout == mix_wait + stabilization is the exact minimum — should pass.

    Note: prepare_recirculation_timeout_sec has a hard minimum of 30s enforced by
    _resolve_int(..., minimum=30). To make mix+stab == timeout, we use mix=25, stab=10
    so that needed=35 == timeout=35.
    """
    import types
    snap = types.SimpleNamespace(
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {
                "prepare_recirculation_timeout_sec": 35,  # exactly mix(25) + stab(10)
            },
            "correction": {
                "ec_mix_wait_sec": 25,
                "stabilization_sec": 10,
            },
        },
        targets={},
    )
    runtime = resolve_two_tank_runtime(snap)
    assert runtime["prepare_recirculation_timeout_sec"] == 35


def test_resolve_two_tank_runtime_raises_when_timeout_less_than_mix_plus_stabilization() -> None:
    """timeout < mix_wait + stabilization is provably impossible — must raise PlannerConfigurationError.

    After _resolve_int clamp, timeout=30 (minimum). mix=25, stab=10 → needed=35 > 30 → error.
    """
    import types
    snap = types.SimpleNamespace(
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {
                "prepare_recirculation_timeout_sec": 30,  # clamped to 30, below mix(25)+stab(10)=35
            },
            "correction": {
                "ec_mix_wait_sec": 25,
                "stabilization_sec": 10,
            },
        },
        targets={},
    )
    with pytest.raises(PlannerConfigurationError, match="prepare_recirculation_timeout_sec"):
        resolve_two_tank_runtime(snap)


def test_resolve_two_tank_runtime_uses_phase_aware_correction_config() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={
                "ec_mix_wait_sec": 120,
                "ph_mix_wait_sec": 60,
                "stabilization_sec": 60,
            },
            correction_config={
                "base": {
                    "timing": {
                        "ec_mix_wait_sec": 45,
                        "ph_mix_wait_sec": 30,
                        "stabilization_sec": 20,
                    },
                    "retry": {
                        "prepare_recirculation_timeout_sec": 600,
                    },
                },
                "phases": {
                    "solution_fill": {
                        "timing": {
                            "ec_mix_wait_sec": 20,
                            "ph_mix_wait_sec": 20,
                            "stabilization_sec": 10,
                        }
                    },
                    "tank_recirc": {
                        "timing": {
                            "ec_mix_wait_sec": 15,
                            "ph_mix_wait_sec": 15,
                            "stabilization_sec": 10,
                        },
                        "retry": {
                            "prepare_recirculation_timeout_sec": 360,
                        },
                    },
                },
                "meta": {
                    "phase_overrides": {
                        "solution_fill": {
                            "timing": {
                                "ec_mix_wait_sec": 20,
                                "ph_mix_wait_sec": 20,
                                "stabilization_sec": 10,
                            },
                        },
                        "tank_recirc": {
                            "timing": {
                                "ec_mix_wait_sec": 15,
                                "ph_mix_wait_sec": 15,
                                "stabilization_sec": 10,
                            },
                            "retry": {
                                "prepare_recirculation_timeout_sec": 360,
                            },
                        },
                    }
                },
            },
        )
    )

    assert runtime["correction"]["ec_mix_wait_sec"] == 20
    assert runtime["correction"]["ph_mix_wait_sec"] == 20
    assert runtime["correction_by_phase"]["tank_recirc"]["ec_mix_wait_sec"] == 15
    assert runtime["correction_by_phase"]["tank_recirc"]["ph_mix_wait_sec"] == 15
    assert runtime["prepare_recirculation_timeout_sec"] == 360


def test_resolve_two_tank_runtime_keeps_startup_prepare_timeout_when_phase_is_not_overridden() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={"ec_mix_wait_sec": 10, "stabilization_sec": 0},
            startup={"prepare_recirculation_timeout_sec": 30},
            correction_config={
                "base": {
                    "retry": {
                        "prepare_recirculation_timeout_sec": 600,
                    }
                },
                "phases": {
                    "tank_recirc": {
                        "retry": {
                            "prepare_recirculation_timeout_sec": 600,
                        }
                    }
                },
            },
        )
    )

    assert runtime["prepare_recirculation_timeout_sec"] == 30
