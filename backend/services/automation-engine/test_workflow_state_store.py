"""Unit tests for workflow state store persistence rules."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

import pytest

import infrastructure.workflow_state_store as workflow_state_store_module
from infrastructure.workflow_state_store import WorkflowStateStore


@pytest.mark.asyncio
async def test_set_passes_payload_through_unchanged(monkeypatch):
    """WorkflowStateStore.set() передаёт payload как есть — без слияния с existing."""
    store = WorkflowStateStore()
    captured: Dict[str, Any] = {}

    async def fake_execute(query: str, *args):
        captured["args"] = args

    monkeypatch.setattr(workflow_state_store_module, "execute", fake_execute)

    await store.set(
        zone_id=6,
        workflow_phase="tank_filling",
        payload={"workflow": "solution_fill_check", "control_mode": "manual"},
        scheduler_task_id="st-next",
    )

    # args: (zone_id, normalized_phase, payload_json, scheduler_task_id)
    payload_json = captured["args"][2]
    payload = json.loads(payload_json)
    assert payload["workflow"] == "solution_fill_check"
    assert payload["control_mode"] == "manual"


@pytest.mark.asyncio
async def test_set_uses_payload_control_mode_override(monkeypatch):
    """control_mode в payload передаётся напрямую, без слияния из existing."""
    store = WorkflowStateStore()
    captured: Dict[str, Any] = {}

    async def fake_execute(query: str, *args):
        captured["args"] = args

    monkeypatch.setattr(workflow_state_store_module, "execute", fake_execute)

    await store.set(
        zone_id=6,
        workflow_phase="idle",
        payload={"control_mode": "auto"},
        scheduler_task_id=None,
    )

    # args: (zone_id, normalized_phase, payload_json, scheduler_task_id)
    payload_json = captured["args"][2]
    payload = json.loads(payload_json)
    assert payload["control_mode"] == "auto"
