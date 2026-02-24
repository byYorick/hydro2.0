from __future__ import annotations

from datetime import datetime

import pytest

from ae2lite.api_contracts import StartCycleRequest
from ae2lite.api_intents import (
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
async def test_claim_start_cycle_intent_returns_missing_when_scheduler_intent_absent():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z5:irrigation:new")
    calls = {"candidate": 0, "existing": 0, "cross_zone_lookup": 0}

    async def fake_fetch(query, *args):
        q = _norm(query)
        if "with candidate as" in q:
            calls["candidate"] += 1
            return []
        if "from zone_automation_intents" in q and "idempotency_key" in q and "order by id desc" in q:
            if "where zone_id = $1" in q:
                calls["existing"] += 1
                return []
            calls["cross_zone_lookup"] += 1
            return []
        raise AssertionError(f"unexpected query: {q}")

    claimed = await claim_start_cycle_intent(
        zone_id=5,
        req=req,
        now=now,
        fetch_fn=fake_fetch,
    )

    assert calls == {"candidate": 1, "existing": 1, "cross_zone_lookup": 1}
    assert claimed["decision"] == "missing"
    assert claimed["intent"] == {}


@pytest.mark.asyncio
async def test_claim_start_cycle_intent_returns_cross_zone_conflict_for_same_idempotency_key():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z5:irrigation:conflict")

    async def fake_fetch(query, *args):
        q = _norm(query)
        if "with candidate as" in q:
            return []
        if "from zone_automation_intents" in q and "idempotency_key" in q and "order by id desc" in q:
            if "where zone_id = $1" in q:
                return []
            return [{"id": 909, "zone_id": 99, "status": "pending", "retry_count": 0, "payload": {}}]
        raise AssertionError(f"unexpected query: {q}")

    claimed = await claim_start_cycle_intent(
        zone_id=5,
        req=req,
        now=now,
        fetch_fn=fake_fetch,
    )

    assert claimed["decision"] == "conflict_cross_zone"
    assert claimed["intent"]["zone_id"] == 99


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
    assert scheduler_req.correlation_id.startswith("start-cycle-intent:1001:2:")
    assert len(scheduler_req.correlation_id) <= 128


def test_build_scheduler_task_request_from_intent_handles_max_idempotency_key_length():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="k" * 160)
    intent = {"id": 42, "retry_count": 0, "payload": {"task_type": "diagnostics", "workflow": "cycle_start"}}

    scheduler_req = build_scheduler_task_request_from_intent(
        zone_id=1,
        req=req,
        intent_row=intent,
        now=now,
        due_in_sec=60,
        expires_in_sec=900,
        default_topology="two_tank_drip_substrate_trays",
    )

    assert scheduler_req.correlation_id.startswith("start-cycle-intent:42:0:")
    assert len(scheduler_req.correlation_id) <= 128
