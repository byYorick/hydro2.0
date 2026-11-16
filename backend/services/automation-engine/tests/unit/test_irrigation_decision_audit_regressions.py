"""Safety and observability regressions found in the irrigation decision audit."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from _test_support_runtime_plan import make_runtime_plan
from ae3lite.domain.services.irrigation_decision_controller import IrrigationDecisionController
from test_ae3lite_irrigation_decision_controller import _GateDecision, _run_gate

NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc).replace(tzinfo=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [-1, float("-inf"), float("inf"), float("nan"), 101, True])
async def test_invalid_soil_samples_never_authorize_irrigation(value):
    runtime = make_runtime_plan(
        irrigation_decision={"strategy": "smart_soil_v1"}, soil_moisture_target={"min": 40, "max": 50}
    )
    monitor = SimpleNamespace(
        read_metric_windows=AsyncMock(
            return_value={
                "sensor_windows": [{"samples": [{"value": value}]}],
                "is_stale": False,
            }
        )
    )
    decision = await IrrigationDecisionController().evaluate(
        zone_id=7, runtime_monitor=monitor, runtime=runtime, mode="normal", requested_duration_sec=120, now=NOW
    )
    assert decision.outcome == "skip"
    assert decision.reason_code == "smart_soil_telemetry_missing_or_stale"


@pytest.mark.asyncio
async def test_degraded_run_is_reported_as_warning(monkeypatch):
    outcome, reports, _ = await _run_gate(
        _GateDecision(outcome="run", reason_code="smart_soil_degraded_below_min", degraded=True), monkeypatch
    )
    assert outcome.next_stage == "irrigation_start"
    assert [report.code for report in reports] == ["biz_irrigation_decision_degraded"]


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["", "unknown", "RUN", "degraded_skip"])
async def test_unrecognized_decision_outcome_cannot_start_irrigation(monkeypatch, outcome):
    result, _, repository = await _run_gate(_GateDecision(outcome=outcome, reason_code="test"), monkeypatch)
    assert result.kind == "fail"
    assert repository.saved["irrigation_decision_outcome"] == "fail"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'target',
    [
        {'min': 60, 'max': 40},
        {'min': -1, 'max': 40},
        {'min': 40, 'max': 101},
        {'min': float('nan'), 'max': 40},
        {'day': float('inf')},
        {'unit': 'ratio', 'min': 0.3, 'max': 0.5},
    ],
)
async def test_invalid_target_band_does_not_silently_control_irrigation(target):
    runtime = make_runtime_plan(irrigation_decision={"strategy": "smart_soil_v1"}, soil_moisture_target=target)
    monitor = SimpleNamespace(
        read_metric_windows=AsyncMock(return_value={"sensor_windows": [{"samples": [{"value": 30}]}]})
    )
    result = await IrrigationDecisionController().evaluate(
        zone_id=7, runtime_monitor=monitor, runtime=runtime, mode="normal", requested_duration_sec=120, now=NOW
    )
    assert result.outcome == 'fail'
    assert result.reason_code == 'smart_soil_target_invalid'
    monitor.read_metric_windows.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_missing_active_sensor_does_not_get_hidden_by_a_dry_peer():
    runtime = make_runtime_plan(
        irrigation_decision={"strategy": "smart_soil_v1"}, soil_moisture_target={"min": 40, "max": 50}
    )
    monitor = SimpleNamespace(
        read_metric_windows=AsyncMock(return_value={"sensor_windows": [{"samples": [{"value": 20}]}, {"samples": []}]})
    )
    result = await IrrigationDecisionController().evaluate(
        zone_id=7, runtime_monitor=monitor, runtime=runtime, mode="normal", requested_duration_sec=120, now=NOW
    )
    assert result.outcome == 'skip'
    assert result.reason_code == 'smart_soil_telemetry_missing_or_stale'
    assert result.details['missing_sensor_count'] == 1


@pytest.mark.asyncio
async def test_spread_warning_is_exposed_without_changing_mean_policy():
    runtime = make_runtime_plan(
        irrigation_decision={"strategy": "smart_soil_v1"}, soil_moisture_target={"min": 40, "max": 50}
    )
    monitor = SimpleNamespace(
        read_metric_windows=AsyncMock(
            return_value={"sensor_windows": [{"samples": [{"value": 0}]}, {"samples": [{"value": 60}]}]}
        )
    )
    result = await IrrigationDecisionController().evaluate(
        zone_id=7, runtime_monitor=monitor, runtime=runtime, mode="normal", requested_duration_sec=120, now=NOW
    )
    assert result.outcome == 'run'
    assert result.degraded is True
    assert result.details['spread_alert'] is True
    assert result.details['zone_average_pct'] == 30
    assert result.details['run_below_pct'] == 38


def test_partial_locked_config_does_not_inherit_later_live_values():
    from ae3lite.domain.services.cycle_start_planner import CycleStartPlanner

    task = SimpleNamespace(
        task_type='irrigation_start',
        irrigation_decision_strategy='smart_soil_v1',
        irrigation_decision_config={'lookback_sec': 900},
        irrigation_bundle_revision='locked',
    )
    result = CycleStartPlanner()._apply_irrigation_decision_snapshot(
        task=task,
        runtime={'irrigation_decision': {'strategy': 'task', 'config': {'hysteresis_pct': 90, 'min_samples': 100}}},
    )
    assert result['irrigation_decision']['config']['hysteresis_pct'] == 2
    assert result['irrigation_decision']['config']['min_samples'] == 3
    assert result['irrigation_decision']['config']['lookback_sec'] == 900


@pytest.mark.parametrize(
    'key', ['lookback_sec', 'min_samples', 'stale_after_sec', 'hysteresis_pct', 'spread_alert_threshold_pct']
)
@pytest.mark.parametrize('value', [float('nan'), float('inf'), 'NaN', True])
def test_invalid_decision_config_is_rejected_before_defaults_can_hide_it(key, value):
    from ae3lite.config.runtime_plan_irrigation import resolve_irrigation_decision_config
    from ae3lite.domain.errors import PlannerConfigurationError

    with pytest.raises(PlannerConfigurationError):
        resolve_irrigation_decision_config({key: value})


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf'), True])
def test_invalid_solution_temperature_is_unavailable_instead_of_a_plausible_reading(value):
    from ae3lite.domain.services.solution_temp_irrigation_guard import evaluate_solution_temp_hold

    result = evaluate_solution_temp_hold(
        min_c=18,
        max_c=24,
        hold_sec=600,
        stale_sec=600,
        now=NOW,
        reading={'samples': [], 'telemetry_last': {'ts': NOW, 'value': value}},
    )
    assert result.reason_code == 'solution_temp_unavailable'
    assert result.blocks_irrigation is False  # Existing agronomy policy for missing temperature.


def test_future_solution_temperature_is_not_fresh():
    from datetime import timedelta
    from ae3lite.domain.services.solution_temp_irrigation_guard import evaluate_solution_temp_hold

    result = evaluate_solution_temp_hold(
        min_c=18,
        max_c=24,
        hold_sec=600,
        stale_sec=600,
        now=NOW,
        reading={'samples': [], 'telemetry_last': {'ts': NOW + timedelta(hours=1), 'value': 20}},
    )
    assert result.reason_code == 'solution_temp_unavailable'


def test_two_hot_points_in_one_second_do_not_prove_a_ten_minute_hold():
    from datetime import timedelta
    from ae3lite.domain.services.solution_temp_irrigation_guard import evaluate_solution_temp_hold

    result = evaluate_solution_temp_hold(
        min_c=18,
        max_c=24,
        hold_sec=600,
        stale_sec=600,
        now=NOW,
        reading={'samples': [{'ts': NOW - timedelta(seconds=1), 'value': 33}, {'ts': NOW, 'value': 33}]},
    )
    assert result.reason_code == 'solution_temp_hot_warn'
    assert result.blocks_irrigation is False
