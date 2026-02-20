"""Unit tests for workflow state store persistence rules."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

import pytest

import infrastructure.workflow_state_store as workflow_state_store_module
from infrastructure.workflow_state_store import WorkflowStateStore


@pytest.mark.asyncio
async def test_set_preserves_existing_control_mode_when_payload_omits_it(monkeypatch):
    store = WorkflowStateStore()
    captured: Dict[str, Any] = {}

    async def fake_get(zone_id: int):
        return {
            "zone_id": zone_id,
            "workflow_phase": "tank_filling",
            "started_at": datetime(2026, 2, 20, 0, 0, 0),
            "payload_normalized": {"control_mode": "manual", "workflow": "clean_fill_check"},
            "scheduler_task_id": "st-prev",
        }

    async def fake_execute(query: str, *args):
        captured["args"] = args

    monkeypatch.setattr(store, "get", fake_get)
    monkeypatch.setattr(workflow_state_store_module, "execute", fake_execute)

    await store.set(
        zone_id=6,
        workflow_phase="tank_filling",
        payload={"workflow": "solution_fill_check"},
        scheduler_task_id="st-next",
    )

    payload_json = captured["args"][3]
    payload = json.loads(payload_json)
    assert payload["workflow"] == "solution_fill_check"
    assert payload["control_mode"] == "manual"


@pytest.mark.asyncio
async def test_set_uses_payload_control_mode_override(monkeypatch):
    store = WorkflowStateStore()
    captured: Dict[str, Any] = {}

    async def fake_get(zone_id: int):
        return {
            "zone_id": zone_id,
            "workflow_phase": "idle",
            "started_at": None,
            "payload_normalized": {"control_mode": "manual"},
            "scheduler_task_id": None,
        }

    async def fake_execute(query: str, *args):
        captured["args"] = args

    monkeypatch.setattr(store, "get", fake_get)
    monkeypatch.setattr(workflow_state_store_module, "execute", fake_execute)

    await store.set(
        zone_id=6,
        workflow_phase="idle",
        payload={"control_mode": "auto"},
        scheduler_task_id=None,
    )

    payload_json = captured["args"][3]
    payload = json.loads(payload_json)
    assert payload["control_mode"] == "auto"
