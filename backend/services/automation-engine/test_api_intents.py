from __future__ import annotations

from datetime import datetime

import pytest

from application.api_contracts import StartCycleRequest
from application.api_intents import (
    build_scheduler_task_request_from_intent,
    claim_start_cycle_intent,
)


def _norm(query: str) -> str:
    return " ".join(str(query).split()).lower()


@pytest.mark.asyncio
async def test_claim_start_cycle_intent_claims_pending_row_first():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z12:irrigation:abc")

    async def fake_fetch(query, *args):
        q = _norm(query)
        if "with candidate as" in q:
            return [
                {
                    "id": 301,
                    "zone_id": 12,
                    "status": "claimed",
                    "retry_count": 0,
                    "payload": {
                        "task_type": "diagnostics",
                        "workflow": "cycle_start",
                        "topology": "two_tank_drip_substrate_trays",
                    },
                }
            ]
        raise AssertionError(f"unexpected query: {q}")

    claimed = await claim_start_cycle_intent(
        zone_id=12,
        req=req,
        now=now,
        fetch_fn=fake_fetch,
    )

    assert claimed["decision"] == "claimed"
    assert claimed["intent"]["id"] == 301
    assert claimed["intent"]["status"] == "claimed"


@pytest.mark.asyncio
async def test_claim_start_cycle_intent_returns_deduplicated_for_running_intent():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z12:irrigation:dup")
    calls = {"candidate": 0, "existing": 0}

    async def fake_fetch(query, *args):
        q = _norm(query)
        if "with candidate as" in q:
            calls["candidate"] += 1
            return []
        if "from zone_automation_intents" in q and "idempotency_key" in q and "order by id desc" in q:
            calls["existing"] += 1
            return [{"id": 777, "zone_id": 12, "status": "running", "payload": {}}]
        return []

    claimed = await claim_start_cycle_intent(
        zone_id=12,
        req=req,
        now=now,
        fetch_fn=fake_fetch,
    )

    assert calls["candidate"] == 1
    assert calls["existing"] == 1
    assert claimed["decision"] == "deduplicated"
    assert claimed["intent"]["id"] == 777


@pytest.mark.asyncio
async def test_claim_start_cycle_intent_inserts_and_claims_when_missing():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z5:irrigation:new")
    calls = {"candidate": 0, "existing": 0, "insert": 0, "claim_after_insert": 0}

    async def fake_fetch(query, *args):
        q = _norm(query)
        if "with candidate as" in q:
            calls["candidate"] += 1
            return []
        if "from zone_automation_intents" in q and "idempotency_key" in q and "order by id desc" in q:
            calls["existing"] += 1
            return []
        if "insert into zone_automation_intents" in q:
            calls["insert"] += 1
            return [{"id": 909, "zone_id": 5, "status": "pending", "retry_count": 0, "payload": {}}]
        if "update zone_automation_intents" in q and "where id = $1" in q and "status = 'pending'" in q:
            calls["claim_after_insert"] += 1
            return [{"id": 909, "zone_id": 5, "status": "claimed", "retry_count": 0, "payload": {}}]
        raise AssertionError(f"unexpected query: {q}")

    claimed = await claim_start_cycle_intent(
        zone_id=5,
        req=req,
        now=now,
        fetch_fn=fake_fetch,
    )

    assert calls == {"candidate": 1, "existing": 1, "insert": 1, "claim_after_insert": 1}
    assert claimed["decision"] == "claimed"
    assert claimed["intent"]["id"] == 909


def test_build_scheduler_task_request_from_intent_uses_intent_identity():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z12:irrigation:test")
    intent = {
        "id": 1001,
        "retry_count": 2,
        "payload": {
            "task_type": "diagnostics",
            "workflow": "cycle_start",
            "topology": "two_tank_drip_substrate_trays",
        },
    }

    scheduler_req = build_scheduler_task_request_from_intent(
        zone_id=12,
        req=req,
        intent_row=intent,
        now=now,
        due_in_sec=60,
        expires_in_sec=900,
        default_topology="two_tank_drip_substrate_trays",
    )

    assert scheduler_req.zone_id == 12
    assert scheduler_req.task_type == "diagnostics"
    assert scheduler_req.payload["workflow"] == "cycle_start"
    assert scheduler_req.payload["config"]["execution"]["topology"] == "two_tank_drip_substrate_trays"
    assert scheduler_req.correlation_id == "start-cycle-intent:1001:2:sch:z12:irrigation:test"
