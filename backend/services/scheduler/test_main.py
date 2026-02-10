"""Tests for scheduler planner-only mode."""

import pytest
from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch
import httpx
import sys
import types

import main as scheduler_main
from main import (
    _ACTIVE_SCHEDULE_TASKS,
    _ACTIVE_TASKS,
    _WINDOW_LAST_STATE,
    _parse_time_spec,
    _extract_simulation_clock,
    _schedule_crossings,
    ensure_scheduler_bootstrap_ready,
    get_active_schedules,
    send_scheduler_bootstrap_heartbeat,
    submit_task_to_automation_engine,
    wait_task_completion,
    reconcile_active_tasks,
    execute_scheduled_task,
    check_and_execute_schedules,
    process_internal_enqueued_tasks,
)


@pytest.fixture(autouse=True)
def reset_scheduler_runtime_state():
    _ACTIVE_TASKS.clear()
    _ACTIVE_SCHEDULE_TASKS.clear()
    _WINDOW_LAST_STATE.clear()
    scheduler_main._bootstrap_ready = False
    scheduler_main._bootstrap_lease_id = None
    scheduler_main._bootstrap_next_attempt_at = None
    scheduler_main._bootstrap_next_heartbeat_at = None
    scheduler_main._bootstrap_lease_expires_at = None
    scheduler_main._bootstrap_retry_idx = 0
    yield
    _ACTIVE_TASKS.clear()
    _ACTIVE_SCHEDULE_TASKS.clear()
    _WINDOW_LAST_STATE.clear()
    scheduler_main._bootstrap_ready = False
    scheduler_main._bootstrap_lease_id = None
    scheduler_main._bootstrap_next_attempt_at = None
    scheduler_main._bootstrap_next_heartbeat_at = None
    scheduler_main._bootstrap_lease_expires_at = None
    scheduler_main._bootstrap_retry_idx = 0


def test_parse_time_spec():
    assert _parse_time_spec("08:00") == time(8, 0)
    assert _parse_time_spec("14:30") == time(14, 30)
    assert _parse_time_spec("invalid") is None
    assert _parse_time_spec("25:00") is None


def test_extract_simulation_clock_scales_time():
    real_start = datetime(2025, 1, 1, 0, 0, 0)
    row = {
        "zone_id": 1,
        "scenario": {
            "simulation": {
                "real_started_at": real_start.isoformat(),
                "sim_started_at": real_start.isoformat(),
                "time_scale": 60,
            }
        },
        "duration_hours": 1,
        "created_at": real_start,
    }
    clock = _extract_simulation_clock(row)
    assert clock is not None
    with patch("main.utcnow") as mock_utcnow:
        mock_utcnow.return_value = real_start.replace(tzinfo=timezone.utc) + timedelta(seconds=60)
        sim_now = clock.now()
    assert sim_now == real_start + timedelta(hours=1)


def test_schedule_crossings_across_midnight():
    last_dt = datetime(2025, 1, 1, 23, 30, 0)
    now_dt = datetime(2025, 1, 2, 0, 30, 0)
    target = time(0, 15)
    crossings = _schedule_crossings(last_dt, now_dt, target)
    assert crossings == [datetime(2025, 1, 2, 0, 15, 0)]


@pytest.mark.asyncio
async def test_get_active_schedules_builds_abstract_tasks():
    repositories_module = types.ModuleType("repositories")
    laravel_module = types.ModuleType("repositories.laravel_api_repository")

    class DummyLaravelApiRepository:
        pass

    laravel_module.LaravelApiRepository = DummyLaravelApiRepository
    sys.modules["repositories"] = repositories_module
    sys.modules["repositories.laravel_api_repository"] = laravel_module

    with patch("main.fetch") as mock_fetch, \
         patch("repositories.laravel_api_repository.LaravelApiRepository") as mock_api_cls:
        mock_fetch.return_value = [{"zone_id": 28}]
        mock_api = AsyncMock()
        mock_api.get_effective_targets_batch.return_value = {
            28: {
                "zone_id": 28,
                "targets": {
                    "irrigation": {"interval_sec": 1200, "duration_sec": 20},
                    "lighting": {"photoperiod_hours": 18, "start_time": "06:00"},
                    "ventilation": {"interval_sec": 900},
                    "mist": {"times": ["08:00", "12:00"]},
                    "diagnostics": {"interval_sec": 1800},
                },
            }
        }
        mock_api_cls.return_value = mock_api

        schedules = await get_active_schedules()

    types_seen = {entry["type"] for entry in schedules}
    assert "irrigation" in types_seen
    assert "lighting" in types_seen
    assert "ventilation" in types_seen
    assert "mist" in types_seen
    assert "diagnostics" in types_seen


@pytest.mark.asyncio
async def test_bootstrap_ready_and_heartbeat_flow():
    bootstrap_response = Mock()
    bootstrap_response.status_code = 200
    bootstrap_response.content = b"{}"
    bootstrap_response.json = Mock(return_value={
        "status": "ok",
        "data": {
            "bootstrap_status": "ready",
            "lease_id": "lease-1",
            "lease_ttl_sec": 60,
            "poll_interval_sec": 5,
        },
    })

    heartbeat_response = Mock()
    heartbeat_response.status_code = 200
    heartbeat_response.content = b"{}"
    heartbeat_response.json = Mock(return_value={
        "status": "ok",
        "data": {
            "bootstrap_status": "ready",
            "lease_id": "lease-1",
            "lease_ttl_sec": 60,
        },
    })

    bootstrap_client = AsyncMock()
    bootstrap_client.__aenter__ = AsyncMock(return_value=bootstrap_client)
    bootstrap_client.__aexit__ = AsyncMock(return_value=None)
    bootstrap_client.post = AsyncMock(return_value=bootstrap_response)

    heartbeat_client = AsyncMock()
    heartbeat_client.__aenter__ = AsyncMock(return_value=heartbeat_client)
    heartbeat_client.__aexit__ = AsyncMock(return_value=None)
    heartbeat_client.post = AsyncMock(return_value=heartbeat_response)

    with patch("httpx.AsyncClient", side_effect=[bootstrap_client, heartbeat_client]), \
         patch("main.send_service_log"):
        assert await ensure_scheduler_bootstrap_ready() is True
        assert scheduler_main._bootstrap_ready is True
        assert scheduler_main._bootstrap_lease_id == "lease-1"

        scheduler_main._bootstrap_next_heartbeat_at = datetime.utcnow() - timedelta(seconds=1)
        assert await send_scheduler_bootstrap_heartbeat() is True


@pytest.mark.asyncio
async def test_bootstrap_wait_sets_retry_backoff():
    response = Mock()
    response.status_code = 200
    response.content = b"{}"
    response.json = Mock(return_value={"status": "ok", "data": {"bootstrap_status": "wait"}})

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)

    with patch("httpx.AsyncClient", return_value=client), \
         patch("main._emit_scheduler_diagnostic", new_callable=AsyncMock):
        assert await ensure_scheduler_bootstrap_ready() is False
        assert scheduler_main._bootstrap_ready is False
        assert scheduler_main._bootstrap_next_attempt_at is not None


@pytest.mark.asyncio
async def test_submit_task_to_automation_engine_success():
    with patch("httpx.AsyncClient") as mock_client_class, \
         patch("main.record_simulation_event", new_callable=AsyncMock):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(
            return_value={
                "status": "ok",
                "data": {"task_id": "st-1", "status": "accepted"},
            }
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        task_id = await submit_task_to_automation_engine(
            zone_id=1,
            task_type="irrigation",
            payload={"duration_sec": 20},
        )

    assert task_id == "st-1"


@pytest.mark.asyncio
async def test_submit_task_to_automation_engine_http_error():
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        task_id = await submit_task_to_automation_engine(
            zone_id=1,
            task_type="irrigation",
            payload={},
        )

    assert task_id is None


@pytest.mark.asyncio
async def test_wait_task_completion_completed():
    with patch("httpx.AsyncClient") as mock_client_class:
        response = Mock()
        response.status_code = 200
        response.content = b"{}"
        response.json = Mock(
            return_value={
                "status": "ok",
                "data": {"task_id": "st-1", "status": "completed"},
            }
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=response)
        mock_client_class.return_value = mock_client

        completed, status, payload = await wait_task_completion(
            zone_id=1,
            task_id="st-1",
            task_type="irrigation",
            timeout_sec=2,
        )

    assert completed is True
    assert status == "completed"
    assert payload["task_id"] == "st-1"


@pytest.mark.asyncio
async def test_wait_task_completion_failed_status():
    with patch("httpx.AsyncClient") as mock_client_class:
        response = Mock()
        response.status_code = 200
        response.content = b"{}"
        response.json = Mock(
            return_value={
                "status": "ok",
                "data": {"task_id": "st-1", "status": "failed", "error": "no_nodes"},
            }
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(return_value=response)
        mock_client_class.return_value = mock_client

        completed, status, _ = await wait_task_completion(
            zone_id=1,
            task_id="st-1",
            task_type="irrigation",
            timeout_sec=2,
        )

    assert completed is False
    assert status == "failed"


@pytest.mark.asyncio
async def test_execute_scheduled_task_success_flow():
    with patch("main.submit_task_to_automation_engine", new_callable=AsyncMock) as mock_submit, \
         patch("main.create_scheduler_log", new_callable=AsyncMock) as mock_log, \
         patch("main.create_zone_event", new_callable=AsyncMock) as mock_events:
        mock_submit.return_value = "st-1"

        dispatched = await execute_scheduled_task(
            zone_id=28,
            schedule={"type": "irrigation", "targets": {"irrigation": {"duration_sec": 20}}},
            trigger_time=datetime(2025, 1, 1, 8, 0, 0),
        )

    assert dispatched is True
    assert mock_log.await_count == 1
    statuses = [call.args[1] for call in mock_log.await_args_list]
    assert statuses == ["running"]
    assert "st-1" in _ACTIVE_TASKS
    event_types = [call.args[1] for call in mock_events.await_args_list]
    assert "SCHEDULE_TASK_ACCEPTED" in event_types


@pytest.mark.asyncio
async def test_execute_scheduled_task_end_to_end_with_automation_lifecycle():
    post_response = Mock()
    post_response.status_code = 200
    post_response.json = Mock(
        return_value={
            "status": "ok",
            "data": {"task_id": "st-e2e-1", "status": "accepted"},
        }
    )

    completed_response = Mock()
    completed_response.status_code = 200
    completed_response.content = b"{}"
    completed_response.json = Mock(
        return_value={
            "status": "ok",
            "data": {
                "task_id": "st-e2e-1",
                "status": "completed",
                "result": {"success": True, "commands_sent": 1},
            },
        }
    )

    submit_client = AsyncMock()
    submit_client.__aenter__ = AsyncMock(return_value=submit_client)
    submit_client.__aexit__ = AsyncMock(return_value=None)
    submit_client.post = AsyncMock(return_value=post_response)

    status_client = AsyncMock()
    status_client.__aenter__ = AsyncMock(return_value=status_client)
    status_client.__aexit__ = AsyncMock(return_value=None)
    status_client.get = AsyncMock(side_effect=[completed_response])

    with patch("httpx.AsyncClient", side_effect=[submit_client, status_client]), \
         patch("main.record_simulation_event", new_callable=AsyncMock), \
         patch("main.create_scheduler_log", new_callable=AsyncMock) as mock_log, \
         patch("main.create_zone_event", new_callable=AsyncMock) as mock_events, \
         patch("main.SCHEDULER_TASK_POLL_INTERVAL_SEC", 0.01):
        await execute_scheduled_task(
            zone_id=28,
            schedule={
                "type": "diagnostics",
                "targets": {"diagnostics": {"interval_sec": 1800}},
                "config": {"interval_sec": 1800},
            },
            trigger_time=datetime(2025, 1, 1, 8, 0, 0),
        )
        await reconcile_active_tasks()

    statuses = [call.args[1] for call in mock_log.await_args_list]
    assert statuses == ["running", "completed"]

    event_types = [call.args[1] for call in mock_events.await_args_list]
    assert "SCHEDULE_TASK_ACCEPTED" in event_types
    assert "SCHEDULE_TASK_COMPLETED" in event_types


@pytest.mark.asyncio
async def test_check_and_execute_schedules_runs_interval_task():
    with patch("main.get_active_schedules", new_callable=AsyncMock) as mock_schedules, \
         patch("main.get_simulation_clocks", new_callable=AsyncMock) as mock_sim_clocks, \
         patch("main.reconcile_active_tasks", new_callable=AsyncMock), \
         patch("main._should_run_interval_task", new_callable=AsyncMock) as mock_should_run, \
         patch("main.execute_scheduled_task", new_callable=AsyncMock) as mock_execute:
        mock_schedules.return_value = [
            {
                "zone_id": 28,
                "type": "irrigation",
                "interval_sec": 1200,
                "targets": {},
                "config": {},
            }
        ]
        mock_sim_clocks.return_value = {}
        mock_should_run.return_value = True
        mock_execute.return_value = True

        await check_and_execute_schedules()

    mock_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_and_execute_schedules_window_edge_trigger_dispatches_on_change_only():
    start_t = time(6, 0)
    end_t = time(18, 0)
    schedule = {
        "zone_id": 28,
        "type": "lighting",
        "start_time": start_t,
        "end_time": end_t,
        "targets": {},
        "config": {},
    }

    with patch("main.get_active_schedules", new_callable=AsyncMock) as mock_schedules, \
         patch("main.get_simulation_clocks", new_callable=AsyncMock) as mock_sim_clocks, \
         patch("main.reconcile_active_tasks", new_callable=AsyncMock), \
         patch("main.execute_scheduled_task", new_callable=AsyncMock) as mock_execute, \
         patch("main.datetime") as mock_datetime:
        mock_schedules.return_value = [schedule]
        mock_sim_clocks.return_value = {}
        mock_execute.return_value = True
        mock_datetime.now.return_value = datetime(2025, 1, 1, 9, 0, 0)

        await check_and_execute_schedules()
        await check_and_execute_schedules()

    assert mock_execute.await_count == 1


@pytest.mark.asyncio
async def test_submit_task_to_automation_engine_timeout():
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client_class.return_value = mock_client

        task_id = await submit_task_to_automation_engine(
            zone_id=1,
            task_type="irrigation",
            payload={},
        )

    assert task_id is None


@pytest.mark.asyncio
async def test_execute_scheduled_task_respects_preset_correlation_id_and_payload_merge():
    with patch("main.submit_task_to_automation_engine", new_callable=AsyncMock) as mock_submit, \
         patch("main.create_scheduler_log", new_callable=AsyncMock), \
         patch("main.create_zone_event", new_callable=AsyncMock):
        mock_submit.return_value = "st-custom-correlation"

        schedule = {
            "type": "irrigation",
            "targets": {"irrigation": {"duration_sec": 25}},
            "config": {"duration_sec": 25},
            "payload": {
                "custom_flag": True,
                "config": {"duration_sec": 30},
            },
            "correlation_id": "ae:self:28:irrigation:enq-1",
        }

        dispatched = await execute_scheduled_task(
            zone_id=28,
            schedule=schedule,
            trigger_time=datetime(2025, 1, 1, 8, 0, 0),
            schedule_key="internal_enqueue:enq-1",
        )

    assert dispatched is True
    call_kwargs = mock_submit.await_args.kwargs
    assert call_kwargs["correlation_id"] == "ae:self:28:irrigation:enq-1"
    assert call_kwargs["payload"]["custom_flag"] is True
    assert call_kwargs["payload"]["config"]["duration_sec"] == 30
    assert call_kwargs["payload"]["targets"]["irrigation"]["duration_sec"] == 25


@pytest.mark.asyncio
async def test_process_internal_enqueued_tasks_dispatches_pending_entry():
    now_dt = datetime(2025, 1, 1, 8, 0, 0)
    pending_entry = {
        "enqueue_id": "enq-123",
        "zone_id": 28,
        "task_type": "irrigation",
        "payload": {"custom": "value"},
        "scheduled_for": (now_dt - timedelta(seconds=1)).isoformat(),
        "expires_at": (now_dt + timedelta(minutes=2)).isoformat(),
        "correlation_id": "ae:self:28:irrigation:enq-123",
    }

    with patch("main._load_pending_internal_enqueues", new_callable=AsyncMock) as mock_load, \
         patch("main.execute_scheduled_task", new_callable=AsyncMock) as mock_execute, \
         patch("main._mark_internal_enqueue_status", new_callable=AsyncMock) as mock_mark, \
         patch("main.create_zone_event", new_callable=AsyncMock) as mock_event:
        mock_load.return_value = [pending_entry]
        mock_execute.return_value = True
        _ACTIVE_SCHEDULE_TASKS["internal_enqueue:enq-123"] = "st-internal-1"

        await process_internal_enqueued_tasks(now_dt)

    mock_execute.assert_awaited_once()
    execute_kwargs = mock_execute.await_args.kwargs
    assert execute_kwargs["zone_id"] == 28
    assert execute_kwargs["schedule"]["correlation_id"] == "ae:self:28:irrigation:enq-123"
    assert execute_kwargs["schedule"]["payload"]["custom"] == "value"
    assert execute_kwargs["schedule_key"] == "internal_enqueue:enq-123"
    mock_mark.assert_awaited_with(
        "ae_internal_enqueue_enq-123",
        "dispatched",
        {
            **pending_entry,
            "task_id": "st-internal-1",
            "scheduled_for": (now_dt - timedelta(seconds=1)).isoformat(),
        },
    )
    assert mock_event.await_args.args[1] == "SELF_TASK_DISPATCHED"


@pytest.mark.asyncio
async def test_process_internal_enqueued_tasks_marks_expired_entry():
    now_dt = datetime(2025, 1, 1, 8, 0, 0)
    pending_entry = {
        "enqueue_id": "enq-expired",
        "zone_id": 28,
        "task_type": "diagnostics",
        "payload": {},
        "scheduled_for": (now_dt - timedelta(minutes=2)).isoformat(),
        "expires_at": (now_dt - timedelta(seconds=1)).isoformat(),
    }

    with patch("main._load_pending_internal_enqueues", new_callable=AsyncMock) as mock_load, \
         patch("main.execute_scheduled_task", new_callable=AsyncMock) as mock_execute, \
         patch("main._mark_internal_enqueue_status", new_callable=AsyncMock) as mock_mark, \
         patch("main.create_zone_event", new_callable=AsyncMock) as mock_event:
        mock_load.return_value = [pending_entry]

        await process_internal_enqueued_tasks(now_dt)

    mock_execute.assert_not_awaited()
    assert mock_mark.await_args.args[0] == "ae_internal_enqueue_enq-expired"
    assert mock_mark.await_args.args[1] == "expired"
    assert mock_event.await_args.args[1] == "SELF_TASK_EXPIRED"
