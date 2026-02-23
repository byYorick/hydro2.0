from __future__ import annotations

import pytest

import scheduler_task_executor as ste


@pytest.fixture
def patch_scheduler_impl_init(monkeypatch):
    captured = {}

    def fake_init(self, command_bus, zone_service=None, workflow_state_store=None):
        captured["command_bus"] = command_bus
        captured["zone_service"] = zone_service
        captured["workflow_state_store"] = workflow_state_store
        self.command_bus = command_bus
        self.zone_service = zone_service
        self.workflow_state_store = workflow_state_store

    monkeypatch.setattr(ste._impl.SchedulerTaskExecutor, "__init__", fake_init)
    return captured


def test_ctor_applies_explicit_runtime_bindings(patch_scheduler_impl_init):
    async def fetch_fn(*args, **kwargs):
        return {"kind": "fetch", "args": args, "kwargs": kwargs}

    async def create_zone_event_fn(*args, **kwargs):
        return {"kind": "zone_event", "args": args, "kwargs": kwargs}

    async def send_infra_alert_fn(*args, **kwargs):
        return {"kind": "infra_alert", "args": args, "kwargs": kwargs}

    async def enqueue_internal_scheduler_task_fn(*args, **kwargs):
        return {"kind": "enqueue", "args": args, "kwargs": kwargs}

    bindings = ste.build_scheduler_executor_runtime_bindings(
        fetch_fn=fetch_fn,
        create_zone_event_fn=create_zone_event_fn,
        send_infra_alert_fn=send_infra_alert_fn,
        enqueue_internal_scheduler_task_fn=enqueue_internal_scheduler_task_fn,
    )

    executor = ste.SchedulerTaskExecutor(command_bus=object(), runtime_bindings=bindings)

    assert executor.fetch_fn is fetch_fn
    assert executor.create_zone_event_fn is create_zone_event_fn
    assert executor.send_infra_alert_fn is send_infra_alert_fn
    assert executor.enqueue_internal_scheduler_task_fn is enqueue_internal_scheduler_task_fn
    assert patch_scheduler_impl_init["zone_service"] is None


@pytest.mark.asyncio
async def test_default_runtime_bindings_use_public_patch_points(monkeypatch, patch_scheduler_impl_init):
    calls = []

    async def fake_fetch(*args, **kwargs):
        calls.append(("fetch", args, kwargs))
        return "fetch-ok"

    async def fake_create_zone_event(*args, **kwargs):
        calls.append(("zone_event", args, kwargs))
        return "event-ok"

    async def fake_send_infra_alert(*args, **kwargs):
        calls.append(("infra", args, kwargs))
        return "infra-ok"

    async def fake_enqueue_internal_scheduler_task(*args, **kwargs):
        calls.append(("enqueue", args, kwargs))
        return "enqueue-ok"

    monkeypatch.setattr(ste, "fetch", fake_fetch)
    monkeypatch.setattr(ste, "create_zone_event", fake_create_zone_event)
    monkeypatch.setattr(ste, "send_infra_alert", fake_send_infra_alert)
    monkeypatch.setattr(ste, "enqueue_internal_scheduler_task", fake_enqueue_internal_scheduler_task)

    executor = ste.SchedulerTaskExecutor(command_bus=object())

    assert await executor.fetch_fn("sql", 1) == "fetch-ok"
    assert await executor.create_zone_event_fn(3, "E", {"k": "v"}) == "event-ok"
    assert await executor.send_infra_alert_fn(code="x") == "infra-ok"
    assert await executor.enqueue_internal_scheduler_task_fn(9, "task", {}) == "enqueue-ok"

    assert [name for name, _, _ in calls] == ["fetch", "zone_event", "infra", "enqueue"]
    assert patch_scheduler_impl_init["workflow_state_store"] is None


@pytest.mark.asyncio
async def test_execute_delegates_to_policy_run(monkeypatch, patch_scheduler_impl_init):
    async def passthrough(*args, **kwargs):
        return None

    bindings = ste.build_scheduler_executor_runtime_bindings(
        fetch_fn=passthrough,
        create_zone_event_fn=passthrough,
        send_infra_alert_fn=passthrough,
        enqueue_internal_scheduler_task_fn=passthrough,
    )

    captured = {}

    async def fake_policy_run(**kwargs):
        captured.update(kwargs)
        return {"status": "ok", "source": "policy"}

    monkeypatch.setattr(ste._impl, "policy_run_scheduler_executor_execute", fake_policy_run)

    executor = ste.SchedulerTaskExecutor(command_bus=object(), runtime_bindings=bindings)
    result = await executor.execute(
        zone_id=12,
        task_type="diagnostics",
        payload={"workflow": "two_tank"},
        task_context={"trace_id": "trace-1"},
    )

    assert result == {"status": "ok", "source": "policy"}
    assert captured["executor"] is executor
    assert captured["zone_id"] == 12
    assert captured["task_type"] == "diagnostics"
    assert captured["payload"] == {"workflow": "two_tank"}
    assert captured["task_context"] == {"trace_id": "trace-1"}
    assert captured["send_infra_alert_fn"] is executor.send_infra_alert_fn
