from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

from ae3lite.api import bind_start_irrigation_route
from ae3lite.api.contracts import StartIrrigationRequest
from ae3lite.application.dto import TaskCreationResult
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import TaskCreateError


def _task(*, task_id: int, zone_id: int, status: str) -> AutomationTask:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return AutomationTask.from_row({
        "id": task_id,
        "zone_id": zone_id,
        "task_type": "irrigation_start",
        "status": status,
        "idempotency_key": "sch:z7:irrigation",
        "scheduled_for": now,
        "due_at": now,
        "claimed_by": None,
        "claimed_at": None,
        "error_code": None,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "topology": "two_tank",
        "intent_source": None,
        "intent_trigger": None,
        "intent_id": 88,
        "intent_meta": {},
        "irrigation_mode": "normal",
        "irrigation_requested_duration_sec": 120,
        "current_stage": "await_ready",
        "workflow_phase": "ready",
        "stage_deadline_at": None,
        "stage_retry_count": 0,
        "stage_entered_at": None,
        "clean_fill_cycle": 0,
        "corr_step": None,
    })


def _bind_test_route(*, creation_result: TaskCreationResult, decision: str = "claimed"):
    app = FastAPI()
    captured: dict[str, object] = {"worker_kicked": 0}

    async def validate_zone(_zone_id: int):
        return None

    async def validate_security(_request):
        return None

    async def claim_intent(*, zone_id: int, req, now):
        captured["claim_kwargs"] = {"zone_id": zone_id, "mode": req.mode, "duration": req.requested_duration_sec}
        return {"decision": decision, "intent": {"id": 88, "zone_id": zone_id, "status": "running"}}

    async def load_zone_workflow_phase(_zone_id: int) -> str | None:
        return "ready"

    async def create_task_from_intent(**kwargs):
        captured["create_kwargs"] = kwargs
        return creation_result

    async def mark_intent_terminal(**kwargs):
        captured["marked_terminal"] = kwargs

    bind_start_irrigation_route(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security,
        is_start_irrigation_rate_limit_enabled_fn=lambda: False,
        start_irrigation_rate_limit_check_fn=lambda _zone_id: True,
        start_irrigation_rate_limit_window_sec_fn=lambda: 10,
        start_irrigation_rate_limit_max_requests_fn=lambda: 30,
        claim_start_irrigation_intent_fn=claim_intent,
        load_zone_workflow_phase_fn=load_zone_workflow_phase,
        create_task_from_intent_fn=create_task_from_intent,
        kick_worker_fn=lambda: captured.__setitem__("worker_kicked", int(captured["worker_kicked"]) + 1),
        build_start_cycle_response_fn=lambda **kwargs: {"status": "ok", "data": kwargs},
        mark_intent_terminal_fn=mark_intent_terminal,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/start-irrigation")
    return endpoint, captured


@pytest.mark.asyncio
async def test_compat_start_irrigation_routes_to_canonical_task_creation() -> None:
    endpoint, captured = _bind_test_route(
        creation_result=TaskCreationResult(task=_task(task_id=777, zone_id=7, status="pending"), created=True),
    )

    response = await endpoint(
        zone_id=7,
        request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-irrigation"}),
        req=StartIrrigationRequest(source="laravel_scheduler", idempotency_key="sch:z7:irrigation", requested_duration_sec=120),
    )

    assert response["status"] == "ok"
    assert response["data"]["task_id"] == "777"
    assert response["data"]["accepted"] is True
    assert captured["worker_kicked"] == 1
    assert captured["claim_kwargs"] == {"zone_id": 7, "mode": "normal", "duration": 120}


@pytest.mark.asyncio
async def test_compat_start_irrigation_translates_zone_busy_to_409() -> None:
    endpoint, _captured = _bind_test_route(
        creation_result=TaskCreationResult(task=_task(task_id=777, zone_id=7, status="pending"), created=True),
        decision="zone_busy",
    )

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-irrigation-busy"}),
            req=StartIrrigationRequest(source="laravel_scheduler", idempotency_key="sch:z7:irrigation"),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "start_irrigation_zone_busy"


@pytest.mark.asyncio
async def test_compat_start_irrigation_translates_create_task_busy_error_to_409() -> None:
    app = FastAPI()

    async def validate_zone(_zone_id: int):
        return None

    async def validate_security(_request):
        return None

    async def claim_intent(*, zone_id: int, req, now):
        return {"decision": "claimed", "intent": {"id": 88, "zone_id": zone_id, "status": "claimed"}}

    async def load_zone_workflow_phase(_zone_id: int) -> str | None:
        return "ready"

    async def create_task_from_intent(**kwargs):
        raise TaskCreateError("start_cycle_zone_busy", "busy", details={"active_task_id": 99})

    async def mark_intent_terminal(**kwargs):
        return None

    bind_start_irrigation_route(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security,
        is_start_irrigation_rate_limit_enabled_fn=lambda: False,
        start_irrigation_rate_limit_check_fn=lambda _zone_id: True,
        start_irrigation_rate_limit_window_sec_fn=lambda: 10,
        start_irrigation_rate_limit_max_requests_fn=lambda: 30,
        claim_start_irrigation_intent_fn=claim_intent,
        load_zone_workflow_phase_fn=load_zone_workflow_phase,
        create_task_from_intent_fn=create_task_from_intent,
        kick_worker_fn=lambda: None,
        build_start_cycle_response_fn=lambda **kwargs: {"status": "ok", "data": kwargs},
        mark_intent_terminal_fn=mark_intent_terminal,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/start-irrigation")

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-irrigation"}),
            req=StartIrrigationRequest(source="laravel_scheduler", idempotency_key="sch:z7:irrigation"),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "start_irrigation_zone_busy"
    assert detail["active_task_id"] == 99


@pytest.mark.asyncio
async def test_compat_start_irrigation_translates_intent_terminal_task_create_error_to_409() -> None:
    app = FastAPI()

    async def validate_zone(_zone_id: int):
        return None

    async def validate_security(_request):
        return None

    async def claim_intent(*, zone_id: int, req, now):
        return {"decision": "claimed", "intent": {"id": 88, "zone_id": zone_id, "status": "claimed"}}

    async def load_zone_workflow_phase(_zone_id: int) -> str | None:
        return "ready"

    async def create_task_from_intent(**kwargs):
        raise TaskCreateError(
            "start_cycle_intent_terminal",
            "intent is terminal",
            details={"hint": "already_done"},
        )

    async def mark_intent_terminal(**kwargs):
        return None

    bind_start_irrigation_route(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security,
        is_start_irrigation_rate_limit_enabled_fn=lambda: False,
        start_irrigation_rate_limit_check_fn=lambda _zone_id: True,
        start_irrigation_rate_limit_window_sec_fn=lambda: 10,
        start_irrigation_rate_limit_max_requests_fn=lambda: 30,
        claim_start_irrigation_intent_fn=claim_intent,
        load_zone_workflow_phase_fn=load_zone_workflow_phase,
        create_task_from_intent_fn=create_task_from_intent,
        kick_worker_fn=lambda: None,
        build_start_cycle_response_fn=lambda **kwargs: {"status": "ok", "data": kwargs},
        mark_intent_terminal_fn=mark_intent_terminal,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/start-irrigation")

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-terminal"}),
            req=StartIrrigationRequest(source="laravel_scheduler", idempotency_key="sch:z7:irrigation-term"),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "start_irrigation_intent_terminal"
    assert detail["zone_id"] == 7
    assert detail["idempotency_key"] == "sch:z7:irrigation-term"
    assert detail["hint"] == "already_done"


@pytest.mark.asyncio
async def test_compat_start_irrigation_rate_limit_returns_429() -> None:
    app = FastAPI()

    async def validate_zone(_zone_id: int):
        return None

    async def validate_security(_request):
        return None

    async def claim_intent(*, zone_id: int, req, now):
        return {"decision": "claimed", "intent": {"id": 88, "zone_id": zone_id, "status": "claimed"}}

    async def load_zone_workflow_phase(_zone_id: int) -> str | None:
        return "ready"

    async def create_task_from_intent(**kwargs):
        raise AssertionError("create_task_from_intent must not be called when rate-limited")

    async def mark_intent_terminal(**kwargs):
        return None

    bind_start_irrigation_route(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security,
        is_start_irrigation_rate_limit_enabled_fn=lambda: True,
        start_irrigation_rate_limit_check_fn=lambda _zone_id: False,
        start_irrigation_rate_limit_window_sec_fn=lambda: 12,
        start_irrigation_rate_limit_max_requests_fn=lambda: 3,
        claim_start_irrigation_intent_fn=claim_intent,
        load_zone_workflow_phase_fn=load_zone_workflow_phase,
        create_task_from_intent_fn=create_task_from_intent,
        kick_worker_fn=lambda: None,
        build_start_cycle_response_fn=lambda **kwargs: {"status": "ok", "data": kwargs},
        mark_intent_terminal_fn=mark_intent_terminal,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/start-irrigation")

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-irrigation"}),
            req=StartIrrigationRequest(source="laravel_scheduler", idempotency_key="sch:z7:irrigation"),
        )

    assert exc.value.status_code == 429
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "start_irrigation_rate_limited"


@pytest.mark.asyncio
async def test_compat_start_irrigation_blocks_when_zone_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    captured: dict[str, object] = {"events": []}

    async def validate_zone(_zone_id: int):
        return None

    async def validate_security(_request):
        return None

    async def claim_intent(*, zone_id: int, req, now):
        captured["claim_called"] = True
        return {"decision": "claimed", "intent": {"id": 88, "zone_id": zone_id, "status": "claimed"}}

    async def load_zone_workflow_phase(_zone_id: int) -> str | None:
        return "idle"

    async def create_task_from_intent(**kwargs):
        raise AssertionError("create_task_from_intent must not be called when setup is pending")

    async def mark_intent_terminal(**kwargs):
        captured["marked_terminal"] = kwargs

    async def fake_create_zone_event(zone_id: int, event_type: str, payload: dict):
        captured["events"] = list(captured["events"]) + [{"zone_id": zone_id, "event_type": event_type, "payload": payload}]

    monkeypatch.setattr("ae3lite.api.compat_endpoints.create_zone_event", fake_create_zone_event)

    bind_start_irrigation_route(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security,
        is_start_irrigation_rate_limit_enabled_fn=lambda: False,
        start_irrigation_rate_limit_check_fn=lambda _zone_id: True,
        start_irrigation_rate_limit_window_sec_fn=lambda: 10,
        start_irrigation_rate_limit_max_requests_fn=lambda: 30,
        claim_start_irrigation_intent_fn=claim_intent,
        load_zone_workflow_phase_fn=load_zone_workflow_phase,
        create_task_from_intent_fn=create_task_from_intent,
        kick_worker_fn=lambda: None,
        build_start_cycle_response_fn=lambda **kwargs: {"status": "ok", "data": kwargs},
        mark_intent_terminal_fn=mark_intent_terminal,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/start-irrigation")

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-irrigation-setup"}),
            req=StartIrrigationRequest(source="laravel_scheduler", idempotency_key="sch:z7:irrigation"),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "start_irrigation_setup_pending"
    assert detail["workflow_phase"] == "idle"
    assert captured["events"] and captured["events"][0]["event_type"] == "IRRIGATION_BLOCKED_SETUP_PENDING"
    assert "claim_called" not in captured


@pytest.mark.asyncio
async def test_compat_start_irrigation_blocks_when_workflow_phase_row_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    captured: dict[str, object] = {"events": []}

    async def validate_zone(_zone_id: int):
        return None

    async def validate_security(_request):
        return None

    async def claim_intent(*, zone_id: int, req, now):
        captured["claim_called"] = True
        return {"decision": "claimed", "intent": {"id": 88, "zone_id": zone_id, "status": "claimed"}}

    async def load_zone_workflow_phase(_zone_id: int) -> str | None:
        return None

    async def create_task_from_intent(**kwargs):
        raise AssertionError("create_task_from_intent must not be called when workflow phase row is missing")

    async def mark_intent_terminal(**kwargs):
        captured["marked_terminal"] = kwargs

    async def fake_create_zone_event(zone_id: int, event_type: str, payload: dict):
        captured["events"] = list(captured["events"]) + [{"zone_id": zone_id, "event_type": event_type, "payload": payload}]

    monkeypatch.setattr("ae3lite.api.compat_endpoints.create_zone_event", fake_create_zone_event)

    bind_start_irrigation_route(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security,
        is_start_irrigation_rate_limit_enabled_fn=lambda: False,
        start_irrigation_rate_limit_check_fn=lambda _zone_id: True,
        start_irrigation_rate_limit_window_sec_fn=lambda: 10,
        start_irrigation_rate_limit_max_requests_fn=lambda: 30,
        claim_start_irrigation_intent_fn=claim_intent,
        load_zone_workflow_phase_fn=load_zone_workflow_phase,
        create_task_from_intent_fn=create_task_from_intent,
        kick_worker_fn=lambda: None,
        build_start_cycle_response_fn=lambda **kwargs: {"status": "ok", "data": kwargs},
        mark_intent_terminal_fn=mark_intent_terminal,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/start-irrigation")

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-irrigation-missing"}),
            req=StartIrrigationRequest(source="laravel_scheduler", idempotency_key="sch:z7:irrigation"),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "start_irrigation_setup_pending"
    assert detail["workflow_phase"] == "missing"
    assert captured["events"] and captured["events"][0]["event_type"] == "IRRIGATION_BLOCKED_SETUP_PENDING"
    payload = captured["events"][0]["payload"]
    assert payload["workflow_phase"] == "missing"
    assert "claim_called" not in captured
