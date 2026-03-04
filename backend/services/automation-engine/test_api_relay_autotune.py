from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

import ae2lite.api_runtime_zone_routes as zone_routes
from ae2lite.api_runtime_zone_routes import bind_zone_routes


class _WorkflowStateStoreStub:
    def __init__(self, phase: str):
        self.phase = phase

    async def get(self, _zone_id: int):
        return {"workflow_phase": self.phase, "payload_normalized": {"control_mode": "manual"}}

    async def set(self, **_kwargs):
        return None


class _ControllerStub:
    def __init__(self):
        self._autotune_by_zone = {}
        self._pid_by_zone = {}
        self._last_target_by_zone = {}


class _ZoneServiceStub:
    def __init__(self):
        self.ph_controller = _ControllerStub()
        self.ec_controller = _ControllerStub()


class _AutotuneResultStub:
    def __init__(self):
        self.ku = 14.2
        self.tu_sec = 95.0
        self.kp = 6.7
        self.ki = 0.11
        self.oscillation_amplitude = 0.15
        self.cycles_detected = 3
        self.tuned_at = "2026-03-04T12:00:00Z"


class _AutotunerStub:
    def __init__(self, *, complete: bool = False, timed_out: bool = False, running_cycles: int = 0):
        self.is_complete = complete
        self.is_timed_out = timed_out
        self.result = _AutotuneResultStub() if complete else None
        self.start_time_sec = 100.0
        self._zero_crossings = running_cycles * 2
        self.config = SimpleNamespace(min_cycles=3, max_duration_sec=7200.0)


def _build_app(*, phase: str, validate_security_fn, zone_service):
    app = FastAPI()
    store = _WorkflowStateStoreStub(phase=phase)

    async def validate_zone(_zone_id: int):
        return None

    async def load_latest_zone_task(_zone_id: int):
        return {"payload": {"config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}}}

    async def create_scheduler_task(_req):
        return {"task_id": "st-manual"}, False

    async def execute_scheduler_task(_task_id, _req, _trace_id):
        return None

    def spawn_background_task(coro, **_kwargs):
        coro.close()
        return None

    async def fetch_fn(*_args, **_kwargs):
        return []

    async def create_zone_event_fn(_zone_id, _event_type, _details):
        return None

    bind_zone_routes(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security_fn,
        load_latest_zone_task_fn=load_latest_zone_task,
        create_scheduler_task_fn=create_scheduler_task,
        execute_scheduler_task_fn=execute_scheduler_task,
        spawn_background_task_fn=spawn_background_task,
        workflow_state_store=store,
        default_topology="two_tank_drip_substrate_trays",
        fetch_fn=fetch_fn,
        create_zone_event_fn=create_zone_event_fn,
        get_trace_id_fn=lambda: None,
        logger=SimpleNamespace(info=lambda *_a, **_k: None, warning=lambda *_a, **_k: None),
        get_zone_service_fn=lambda: zone_service,
    )
    return app


@pytest.mark.asyncio
async def test_start_relay_autotune_starts_for_active_zone():
    async def validate_security(_request):
        return None

    zone_service = _ZoneServiceStub()
    app = _build_app(phase="tank_filling", validate_security_fn=validate_security, zone_service=zone_service)
    start_relay_autotune = next(
        route.endpoint
        for route in app.routes
        if route.path == "/zones/{zone_id}/start-relay-autotune"
    )

    response = await start_relay_autotune(
        zone_id=9,
        request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "t1"}),
        payload={"pid_type": "ph"},
    )

    assert response == {"status": "started", "zone_id": 9, "pid_type": "ph"}
    assert 9 in zone_service.ph_controller._autotune_by_zone


@pytest.mark.asyncio
async def test_start_relay_autotune_rejects_inactive_zone():
    async def validate_security(_request):
        return None

    zone_service = _ZoneServiceStub()
    app = _build_app(phase="idle", validate_security_fn=validate_security, zone_service=zone_service)
    start_relay_autotune = next(
        route.endpoint
        for route in app.routes
        if route.path == "/zones/{zone_id}/start-relay-autotune"
    )

    with pytest.raises(HTTPException) as exc:
        await start_relay_autotune(
            zone_id=9,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "t1"}),
            payload={"pid_type": "ph"},
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("code") == "relay_autotune_zone_inactive"


@pytest.mark.asyncio
async def test_relay_autotune_status_returns_idle_for_both_types():
    async def validate_security(_request):
        return None

    zone_service = _ZoneServiceStub()
    app = _build_app(phase="tank_filling", validate_security_fn=validate_security, zone_service=zone_service)
    status_route = next(
        route.endpoint
        for route in app.routes
        if route.path == "/zones/{zone_id}/relay-autotune/status"
    )

    payload = await status_route(zone_id=4)
    assert payload["status"] == "ok"
    assert payload["zone_id"] == 4
    assert payload["data"]["ph"]["status"] == "idle"
    assert payload["data"]["ec"]["status"] == "idle"


@pytest.mark.asyncio
async def test_relay_autotune_status_running_returns_progress_for_pid_type(monkeypatch):
    async def validate_security(_request):
        return None

    monkeypatch.setattr(zone_routes.time, "monotonic", lambda: 145.0)
    zone_service = _ZoneServiceStub()
    zone_service.ph_controller._autotune_by_zone[9] = _AutotunerStub(running_cycles=2)
    app = _build_app(phase="tank_filling", validate_security_fn=validate_security, zone_service=zone_service)
    status_route = next(
        route.endpoint
        for route in app.routes
        if route.path == "/zones/{zone_id}/relay-autotune/status"
    )

    payload = await status_route(zone_id=9, pid_type="ph")
    assert payload["zone_id"] == 9
    assert payload["pid_type"] == "ph"
    assert payload["status"] == "running"
    assert payload["progress"]["cycles_detected"] == 2
    assert payload["progress"]["elapsed_sec"] == pytest.approx(45.0)


@pytest.mark.asyncio
async def test_relay_autotune_status_complete_returns_result():
    async def validate_security(_request):
        return None

    zone_service = _ZoneServiceStub()
    zone_service.ec_controller._autotune_by_zone[5] = _AutotunerStub(complete=True)
    app = _build_app(phase="tank_filling", validate_security_fn=validate_security, zone_service=zone_service)
    status_route = next(
        route.endpoint
        for route in app.routes
        if route.path == "/zones/{zone_id}/relay-autotune/status"
    )

    payload = await status_route(zone_id=5, pid_type="ec")
    assert payload["status"] == "complete"
    assert payload["result"]["source"] == "relay_autotune"
    assert payload["result"]["ku"] == pytest.approx(14.2)
    assert payload["result"]["ki"] == pytest.approx(0.11)


@pytest.mark.asyncio
async def test_relay_autotune_status_rejects_invalid_pid_type():
    async def validate_security(_request):
        return None

    zone_service = _ZoneServiceStub()
    app = _build_app(phase="tank_filling", validate_security_fn=validate_security, zone_service=zone_service)
    status_route = next(
        route.endpoint
        for route in app.routes
        if route.path == "/zones/{zone_id}/relay-autotune/status"
    )

    with pytest.raises(HTTPException) as exc:
        await status_route(zone_id=5, pid_type="climate")

    assert exc.value.status_code == 422
