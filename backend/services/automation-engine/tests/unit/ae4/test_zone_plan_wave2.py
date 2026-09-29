"""zone_plan без дефолтов AE3: нет ключа — ошибка конфигурации."""

from __future__ import annotations

import pytest

from ae4.config.zone_plan import (
    ZonePlanConfigurationError,
    _require_float,
    _require_int,
    require_plan_steps,
    ZonePlan,
)


def test_zone_plan_missing_timeout_is_error() -> None:
    with pytest.raises(ZonePlanConfigurationError) as exc:
        _require_int(None, path="runtime.clean_fill_timeout_sec")
    assert "clean_fill_timeout_sec" in str(exc.value)


def test_zone_plan_does_not_default_volume() -> None:
    with pytest.raises(ZonePlanConfigurationError) as exc:
        _require_float(None, path="grow_cycle_phases.nutrient_solution_volume_l")
    assert "nutrient_solution_volume_l" in str(exc.value)
    # Каталожные 100 л не подставляются.
    with pytest.raises(ZonePlanConfigurationError):
        _require_float(0, path="grow_cycle_phases.nutrient_solution_volume_l")


def test_zone_plan_missing_steps_is_error() -> None:
    plan = ZonePlan(
        zone_id=1,
        grow_cycle_id=1,
        greenhouse_id=1,
        greenhouse_uid="gh",
        timezone="UTC",
        control_mode="auto",
        telemetry_max_age_sec=30,
        clean_fill_timeout_sec=120,
        solution_topup_timeout_sec=120,
        nutrient_solution_volume_l=50.0,
        command_plans={"plans": {}},
    )
    with pytest.raises(ZonePlanConfigurationError) as exc:
        require_plan_steps(plan, plan_key="irrigation_stop")
    assert "irrigation_stop" in str(exc.value)
