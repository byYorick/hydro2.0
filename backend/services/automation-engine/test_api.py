"""Tests for automation-engine REST API."""
import asyncio
import pytest
import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

# Добавляем путь к модулю для импорта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api
from api import app, set_command_bus
from infrastructure.command_bus import CommandBus


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_command_bus():
    """Create mock command bus."""
    return Mock(spec=CommandBus)


@pytest.fixture(autouse=True)
def mock_api_fetch():
    """Mock DB lookups used by scheduler task API."""
    async def _mock_fetch(query, *args):
        normalized = " ".join(str(query).split()).lower()

        if "from zones" in normalized and "where id = $1" in normalized:
            zone_id = int(args[0])
            if zone_id in {1, 11, 12}:
                return [{"id": zone_id}]
            return []

        if "from scheduler_logs" in normalized and "where task_name = $1" in normalized:
            task_name = str(args[0])
            if task_name == "ae_scheduler_task_st-persisted":
                return [{
                    "status": "completed",
                    "details": {
                        "task_id": "st-persisted",
                        "zone_id": 1,
                        "task_type": "diagnostics",
                        "status": "completed",
                        "created_at": "2026-02-10T00:00:00",
                        "updated_at": "2026-02-10T00:00:05",
                        "result": {"success": True},
                    },
                    "created_at": datetime(2026, 2, 10, 0, 0, 5),
                }]
            return []

        return []

    with patch("api.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("api.create_zone_event", new_callable=AsyncMock), \
         patch("api.create_scheduler_log", new_callable=AsyncMock):
        mock_fetch.side_effect = _mock_fetch
        yield mock_fetch


@pytest.fixture(autouse=True)
def reset_scheduler_task_state():
    api._scheduler_tasks.clear()
    yield
    api._scheduler_tasks.clear()


@pytest.fixture(autouse=True)
def reset_bootstrap_state():
    old_enforce = api._SCHEDULER_BOOTSTRAP_ENFORCE
    api._SCHEDULER_BOOTSTRAP_ENFORCE = True
    api._scheduler_bootstrap_leases.clear()
    yield
    api._scheduler_bootstrap_leases.clear()
    api._SCHEDULER_BOOTSTRAP_ENFORCE = old_enforce


def bootstrap_headers(client: TestClient, scheduler_id: str = "scheduler-test") -> dict:
    response = client.post("/scheduler/bootstrap", json={
        "scheduler_id": scheduler_id,
        "scheduler_version": "test",
        "protocol_version": "2.0",
    })
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["bootstrap_status"] == "ready"
    lease_id = data["lease_id"]
    return {
        "X-Scheduler-Id": scheduler_id,
        "X-Scheduler-Lease-Id": lease_id,
    }


def scheduler_task_payload(**overrides) -> dict:
    base_scheduled_for = (datetime.utcnow() + timedelta(minutes=5)).replace(microsecond=0)
    base_due_at = base_scheduled_for + timedelta(seconds=15)
    base_expires_at = base_scheduled_for + timedelta(minutes=2)

    payload = {
        "zone_id": 1,
        "task_type": "diagnostics",
        "payload": {"reason": "scheduled_check"},
        "scheduled_for": base_scheduled_for.isoformat(),
        "due_at": base_due_at.isoformat(),
        "expires_at": base_expires_at.isoformat(),
        "correlation_id": "sch:z1:diagnostics:test",
    }
    payload.update(overrides)
    return payload


def test_health_legacy_endpoint_removed(client):
    """Legacy /health alias must not be exposed."""
    response = client.get("/health")
    assert response.status_code == 404


def test_health_live_endpoint(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "automation-engine"


def test_health_ready_endpoint_when_ready(client, mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        set_command_bus(mock_command_bus, "gh-1")
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["checks"]["command_bus"]["ok"] is True
        assert data["checks"]["db"]["ok"] is True
        assert data["checks"]["bootstrap_store"]["ok"] is True
    finally:
        set_command_bus(old_command_bus, old_gh_uid)


def test_health_ready_endpoint_when_command_bus_not_ready(client):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        set_command_bus(None, "")
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False
        assert data["checks"]["command_bus"]["ok"] is False
        assert data["checks"]["command_bus"]["reason"] == "command_bus_unavailable"
    finally:
        set_command_bus(old_command_bus, old_gh_uid)


def test_health_ready_endpoint_when_db_probe_fails(client, mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        set_command_bus(mock_command_bus, "gh-1")
        with patch("api.fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = RuntimeError("db down")
            response = client.get("/health/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["ready"] is False
        assert data["checks"]["db"]["ok"] is False
        assert data["checks"]["db"]["reason"] == "RuntimeError"
    finally:
        set_command_bus(old_command_bus, old_gh_uid)


def test_scheduler_command_endpoint_removed(client):
    """Legacy device-level endpoint must not be exposed anymore."""
    response = client.post("/scheduler/command", json={"zone_id": 1})
    assert response.status_code == 404


def test_scheduler_bootstrap_wait_when_command_bus_not_ready(client):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        set_command_bus(None, "")
        response = client.post("/scheduler/bootstrap", json={
            "scheduler_id": "scheduler-test",
            "scheduler_version": "test",
            "protocol_version": "2.0",
        })
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["bootstrap_status"] == "wait"
    finally:
        set_command_bus(old_command_bus, old_gh_uid)


def test_scheduler_bootstrap_wait_when_db_not_ready(client, mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        set_command_bus(mock_command_bus, "gh-1")
        with patch("api.fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = RuntimeError("db unavailable")
            response = client.post("/scheduler/bootstrap", json={
                "scheduler_id": "scheduler-db-wait",
                "scheduler_version": "test",
                "protocol_version": "2.0",
            })

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["bootstrap_status"] == "wait"
        assert data["reason"] == "automation_not_ready"
        assert data["readiness_reason"] == "RuntimeError"
        assert "lease_id" not in data
        assert "scheduler-db-wait" not in api._scheduler_bootstrap_leases
    finally:
        set_command_bus(old_command_bus, old_gh_uid)


def test_scheduler_bootstrap_and_heartbeat_success(client, mock_command_bus):
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")

    bootstrap_response = client.post("/scheduler/bootstrap", json={
        "scheduler_id": "scheduler-test",
        "scheduler_version": "test",
        "protocol_version": "2.0",
    })
    assert bootstrap_response.status_code == 200
    bootstrap_data = bootstrap_response.json()["data"]
    assert bootstrap_data["bootstrap_status"] == "ready"
    lease_id = bootstrap_data["lease_id"]

    heartbeat_response = client.post("/scheduler/bootstrap/heartbeat", json={
        "scheduler_id": "scheduler-test",
        "lease_id": lease_id,
    })
    assert heartbeat_response.status_code == 200
    heartbeat_data = heartbeat_response.json()["data"]
    assert heartbeat_data["bootstrap_status"] == "ready"
    assert heartbeat_data["lease_id"] == lease_id


def test_scheduler_bootstrap_heartbeat_wait_when_automation_not_ready(client, mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        mock_command_bus.publish_command = AsyncMock(return_value=True)
        set_command_bus(mock_command_bus, "gh-1")
        scheduler_id = "scheduler-heartbeat-wait"

        headers = bootstrap_headers(client, scheduler_id=scheduler_id)
        lease_id = headers["X-Scheduler-Lease-Id"]

        set_command_bus(None, "")
        heartbeat_response = client.post("/scheduler/bootstrap/heartbeat", json={
            "scheduler_id": scheduler_id,
            "lease_id": lease_id,
        })

        assert heartbeat_response.status_code == 200
        heartbeat_data = heartbeat_response.json()["data"]
        assert heartbeat_data["bootstrap_status"] == "wait"
        assert heartbeat_data["reason"] == "automation_not_ready"
        assert scheduler_id not in api._scheduler_bootstrap_leases
    finally:
        set_command_bus(old_command_bus, old_gh_uid)


def test_scheduler_bootstrap_heartbeat_wait_when_db_not_ready(client, mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        mock_command_bus.publish_command = AsyncMock(return_value=True)
        set_command_bus(mock_command_bus, "gh-1")
        scheduler_id = "scheduler-heartbeat-db-wait"

        headers = bootstrap_headers(client, scheduler_id=scheduler_id)
        lease_id = headers["X-Scheduler-Lease-Id"]

        with patch("api.fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = RuntimeError("db unavailable")
            heartbeat_response = client.post("/scheduler/bootstrap/heartbeat", json={
                "scheduler_id": scheduler_id,
                "lease_id": lease_id,
            })

        assert heartbeat_response.status_code == 200
        heartbeat_data = heartbeat_response.json()["data"]
        assert heartbeat_data["bootstrap_status"] == "wait"
        assert heartbeat_data["reason"] == "automation_not_ready"
        assert heartbeat_data["readiness_reason"] == "RuntimeError"
        assert scheduler_id not in api._scheduler_bootstrap_leases
    finally:
        set_command_bus(old_command_bus, old_gh_uid)


def test_scheduler_internal_enqueue_creates_pending_entry(client):
    tz_msk = timezone(timedelta(hours=3))
    scheduled_for = (datetime.now(tz_msk) + timedelta(minutes=5)).replace(microsecond=0)
    expires_at = scheduled_for + timedelta(hours=2)

    with patch("scheduler_internal_enqueue.create_scheduler_log", new_callable=AsyncMock) as mock_scheduler_log, \
         patch("scheduler_internal_enqueue.create_zone_event", new_callable=AsyncMock) as mock_zone_event:
        response = client.post("/scheduler/internal/enqueue", json={
            "zone_id": 1,
            "task_type": "irrigation",
            "payload": {"config": {"duration_sec": 20}},
            "scheduled_for": scheduled_for.isoformat(),
            "expires_at": expires_at.isoformat(),
            "source": "automation-engine",
        })

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "pending"
    assert data["zone_id"] == 1
    assert data["task_type"] == "irrigation"
    assert data["scheduled_for"] == scheduled_for.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
    assert data["expires_at"] == expires_at.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
    assert data["correlation_id"].startswith("ae:self:1:irrigation:enq-")
    mock_scheduler_log.assert_awaited_once()
    assert mock_scheduler_log.await_args.args[1] == "pending"
    assert mock_zone_event.await_args.args[1] == "SELF_TASK_ENQUEUED"


@pytest.mark.asyncio
async def test_scheduler_task_success(client, mock_command_bus):
    """Task endpoint should return accepted and expose status."""
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")
    headers = bootstrap_headers(client)

    payload = scheduler_task_payload(correlation_id="sch:z1:diagnostics:success")

    response = client.post("/scheduler/task", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] in {"accepted", "running", "completed"}
    assert data["zone_id"] == 1
    assert data["task_type"] == "diagnostics"
    task_id = data["task_id"]

    status_response = client.get(f"/scheduler/task/{task_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()["data"]
    assert status_data["task_id"] == task_id
    assert status_data["task_type"] == "diagnostics"
    assert status_data["due_at"] == payload["due_at"]
    assert status_data["expires_at"] == payload["expires_at"]


def test_scheduler_task_lifecycle_persists_snapshots(client, mock_command_bus):
    """Task endpoint должен пройти lifecycle accepted->running->completed и записать snapshots."""
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")
    headers = bootstrap_headers(client)

    async def _execute(**kwargs):
        await asyncio.sleep(0.01)
        return {"success": True, "commands_sent": 1, "task_type": kwargs.get("task_type")}

    def _cancel_background_task(coro):
        coro.close()
        return Mock()

    with patch("api.SchedulerTaskExecutor") as mock_executor_cls, \
         patch("api.create_scheduler_log", new_callable=AsyncMock) as mock_scheduler_log, \
         patch("api.create_zone_event", new_callable=AsyncMock), \
         patch("api.asyncio.create_task", side_effect=_cancel_background_task) as mock_create_task:
        mock_executor = mock_executor_cls.return_value
        mock_executor.execute = AsyncMock(side_effect=_execute)
        payload = scheduler_task_payload(correlation_id="sch:z1:diagnostics:lifecycle")

        response = client.post(
            "/scheduler/task",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 200
        task_id = response.json()["data"]["task_id"]
        mock_create_task.assert_called_once()

        asyncio.run(
            api._execute_scheduler_task(
                task_id=task_id,
                req=api.SchedulerTaskRequest(**payload),
                trace_id=None,
            )
        )

        status_response = client.get(f"/scheduler/task/{task_id}")
        assert status_response.status_code == 200
        terminal_status = status_response.json()["data"]["status"]
        assert terminal_status == "completed"
        snapshots = [call.args[1] for call in mock_scheduler_log.await_args_list]
        assert "accepted" in snapshots
        assert "running" in snapshots
        assert "completed" in snapshots
        execute_kwargs = mock_executor.execute.await_args.kwargs
        assert execute_kwargs["task_context"]["task_id"] == task_id
        assert execute_kwargs["task_context"]["correlation_id"] == "sch:z1:diagnostics:lifecycle"


def test_scheduler_task_validation_error(client, mock_command_bus):
    """Task endpoint must validate task_type."""
    set_command_bus(mock_command_bus, "gh-1")
    payload = scheduler_task_payload(
        task_type="unknown_task",
        correlation_id="sch:z1:unknown:validation",
    )
    response = client.post("/scheduler/task", json=payload, headers=bootstrap_headers(client))
    assert response.status_code == 422


def test_scheduler_task_zone_not_found(client, mock_command_bus):
    """Task endpoint must reject unknown zone."""
    set_command_bus(mock_command_bus, "gh-1")
    payload = scheduler_task_payload(
        zone_id=999,
        correlation_id="sch:z999:diagnostics:notfound",
    )
    response = client.post("/scheduler/task", json=payload, headers=bootstrap_headers(client))
    assert response.status_code == 404


def test_scheduler_task_requires_bootstrap_headers(client, mock_command_bus):
    set_command_bus(mock_command_bus, "gh-1")
    payload = scheduler_task_payload(correlation_id="sch:z1:diagnostics:no-lease")
    response = client.post("/scheduler/task", json=payload)
    assert response.status_code == 403
    assert "scheduler_bootstrap_required" in response.json()["detail"]


def test_scheduler_task_rejects_lease_mismatch(client, mock_command_bus):
    set_command_bus(mock_command_bus, "gh-1")
    headers = bootstrap_headers(client, scheduler_id="scheduler-lease-mismatch")
    headers["X-Scheduler-Lease-Id"] = "lease-invalid"

    payload = scheduler_task_payload(correlation_id="sch:z1:diagnostics:lease-mismatch")
    response = client.post("/scheduler/task", json=payload, headers=headers)

    assert response.status_code == 409
    assert "scheduler_lease_mismatch" in response.json()["detail"]


def test_scheduler_task_rejects_expired_lease(client, mock_command_bus):
    set_command_bus(mock_command_bus, "gh-1")
    scheduler_id = "scheduler-lease-expired"
    headers = bootstrap_headers(client, scheduler_id=scheduler_id)

    api._scheduler_bootstrap_leases[scheduler_id]["expires_at"] = datetime.utcnow() - timedelta(seconds=1)

    payload = scheduler_task_payload(correlation_id="sch:z1:diagnostics:lease-expired")
    response = client.post("/scheduler/task", json=payload, headers=headers)

    assert response.status_code == 409
    assert "scheduler_lease_not_found" in response.json()["detail"]
    assert scheduler_id not in api._scheduler_bootstrap_leases


def test_scheduler_task_requires_due_at_and_expires_at(client, mock_command_bus):
    set_command_bus(mock_command_bus, "gh-1")
    headers = bootstrap_headers(client)

    payload_missing_due = scheduler_task_payload(correlation_id="sch:z1:diagnostics:missing-due")
    payload_missing_due.pop("due_at")
    due_response = client.post("/scheduler/task", json=payload_missing_due, headers=headers)
    assert due_response.status_code == 422
    assert "due_at" in str(due_response.json().get("detail", ""))

    payload_missing_expires = scheduler_task_payload(correlation_id="sch:z1:diagnostics:missing-exp")
    payload_missing_expires.pop("expires_at")
    expires_response = client.post("/scheduler/task", json=payload_missing_expires, headers=headers)
    assert expires_response.status_code == 422
    assert "expires_at" in str(expires_response.json().get("detail", ""))


def test_scheduler_task_deadline_fast_fail_rejected(client, mock_command_bus):
    set_command_bus(mock_command_bus, "gh-1")
    headers = bootstrap_headers(client)
    now = datetime.utcnow().replace(microsecond=0)

    payload = scheduler_task_payload(
        correlation_id="sch:z1:diagnostics:late-due",
        scheduled_for=(now - timedelta(seconds=20)).isoformat(),
        due_at=(now - timedelta(seconds=5)).isoformat(),
        expires_at=(now + timedelta(seconds=30)).isoformat(),
    )
    response = client.post("/scheduler/task", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "rejected"
    assert data["is_duplicate"] is False

    status_response = client.get(f"/scheduler/task/{data['task_id']}")
    assert status_response.status_code == 200
    status_data = status_response.json()["data"]
    assert status_data["status"] == "rejected"
    assert status_data["error_code"] == "task_due_deadline_exceeded"


def test_scheduler_task_deadline_fast_fail_expired(client, mock_command_bus):
    set_command_bus(mock_command_bus, "gh-1")
    headers = bootstrap_headers(client)
    now = datetime.utcnow().replace(microsecond=0)

    payload = scheduler_task_payload(
        correlation_id="sch:z1:diagnostics:expired",
        scheduled_for=(now - timedelta(seconds=50)).isoformat(),
        due_at=(now - timedelta(seconds=30)).isoformat(),
        expires_at=(now - timedelta(seconds=5)).isoformat(),
    )
    response = client.post("/scheduler/task", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "expired"
    assert data["is_duplicate"] is False

    status_response = client.get(f"/scheduler/task/{data['task_id']}")
    assert status_response.status_code == 200
    status_data = status_response.json()["data"]
    assert status_data["status"] == "expired"
    assert status_data["error_code"] == "task_expired"


@pytest.mark.asyncio
async def test_execute_scheduler_task_command_bus_unavailable_sets_structured_failure(mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        set_command_bus(mock_command_bus, "gh-1")
        req = api.SchedulerTaskRequest(**scheduler_task_payload(correlation_id="sch:z1:diagnostics:bus-down"))
        task, _ = await api._create_scheduler_task(req)

        set_command_bus(None, "")
        await api._execute_scheduler_task(task["task_id"], req, None)

        stored = api._scheduler_tasks[task["task_id"]]
        assert stored["status"] == "failed"
        assert stored["error_code"] == "command_bus_unavailable"
        assert stored["result"]["reason_code"] == "command_bus_unavailable"
        assert stored["result"]["decision"] == "execute"
        assert stored["result"]["action_required"] is True
    finally:
        set_command_bus(old_command_bus, old_gh_uid)


@pytest.mark.asyncio
async def test_execute_scheduler_task_exception_sets_structured_failure(mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        set_command_bus(mock_command_bus, "gh-1")
        req = api.SchedulerTaskRequest(**scheduler_task_payload(correlation_id="sch:z1:diagnostics:executor-exc"))
        task, _ = await api._create_scheduler_task(req)

        with patch("api.SchedulerTaskExecutor.execute", new_callable=AsyncMock) as mock_execute, \
             patch("api.send_infra_exception_alert", new_callable=AsyncMock) as mock_alert:
            mock_execute.side_effect = RuntimeError("executor exploded")
            await api._execute_scheduler_task(task["task_id"], req, None)

        stored = api._scheduler_tasks[task["task_id"]]
        assert stored["status"] == "failed"
        assert stored["error_code"] == "execution_exception"
        assert stored["result"]["reason_code"] == "execution_exception"
        assert stored["result"]["decision"] == "execute"
        assert stored["result"]["action_required"] is True
        assert stored["result"]["exception_type"] == "RuntimeError"
        mock_alert.assert_awaited_once()
    finally:
        set_command_bus(old_command_bus, old_gh_uid)


@pytest.mark.asyncio
async def test_execute_scheduler_task_normalizes_failed_result_without_codes(mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        set_command_bus(mock_command_bus, "gh-1")
        req = api.SchedulerTaskRequest(**scheduler_task_payload(correlation_id="sch:z1:diagnostics:no-codes"))
        task, _ = await api._create_scheduler_task(req)

        with patch("api.SchedulerTaskExecutor.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "success": False,
                "mode": "custom_failed_mode",
            }
            await api._execute_scheduler_task(task["task_id"], req, None)

        stored = api._scheduler_tasks[task["task_id"]]
        assert stored["status"] == "failed"
        assert stored["error_code"] == "task_execution_failed"
        assert stored["result"]["reason_code"] == "task_execution_failed"
        assert stored["result"]["decision"] == "execute"
        assert stored["result"]["action_required"] is True
        assert stored["result"]["mode"] == "custom_failed_mode"
    finally:
        set_command_bus(old_command_bus, old_gh_uid)


@pytest.mark.asyncio
async def test_execute_scheduler_task_updates_command_effect_confirm_rate_metric(mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        api._command_effect_totals.clear()
        api._command_effect_confirmed_totals.clear()
        set_command_bus(mock_command_bus, "gh-1")
        req = api.SchedulerTaskRequest(**scheduler_task_payload(task_type="irrigation", correlation_id="sch:z1:irrigation:metric"))
        task, _ = await api._create_scheduler_task(req)

        with patch("api.SchedulerTaskExecutor.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {
                "success": False,
                "commands_total": 2,
                "commands_effect_confirmed": 1,
                "command_effect_confirmed": False,
                "error_code": "command_no_effect",
            }
            await api._execute_scheduler_task(task["task_id"], req, None)

        assert api._command_effect_totals["irrigation"] == 2
        assert api._command_effect_confirmed_totals["irrigation"] == 1
    finally:
        set_command_bus(old_command_bus, old_gh_uid)


def test_scheduler_task_idempotent_duplicate_returns_same_task(client, mock_command_bus):
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")
    headers = bootstrap_headers(client)
    payload = scheduler_task_payload(correlation_id="sch:z1:diagnostics:duplicate")

    first = client.post("/scheduler/task", json=payload, headers=headers)
    assert first.status_code == 200
    first_data = first.json()["data"]
    assert first_data["is_duplicate"] is False

    second = client.post("/scheduler/task", json=payload, headers=headers)
    assert second.status_code == 200
    second_data = second.json()["data"]
    assert second_data["is_duplicate"] is True
    assert second_data["task_id"] == first_data["task_id"]


def test_scheduler_task_idempotency_payload_mismatch_returns_409(client, mock_command_bus):
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")
    headers = bootstrap_headers(client)
    correlation_id = "sch:z1:diagnostics:mismatch"

    first = client.post(
        "/scheduler/task",
        json=scheduler_task_payload(
            payload={"reason": "first"},
            correlation_id=correlation_id,
        ),
        headers=headers,
    )
    assert first.status_code == 200

    second = client.post(
        "/scheduler/task",
        json=scheduler_task_payload(
            payload={"reason": "second"},
            correlation_id=correlation_id,
        ),
        headers=headers,
    )
    assert second.status_code == 409
    assert "idempotency_payload_mismatch" in second.json()["detail"]


def test_scheduler_task_status_not_found(client):
    """Status endpoint must return 404 for unknown task."""
    response = client.get("/scheduler/task/st-unknown")
    assert response.status_code == 404


def test_scheduler_task_status_reads_persisted_snapshot(client):
    """Status endpoint should load snapshot from scheduler_logs when task is not in memory."""
    response = client.get("/scheduler/task/st-persisted")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["task_id"] == "st-persisted"
    assert data["status"] == "completed"
    assert data["task_type"] == "diagnostics"


@pytest.mark.asyncio
async def test_cleanup_scheduler_tasks_locked_handles_timezone_aware_updated_at():
    api._scheduler_tasks.clear()
    api._scheduler_tasks["st-aware-stale"] = {
        "task_id": "st-aware-stale",
        "updated_at": "2026-02-10T00:00:00+00:00",
    }

    with patch("api._SCHEDULER_TASK_TTL_SECONDS", 60):
        await api._cleanup_scheduler_tasks_locked(datetime(2026, 2, 10, 0, 2, 0))

    assert "st-aware-stale" not in api._scheduler_tasks


@pytest.mark.asyncio
async def test_load_scheduler_task_by_correlation_id_uses_deterministic_order():
    with patch("api.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        result = await api._load_scheduler_task_by_correlation_id("sch:z1:diagnostics:det-order")

    assert result is None
    query = " ".join(str(mock_fetch.await_args.args[0]).split()).lower()
    assert "order by created_at desc, id desc" in query


@pytest.mark.asyncio
async def test_load_scheduler_task_snapshot_uses_deterministic_order():
    with patch("api.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        result = await api._load_scheduler_task_snapshot("st-order-check")

    assert result is None
    query = " ".join(str(mock_fetch.await_args.args[0]).split()).lower()
    assert "order by created_at desc, id desc" in query


@pytest.mark.asyncio
async def test_recover_inflight_scheduler_tasks_marks_running_as_failed():
    old_enabled = api._AE_TASK_RECOVERY_ENABLED
    api._AE_TASK_RECOVERY_ENABLED = True
    try:
        with patch("api.fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("api.create_scheduler_log", new_callable=AsyncMock) as mock_scheduler_log, \
             patch("api.create_zone_event", new_callable=AsyncMock) as mock_zone_event:
            mock_fetch.return_value = [
                {
                    "task_name": "ae_scheduler_task_st-recover-1",
                    "status": "running",
                    "details": {
                        "task_id": "st-recover-1",
                        "zone_id": 1,
                        "task_type": "diagnostics",
                        "status": "running",
                        "created_at": "2026-02-10T10:00:00",
                        "updated_at": "2026-02-10T10:00:03",
                        "correlation_id": "sch:z1:diagnostics:recover-1",
                    },
                    "created_at": datetime(2026, 2, 10, 10, 0, 3),
                }
            ]

            summary = await api._recover_inflight_scheduler_tasks()

        assert summary["scanned"] == 1
        assert summary["inflight"] == 1
        assert summary["recovered"] == 1
        assert "st-recover-1" in api._scheduler_tasks
        recovered_task = api._scheduler_tasks["st-recover-1"]
        assert recovered_task["status"] == "failed"
        assert recovered_task["error_code"] == "task_recovered_after_restart"
        assert recovered_task["result"]["reason_code"] == "task_recovered_after_restart"
        mock_scheduler_log.assert_awaited_once()
        mock_zone_event.assert_awaited_once()
    finally:
        api._AE_TASK_RECOVERY_ENABLED = old_enabled


@pytest.mark.asyncio
async def test_recover_inflight_scheduler_tasks_updates_recovery_success_rate_metric():
    old_enabled = api._AE_TASK_RECOVERY_ENABLED
    api._AE_TASK_RECOVERY_ENABLED = True
    try:
        with patch("api.fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("api.create_scheduler_log", new_callable=AsyncMock), \
             patch("api.create_zone_event", new_callable=AsyncMock):
            mock_fetch.return_value = [
                {
                    "task_name": "ae_scheduler_task_st-recover-metric-1",
                    "status": "running",
                    "details": {
                        "task_id": "st-recover-metric-1",
                        "zone_id": 1,
                        "task_type": "diagnostics",
                        "status": "running",
                    },
                    "created_at": datetime(2026, 2, 10, 10, 0, 3),
                },
                {
                    "task_name": "ae_scheduler_task_st-recover-metric-2",
                    "status": "completed",
                    "details": {
                        "task_id": "st-recover-metric-2",
                        "zone_id": 1,
                        "task_type": "diagnostics",
                        "status": "completed",
                    },
                    "created_at": datetime(2026, 2, 10, 10, 0, 4),
                },
            ]

            summary = await api._recover_inflight_scheduler_tasks()

        assert summary["scanned"] == 2
        assert summary["inflight"] == 1
        assert summary["recovered"] == 1
        assert api.TASK_RECOVERY_SUCCESS_RATE._value.get() == pytest.approx(1.0)
    finally:
        api._AE_TASK_RECOVERY_ENABLED = old_enabled


@pytest.mark.asyncio
async def test_recover_inflight_scheduler_tasks_skips_terminal_snapshots():
    old_enabled = api._AE_TASK_RECOVERY_ENABLED
    api._AE_TASK_RECOVERY_ENABLED = True
    try:
        with patch("api.fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("api.create_scheduler_log", new_callable=AsyncMock) as mock_scheduler_log, \
             patch("api.create_zone_event", new_callable=AsyncMock) as mock_zone_event:
            mock_fetch.return_value = [
                {
                    "task_name": "ae_scheduler_task_st-done-1",
                    "status": "completed",
                    "details": {
                        "task_id": "st-done-1",
                        "zone_id": 1,
                        "task_type": "diagnostics",
                        "status": "completed",
                    },
                    "created_at": datetime(2026, 2, 10, 10, 0, 3),
                }
            ]

            summary = await api._recover_inflight_scheduler_tasks()

        assert summary["scanned"] == 1
        assert summary["inflight"] == 0
        assert summary["recovered"] == 0
        assert "st-done-1" not in api._scheduler_tasks
        mock_scheduler_log.assert_not_awaited()
        mock_zone_event.assert_not_awaited()
    finally:
        api._AE_TASK_RECOVERY_ENABLED = old_enabled


@pytest.mark.asyncio
async def test_recover_inflight_scheduler_tasks_continues_when_zone_event_publish_fails():
    old_enabled = api._AE_TASK_RECOVERY_ENABLED
    api._AE_TASK_RECOVERY_ENABLED = True
    try:
        with patch("api.fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("api._persist_scheduler_task_snapshot", new_callable=AsyncMock), \
             patch("api.create_zone_event", new_callable=AsyncMock) as mock_zone_event, \
             patch("api.send_infra_exception_alert", new_callable=AsyncMock) as mock_alert:
            mock_fetch.return_value = [
                {
                    "task_name": "ae_scheduler_task_st-recover-zone-event-fail",
                    "status": "running",
                    "details": {
                        "task_id": "st-recover-zone-event-fail",
                        "zone_id": 1,
                        "task_type": "diagnostics",
                        "status": "running",
                    },
                    "created_at": datetime(2026, 2, 10, 10, 0, 3),
                }
            ]
            mock_zone_event.side_effect = RuntimeError("zone events unavailable")

            summary = await api._recover_inflight_scheduler_tasks()

        assert summary["scanned"] == 1
        assert summary["inflight"] == 1
        assert summary["recovered"] == 1
        assert "st-recover-zone-event-fail" in api._scheduler_tasks
        mock_alert.assert_awaited_once()
        assert mock_alert.await_args.kwargs["code"] == "infra_scheduler_task_recovery_event_failed"
    finally:
        api._AE_TASK_RECOVERY_ENABLED = old_enabled


def test_scheduler_task_status_triggers_cleanup_and_memory_limit(client):
    """Status endpoint должен выполнять cleanup TTL и ограничение размера in-memory кэша."""
    old_ttl = api._SCHEDULER_TASK_TTL_SECONDS
    old_max = api._SCHEDULER_TASK_MAX_IN_MEMORY
    try:
        api._SCHEDULER_TASK_TTL_SECONDS = 1
        api._SCHEDULER_TASK_MAX_IN_MEMORY = 2
        api._scheduler_tasks.clear()
        api._scheduler_tasks.update({
            "st-old-1": {
                "task_id": "st-old-1",
                "zone_id": 1,
                "task_type": "diagnostics",
                "status": "running",
                "created_at": "2026-02-10T00:00:00",
                "updated_at": "2026-02-10T00:00:00",
            },
            "st-old-2": {
                "task_id": "st-old-2",
                "zone_id": 1,
                "task_type": "diagnostics",
                "status": "running",
                "created_at": "2026-02-10T00:00:00",
                "updated_at": "2026-02-10T00:00:01",
            },
            "st-new-1": {
                "task_id": "st-new-1",
                "zone_id": 1,
                "task_type": "diagnostics",
                "status": "running",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            },
        })

        response = client.get("/scheduler/task/st-unknown-cleanup")
        assert response.status_code == 404
        assert len(api._scheduler_tasks) <= 2
        assert "st-new-1" in api._scheduler_tasks
    finally:
        api._SCHEDULER_TASK_TTL_SECONDS = old_ttl
        api._SCHEDULER_TASK_MAX_IN_MEMORY = old_max


def test_test_hook_forbidden_when_test_mode_disabled(client):
    """Test hook should be unavailable when AE_TEST_MODE is disabled."""
    old_mode = api._test_mode
    try:
        api._test_mode = False
        response = client.post("/test/hook", json={
            "zone_id": 1,
            "action": "reset_backoff",
        })
        assert response.status_code == 403
    finally:
        api._test_mode = old_mode


def test_test_hook_reset_backoff_and_get_state(client):
    """Reset backoff should persist state override and be retrievable."""
    old_mode = api._test_mode
    old_hooks = dict(api._test_hooks)
    old_states = dict(api._zone_states_override)
    try:
        api._test_mode = True
        api._test_hooks.clear()
        api._zone_states_override.clear()

        reset_resp = client.post("/test/hook", json={
            "zone_id": 11,
            "action": "reset_backoff",
        })
        assert reset_resp.status_code == 200
        assert reset_resp.json()["status"] == "ok"

        state_resp = client.get("/test/hook/11")
        assert state_resp.status_code == 200
        payload = state_resp.json()["data"]["state_override"]
        assert payload["error_streak"] == 0
        assert payload["next_allowed_run_at"] is None
        assert payload["degraded_alert_active"] is False
        assert payload["last_backoff_reported_until"] is None
        assert payload["last_missing_targets_report_at"] is None
    finally:
        api._test_mode = old_mode
        api._test_hooks.clear()
        api._test_hooks.update(old_hooks)
        api._zone_states_override.clear()
        api._zone_states_override.update(old_states)


def test_test_hook_set_state_and_unknown_action_validation(client):
    """set_state should require state payload, unknown action should return 400."""
    old_mode = api._test_mode
    old_states = dict(api._zone_states_override)
    try:
        api._test_mode = True
        api._zone_states_override.clear()

        missing_state_resp = client.post("/test/hook", json={
            "zone_id": 12,
            "action": "set_state",
        })
        assert missing_state_resp.status_code == 400
        assert "set_state requires state" in missing_state_resp.json()["detail"]

        unknown_action_resp = client.post("/test/hook", json={
            "zone_id": 12,
            "action": "unknown_action",
        })
        assert unknown_action_resp.status_code == 400
        assert "Unknown action" in unknown_action_resp.json()["detail"]
    finally:
        api._test_mode = old_mode
        api._zone_states_override.clear()
        api._zone_states_override.update(old_states)


def test_test_hook_set_state_normalizes_datetime_fields(client):
    """set_state должен преобразовывать ISO-дату в datetime внутри override."""
    old_mode = api._test_mode
    old_states = dict(api._zone_states_override)
    try:
        api._test_mode = True
        api._zone_states_override.clear()

        response = client.post("/test/hook", json={
            "zone_id": 13,
            "action": "set_state",
            "state": {
                "error_streak": 2,
                "next_allowed_run_at": "2099-01-01T00:00:00Z",
            },
        })
        assert response.status_code == 200

        state = api._zone_states_override[13]
        assert state["error_streak"] == 2
        assert isinstance(state["next_allowed_run_at"], datetime)
        assert state["next_allowed_run_at"].isoformat().startswith("2099-01-01T00:00:00")
        assert state["degraded_alert_active"] is False
    finally:
        api._test_mode = old_mode
        api._zone_states_override.clear()
        api._zone_states_override.update(old_states)


def test_test_hook_publish_command_success(client, mock_command_bus):
    """publish_command в test hook должен вызывать CommandBus и возвращать флаг published."""
    old_mode = api._test_mode
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        api._test_mode = True
        mock_command_bus.publish_command = AsyncMock(return_value=False)
        set_command_bus(mock_command_bus, "gh-test")

        response = client.post("/test/hook", json={
            "zone_id": 21,
            "action": "publish_command",
            "command": {
                "node_uid": "nd-ph-esp32una",
                "channel": "main_pump",
                "cmd": "set_relay",
                "params": {"state": 1, "marker": "e2e-marker"},
                "cmd_id": "cmd-e2e-1",
            },
        })

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["data"]["published"] is False
        assert payload["data"]["zone_id"] == 21
        assert payload["data"]["node_uid"] == "nd-ph-esp32una"

        mock_command_bus.publish_command.assert_called_once_with(
            zone_id=21,
            node_uid="nd-ph-esp32una",
            channel="main_pump",
            cmd="set_relay",
            params={"state": 1, "marker": "e2e-marker"},
            cmd_id="cmd-e2e-1",
        )
    finally:
        api._test_mode = old_mode
        set_command_bus(old_command_bus, old_gh_uid)


def test_test_hook_publish_command_requires_payload(client, mock_command_bus):
    """publish_command в test hook должен требовать command payload."""
    old_mode = api._test_mode
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        api._test_mode = True
        set_command_bus(mock_command_bus, "gh-test")

        response = client.post("/test/hook", json={
            "zone_id": 22,
            "action": "publish_command",
        })

        assert response.status_code == 400
        assert "publish_command requires command payload" in response.json()["detail"]
    finally:
        api._test_mode = old_mode
        set_command_bus(old_command_bus, old_gh_uid)


def test_test_hook_publish_command_validates_required_fields(client, mock_command_bus):
    """publish_command в test hook валидирует обязательные поля node_uid/channel/cmd."""
    old_mode = api._test_mode
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        api._test_mode = True
        mock_command_bus.publish_command = AsyncMock(return_value=True)
        set_command_bus(mock_command_bus, "gh-test")

        response = client.post("/test/hook", json={
            "zone_id": 23,
            "action": "publish_command",
            "command": {
                "node_uid": "",
                "channel": "main_pump",
                "cmd": "set_relay",
            },
        })

        assert response.status_code == 400
        assert "command.node_uid" in response.json()["detail"]
        mock_command_bus.publish_command.assert_not_called()
    finally:
        api._test_mode = old_mode
        set_command_bus(old_command_bus, old_gh_uid)


def test_test_hook_publish_command_uses_temporary_command_bus_when_not_initialized(client):
    """При отсутствии глобального CommandBus test hook должен поднять временный экземпляр."""
    old_mode = api._test_mode
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        api._test_mode = True
        set_command_bus(None, "")

        temp_bus = Mock()
        temp_bus.start = AsyncMock(return_value=None)
        temp_bus.stop = AsyncMock(return_value=None)
        temp_bus.publish_command = AsyncMock(return_value=False)

        with patch("api.CommandBus", return_value=temp_bus) as command_bus_cls:
            response = client.post("/test/hook", json={
                "zone_id": 24,
                "action": "publish_command",
                "command": {
                    "node_uid": "nd-ph-esp32una",
                    "channel": "main_pump",
                    "cmd": "set_relay",
                    "params": {"state": 1},
                },
            })

        assert response.status_code == 200
        assert response.json()["data"]["published"] is False
        command_bus_cls.assert_called_once()
        assert command_bus_cls.call_args.kwargs["enforce_node_zone_assignment"] is True
        temp_bus.start.assert_awaited_once()
        temp_bus.publish_command.assert_awaited_once()
        temp_bus.stop.assert_awaited_once()
    finally:
        api._test_mode = old_mode
        set_command_bus(old_command_bus, old_gh_uid)
