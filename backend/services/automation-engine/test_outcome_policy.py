"""Unit tests for outcome policy helpers."""

from domain.policies.outcome_policy import (
    build_decision_retry_correlation_id,
    extract_two_tank_chemistry_orchestration,
)


def test_build_decision_retry_correlation_id_uses_parent_when_present():
    value = build_decision_retry_correlation_id(
        zone_id=1,
        task_type="irrigation",
        parent_correlation_id="parent-1",
        retry_attempt=2,
        unique_suffix_factory=lambda: "abcdef1234",
    )
    assert value == "parent-1:retry2:abcdef1234"


def test_extract_two_tank_chemistry_orchestration_uses_default_when_missing():
    orchestration = extract_two_tank_chemistry_orchestration(payload={})
    assert orchestration["irrigation_online_sequence"] == ["ec", "ph"]
