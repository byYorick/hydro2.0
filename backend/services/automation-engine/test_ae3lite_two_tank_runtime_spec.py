from __future__ import annotations

from types import SimpleNamespace

import pytest

from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.two_tank_runtime_spec import resolve_two_tank_runtime


def _minimal_zone_correction_config() -> dict[str, object]:
    return {
        "base": {
            "timing": {},
            "retry": {},
            "dosing": {},
        },
        "phases": {
            "solution_fill": {},
            "tank_recirc": {},
            "irrigation": {},
        },
        "meta": {},
    }


def _snapshot(
    *,
    correction: dict[str, object],
    startup: dict[str, object] | None = None,
    correction_config: dict[str, object] | None = None,
    prepare_tolerance: dict[str, object] | None = None,
    process_calibrations: dict[str, object] | None = None,
) -> SimpleNamespace:
    default_process_calibrations = {
        "solution_fill": {"transport_delay_sec": 10, "settle_sec": 10},
        "tank_recirc": {"transport_delay_sec": 10, "settle_sec": 10},
        "irrigation": {"transport_delay_sec": 10, "settle_sec": 10},
    }
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
        process_calibrations=process_calibrations if process_calibrations is not None else default_process_calibrations,
        correction_config=correction_config if correction_config is not None else _minimal_zone_correction_config(),
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
        process_calibrations={
            "tank_recirc": {
                "transport_delay_sec": 10,
                "settle_sec": 10,
            }
        },
        correction_config=_minimal_zone_correction_config(),
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


def test_resolve_two_tank_runtime_preserves_explicit_prepare_recirculation_attempt_cap() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={
                "prepare_recirculation_max_correction_attempts": 200,
            }
        )
    )

    assert runtime["correction"]["prepare_recirculation_max_correction_attempts"] == 200


def test_resolve_two_tank_runtime_clamps_correction_attempt_caps_to_contract_maximum() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={
                "max_ec_correction_attempts": 999,
                "max_ph_correction_attempts": 999,
                "prepare_recirculation_max_correction_attempts": 999,
            }
        )
    )

    assert runtime["correction"]["max_ec_correction_attempts"] == 500
    assert runtime["correction"]["max_ph_correction_attempts"] == 500
    assert runtime["correction"]["prepare_recirculation_max_correction_attempts"] == 500


def test_resolve_two_tank_runtime_accepts_timeout_equal_to_observe_window_plus_stabilization() -> None:
    """timeout == observe_window + stabilization is the exact minimum — should pass."""
    import types
    snap = types.SimpleNamespace(
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {
                "prepare_recirculation_timeout_sec": 35,
            },
            "correction": {
                "stabilization_sec": 10,
            },
        },
        targets={},
        correction_config=_minimal_zone_correction_config(),
        process_calibrations={
            "tank_recirc": {
                "transport_delay_sec": 15,
                "settle_sec": 10,
            }
        },
    )
    runtime = resolve_two_tank_runtime(snap)
    assert runtime["prepare_recirculation_timeout_sec"] == 35


def test_resolve_two_tank_runtime_raises_when_timeout_less_than_observe_window_plus_stabilization() -> None:
    """timeout < observe_window + stabilization is provably impossible — must raise PlannerConfigurationError."""
    import types
    snap = types.SimpleNamespace(
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {
                "prepare_recirculation_timeout_sec": 30,
            },
            "correction": {
                "stabilization_sec": 10,
            },
        },
        targets={},
        correction_config=_minimal_zone_correction_config(),
        process_calibrations={
            "tank_recirc": {
                "transport_delay_sec": 15,
                "settle_sec": 10,
            }
        },
    )
    with pytest.raises(PlannerConfigurationError, match="prepare_recirculation_timeout_sec"):
        resolve_two_tank_runtime(snap)


def test_resolve_two_tank_runtime_prefers_process_hold_window_for_prepare_recirculation_validation() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={
                "stabilization_sec": 10,
            },
            startup={
                "prepare_recirculation_timeout_sec": 55,
            },
            process_calibrations={
                "tank_recirc": {
                    "transport_delay_sec": 25,
                    "settle_sec": 20,
                }
            },
        )
    )

    assert runtime["prepare_recirculation_timeout_sec"] == 55


def test_resolve_two_tank_runtime_raises_when_timeout_less_than_process_hold_window() -> None:
    with pytest.raises(PlannerConfigurationError, match="observe_window_sec"):
        resolve_two_tank_runtime(
            _snapshot(
                correction={
                    "stabilization_sec": 10,
                },
                startup={
                    "prepare_recirculation_timeout_sec": 50,
                },
                process_calibrations={
                    "tank_recirc": {
                        "transport_delay_sec": 25,
                        "settle_sec": 20,
                    }
                },
            )
        )


def test_resolve_two_tank_runtime_raises_when_zone_correction_config_missing() -> None:
    snap = SimpleNamespace(
        zone_id=188,
        workflow_phase="tank_filling",
        diagnostics_execution={
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
            "required_node_types": ["irrig"],
            "target_ph": 5.8,
            "target_ec": 2.2,
            "startup": {},
            "correction": {},
        },
        targets={},
        correction_config=None,
    )
    with pytest.raises(PlannerConfigurationError) as exc_info:
        resolve_two_tank_runtime(snap)
    assert getattr(exc_info.value, "code", "") == "zone_correction_config_missing_critical"


def test_resolve_two_tank_runtime_uses_phase_aware_correction_config() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={
                "stabilization_sec": 60,
            },
            correction_config={
                "base": {
                    "timing": {
                        "stabilization_sec": 20,
                    },
                    "retry": {
                        "prepare_recirculation_timeout_sec": 600,
                    },
                },
                "phases": {
                    "solution_fill": {
                        "timing": {
                            "stabilization_sec": 10,
                        }
                    },
                    "tank_recirc": {
                        "timing": {
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
                                "stabilization_sec": 10,
                            },
                        },
                        "tank_recirc": {
                            "timing": {
                                "stabilization_sec": 10,
                            },
                            "retry": {
                                "prepare_recirculation_timeout_sec": 360,
                            },
                        },
                    }
                },
            },
            process_calibrations={
                "solution_fill": {"transport_delay_sec": 10, "settle_sec": 10},
                "tank_recirc": {"transport_delay_sec": 15, "settle_sec": 15},
                "irrigation": {"transport_delay_sec": 20, "settle_sec": 20},
            },
        )
    )

    assert runtime["correction"]["stabilization_sec"] == 10
    assert runtime["correction_by_phase"]["tank_recirc"]["stabilization_sec"] == 10
    assert "ec_mix_wait_sec" not in runtime["correction"]
    assert "ph_mix_wait_sec" not in runtime["correction_by_phase"]["tank_recirc"]
    assert runtime["prepare_recirculation_timeout_sec"] == 360


def test_resolve_two_tank_runtime_prefers_correction_config_over_execution_defaults() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={
                "max_ec_correction_attempts": 8,
                "max_ph_correction_attempts": 8,
            },
            startup={
                "solution_fill_timeout_sec": 240,
                "prepare_recirculation_timeout_sec": 30,
                "level_poll_interval_sec": 5,
            },
            correction_config={
                "base": {
                    "timing": {
                        "level_poll_interval_sec": 20,
                    },
                    "retry": {
                        "max_ec_correction_attempts": 5,
                        "max_ph_correction_attempts": 5,
                        "prepare_recirculation_timeout_sec": 600,
                    },
                    "runtime": {
                        "solution_fill_timeout_sec": 900,
                    },
                },
                "phases": {
                    "solution_fill": {"timing": {}},
                    "tank_recirc": {},
                    "irrigation": {},
                },
                "meta": {},
            },
            process_calibrations={
                "solution_fill": {"transport_delay_sec": 10, "settle_sec": 10},
                "tank_recirc": {"transport_delay_sec": 10, "settle_sec": 10},
                "irrigation": {"transport_delay_sec": 10, "settle_sec": 10},
            },
        )
    )

    assert "ec_mix_wait_sec" not in runtime["correction"]
    assert "ph_mix_wait_sec" not in runtime["correction"]
    assert runtime["correction"]["max_ec_correction_attempts"] == 5
    assert runtime["correction"]["max_ph_correction_attempts"] == 5
    assert runtime["solution_fill_timeout_sec"] == 900
    assert runtime["prepare_recirculation_timeout_sec"] == 600
    assert runtime["level_poll_interval_sec"] == 20


def test_resolve_two_tank_runtime_prefers_correction_config_prepare_timeout_over_startup_default() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={"stabilization_sec": 0},
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
            process_calibrations={
                "tank_recirc": {
                    "transport_delay_sec": 10,
                    "settle_sec": 10,
                }
            },
        )
    )

    assert runtime["prepare_recirculation_timeout_sec"] == 600


def test_resolve_two_tank_runtime_exposes_process_calibrations_to_runtime() -> None:
    runtime = resolve_two_tank_runtime(
        _snapshot(
            correction={"stabilization_sec": 0},
            process_calibrations={
                "solution_fill": {
                    "ec_gain_per_ml": 0.25,
                    "transport_delay_sec": 15,
                },
                "tank_recirc": {
                    "ph_down_gain_per_ml": 0.12,
                    "transport_delay_sec": 15,
                    "settle_sec": 45,
                },
            },
        )
    )

    assert runtime["process_calibrations"]["solution_fill"]["ec_gain_per_ml"] == 0.25
    assert runtime["process_calibrations"]["tank_recirc"]["settle_sec"] == 45


def test_resolve_two_tank_runtime_requires_process_hold_window_for_prepare_recirculation() -> None:
    with pytest.raises(PlannerConfigurationError, match="transport_delay_sec and settle_sec"):
        resolve_two_tank_runtime(
            _snapshot(
                correction={"stabilization_sec": 5},
                startup={"prepare_recirculation_timeout_sec": 60},
                process_calibrations={
                    "tank_recirc": {
                        "transport_delay_sec": 15,
                    }
                },
            )
        )
