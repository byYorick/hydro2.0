from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

from ae2lite.api_runtime_zone_routes import bind_zone_routes


class _DummyWorkflowStateStore:
    def __init__(self, *, workflow_phase: str = "idle", control_mode: str = "manual") -> None:
        self.workflow_phase = workflow_phase
        self.control_mode = control_mode

    async def get(self, _zone_id: int):
        return {"workflow_phase": self.workflow_phase, "payload_normalized": {"control_mode": self.control_mode}}

    async def set(self, **_kwargs):
        return None


def _build_test_app(*, validate_security_fn, latest_zone_task=None, workflow_phase: str = "idle", control_mode: str = "manual"):
    app = FastAPI()
    store = _DummyWorkflowStateStore(workflow_phase=workflow_phase, control_mode=control_mode)
    latest_task = latest_zone_task or {"payload": {"config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}}}

    async def validate_zone(_zone_id: int):
        return None

    async def load_latest_zone_task(_zone_id: int):
        return latest_task

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
    )
    return app


def _bind_test_routes(*, validate_security_fn, latest_zone_task=None, workflow_phase: str = "idle", control_mode: str = "manual"):
    app = _build_test_app(
        validate_security_fn=validate_security_fn,
        latest_zone_task=latest_zone_task,
        workflow_phase=workflow_phase,
        control_mode=control_mode,
    )
    return (
        next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/state"),
        next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/control-mode" and "GET" in route.methods),
        next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/control-mode" and "POST" in route.methods),
        next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/manual-step"),
    )


@pytest.mark.asyncio
async def test_control_mode_write_requires_security_baseline():
    async def validate_security(_request):
        raise HTTPException(status_code=401, detail="unauthorized")

    (_, _, set_control_mode, _) = _bind_test_routes(validate_security_fn=validate_security)

    with pytest.raises(HTTPException) as exc:
        await set_control_mode(
            zone_id=3,
            request=SimpleNamespace(headers={}),
            payload={"control_mode": "manual", "source": "frontend"},
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_manual_step_requires_security_baseline():
    async def validate_security(_request):
        raise HTTPException(status_code=401, detail="unauthorized")

    (_, _, _, manual_step) = _bind_test_routes(validate_security_fn=validate_security)

    with pytest.raises(HTTPException) as exc:
        await manual_step(
            zone_id=3,
            request=SimpleNamespace(headers={}),
            payload={"manual_step": "clean_fill_start", "source": "frontend"},
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_manual_step_returns_409_when_zone_has_active_task():
    async def validate_security(_request):
        return None

    (_, _, _, manual_step) = _bind_test_routes(
        validate_security_fn=validate_security,
        latest_zone_task={
            "task_id": "st-active",
            "status": "running",
            "payload": {"config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}},
        },
    )

    with pytest.raises(HTTPException) as exc:
        await manual_step(
            zone_id=3,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "t1"}),
            payload={"manual_step": "clean_fill_start", "source": "frontend"},
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("code") == "manual_step_zone_busy"
    assert detail.get("zone_id") == 3
    assert detail.get("active_task_id") == "st-active"
    assert detail.get("active_task_status") == "running"


@pytest.mark.asyncio
async def test_manual_step_accepts_idle_phase_in_manual_mode():
    async def validate_security(_request):
        return None

    (_, _, _, manual_step) = _bind_test_routes(
        validate_security_fn=validate_security,
        latest_zone_task={
            "task_id": "st-completed",
            "status": "completed",
            "payload": {"config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}},
        },
        workflow_phase="idle",
        control_mode="manual",
    )

    response = await manual_step(
        zone_id=3,
        request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "t1"}),
        payload={"manual_step": "clean_fill_start", "source": "frontend"},
    )

    data = response.get("data") if isinstance(response, dict) else {}
    assert response.get("status") == "ok"
    assert data.get("manual_step") == "clean_fill_start"
    assert data.get("workflow_phase") == "idle"


@pytest.mark.asyncio
async def test_manual_step_returns_409_for_idle_phase_in_semi_mode():
    async def validate_security(_request):
        return None

    (_, _, _, manual_step) = _bind_test_routes(
        validate_security_fn=validate_security,
        latest_zone_task={
            "task_id": "st-completed",
            "status": "completed",
            "payload": {"config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}},
        },
        workflow_phase="idle",
        control_mode="semi",
    )

    with pytest.raises(HTTPException) as exc:
        await manual_step(
            zone_id=3,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "t1"}),
            payload={"manual_step": "clean_fill_start", "source": "frontend"},
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("code") == "manual_step_zone_inactive"
    assert detail.get("workflow_phase") == "idle"


@pytest.mark.asyncio
async def test_manual_step_returns_409_when_step_not_allowed_for_current_phase():
    async def validate_security(_request):
        return None

    (_, _, _, manual_step) = _bind_test_routes(
        validate_security_fn=validate_security,
        latest_zone_task={
            "task_id": "st-completed",
            "status": "queued",
            "payload": {"config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}},
        },
        workflow_phase="tank_filling",
        control_mode="manual",
    )

    with pytest.raises(HTTPException) as exc:
        await manual_step(
            zone_id=3,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "t1"}),
            payload={"manual_step": "irrigation_recovery_start", "source": "frontend"},
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("code") == "manual_step_not_allowed_for_phase"
    assert detail.get("workflow_phase") == "tank_filling"
    assert "clean_fill_start" in (detail.get("allowed_manual_steps") or [])


@pytest.mark.asyncio
async def test_manual_step_treats_terminal_task_with_active_phase_as_idle_for_manual_mode():
    async def validate_security(_request):
        return None

    (_, _, _, manual_step) = _bind_test_routes(
        validate_security_fn=validate_security,
        latest_zone_task={
            "task_id": "st-completed",
            "status": "completed",
            "payload": {"config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}},
        },
        workflow_phase="irrig_recirc",
        control_mode="manual",
    )

    response = await manual_step(
        zone_id=3,
        request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "t1"}),
        payload={"manual_step": "clean_fill_start", "source": "frontend"},
    )

    data = response.get("data") if isinstance(response, dict) else {}
    assert response.get("status") == "ok"
    assert data.get("manual_step") == "clean_fill_start"
    assert data.get("workflow_phase") == "idle"


@pytest.mark.asyncio
async def test_state_uses_effective_idle_phase_when_terminal_task_detected():
    async def validate_security(_request):
        return None

    (state_route, _, _, _) = _bind_test_routes(
        validate_security_fn=validate_security,
        latest_zone_task={
            "task_id": "st-completed",
            "status": "completed",
            "payload": {"config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}},
        },
        workflow_phase="irrig_recirc",
        control_mode="semi",
    )

    response = await state_route(zone_id=3)

    assert response.get("control_mode") == "semi"
    assert response.get("workflow_phase") == "idle"
    assert response.get("allowed_manual_steps") == []


@pytest.mark.asyncio
async def test_control_mode_get_returns_phase_aware_allowed_manual_steps():
    async def validate_security(_request):
        return None

    (_, get_control_mode, _, _) = _bind_test_routes(
        validate_security_fn=validate_security,
        workflow_phase="tank_recirc",
        control_mode="manual",
    )

    response = await get_control_mode(zone_id=3)
    data = response.get("data") if isinstance(response, dict) else {}

    assert data.get("control_mode") == "manual"
    assert data.get("workflow_phase") == "tank_recirc"
    assert data.get("allowed_manual_steps") == [
        "prepare_recirculation_start",
        "prepare_recirculation_stop",
    ]


@pytest.mark.asyncio
async def test_control_mode_get_returns_all_manual_steps_for_manual_idle():
    async def validate_security(_request):
        return None

    (_, get_control_mode, _, _) = _bind_test_routes(
        validate_security_fn=validate_security,
        workflow_phase="idle",
        control_mode="manual",
    )

    response = await get_control_mode(zone_id=3)
    data = response.get("data") if isinstance(response, dict) else {}

    assert data.get("control_mode") == "manual"
    assert data.get("workflow_phase") == "idle"
    assert data.get("allowed_manual_steps") == [
        "clean_fill_start",
        "clean_fill_stop",
        "solution_fill_start",
        "solution_fill_stop",
        "prepare_recirculation_start",
        "prepare_recirculation_stop",
        "irrigation_recovery_start",
        "irrigation_recovery_stop",
    ]


@pytest.mark.asyncio
async def test_start_relay_autotune_requires_security_baseline():
    async def validate_security(_request):
        raise HTTPException(status_code=401, detail="unauthorized")

    app = _build_test_app(validate_security_fn=validate_security)
    start_relay_autotune = next(
        route.endpoint
        for route in app.routes
        if route.path == "/zones/{zone_id}/start-relay-autotune"
    )

    with pytest.raises(HTTPException) as exc:
        await start_relay_autotune(
            zone_id=3,
            request=SimpleNamespace(headers={}),
            payload={"pid_type": "ph"},
        )

    assert exc.value.status_code == 401
