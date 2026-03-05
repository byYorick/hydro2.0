from __future__ import annotations

import pytest

import executor.executor_run as executor_run


class _LoggerStub:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None


class _ZoneServiceStub:
    def __init__(self) -> None:
        self.reset_calls: list[int] = []

    def reset_zone_correction_anomaly_state(self, zone_id: int):
        self.reset_calls.append(zone_id)
        return {"changed": True}


class _ExecutorStub:
    def __init__(self, zone_service=None) -> None:
        self.zone_service = zone_service


@pytest.mark.asyncio
async def test_run_scheduler_executor_execute_resets_anomaly_state_for_cycle_start(monkeypatch):
    zone_service = _ZoneServiceStub()
    executor = _ExecutorStub(zone_service=zone_service)

    async def fake_run_executor_execute_flow(**_kwargs):
        return {"success": True}

    async def fake_send_infra_alert(**_kwargs):
        return True

    monkeypatch.setattr(executor_run, "run_executor_execute_flow", fake_run_executor_execute_flow)

    result = await executor_run.run_scheduler_executor_execute(
        executor=executor,
        zone_id=447,
        task_type="diagnostics",
        payload={"workflow": "cycle_start"},
        task_context=None,
        get_task_mapping_fn=lambda *_args, **_kwargs: None,
        send_infra_alert_fn=fake_send_infra_alert,
        log_structured_fn=lambda **_kwargs: None,
        logger_obj=_LoggerStub(),
        auto_logic_climate_guards_v1=False,
        auto_logic_extended_outcome_v1=False,
        workflow_phase_irrigating="irrigating",
    )

    assert result == {"success": True}
    assert zone_service.reset_calls == [447]


@pytest.mark.asyncio
async def test_run_scheduler_executor_execute_skips_anomaly_reset_for_non_cycle_start(monkeypatch):
    zone_service = _ZoneServiceStub()
    executor = _ExecutorStub(zone_service=zone_service)

    async def fake_run_executor_execute_flow(**_kwargs):
        return {"success": True}

    async def fake_send_infra_alert(**_kwargs):
        return True

    monkeypatch.setattr(executor_run, "run_executor_execute_flow", fake_run_executor_execute_flow)

    result = await executor_run.run_scheduler_executor_execute(
        executor=executor,
        zone_id=447,
        task_type="irrigation",
        payload={"workflow": "irrigation"},
        task_context=None,
        get_task_mapping_fn=lambda *_args, **_kwargs: None,
        send_infra_alert_fn=fake_send_infra_alert,
        log_structured_fn=lambda **_kwargs: None,
        logger_obj=_LoggerStub(),
        auto_logic_climate_guards_v1=False,
        auto_logic_extended_outcome_v1=False,
        workflow_phase_irrigating="irrigating",
    )

    assert result == {"success": True}
    assert zone_service.reset_calls == []

