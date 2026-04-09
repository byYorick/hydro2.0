from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import suppress
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.responses import JSONResponse

os.environ.setdefault("HISTORY_LOGGER_API_TOKEN", "test-token")

import ae3lite.runtime.app as runtime_app_module


NOW = datetime(2026, 4, 9, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_spawn_background_task_fails_closed_when_limit_is_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocker = asyncio.Event()
    existing_task = asyncio.create_task(blocker.wait(), name="existing-background-task")
    background_tasks = {existing_task}

    monkeypatch.setattr(runtime_app_module, "_BACKGROUND_TASKS_SIZE_LIMIT", 1)

    async def sample_coro() -> None:
        await asyncio.sleep(0)

    try:
        with pytest.raises(runtime_app_module.BackgroundTaskLimitError, match="ae3_background_task_limit_exceeded"):
            runtime_app_module._spawn_background_task(
                sample_coro(),
                task_name="overflow-task",
                background_tasks=background_tasks,
            )
        assert background_tasks == {existing_task}
    finally:
        existing_task.cancel()
        with suppress(asyncio.CancelledError):
            await existing_task


@pytest.mark.asyncio
async def test_intent_listener_callback_kicks_worker() -> None:
    kicks: list[str] = []

    class _Worker:
        def kick(self) -> None:
            kicks.append("kick")

    callback = runtime_app_module._build_intent_listener_callback(
        worker=_Worker(),
        logger=logging.getLogger("ae3-runtime-test"),
    )

    await callback({"intent_id": 11, "zone_id": 22, "status": "completed"})

    assert kicks == ["kick"]


@pytest.mark.asyncio
async def test_zone_event_listener_callback_kicks_worker_and_runs_solution_tank_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kicks: list[str] = []
    guard_calls: list[dict[str, object]] = []
    service_logs: list[dict[str, object]] = []

    class _Worker:
        def kick(self) -> None:
            kicks.append("kick")

    class _Guard:
        async def run(self, *, zone_id: int, now):
            guard_calls.append({"zone_id": zone_id, "now": now})
            return {"reset": True, "reason": "solution_tank_depleted"}

    monkeypatch.setattr(
        runtime_app_module,
        "send_service_log",
        lambda **kwargs: service_logs.append(dict(kwargs)),
    )

    callback = runtime_app_module._build_zone_event_listener_callback(
        worker=_Worker(),
        solution_tank_startup_guard_use_case=_Guard(),
        now_fn=lambda: NOW.replace(tzinfo=None),
        logger=logging.getLogger("ae3-runtime-test"),
    )

    await callback(
        {
            "source": "node_event",
            "zone_id": 22,
            "event_type": "LEVEL_SWITCH_CHANGED",
            "channel": "level_solution_min",
            "state": False,
            "initial": False,
        }
    )

    assert kicks == ["kick"]
    assert len(guard_calls) == 1
    assert guard_calls[0]["zone_id"] == 22
    assert len(service_logs) == 1
    assert service_logs[0]["message"] == "AE3 worker.kick by node runtime event"


@pytest.mark.asyncio
async def test_zone_event_listener_callback_accepts_storage_state_fail_safe_event_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kicks: list[str] = []
    guard_calls: list[dict[str, object]] = []

    class _Worker:
        def kick(self) -> None:
            kicks.append("kick")

    class _Guard:
        async def run(self, *, zone_id: int, now):
            guard_calls.append({"zone_id": zone_id, "now": now})
            return {"reset": True, "reason": "solution_tank_depleted"}

    monkeypatch.setattr(runtime_app_module, "send_service_log", lambda **_kwargs: None)

    callback = runtime_app_module._build_zone_event_listener_callback(
        worker=_Worker(),
        solution_tank_startup_guard_use_case=_Guard(),
        now_fn=lambda: NOW.replace(tzinfo=None),
        logger=logging.getLogger("ae3-runtime-test"),
    )

    await callback(
        {
            "source": "node_event",
            "zone_id": 22,
            "event_type": "IRRIGATION_SOLUTION_LOW",
            "channel": "storage_state",
            "snapshot": {"solution_level_min": False},
        }
    )

    assert kicks == ["kick"]
    assert len(guard_calls) == 1
    assert guard_calls[0]["zone_id"] == 22


@pytest.mark.asyncio
async def test_zone_event_listener_callback_ignores_irrelevant_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kicks: list[str] = []
    service_logs: list[dict[str, object]] = []

    class _Worker:
        def kick(self) -> None:
            kicks.append("kick")

    monkeypatch.setattr(
        runtime_app_module,
        "send_service_log",
        lambda **kwargs: service_logs.append(dict(kwargs)),
    )

    callback = runtime_app_module._build_zone_event_listener_callback(
        worker=_Worker(),
        solution_tank_startup_guard_use_case=None,
        now_fn=lambda: NOW.replace(tzinfo=None),
        logger=logging.getLogger("ae3-runtime-test"),
    )

    await callback(
        {
            "source": "ae3_runtime",
            "zone_id": 22,
            "event_type": "PID_OUTPUT",
            "channel": "pid",
        }
    )

    assert kicks == []
    assert service_logs == []


def test_critical_background_tasks_health_reports_crashed_task() -> None:
    loop = asyncio.new_event_loop()
    try:
        async def _boom() -> None:
            raise RuntimeError("boom")

        task = loop.create_task(_boom())
        with suppress(RuntimeError):
            loop.run_until_complete(task)

        ok, reason = runtime_app_module._critical_background_tasks_health(
            {"ae3-intent-status-listener": task}
        )
        assert ok is False
        assert reason == "ae3-intent-status-listener:crashed:RuntimeError"
    finally:
        loop.close()


def test_create_app_validates_explicit_runtime_config() -> None:
    class _Config(SimpleNamespace):
        def __init__(self) -> None:
            super().__init__(
                start_cycle_rate_limit_max_requests=30,
                start_cycle_rate_limit_window_sec=10,
                start_cycle_claim_stale_sec=60,
                start_cycle_running_stale_sec=300,
                db_dsn="",
                scheduler_security_baseline_enforce=False,
                scheduler_api_token="test-token",
                scheduler_require_trace_id=False,
            )
            self.validated = 0

        def validate(self) -> None:
            self.validated += 1

    cfg = _Config()
    bundle = SimpleNamespace(
        create_task_from_intent_use_case=None,
        solution_tank_startup_guard_use_case=None,
        get_zone_control_state_use_case=SimpleNamespace(run=lambda **kwargs: None),
        request_manual_step_use_case=None,
        set_control_mode_use_case=None,
        get_zone_automation_state_use_case=SimpleNamespace(run=lambda **kwargs: None),
        task_status_read_model=SimpleNamespace(get_by_task_id=lambda **kwargs: None),
        zone_intent_repository=SimpleNamespace(
            claim_start_cycle=lambda **kwargs: None,
            claim_start_irrigation=lambda **kwargs: None,
            mark_terminal=lambda **kwargs: None,
        ),
        worker=SimpleNamespace(kick=lambda: None, recover_on_startup=lambda: None, drain_health=lambda: (True, "ok")),
        http_client=SimpleNamespace(aclose=lambda: None),
    )
    original_build = runtime_app_module.build_ae3_runtime_bundle
    runtime_app_module.build_ae3_runtime_bundle = lambda **_kwargs: bundle
    app = runtime_app_module.create_app(cfg)
    try:
        assert app is not None
        assert cfg.validated == 1
    finally:
        runtime_app_module.build_ae3_runtime_bundle = original_build


@pytest.mark.asyncio
async def test_runtime_get_routes_validate_zone_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = SimpleNamespace(
        create_task_from_intent_use_case=None,
        solution_tank_startup_guard_use_case=None,
        get_zone_control_state_use_case=SimpleNamespace(run=lambda **kwargs: None),
        request_manual_step_use_case=None,
        set_control_mode_use_case=None,
        get_zone_automation_state_use_case=SimpleNamespace(run=lambda **kwargs: None),
        task_status_read_model=None,
        zone_intent_repository=None,
        worker=SimpleNamespace(kick=lambda: None, recover_on_startup=lambda: None, drain_health=lambda: (True, "ok")),
        http_client=SimpleNamespace(aclose=lambda: None),
    )
    monkeypatch.setattr(runtime_app_module, "build_ae3_runtime_bundle", lambda **_kwargs: bundle)

    async def fetch_fn(query: str, *args: object):
        return []

    monkeypatch.setattr(runtime_app_module, "fetch", fetch_fn)
    app = runtime_app_module.create_app(
        SimpleNamespace(
            start_cycle_rate_limit_max_requests=30,
            start_cycle_rate_limit_window_sec=10,
            start_cycle_claim_stale_sec=60,
            start_cycle_running_stale_sec=300,
            db_dsn="",
            scheduler_security_baseline_enforce=False,
            scheduler_api_token="test-token",
            scheduler_require_trace_id=False,
        )
    )

    state_endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/state")
    control_endpoint = next(
        route.endpoint
        for route in app.routes
        if route.path == "/zones/{zone_id}/control-mode" and "GET" in route.methods
    )

    with pytest.raises(HTTPException) as state_exc:
        await state_endpoint(zone_id=404)
    with pytest.raises(HTTPException) as control_exc:
        await control_endpoint(zone_id=404)

    assert state_exc.value.status_code == 404
    assert control_exc.value.status_code == 404


@pytest.mark.asyncio
async def test_health_ready_returns_503_when_critical_background_task_crashed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = SimpleNamespace(
        create_task_from_intent_use_case=None,
        solution_tank_startup_guard_use_case=None,
        get_zone_control_state_use_case=SimpleNamespace(run=lambda **kwargs: None),
        request_manual_step_use_case=None,
        set_control_mode_use_case=None,
        get_zone_automation_state_use_case=SimpleNamespace(run=lambda **kwargs: None),
        task_status_read_model=None,
        zone_intent_repository=None,
        worker=SimpleNamespace(kick=lambda: None, recover_on_startup=lambda: None, drain_health=lambda: (True, "ok")),
        http_client=SimpleNamespace(aclose=lambda: None),
    )
    monkeypatch.setattr(runtime_app_module, "build_ae3_runtime_bundle", lambda **_kwargs: bundle)

    async def fetch_fn(query: str, *args: object):
        return [{"ready": 1}]

    monkeypatch.setattr(runtime_app_module, "fetch", fetch_fn)
    app = runtime_app_module.create_app(
        SimpleNamespace(
            start_cycle_rate_limit_max_requests=30,
            start_cycle_rate_limit_window_sec=10,
            start_cycle_claim_stale_sec=60,
            start_cycle_running_stale_sec=300,
            db_dsn="",
            scheduler_security_baseline_enforce=False,
            scheduler_api_token="test-token",
            scheduler_require_trace_id=False,
        )
    )

    health_ready = next(route.endpoint for route in app.routes if route.path == "/health/ready")

    async def _boom() -> None:
        raise RuntimeError("listener boom")

    crashed = asyncio.create_task(_boom())
    with suppress(RuntimeError):
        await crashed
    app.state.ae3_critical_background_tasks = {"ae3-intent-status-listener": crashed}

    resp = await health_ready()
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 503
    payload = json.loads(resp.body.decode())
    assert payload["ready"] is False
    assert payload["checks"]["critical_background_tasks"]["ok"] is False
    assert "crashed" in payload["checks"]["critical_background_tasks"]["reason"]
