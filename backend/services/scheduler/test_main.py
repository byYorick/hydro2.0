"""Tests for scheduler planner-only mode."""

import pytest
from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch
import multiprocessing
import asyncpg
import httpx
import sys
import types

import main as scheduler_main
from common.env import get_settings
from main import (
    _ACTIVE_SCHEDULE_TASKS,
    _ACTIVE_TASKS,
    _WINDOW_LAST_STATE,
    _parse_time_spec,
    _extract_simulation_clock,
    _schedule_crossings,
    ensure_scheduler_leader,
    release_scheduler_leader,
    ensure_scheduler_bootstrap_ready,
    get_active_schedules,
    send_scheduler_bootstrap_heartbeat,
    submit_task_to_automation_engine,
    wait_task_completion,
    reconcile_active_tasks,
    execute_scheduled_task,
    check_and_execute_schedules,
    process_internal_enqueued_tasks,
    recover_active_tasks_after_restart,
)


def _leader_probe_worker(hold_sec: float, result_queue):
    import asyncio
    import main as scheduler_main_local

    async def _run():
        scheduler_main_local.SCHEDULER_LEADER_ELECTION_ENABLED = True
        acquired = await scheduler_main_local.ensure_scheduler_leader()
        result_queue.put({"acquired": bool(acquired)})
        if acquired and hold_sec > 0:
            await asyncio.sleep(hold_sec)
        if acquired:
            await scheduler_main_local.release_scheduler_leader(reason="process_probe_done")

    try:
        asyncio.run(_run())
    except Exception as exc:
        result_queue.put({"error": f"{type(exc).__name__}: {exc}"})


@pytest.fixture(autouse=True)
def reset_scheduler_runtime_state():
    scheduler_main._LAST_SCHEDULE_CHECKS.clear()
    scheduler_main._LOADED_ZONE_CURSORS.clear()
    scheduler_main._TASK_TERMINAL_COUNTS.clear()
    scheduler_main._TASK_DEADLINE_VIOLATIONS.clear()
    _ACTIVE_TASKS.clear()
    _ACTIVE_SCHEDULE_TASKS.clear()
    _WINDOW_LAST_STATE.clear()
    scheduler_main._bootstrap_ready = False
    scheduler_main._bootstrap_lease_id = None
    scheduler_main._bootstrap_next_attempt_at = None
    scheduler_main._bootstrap_next_heartbeat_at = None
    scheduler_main._bootstrap_lease_expires_at = None
    scheduler_main._bootstrap_retry_idx = 0
    scheduler_main._leader_conn = None
    scheduler_main._leader_active = False
    scheduler_main._leader_next_attempt_at = None
    scheduler_main._leader_next_healthcheck_at = None
    yield
    scheduler_main._LAST_SCHEDULE_CHECKS.clear()
    scheduler_main._LOADED_ZONE_CURSORS.clear()
    scheduler_main._TASK_TERMINAL_COUNTS.clear()
    scheduler_main._TASK_DEADLINE_VIOLATIONS.clear()
    _ACTIVE_TASKS.clear()
    _ACTIVE_SCHEDULE_TASKS.clear()
    _WINDOW_LAST_STATE.clear()
    scheduler_main._bootstrap_ready = False
    scheduler_main._bootstrap_lease_id = None
    scheduler_main._bootstrap_next_attempt_at = None
    scheduler_main._bootstrap_next_heartbeat_at = None
    scheduler_main._bootstrap_lease_expires_at = None
    scheduler_main._bootstrap_retry_idx = 0
    scheduler_main._leader_conn = None
    scheduler_main._leader_active = False
    scheduler_main._leader_next_attempt_at = None
    scheduler_main._leader_next_healthcheck_at = None


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
async def test_resolve_zone_last_check_loads_persistent_cursor():
    now_dt = datetime(2025, 1, 1, 12, 0, 0)
    persisted_cursor = now_dt - timedelta(minutes=17)

    with patch("main.SCHEDULER_CURSOR_PERSIST_ENABLED", True), \
         patch("main.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{"details": {"last_check": persisted_cursor.isoformat()}}]
        resolved = await scheduler_main._resolve_zone_last_check(28, now_dt, None)

    assert resolved == persisted_cursor
    assert scheduler_main._LAST_SCHEDULE_CHECKS[28] == persisted_cursor
    assert 28 in scheduler_main._LOADED_ZONE_CURSORS


@pytest.mark.asyncio
async def test_resolve_zone_last_check_retries_after_temporary_db_error():
    now_dt = datetime(2025, 1, 1, 12, 0, 0)
    persisted_cursor = now_dt - timedelta(minutes=3)

    with patch("main.SCHEDULER_CURSOR_PERSIST_ENABLED", True), \
         patch("main.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = [RuntimeError("db down"), [{"details": {"last_check": persisted_cursor.isoformat()}}]]
        first = await scheduler_main._resolve_zone_last_check(31, now_dt, None)
        second = await scheduler_main._resolve_zone_last_check(31, now_dt, None)

    assert first == now_dt - timedelta(seconds=60)
    assert second == persisted_cursor
    assert 31 in scheduler_main._LOADED_ZONE_CURSORS


@pytest.mark.asyncio
async def test_should_run_interval_task_uses_latest_terminal_snapshot_for_throttling():
    now_real = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    last_failed_at = now_real.replace(tzinfo=None) - timedelta(seconds=120)

    with patch("main.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("main.utcnow") as mock_utcnow:
        mock_fetch.return_value = [{"created_at": last_failed_at}]
        mock_utcnow.return_value = now_real

        should_run = await scheduler_main._should_run_interval_task(
            task_name="diagnostics_zone_28",
            interval_sec=1200,
            sim_clock=None,
        )

    assert should_run is False
    query = " ".join(str(mock_fetch.await_args.args[0]).split()).lower()
    assert "status in ('completed', 'failed')" in query
    assert "order by created_at desc, id desc" in query


def test_apply_catchup_policy_skip_uses_single_now_trigger():
    now_dt = datetime(2025, 1, 1, 12, 0, 0)
    crossings = [now_dt - timedelta(minutes=10), now_dt - timedelta(minutes=5)]
    with patch("main.SCHEDULER_CATCHUP_POLICY", "skip"):
        planned = scheduler_main._apply_catchup_policy(crossings, now_dt)
    assert planned == [now_dt]


def test_apply_catchup_policy_replay_limited_respects_max_windows():
    now_dt = datetime(2025, 1, 1, 12, 0, 0)
    crossings = [
        now_dt - timedelta(minutes=30),
        now_dt - timedelta(minutes=20),
        now_dt - timedelta(minutes=10),
        now_dt - timedelta(minutes=5),
    ]
    with patch("main.SCHEDULER_CATCHUP_POLICY", "replay_limited"), \
         patch("main.SCHEDULER_CATCHUP_MAX_WINDOWS", 2):
        planned = scheduler_main._apply_catchup_policy(crossings, now_dt)
    assert planned == crossings[-2:]


def test_update_deadline_violation_rate_counts_rejected_and_expired():
    scheduler_main._update_deadline_violation_rate("diagnostics", "completed")
    scheduler_main._update_deadline_violation_rate("diagnostics", "failed")
    scheduler_main._update_deadline_violation_rate("diagnostics", "rejected")
    scheduler_main._update_deadline_violation_rate("diagnostics", "expired")

    assert scheduler_main._TASK_TERMINAL_COUNTS["diagnostics"] == 4
    assert scheduler_main._TASK_DEADLINE_VIOLATIONS["diagnostics"] == 2


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
                    "lighting": {"photoperiod_hours": 18, "start_time": "06:00", "interval_sec": 1800},
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
    lighting_entries = [entry for entry in schedules if entry.get("type") == "lighting"]
    assert any(entry.get("interval_sec") == 1800 for entry in lighting_entries)


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
async def test_bootstrap_backoff_emits_diagnostic():
    scheduler_main._bootstrap_next_attempt_at = datetime.utcnow() + timedelta(seconds=30)

    with patch("main._emit_scheduler_diagnostic", new_callable=AsyncMock) as mock_diag:
        assert await ensure_scheduler_bootstrap_ready() is False

    mock_diag.assert_awaited_once()
    assert mock_diag.await_args.kwargs["reason"] == "scheduler_bootstrap_retry_backoff"


@pytest.mark.asyncio
async def test_heartbeat_wait_switches_scheduler_to_safe_mode():
    scheduler_main._bootstrap_ready = True
    scheduler_main._bootstrap_lease_id = "lease-stale"
    scheduler_main._bootstrap_next_heartbeat_at = datetime.utcnow() - timedelta(seconds=1)

    heartbeat_response = Mock()
    heartbeat_response.status_code = 200
    heartbeat_response.content = b"{}"
    heartbeat_response.json = Mock(return_value={
        "status": "ok",
        "data": {
            "bootstrap_status": "wait",
            "reason": "lease_not_found",
        },
    })

    heartbeat_client = AsyncMock()
    heartbeat_client.__aenter__ = AsyncMock(return_value=heartbeat_client)
    heartbeat_client.__aexit__ = AsyncMock(return_value=None)
    heartbeat_client.post = AsyncMock(return_value=heartbeat_response)

    with patch("httpx.AsyncClient", return_value=heartbeat_client):
        ok = await send_scheduler_bootstrap_heartbeat()

    assert ok is False
    assert scheduler_main._bootstrap_ready is False
    assert scheduler_main._bootstrap_lease_id is None
    assert scheduler_main._bootstrap_next_attempt_at is not None


@pytest.mark.asyncio
async def test_scheduler_rebootstrap_after_lease_loss_recovers_ready_state():
    scheduler_main._bootstrap_ready = True
    scheduler_main._bootstrap_lease_id = "lease-stale"
    scheduler_main._bootstrap_next_heartbeat_at = datetime.utcnow() - timedelta(seconds=1)

    heartbeat_response = Mock()
    heartbeat_response.status_code = 200
    heartbeat_response.content = b"{}"
    heartbeat_response.json = Mock(return_value={
        "status": "ok",
        "data": {
            "bootstrap_status": "wait",
            "reason": "lease_not_found",
        },
    })

    bootstrap_response = Mock()
    bootstrap_response.status_code = 200
    bootstrap_response.content = b"{}"
    bootstrap_response.json = Mock(return_value={
        "status": "ok",
        "data": {
            "bootstrap_status": "ready",
            "lease_id": "lease-new",
            "lease_ttl_sec": 60,
            "poll_interval_sec": 5,
        },
    })

    heartbeat_client = AsyncMock()
    heartbeat_client.__aenter__ = AsyncMock(return_value=heartbeat_client)
    heartbeat_client.__aexit__ = AsyncMock(return_value=None)
    heartbeat_client.post = AsyncMock(return_value=heartbeat_response)

    bootstrap_client = AsyncMock()
    bootstrap_client.__aenter__ = AsyncMock(return_value=bootstrap_client)
    bootstrap_client.__aexit__ = AsyncMock(return_value=None)
    bootstrap_client.post = AsyncMock(return_value=bootstrap_response)

    with patch("httpx.AsyncClient", side_effect=[heartbeat_client, bootstrap_client]), \
         patch("main.send_service_log"):
        heartbeat_ok = await send_scheduler_bootstrap_heartbeat()
        assert heartbeat_ok is False

        # Симулируем завершение backoff-окна перед повторным bootstrap.
        scheduler_main._bootstrap_next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        ready = await ensure_scheduler_bootstrap_ready()

    assert ready is True
    assert scheduler_main._bootstrap_ready is True
    assert scheduler_main._bootstrap_lease_id == "lease-new"
    assert scheduler_main._bootstrap_next_attempt_at is None


@pytest.mark.asyncio
async def test_send_scheduler_bootstrap_heartbeat_http_error_emits_diagnostic():
    scheduler_main._bootstrap_ready = True
    scheduler_main._bootstrap_lease_id = "lease-1"
    scheduler_main._bootstrap_next_heartbeat_at = datetime.utcnow() - timedelta(seconds=1)

    heartbeat_response = Mock()
    heartbeat_response.status_code = 503
    heartbeat_response.text = "Service Unavailable"

    heartbeat_client = AsyncMock()
    heartbeat_client.__aenter__ = AsyncMock(return_value=heartbeat_client)
    heartbeat_client.__aexit__ = AsyncMock(return_value=None)
    heartbeat_client.post = AsyncMock(return_value=heartbeat_response)

    with patch("httpx.AsyncClient", return_value=heartbeat_client), \
         patch("main._emit_scheduler_diagnostic", new_callable=AsyncMock) as mock_diag:
        ok = await send_scheduler_bootstrap_heartbeat()

    assert ok is False
    mock_diag.assert_awaited_once()
    assert mock_diag.await_args.kwargs["reason"] == "scheduler_bootstrap_heartbeat_http_error"


@pytest.mark.asyncio
async def test_ensure_scheduler_leader_acquires_lock_and_releases():
    leader_conn = AsyncMock()
    leader_conn.fetchval = AsyncMock(return_value=True)
    leader_conn.execute = AsyncMock(return_value="SELECT 1")
    leader_conn.close = AsyncMock(return_value=None)
    leader_conn.is_closed = Mock(return_value=False)

    with patch("main.SCHEDULER_LEADER_ELECTION_ENABLED", True), \
         patch("main.asyncpg.connect", new_callable=AsyncMock) as mock_connect, \
         patch("main.send_service_log"):
        mock_connect.return_value = leader_conn
        is_leader = await ensure_scheduler_leader()
        assert is_leader is True
        assert scheduler_main._leader_active is True
        assert scheduler_main._leader_conn is leader_conn

        await release_scheduler_leader(reason="test_release")

    leader_conn.execute.assert_awaited_once()
    leader_conn.close.assert_awaited_once()
    assert scheduler_main._leader_active is False
    assert scheduler_main._leader_conn is None


@pytest.mark.asyncio
async def test_ensure_scheduler_leader_backoff_emits_diagnostic():
    scheduler_main._leader_next_attempt_at = datetime.utcnow() + timedelta(seconds=30)

    with patch("main.SCHEDULER_LEADER_ELECTION_ENABLED", True), \
         patch("main._emit_scheduler_diagnostic", new_callable=AsyncMock) as mock_diag:
        is_leader = await ensure_scheduler_leader()

    assert is_leader is False
    mock_diag.assert_awaited_once()
    assert mock_diag.await_args.kwargs["reason"] == "scheduler_leader_retry_backoff"


@pytest.mark.asyncio
async def test_ensure_scheduler_leader_returns_false_when_lock_busy():
    leader_conn = AsyncMock()
    leader_conn.fetchval = AsyncMock(return_value=False)
    leader_conn.close = AsyncMock(return_value=None)
    leader_conn.is_closed = Mock(return_value=False)

    with patch("main.SCHEDULER_LEADER_ELECTION_ENABLED", True), \
         patch("main.asyncpg.connect", new_callable=AsyncMock) as mock_connect, \
         patch("main._emit_scheduler_diagnostic", new_callable=AsyncMock):
        mock_connect.return_value = leader_conn
        is_leader = await ensure_scheduler_leader()

    assert is_leader is False
    assert scheduler_main._leader_active is False
    assert scheduler_main._leader_conn is None
    assert scheduler_main._leader_next_attempt_at is not None
    leader_conn.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_scheduler_leader_handles_connection_loss_and_reacquires():
    first_conn = AsyncMock()
    first_conn.fetchval = AsyncMock(side_effect=[True, Exception("db connection lost")])
    first_conn.execute = AsyncMock(return_value="SELECT 1")
    first_conn.close = AsyncMock(return_value=None)
    first_conn.is_closed = Mock(return_value=False)

    second_conn = AsyncMock()
    second_conn.fetchval = AsyncMock(return_value=True)
    second_conn.execute = AsyncMock(return_value="SELECT 1")
    second_conn.close = AsyncMock(return_value=None)
    second_conn.is_closed = Mock(return_value=False)

    with patch("main.SCHEDULER_LEADER_ELECTION_ENABLED", True), \
         patch("main.asyncpg.connect", new_callable=AsyncMock) as mock_connect, \
         patch("main._emit_scheduler_diagnostic", new_callable=AsyncMock):
        mock_connect.side_effect = [first_conn, second_conn]

        assert await ensure_scheduler_leader() is True
        scheduler_main._leader_next_healthcheck_at = datetime.utcnow() - timedelta(seconds=1)
        assert await ensure_scheduler_leader() is False
        assert scheduler_main._leader_active is False

        scheduler_main._leader_next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
        assert await ensure_scheduler_leader() is True
        assert scheduler_main._leader_conn is second_conn
        assert scheduler_main._leader_active is True


@pytest.mark.asyncio
async def test_scheduler_leader_lock_busy_with_real_postgres_session():
    settings = get_settings()
    external_conn = await asyncpg.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        database=settings.pg_db,
        user=settings.pg_user,
        password=settings.pg_pass,
    )
    try:
        acquired = await external_conn.fetchval(
            "SELECT pg_try_advisory_lock($1::bigint)",
            scheduler_main._LEADER_LOCK_KEY,
        )
        assert acquired is True

        with patch("main.SCHEDULER_LEADER_ELECTION_ENABLED", True):
            is_leader = await ensure_scheduler_leader()

        assert is_leader is False
        assert scheduler_main._leader_active is False
    finally:
        try:
            await external_conn.execute(
                "SELECT pg_advisory_unlock($1::bigint)",
                scheduler_main._LEADER_LOCK_KEY,
            )
        except Exception:
            pass
        await external_conn.close()


@pytest.mark.asyncio
async def test_scheduler_leader_failover_reacquire_with_real_postgres_session():
    settings = get_settings()
    external_conn = await asyncpg.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        database=settings.pg_db,
        user=settings.pg_user,
        password=settings.pg_pass,
    )
    try:
        acquired = await external_conn.fetchval(
            "SELECT pg_try_advisory_lock($1::bigint)",
            scheduler_main._LEADER_LOCK_KEY,
        )
        assert acquired is True

        with patch("main.SCHEDULER_LEADER_ELECTION_ENABLED", True):
            assert await ensure_scheduler_leader() is False

            await external_conn.execute(
                "SELECT pg_advisory_unlock($1::bigint)",
                scheduler_main._LEADER_LOCK_KEY,
            )
            scheduler_main._leader_next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
            assert await ensure_scheduler_leader() is True
            assert scheduler_main._leader_active is True
            assert scheduler_main._leader_conn is not None

            await release_scheduler_leader(reason="test_failover_release")

        assert scheduler_main._leader_active is False
    finally:
        try:
            if not external_conn.is_closed():
                await external_conn.close()
        except Exception:
            pass


def test_scheduler_multi_instance_has_single_leader_process_level():
    ctx = multiprocessing.get_context("fork")
    q1 = ctx.Queue()
    q2 = ctx.Queue()

    p1 = ctx.Process(target=_leader_probe_worker, args=(2.0, q1))
    p2 = ctx.Process(target=_leader_probe_worker, args=(0.0, q2))

    p1.start()
    first = q1.get(timeout=10)
    assert first.get("error") is None
    assert first["acquired"] is True

    p2.start()
    second = q2.get(timeout=10)
    assert second.get("error") is None
    assert second["acquired"] is False

    p2.join(timeout=10)
    p1.join(timeout=10)
    assert p1.exitcode == 0
    assert p2.exitcode == 0


def test_scheduler_multi_instance_failover_reacquire_process_level():
    ctx = multiprocessing.get_context("fork")
    q1 = ctx.Queue()
    q2 = ctx.Queue()
    q3 = ctx.Queue()

    p1 = ctx.Process(target=_leader_probe_worker, args=(1.5, q1))
    p2 = ctx.Process(target=_leader_probe_worker, args=(0.0, q2))

    p1.start()
    first = q1.get(timeout=10)
    assert first.get("error") is None
    assert first["acquired"] is True

    p2.start()
    second = q2.get(timeout=10)
    assert second.get("error") is None
    assert second["acquired"] is False

    p2.join(timeout=10)
    p1.join(timeout=10)
    assert p1.exitcode == 0
    assert p2.exitcode == 0

    p3 = ctx.Process(target=_leader_probe_worker, args=(0.0, q3))
    p3.start()
    third = q3.get(timeout=10)
    assert third.get("error") is None
    assert third["acquired"] is True
    p3.join(timeout=10)
    assert p3.exitcode == 0


@pytest.mark.asyncio
async def test_main_loop_does_not_dispatch_when_not_leader():
    with patch("main.start_http_server"), \
         patch("main.send_service_log"), \
         patch("main.ensure_scheduler_leader", new_callable=AsyncMock) as mock_leader, \
         patch("main.ensure_scheduler_bootstrap_ready", new_callable=AsyncMock) as mock_ready, \
         patch("main.send_scheduler_bootstrap_heartbeat", new_callable=AsyncMock) as mock_heartbeat, \
         patch("main.check_and_execute_schedules", new_callable=AsyncMock) as mock_dispatch, \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        mock_leader.side_effect = [False, KeyboardInterrupt()]
        await scheduler_main.main()

    mock_ready.assert_not_awaited()
    mock_heartbeat.assert_not_awaited()
    mock_dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_main_loop_does_not_dispatch_when_heartbeat_fails_after_ready():
    with patch("main.start_http_server"), \
         patch("main.send_service_log"), \
         patch("main.ensure_scheduler_leader", new_callable=AsyncMock) as mock_leader, \
         patch("main.ensure_scheduler_bootstrap_ready", new_callable=AsyncMock) as mock_ready, \
         patch("main.send_scheduler_bootstrap_heartbeat", new_callable=AsyncMock) as mock_heartbeat, \
         patch("main.check_and_execute_schedules", new_callable=AsyncMock) as mock_dispatch, \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        mock_leader.side_effect = [True, True]
        mock_ready.side_effect = [True, KeyboardInterrupt()]
        mock_heartbeat.return_value = False

        await scheduler_main.main()

    mock_dispatch.assert_not_awaited()
    mock_heartbeat.assert_awaited_once()


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
async def test_submit_task_to_automation_engine_sets_due_and_expires():
    with patch("httpx.AsyncClient") as mock_client_class, \
         patch("main.record_simulation_event", new_callable=AsyncMock):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(
            return_value={
                "status": "ok",
                "data": {"task_id": "st-deadline-1", "status": "accepted"},
            }
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        scheduled_for = "2025-01-01T08:00:00"
        task_id = await submit_task_to_automation_engine(
            zone_id=1,
            task_type="diagnostics",
            payload={"reason": "deadline-contract"},
            scheduled_for=scheduled_for,
            correlation_id="sch:z1:diagnostics:deadline-contract",
        )

    assert task_id == "st-deadline-1"

    submitted_payload = mock_client.post.await_args.kwargs["json"]
    due_at_dt = datetime.fromisoformat(submitted_payload["due_at"])
    expires_at_dt = datetime.fromisoformat(submitted_payload["expires_at"])
    scheduled_dt = datetime.fromisoformat(submitted_payload["scheduled_for"])

    assert submitted_payload["scheduled_for"] == scheduled_for
    assert (due_at_dt - scheduled_dt).total_seconds() == scheduler_main.SCHEDULER_DUE_GRACE_SEC
    assert (expires_at_dt - scheduled_dt).total_seconds() == scheduler_main.SCHEDULER_EXPIRES_AFTER_SEC


@pytest.mark.asyncio
async def test_submit_task_to_automation_engine_include_response_meta_returns_status():
    with patch("httpx.AsyncClient") as mock_client_class, \
         patch("main.record_simulation_event", new_callable=AsyncMock) as mock_sim_event:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(
            return_value={
                "status": "ok",
                "data": {
                    "task_id": "st-rejected-1",
                    "status": "rejected",
                    "error_code": "task_due_deadline_exceeded",
                },
            }
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        submit_meta = await submit_task_to_automation_engine(
            zone_id=1,
            task_type="diagnostics",
            payload={"reason": "deadline-contract"},
            scheduled_for="2025-01-01T08:00:00",
            correlation_id="sch:z1:diagnostics:deadline-fast-fail",
            include_response_meta=True,
        )

    assert isinstance(submit_meta, dict)
    assert submit_meta["task_id"] == "st-rejected-1"
    assert submit_meta["status"] == "rejected"
    assert submit_meta["payload"]["error_code"] == "task_due_deadline_exceeded"
    assert mock_sim_event.await_args.kwargs["status"] == "rejected"


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
async def test_wait_task_completion_expired_status():
    with patch("httpx.AsyncClient") as mock_client_class:
        response = Mock()
        response.status_code = 200
        response.content = b"{}"
        response.json = Mock(
            return_value={
                "status": "ok",
                "data": {"task_id": "st-1", "status": "expired", "error_code": "task_expired"},
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

    assert completed is False
    assert status == "expired"
    assert payload["error_code"] == "task_expired"


@pytest.mark.asyncio
async def test_reconcile_active_tasks_handles_expired_status_as_terminal():
    accepted_at = datetime(2025, 1, 1, 8, 0, 0)
    _ACTIVE_TASKS["st-expired-1"] = {
        "zone_id": 28,
        "task_type": "diagnostics",
        "task_name": "diagnostics_zone_28",
        "accepted_at": accepted_at,
        "schedule_key": "zone:28|type:diagnostics|interval=1800",
        "correlation_id": "sch:z28:diagnostics:expired",
    }
    _ACTIVE_SCHEDULE_TASKS["zone:28|type:diagnostics|interval=1800"] = "st-expired-1"

    status_payload = {
        "task_id": "st-expired-1",
        "status": "expired",
        "error": "task_expired",
        "error_code": "task_expired",
        "result": {
            "action_required": False,
            "decision": "skip",
            "reason_code": "task_expired",
            "error_code": "task_expired",
        },
    }

    with patch("main._fetch_task_status_once", new_callable=AsyncMock) as mock_status, \
         patch("main.create_scheduler_log", new_callable=AsyncMock) as mock_log, \
         patch("main.create_zone_event", new_callable=AsyncMock) as mock_event:
        mock_status.return_value = ("expired", status_payload)
        await reconcile_active_tasks()

    assert "st-expired-1" not in _ACTIVE_TASKS
    assert "zone:28|type:diagnostics|interval=1800" not in _ACTIVE_SCHEDULE_TASKS
    mock_log.assert_awaited_once()
    assert mock_log.await_args.args[1] == "failed"
    assert mock_log.await_args.args[2]["status"] == "expired"
    assert mock_log.await_args.args[2]["error_code"] == "task_expired"
    mock_event.assert_awaited_once()
    assert mock_event.await_args.args[1] == "SCHEDULE_TASK_FAILED"
    assert mock_event.await_args.args[2]["status"] == "expired"
    assert mock_event.await_args.args[2]["error_code"] == "task_expired"


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
    assert mock_log.await_count == 2
    statuses = [call.args[1] for call in mock_log.await_args_list]
    assert statuses == ["running", "accepted"]
    assert "st-1" in _ACTIVE_TASKS
    event_types = [call.args[1] for call in mock_events.await_args_list]
    assert "SCHEDULE_TASK_ACCEPTED" in event_types


@pytest.mark.asyncio
async def test_execute_scheduled_task_busy_emits_diagnostic_and_skips_dispatch():
    _ACTIVE_TASKS["st-busy-1"] = {"zone_id": 28, "task_type": "irrigation"}
    _ACTIVE_SCHEDULE_TASKS["busy-key"] = "st-busy-1"

    with patch("main._emit_scheduler_diagnostic", new_callable=AsyncMock) as mock_diag, \
         patch("main.create_scheduler_log", new_callable=AsyncMock) as mock_log, \
         patch("main.submit_task_to_automation_engine", new_callable=AsyncMock) as mock_submit:
        dispatched = await execute_scheduled_task(
            zone_id=28,
            schedule={"type": "irrigation", "targets": {"irrigation": {"duration_sec": 20}}},
            trigger_time=datetime(2025, 1, 1, 8, 0, 0),
            schedule_key="busy-key",
        )

    assert dispatched is False
    mock_diag.assert_awaited_once()
    assert mock_diag.await_args.kwargs["reason"] == "schedule_busy_skip"
    mock_log.assert_not_awaited()
    mock_submit.assert_not_awaited()


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
    assert statuses == ["running", "accepted", "completed"]

    event_types = [call.args[1] for call in mock_events.await_args_list]
    assert "SCHEDULE_TASK_ACCEPTED" in event_types
    assert "SCHEDULE_TASK_COMPLETED" in event_types


@pytest.mark.asyncio
async def test_execute_scheduled_task_terminal_rejected_on_submit_does_not_register_active_task():
    terminal_payload = {
        "task_id": "st-rejected-fast-fail",
        "status": "rejected",
        "result": {
            "action_required": False,
            "decision": "skip",
            "reason_code": "task_due_deadline_exceeded",
            "error_code": "task_due_deadline_exceeded",
        },
        "error": "task_due_deadline_exceeded",
        "error_code": "task_due_deadline_exceeded",
    }

    with patch("main.submit_task_to_automation_engine", new_callable=AsyncMock) as mock_submit, \
         patch("main._fetch_task_status_once", new_callable=AsyncMock) as mock_fetch_status, \
         patch("main.create_scheduler_log", new_callable=AsyncMock) as mock_log, \
         patch("main.create_zone_event", new_callable=AsyncMock) as mock_event:
        mock_submit.return_value = {
            "task_id": "st-rejected-fast-fail",
            "status": "rejected",
            "payload": {},
        }
        mock_fetch_status.return_value = ("rejected", terminal_payload)

        dispatched = await execute_scheduled_task(
            zone_id=28,
            schedule={"type": "diagnostics", "targets": {}, "config": {}},
            trigger_time=datetime(2025, 1, 1, 8, 0, 0),
            schedule_key="zone:28|type:diagnostics|interval=1800",
        )

    assert dispatched is False
    assert "st-rejected-fast-fail" not in _ACTIVE_TASKS
    assert "zone:28|type:diagnostics|interval=1800" not in _ACTIVE_SCHEDULE_TASKS

    statuses = [call.args[1] for call in mock_log.await_args_list]
    assert statuses == ["running", "failed"]
    failure_payload = mock_log.await_args_list[-1].args[2]
    assert failure_payload["status"] == "rejected"
    assert failure_payload["terminal_on_submit"] is True
    assert scheduler_main._TASK_TERMINAL_COUNTS["diagnostics"] == 1
    assert scheduler_main._TASK_DEADLINE_VIOLATIONS["diagnostics"] == 1

    event_types = [call.args[1] for call in mock_event.await_args_list]
    assert event_types == ["SCHEDULE_TASK_FAILED"]
    assert mock_event.await_args.args[2]["status"] == "rejected"


@pytest.mark.asyncio
async def test_execute_scheduled_task_terminal_submit_keeps_terminal_when_fetch_returns_non_terminal():
    with patch("main.submit_task_to_automation_engine", new_callable=AsyncMock) as mock_submit, \
         patch("main._fetch_task_status_once", new_callable=AsyncMock) as mock_fetch_status, \
         patch("main.create_scheduler_log", new_callable=AsyncMock) as mock_log, \
         patch("main.create_zone_event", new_callable=AsyncMock) as mock_event:
        mock_submit.return_value = {
            "task_id": "st-race-terminal",
            "status": "rejected",
            "payload": {
                "task_id": "st-race-terminal",
                "status": "rejected",
                "error_code": "task_due_deadline_exceeded",
            },
        }
        # Защита от race: если status API временно вернул non-terminal accepted,
        # scheduler должен сохранить terminal статус из submit.
        mock_fetch_status.return_value = (
            "accepted",
            {
                "task_id": "st-race-terminal",
                "status": "accepted",
            },
        )

        dispatched = await execute_scheduled_task(
            zone_id=28,
            schedule={"type": "diagnostics", "targets": {}, "config": {}},
            trigger_time=datetime(2025, 1, 1, 8, 0, 0),
            schedule_key="zone:28|type:diagnostics|interval=1800",
        )

    assert dispatched is False
    assert "st-race-terminal" not in _ACTIVE_TASKS
    assert "zone:28|type:diagnostics|interval=1800" not in _ACTIVE_SCHEDULE_TASKS
    failure_payload = mock_log.await_args_list[-1].args[2]
    assert failure_payload["status"] == "rejected"
    assert failure_payload["terminal_on_submit"] is True
    assert mock_event.await_args.args[2]["status"] == "rejected"


@pytest.mark.asyncio
async def test_check_and_execute_schedules_runs_interval_task():
    with patch("main.get_active_schedules", new_callable=AsyncMock) as mock_schedules, \
         patch("main.get_simulation_clocks", new_callable=AsyncMock) as mock_sim_clocks, \
         patch("main.reconcile_active_tasks", new_callable=AsyncMock), \
         patch("main.process_internal_enqueued_tasks", new_callable=AsyncMock), \
         patch("main._resolve_zone_last_check", new_callable=AsyncMock) as mock_resolve_last, \
         patch("main._should_run_interval_task", new_callable=AsyncMock) as mock_should_run, \
         patch("main.execute_scheduled_task", new_callable=AsyncMock) as mock_execute, \
         patch("main._persist_zone_cursor", new_callable=AsyncMock):
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
        mock_resolve_last.return_value = datetime(2025, 1, 1, 8, 0, 0)
        mock_should_run.return_value = True
        mock_execute.return_value = True

        await check_and_execute_schedules()

    mock_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_and_execute_schedules_replay_dispatch_uses_now_trigger_and_persists_cursor():
    now_dt = datetime(2025, 1, 1, 12, 0, 0)
    last_dt = datetime(2025, 1, 1, 9, 0, 0)
    sim_clock = Mock()
    sim_clock.now.return_value = now_dt

    with patch("main.get_active_schedules", new_callable=AsyncMock) as mock_schedules, \
         patch("main.get_simulation_clocks", new_callable=AsyncMock) as mock_sim_clocks, \
         patch("main.reconcile_active_tasks", new_callable=AsyncMock), \
         patch("main.process_internal_enqueued_tasks", new_callable=AsyncMock), \
         patch("main._resolve_zone_last_check", new_callable=AsyncMock) as mock_resolve_last, \
         patch("main.execute_scheduled_task", new_callable=AsyncMock) as mock_execute, \
         patch("main._persist_zone_cursor", new_callable=AsyncMock) as mock_persist_cursor, \
         patch("main.SCHEDULER_CATCHUP_POLICY", "replay_all"), \
         patch("main.SCHEDULER_CATCHUP_JITTER_SEC", 0):
        mock_schedules.return_value = [
            {
                "zone_id": 28,
                "type": "diagnostics",
                "time": time(10, 0),
                "targets": {},
                "config": {},
            }
        ]
        mock_sim_clocks.return_value = {28: sim_clock}
        mock_resolve_last.return_value = last_dt
        mock_execute.return_value = True

        await check_and_execute_schedules()

    mock_execute.assert_awaited_once()
    execute_kwargs = mock_execute.await_args.kwargs
    assert execute_kwargs["trigger_time"] == now_dt
    assert execute_kwargs["schedule"]["payload"]["catchup_original_trigger_time"] == datetime(
        2025, 1, 1, 10, 0, 0
    ).isoformat()
    assert execute_kwargs["schedule"]["payload"]["catchup_policy"] == "replay_all"
    mock_persist_cursor.assert_awaited_once_with(28, now_dt)


@pytest.mark.asyncio
async def test_check_and_execute_schedules_keeps_cursor_when_time_dispatch_not_successful():
    now_dt = datetime(2025, 1, 1, 12, 0, 0)
    last_dt = datetime(2025, 1, 1, 9, 0, 0)
    sim_clock = Mock()
    sim_clock.now.return_value = now_dt

    with patch("main.get_active_schedules", new_callable=AsyncMock) as mock_schedules, \
         patch("main.get_simulation_clocks", new_callable=AsyncMock) as mock_sim_clocks, \
         patch("main.reconcile_active_tasks", new_callable=AsyncMock), \
         patch("main.process_internal_enqueued_tasks", new_callable=AsyncMock), \
         patch("main._resolve_zone_last_check", new_callable=AsyncMock) as mock_resolve_last, \
         patch("main.execute_scheduled_task", new_callable=AsyncMock) as mock_execute, \
         patch("main._persist_zone_cursor", new_callable=AsyncMock) as mock_persist_cursor, \
         patch("main._emit_scheduler_diagnostic", new_callable=AsyncMock):
        mock_schedules.return_value = [
            {
                "zone_id": 28,
                "type": "diagnostics",
                "time": time(10, 0),
                "targets": {},
                "config": {},
            }
        ]
        mock_sim_clocks.return_value = {28: sim_clock}
        mock_resolve_last.return_value = last_dt
        mock_execute.return_value = False

        await check_and_execute_schedules()

    mock_execute.assert_awaited_once()
    mock_persist_cursor.assert_awaited_once_with(28, last_dt)
    assert scheduler_main._LAST_SCHEDULE_CHECKS[28] == last_dt


@pytest.mark.asyncio
async def test_check_and_execute_schedules_advances_cursor_when_zone_has_partial_time_success():
    now_dt = datetime(2025, 1, 1, 12, 0, 0)
    last_dt = datetime(2025, 1, 1, 9, 0, 0)
    sim_clock = Mock()
    sim_clock.now.return_value = now_dt

    with patch("main.get_active_schedules", new_callable=AsyncMock) as mock_schedules, \
         patch("main.get_simulation_clocks", new_callable=AsyncMock) as mock_sim_clocks, \
         patch("main.reconcile_active_tasks", new_callable=AsyncMock), \
         patch("main.process_internal_enqueued_tasks", new_callable=AsyncMock), \
         patch("main._resolve_zone_last_check", new_callable=AsyncMock) as mock_resolve_last, \
         patch("main.execute_scheduled_task", new_callable=AsyncMock) as mock_execute, \
         patch("main._persist_zone_cursor", new_callable=AsyncMock) as mock_persist_cursor, \
         patch("main._emit_scheduler_diagnostic", new_callable=AsyncMock):
        mock_schedules.return_value = [
            {
                "zone_id": 28,
                "type": "diagnostics",
                "time": time(10, 0),
                "targets": {},
                "config": {},
            },
            {
                "zone_id": 28,
                "type": "mist",
                "time": time(11, 0),
                "targets": {},
                "config": {},
            },
        ]
        mock_sim_clocks.return_value = {28: sim_clock}
        mock_resolve_last.return_value = last_dt
        mock_execute.side_effect = [True, False]

        await check_and_execute_schedules()

    assert mock_execute.await_count == 2
    mock_persist_cursor.assert_awaited_once_with(28, now_dt)
    assert scheduler_main._LAST_SCHEDULE_CHECKS[28] == now_dt


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
         patch("main.process_internal_enqueued_tasks", new_callable=AsyncMock), \
         patch("main._resolve_zone_last_check", new_callable=AsyncMock) as mock_resolve_last, \
         patch("main.execute_scheduled_task", new_callable=AsyncMock) as mock_execute, \
         patch("main._persist_zone_cursor", new_callable=AsyncMock), \
         patch("main.datetime") as mock_datetime:
        mock_schedules.return_value = [schedule]
        mock_sim_clocks.return_value = {}
        mock_resolve_last.return_value = datetime(2025, 1, 1, 8, 0, 0)
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
async def test_execute_scheduled_task_uses_stable_correlation_anchor_for_catchup_retries():
    original_trigger_iso = datetime(2025, 1, 1, 10, 0, 0).isoformat()
    schedule_key = "zone:28|type:diagnostics|time=10:00"
    schedule = {
        "type": "diagnostics",
        "targets": {},
        "config": {},
        "payload": {
            "catchup_original_trigger_time": original_trigger_iso,
        },
    }

    with patch("main.submit_task_to_automation_engine", new_callable=AsyncMock) as mock_submit, \
         patch("main.create_scheduler_log", new_callable=AsyncMock), \
         patch("main.create_zone_event", new_callable=AsyncMock):
        mock_submit.return_value = None

        await execute_scheduled_task(
            zone_id=28,
            schedule=dict(schedule),
            trigger_time=datetime(2025, 1, 1, 12, 0, 0),
            schedule_key=schedule_key,
        )
        await execute_scheduled_task(
            zone_id=28,
            schedule=dict(schedule),
            trigger_time=datetime(2025, 1, 1, 12, 5, 0),
            schedule_key=schedule_key,
        )

    assert mock_submit.await_count == 2
    correlation_ids = [call.kwargs["correlation_id"] for call in mock_submit.await_args_list]
    assert correlation_ids[0] == correlation_ids[1]
    assert correlation_ids[0] == scheduler_main._build_scheduler_correlation_id(
        zone_id=28,
        task_type="diagnostics",
        scheduled_for=original_trigger_iso,
        schedule_key=schedule_key,
    )


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


@pytest.mark.asyncio
async def test_process_internal_enqueued_tasks_invalid_zone_emits_diagnostic():
    now_dt = datetime(2025, 1, 1, 8, 0, 0)
    pending_entry = {
        "enqueue_id": "enq-invalid-zone",
        "zone_id": "oops",
        "task_type": "diagnostics",
        "payload": {},
    }

    with patch("main._load_pending_internal_enqueues", new_callable=AsyncMock) as mock_load, \
         patch("main._mark_internal_enqueue_status", new_callable=AsyncMock) as mock_mark, \
         patch("main._emit_scheduler_diagnostic", new_callable=AsyncMock) as mock_diag:
        mock_load.return_value = [pending_entry]
        await process_internal_enqueued_tasks(now_dt)

    mock_mark.assert_awaited_once()
    assert mock_mark.await_args.args[0] == "ae_internal_enqueue_enq-invalid-zone"
    assert mock_mark.await_args.args[1] == "failed"
    assert mock_diag.await_count == 1
    assert mock_diag.await_args.kwargs["reason"] == "internal_enqueue_invalid_zone"


@pytest.mark.asyncio
async def test_process_internal_enqueued_tasks_dispatch_failed_emits_diagnostic():
    now_dt = datetime(2025, 1, 1, 8, 0, 0)
    pending_entry = {
        "enqueue_id": "enq-dispatch-failed",
        "zone_id": 28,
        "task_type": "diagnostics",
        "payload": {},
        "scheduled_for": (now_dt - timedelta(seconds=5)).isoformat(),
    }

    with patch("main._load_pending_internal_enqueues", new_callable=AsyncMock) as mock_load, \
         patch("main.execute_scheduled_task", new_callable=AsyncMock) as mock_execute, \
         patch("main._mark_internal_enqueue_status", new_callable=AsyncMock) as mock_mark, \
         patch("main.create_zone_event", new_callable=AsyncMock), \
         patch("main._emit_scheduler_diagnostic", new_callable=AsyncMock) as mock_diag:
        mock_load.return_value = [pending_entry]
        mock_execute.return_value = False
        await process_internal_enqueued_tasks(now_dt)

    mock_mark.assert_awaited_once()
    assert mock_mark.await_args.args[0] == "ae_internal_enqueue_enq-dispatch-failed"
    assert mock_mark.await_args.args[1] == "failed"
    assert mock_diag.await_count == 1
    assert mock_diag.await_args.kwargs["reason"] == "internal_enqueue_dispatch_failed"


@pytest.mark.asyncio
async def test_recover_active_tasks_after_restart_restores_latest_accepted():
    rows = [
        {
            "status": "accepted",
            "created_at": datetime(2025, 1, 1, 8, 0, 10),
            "details": {
                "task_id": "st-recover-1",
                "zone_id": 28,
                "task_type": "diagnostics",
                "schedule_key": "zone:28|type:diagnostics|interval=1800",
                "correlation_id": "sch:z28:diagnostics:recover",
                "accepted_at": "2025-01-01T08:00:00",
            },
        },
        {
            "status": "completed",
            "created_at": datetime(2025, 1, 1, 8, 0, 15),
            "details": {
                "task_id": "st-terminal-1",
                "zone_id": 28,
                "task_type": "irrigation",
            },
        },
    ]

    with patch("main.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("main.send_service_log"):
        mock_fetch.return_value = rows
        recovered = await recover_active_tasks_after_restart()

    assert recovered == 1
    assert "st-recover-1" in _ACTIVE_TASKS
    assert "st-terminal-1" not in _ACTIVE_TASKS
    assert _ACTIVE_TASKS["st-recover-1"]["recovered_after_restart"] is True
    assert _ACTIVE_SCHEDULE_TASKS["zone:28|type:diagnostics|interval=1800"] == "st-recover-1"


@pytest.mark.asyncio
async def test_recover_active_tasks_after_restart_fetch_error_emits_diagnostic():
    with patch("main.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("main._emit_scheduler_diagnostic", new_callable=AsyncMock) as mock_diag:
        mock_fetch.side_effect = RuntimeError("db down")
        recovered = await recover_active_tasks_after_restart()

    assert recovered == 0
    mock_diag.assert_awaited_once()
    assert mock_diag.await_args.kwargs["reason"] == "active_task_recovery_failed"
