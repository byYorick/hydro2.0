"""Unit tests for PH/EC target evaluation policy."""

import pytest

from domain.policies.target_evaluation_policy import evaluate_ph_ec_targets, is_value_within_pct


def test_is_value_within_pct_handles_non_positive_target_with_absolute_floor():
    assert is_value_within_pct(value=0.05, target=0.0, tolerance_pct=5.0) is True
    assert is_value_within_pct(value=0.2, target=0.0, tolerance_pct=5.0) is False


@pytest.mark.asyncio
async def test_evaluate_ph_ec_targets_returns_no_data_when_metric_missing():
    async def _read_metric(*, zone_id, sensor_type):
        if sensor_type == "PH":
            return {"has_value": False, "is_stale": False}
        return {"has_value": True, "is_stale": False, "value": 1.5}

    state = await evaluate_ph_ec_targets(
        read_metric=_read_metric,
        zone_id=1,
        target_ph=6.0,
        target_ec=1.6,
        tolerance={"ph_pct": 5.0, "ec_pct": 10.0},
        telemetry_freshness_enforce=True,
    )

    assert state["has_data"] is False
    assert state["targets_reached"] is False


@pytest.mark.asyncio
async def test_evaluate_ph_ec_targets_respects_stale_block_when_enforced():
    async def _read_metric(*, zone_id, sensor_type):
        return {"has_value": True, "is_stale": sensor_type == "PH", "value": 6.1 if sensor_type == "PH" else 1.6}

    state = await evaluate_ph_ec_targets(
        read_metric=_read_metric,
        zone_id=1,
        target_ph=6.0,
        target_ec=1.6,
        tolerance={"ph_pct": 5.0, "ec_pct": 10.0},
        telemetry_freshness_enforce=True,
    )

    assert state["has_data"] is True
    assert state["is_stale"] is True
    assert state["targets_reached"] is False


@pytest.mark.asyncio
async def test_evaluate_ph_ec_targets_returns_reached_when_both_in_tolerance():
    async def _read_metric(*, zone_id, sensor_type):
        return {"has_value": True, "is_stale": False, "value": 6.02 if sensor_type == "PH" else 1.58}

    state = await evaluate_ph_ec_targets(
        read_metric=_read_metric,
        zone_id=1,
        target_ph=6.0,
        target_ec=1.6,
        tolerance={"ph_pct": 5.0, "ec_pct": 10.0},
        telemetry_freshness_enforce=False,
    )

    assert state["has_data"] is True
    assert state["targets_reached"] is True
    assert state["ph_ok"] is True
    assert state["ec_ok"] is True
