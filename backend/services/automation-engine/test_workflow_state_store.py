from __future__ import annotations

import pytest

from infrastructure.workflow_state_store import WorkflowStateStore


@pytest.mark.asyncio
async def test_get_normalizes_payload_from_json_string(monkeypatch):
    async def fetch_stub(*_args, **_kwargs):
        return [
            {
                "zone_id": 12,
                "workflow_phase": "idle",
                "started_at": None,
                "updated_at": None,
                "payload": '{"control_mode":"semi"}',
                "scheduler_task_id": None,
            }
        ]

    monkeypatch.setattr("infrastructure.workflow_state_store.fetch", fetch_stub)

    store = WorkflowStateStore()
    row = await store.get(12)
    assert row is not None
    assert row["payload_normalized"]["control_mode"] == "semi"


@pytest.mark.asyncio
async def test_list_active_normalizes_payload_from_json_bytes(monkeypatch):
    async def fetch_stub(*_args, **_kwargs):
        return [
            {
                "zone_id": 7,
                "workflow_phase": "tank_filling",
                "started_at": None,
                "updated_at": None,
                "payload": b'{"control_mode":"manual","workflow":"startup"}',
                "scheduler_task_id": "st-1",
            }
        ]

    monkeypatch.setattr("infrastructure.workflow_state_store.fetch", fetch_stub)

    store = WorkflowStateStore()
    rows = await store.list_active()
    assert len(rows) == 1
    assert rows[0]["payload_normalized"]["control_mode"] == "manual"
    assert rows[0]["payload_normalized"]["workflow"] == "startup"


@pytest.mark.asyncio
async def test_set_persists_payload_as_json_object(monkeypatch):
    captured = {}

    async def fetch_stub(*_args, **_kwargs):
        return []

    async def execute_stub(query, *args):
        captured["query"] = query
        captured["args"] = args
        return "INSERT 0 1"

    monkeypatch.setattr("infrastructure.workflow_state_store.fetch", fetch_stub)
    monkeypatch.setattr("infrastructure.workflow_state_store.execute", execute_stub)

    store = WorkflowStateStore()
    payload = {"workflow": "startup", "workflow_phase": "tank_filling"}
    await store.set(
        zone_id=99,
        workflow_phase="tank_filling",
        payload=payload,
        scheduler_task_id="st-99",
    )

    assert isinstance(captured["args"][3], dict)
    assert captured["args"][3] == payload
