from __future__ import annotations

from datetime import datetime, timezone

import pytest

from services.zone_process_cycle import process_zone_cycle


class _GrowCycleRepoStub:
    async def get_active_grow_cycle(self, _zone_id: int):
        return {"id": 44, "targets": {"target_ph": 5.8, "target_ec": 1.2}}


class _RecipeRepoStub:
    async def get_zone_data_batch(self, _zone_id: int):
        return {
            "telemetry": {},
            "telemetry_timestamps": {},
            "correction_flags": {},
            "nodes": {},
            "capabilities": {
                "ph_control": True,
                "ec_control": True,
                "climate_control": False,
                "irrigation_control": False,
                "recirculation": False,
                "light_control": False,
            },
        }


class _InfrastructureRepoStub:
    async def get_zone_bindings_by_role(self, _zone_id: int):
        return {}


class _ActuatorRegistryStub:
    def resolve(self, _zone_id: int, _bindings, _nodes):
        return {}


class _TimerCtx:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _LatencyMetricStub:
    def time(self):
        return _TimerCtx()


class _CounterMetricStub:
    def __init__(self) -> None:
        self.value = 0

    def inc(self) -> None:
        self.value += 1


async def _run_process_cycle(*, active_task, control_mode: str = "auto"):
    calls = {"correction": 0}

    async def _noop_async(*_args, **_kwargs):
        return None

    async def _safe_process(_name, coro, _zone_id):
        await coro

    async def _process_correction(*_args, **_kwargs):
        calls["correction"] += 1

    async def _load_latest_zone_task(_zone_id: int):
        return active_task

    await process_zone_cycle(
        zone_id=447,
        sim_clock=None,
        should_process_zone_fn=lambda _zone_id: True,
        emit_backoff_skip_signal_fn=_noop_async,
        is_degraded_mode_fn=lambda _zone_id: False,
        check_zone_deletion_fn=_noop_async,
        check_pid_config_updates_fn=_noop_async,
        check_phase_transitions_fn=_noop_async,
        grow_cycle_repo=_GrowCycleRepoStub(),
        recipe_repo=_RecipeRepoStub(),
        infrastructure_repo=_InfrastructureRepoStub(),
        actuator_registry=_ActuatorRegistryStub(),
        record_zone_error_fn=lambda _zone_id: None,
        emit_zone_data_unavailable_signal_fn=_noop_async,
        get_or_restore_workflow_phase_fn=lambda _zone_id: _as_async_value("tank_recirc"),
        safe_process_controller_fn=_safe_process,
        process_light_controller_fn=_noop_async,
        process_climate_controller_fn=_noop_async,
        process_irrigation_controller_fn=_noop_async,
        process_recirculation_controller_fn=_noop_async,
        process_correction_controllers_fn=_process_correction,
        load_zone_control_mode_fn=lambda _zone_id: _as_async_value(control_mode),
        load_latest_zone_task_fn=_load_latest_zone_task,
        evaluate_required_nodes_recovery_gate_fn=lambda _zone_id, _caps: _as_async_value(True),
        update_zone_health_fn=_noop_async,
        emit_missing_targets_signal_fn=_noop_async,
        emit_degraded_mode_signal_fn=_noop_async,
        reset_zone_error_streak_fn=lambda _zone_id: 0,
        emit_zone_recovered_signal_fn=_noop_async,
        get_error_streak_fn=lambda _zone_id: 0,
        get_next_allowed_run_at_fn=lambda _zone_id: None,
        create_zone_event_fn=_noop_async,
        check_water_level_fn=lambda _zone_id, **_kw: _as_async_value((True, 1.0)),
        ensure_water_level_alert_fn=_noop_async,
        utcnow_fn=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        check_latency_metric=_LatencyMetricStub(),
        zone_checks_metric=_CounterMetricStub(),
        logger=_LoggerStub(),
    )

    return calls["correction"]


def _as_async_value(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner()


class _LoggerStub:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None

    def error(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_process_zone_cycle_skips_correction_while_scheduler_task_running():
    correction_calls = await _run_process_cycle(active_task={"task_id": "st-1", "status": "running"})
    assert correction_calls == 0


@pytest.mark.asyncio
async def test_process_zone_cycle_skips_correction_while_scheduler_task_accepted():
    correction_calls = await _run_process_cycle(active_task={"task_id": "st-2", "status": "accepted"})
    assert correction_calls == 0


@pytest.mark.asyncio
async def test_process_zone_cycle_runs_correction_without_active_scheduler_task():
    correction_calls = await _run_process_cycle(active_task=None)
    assert correction_calls == 1


@pytest.mark.asyncio
async def test_process_zone_cycle_runs_correction_for_terminal_scheduler_task_status():
    correction_calls = await _run_process_cycle(active_task={"task_id": "st-3", "status": "completed"})
    assert correction_calls == 1


@pytest.mark.asyncio
async def test_process_zone_cycle_skips_automation_in_manual_control_mode():
    correction_calls = await _run_process_cycle(active_task=None, control_mode="manual")
    assert correction_calls == 0
