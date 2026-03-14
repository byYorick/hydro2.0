from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

from ae3lite.api import bind_start_cycle_route
from ae3lite.api.contracts import StartCycleRequest
from ae3lite.application.dto import TaskCreationResult
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import TaskCreateError


def _task(*, task_id: int, zone_id: int, status: str) -> AutomationTask:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return AutomationTask.from_row({
        "id": task_id, "zone_id": zone_id, "task_type": "cycle_start", "status": status,
        "idempotency_key": "sch:z7:test", "scheduled_for": now, "due_at": now,
        "claimed_by": None, "claimed_at": None,
        "error_code": None, "error_message": None,
        "created_at": now, "updated_at": now, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": 77, "intent_meta": {},
        "current_stage": "startup", "workflow_phase": "idle",
        "stage_deadline_at": None, "stage_retry_count": 0, "stage_entered_at": None,
        "clean_fill_cycle": 0, "corr_step": None,
    })


def _bind_test_route(
    *,
    creation_result: TaskCreationResult | None,
    decision: str = "claimed",
    create_error: Exception | None = None,
    guard_error: Exception | None = None,
):
    app = FastAPI()
    captured: dict[str, object] = {"worker_kicked": 0, "guard_calls": 0, "claim_calls": 0}

    async def validate_zone(_zone_id: int):
        return None

    async def validate_security(_request):
        return None

    async def claim_intent(*, zone_id: int, req, now):
        captured["claim_calls"] = int(captured["claim_calls"]) + 1
        return {"decision": decision, "intent": {"id": 77, "zone_id": zone_id, "status": "running"}}

    async def create_task_from_intent(**kwargs):
        captured["create_kwargs"] = kwargs
        if create_error is not None:
            raise create_error
        assert creation_result is not None
        return creation_result

    async def ensure_solution_tank_startup_reset(**kwargs):
        captured["guard_calls"] = int(captured["guard_calls"]) + 1
        captured["guard_kwargs"] = kwargs
        if guard_error is not None:
            raise guard_error
        return {"reset": False}

    def kick_worker():
        captured["worker_kicked"] = int(captured["worker_kicked"]) + 1

    async def mark_intent_terminal(**kwargs):
        captured["marked_terminal"] = kwargs

    async def mark_intent_terminal(**kwargs):
        captured["marked_terminal"] = kwargs

    bind_start_cycle_route(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security,
        is_start_cycle_rate_limit_enabled_fn=lambda: False,
        start_cycle_rate_limit_check_fn=lambda _zone_id: True,
        start_cycle_rate_limit_window_sec_fn=lambda: 10,
        start_cycle_rate_limit_max_requests_fn=lambda: 30,
        claim_start_cycle_intent_fn=claim_intent,
        create_task_from_intent_fn=create_task_from_intent,
        ensure_solution_tank_startup_reset_fn=ensure_solution_tank_startup_reset,
        kick_worker_fn=kick_worker,
        build_start_cycle_response_fn=lambda **kwargs: {"status": "ok", "data": kwargs},
        mark_intent_terminal_fn=mark_intent_terminal,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/start-cycle")
    return endpoint, captured


@pytest.mark.asyncio
async def test_compat_start_cycle_routes_ae3_zone_to_canonical_task_creation() -> None:
    endpoint, captured = _bind_test_route(
        creation_result=TaskCreationResult(task=_task(task_id=321, zone_id=7, status="pending"), created=True),
    )

    response = await endpoint(
        zone_id=7,
        request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-ae3"}),
        req=StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z7:test"),
    )

    assert response["status"] == "ok"
    assert response["data"]["task_id"] == "321"
    assert response["data"]["accepted"] is True
    assert response["data"]["runner_state"] == "active"
    assert response["data"]["is_duplicate"] is False
    assert captured["worker_kicked"] == 1
    assert captured["guard_calls"] == 1
    assert captured["guard_kwargs"] == {"zone_id": 7}


@pytest.mark.asyncio
async def test_compat_start_cycle_returns_terminal_payload_for_terminal_ae3_task() -> None:
    endpoint, _captured = _bind_test_route(
        creation_result=TaskCreationResult(task=_task(task_id=654, zone_id=7, status="failed"), created=False),
        decision="terminal",
    )

    response = await endpoint(
        zone_id=7,
        request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-terminal"}),
        req=StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z7:test"),
    )

    assert response["data"]["task_id"] == "654"
    assert response["data"]["accepted"] is False
    assert response["data"]["runner_state"] == "terminal"
    assert response["data"]["task_status"] == "failed"
    assert _captured["create_kwargs"]["allow_create"] is False


@pytest.mark.asyncio
async def test_compat_start_cycle_translates_ae3_busy_error_to_409() -> None:
    app = FastAPI()

    async def validate_zone(_zone_id: int):
        return None

    async def validate_security(_request):
        return None

    async def claim_intent(*, zone_id: int, req, now):
        return {"decision": "claimed", "intent": {"id": 77, "zone_id": zone_id, "status": "claimed"}}

    async def create_task_from_intent(**kwargs):
        from ae3lite.domain.errors import TaskCreateError

        raise TaskCreateError("start_cycle_zone_busy", "busy", details={"active_task_id": 99, "active_task_status": "running"})

    async def mark_intent_terminal(**kwargs):
        return None

    bind_start_cycle_route(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security,
        is_start_cycle_rate_limit_enabled_fn=lambda: False,
        start_cycle_rate_limit_check_fn=lambda _zone_id: True,
        start_cycle_rate_limit_window_sec_fn=lambda: 10,
        start_cycle_rate_limit_max_requests_fn=lambda: 30,
        claim_start_cycle_intent_fn=claim_intent,
        create_task_from_intent_fn=create_task_from_intent,
        ensure_solution_tank_startup_reset_fn=None,
        kick_worker_fn=lambda: None,
        build_start_cycle_response_fn=lambda **kwargs: {"status": "ok", "data": kwargs},
        mark_intent_terminal_fn=mark_intent_terminal,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/start-cycle")

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-busy"}),
            req=StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z7:test"),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "start_cycle_zone_busy"
    assert detail["active_task_id"] == 99


@pytest.mark.asyncio
async def test_compat_start_cycle_terminal_intent_missing_task_returns_409_fail_closed() -> None:
    endpoint, captured = _bind_test_route(
        creation_result=None,
        decision="terminal",
        create_error=TaskCreateError(
            "start_cycle_intent_terminal",
            "terminal intent has no canonical task",
            details={"idempotency_key": "sch:z7:test"},
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-terminal-missing"}),
            req=StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z7:test"),
        )

    assert captured["create_kwargs"]["allow_create"] is False
    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "start_cycle_intent_terminal"
    assert detail["zone_id"] == 7


@pytest.mark.asyncio
async def test_compat_start_cycle_guard_failure_returns_503_before_claiming_intent() -> None:
    endpoint, captured = _bind_test_route(
        creation_result=None,
        guard_error=RuntimeError("db offline"),
    )

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-guard-fail"}),
            req=StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z7:guardfail"),
        )

    assert captured["guard_calls"] == 1
    assert captured["claim_calls"] == 0
    assert "create_kwargs" not in captured
    assert exc.value.status_code == 503
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "start_cycle_solution_tank_guard_failed"
    assert detail["zone_id"] == 7
