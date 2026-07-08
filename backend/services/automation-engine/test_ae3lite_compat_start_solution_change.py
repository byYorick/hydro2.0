from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException

from ae3lite.api import bind_start_solution_change_route
from ae3lite.api.contracts import StartSolutionChangeRequest
from ae3lite.application.dto import TaskCreationResult
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import TaskCreateError


def _task(*, task_id: int, zone_id: int, status: str) -> AutomationTask:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return AutomationTask.from_row({
        "id": task_id,
        "zone_id": zone_id,
        "task_type": "solution_change",
        "status": status,
        "idempotency_key": "sched:z5:solution_change",
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
        "intent_id": 92,
        "intent_meta": {},
        "current_stage": "await_operator_drain_confirm",
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

    async def load_workflow_phase(_zone_id: int):
        return "ready"

    async def claim_intent(*, zone_id: int, req, now):
        captured["claim_kwargs"] = {"zone_id": zone_id, "key": req.idempotency_key}
        return {
            "decision": decision,
            "intent": {
                "id": 92,
                "zone_id": zone_id,
                "status": "running",
                "topology": "two_tank",
                "task_type": "solution_change",
            },
        }

    async def create_task_from_intent(**kwargs):
        captured["create_kwargs"] = kwargs
        return creation_result

    bind_start_solution_change_route(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security,
        load_zone_workflow_phase_fn=load_workflow_phase,
        is_start_solution_change_rate_limit_enabled_fn=lambda: False,
        start_solution_change_rate_limit_check_fn=lambda _zone_id: True,
        start_solution_change_rate_limit_window_sec_fn=lambda: 10,
        start_solution_change_rate_limit_max_requests_fn=lambda: 30,
        claim_start_solution_change_intent_fn=claim_intent,
        create_task_from_intent_fn=create_task_from_intent,
        kick_worker_fn=lambda: captured.__setitem__("worker_kicked", int(captured["worker_kicked"]) + 1),
        build_start_cycle_response_fn=lambda **kwargs: {"status": "ok", "data": kwargs},
        mark_intent_terminal_fn=AsyncMock(),
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None),
    )
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/start-solution-change")
    return endpoint, captured


@pytest.mark.asyncio
async def test_compat_start_solution_change_routes_to_canonical_task_creation() -> None:
    endpoint, captured = _bind_test_route(
        creation_result=TaskCreationResult(task=_task(task_id=880, zone_id=5, status="pending"), created=True),
    )

    response = await endpoint(
        zone_id=5,
        request=SimpleNamespace(headers={"authorization": "Bearer test"}),
        req=StartSolutionChangeRequest(
            source="laravel_scheduler",
            idempotency_key="sched:z5:solution_change",
            trigger="operator",
        ),
    )

    assert response["status"] == "ok"
    assert captured["worker_kicked"] == 1
    create_kwargs = captured["create_kwargs"]
    assert isinstance(create_kwargs, dict)
    assert create_kwargs["zone_id"] == 5


@pytest.mark.asyncio
async def test_compat_start_solution_change_translates_active_irrigation_error_to_409() -> None:
    app = FastAPI()

    async def validate_zone(_zone_id: int):
        return None

    async def validate_security(_request):
        return None

    async def load_workflow_phase(_zone_id: int):
        return "ready"

    async def claim_intent(*, zone_id: int, req, now):
        return {
            "decision": "claimed",
            "intent": {
                "id": 92,
                "zone_id": zone_id,
                "status": "claimed",
                "topology": "two_tank",
                "task_type": "solution_change",
            },
        }

    async def create_task_from_intent(**kwargs):
        raise TaskCreateError(
            "solution_change_active_irrigation",
            "Подмена раствора запрещена во время активного полива",
            details={"active_irrigation_task_id": 501, "active_irrigation_task_status": "running"},
        )

    bind_start_solution_change_route(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security,
        load_zone_workflow_phase_fn=load_workflow_phase,
        is_start_solution_change_rate_limit_enabled_fn=lambda: False,
        start_solution_change_rate_limit_check_fn=lambda _zone_id: True,
        start_solution_change_rate_limit_window_sec_fn=lambda: 10,
        start_solution_change_rate_limit_max_requests_fn=lambda: 30,
        claim_start_solution_change_intent_fn=claim_intent,
        create_task_from_intent_fn=create_task_from_intent,
        kick_worker_fn=lambda: None,
        build_start_cycle_response_fn=lambda **kwargs: {"status": "ok", "data": kwargs},
        mark_intent_terminal_fn=AsyncMock(),
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None),
    )
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/start-solution-change")

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=5,
            request=SimpleNamespace(headers={"authorization": "Bearer test"}),
            req=StartSolutionChangeRequest(
                source="laravel_scheduler",
                idempotency_key="sched:z5:solution_change",
                trigger="operator",
            ),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "solution_change_active_irrigation"
    assert detail["active_irrigation_task_id"] == 501
