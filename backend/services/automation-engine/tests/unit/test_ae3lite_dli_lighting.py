"""Потолок dli_target: duty ON-тика и формула 100 × 10000 с = 1.0 моль/м²."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ae3lite.application.dto import ZoneActuatorRef, ZoneSnapshot
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.services.cycle_start_planner import CycleStartPlanner
from ae3lite.domain.services.dli_integral import (
    configured_channel_unit,
    integrate_ppfd,
    select_light_channel_row,
)

_START = datetime(2026, 10, 4, 6, 0, tzinfo=timezone.utc)
_AS_OF = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
_WINDOW_START = datetime(2026, 10, 3, 21, 0, tzinfo=timezone.utc)


def _samples_one_mol() -> list[dict[str, float | str]]:
    points: list[dict[str, float | str]] = [
        {"ts": (_WINDOW_START - timedelta(hours=2)).isoformat(), "value": 9000.0},
    ]
    for index in range(21):
        points.append({
            "ts": (_START + timedelta(seconds=500 * index)).isoformat(),
            "value": 100.0,
        })
    return points


def _series(*, unit: str, samples: list[dict[str, float | str]] | None = None) -> dict[str, object]:
    return {
        "unit": unit,
        "samples": _samples_one_mol() if samples is None else samples,
        "timezone": "Europe/Moscow",
        "window_start": _WINDOW_START.isoformat(),
        "as_of": _AS_OF.isoformat(),
    }


def _task(*, desired: str, brightness: int | None = None) -> AutomationTask:
    now = _AS_OF
    payload: dict[str, object] = {"desired_state": desired}
    if brightness is not None:
        payload["brightness_pct"] = brightness
    return AutomationTask.from_row({
        "id": 81,
        "zone_id": 9,
        "task_type": "lighting_tick",
        "status": "claimed",
        "idempotency_key": "lt-dli",
        "scheduled_for": now,
        "due_at": now,
        "claimed_by": "w",
        "claimed_at": now,
        "error_code": None,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "topology": "lighting_tick",
        "intent_source": "laravel_scheduler",
        "intent_trigger": "lighting_tick",
        "intent_id": 1,
        "intent_meta": {"intent_payload": payload},
        "current_stage": "apply",
        "workflow_phase": "ready",
        "stage_deadline_at": None,
        "stage_retry_count": 0,
        "stage_entered_at": None,
        "clean_fill_cycle": 0,
        "corr_step": None,
    })


def _snapshot(*, lighting: dict[str, object], series: dict[str, object] | None) -> ZoneSnapshot:
    return ZoneSnapshot(
        zone_id=9,
        greenhouse_id=3,
        automation_runtime="ae3",
        grow_cycle_id=1,
        current_phase_id=1,
        phase_name="veg",
        workflow_phase="ready",
        workflow_version=1,
        targets={"lighting": lighting, "greenhouse_timezone": "Europe/Moscow"},
        diagnostics_execution={},
        command_plans={},
        telemetry_last={},
        pid_state={},
        pid_configs={},
        actuators=(
            ZoneActuatorRef(
                node_uid="nd-light-1",
                node_type="light",
                channel="light_main",
                node_channel_id=501,
                role="main",
            ),
        ),
        dli_light_series=series,
    )


def test_formula_100_ppfd_for_10000s_is_one_mol() -> None:
    start = datetime(2026, 10, 4, tzinfo=timezone.utc)
    mol, status = integrate_ppfd(
        [(start, 100.0), (start + timedelta(seconds=10_000), 100.0)],
        gap_sec=10_000,
    )
    assert status == "ok"
    assert mol == 1.0


def test_off_stays_duty_zero_when_integral_is_above_target() -> None:
    snapshot = _snapshot(
        lighting={"dli_target": 0.5, "brightness": 80},
        series=_series(unit="ppfd"),
    )
    plan = CycleStartPlanner().build(task=_task(desired="off", brightness=80), snapshot=snapshot)
    assert plan.steps[0].payload["cmd"] == "set_pwm"
    assert plan.steps[0].payload["params"]["duty"] == 0
    assert "dli_status" not in plan.steps[0].payload


def test_on_above_target_sets_duty_zero_and_below_keeps_requested_brightness() -> None:
    above = CycleStartPlanner().build(
        task=_task(desired="on", brightness=41),
        snapshot=_snapshot(lighting={"dli_target": 0.5, "brightness": 80}, series=_series(unit="ppfd")),
    )
    assert above.steps[0].payload["params"]["duty"] == 0
    assert above.steps[0].payload["dli_status"] == "capped"
    assert above.steps[0].payload["dli_mol"] == 1.0

    below = CycleStartPlanner().build(
        task=_task(desired="on", brightness=41),
        snapshot=_snapshot(lighting={"dli_target": 5, "brightness": 80}, series=_series(unit="ppfd")),
    )
    assert below.steps[0].payload["params"]["duty"] == 41
    assert below.steps[0].payload["dli_status"] == "within_target"
    assert below.steps[0].payload["dli_mol"] == 1.0


def test_lux_is_not_moles_and_gap_does_not_zero_duty() -> None:
    alerts: list[tuple[int, str]] = []
    planner = CycleStartPlanner(dli_alert_writer=lambda zone_id, local_date: alerts.append((zone_id, local_date)))
    lux = _snapshot(lighting={"dli_target": 5, "brightness": 55}, series=_series(unit="lux"))
    plan = planner.build(task=_task(desired="on", brightness=55), snapshot=lux)
    assert plan.steps[0].payload["params"]["duty"] == 55
    assert plan.steps[0].payload["dli_status"] == "sensor_unavailable"
    assert plan.steps[0].payload["dli_mol"] is None

    planner.build(task=_task(desired="on", brightness=55), snapshot=lux)
    assert alerts == [(9, "2026-10-04")]

    gap_samples = [
        {"ts": _START.isoformat(), "value": 100.0},
        {"ts": (_START + timedelta(seconds=1000)).isoformat(), "value": 100.0},
    ]
    gap = planner.build(
        task=_task(desired="on", brightness=55),
        snapshot=_snapshot(
            lighting={"dli_target": 0.1, "brightness": 55},
            series=_series(unit="ppfd", samples=gap_samples),
        ),
    )
    assert gap.steps[0].payload["params"]["duty"] == 55
    assert gap.steps[0].payload["dli_status"] == "gap"
    assert gap.steps[0].payload["dli_mol"] is None
    assert alerts == [(9, "2026-10-04")]


def test_empty_target_does_not_cap_and_does_not_alert() -> None:
    alerts: list[tuple[int, str]] = []
    planner = CycleStartPlanner(dli_alert_writer=lambda zone_id, local_date: alerts.append((zone_id, local_date)))
    plan = planner.build(
        task=_task(desired="on", brightness=73),
        snapshot=_snapshot(lighting={"brightness": 73}, series=_series(unit="ppfd")),
    )
    assert plan.steps[0].payload["params"]["duty"] == 73
    assert plan.steps[0].payload["dli_status"] == "not_configured"
    assert alerts == []


def test_channel_unit_lux_and_mixed_are_not_ppfd() -> None:
    assert configured_channel_unit("ppfd", None) == "ppfd"
    assert configured_channel_unit("lux", {"unit": "ppfd"}) == "mixed"
    assert configured_channel_unit("", None) == ""
    rows = [
        {"id": 2, "channel": "light_level", "metric": "LIGHT_INTENSITY", "scope": "inside"},
        {"id": 3, "channel": "outside_light", "metric": "OUTSIDE_LIGHT", "scope": "outside"},
    ]
    assert select_light_channel_row(rows, explicit_channel=None)["channel"] == "light_level"
    assert select_light_channel_row(rows, explicit_channel="outside_light")["channel"] == "outside_light"
