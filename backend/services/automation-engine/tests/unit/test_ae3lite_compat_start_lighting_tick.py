from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

from ae3lite.api import bind_start_lighting_tick_route
from ae3lite.api.contracts import StartLightingTickRequest
from ae3lite.application.dto import TaskCreationResult
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import TaskCreateError


def _task(*, task_id: int, zone_id: int, status: str) -> AutomationTask:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return AutomationTask.from_row({
        "id": task_id,
        "zone_id": zone_id,
        "task_type": "lighting_tick",
        "status": status,
        "idempotency_key": "sch:z7:lighting",
        "scheduled_for": now,
        "due_at": now,
        "claimed_by": None,
        "claimed_at": None,
        "error_code": None,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "topology": "lighting_tick",
        "intent_source": None,
        "intent_trigger": None,
        "intent_id": 90,
        "intent_meta": {},
        "current_stage": "apply",
        "workflow_phase": "ready",
        "stage_deadline_at": None,
        "stage_retry_count": 0,
        "stage_entered_at": None,
        "clean_fill_cycle": 0,
        "corr_step": None,
    })


def _bind_test_route(
    *,
    creation_result: TaskCreationResult | None = None,
    decision: str = "claimed",
    create_error: Exception | None = None,
):
    app = FastAPI()
    captured: dict[str, object] = {"worker_kicked": 0}

    async def validate_zone(_zone_id: int):
        return None

    async def validate_security(_request):
        return None

    async def claim_intent(*, zone_id: int, req, now):
        captured["claim_kwargs"] = {"zone_id": zone_id, "key": req.idempotency_key}
        if decision == "zone_busy":
            return {
                "decision": "zone_busy",
                "intent": {"id": 1, "zone_id": zone_id, "status": "running"},
                "requested_intent": {"id": 90, "zone_id": zone_id, "status": "pending"},
            }
        return {"decision": decision, "intent": {"id": 90, "zone_id": zone_id, "status": "running"}}

    async def create_task_from_intent(**kwargs):
        captured["create_kwargs"] = kwargs
        if create_error is not None:
            raise create_error
        assert creation_result is not None
        return creation_result

    async def mark_intent_terminal(**kwargs):
        captured["marked_terminal"] = kwargs

    bind_start_lighting_tick_route(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security,
        is_start_lighting_tick_rate_limit_enabled_fn=lambda: False,
        start_lighting_tick_rate_limit_check_fn=lambda _zone_id: True,
        start_lighting_tick_rate_limit_window_sec_fn=lambda: 10,
        start_lighting_tick_rate_limit_max_requests_fn=lambda: 30,
        claim_start_lighting_tick_intent_fn=claim_intent,
        create_task_from_intent_fn=create_task_from_intent,
        kick_worker_fn=lambda: captured.__setitem__("worker_kicked", int(captured["worker_kicked"]) + 1),
        build_start_cycle_response_fn=lambda **kwargs: {"status": "ok", "data": kwargs},
        mark_intent_terminal_fn=mark_intent_terminal,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None),
    )
    endpoint = next(route.endpoint for route in app.routes if route.path == "/zones/{zone_id}/start-lighting-tick")
    return endpoint, captured


@pytest.mark.asyncio
async def test_compat_start_lighting_tick_rejects_legacy_brightness_field() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        StartLightingTickRequest(
            source="laravel_scheduler",
            idempotency_key="sch:z7:lighting",
            desired_state="on",
            brightness=60,
        )


@pytest.mark.asyncio
async def test_compat_start_lighting_tick_routes_to_canonical_task_creation() -> None:
    endpoint, captured = _bind_test_route(
        creation_result=TaskCreationResult(task=_task(task_id=778, zone_id=7, status="pending"), created=True),
    )

    response = await endpoint(
        zone_id=7,
        request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-lighting"}),
        req=StartLightingTickRequest(
            source="laravel_scheduler",
            idempotency_key="sch:z7:lighting",
            desired_state="off",
            brightness_pct=25,
        ),
    )
    assert response["status"] == "ok"
    assert int(captured["worker_kicked"]) == 1
    ck = captured["create_kwargs"]
    assert ck["zone_id"] == 7
    assert ck["source"] == "laravel_scheduler"
    assert ck["lighting_desired_state"] == "off"
    assert ck["lighting_brightness_pct"] == 25


@pytest.mark.asyncio
async def test_compat_start_lighting_tick_zone_busy_keeps_requested_intent_pending() -> None:
    endpoint, captured = _bind_test_route(
        creation_result=TaskCreationResult(task=_task(task_id=778, zone_id=7, status="pending"), created=True),
        decision="zone_busy",
    )

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-lighting-busy"}),
            req=StartLightingTickRequest(
                source="laravel_scheduler",
                idempotency_key="sch:z7:lighting",
                desired_state="off",
                brightness_pct=25,
            ),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "start_lighting_tick_zone_busy"
    assert "marked_terminal" not in captured


@pytest.mark.asyncio
async def test_compat_start_lighting_tick_translates_busy_error_to_409() -> None:
    endpoint, captured = _bind_test_route(
        create_error=TaskCreateError(
            "start_cycle_zone_busy",
            "busy",
            details={"active_task_id": 99},
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-lighting-create-busy"}),
            req=StartLightingTickRequest(
                source="laravel_scheduler",
                idempotency_key="sch:z7:lighting",
                desired_state="off",
                brightness_pct=25,
            ),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "start_lighting_tick_zone_busy"
    assert detail["active_task_id"] == 99
    assert "marked_terminal" not in captured


@pytest.mark.asyncio
async def test_compat_start_lighting_tick_claim_race_maps_to_409_zone_busy() -> None:
    endpoint, captured = _bind_test_route(
        creation_result=TaskCreationResult(task=_task(task_id=778, zone_id=7, status="pending"), created=True),
        decision="claim_race",
    )

    with pytest.raises(HTTPException) as exc:
        await endpoint(
            zone_id=7,
            request=SimpleNamespace(headers={"authorization": "Bearer test", "x-trace-id": "trace-lighting-race"}),
            req=StartLightingTickRequest(
                source="laravel_scheduler",
                idempotency_key="sch:z7:lighting",
                desired_state="off",
                brightness_pct=25,
            ),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail["error"] == "start_lighting_tick_zone_busy"
    assert "marked_terminal" not in captured
    assert "create_kwargs" not in captured


def test_lighting_tick_planner_rejects_invalid_desired_state() -> None:
    from dataclasses import replace

    from ae3lite.application.dto import ZoneActuatorRef, ZoneSnapshot
    from ae3lite.domain.errors import PlannerConfigurationError
    from ae3lite.domain.services.cycle_start_planner import CycleStartPlanner

    planner = CycleStartPlanner()
    snapshot = ZoneSnapshot(
        zone_id=7,
        greenhouse_id=1,
        automation_runtime="ae3",
        grow_cycle_id=1,
        current_phase_id=1,
        phase_name="VEG",
        workflow_phase="ready",
        workflow_version=1,
        targets={"lighting": {"pwm_duty": 73}},
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
    )
    task = replace(
        _task(task_id=7, zone_id=7, status="claimed"),
        intent_meta={"intent_payload": {"desired_state": "maybe"}},
    )
    with pytest.raises(PlannerConfigurationError, match="desired_state"):
        planner.build(task=task, snapshot=snapshot)
