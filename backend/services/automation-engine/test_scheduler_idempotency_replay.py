from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from application.api_scheduler_helpers import (
    task_payload_fingerprint as policy_task_payload_fingerprint,
    task_payload_matches as policy_task_payload_matches,
)
from application.api_scheduler_store import create_scheduler_task
from services.resilience_contract import SCHEDULER_IDEMPOTENCY_PAYLOAD_MISMATCH


def _build_req(*, correlation_id: str, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        zone_id=12,
        task_type="diagnostics",
        payload=payload,
        scheduled_for="2026-02-22T05:00:00",
        due_at="2026-02-22T05:01:00",
        expires_at="2026-02-22T05:10:00",
        correlation_id=correlation_id,
    )


@pytest.mark.asyncio
async def test_create_scheduler_task_returns_duplicate_for_same_correlation_and_payload():
    req = _build_req(
        correlation_id="start-cycle:12:sch:z12:irrigation:2026-02-22T05:00:00Z",
        payload={"workflow": "cycle_start", "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}},
    )
    fingerprint = policy_task_payload_fingerprint(req)
    scheduler_tasks = {
        "st-existing": {
            "task_id": "st-existing",
            "zone_id": req.zone_id,
            "task_type": req.task_type,
            "status": "accepted",
            "payload": req.payload,
            "created_at": "2026-02-22T05:00:00",
            "updated_at": "2026-02-22T05:00:00",
            "scheduled_for": req.scheduled_for,
            "due_at": req.due_at,
            "expires_at": req.expires_at,
            "correlation_id": req.correlation_id,
            "payload_fingerprint": fingerprint,
            "result": None,
            "error": None,
            "error_code": None,
        }
    }
    persist_calls = []

    async def cleanup_scheduler_tasks_locked_fn(_now):
        return None

    async def load_scheduler_task_by_correlation_id_fn(_correlation_id):
        return None

    async def persist_scheduler_task_snapshot_fn(task):
        persist_calls.append(task)

    task, is_duplicate = await create_scheduler_task(
        req,
        scheduler_tasks=scheduler_tasks,
        scheduler_tasks_lock=asyncio.Lock(),
        cleanup_scheduler_tasks_locked_fn=cleanup_scheduler_tasks_locked_fn,
        load_scheduler_task_by_correlation_id_fn=load_scheduler_task_by_correlation_id_fn,
        task_payload_fingerprint_fn=policy_task_payload_fingerprint,
        task_payload_matches_fn=policy_task_payload_matches,
        new_scheduler_task_id_fn=lambda: "st-new",
        persist_scheduler_task_snapshot_fn=persist_scheduler_task_snapshot_fn,
    )

    assert is_duplicate is True
    assert task["task_id"] == "st-existing"
    assert persist_calls == []


@pytest.mark.asyncio
async def test_create_scheduler_task_rejects_payload_mismatch_for_same_correlation():
    req = _build_req(
        correlation_id="start-cycle:12:sch:z12:irrigation:2026-02-22T05:00:00Z",
        payload={"workflow": "cycle_start", "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}},
    )
    scheduler_tasks = {
        "st-existing": {
            "task_id": "st-existing",
            "zone_id": req.zone_id,
            "task_type": req.task_type,
            "status": "accepted",
            "payload": {"workflow": "cycle_start", "config": {"execution": {"topology": "another_topology"}}},
            "created_at": "2026-02-22T05:00:00",
            "updated_at": "2026-02-22T05:00:00",
            "scheduled_for": req.scheduled_for,
            "due_at": req.due_at,
            "expires_at": req.expires_at,
            "correlation_id": req.correlation_id,
            "payload_fingerprint": "different-fingerprint",
            "result": None,
            "error": None,
            "error_code": None,
        }
    }

    async def cleanup_scheduler_tasks_locked_fn(_now):
        return None

    async def load_scheduler_task_by_correlation_id_fn(_correlation_id):
        return None

    async def persist_scheduler_task_snapshot_fn(_task):
        return None

    with pytest.raises(HTTPException) as exc:
        await create_scheduler_task(
            req,
            scheduler_tasks=scheduler_tasks,
            scheduler_tasks_lock=asyncio.Lock(),
            cleanup_scheduler_tasks_locked_fn=cleanup_scheduler_tasks_locked_fn,
            load_scheduler_task_by_correlation_id_fn=load_scheduler_task_by_correlation_id_fn,
            task_payload_fingerprint_fn=policy_task_payload_fingerprint,
            task_payload_matches_fn=policy_task_payload_matches,
            new_scheduler_task_id_fn=lambda: "st-new",
            persist_scheduler_task_snapshot_fn=persist_scheduler_task_snapshot_fn,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == SCHEDULER_IDEMPOTENCY_PAYLOAD_MISMATCH


@pytest.mark.asyncio
async def test_create_scheduler_task_uses_db_snapshot_for_duplicate_replay():
    req = _build_req(
        correlation_id="start-cycle:12:sch:z12:irrigation:2026-02-22T05:00:00Z",
        payload={"workflow": "cycle_start", "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}},
    )
    fingerprint = policy_task_payload_fingerprint(req)
    scheduler_tasks = {}
    existing_from_db = {
        "task_id": "st-from-db",
        "zone_id": req.zone_id,
        "task_type": req.task_type,
        "status": "accepted",
        "payload": req.payload,
        "created_at": "2026-02-22T05:00:00",
        "updated_at": "2026-02-22T05:00:00",
        "scheduled_for": req.scheduled_for,
        "due_at": req.due_at,
        "expires_at": req.expires_at,
        "correlation_id": req.correlation_id,
        "payload_fingerprint": fingerprint,
        "result": None,
        "error": None,
        "error_code": None,
    }

    async def cleanup_scheduler_tasks_locked_fn(_now):
        return None

    async def load_scheduler_task_by_correlation_id_fn(_correlation_id):
        return dict(existing_from_db)

    async def persist_scheduler_task_snapshot_fn(_task):
        return None

    task, is_duplicate = await create_scheduler_task(
        req,
        scheduler_tasks=scheduler_tasks,
        scheduler_tasks_lock=asyncio.Lock(),
        cleanup_scheduler_tasks_locked_fn=cleanup_scheduler_tasks_locked_fn,
        load_scheduler_task_by_correlation_id_fn=load_scheduler_task_by_correlation_id_fn,
        task_payload_fingerprint_fn=policy_task_payload_fingerprint,
        task_payload_matches_fn=policy_task_payload_matches,
        new_scheduler_task_id_fn=lambda: "st-new",
        persist_scheduler_task_snapshot_fn=persist_scheduler_task_snapshot_fn,
    )

    assert is_duplicate is True
    assert task["task_id"] == "st-from-db"
    assert scheduler_tasks["st-from-db"]["correlation_id"] == req.correlation_id
