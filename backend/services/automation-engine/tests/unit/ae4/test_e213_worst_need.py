"""E213: ограничитель — худшая потребность; климат листа и кислород корня."""

from __future__ import annotations

from datetime import datetime, timezone

from ae4.domain.planting import (
    PhaseTargets,
    observe_leaf_climate,
    observe_root_oxygen,
    worst_need,
)
from tests.unit.ae4.conftest_wave1 import sample


def test_e213_worst_need_picks_highest_severity() -> None:
    assert worst_need({"nutrition": "above", "water": "below"}) == "water"
    assert worst_need({"leaf_climate": "unseen", "nutrition": "above"}) == "leaf_climate"
    assert worst_need({"root_oxygen": "unseen"}) == "root_oxygen"


def test_e213_leaf_climate_and_root_oxygen_as_observation() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    phase = PhaseTargets(
        phase_id=1,
        started_at=now,
        temp_air_target=24.0,
        humidity_target=60.0,
        solution_temp_min=18.0,
        solution_temp_max=22.0,
    )
    leaf = observe_leaf_climate(
        phase=phase,
        temp_air=sample(
            metric_type="TEMPERATURE",
            channel="temperature",
            value=20.0,
            ts=now,
            unit="C",
        ),
        humidity_air=sample(
            metric_type="HUMIDITY",
            channel="humidity",
            value=60.0,
            ts=now,
            unit="%",
        ),
        now=now,
        telemetry_max_age_sec=120,
    )
    assert leaf == "below"

    root = observe_root_oxygen(
        phase=phase,
        solution_temp=sample(
            metric_type="TEMPERATURE",
            channel="solution_temp_c",
            value=25.0,
            ts=now,
            unit="C",
        ),
        now=now,
        telemetry_max_age_sec=120,
    )
    assert root == "above"

    stale = observe_root_oxygen(
        phase=phase,
        solution_temp=None,
        now=now,
        telemetry_max_age_sec=120,
    )
    assert stale == "unseen"

    silent = observe_leaf_climate(
        phase=PhaseTargets(phase_id=1, started_at=now),
        temp_air=None,
        humidity_air=None,
        now=now,
        telemetry_max_age_sec=120,
    )
    assert silent is None

    assert worst_need({"leaf_climate": leaf, "root_oxygen": root}) == "leaf_climate"


def test_e213_rejects_solution_temp_as_leaf_and_temperature_without_channel() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    phase = PhaseTargets(
        phase_id=1,
        started_at=now,
        temp_air_target=24.0,
        humidity_target=60.0,
        solution_temp_min=18.0,
        solution_temp_max=22.0,
    )
    # Температура раствора не становится климатом листа.
    leaf_from_solution = observe_leaf_climate(
        phase=phase,
        temp_air=sample(
            metric_type="TEMPERATURE",
            channel="solution_temp_c",
            value=10.0,
            ts=now,
            unit="C",
        ),
        humidity_air=sample(
            metric_type="HUMIDITY",
            channel="humidity",
            value=60.0,
            ts=now,
            unit="%",
        ),
        now=now,
        telemetry_max_age_sec=120,
    )
    assert leaf_from_solution == "unseen"

    # TEMPERATURE без канала воздуха не читается.
    leaf_no_channel = observe_leaf_climate(
        phase=phase,
        temp_air=sample(
            metric_type="TEMPERATURE",
            channel="",
            value=10.0,
            ts=now,
            unit="C",
        ),
        humidity_air=sample(
            metric_type="HUMIDITY",
            channel="humidity",
            value=60.0,
            ts=now,
            unit="%",
        ),
        now=now,
        telemetry_max_age_sec=120,
    )
    assert leaf_no_channel == "unseen"

    # Верный канал воздуха и solution_temp_c дают наблюдение.
    leaf_ok = observe_leaf_climate(
        phase=phase,
        temp_air=sample(
            metric_type="TEMPERATURE",
            channel="air_temp_c",
            value=20.0,
            ts=now,
            unit="C",
        ),
        humidity_air=sample(
            metric_type="HUMIDITY",
            channel="air_rh",
            value=60.0,
            ts=now,
            unit="%",
        ),
        now=now,
        telemetry_max_age_sec=120,
    )
    assert leaf_ok == "below"

    root_ok = observe_root_oxygen(
        phase=phase,
        solution_temp=sample(
            metric_type="TEMPERATURE",
            channel="solution_temp_c",
            value=25.0,
            ts=now,
            unit="C",
        ),
        now=now,
        telemetry_max_age_sec=120,
    )
    assert root_ok == "above"

    root_from_air = observe_root_oxygen(
        phase=phase,
        solution_temp=sample(
            metric_type="TEMPERATURE",
            channel="temperature",
            value=25.0,
            ts=now,
            unit="C",
        ),
        now=now,
        telemetry_max_age_sec=120,
    )
    assert root_from_air == "unseen"
