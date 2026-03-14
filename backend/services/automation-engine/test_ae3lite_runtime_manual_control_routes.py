from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ae3lite.domain.errors import ManualControlError
from ae3lite.runtime.app import ControlModeRequest, ManualStepRequest, create_app


class _Worker:
    def __init__(self) -> None:
        self.kicks = 0

    def kick(self) -> None:
        self.kicks += 1


class _UseCase:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


def _app(monkeypatch: pytest.MonkeyPatch):
    worker = _Worker()
    get_control = _UseCase(
        result={
            "control_mode": "manual",
            "available_modes": ["auto", "semi", "manual"],
            "current_stage": "startup",
            "workflow_phase": "idle",
            "pending_manual_step": None,
            "allowed_manual_steps": ["clean_fill_start", "solution_fill_start"],
        }
    )
    request_manual = _UseCase(
        result={
            "zone_id": 7,
            "task_id": "321",
            "manual_step": "clean_fill_start",
            "pending_manual_step": "clean_fill_start",
            "control_mode": "manual",
            "current_stage": "startup",
            "workflow_phase": "idle",
        }
    )
    set_control_mode = _UseCase(result="manual")
    bundle = SimpleNamespace(
        create_task_from_intent_use_case=None,
        solution_tank_startup_guard_use_case=None,
        get_zone_control_state_use_case=get_control,
        request_manual_step_use_case=request_manual,
        set_control_mode_use_case=set_control_mode,
        get_zone_automation_state_use_case=None,
        task_status_read_model=None,
        zone_intent_repository=None,
        worker=worker,
        http_client=SimpleNamespace(aclose=lambda: None),
    )

    monkeypatch.setattr("ae3lite.runtime.app.build_ae3_runtime_bundle", lambda **_kwargs: bundle)

    async def fetch_fn(query: str, *args: object):
        if "FROM zones" in query:
            return [{"id": args[0]}]
        return []

    monkeypatch.setattr("ae3lite.runtime.app.fetch", fetch_fn)
    app = create_app(
        SimpleNamespace(
            start_cycle_rate_limit_max_requests=30,
            start_cycle_rate_limit_window_sec=10,
            start_cycle_claim_stale_sec=60,
            start_cycle_running_stale_sec=300,
            db_dsn="",
            scheduler_security_baseline_enforce=True,
            scheduler_api_token="test-token",
            scheduler_require_trace_id=True,
        )
    )
    return app, bundle


@pytest.mark.asyncio
async def test_runtime_control_mode_get_returns_status_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _bundle = _app(monkeypatch)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/control-mode" and "GET" in route.methods)
    response = await endpoint(zone_id=7)
    assert response["status"] == "ok"
    assert response["data"]["available_modes"] == ["auto", "semi", "manual"]


@pytest.mark.asyncio
async def test_runtime_manual_step_route_returns_numeric_task_id(monkeypatch: pytest.MonkeyPatch) -> None:
    app, bundle = _app(monkeypatch)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/manual-step")
    response = await endpoint(
        zone_id=7,
        request=SimpleNamespace(headers={"authorization": "Bearer test-token", "x-trace-id": "trace-1"}),
        req=ManualStepRequest(manual_step="clean_fill_start"),
    )
    assert response["status"] == "ok"
    assert response["data"]["task_id"] == "321"
    assert bundle.worker.kicks == 1


@pytest.mark.asyncio
async def test_runtime_manual_step_route_maps_business_error(monkeypatch: pytest.MonkeyPatch) -> None:
    app, bundle = _app(monkeypatch)
    bundle.request_manual_step_use_case.error = ManualControlError(
        "manual_step_forbidden_in_auto_mode",
        "manual step disabled in auto mode",
        status_code=409,
        details={"zone_id": 7},
    )
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/manual-step")
    with pytest.raises(HTTPException) as exc_info:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test-token", "x-trace-id": "trace-1"}),
            req=ManualStepRequest(manual_step="clean_fill_start"),
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "manual_step_forbidden_in_auto_mode"


@pytest.mark.asyncio
async def test_runtime_control_mode_post_requires_security_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _bundle = _app(monkeypatch)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/control-mode" and "POST" in route.methods)
    with pytest.raises(HTTPException) as exc_info:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={}),
            req=ControlModeRequest(control_mode="manual"),
        )
    assert exc_info.value.status_code == 401
