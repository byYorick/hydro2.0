"""Unit tests: cumulative T_* from ratios + water_ec (+ day/night)."""

from __future__ import annotations

import pytest

from ae3lite.domain.services.nutrient_pipeline import compute_component_targets


def test_cumulative_targets_order() -> None:
    t = compute_component_targets(
        water_ec=0.3,
        water_ph=7.1,
        target_ec=2.3,
        ratios={"calcium": 20, "magnesium": 20, "npk": 40, "micro": 20},
    )
    assert t.T_ca < t.T_ca_mg < t.T_ca_mg_npk <= t.T_full
    assert t.T_full == pytest.approx(2.3)


def test_night_target_minus_water_ec() -> None:
    """Day/night: budget uses night target_ec − water_ec."""
    night_target = 1.6
    water = 0.35
    t = compute_component_targets(
        water_ec=water,
        water_ph=6.9,
        target_ec=night_target,
        ratios={"calcium": 0.3, "magnesium": 0.2, "npk": 0.4, "micro": 0.1},
    )
    assert t.nutrient_budget == pytest.approx(night_target - water)
    assert t.T_full == pytest.approx(night_target)
