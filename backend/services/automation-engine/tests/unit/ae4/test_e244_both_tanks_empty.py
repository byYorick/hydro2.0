"""E244: оба бака пусты; clean пуст → supply_to_clean; нет шагов — клапан не выдумывается."""

from __future__ import annotations

from datetime import datetime, timezone

from ae4.application.mutation_decision import decide_mutation
from ae4.domain.planting import LightIntegralCursor
from tests.unit.ae4.conftest_wave3 import make_phase, make_plan, make_telemetry


def _integral(at: datetime) -> LightIntegralCursor:
    return LightIntegralCursor(
        accumulated=0.0,
        last_accounted_ts=at,
        unit=None,
        status="ok",
    )


def test_e244_both_empty_no_pump_critical() -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    plan = make_plan()
    decision = decide_mutation(
        plan=plan,
        phase=make_phase(started_at=now.replace(hour=8)),
        telemetry=make_telemetry(feed_min=0, clean_min=0, soil_value=50.0, now=now),
        now=now,
        emergency_stop=False,
        last_shot=None,
        last_planned_shot_at=None,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=_integral(now),
        new_light_samples=(),
    )
    assert decision.kind == "supply_to_clean"
    assert decision.create_task is True
    assert decision.failed is False
    assert decision.reason_code == "supply_to_clean"


def test_e244_clean_empty_feed_not_empty_supply_to_clean() -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    plan = make_plan()
    decision = decide_mutation(
        plan=plan,
        phase=make_phase(started_at=now.replace(hour=8)),
        telemetry=make_telemetry(feed_min=1, clean_min=0, soil_value=50.0, now=now),
        now=now,
        emergency_stop=False,
        last_shot=None,
        last_planned_shot_at=None,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=_integral(now),
        new_light_samples=(),
    )
    assert decision.kind == "supply_to_clean"
    assert decision.create_task is True
    assert decision.failed is False


def test_e244_clean_empty_without_steps_no_invented_valve() -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    plan = make_plan(
        command_plans={
            "plans": {
                "irrigation_start": [
                    {
                        "node_uid": "nd-1",
                        "channel": "valve_solution_supply",
                        "cmd": "set_relay",
                        "params": {"state": True},
                    },
                    {
                        "node_uid": "nd-1",
                        "channel": "valve_irrigation",
                        "cmd": "set_relay",
                        "params": {"state": True},
                    },
                    {
                        "node_uid": "nd-1",
                        "channel": "pump_main",
                        "cmd": "run_pump",
                        "params": {"duration_ms": 1000},
                    },
                ],
                "irrigation_stop": [
                    {
                        "node_uid": "nd-1",
                        "channel": "pump_main",
                        "cmd": "set_relay",
                        "params": {"state": False},
                    }
                ],
            }
        }
    )
    decision = decide_mutation(
        plan=plan,
        phase=make_phase(started_at=now.replace(hour=8)),
        telemetry=make_telemetry(feed_min=1, clean_min=0, soil_value=50.0, now=now),
        now=now,
        emergency_stop=False,
        last_shot=None,
        last_planned_shot_at=None,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=_integral(now),
        new_light_samples=(),
    )
    assert decision.kind is None
    assert decision.create_task is False
    assert decision.failed is True
    assert decision.reason_code == "clean_fill_steps_missing"
