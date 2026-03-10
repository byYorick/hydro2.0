from __future__ import annotations

from types import SimpleNamespace

from ae3lite.domain.services.two_tank_runtime_spec import resolve_two_tank_runtime


def _snapshot(*, correction: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {
                "irr_state_wait_timeout_sec": 4.5,
            },
            "correction": correction,
        },
        targets={},
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
