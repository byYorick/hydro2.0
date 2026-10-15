from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from ae3lite.application.use_cases import startup_recovery as recovery_module
from ae3lite.application.use_cases.startup_recovery import StartupRecoveryUseCase


NOW = datetime(2026, 10, 12, 12, 0, 0)


class _TaskRepository:
    def __init__(self, task):
        self.task = task

    async def get_by_id(self, *, task_id):
        assert task_id == self.task.id
        return self.task


class _CommandRepository:
    def __init__(self, rows):
        self.rows = rows

    async def list_unreconciled_for_terminal_tasks(self, *, limit):
        assert limit == 100
        return list(self.rows)


class _Gateway:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def reconcile_terminal_task_command(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self.result)


class _PidRepository:
    def __init__(self):
        self.calls = []

    async def reconcile_completed_dose(self, **kwargs):
        self.calls.append(kwargs)
        return True


class _AlertRepository:
    def __init__(self):
        self.calls = []

    async def raise_active(self, **kwargs):
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_terminal_done_dose_repairs_command_and_pid_state(monkeypatch: pytest.MonkeyPatch):
    events = []

    async def _create_zone_event(zone_id, event_type, payload):
        events.append((zone_id, event_type, payload))

    monkeypatch.setattr(recovery_module, "create_zone_event", _create_zone_event)
    task = SimpleNamespace(
        id=32,
        zone_id=3,
        status="completed",
        task_type="irrigation_start",
        topology="two_tank",
        current_stage="irrigation_check",
        workflow=SimpleNamespace(stage_retry_count=0),
        correction=None,
    )
    command = {
        "id": 901,
        "task_id": 32,
        "planner_step": "irrigation_check:corr_dose_ph:pump_acid",
        "stage_name": "irrigation_check",
        "channel": "pump_acid",
        "payload": {
            "cmd": "dose",
            "cmd_id": "ae3-t32-z3-s39",
            "params": {"ml": 2.0, "duration_ms": 2000},
        },
    }
    terminal_at = datetime(2026, 10, 12, 11, 59, 30)
    gateway = _Gateway(
        {
            "state": "done",
            "legacy_status": "DONE",
            "cmd_id": "ae3-t32-z3-s39",
            "response_details": {"duration_ms": 1750},
            "terminal_at": terminal_at,
        }
    )
    pid_repository = _PidRepository()
    alert_repository = _AlertRepository()
    use_case = StartupRecoveryUseCase(
        task_repository=_TaskRepository(task),
        lease_repository=SimpleNamespace(),
        command_gateway=gateway,
        command_repository=_CommandRepository([command]),
        pid_state_repository=pid_repository,
        alert_repository=alert_repository,
        use_startup_recovery_lock=False,
    )

    reconciled, unresolved = await use_case._reconcile_terminal_task_commands(now=NOW)

    assert (reconciled, unresolved) == (1, 0)
    assert pid_repository.calls == [
        {
            "zone_id": 3,
            "pid_type": "ph",
            "last_output_ms": 1750,
            "last_dose_at": terminal_at,
            "last_correction_kind": "ph_down",
            "ae_command_id": 901,
            "now": NOW,
        }
    ]
    assert events[0][1] == "AE_TERMINAL_TASK_COMMAND_RECONCILED"
    assert alert_repository.calls[0]["code"] == "biz_ae3_terminal_task_command_reconciled"


@pytest.mark.asyncio
async def test_terminal_non_terminal_command_stays_unresolved_and_alerts():
    task = SimpleNamespace(
        id=34,
        zone_id=3,
        status="completed",
        task_type="irrigation_start",
        topology="two_tank",
        current_stage="irrigation_check",
        workflow=SimpleNamespace(stage_retry_count=0),
        correction=None,
    )
    command = {
        "id": 902,
        "task_id": 34,
        "planner_step": "irrigation_check:corr_dose_ec:pump_npk",
        "stage_name": "irrigation_check",
        "channel": "pump_npk",
        "payload": {"cmd": "dose", "params": {"duration_ms": 2000}},
    }
    alerts = _AlertRepository()
    use_case = StartupRecoveryUseCase(
        task_repository=_TaskRepository(task),
        lease_repository=SimpleNamespace(),
        command_gateway=_Gateway(
            {
                "state": "waiting_command",
                "legacy_status": "RUNNING",
                "cmd_id": "ae3-t34-z3-s1",
                "response_details": {},
                "terminal_at": None,
            }
        ),
        command_repository=_CommandRepository([command]),
        pid_state_repository=_PidRepository(),
        alert_repository=alerts,
        use_startup_recovery_lock=False,
    )

    reconciled, unresolved = await use_case._reconcile_terminal_task_commands(now=NOW)

    assert (reconciled, unresolved) == (0, 1)
    assert alerts.calls[0]["code"] == "biz_ae3_terminal_task_command_unknown"


@pytest.mark.asyncio
async def test_terminal_command_error_is_reconciled_as_failed_alert() -> None:
    task = SimpleNamespace(
        id=35,
        zone_id=3,
        status="failed",
        task_type="irrigation_start",
        topology="two_tank",
        current_stage="irrigation_check",
        workflow=SimpleNamespace(stage_retry_count=0),
        correction=None,
    )
    command = {
        "id": 903,
        "task_id": 35,
        "planner_step": "irrigation_check:corr_dose_ec:pump_a",
        "stage_name": "irrigation_check",
        "channel": "pump_a",
        "payload": {"cmd": "dose", "params": {"duration_ms": 2000}},
    }
    alerts = _AlertRepository()
    use_case = StartupRecoveryUseCase(
        task_repository=_TaskRepository(task),
        lease_repository=SimpleNamespace(),
        command_gateway=_Gateway(
            {
                "state": "failed",
                "legacy_status": "ERROR",
                "cmd_id": "ae3-t35-z3-s1",
                "response_details": {"duration_ms": 0},
                "terminal_at": NOW,
            }
        ),
        command_repository=_CommandRepository([command]),
        pid_state_repository=_PidRepository(),
        alert_repository=alerts,
        use_startup_recovery_lock=False,
    )

    reconciled, unresolved = await use_case._reconcile_terminal_task_commands(now=NOW)

    assert (reconciled, unresolved) == (1, 0)
    assert alerts.calls[0]["code"] == "biz_ae3_terminal_task_command_failed"
