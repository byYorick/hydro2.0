"""Tests for automation-engine REST API."""
import asyncio
import logging
import pytest
import sys
import os
import httpx
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

# Добавляем путь к модулю для импорта
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api
from api import app, set_command_bus
from infrastructure.command_bus import CommandBus


@pytest.fixture(scope="session")
def client():
    """Create test client."""
    with TestClient(app) as test_client:
        yield test_client


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
def disable_scheduler_background_spawn():
    """Keep API tests deterministic: do not execute fire-and-forget background tasks."""

    def _drop_background_task(coro, **kwargs):
        coro.close()
        return Mock()

    with patch("api._spawn_background_task", side_effect=_drop_background_task):
        yield


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


@pytest.fixture(autouse=True)
def scheduler_security_baseline_defaults():
    old_enforce = api._AE_SCHEDULER_SECURITY_BASELINE_ENFORCE
    old_require_trace = api._AE_SCHEDULER_REQUIRE_TRACE_ID
    old_token = api._AE_SCHEDULER_API_TOKEN
    api._AE_SCHEDULER_SECURITY_BASELINE_ENFORCE = True
    api._AE_SCHEDULER_REQUIRE_TRACE_ID = True
    api._AE_SCHEDULER_API_TOKEN = "dev-token-12345"
    yield
    api._AE_SCHEDULER_SECURITY_BASELINE_ENFORCE = old_enforce
    api._AE_SCHEDULER_REQUIRE_TRACE_ID = old_require_trace
    api._AE_SCHEDULER_API_TOKEN = old_token


def bootstrap_headers(
    client: TestClient,
    scheduler_id: str = "scheduler-test",
    *,
    auth_token: str = "dev-token-12345",
    trace_id: str = "trace-test-scheduler",
) -> dict:
    response = client.post("/scheduler/bootstrap", json={
        "scheduler_id": scheduler_id,
        "scheduler_version": "test",
        "protocol_version": "2.0",
    })
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["bootstrap_status"] == "ready"
    lease_id = data["lease_id"]
    headers = {
        "X-Scheduler-Id": scheduler_id,
        "X-Scheduler-Lease-Id": lease_id,
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    if trace_id:
        headers["X-Trace-Id"] = trace_id
    return headers


def scheduler_task_payload(**overrides) -> dict:
    def _merge_dict(dst: dict, src: dict) -> dict:
        for key, value in src.items():
            if isinstance(value, dict) and isinstance(dst.get(key), dict):
                _merge_dict(dst[key], value)
            else:
                dst[key] = value
        return dst

    base_scheduled_for = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)).replace(microsecond=0)
    base_due_at = base_scheduled_for + timedelta(seconds=15)
    base_expires_at = base_scheduled_for + timedelta(minutes=2)

    payload = {
        "zone_id": 1,
        "task_type": "diagnostics",
        "payload": {
            "workflow": "startup",
            "config": {
                "execution": {
                    "topology": "two_tank_drip_substrate_trays",
                }
            },
            "reason": "scheduled_check",
        },
        "scheduled_for": base_scheduled_for.isoformat(),
        "due_at": base_due_at.isoformat(),
        "expires_at": base_expires_at.isoformat(),
        "correlation_id": "sch:z1:diagnostics:test",
    }
    local_overrides = dict(overrides)
    payload_override = local_overrides.pop("payload", None)
    if isinstance(payload_override, dict):
        _merge_dict(payload["payload"], payload_override)
    elif payload_override is not None:
        payload["payload"] = payload_override
    payload.update(local_overrides)
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


def test_zone_automation_state_returns_idle_without_active_tasks(client):
    response = client.get("/zones/1/automation-state")
    assert response.status_code == 200
    data = response.json()
    assert data["zone_id"] == 1
    assert data["state"] == "IDLE"
    assert data["state_details"]["progress_percent"] == 0
    assert data["active_processes"]["pump_in"] is False
    assert data["system_config"]["tanks_count"] == 2
    assert data["irr_node_state"] is None
    assert data["control_mode"] == "auto"
    assert data["allowed_manual_steps"] == []


def test_zone_automation_state_maps_two_tank_workflow_to_tank_filling(client):
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat()
    api._scheduler_tasks["st-panel-1"] = {
        "task_id": "st-panel-1",
        "zone_id": 1,
        "task_type": "diagnostics",
        "status": "running",
        "payload": {
            "workflow": "clean_fill_check",
            "config": {
                "execution": {
                    "system_type": "substrate_trays",
                    "tanks_count": 2,
                    "clean_tank_fill_l": 80,
                    "nutrient_tank_target_l": 120,
                }
            },
            "clean_fill_started_at": now_iso,
        },
        "result": {"mode": "two_tank_clean_fill_in_progress"},
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    response = client.get("/zones/1/automation-state")
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "TANK_FILLING"
    assert data["active_processes"]["pump_in"] is True
    assert data["active_processes"]["circulation_pump"] is False
    assert data["system_config"]["system_type"] == "substrate_trays"
    assert data["system_config"]["tanks_count"] == 2
    assert data["system_config"]["clean_tank_capacity_l"] == 80.0
    assert data["system_config"]["nutrient_tank_capacity_l"] == 120.0
    assert "irr_node_state" in data
    assert data["control_mode"] == "auto"


def test_zone_automation_state_includes_manual_control_mode(client):
    with patch("api._load_zone_control_mode", new_callable=AsyncMock, return_value="manual"):
        response = client.get("/zones/1/automation-state")

    assert response.status_code == 200
    data = response.json()
    assert data["control_mode"] == "manual"
    assert isinstance(data["allowed_manual_steps"], list)
    assert "clean_fill_start" in data["allowed_manual_steps"]


def test_automation_control_mode_get_returns_default_auto(client):
    with patch.object(api._workflow_state_store, "get", new_callable=AsyncMock, return_value=None):
        response = client.get("/zones/1/automation/control-mode")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["control_mode"] == "auto"
    assert data["data"]["allowed_manual_steps"] == []


def test_automation_control_mode_post_rejects_invalid_mode(client):
    response = client.post("/zones/1/automation/control-mode", json={"control_mode": "invalid"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_control_mode"


def test_automation_control_mode_post_updates_mode(client):
    with patch("api._load_zone_control_mode", new_callable=AsyncMock, return_value="auto"), \
         patch("api._persist_zone_control_mode", new_callable=AsyncMock, return_value={"updated_at": datetime.now(timezone.utc)}), \
         patch("api.create_zone_event", new_callable=AsyncMock) as mock_event:
        response = client.post("/zones/1/automation/control-mode", json={"control_mode": "manual"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["control_mode"] == "manual"
    assert "clean_fill_start" in data["data"]["allowed_manual_steps"]
    mock_event.assert_awaited_once()


def test_automation_manual_step_rejects_in_auto_mode(client):
    with patch("api._load_zone_control_mode", new_callable=AsyncMock, return_value="auto"):
        response = client.post("/zones/1/automation/manual-step", json={"manual_step": "clean_fill_start"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "manual_step_forbidden_in_auto_mode"


def test_automation_manual_step_accepts_supported_step(client):
    with patch("api._load_zone_control_mode", new_callable=AsyncMock, return_value="manual"), \
         patch("api.create_zone_event", new_callable=AsyncMock) as mock_event:
        response = client.post("/zones/1/automation/manual-step", json={"manual_step": "clean_fill_start"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["manual_step"] == "clean_fill_start"
    task_id = data["data"]["task_id"]
    assert task_id in api._scheduler_tasks
    payload = api._scheduler_tasks[task_id]["payload"]
    assert payload["workflow"] == "manual_step"
    assert payload["manual_step"] == "clean_fill_start"
    assert payload["config"]["execution"]["topology"] == "two_tank_drip_substrate_trays"
    mock_event.assert_awaited_once()


def test_automation_manual_step_rejects_unsupported_topology(client):
    with patch("api._load_zone_control_mode", new_callable=AsyncMock, return_value="manual"), \
         patch("api._load_latest_zone_task", new_callable=AsyncMock, return_value={
             "payload": {"config": {"execution": {"topology": "three_tank"}}}
         }):
        response = client.post("/zones/1/automation/manual-step", json={"manual_step": "clean_fill_start"})

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "manual_step_topology_not_supported"


def test_manual_resume_accepts_manual_ack_blocked_task(client):
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat()
    api._scheduler_tasks["st-blocked-recovery"] = {
        "task_id": "st-blocked-recovery",
        "zone_id": 1,
        "task_type": "diagnostics",
        "status": "failed",
        "payload": {
            "workflow": "irrigation_recovery_check",
            "irrigation_recovery_attempt": 2,
            "irrigation_recovery_started_at": now_iso,
            "irrigation_recovery_timeout_at": now_iso,
            "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}},
        },
        "result": {
            "success": False,
            "reason_code": "manual_ack_required_after_retries",
            "error_code": "irrigation_recovery_attempts_exceeded",
            "manual_ack_required": True,
        },
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    response = client.post("/zones/1/automation/manual-resume", json={"task_id": "st-blocked-recovery"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["zone_id"] == 1
    assert data["data"]["manual_resume"] == "accepted"
    resumed_task_id = data["data"]["task_id"]
    assert resumed_task_id in api._scheduler_tasks
    resumed_payload = api._scheduler_tasks[resumed_task_id]["payload"]
    assert resumed_payload["workflow"] == "irrigation_recovery"
    assert resumed_payload["irrigation_recovery_attempt"] == 1
    assert "irrigation_recovery_started_at" not in resumed_payload
    assert "irrigation_recovery_timeout_at" not in resumed_payload


def test_manual_resume_rejects_when_manual_ack_not_required(client):
    now_iso = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat()
    api._scheduler_tasks["st-not-blocked"] = {
        "task_id": "st-not-blocked",
        "zone_id": 1,
        "task_type": "diagnostics",
        "status": "failed",
        "payload": {
            "workflow": "irrigation_recovery_check",
            "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}},
        },
        "result": {"success": False, "reason_code": "irrigation_recovery_failed"},
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    response = client.post("/zones/1/automation/manual-resume", json={"task_id": "st-not-blocked"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "manual_ack_not_required"


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


def test_scheduler_bootstrap_protocol_mismatch_emits_deny_alert(client, mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        set_command_bus(mock_command_bus, "gh-1")
        with patch("api.send_infra_alert", new_callable=AsyncMock) as mock_alert:
            response = client.post("/scheduler/bootstrap", json={
                "scheduler_id": "scheduler-proto-mismatch",
                "scheduler_version": "test",
                "protocol_version": "1.0",
            })

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["bootstrap_status"] == "deny"
        assert data["reason"] == "protocol_not_supported"
        mock_alert.assert_awaited_once()
        assert mock_alert.await_args.kwargs["code"] == "infra_scheduler_bootstrap_denied"
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
    assert bootstrap_data["rollout_profile"] == "canary-first"
    assert bootstrap_data["tier2_capabilities"] == {
        "gdd_phase_transitions": False,
        "mobile_approvals": False,
        "daily_health_digest": False,
    }
    lease_id = bootstrap_data["lease_id"]

    heartbeat_response = client.post("/scheduler/bootstrap/heartbeat", json={
        "scheduler_id": "scheduler-test",
        "lease_id": lease_id,
    })
    assert heartbeat_response.status_code == 200
    heartbeat_data = heartbeat_response.json()["data"]
    assert heartbeat_data["bootstrap_status"] == "ready"
    assert heartbeat_data["rollout_profile"] == "canary-first"
    assert heartbeat_data["tier2_capabilities"] == {
        "gdd_phase_transitions": False,
        "mobile_approvals": False,
        "daily_health_digest": False,
    }
    assert heartbeat_data["lease_id"] == lease_id


def test_scheduler_cutover_state_endpoint(client):
    response = client.get("/scheduler/cutover/state")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["rollout_profile"] == "canary-first"
    assert data["tier2_capabilities"] == {
        "gdd_phase_transitions": False,
        "mobile_approvals": False,
        "daily_health_digest": False,
    }
    ingress = data["scheduler_ingress"]
    assert ingress["bootstrap_enforce"] is True
    assert ingress["security_baseline_enforce"] is True
    assert ingress["require_trace_id"] is True


def test_scheduler_integration_contracts_endpoint(client):
    response = client.get("/scheduler/integration/contracts")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["contract_version"] == "s11-v1"
    assert data["rollout_profile"] == "canary-first"
    integrations = data["integrations"]
    assert integrations["gdd_phase_transitions"]["enabled"] is False
    assert integrations["mobile_approvals"]["enabled"] is False
    assert integrations["daily_health_digest"]["enabled"] is False


def test_scheduler_observability_contracts_endpoint(client):
    response = client.get("/scheduler/observability/contracts")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["contract_version"] == "s11-observability-v1"
    assert "scheduler_bootstrap_status_total{status,rollout_profile}" in data["required_metrics"]
    assert "infra_scheduler_bootstrap_denied" in data["required_alert_codes"]
    assert "SCHEDULE_TASK_FAILED" in data["required_events"]


def test_scheduler_observability_contracts_lists_are_unique(client):
    response = client.get("/scheduler/observability/contracts")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["required_metrics"]) == len(set(data["required_metrics"]))
    assert len(data["required_alert_codes"]) == len(set(data["required_alert_codes"]))
    assert len(data["required_events"]) == len(set(data["required_events"]))


def test_scheduler_cutover_contracts_follow_rollout_and_tier2_flags(client, mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    old_rollout_profile = api._AE2_ROLLOUT_PROFILE
    old_tier2_gdd = api._AE2_TIER2_GDD_ENABLED
    old_tier2_approvals = api._AE2_TIER2_APPROVALS_ENABLED
    old_tier2_digest = api._AE2_TIER2_DAILY_DIGEST_ENABLED

    try:
        mock_command_bus.publish_command = AsyncMock(return_value=True)
        set_command_bus(mock_command_bus, "gh-1")
        api._AE2_ROLLOUT_PROFILE = "shadow-canary-full"
        api._AE2_TIER2_GDD_ENABLED = True
        api._AE2_TIER2_APPROVALS_ENABLED = True
        api._AE2_TIER2_DAILY_DIGEST_ENABLED = False

        bootstrap_response = client.post("/scheduler/bootstrap", json={
            "scheduler_id": "scheduler-cutover-flags",
            "scheduler_version": "test",
            "protocol_version": "2.0",
        })
        assert bootstrap_response.status_code == 200
        bootstrap_data = bootstrap_response.json()["data"]
        assert bootstrap_data["bootstrap_status"] == "ready"
        assert bootstrap_data["rollout_profile"] == "shadow-canary-full"
        assert bootstrap_data["tier2_capabilities"] == {
            "gdd_phase_transitions": True,
            "mobile_approvals": True,
            "daily_health_digest": False,
        }

        heartbeat_response = client.post("/scheduler/bootstrap/heartbeat", json={
            "scheduler_id": "scheduler-cutover-flags",
            "lease_id": bootstrap_data["lease_id"],
        })
        assert heartbeat_response.status_code == 200
        heartbeat_data = heartbeat_response.json()["data"]
        assert heartbeat_data["rollout_profile"] == "shadow-canary-full"
        assert heartbeat_data["tier2_capabilities"] == bootstrap_data["tier2_capabilities"]

        cutover_response = client.get("/scheduler/cutover/state")
        assert cutover_response.status_code == 200
        cutover_data = cutover_response.json()["data"]
        assert cutover_data["rollout_profile"] == "shadow-canary-full"
        assert cutover_data["tier2_capabilities"] == bootstrap_data["tier2_capabilities"]

        integration_response = client.get("/scheduler/integration/contracts")
        assert integration_response.status_code == 200
        integration_data = integration_response.json()["data"]
        assert integration_data["rollout_profile"] == "shadow-canary-full"
        assert integration_data["integrations"]["gdd_phase_transitions"]["enabled"] is True
        assert integration_data["integrations"]["mobile_approvals"]["enabled"] is True
        assert integration_data["integrations"]["daily_health_digest"]["enabled"] is False
    finally:
        api._AE2_ROLLOUT_PROFILE = old_rollout_profile
        api._AE2_TIER2_GDD_ENABLED = old_tier2_gdd
        api._AE2_TIER2_APPROVALS_ENABLED = old_tier2_approvals
        api._AE2_TIER2_DAILY_DIGEST_ENABLED = old_tier2_digest
        set_command_bus(old_command_bus, old_gh_uid)


def test_scheduler_bootstrap_wait_then_ready_transition(client, mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid

    try:
        set_command_bus(None, "")
        wait_response = client.post("/scheduler/bootstrap", json={
            "scheduler_id": "scheduler-cutover-transition",
            "scheduler_version": "test",
            "protocol_version": "2.0",
        })
        assert wait_response.status_code == 200
        wait_data = wait_response.json()["data"]
        assert wait_data["bootstrap_status"] == "wait"
        assert wait_data["reason"] == "automation_not_ready"
        assert "lease_id" not in wait_data

        mock_command_bus.publish_command = AsyncMock(return_value=True)
        set_command_bus(mock_command_bus, "gh-1")
        ready_response = client.post("/scheduler/bootstrap", json={
            "scheduler_id": "scheduler-cutover-transition",
            "scheduler_version": "test",
            "protocol_version": "2.0",
        })
        assert ready_response.status_code == 200
        ready_data = ready_response.json()["data"]
        assert ready_data["bootstrap_status"] == "ready"
        assert "reason" not in ready_data
        assert ready_data["lease_id"]
    finally:
        set_command_bus(old_command_bus, old_gh_uid)


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


def test_scheduler_internal_enqueue_returns_ok_when_zone_event_fails(client):
    tz_msk = timezone(timedelta(hours=3))
    scheduled_for = (datetime.now(tz_msk) + timedelta(minutes=5)).replace(microsecond=0)

    with patch("scheduler_internal_enqueue.create_scheduler_log", new_callable=AsyncMock) as mock_scheduler_log, \
         patch("scheduler_internal_enqueue.create_zone_event", new_callable=AsyncMock, side_effect=RuntimeError("zone event failed")):
        response = client.post("/scheduler/internal/enqueue", json={
            "zone_id": 1,
            "task_type": "diagnostics",
            "payload": {"workflow": "check"},
            "scheduled_for": scheduled_for.isoformat(),
            "source": "automation-engine",
        })

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
    mock_scheduler_log.assert_awaited_once()


def test_scheduler_internal_enqueue_rejects_expiry_before_schedule(client):
    tz_msk = timezone(timedelta(hours=3))
    scheduled_for = (datetime.now(tz_msk) + timedelta(minutes=5)).replace(microsecond=0)
    expires_at = scheduled_for - timedelta(seconds=10)

    response = client.post("/scheduler/internal/enqueue", json={
        "zone_id": 1,
        "task_type": "diagnostics",
        "payload": {"workflow": "refill_check"},
        "scheduled_for": scheduled_for.isoformat(),
        "expires_at": expires_at.isoformat(),
        "source": "automation-engine",
    })

    assert response.status_code == 422
    assert response.json()["detail"] == "expires_at_before_scheduled_for"


def test_scheduler_internal_enqueue_rejects_invalid_scheduled_for(client):
    response = client.post("/scheduler/internal/enqueue", json={
        "zone_id": 1,
        "task_type": "diagnostics",
        "payload": {"workflow": "refill_check"},
        "scheduled_for": "not-a-datetime",
        "source": "automation-engine",
    })

    assert response.status_code == 422
    assert response.json()["detail"] == "scheduled_for_invalid"


def test_scheduler_internal_enqueue_rejects_invalid_expires_at(client):
    response = client.post("/scheduler/internal/enqueue", json={
        "zone_id": 1,
        "task_type": "diagnostics",
        "payload": {"workflow": "refill_check"},
        "expires_at": "invalid-expiry",
        "source": "automation-engine",
    })

    assert response.status_code == 422
    assert response.json()["detail"] == "expires_at_invalid"


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


@pytest.mark.asyncio
async def test_scheduler_task_accepts_when_schedule_event_fails(client, mock_command_bus):
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")
    headers = bootstrap_headers(client)
    payload = scheduler_task_payload(correlation_id="sch:z1:diagnostics:event-fail")

    def _cancel_background_task(coro, **kwargs):
        coro.close()
        return Mock()

    with patch("api.create_zone_event", new=AsyncMock(side_effect=RuntimeError("event insert failed"))), \
         patch("api._spawn_background_task", side_effect=_cancel_background_task) as mock_create_task:
        response = client.post("/scheduler/task", json=payload, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    mock_create_task.assert_called_once()


def test_scheduler_task_lifecycle_persists_snapshots(client, mock_command_bus):
    """Task endpoint должен пройти lifecycle accepted->running->completed и записать snapshots."""
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")
    headers = bootstrap_headers(client)

    async def _execute(**kwargs):
        await asyncio.sleep(0.01)
        return {"success": True, "commands_sent": 1, "task_type": kwargs.get("task_type")}

    def _cancel_background_task(coro, **kwargs):
        coro.close()
        return Mock()

    with patch("api.SchedulerTaskExecutor") as mock_executor_cls, \
         patch("api.create_scheduler_log", new_callable=AsyncMock) as mock_scheduler_log, \
         patch("api.create_zone_event", new_callable=AsyncMock), \
         patch("api._spawn_background_task", side_effect=_cancel_background_task) as mock_create_task:
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


def test_scheduler_task_diagnostics_requires_topology(client, mock_command_bus):
    set_command_bus(mock_command_bus, "gh-1")
    payload = scheduler_task_payload(
        payload={
            "workflow": "startup",
            "config": {"execution": {"topology": ""}},
        },
        correlation_id="sch:z1:diagnostics:missing-topology",
    )
    response = client.post("/scheduler/task", json=payload, headers=bootstrap_headers(client))
    assert response.status_code == 422
    assert "missing_topology" in response.text


def test_scheduler_task_diagnostics_requires_workflow(client, mock_command_bus):
    set_command_bus(mock_command_bus, "gh-1")
    payload = scheduler_task_payload(
        payload={"workflow": "", "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}}},
        correlation_id="sch:z1:diagnostics:missing-workflow",
    )
    response = client.post("/scheduler/task", json=payload, headers=bootstrap_headers(client))
    assert response.status_code == 422
    assert "missing_workflow" in response.text


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


def test_scheduler_task_requires_authorization_header(client, mock_command_bus):
    set_command_bus(mock_command_bus, "gh-1")
    payload = scheduler_task_payload(correlation_id="sch:z1:diagnostics:no-auth")
    headers = bootstrap_headers(client)
    headers.pop("Authorization", None)

    response = client.post("/scheduler/task", json=payload, headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "unauthorized"


def test_scheduler_task_rejects_invalid_authorization_token(client, mock_command_bus):
    set_command_bus(mock_command_bus, "gh-1")
    payload = scheduler_task_payload(correlation_id="sch:z1:diagnostics:bad-auth")
    headers = bootstrap_headers(client, auth_token="wrong-token")

    response = client.post("/scheduler/task", json=payload, headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "unauthorized"


def test_scheduler_task_requires_trace_header(client, mock_command_bus):
    set_command_bus(mock_command_bus, "gh-1")
    payload = scheduler_task_payload(correlation_id="sch:z1:diagnostics:no-trace")
    headers = bootstrap_headers(client)
    headers.pop("X-Trace-Id", None)

    response = client.post("/scheduler/task", json=payload, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"] == "missing_trace_id"


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

    api._scheduler_bootstrap_leases[scheduler_id]["expires_at"] = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)

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
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)

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
    now = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0)

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
    old_command_bus_loop_id = api._command_bus_loop_id
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
        assert stored["result"]["decision"] == "fail"
        assert stored["result"]["action_required"] is True
    finally:
        set_command_bus(old_command_bus, old_gh_uid)
        api._command_bus_loop_id = old_command_bus_loop_id


@pytest.mark.asyncio
async def test_execute_scheduler_task_command_bus_loop_mismatch_sets_structured_failure(mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    old_command_bus_loop_id = api._command_bus_loop_id
    try:
        set_command_bus(mock_command_bus, "gh-1")
        req = api.SchedulerTaskRequest(**scheduler_task_payload(correlation_id="sch:z1:diagnostics:loop-mismatch"))
        task, _ = await api._create_scheduler_task(req)

        api._command_bus_loop_id = -1
        await api._execute_scheduler_task(task["task_id"], req, None)

        stored = api._scheduler_tasks[task["task_id"]]
        assert stored["status"] == "failed"
        assert stored["error_code"] == "command_bus_loop_mismatch"
        assert stored["result"]["reason_code"] == "command_bus_loop_mismatch"
        assert stored["result"]["decision"] == "fail"
        assert stored["result"]["action_required"] is True
    finally:
        set_command_bus(old_command_bus, old_gh_uid)
        api._command_bus_loop_id = old_command_bus_loop_id


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
        assert stored["result"]["decision"] == "fail"
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
        assert stored["result"]["decision"] == "fail"
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


@pytest.mark.asyncio
async def test_execute_scheduler_task_irrigation_two_tank_failure_transitions_to_recovery(mock_command_bus):
    old_command_bus = api._command_bus
    old_gh_uid = api._gh_uid
    try:
        call_state = {"attempt": 0}

        async def _closed_loop_side_effect(**kwargs):
            call_state["attempt"] += 1
            command = kwargs.get("command") if isinstance(kwargs.get("command"), dict) else {}
            channel = str(command.get("channel") or "")
            if call_state["attempt"] == 1 and channel == "default":
                return {
                    "command_submitted": True,
                    "command_effect_confirmed": False,
                    "terminal_status": "NO_EFFECT",
                    "cmd_id": "cmd-irrig-fail-api-1",
                    "error_code": "NO_EFFECT",
                    "error": "terminal_no_effect",
                }
            return {
                "command_submitted": True,
                "command_effect_confirmed": True,
                "terminal_status": "DONE",
                "cmd_id": f"cmd-recovery-api-{call_state['attempt']}",
                "error_code": None,
                "error": None,
            }

        mock_command_bus.publish_command = AsyncMock(return_value=True)
        mock_command_bus.publish_controller_command_closed_loop = AsyncMock(side_effect=_closed_loop_side_effect)
        set_command_bus(mock_command_bus, "gh-1")

        req = api.SchedulerTaskRequest(
            **scheduler_task_payload(
                task_type="irrigation",
                correlation_id="sch:z1:irrigation:two-tank-recovery",
                payload={
                    "targets": {
                        "ph": {"target": 5.8},
                        "ec": {"target": 1.6},
                        "diagnostics": {
                            "execution": {
                                "topology": "two_tank_drip_substrate_trays",
                                "startup": {"required_node_types": ["irrig"]},
                                "irrigation_recovery": {"max_continue_attempts": 5, "timeout_sec": 600},
                            }
                        },
                    }
                },
            )
        )
        task, _ = await api._create_scheduler_task(req)

        async def _fetch_side_effect(query, *args):
            normalized = " ".join(str(query).split()).lower()
            if "from nodes n left join node_channels nc on nc.node_id = n.id" in normalized:
                return [{"uid": "nd-irrig-1", "type": "irrig", "channel": "default"}]
            if "join node_channels nc on nc.node_id = n.id" in normalized and "lower(coalesce(nc.channel, 'default')) = $2" in normalized:
                channel = args[1]
                if channel in {"valve_irrigation", "valve_solution_supply", "valve_solution_fill", "pump_main"}:
                    return [{"node_uid": "nd-irrig-1", "node_type": "irrig", "channel": channel}]
            return []

        with patch("scheduler_task_executor.fetch", new_callable=AsyncMock) as mock_fetch, \
             patch("scheduler_task_executor.create_zone_event", new_callable=AsyncMock), \
             patch("scheduler_task_executor.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue:
            mock_fetch.side_effect = _fetch_side_effect
            mock_enqueue.return_value = {
                "enqueue_id": "enq-api-recovery-1",
                "scheduled_for": "2026-02-13T11:01:00",
                "expires_at": "2026-02-13T11:21:00",
                "correlation_id": "ae:self:1:diagnostics:enq-api-recovery-1",
                "status": "pending",
                "zone_id": 1,
                "task_type": "diagnostics",
            }

            await api._execute_scheduler_task(task["task_id"], req, None)

        stored = api._scheduler_tasks[task["task_id"]]
        assert stored["status"] == "completed"
        assert stored["task_type"] == "irrigation"
        assert stored["result"]["mode"] == "two_tank_irrigation_recovery_in_progress"
        assert stored["result"]["workflow"] == "irrigation_recovery"
        assert stored["result"]["source_reason_code"] == "online_correction_failed"
        assert stored["result"]["transition_reason_code"] == "tank_to_tank_correction_started"
        assert stored["result"]["online_correction_error_code"] == "command_no_effect"
        assert stored["result"]["next_check"]["enqueue_id"] == "enq-api-recovery-1"
        assert mock_command_bus.publish_controller_command_closed_loop.await_count == 5
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


@pytest.mark.asyncio
async def test_scheduler_task_concurrent_submit_with_housekeeping_no_loop_errors(mock_command_bus):
    """Concurrent scheduler/task submits with background housekeeping must remain stable."""
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        bootstrap_response = await async_client.post(
            "/scheduler/bootstrap",
            json={
                "scheduler_id": "scheduler-concurrent",
                "scheduler_version": "test",
                "protocol_version": "2.0",
            },
        )
        assert bootstrap_response.status_code == 200
        bootstrap_data = bootstrap_response.json()["data"]
        lease_id = bootstrap_data["lease_id"]

        headers = {
            "X-Scheduler-Id": "scheduler-concurrent",
            "X-Scheduler-Lease-Id": lease_id,
            "Authorization": "Bearer dev-token-12345",
            "X-Trace-Id": "trace-test-concurrent",
        }

        stop_housekeeping = asyncio.Event()

        async def _housekeeping_loop():
            while not stop_housekeeping.is_set():
                await api._cleanup_scheduler_tasks_locked(datetime.now(timezone.utc).replace(tzinfo=None))
                await asyncio.sleep(0)

        housekeeping_task = asyncio.create_task(_housekeeping_loop())
        try:
            async def _submit(index: int) -> str:
                payload = scheduler_task_payload(
                    correlation_id=f"sch:z1:diagnostics:concurrent-{index}",
                    payload={"reason": "concurrent", "index": index},
                )
                response = await async_client.post(
                    "/scheduler/task",
                    json=payload,
                    headers=headers,
                )
                assert response.status_code == 200, response.text
                data = response.json()["data"]
                assert data["is_duplicate"] is False
                return data["task_id"]

            task_ids = await asyncio.gather(*(_submit(i) for i in range(40)))
        finally:
            stop_housekeeping.set()
            housekeeping_task.cancel()
            try:
                await housekeeping_task
            except asyncio.CancelledError:
                pass

    assert len(task_ids) == 40
    assert len(set(task_ids)) == 40


@pytest.mark.asyncio
async def test_scheduler_cutover_contract_endpoints_burst_no_errors():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        async def _call(path: str) -> None:
            response = await async_client.get(path)
            assert response.status_code == 200, response.text
            data = response.json()["data"]
            assert isinstance(data, dict)

        paths = (
            "/scheduler/cutover/state",
            "/scheduler/integration/contracts",
            "/scheduler/observability/contracts",
        )
        await asyncio.gather(*(_call(paths[i % len(paths)]) for i in range(180)))


@pytest.mark.asyncio
async def test_scheduler_bootstrap_heartbeat_churn_stays_ready(mock_command_bus):
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        async def _bootstrap_and_heartbeat(index: int) -> str:
            scheduler_id = f"scheduler-churn-{index}"
            bootstrap = await async_client.post(
                "/scheduler/bootstrap",
                json={
                    "scheduler_id": scheduler_id,
                    "scheduler_version": "test",
                    "protocol_version": "2.0",
                },
            )
            assert bootstrap.status_code == 200, bootstrap.text
            bootstrap_data = bootstrap.json()["data"]
            assert bootstrap_data["bootstrap_status"] == "ready"
            lease_id = bootstrap_data["lease_id"]

            heartbeat = await async_client.post(
                "/scheduler/bootstrap/heartbeat",
                json={
                    "scheduler_id": scheduler_id,
                    "lease_id": lease_id,
                },
            )
            assert heartbeat.status_code == 200, heartbeat.text
            heartbeat_data = heartbeat.json()["data"]
            assert heartbeat_data["bootstrap_status"] == "ready"
            assert heartbeat_data["lease_id"] == lease_id
            return lease_id

        lease_ids = await asyncio.gather(*(_bootstrap_and_heartbeat(i) for i in range(30)))

    assert len(lease_ids) == 30
    assert len(set(lease_ids)) == 30


@pytest.mark.asyncio
async def test_scheduler_task_high_volume_concurrent_submit_stable(mock_command_bus):
    mock_command_bus.publish_command = AsyncMock(return_value=True)
    set_command_bus(mock_command_bus, "gh-1")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        bootstrap_response = await async_client.post(
            "/scheduler/bootstrap",
            json={
                "scheduler_id": "scheduler-high-volume",
                "scheduler_version": "test",
                "protocol_version": "2.0",
            },
        )
        assert bootstrap_response.status_code == 200
        lease_id = bootstrap_response.json()["data"]["lease_id"]
        headers = {
            "X-Scheduler-Id": "scheduler-high-volume",
            "X-Scheduler-Lease-Id": lease_id,
            "Authorization": "Bearer dev-token-12345",
            "X-Trace-Id": "trace-test-high-volume",
        }

        async def _submit(index: int) -> str:
            payload = scheduler_task_payload(
                correlation_id=f"sch:z1:diagnostics:high-volume-{index}",
                payload={"reason": "high_volume", "index": index},
            )
            response = await async_client.post("/scheduler/task", json=payload, headers=headers)
            assert response.status_code == 200, response.text
            data = response.json()["data"]
            assert data["is_duplicate"] is False
            return data["task_id"]

        task_ids = await asyncio.gather(*(_submit(i) for i in range(120)))

    assert len(task_ids) == 120
    assert len(set(task_ids)) == 120


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


@pytest.mark.asyncio
async def test_recover_zone_workflow_states_enqueues_continuation_for_active_phase():
    old_enabled = api._AE_WORKFLOW_STATE_RECOVERY_ENABLED
    old_stale_timeout = api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC
    api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = True
    api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = 1800
    try:
        active_state = {
            "zone_id": 1,
            "workflow_phase": "tank_filling",
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=120),
            "payload": {
                "workflow": "solution_fill_check",
                "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}},
            },
            "scheduler_task_id": "st-old-1",
        }
        with patch.object(api._workflow_state_store, "list_active", new_callable=AsyncMock, return_value=[active_state]), \
             patch.object(api._workflow_state_store, "set", new_callable=AsyncMock) as mock_state_set, \
             patch("api.enqueue_internal_scheduler_task", new_callable=AsyncMock, return_value={"enqueue_id": "enq-1", "task_type": "diagnostics", "correlation_id": "corr-enq-1"}), \
             patch("api.create_zone_event", new_callable=AsyncMock) as mock_zone_event:
            summary = await api._recover_zone_workflow_states()

        assert summary["active"] == 1
        assert summary["recovered"] == 1
        assert summary["stale_stopped"] == 0
        mock_state_set.assert_awaited_once()
        kwargs = mock_state_set.await_args.kwargs
        assert kwargs["zone_id"] == 1
        assert kwargs["workflow_phase"] == "tank_filling"
        assert kwargs["scheduler_task_id"] == "enq-1"
        event_types = [call.args[1] for call in mock_zone_event.await_args_list]
        assert "WORKFLOW_RECOVERY_ENQUEUED" in event_types
    finally:
        api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = old_enabled
        api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = old_stale_timeout


@pytest.mark.asyncio
async def test_recover_zone_workflow_states_canonicalizes_startup_to_check_phase():
    old_enabled = api._AE_WORKFLOW_STATE_RECOVERY_ENABLED
    old_stale_timeout = api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC
    api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = True
    api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = 1800
    try:
        active_state = {
            "zone_id": 7,
            "workflow_phase": "tank_filling",
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=90),
            "payload": {
                "workflow": "startup",
                "clean_fill_started_at": (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=180)).isoformat(),
                "clean_fill_timeout_at": (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=300)).isoformat(),
                "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}},
            },
            "scheduler_task_id": "st-old-7",
        }
        with patch.object(api._workflow_state_store, "list_active", new_callable=AsyncMock, return_value=[active_state]), \
             patch.object(api._workflow_state_store, "set", new_callable=AsyncMock) as mock_state_set, \
             patch("api.enqueue_internal_scheduler_task", new_callable=AsyncMock, return_value={"enqueue_id": "enq-7", "task_type": "diagnostics", "correlation_id": "corr-enq-7"}) as mock_enqueue, \
             patch("api.create_zone_event", new_callable=AsyncMock):
            summary = await api._recover_zone_workflow_states()

        assert summary["active"] == 1
        assert summary["recovered"] == 1
        assert mock_enqueue.await_count == 1
        enqueue_payload = mock_enqueue.await_args.kwargs["payload"]
        assert enqueue_payload["workflow"] == "clean_fill_check"
        persisted_payload = mock_state_set.await_args.kwargs["payload"]
        assert persisted_payload["workflow"] == "clean_fill_check"
    finally:
        api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = old_enabled
        api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = old_stale_timeout


@pytest.mark.asyncio
async def test_recover_zone_workflow_states_canonicalizes_prepare_recirculation_to_check_phase():
    old_enabled = api._AE_WORKFLOW_STATE_RECOVERY_ENABLED
    old_stale_timeout = api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC
    api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = True
    api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = 1800
    try:
        active_state = {
            "zone_id": 8,
            "workflow_phase": "tank_recirc",
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=120),
            "payload": {
                "workflow": "prepare_recirculation",
                "prepare_recirculation_started_at": (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=300)).isoformat(),
                "prepare_recirculation_timeout_at": (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=300)).isoformat(),
                "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}},
            },
            "scheduler_task_id": "st-old-8",
        }
        with patch.object(api._workflow_state_store, "list_active", new_callable=AsyncMock, return_value=[active_state]), \
             patch.object(api._workflow_state_store, "set", new_callable=AsyncMock) as mock_state_set, \
             patch("api.enqueue_internal_scheduler_task", new_callable=AsyncMock, return_value={"enqueue_id": "enq-8", "task_type": "diagnostics", "correlation_id": "corr-enq-8"}) as mock_enqueue, \
             patch("api.create_zone_event", new_callable=AsyncMock):
            summary = await api._recover_zone_workflow_states()

        assert summary["active"] == 1
        assert summary["recovered"] == 1
        assert mock_enqueue.await_count == 1
        enqueue_payload = mock_enqueue.await_args.kwargs["payload"]
        assert enqueue_payload["workflow"] == "prepare_recirculation_check"
        persisted_payload = mock_state_set.await_args.kwargs["payload"]
        assert persisted_payload["workflow"] == "prepare_recirculation_check"
    finally:
        api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = old_enabled
        api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = old_stale_timeout


@pytest.mark.asyncio
async def test_recover_zone_workflow_states_marks_stale_state_idle():
    old_enabled = api._AE_WORKFLOW_STATE_RECOVERY_ENABLED
    old_stale_timeout = api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC
    api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = True
    api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = 60
    try:
        stale_state = {
            "zone_id": 2,
            "workflow_phase": "tank_recirc",
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=3600),
            "payload": {"workflow": "prepare_recirculation_check"},
            "scheduler_task_id": "st-old-2",
        }
        with patch.object(api._workflow_state_store, "list_active", new_callable=AsyncMock, return_value=[stale_state]), \
             patch.object(api._workflow_state_store, "set", new_callable=AsyncMock) as mock_state_set, \
             patch("api.enqueue_internal_scheduler_task", new_callable=AsyncMock) as mock_enqueue, \
             patch("api.create_zone_event", new_callable=AsyncMock) as mock_zone_event:
            summary = await api._recover_zone_workflow_states()

        assert summary["active"] == 1
        assert summary["recovered"] == 0
        assert summary["stale_stopped"] == 1
        mock_enqueue.assert_not_awaited()
        mock_state_set.assert_awaited_once()
        kwargs = mock_state_set.await_args.kwargs
        assert kwargs["zone_id"] == 2
        assert kwargs["workflow_phase"] == "idle"
        assert kwargs["scheduler_task_id"] is None
        event_types = [call.args[1] for call in mock_zone_event.await_args_list]
        assert "WORKFLOW_RECOVERY_STALE_STOPPED" in event_types
    finally:
        api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = old_enabled
        api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = old_stale_timeout


@pytest.mark.asyncio
async def test_recover_zone_workflow_states_canonicalizes_irrigation_recovery_to_check_phase():
    old_enabled = api._AE_WORKFLOW_STATE_RECOVERY_ENABLED
    old_stale_timeout = api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC
    api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = True
    api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = 1800
    try:
        active_state = {
            "zone_id": 18,
            "workflow_phase": "irrig_recirc",
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=45),
            "payload": {
                "workflow": "irrigation_recovery",
                "irrigation_recovery_started_at": (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=120)).isoformat(),
                "irrigation_recovery_timeout_at": (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=300)).isoformat(),
                "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}},
            },
            "scheduler_task_id": "st-old-18",
        }
        with patch.object(api._workflow_state_store, "list_active", new_callable=AsyncMock, return_value=[active_state]), \
             patch.object(api._workflow_state_store, "set", new_callable=AsyncMock) as mock_state_set, \
             patch("api.enqueue_internal_scheduler_task", new_callable=AsyncMock, return_value={"enqueue_id": "enq-18", "task_type": "diagnostics", "correlation_id": "corr-enq-18"}) as mock_enqueue, \
             patch("api.create_zone_event", new_callable=AsyncMock):
            summary = await api._recover_zone_workflow_states()

        assert summary["active"] == 1
        assert summary["recovered"] == 1
        assert mock_enqueue.await_count == 1
        enqueue_payload = mock_enqueue.await_args.kwargs["payload"]
        assert enqueue_payload["workflow"] == "irrigation_recovery_check"
        assert enqueue_payload["workflow_stage"] == "irrigation_recovery_check"
        persisted_payload = mock_state_set.await_args.kwargs["payload"]
        assert persisted_payload["workflow"] == "irrigation_recovery_check"
    finally:
        api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = old_enabled
        api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = old_stale_timeout


@pytest.mark.asyncio
async def test_recover_zone_workflow_states_missing_workflow_uses_phase_fallback_without_startup_restart():
    old_enabled = api._AE_WORKFLOW_STATE_RECOVERY_ENABLED
    old_stale_timeout = api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC
    api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = True
    api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = 1800
    try:
        active_state = {
            "zone_id": 19,
            "workflow_phase": "tank_filling",
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=70),
            "payload": {
                "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}},
            },
            "scheduler_task_id": "st-old-19",
        }
        with patch.object(api._workflow_state_store, "list_active", new_callable=AsyncMock, return_value=[active_state]), \
             patch.object(api._workflow_state_store, "set", new_callable=AsyncMock), \
             patch("api.enqueue_internal_scheduler_task", new_callable=AsyncMock, return_value={"enqueue_id": "enq-19", "task_type": "diagnostics", "correlation_id": "corr-enq-19"}) as mock_enqueue, \
             patch("api.create_zone_event", new_callable=AsyncMock) as mock_zone_event:
            summary = await api._recover_zone_workflow_states()

        assert summary["active"] == 1
        assert summary["recovered"] == 1
        enqueue_payload = mock_enqueue.await_args.kwargs["payload"]
        assert enqueue_payload["workflow"] == "solution_fill_check"
        assert enqueue_payload["workflow"] != "startup"
        fallback_calls = [call for call in mock_zone_event.await_args_list if call.args[1] == "WORKFLOW_RECOVERY_WORKFLOW_FALLBACK"]
        assert len(fallback_calls) == 1
        fallback_payload = fallback_calls[0].args[2]
        assert fallback_payload["fallback_from"] == "missing_workflow"
        assert fallback_payload["fallback_to"] == "solution_fill_check"
    finally:
        api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = old_enabled
        api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = old_stale_timeout


@pytest.mark.asyncio
async def test_recover_zone_workflow_states_emits_fallback_event_for_incompatible_workflow():
    old_enabled = api._AE_WORKFLOW_STATE_RECOVERY_ENABLED
    old_stale_timeout = api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC
    api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = True
    api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = 1800
    try:
        active_state = {
            "zone_id": 20,
            "workflow_phase": "tank_recirc",
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=50),
            "payload": {
                "workflow": "clean_fill_check",
                "config": {"execution": {"topology": "two_tank_drip_substrate_trays"}},
            },
            "scheduler_task_id": "st-old-20",
        }
        with patch.object(api._workflow_state_store, "list_active", new_callable=AsyncMock, return_value=[active_state]), \
             patch.object(api._workflow_state_store, "set", new_callable=AsyncMock), \
             patch("api.enqueue_internal_scheduler_task", new_callable=AsyncMock, return_value={"enqueue_id": "enq-20", "task_type": "diagnostics", "correlation_id": "corr-enq-20"}) as mock_enqueue, \
             patch("api.create_zone_event", new_callable=AsyncMock) as mock_zone_event:
            summary = await api._recover_zone_workflow_states()

        assert summary["active"] == 1
        assert summary["recovered"] == 1
        enqueue_payload = mock_enqueue.await_args.kwargs["payload"]
        assert enqueue_payload["workflow"] == "prepare_recirculation_check"
        fallback_calls = [call for call in mock_zone_event.await_args_list if call.args[1] == "WORKFLOW_RECOVERY_WORKFLOW_FALLBACK"]
        assert len(fallback_calls) == 1
        fallback_payload = fallback_calls[0].args[2]
        assert fallback_payload["fallback_from"] == "clean_fill_check"
        assert fallback_payload["fallback_to"] == "prepare_recirculation_check"
    finally:
        api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = old_enabled
        api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = old_stale_timeout


@pytest.mark.asyncio
async def test_recover_zone_workflow_states_continues_after_invalid_row_and_logs_structured_actions(caplog):
    old_enabled = api._AE_WORKFLOW_STATE_RECOVERY_ENABLED
    old_stale_timeout = api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC
    api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = True
    api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = 1800
    caplog.set_level(logging.INFO, logger="api")
    try:
        active_states = [
            {
                "zone_id": "invalid-zone",
                "workflow_phase": "tank_filling",
                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=40),
                "payload": {"workflow": "solution_fill_check"},
                "scheduler_task_id": "st-invalid-row",
            },
            {
                "zone_id": 21,
                "workflow_phase": "tank_recirc",
                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=30),
                "payload": {
                    "workflow": "prepare_recirculation_check",
                    "correlation_id": "corr-zone-21",
                },
                "scheduler_task_id": "st-old-21",
            },
        ]
        with patch.object(api._workflow_state_store, "list_active", new_callable=AsyncMock, return_value=active_states), \
             patch.object(api._workflow_state_store, "set", new_callable=AsyncMock), \
             patch("api.enqueue_internal_scheduler_task", new_callable=AsyncMock, return_value={"enqueue_id": "enq-21", "task_type": "diagnostics", "correlation_id": "corr-enq-21"}) as mock_enqueue, \
             patch("api.create_zone_event", new_callable=AsyncMock):
            summary = await api._recover_zone_workflow_states()

        assert summary["active"] == 2
        assert summary["recovered"] == 1
        assert summary["skipped"] == 1
        assert summary["failed"] == 0
        mock_enqueue.assert_awaited_once()
        assert mock_enqueue.await_args.kwargs["zone_id"] == 21

        recovery_records = [record for record in caplog.records if getattr(record, "component", None) == "workflow_state_recovery"]
        assert any(
            getattr(record, "recovery_action", None) == "skip_invalid"
            and getattr(record, "reason_code", None) == "invalid_zone_id"
            for record in recovery_records
        )
        assert any(
            getattr(record, "recovery_action", None) == "enqueue_continuation"
            and getattr(record, "zone_id", None) == 21
            and getattr(record, "workflow_selected", None) == "prepare_recirculation_check"
            for record in recovery_records
        )
    finally:
        api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = old_enabled
        api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = old_stale_timeout


@pytest.mark.asyncio
async def test_recover_zone_workflow_states_continues_when_alert_publish_fails():
    old_enabled = api._AE_WORKFLOW_STATE_RECOVERY_ENABLED
    old_stale_timeout = api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC
    api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = True
    api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = 1800
    try:
        active_states = [
            {
                "zone_id": 31,
                "workflow_phase": "tank_recirc",
                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=30),
                "payload": {"workflow": "prepare_recirculation_check"},
                "scheduler_task_id": "st-old-31",
            },
            {
                "zone_id": 32,
                "workflow_phase": "tank_recirc",
                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=25),
                "payload": {"workflow": "prepare_recirculation_check"},
                "scheduler_task_id": "st-old-32",
            },
        ]
        enqueue_results = [
            RuntimeError("enqueue unavailable"),
            {"enqueue_id": "enq-32", "task_type": "diagnostics", "correlation_id": "corr-enq-32"},
        ]

        with patch.object(api._workflow_state_store, "list_active", new_callable=AsyncMock, return_value=active_states), \
             patch.object(api._workflow_state_store, "set", new_callable=AsyncMock), \
             patch("api.enqueue_internal_scheduler_task", new_callable=AsyncMock, side_effect=enqueue_results) as mock_enqueue, \
             patch("api.send_infra_exception_alert", new_callable=AsyncMock, side_effect=RuntimeError("alert unavailable")), \
             patch("api.create_zone_event", new_callable=AsyncMock):
            summary = await api._recover_zone_workflow_states()

        assert summary["active"] == 2
        assert summary["failed"] == 1
        assert summary["recovered"] == 1
        assert mock_enqueue.await_count == 2
        assert mock_enqueue.await_args_list[1].kwargs["zone_id"] == 32
    finally:
        api._AE_WORKFLOW_STATE_RECOVERY_ENABLED = old_enabled
        api._AE_WORKFLOW_STATE_STALE_TIMEOUT_SEC = old_stale_timeout


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
                "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "updated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
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


def test_test_hook_set_state_accepts_workflow_phase_override(client):
    """set_state должен принимать workflow_phase override для fail-closed тестов."""
    old_mode = api._test_mode
    old_states = dict(api._zone_states_override)
    try:
        api._test_mode = True
        api._zone_states_override.clear()

        response = client.post("/test/hook", json={
            "zone_id": 14,
            "action": "set_state",
            "state": {
                "error_streak": 0,
                "workflow_phase": "tank_filling",
            },
        })
        assert response.status_code == 200

        state = api._zone_states_override[14]
        assert state["workflow_phase"] == "tank_filling"
        assert state["workflow_phase_loaded"] is True
        assert state["workflow_phase_source"] == "test_hook"
        assert isinstance(state["workflow_phase_updated_at"], datetime)
    finally:
        api._test_mode = old_mode
        api._zone_states_override.clear()
        api._zone_states_override.update(old_states)


def test_test_hook_set_state_rejects_unknown_workflow_phase(client):
    """set_state должен валидировать workflow_phase и отклонять неизвестные значения."""
    old_mode = api._test_mode
    old_states = dict(api._zone_states_override)
    try:
        api._test_mode = True
        api._zone_states_override.clear()

        response = client.post("/test/hook", json={
            "zone_id": 15,
            "action": "set_state",
            "state": {
                "workflow_phase": "unknown_phase",
            },
        })
        assert response.status_code == 400
        assert "workflow_phase" in response.json()["detail"]
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
