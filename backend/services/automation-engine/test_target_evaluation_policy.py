from __future__ import annotations

import pytest

from domain.policies.target_evaluation_policy import evaluate_ph_ec_targets


@pytest.mark.asyncio
async def test_evaluate_ph_ec_targets_hard_bounds_override_wide_pct_tolerance():
    async def _read_metric(*, sensor_type: str, **_kwargs):
        if sensor_type == "PH":
            return {"has_value": True, "is_stale": False, "value": 6.37}
        return {"has_value": True, "is_stale": False, "value": 0.87}

    result = await evaluate_ph_ec_targets(
        read_metric=_read_metric,
        zone_id=5,
        target_ph=5.75,
        target_ec=1.05,
        tolerance={"ph_pct": 15.0, "ec_pct": 25.0},
        telemetry_freshness_enforce=True,
        hard_bounds={"ph_min": 5.6, "ph_max": 6.1, "ec_min": 0.9, "ec_max": 1.2},
    )

    assert result["ph_ok_pct"] is True
    assert result["ec_ok_pct"] is True
    assert result["ph_ok"] is False
    assert result["ec_ok"] is False
    assert result["targets_reached"] is False


@pytest.mark.asyncio
async def test_evaluate_ph_ec_targets_uses_absolute_tolerance_when_bounds_missing():
    async def _read_metric(*, sensor_type: str, **_kwargs):
        if sensor_type == "PH":
            return {"has_value": True, "is_stale": False, "value": 6.05}
        return {"has_value": True, "is_stale": False, "value": 1.01}

    result = await evaluate_ph_ec_targets(
        read_metric=_read_metric,
        zone_id=5,
        target_ph=5.75,
        target_ec=1.05,
        tolerance={"ph_pct": 15.0, "ec_pct": 25.0},
        telemetry_freshness_enforce=True,
        absolute_tolerance={"ph_abs": 0.2, "ec_abs": 0.1},
    )

    assert result["ph_ok_pct"] is True
    assert result["ec_ok_pct"] is True
    assert result["ph_ok"] is False
    assert result["ec_ok"] is True
    assert result["targets_reached"] is False
