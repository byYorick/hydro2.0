"""E220: нет feed_only или нет level_solution_min → failed=true."""

from __future__ import annotations

from datetime import datetime, timezone

from ae4.application.mutation_decision import decide_mutation
from ae4.domain.planting import LightIntegralCursor
from tests.unit.ae4.conftest_wave3 import make_phase, make_plan, make_telemetry


def test_e220_missing_feed_only_circuit_failed() -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    plan = make_plan(command_plans={"plans": {}})
    decision = decide_mutation(
        plan=plan,
        phase=make_phase(started_at=now.replace(hour=8)),
        telemetry=make_telemetry(now=now),
        now=now,
        emergency_stop=False,
        last_shot=None,
        last_planned_shot_at=None,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=LightIntegralCursor(0.0, now, None, "ok"),
        new_light_samples=(),
    )
    assert decision.failed is True
    assert decision.reason_code == "feed_only_circuit_unbound"
    assert decision.create_task is False


def test_e220_irrigation_step_without_node_uid_is_unbound() -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    plan = make_plan()
    plan.command_plans["plans"]["irrigation_start"][2]["node_uid"] = ""
    decision = decide_mutation(
        plan=plan,
        phase=make_phase(started_at=now.replace(hour=8)),
        telemetry=make_telemetry(now=now),
        now=now,
        emergency_stop=False,
        last_shot=None,
        last_planned_shot_at=None,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=LightIntegralCursor(0.0, now, None, "ok"),
        new_light_samples=(),
    )
    assert decision.failed is True
    assert decision.reason_code == "feed_only_circuit_unbound"
    assert decision.create_task is False


def test_e220_missing_level_solution_min_failed() -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    plan = make_plan()
    decision = decide_mutation(
        plan=plan,
        phase=make_phase(started_at=now.replace(hour=8)),
        telemetry=make_telemetry(now=now, unbound_feed_min=True),
        now=now,
        emergency_stop=False,
        last_shot=None,
        last_planned_shot_at=None,
        extra_used_in_half_interval=False,
        successful_shots_in_window=0,
        integral=LightIntegralCursor(0.0, now, None, "ok"),
        new_light_samples=(),
    )
    assert decision.failed is True
    assert decision.reason_code == "level_solution_min_unbound_or_stale"
    assert decision.create_task is False
