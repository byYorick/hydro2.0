from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException

import api
from ae2lite.api_contracts import StartCycleRequest


@pytest.fixture(autouse=True)
def _stub_workflow_state_store(monkeypatch):
    class _WorkflowStateStoreStub:
        async def get(self, _zone_id: int):
            return {"workflow_phase": "idle", "scheduler_task_id": None}

    monkeypatch.setattr(api, "_workflow_state_store", _WorkflowStateStoreStub())


@pytest.mark.asyncio
async def test_zone_start_cycle_claims_intent_and_enqueues_execution(monkeypatch):
    captured = {}

    async def fake_validate_zone(zone_id: int):
        captured["validated_zone_id"] = zone_id

    async def fake_validate_security(_request):
        captured["security_checked"] = True

    async def fake_claim_start_cycle_intent(*, zone_id, req, now, claimed_stale_after_sec, fetch_fn):
        captured["claim_zone_id"] = zone_id
        captured["claim_req"] = req
        captured["claim_now"] = now
        captured["claim_stale_after_sec"] = claimed_stale_after_sec
        captured["claim_fetch_fn"] = fetch_fn
        return {
            "decision": "claimed",
            "intent": {
                "id": 101,
                "retry_count": 0,
                "payload": {
                    "task_type": "diagnostics",
                    "workflow": "cycle_start",
                    "topology": "two_tank_drip_substrate_trays",
                },
            },
        }

    async def fake_create_scheduler_task(req):
        captured["scheduler_req"] = req
        return {"task_id": "st-intent-101"}, False

    def fake_spawn_background_task(coro, **kwargs):
        captured["spawned"] = {"coro": coro, "kwargs": kwargs}
        coro.close()

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_start_cycle_intent)
    monkeypatch.setattr(api, "_create_scheduler_task", fake_create_scheduler_task)
    monkeypatch.setattr(api, "_spawn_background_task", fake_spawn_background_task)

    response = await api.zone_start_cycle(
        zone_id=12,
        request=SimpleNamespace(headers={"x-trace-id": "trace-1"}),
        req=StartCycleRequest(
            source="laravel_scheduler",
            idempotency_key="sch:z12:irrigation:2026-02-21T10:00:00Z",
        ),
    )

    assert captured["validated_zone_id"] == 12
    assert captured["security_checked"] is True
    assert int(captured["claim_stale_after_sec"]) >= 30
    scheduler_req = captured["scheduler_req"]
    assert scheduler_req.zone_id == 12
    assert scheduler_req.task_type == "diagnostics"
    assert scheduler_req.payload["workflow"] == "cycle_start"
    assert scheduler_req.payload["trigger"] == "start_cycle_api"
    assert scheduler_req.correlation_id.startswith("start-cycle-intent:101:0:")

    assert response == {
        "status": "ok",
        "data": {
            "zone_id": 12,
            "accepted": True,
            "runner_state": "active",
            "deduplicated": False,
            "task_id": "intent-101",
            "idempotency_key": "sch:z12:irrigation:2026-02-21T10:00:00Z",
        },
    }
    assert captured["spawned"]["kwargs"]["zone_id"] == 12


@pytest.mark.asyncio
async def test_zone_start_cycle_marks_deduplicated_when_intent_already_claimed(monkeypatch):
    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_start_cycle_intent(*_args, **_kwargs):
        return {
            "decision": "deduplicated",
            "intent": {"id": 77, "status": "running"},
        }

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_start_cycle_intent)

    response = await api.zone_start_cycle(
        zone_id=12,
        request=SimpleNamespace(headers={"x-trace-id": "trace-dup"}),
        req=StartCycleRequest(
            source="laravel_scheduler",
            idempotency_key="sch:z12:irrigation:2026-02-22T05:00:00Z",
        ),
    )

    assert response["status"] == "ok"
    assert response["data"]["zone_id"] == 12
    assert response["data"]["accepted"] is True
    assert response["data"]["runner_state"] == "active"
    assert response["data"]["deduplicated"] is True
    assert response["data"]["task_id"] == "intent-77"


@pytest.mark.asyncio
async def test_zone_start_cycle_returns_terminal_payload_when_intent_is_terminal(monkeypatch):
    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_start_cycle_intent(*_args, **_kwargs):
        return {
            "decision": "terminal",
            "intent": {"id": 88, "status": "failed"},
        }

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_start_cycle_intent)

    response = await api.zone_start_cycle(
        zone_id=12,
        request=SimpleNamespace(headers={"x-trace-id": "trace-terminal"}),
        req=StartCycleRequest(
            source="laravel_scheduler",
            idempotency_key="sch:z12:irrigation:2026-02-22T05:05:00Z",
        ),
    )

    assert response["status"] == "ok"
    assert response["data"]["zone_id"] == 12
    assert response["data"]["accepted"] is False
    assert response["data"]["runner_state"] == "terminal"
    assert response["data"]["deduplicated"] is True
    assert response["data"]["task_id"] == "intent-88"
    assert response["data"]["task_status"] == "failed"
    assert response["data"]["reason"] == "start_cycle_intent_terminal"


@pytest.mark.asyncio
async def test_zone_start_cycle_returns_409_when_intent_missing(monkeypatch):
    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_start_cycle_intent(*_args, **_kwargs):
        return {"decision": "missing", "intent": {}}

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_start_cycle_intent)

    with pytest.raises(HTTPException) as exc:
        await api.zone_start_cycle(
            zone_id=12,
            request=SimpleNamespace(headers={"x-trace-id": "trace-missing"}),
            req=StartCycleRequest(
                source="laravel_scheduler",
                idempotency_key="sch:z12:irrigation:2026-02-22T05:10:00Z",
            ),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("error") == "start_cycle_intent_not_found"
    assert detail.get("zone_id") == 12


@pytest.mark.asyncio
async def test_zone_start_cycle_returns_409_when_cross_zone_idempotency_conflict(monkeypatch):
    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_start_cycle_intent(*_args, **_kwargs):
        return {
            "decision": "conflict_cross_zone",
            "intent": {"id": 555, "zone_id": 77, "status": "pending"},
        }

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_start_cycle_intent)

    with pytest.raises(HTTPException) as exc:
        await api.zone_start_cycle(
            zone_id=12,
            request=SimpleNamespace(headers={"x-trace-id": "trace-conflict"}),
            req=StartCycleRequest(
                source="laravel_scheduler",
                idempotency_key="sch:z12:irrigation:2026-02-22T05:20:00Z",
            ),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("error") == "start_cycle_idempotency_key_conflict"
    assert detail.get("zone_id") == 12
    assert detail.get("conflict_zone_id") == 77


@pytest.mark.asyncio
async def test_zone_start_cycle_returns_409_when_zone_busy(monkeypatch):
    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_start_cycle_intent(*_args, **_kwargs):
        return {
            "decision": "zone_busy",
            "intent": {"id": 889, "zone_id": 12, "status": "running"},
        }

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_start_cycle_intent)

    with pytest.raises(HTTPException) as exc:
        await api.zone_start_cycle(
            zone_id=12,
            request=SimpleNamespace(headers={"x-trace-id": "trace-busy"}),
            req=StartCycleRequest(
                source="laravel_scheduler",
                idempotency_key="sch:z12:irrigation:2026-02-22T05:30:00Z",
            ),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("error") == "start_cycle_zone_busy"
    assert detail.get("zone_id") == 12
    assert detail.get("active_intent_id") == 889
    assert detail.get("active_status") == "running"


@pytest.mark.asyncio
async def test_zone_start_cycle_returns_409_when_zone_has_active_task_and_reverts_intent(monkeypatch):
    captured = {"create_called": False, "pending_calls": []}

    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_start_cycle_intent(*_args, **_kwargs):
        return {
            "decision": "claimed",
            "intent": {"id": 901, "zone_id": 12, "status": "claimed", "retry_count": 0, "payload": {}},
        }

    async def fake_load_latest_zone_task(_zone_id: int):
        return {"task_id": "st-running", "status": "running"}

    async def fake_mark_intent_pending(*, intent_id, now, execute_fn):
        captured["pending_calls"].append({"intent_id": intent_id, "now": now, "execute_fn": execute_fn})

    async def fake_create_scheduler_task(_req):
        captured["create_called"] = True
        return {"task_id": "st-should-not-run"}, False

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_start_cycle_intent)
    monkeypatch.setattr(api, "_load_latest_zone_task", fake_load_latest_zone_task)
    monkeypatch.setattr(api, "policy_mark_intent_pending", fake_mark_intent_pending)
    monkeypatch.setattr(api, "_create_scheduler_task", fake_create_scheduler_task)

    with pytest.raises(HTTPException) as exc:
        await api.zone_start_cycle(
            zone_id=12,
            request=SimpleNamespace(headers={"x-trace-id": "trace-active-task"}),
            req=StartCycleRequest(
                source="laravel_scheduler",
                idempotency_key="sch:z12:irrigation:2026-02-22T05:31:00Z",
            ),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("error") == "start_cycle_zone_busy"
    assert detail.get("zone_id") == 12
    assert detail.get("active_task_id") == "st-running"
    assert detail.get("active_task_status") == "running"
    assert captured["create_called"] is False
    assert len(captured["pending_calls"]) == 1
    assert captured["pending_calls"][0]["intent_id"] == 901


@pytest.mark.asyncio
async def test_zone_start_cycle_returns_409_when_workflow_phase_is_active(monkeypatch):
    captured = {"create_called": False, "pending_calls": []}

    async def fake_validate_zone(_zone_id: int):
        return None

    async def fake_validate_security(_request):
        return None

    async def fake_claim_start_cycle_intent(*_args, **_kwargs):
        return {
            "decision": "claimed",
            "intent": {"id": 902, "zone_id": 12, "status": "claimed", "retry_count": 0, "payload": {}},
        }

    async def fake_load_latest_zone_task(_zone_id: int):
        return {"task_id": "st-completed", "status": "completed"}

    async def fake_mark_intent_pending(*, intent_id, now, execute_fn):
        captured["pending_calls"].append({"intent_id": intent_id, "now": now, "execute_fn": execute_fn})

    async def fake_create_scheduler_task(_req):
        captured["create_called"] = True
        return {"task_id": "st-should-not-run"}, False

    class _WorkflowStateStoreStub:
        async def get(self, _zone_id: int):
            return {"workflow_phase": "tank_filling", "scheduler_task_id": "st-existing"}

    monkeypatch.setattr(api, "_validate_scheduler_zone", fake_validate_zone)
    monkeypatch.setattr(api, "_validate_scheduler_security_baseline", fake_validate_security)
    monkeypatch.setattr(api, "policy_claim_start_cycle_intent", fake_claim_start_cycle_intent)
    monkeypatch.setattr(api, "_load_latest_zone_task", fake_load_latest_zone_task)
    monkeypatch.setattr(api, "policy_mark_intent_pending", fake_mark_intent_pending)
    monkeypatch.setattr(api, "_create_scheduler_task", fake_create_scheduler_task)
    monkeypatch.setattr(api, "_workflow_state_store", _WorkflowStateStoreStub())

    with pytest.raises(HTTPException) as exc:
        await api.zone_start_cycle(
            zone_id=12,
            request=SimpleNamespace(headers={"x-trace-id": "trace-active-phase"}),
            req=StartCycleRequest(
                source="laravel_scheduler",
                idempotency_key="sch:z12:irrigation:2026-02-22T05:32:00Z",
            ),
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("error") == "start_cycle_zone_busy"
    assert detail.get("zone_id") == 12
    assert detail.get("active_workflow_phase") == "tank_filling"
    assert detail.get("active_workflow_scheduler_task_id") == "st-existing"
    assert captured["create_called"] is False
    assert len(captured["pending_calls"]) == 1
    assert captured["pending_calls"][0]["intent_id"] == 902


def test_router_exposes_start_cycle_and_not_legacy_scheduler_task_paths():
    route_paths = {route.path for route in api.app.routes}

    assert "/zones/{zone_id}/start-cycle" in route_paths
    assert "/zones/{zone_id}/state" in route_paths
    assert "/zones/{zone_id}/control-mode" in route_paths
    assert "/zones/{zone_id}/manual-step" in route_paths
    assert "/zones/{zone_id}/start-relay-autotune" in route_paths
    assert "/zones/{zone_id}/relay-autotune/status" in route_paths
    assert "/zones/{zone_id}/automation-state" not in route_paths
    assert "/zones/{zone_id}/automation/control-mode" not in route_paths
    assert "/zones/{zone_id}/automation/manual-step" not in route_paths
    assert "/test/hook" not in route_paths
    assert "/test/hook/{zone_id}" not in route_paths
    assert "/scheduler/task" not in route_paths
    assert "/scheduler/task/{task_id}" not in route_paths
    assert "/scheduler/bootstrap" not in route_paths
    assert "/scheduler/bootstrap/heartbeat" not in route_paths
    assert "/scheduler/cutover/state" not in route_paths
    assert "/scheduler/integration/contracts" not in route_paths
    assert "/scheduler/observability/contracts" not in route_paths
    assert "/scheduler/internal/enqueue" not in route_paths


def test_start_cycle_route_is_bound_once_from_split_module():
    assert api.zone_start_cycle.__module__ == "ae2lite.api_runtime_start_cycle"

    start_cycle_routes = [route for route in api.app.routes if route.path == "/zones/{zone_id}/start-cycle"]
    assert len(start_cycle_routes) == 1
    assert sorted(start_cycle_routes[0].methods) == ["POST"]


def test_api_runtime_module_stays_below_400_lines_guard():
    runtime_path = Path(api.__file__).resolve()
    line_count = sum(1 for _ in runtime_path.open("r", encoding="utf-8"))
    assert line_count < 400, f"api_runtime.py line budget exceeded: {line_count}"
