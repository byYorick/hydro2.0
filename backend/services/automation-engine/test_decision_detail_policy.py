"""Unit tests for decision detail policy helpers."""

from domain.models.decision_models import DecisionOutcome
from domain.policies.decision_detail_policy import to_optional_float, with_decision_details


def test_to_optional_float_filters_non_numeric_and_non_finite():
    assert to_optional_float("bad") is None
    assert to_optional_float("nan") is None
    assert to_optional_float("1.25") == 1.25


def test_with_decision_details_merges_safety_flags_and_nested_dicts():
    decision = DecisionOutcome(
        action_required=True,
        decision="run",
        reason_code="r",
        reason="r",
        details={"safety_flags": ["a"], "climate_fallback": {"active": False}},
    )
    merged = with_decision_details(
        decision,
        {
            "safety_flags": ["b", "a"],
            "climate_fallback": {"reasons": ["x"]},
        },
    )
    assert merged.details["safety_flags"] == ["a", "b"]
    assert merged.details["climate_fallback"] == {"active": False, "reasons": ["x"]}
