from __future__ import annotations

from types import SimpleNamespace

import pytest

from ae2lite.api_scheduler_execution import execute_scheduler_task


@pytest.mark.asyncio
async def test_execute_scheduler_task_skips_deleted_zone_without_executor_call():
    updates = []
    trace_ids = []
    infra_alert_calls = []
    infra_resolved_calls = []

    async def update_scheduler_task_fn(**kwargs):
        updates.append(dict(kwargs))

    async def validate_zone_exists_fn(_zone_id: int) -> bool:
        return False

    async def send_infra_exception_alert_fn(**kwargs):
        infra_alert_calls.append(dict(kwargs))

    async def send_infra_resolved_alert_fn(**kwargs):
        infra_resolved_calls.append(dict(kwargs))

    def build_execution_terminal_result_fn(**kwargs):
        payload = dict(kwargs)
        payload.setdefault("error", payload.get("error_code"))
        payload.setdefault("error_code", payload.get("error_code"))
        return payload

    def scheduler_task_executor_factory(**_kwargs):
        raise AssertionError("executor must not be created for deleted zone")

    req = SimpleNamespace(
        zone_id=17,
        task_type="diagnostics",
        payload={},
        correlation_id="corr-zone-missing",
        scheduled_for="2026-02-26T10:00:00",
    )

    await execute_scheduler_task(
        "st-zone-missing",
        req,
        "trace-zone-missing",
        command_bus=object(),
        command_bus_loop_id=None,
        zone_service=object(),
        zone_service_loop_id=None,
        validate_zone_exists_fn=validate_zone_exists_fn,
        is_loop_affinity_mismatch_fn=lambda _loop_id: False,
        update_scheduler_task_fn=update_scheduler_task_fn,
        update_command_effect_confirm_rate_fn=lambda *_args, **_kwargs: None,
        normalize_failed_execution_result_fn=lambda result: result,
        build_execution_terminal_result_fn=build_execution_terminal_result_fn,
        send_infra_exception_alert_fn=send_infra_exception_alert_fn,
        send_infra_resolved_alert_fn=send_infra_resolved_alert_fn,
        scheduler_task_executor_factory=scheduler_task_executor_factory,
        set_trace_id_fn=lambda trace_id: trace_ids.append(trace_id),
        logger=SimpleNamespace(error=lambda *_a, **_k: None, warning=lambda *_a, **_k: None),
        err_command_bus_unavailable="command_bus_unavailable",
        err_command_bus_loop_mismatch="command_bus_loop_mismatch",
        err_zone_service_loop_mismatch="zone_service_loop_mismatch",
        err_zone_not_found="zone_not_found",
        err_execution_exception="execution_exception",
    )

    assert trace_ids == ["trace-zone-missing"]
    assert len(updates) == 1
    assert updates[0]["status"] == "failed"
    assert updates[0]["error_code"] == "zone_not_found"
    assert updates[0]["result"]["decision"] == "skip"
    assert updates[0]["result"]["action_required"] is False
    assert infra_alert_calls == []
    assert infra_resolved_calls == []


@pytest.mark.asyncio
async def test_execute_scheduler_task_continues_when_zone_validation_temporarily_unavailable():
    updates = []
    rate_calls = []
    infra_resolved_calls = []

    async def update_scheduler_task_fn(**kwargs):
        updates.append(dict(kwargs))

    async def validate_zone_exists_fn(_zone_id: int) -> bool:
        raise RuntimeError("db unavailable")

    class _Executor:
        async def execute(self, **_kwargs):
            return {"success": True, "commands_total": 0}

    def scheduler_task_executor_factory(**_kwargs):
        return _Executor()

    req = SimpleNamespace(
        zone_id=18,
        task_type="diagnostics",
        payload={},
        correlation_id="corr-zone-check-failed",
        scheduled_for="2026-02-26T10:00:00",
    )

    await execute_scheduler_task(
        "st-zone-check-failed",
        req,
        None,
        command_bus=object(),
        command_bus_loop_id=None,
        zone_service=object(),
        zone_service_loop_id=None,
        validate_zone_exists_fn=validate_zone_exists_fn,
        is_loop_affinity_mismatch_fn=lambda _loop_id: False,
        update_scheduler_task_fn=update_scheduler_task_fn,
        update_command_effect_confirm_rate_fn=lambda task_type, result: rate_calls.append((task_type, result)),
        normalize_failed_execution_result_fn=lambda result: result,
        build_execution_terminal_result_fn=lambda **kwargs: dict(kwargs),
        send_infra_exception_alert_fn=lambda **_kwargs: None,
        send_infra_resolved_alert_fn=lambda **kwargs: infra_resolved_calls.append(dict(kwargs)),
        scheduler_task_executor_factory=scheduler_task_executor_factory,
        set_trace_id_fn=lambda _trace_id: None,
        logger=SimpleNamespace(error=lambda *_a, **_k: None, warning=lambda *_a, **_k: None),
        err_command_bus_unavailable="command_bus_unavailable",
        err_command_bus_loop_mismatch="command_bus_loop_mismatch",
        err_zone_service_loop_mismatch="zone_service_loop_mismatch",
        err_zone_not_found="zone_not_found",
        err_execution_exception="execution_exception",
    )

    assert [row["status"] for row in updates] == ["running", "completed"]
    assert len(rate_calls) == 1
    assert rate_calls[0][0] == "diagnostics"
    assert len(infra_resolved_calls) == 1
    assert infra_resolved_calls[0]["code"] == "infra_unknown_error"


@pytest.mark.asyncio
async def test_execute_scheduler_task_syncs_workflow_state_on_execution_exception():
    updates = []
    sync_calls = []
    infra_alert_calls = []
    infra_resolved_calls = []

    async def update_scheduler_task_fn(**kwargs):
        updates.append(dict(kwargs))

    async def validate_zone_exists_fn(_zone_id: int) -> bool:
        return True

    async def send_infra_exception_alert_fn(**kwargs):
        infra_alert_calls.append(dict(kwargs))

    async def send_infra_resolved_alert_fn(**kwargs):
        infra_resolved_calls.append(dict(kwargs))

    class _WorkflowStateSync:
        async def sync(self, **kwargs):
            sync_calls.append(dict(kwargs))

    class _Executor:
        workflow_state_sync = _WorkflowStateSync()

        async def execute(self, **_kwargs):
            raise TypeError("unexpected keyword argument 'stabilization_time_sec'")

    def scheduler_task_executor_factory(**_kwargs):
        return _Executor()

    req = SimpleNamespace(
        zone_id=6,
        task_type="diagnostics",
        payload={"workflow": "clean_fill_check"},
        correlation_id="corr-execution-exception",
        scheduled_for="2026-03-03T19:47:02.865755",
    )

    await execute_scheduler_task(
        "st-f9d2b19811554f3c916bce6a26ed2c4e",
        req,
        None,
        command_bus=object(),
        command_bus_loop_id=None,
        zone_service=object(),
        zone_service_loop_id=None,
        validate_zone_exists_fn=validate_zone_exists_fn,
        is_loop_affinity_mismatch_fn=lambda _loop_id: False,
        update_scheduler_task_fn=update_scheduler_task_fn,
        update_command_effect_confirm_rate_fn=lambda *_args, **_kwargs: None,
        normalize_failed_execution_result_fn=lambda result: result,
        build_execution_terminal_result_fn=lambda **kwargs: {
            **kwargs,
            "success": False,
            "error": kwargs.get("error_code"),
            "error_code": kwargs.get("error_code"),
            "reason_code": kwargs.get("error_code"),
            "decision": "fail",
        },
        send_infra_exception_alert_fn=send_infra_exception_alert_fn,
        send_infra_resolved_alert_fn=send_infra_resolved_alert_fn,
        scheduler_task_executor_factory=scheduler_task_executor_factory,
        set_trace_id_fn=lambda _trace_id: None,
        logger=SimpleNamespace(error=lambda *_a, **_k: None, warning=lambda *_a, **_k: None),
        err_command_bus_unavailable="command_bus_unavailable",
        err_command_bus_loop_mismatch="command_bus_loop_mismatch",
        err_zone_service_loop_mismatch="zone_service_loop_mismatch",
        err_zone_not_found="zone_not_found",
        err_execution_exception="execution_exception",
    )

    assert [row["status"] for row in updates] == ["running", "failed"]
    assert updates[-1]["error_code"] == "execution_exception"
    assert len(sync_calls) == 1
    assert sync_calls[0]["zone_id"] == 6
    assert sync_calls[0]["task_type"] == "diagnostics"
    assert sync_calls[0]["result"]["error_code"] == "execution_exception"
    assert sync_calls[0]["context"]["task_id"] == "st-f9d2b19811554f3c916bce6a26ed2c4e"
    assert len(infra_alert_calls) == 1
    assert infra_alert_calls[0]["code"] == "infra_unknown_error"
    assert infra_resolved_calls == []
