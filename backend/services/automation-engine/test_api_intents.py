from __future__ import annotations

from datetime import datetime

import pytest

from ae2lite.api_contracts import StartCycleRequest
from ae2lite.api_intents import (
    build_scheduler_task_request_from_intent,
    claim_start_cycle_intent,
    mark_intent_pending,
)


def _norm(query: str) -> str:
    return " ".join(str(query).split()).lower()


@pytest.mark.asyncio
async def test_mark_intent_pending_clears_claimed_at():
    now = datetime(2026, 2, 22, 12, 0, 0)
    captured = {"query": "", "args": ()}

    async def fake_execute(query, *args):
        captured["query"] = _norm(query)
        captured["args"] = args
        return None

    await mark_intent_pending(
        intent_id=321,
        now=now,
        execute_fn=fake_execute,
    )

    assert "set status = 'pending'" in captured["query"]
    assert "claimed_at = null" in captured["query"]
    assert "not_before = greatest(coalesce(not_before, $2), $3)" in captured["query"]
    assert len(captured["args"]) == 3
    assert captured["args"][0] == 321
    assert captured["args"][1] == now
    assert captured["args"][2] > now


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
        if "idempotency_key <> $2" in q and "status = 'running'" in q:
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
async def test_claim_start_cycle_intent_returns_terminal_for_completed_intent():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z12:irrigation:completed")

    async def fake_fetch(query, *args):
        q = _norm(query)
        if "with candidate as" in q:
            return []
        if "idempotency_key <> $2" in q and "status = 'running'" in q:
            return []
        if "from zone_automation_intents" in q and "idempotency_key" in q and "order by id desc" in q:
            return [{"id": 778, "zone_id": 12, "status": "completed", "payload": {}}]
        return []

    claimed = await claim_start_cycle_intent(
        zone_id=12,
        req=req,
        now=now,
        fetch_fn=fake_fetch,
    )

    assert claimed["decision"] == "terminal"
    assert claimed["intent"]["id"] == 778


@pytest.mark.asyncio
async def test_claim_start_cycle_intent_reclaims_stale_claimed_intent():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z12:irrigation:stale-claimed")
    calls = {"candidate": 0}

    async def fake_fetch(query, *args):
        q = _norm(query)
        if "with candidate as" in q:
            calls["candidate"] += 1
            return [
                {
                    "id": 901,
                    "zone_id": 12,
                    "status": "claimed",
                    "retry_count": 1,
                    "payload": {},
                }
            ]
        raise AssertionError(f"unexpected query: {q}")

    claimed = await claim_start_cycle_intent(
        zone_id=12,
        req=req,
        now=now,
        claimed_stale_after_sec=60,
        fetch_fn=fake_fetch,
    )

    assert calls["candidate"] == 1
    assert claimed["decision"] == "claimed"
    assert claimed["intent"]["id"] == 901
    assert claimed["intent"]["status"] == "claimed"


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
        if "idempotency_key <> $2" in q and "status = 'running'" in q:
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
        if "idempotency_key <> $2" in q and "status = 'running'" in q:
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


@pytest.mark.asyncio
async def test_claim_start_cycle_intent_returns_zone_busy_for_other_active_intent():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z5:irrigation:busy")

    async def fake_fetch(query, *args):
        q = _norm(query)
        if "with candidate as" in q:
            return []
        if "where zone_id = $1" in q and "idempotency_key = $2" in q:
            return [{"id": 910, "zone_id": 5, "status": "pending", "retry_count": 0, "payload": {}}]
        if "idempotency_key <> $2" in q and "status = 'running'" in q:
            return [{"id": 911, "zone_id": 5, "status": "running", "retry_count": 1, "payload": {}}]
        if "from zone_automation_intents" in q and "idempotency_key" in q and "order by id desc" in q:
            return []
        raise AssertionError(f"unexpected query: {q}")

    claimed = await claim_start_cycle_intent(
        zone_id=5,
        req=req,
        now=now,
        fetch_fn=fake_fetch,
    )

    assert claimed["decision"] == "zone_busy"
    assert claimed["intent"]["id"] == 911
    assert claimed["intent"]["zone_id"] == 5
    assert claimed["requested_intent"]["id"] == 910


@pytest.mark.asyncio
async def test_claim_start_cycle_intent_candidate_query_contains_active_intent_guard():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z5:irrigation:race-guard")
    captured_candidate_query = {"sql": ""}

    async def fake_fetch(query, *args):
        q = _norm(query)
        if "with candidate as" in q:
            captured_candidate_query["sql"] = q
            return []
        if "where zone_id = $1" in q and "idempotency_key = $2" in q:
            return []
        if "idempotency_key <> $2" in q and "status = 'running'" in q:
            return [{"id": 1002, "zone_id": 5, "status": "running", "retry_count": 1, "payload": {}}]
        if "from zone_automation_intents" in q and "idempotency_key" in q and "order by id desc" in q:
            return []
        raise AssertionError(f"unexpected query: {q}")

    claimed = await claim_start_cycle_intent(
        zone_id=5,
        req=req,
        now=now,
        fetch_fn=fake_fetch,
    )

    candidate_sql = captured_candidate_query["sql"]
    assert "and not exists" in candidate_sql
    assert "active_intent.idempotency_key <> $2" in candidate_sql
    assert "for update" in candidate_sql
    assert claimed["decision"] == "zone_busy"
    assert claimed["intent"]["id"] == 1002


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


def test_build_scheduler_task_request_from_intent_ignores_legacy_task_payload():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z3:irrigation:wakeup-only")
    intent = {
        "id": 900,
        "retry_count": 0,
        "payload": {
            "source": "laravel_scheduler",
            "workflow": "legacy_workflow_must_be_ignored",
            "topology": "legacy_topology_must_be_ignored",
            "task_payload": {
                "workflow": "legacy_payload_workflow",
                "topology": "legacy_payload_topology",
                "config": {"execution": {"force_execute": True}},
            },
        },
    }

    scheduler_req = build_scheduler_task_request_from_intent(
        zone_id=3,
        req=req,
        intent_row=intent,
        now=now,
        due_in_sec=60,
        expires_in_sec=900,
        default_topology="two_tank_drip_substrate_trays",
    )

    assert scheduler_req.task_type == "diagnostics"
    assert scheduler_req.payload["workflow"] == "cycle_start"
    assert scheduler_req.payload["topology"] == "two_tank_drip_substrate_trays"
    assert scheduler_req.payload["config"]["execution"]["workflow"] == "cycle_start"
    assert scheduler_req.payload["config"]["execution"]["topology"] == "two_tank_drip_substrate_trays"


def test_build_scheduler_task_request_from_intent_uses_payload_task_type_when_supported():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z7:lighting:wakeup-only")
    intent = {
        "id": 77,
        "retry_count": 1,
        "payload": {
            "task_type": "lighting",
            "source": "laravel_scheduler",
        },
    }

    scheduler_req = build_scheduler_task_request_from_intent(
        zone_id=7,
        req=req,
        intent_row=intent,
        now=now,
        due_in_sec=60,
        expires_in_sec=900,
        default_topology="two_tank_drip_substrate_trays",
    )

    assert scheduler_req.task_type == "lighting"
    assert scheduler_req.payload.get("workflow") is None
    assert scheduler_req.payload["config"]["execution"]["topology"] == "two_tank_drip_substrate_trays"
    assert scheduler_req.payload["config"]["execution"].get("workflow") is None


def test_build_scheduler_task_request_from_intent_maps_known_intent_type_to_runtime_task():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z2:ventilation:tick")
    intent = {
        "id": 420,
        "retry_count": 0,
        "intent_type": "VENTILATION_TICK",
        "payload": {
            "source": "laravel_scheduler",
            "workflow": "cycle_start",
        },
    }

    scheduler_req = build_scheduler_task_request_from_intent(
        zone_id=2,
        req=req,
        intent_row=intent,
        now=now,
        due_in_sec=60,
        expires_in_sec=900,
        default_topology="two_tank_drip_substrate_trays",
    )

    assert scheduler_req.task_type == "ventilation"
    assert scheduler_req.payload.get("workflow") is None
    assert scheduler_req.payload["source"] == "laravel_scheduler"
    assert scheduler_req.payload["config"]["execution"]["topology"] == "two_tank_drip_substrate_trays"
    assert scheduler_req.payload["config"]["execution"].get("workflow") is None


def test_build_scheduler_task_request_from_intent_strips_cycle_start_workflow_for_non_diagnostics():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z2:irrigation:tick")
    intent = {
        "id": 421,
        "retry_count": 0,
        "intent_type": "IRRIGATION_TICK",
        "payload": {
            "source": "laravel_scheduler",
            "config": {
                "execution": {
                    "workflow": "cycle_start",
                    "duration_sec": 75,
                }
            },
        },
    }

    scheduler_req = build_scheduler_task_request_from_intent(
        zone_id=2,
        req=req,
        intent_row=intent,
        now=now,
        due_in_sec=60,
        expires_in_sec=900,
        default_topology="two_tank_drip_substrate_trays",
    )

    assert scheduler_req.task_type == "irrigation"
    assert scheduler_req.payload.get("workflow") is None
    assert scheduler_req.payload["topology"] == "two_tank_drip_substrate_trays"
    assert scheduler_req.payload["config"]["execution"]["duration_sec"] == 75
    assert scheduler_req.payload["config"]["execution"]["topology"] == "two_tank_drip_substrate_trays"
    assert scheduler_req.payload["config"]["execution"].get("workflow") is None


def test_build_scheduler_task_request_from_irrigate_once_cycle_start_uses_diagnostics():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_scheduler", idempotency_key="sch:z2:irrigate-once:start-cycle")
    intent = {
        "id": 422,
        "retry_count": 0,
        "intent_type": "IRRIGATE_ONCE",
        "payload": {
            "source": "laravel_scheduler",
            "task_type": "irrigation",
            "workflow": "cycle_start",
            "config": {
                "execution": {
                    "workflow": "cycle_start",
                    "duration_sec": 75,
                }
            },
        },
    }

    scheduler_req = build_scheduler_task_request_from_intent(
        zone_id=2,
        req=req,
        intent_row=intent,
        now=now,
        due_in_sec=60,
        expires_in_sec=900,
        default_topology="two_tank_drip_substrate_trays",
    )

    assert scheduler_req.task_type == "diagnostics"
    assert scheduler_req.payload["workflow"] == "cycle_start"
    assert scheduler_req.payload["config"]["execution"]["workflow"] == "cycle_start"
    assert scheduler_req.payload["config"]["execution"]["topology"] == "two_tank_drip_substrate_trays"


def test_build_scheduler_task_request_from_intent_preserves_grow_cycle_id_metadata():
    now = datetime(2026, 2, 22, 12, 0, 0)
    req = StartCycleRequest(source="laravel_grow_cycle_start", idempotency_key="gcs:z1:c55:test")
    intent = {
        "id": 55,
        "retry_count": 0,
        "payload": {
            "source": "laravel_grow_cycle_start",
            "grow_cycle_id": 55,
        },
    }

    scheduler_req = build_scheduler_task_request_from_intent(
        zone_id=1,
        req=req,
        intent_row=intent,
        now=now,
        due_in_sec=60,
        expires_in_sec=900,
        default_topology="two_tank_drip_substrate_trays",
    )

    assert scheduler_req.task_type == "diagnostics"
    assert scheduler_req.payload["grow_cycle_id"] == 55
