"""E200: состояние посадки без имён стадий бака."""

from __future__ import annotations

from datetime import datetime, timezone

from ae4.domain.planting import PhaseTargets, PlantingState, planting_public_keys


def test_e200_planting_public_keys_exclude_tank_stage_names() -> None:
    state = PlantingState(
        zone_id=1,
        grow_cycle_id=2,
        phase=PhaseTargets(
            phase_id=3,
            started_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            interval_sec=3600,
            duration_sec=60,
        ),
    )
    keys = planting_public_keys(state)
    joined = " ".join(keys).lower()
    assert "two_tank" not in joined
    assert "tank_filling" not in joined
    assert "tank_recirc" not in joined
    assert "irrigating" not in joined
    assert "zone_id" in keys
    assert "soil_moisture_min" in keys
