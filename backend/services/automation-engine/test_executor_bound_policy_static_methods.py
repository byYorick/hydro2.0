from __future__ import annotations

import logging

from executor.executor_bound_policy_static_methods import bound_validate_phase_transition


def test_bound_validate_phase_transition_allows_ready_to_tank_filling(caplog):
    logger = logging.getLogger("test_bound_validate_phase_transition")
    with caplog.at_level(logging.WARNING):
        ok = bound_validate_phase_transition(
            from_phase="ready",
            to_phase="tank_filling",
            zone_id=7,
            logger=logger,
        )

    assert ok is True
    assert "invalid workflow phase transition" not in caplog.text


def test_bound_validate_phase_transition_keeps_policy_for_invalid_transition(caplog):
    logger = logging.getLogger("test_bound_validate_phase_transition")
    with caplog.at_level(logging.WARNING):
        ok = bound_validate_phase_transition(
            from_phase="idle",
            to_phase="irrigating",
            zone_id=8,
            logger=logger,
        )

    assert ok is False
    assert "invalid workflow phase transition idle -> irrigating" in caplog.text
