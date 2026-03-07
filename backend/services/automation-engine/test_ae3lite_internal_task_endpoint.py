from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException

from ae3lite.api import bind_internal_task_route
from ae3lite.application.dto import TaskStatusView


def _bind_test_route(*, validate_security_fn, task_view: TaskStatusView | None):
    app = FastAPI()

    async def load_task_status(task_id: int) -> TaskStatusView | None:
        if task_view is None:
            return None
        assert task_id == task_view.task_id
        return task_view

    bind_internal_task_route(
        app,
        validate_scheduler_security_baseline_fn=validate_security_fn,
        load_task_status_fn=load_task_status,
    )
    return next(route.endpoint for route in app.routes if route.path == "/internal/tasks/{task_id}")


@pytest.mark.asyncio
async def test_internal_task_status_requires_security_baseline() -> None:
    async def validate_security(_request):
        raise HTTPException(status_code=401, detail="unauthorized")

    endpoint = _bind_test_route(validate_security_fn=validate_security, task_view=None)

    with pytest.raises(HTTPException) as exc:
        await endpoint(task_id=15, request=SimpleNamespace(headers={}))

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_internal_task_status_returns_404_when_task_not_found() -> None:
    async def validate_security(_request):
        return None

    endpoint = _bind_test_route(validate_security_fn=validate_security, task_view=None)

    with pytest.raises(HTTPException) as exc:
        await endpoint(task_id=91, request=SimpleNamespace(headers={"authorization": "Bearer test"}))

    assert exc.value.status_code == 404
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("error") == "task_not_found"
    assert detail.get("task_id") == 91


@pytest.mark.asyncio
async def test_internal_task_status_returns_canonical_payload() -> None:
    now = datetime(2026, 3, 6, 12, 30, tzinfo=timezone.utc).replace(tzinfo=None)

    async def validate_security(_request):
        return None

    endpoint = _bind_test_route(
        validate_security_fn=validate_security,
        task_view=TaskStatusView(
            task_id=44,
            zone_id=7,
            task_type="cycle_start",
            status="waiting_command",
            error_code=None,
            error_message=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        ),
    )

    response = await endpoint(task_id=44, request=SimpleNamespace(headers={"authorization": "Bearer test"}))

    assert response == {
        "status": "ok",
        "data": {
            "task_id": 44,
            "zone_id": 7,
            "task_type": "cycle_start",
            "status": "waiting_command",
            "error_code": None,
            "error_message": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "completed_at": None,
        },
    }
