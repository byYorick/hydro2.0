"""E237: смена фазы обнуляет точку интеграла и берёт цели новой фазы."""

from __future__ import annotations

from datetime import datetime, timezone

from ae4.domain.planting import (
    LightIntegralCursor,
    PhaseTargets,
    PlantingState,
    apply_phase_change,
)


def test_e237_phase_change_resets_integral_cursor() -> None:
    old_started = datetime(2026, 6, 1, 6, 0, tzinfo=timezone.utc)
    new_started = datetime(2026, 6, 5, 6, 0, tzinfo=timezone.utc)
    state = PlantingState(
        zone_id=1,
        grow_cycle_id=2,
        phase=PhaseTargets(
            phase_id=1,
            started_at=old_started,
            interval_sec=3600,
            duration_sec=60,
            light_integral_per_shot=1000.0,
            light_integral_unit="lux·s",
            vpd_min=0.5,
            vpd_max=1.2,
        ),
    )
    integral = LightIntegralCursor(
        accumulated=999.0,
        last_accounted_ts=old_started,
        unit="lux·s",
        status="ok",
        last_value=400.0,
    )
    new_phase = PhaseTargets(
        phase_id=2,
        started_at=new_started,
        interval_sec=1800,
        duration_sec=30,
        light_integral_per_shot=500.0,
        light_integral_unit="lux·s",
        vpd_min=0.8,
        vpd_max=1.5,
    )
    new_state, reset = apply_phase_change(state=state, new_phase=new_phase, integral=integral)
    assert new_state.phase.phase_id == 2
    assert new_state.phase.vpd_min == 0.8
    assert reset.accumulated == 0.0
    assert reset.last_accounted_ts == new_started
    assert reset.last_value is None
    assert reset.accumulated != integral.accumulated
