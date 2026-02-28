from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import api
from ae2lite.api_contracts import StartCycleRequest


@pytest.mark.asyncio
async def test_start_cycle_intent_claim_to_completion_flow(monkeypatch):
    running_calls = []
    terminal_calls = []
    spawned_tasks = []

    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_intent(*, zone_id, req, now, claimed_stale_after_sec, fetch_fn):
        return {
            "decision": "claimed",
            "intent": {
                "id": 505,
                "zone_id": zone_id,
                "retry_count": 0,
                "payload": {
                    "task_type": "diagnostics",
                    "workflow": "cycle_start",
                    "topology": "two_tank_drip_substrate_trays",
                },
            },
        }

    async def fake_create_scheduler_task(_req):
        return {"task_id": "st-505"}, False

    async def fake_execute_scheduler_task(task_id, _req, _trace_id):
        api._scheduler_tasks[task_id] = {
            "task_id": task_id,
            "status": "completed",
            "error_code": None,
            "error": None,
        }

    async def fake_mark_running(*, intent_id, now, execute_fn):
        running_calls.append({"intent_id": intent_id, "now": now})

    async def fake_mark_terminal(*, intent_id, now, success, error_code, error_message, execute_fn):
        terminal_calls.append(
            {
                "intent_id": intent_id,
                "success": success,
                "error_code": error_code,
                "error_message": error_message,
            }
        )

    def fake_spawn_background_task(coro, **_kwargs):
        task = asyncio.create_task(coro)
        spawned_tasks.append(task)
        return task

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_intent)
    monkeypatch.setattr(api, "_create_scheduler_task", fake_create_scheduler_task)
    monkeypatch.setattr(api, "_execute_scheduler_task", fake_execute_scheduler_task)
    monkeypatch.setattr(api, "policy_mark_intent_running", fake_mark_running)
    monkeypatch.setattr(api, "policy_mark_intent_terminal", fake_mark_terminal)
    monkeypatch.setattr(api, "_spawn_background_task", fake_spawn_background_task)

    response = await api.zone_start_cycle(
        zone_id=9,
        request=SimpleNamespace(headers={"x-trace-id": "trace-int-flow"}),
        req=StartCycleRequest(
            source="laravel_scheduler",
            idempotency_key="sch:z9:irrigation:2026-02-22T11:00:00Z",
        ),
    )

    assert response["status"] == "ok"
    assert response["data"]["accepted"] is True
    assert response["data"]["deduplicated"] is False
    assert response["data"]["task_id"] == "intent-505"

    await asyncio.gather(*spawned_tasks)

    assert len(running_calls) == 1
    assert running_calls[0]["intent_id"] == 505
    assert len(terminal_calls) == 1
    assert terminal_calls[0]["intent_id"] == 505
    assert terminal_calls[0]["success"] is True
    assert terminal_calls[0]["error_code"] is None


@pytest.mark.asyncio
async def test_start_cycle_intent_marks_terminal_when_mark_running_fails(monkeypatch):
    terminal_calls = []
    update_calls = []
    spawned_tasks = []

    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_intent(*, zone_id, req, now, claimed_stale_after_sec, fetch_fn):
        return {
            "decision": "claimed",
            "intent": {
                "id": 506,
                "zone_id": zone_id,
                "retry_count": 0,
                "payload": {},
            },
        }

    async def fake_create_scheduler_task(_req):
        return {"task_id": "st-506"}, False

    async def fake_mark_running(*, intent_id, now, execute_fn):
        raise RuntimeError(f"mark_running_failed_{intent_id}")

    async def fake_mark_terminal(*, intent_id, now, success, error_code, error_message, execute_fn):
        terminal_calls.append(
            {
                "intent_id": intent_id,
                "success": success,
                "error_code": error_code,
                "error_message": error_message,
            }
        )

    async def fake_update_scheduler_task(*, task_id, status, result=None, error=None, error_code=None):
        update_calls.append(
            {
                "task_id": task_id,
                "status": status,
                "error": error,
                "error_code": error_code,
                "result": result,
            }
        )

    def fake_spawn_background_task(coro, **_kwargs):
        task = asyncio.create_task(coro)
        spawned_tasks.append(task)
        return task

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_intent)
    monkeypatch.setattr(api, "_create_scheduler_task", fake_create_scheduler_task)
    monkeypatch.setattr(api, "policy_mark_intent_running", fake_mark_running)
    monkeypatch.setattr(api, "policy_mark_intent_terminal", fake_mark_terminal)
    monkeypatch.setattr(api, "_update_scheduler_task", fake_update_scheduler_task)
    monkeypatch.setattr(api, "_spawn_background_task", fake_spawn_background_task)

    response = await api.zone_start_cycle(
        zone_id=9,
        request=SimpleNamespace(headers={"x-trace-id": "trace-int-flow-fail"}),
        req=StartCycleRequest(
            source="laravel_scheduler",
            idempotency_key="sch:z9:irrigation:2026-02-22T11:00:01Z",
        ),
    )

    assert response["status"] == "ok"
    assert response["data"]["task_id"] == "intent-506"

    await asyncio.gather(*spawned_tasks)

    assert len(update_calls) == 1
    assert update_calls[0]["task_id"] == "st-506"
    assert update_calls[0]["status"] == "failed"
    assert update_calls[0]["error_code"] is not None

    assert len(terminal_calls) == 1
    assert terminal_calls[0]["intent_id"] == 506
    assert terminal_calls[0]["success"] is False
    assert terminal_calls[0]["error_code"] is not None


@pytest.mark.asyncio
async def test_start_cycle_intent_full_path_runs_scheduler_task_executor(monkeypatch):
    running_calls = []
    terminal_calls = []
    spawned_tasks = []
    persisted_snapshots = []

    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_intent(*, zone_id, req, now, claimed_stale_after_sec, fetch_fn):
        return {
            "decision": "claimed",
            "intent": {
                "id": 507,
                "zone_id": zone_id,
                "retry_count": 0,
                "payload": {},
            },
        }

    async def fake_create_scheduler_task(req):
        task_id = "st-507"
        api._scheduler_tasks[task_id] = {
            "task_id": task_id,
            "zone_id": req.zone_id,
            "task_type": req.task_type,
            "status": "accepted",
            "payload": req.payload,
            "created_at": req.scheduled_for,
            "updated_at": req.scheduled_for,
            "scheduled_for": req.scheduled_for,
            "due_at": req.due_at,
            "expires_at": req.expires_at,
            "correlation_id": req.correlation_id,
            "payload_fingerprint": "fp",
            "result": None,
            "error": None,
            "error_code": None,
        }
        return {"task_id": task_id}, False

    async def fake_mark_running(*, intent_id, now, execute_fn):
        running_calls.append({"intent_id": intent_id, "now": now})

    async def fake_mark_terminal(*, intent_id, now, success, error_code, error_message, execute_fn):
        terminal_calls.append(
            {
                "intent_id": intent_id,
                "success": success,
                "error_code": error_code,
                "error_message": error_message,
            }
        )

    async def fake_scheduler_zone_exists(_zone_id: int) -> bool:
        return True

    async def fake_persist_snapshot(task):
        persisted_snapshots.append(dict(task))

    class _ExecutorStub:
        async def execute(self, *, zone_id, task_type, payload, task_context):
            assert zone_id == 9
            assert task_type == "diagnostics"
            assert task_context.get("task_id") == "st-507"
            return {"success": True, "result_code": "ok"}

    def fake_executor_factory(*, command_bus, zone_service):
        return _ExecutorStub()

    def fake_spawn_background_task(coro, **_kwargs):
        task = asyncio.create_task(coro)
        spawned_tasks.append(task)
        return task

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_intent)
    monkeypatch.setattr(api, "_create_scheduler_task", fake_create_scheduler_task)
    monkeypatch.setattr(api, "policy_mark_intent_running", fake_mark_running)
    monkeypatch.setattr(api, "policy_mark_intent_terminal", fake_mark_terminal)
    monkeypatch.setattr(api, "_scheduler_zone_exists", fake_scheduler_zone_exists)
    monkeypatch.setattr(api, "_persist_scheduler_task_snapshot", fake_persist_snapshot)
    monkeypatch.setattr(api, "_build_scheduler_task_executor", fake_executor_factory)
    monkeypatch.setattr(api, "_spawn_background_task", fake_spawn_background_task)

    monkeypatch.setattr(api, "_command_bus", object())
    monkeypatch.setattr(api, "_command_bus_loop_id", id(asyncio.get_running_loop()))
    monkeypatch.setattr(api, "_zone_service", None)
    monkeypatch.setattr(api, "_zone_service_loop_id", None)

    response = await api.zone_start_cycle(
        zone_id=9,
        request=SimpleNamespace(headers={"x-trace-id": "trace-int-fullpath"}),
        req=StartCycleRequest(
            source="laravel_scheduler",
            idempotency_key="sch:z9:irrigation:2026-02-22T11:00:02Z",
        ),
    )

    assert response["status"] == "ok"
    assert response["data"]["task_id"] == "intent-507"

    await asyncio.gather(*spawned_tasks)

    final_task = api._scheduler_tasks.get("st-507")
    assert isinstance(final_task, dict)
    assert final_task["status"] == "completed"
    assert len(persisted_snapshots) >= 2

    assert len(running_calls) == 1
    assert running_calls[0]["intent_id"] == 507
    assert len(terminal_calls) == 1
    assert terminal_calls[0]["intent_id"] == 507
    assert terminal_calls[0]["success"] is True
