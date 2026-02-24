from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api
from ae2lite.api_contracts import StartCycleRequest


@pytest.mark.asyncio
async def test_zone_start_cycle_claims_intent_and_enqueues_execution(monkeypatch):
    captured = {}

    async def fake_validate_zone(zone_id: int):
        captured["validated_zone_id"] = zone_id

    async def fake_validate_security(_request):
        captured["security_checked"] = True

    async def fake_claim_start_cycle_intent(*, zone_id, req, now, fetch_fn):
        captured["claim_zone_id"] = zone_id
        captured["claim_req"] = req
        captured["claim_now"] = now
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


def test_router_exposes_start_cycle_and_not_legacy_scheduler_task_paths():
    route_paths = {route.path for route in api.app.routes}

    assert "/zones/{zone_id}/start-cycle" in route_paths
    assert "/zones/{zone_id}/state" in route_paths
    assert "/zones/{zone_id}/control-mode" in route_paths
    assert "/zones/{zone_id}/manual-step" in route_paths
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
