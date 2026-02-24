from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

from ae2lite.api_runtime_zone_routes import bind_zone_routes


class _DummyWorkflowStateStore:
    async def get(self, _zone_id: int):
        return {"workflow_phase": "idle", "payload_normalized": {"control_mode": "manual"}}

    async def set(self, **_kwargs):
        return None


def _bind_test_routes(*, validate_security_fn):
    app = FastAPI()
    store = _DummyWorkflowStateStore()

    async def validate_zone(_zone_id: int):
        return None

    async def load_latest_zone_task(_zone_id: int):
        return {"payload": {"config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}}}

    async def create_scheduler_task(_req):
        return {"task_id": "st-manual"}, False

    async def execute_scheduler_task(_task_id, _req, _trace_id):
        return None

    def spawn_background_task(coro, **_kwargs):
        coro.close()
        return None

    async def fetch_fn(*_args, **_kwargs):
        return []

    async def create_zone_event_fn(_zone_id, _event_type, _details):
        return None

    return bind_zone_routes(
        app,
        validate_scheduler_zone_fn=validate_zone,
        validate_scheduler_security_baseline_fn=validate_security_fn,
        load_latest_zone_task_fn=load_latest_zone_task,
        create_scheduler_task_fn=create_scheduler_task,
        execute_scheduler_task_fn=execute_scheduler_task,
        spawn_background_task_fn=spawn_background_task,
        workflow_state_store=store,
        default_topology="two_tank_drip_substrate_trays",
        fetch_fn=fetch_fn,
        create_zone_event_fn=create_zone_event_fn,
        get_trace_id_fn=lambda: None,
        logger=SimpleNamespace(info=lambda *_a, **_k: None, warning=lambda *_a, **_k: None),
    )


@pytest.mark.asyncio
async def test_control_mode_write_requires_security_baseline():
    async def validate_security(_request):
        raise HTTPException(status_code=401, detail="unauthorized")

    (_, _, set_control_mode, _) = _bind_test_routes(validate_security_fn=validate_security)

    with pytest.raises(HTTPException) as exc:
        await set_control_mode(
            zone_id=3,
            request=SimpleNamespace(headers={}),
            payload={"control_mode": "manual", "source": "frontend"},
        )

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_manual_step_requires_security_baseline():
    async def validate_security(_request):
        raise HTTPException(status_code=401, detail="unauthorized")

    (_, _, _, manual_step) = _bind_test_routes(validate_security_fn=validate_security)

    with pytest.raises(HTTPException) as exc:
        await manual_step(
            zone_id=3,
            request=SimpleNamespace(headers={}),
            payload={"manual_step": "clean_fill_start", "source": "frontend"},
        )

    assert exc.value.status_code == 401

