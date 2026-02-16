"""Unit tests for application.ventilation_climate_guards helpers."""

import asyncio
from unittest.mock import AsyncMock

from domain.models.decision_models import DecisionOutcome
from application.ventilation_climate_guards import apply_ventilation_climate_guards


def test_apply_ventilation_climate_guards_keeps_non_action_decision():
    decision = DecisionOutcome(action_required=False, decision="skip", reason_code="no_action", reason="no_action")
    read_metric = AsyncMock()

    result = asyncio.run(
        apply_ventilation_climate_guards(
            zone_id=1,
            payload={"config": {"execution": {"limits": {"strong_wind_mps": 10.0}}}},
            decision=decision,
            read_latest_metric_fn=read_metric,
            to_optional_float_fn=lambda raw: float(raw) if raw is not None else None,
            with_decision_details_fn=lambda outcome, _: outcome,
            wind_blocked_reason="wind_blocked",
            outside_temp_blocked_reason="outside_temp_blocked",
        )
    )

    assert result == decision
    read_metric.assert_not_awaited()


def test_apply_ventilation_climate_guards_blocks_on_wind_threshold():
    decision = DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok")
    read_metric = AsyncMock(return_value={"has_value": True, "is_stale": False, "value": 12.5})

    result = asyncio.run(
        apply_ventilation_climate_guards(
            zone_id=3,
            payload={"config": {"execution": {"limits": {"strong_wind_mps": 10.0}}}},
            decision=decision,
            read_latest_metric_fn=read_metric,
            to_optional_float_fn=lambda raw: float(raw) if raw is not None else None,
            with_decision_details_fn=lambda outcome, _: outcome,
            wind_blocked_reason="wind_blocked",
            outside_temp_blocked_reason="outside_temp_blocked",
        )
    )

    assert result.action_required is False
    assert result.reason_code == "wind_blocked"


def test_apply_ventilation_climate_guards_blocks_on_outside_temp_threshold():
    decision = DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok")

    async def _read_metric(*, zone_id: int, sensor_type: str):
        assert zone_id == 7
        if sensor_type == "OUTSIDE_TEMP":
            return {"has_value": True, "is_stale": False, "value": 2.0}
        return {"has_value": True, "is_stale": False, "value": 1.0}

    result = asyncio.run(
        apply_ventilation_climate_guards(
            zone_id=7,
            payload={"config": {"execution": {"limits": {"low_outside_temp_c": 5.0}}}},
            decision=decision,
            read_latest_metric_fn=_read_metric,
            to_optional_float_fn=lambda raw: float(raw) if raw is not None else None,
            with_decision_details_fn=lambda outcome, _: outcome,
            wind_blocked_reason="wind_blocked",
            outside_temp_blocked_reason="outside_temp_blocked",
        )
    )

    assert result.action_required is False
    assert result.reason_code == "outside_temp_blocked"


def test_apply_ventilation_climate_guards_marks_fallback_when_metrics_unavailable():
    decision = DecisionOutcome(
        action_required=True,
        decision="run",
        reason_code="target_reached",
        reason="target_reached",
        details={"existing": True},
    )
    read_metric = AsyncMock(return_value={"has_value": False, "is_stale": False, "value": None})

    def _with_details(outcome: DecisionOutcome, patch):
        merged = dict(outcome.details or {})
        merged.update(patch)
        return DecisionOutcome(
            action_required=outcome.action_required,
            decision=outcome.decision,
            reason_code=outcome.reason_code,
            reason=outcome.reason,
            details=merged,
        )

    result = asyncio.run(
        apply_ventilation_climate_guards(
            zone_id=1,
            payload={
                "config": {
                    "execution": {
                        "limits": {
                            "strong_wind_mps": 10.0,
                            "low_outside_temp_c": 8.0,
                        }
                    }
                }
            },
            decision=decision,
            read_latest_metric_fn=read_metric,
            to_optional_float_fn=lambda raw: float(raw) if raw is not None else None,
            with_decision_details_fn=_with_details,
            wind_blocked_reason="wind_blocked",
            outside_temp_blocked_reason="outside_temp_blocked",
        )
    )

    assert result.action_required is True
    assert result.reason_code == "climate_external_nodes_unavailable"
    assert result.details is not None
    assert result.details["climate_fallback"]["active"] is True
    assert "climate_external_nodes_unavailable" in result.details["safety_flags"]
