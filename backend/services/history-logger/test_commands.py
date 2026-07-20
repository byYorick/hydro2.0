"""Tests for history-logger command endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, Mock
from app import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create auth headers for testing."""
    return {"Authorization": "Bearer dev-token-12345"}


@pytest.fixture(autouse=True)
def auth_settings():
    """Ensure auth uses a stable test token unless overridden."""
    with patch("auth.get_settings") as mock_settings:
        mock_settings.return_value = Mock(history_logger_api_token="dev-token-12345")
        yield mock_settings


@pytest.fixture
def mock_mqtt_client():
    """Create mock MQTT client with proper structure."""
    mqtt = Mock()
    mqtt.is_connected = Mock(return_value=True)
    
    # Создаем правильную структуру для mqtt_client._client._client.publish()
    publish_result = Mock()
    publish_result.rc = 0  # 0 означает успех в paho-mqtt
    
    base_client = Mock()
    base_client._client = Mock()
    base_client._client.publish = Mock(return_value=publish_result)
    
    mqtt._client = base_client
    return mqtt


@pytest.fixture(autouse=True)
def mock_command_routes_db():
    """Mock DB calls used by command endpoints to keep tests deterministic."""
    async def _mock_fetch(query, *args):
        normalized = " ".join(str(query).split()).lower()

        if "select status from commands where cmd_id = $1" in normalized:
            return [{"status": "SENT"}]

        if "from nodes where uid = $1" in normalized and "zone_id = $2" not in normalized:
            node_uid = args[0]
            if node_uid in {"nd-irrig-1", "nd-relay-1", "nd-test"}:
                return [{"id": 1, "zone_id": 1, "pending_zone_id": None}]
            if node_uid == "nd-pending-1":
                return [{"id": 2, "zone_id": None, "pending_zone_id": 1}]
            if node_uid == "nd-other-zone":
                return [{"id": 3, "zone_id": 2, "pending_zone_id": None}]
            return []

        if "from nodes where uid = $1 and zone_id = $2" in normalized:
            node_uid, zone_id = args
            if node_uid in {"nd-irrig-1", "nd-relay-1", "nd-test"} and int(zone_id) == 1:
                return [{"id": 1}]
            return []

        if "from commands where cmd_id = $1" in normalized:
            return []

        return []

    with patch("command_routes.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("command_routes.execute", new_callable=AsyncMock) as mock_execute, \
         patch("command_routes.mark_command_sent", new_callable=AsyncMock) as mock_mark_command_sent, \
         patch("command_routes.mark_command_send_failed", new_callable=AsyncMock) as mock_mark_command_send_failed, \
         patch("command_routes._get_gh_uid_from_zone_id", new_callable=AsyncMock) as mock_get_gh_uid, \
         patch(
             "command_service.fetch",
             new_callable=AsyncMock,
             return_value=[{"node_secret": "a" * 64}],
         ):
        mock_fetch.side_effect = _mock_fetch
        mock_execute.return_value = "OK"
        mock_mark_command_sent.return_value = True
        mock_mark_command_send_failed.return_value = None
        mock_get_gh_uid.return_value = "gh-1"
        yield


@pytest.mark.asyncio
async def test_resolve_node_secret_reads_per_node_secret_from_db():
    from command_service import _resolve_node_secret

    per_node_secret = "b" * 64
    with patch(
        "command_service.fetch",
        new_callable=AsyncMock,
        return_value=[{"node_secret": per_node_secret}],
    ) as mock_fetch:
        resolved = await _resolve_node_secret(node_uid="nd-irrig-1", node_id=7)

    assert resolved == per_node_secret
    query, node_id, node_uid = mock_fetch.await_args.args
    assert "config->>'node_secret'" in query
    assert node_id == 7
    assert node_uid == "nd-irrig-1"


@pytest.mark.asyncio
async def test_resolve_node_secret_preserves_raw_secret_without_strip():
    """Laravel NodeSecretService returns raw secret; HL must not strip whitespace."""
    from command_service import _resolve_node_secret

    raw_secret = "  " + ("ab" * 32) + "  "
    with patch(
        "command_service.fetch",
        new_callable=AsyncMock,
        return_value=[{"node_secret": raw_secret}],
    ):
        resolved = await _resolve_node_secret(node_uid="nd-irrig-1", node_id=7)

    assert resolved == raw_secret


@pytest.mark.asyncio
async def test_resolve_node_secret_with_zone_id_checks_assignment_in_one_query():
    from command_service import NodeSecretResolutionError, _resolve_node_secret

    per_node_secret = "c" * 64
    with patch(
        "command_service.fetch",
        new_callable=AsyncMock,
        return_value=[{"node_secret": per_node_secret}],
    ) as mock_fetch:
        resolved = await _resolve_node_secret(
            node_uid="nd-irrig-1",
            node_id=7,
            zone_id=42,
        )

    assert resolved == per_node_secret
    query, node_id, node_uid, zone_id = mock_fetch.await_args.args
    assert "zone_id = $3" in query
    assert node_id == 7
    assert node_uid == "nd-irrig-1"
    assert zone_id == 42

    with patch(
        "command_service.fetch",
        new_callable=AsyncMock,
        return_value=[],
    ):
        with pytest.raises(NodeSecretResolutionError, match="not assigned to zone"):
            await _resolve_node_secret(node_uid="nd-irrig-1", node_id=7, zone_id=99)


@pytest.mark.asyncio
async def test_resolve_node_secret_fails_closed_in_production(monkeypatch):
    from command_service import NodeSecretResolutionError, _resolve_node_secret

    monkeypatch.setenv("APP_ENV", "production")
    with patch(
        "command_service.fetch",
        new_callable=AsyncMock,
        return_value=[{"node_secret": None}],
    ), patch("command_service.get_settings") as mock_settings:
        with pytest.raises(NodeSecretResolutionError, match="not configured"):
            await _resolve_node_secret(node_uid="nd-irrig-1", node_id=7)

    mock_settings.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_node_secret_uses_default_only_outside_production(
    monkeypatch, caplog
):
    from command_service import _resolve_node_secret

    monkeypatch.setenv("APP_ENV", "local")
    with patch(
        "command_service.fetch",
        new_callable=AsyncMock,
        return_value=[{"node_secret": None}],
    ), patch("command_service.get_settings") as mock_settings:
        mock_settings.return_value = Mock(node_default_secret="dev-default-secret")
        resolved = await _resolve_node_secret(node_uid="nd-irrig-1", node_id=7)

    assert resolved == "dev-default-secret"
    assert "Using NODE_DEFAULT_SECRET fallback" in caplog.text


def test_create_command_payload_resigns_with_explicit_per_node_secret(caplog):
    import hashlib
    import hmac

    from command_service import _create_command_payload
    from common.hmac_utils import canonical_json_payload

    secret = "c" * 64
    unsigned_payload = {
        "cmd": "run_pump",
        "cmd_id": "cmd-per-node-secret",
        "params": {"duration_ms": 1000},
        "ts": 1737979200,
    }

    with patch("command_service.time.time", return_value=1737979200):
        payload = _create_command_payload(
            node_uid="nd-irrig-1",
            secret=secret,
            cmd=unsigned_payload["cmd"],
            cmd_id=unsigned_payload["cmd_id"],
            params=unsigned_payload["params"],
            ts=unsigned_payload["ts"],
            sig="caller-supplied-signature",
        )

    expected_sig = hmac.new(
        secret.encode(),
        canonical_json_payload(unsigned_payload).encode(),
        hashlib.sha256,
    ).hexdigest()
    assert payload["sig"] == expected_sig
    assert payload["sig"] != "caller-supplied-signature"
    assert "Ignoring caller-provided command signature" in caplog.text


@pytest.mark.asyncio
async def test_ensure_command_for_publish_handles_unique_violation_race():
    """Concurrent insert race by cmd_id must not end as 503 error."""
    import asyncpg
    from command_routes import _ensure_command_for_publish

    calls = {"commands_fetch": 0}

    async def _fetch(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from commands where cmd_id = $1" in normalized:
            if calls["commands_fetch"] == 0:
                calls["commands_fetch"] += 1
                return []
            return [{
                "status": "SENT",
                "source": "automation",
                "zone_id": 1,
                "node_id": 1,
                "channel": "default",
                "cmd": "run_pump",
                "params": {"duration_ms": 1000},
            }]
        return []

    async def _execute(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "insert into commands" in normalized:
            raise asyncpg.UniqueViolationError("duplicate key value violates unique constraint")
        return "OK"

    with patch("command_routes.fetch", new=AsyncMock(side_effect=_fetch)), \
         patch("command_routes.execute", new=AsyncMock(side_effect=_execute)):
        response = await _ensure_command_for_publish(
            cmd_id="cmd-race-1",
            zone_id=1,
            node_id=1,
            node_uid="nd-irrig-1",
            channel="default",
            cmd_name="run_pump",
            params={"duration_ms": 1000},
            command_source="automation",
        )

    assert response is not None
    assert response["status"] == "ok"
    assert response["data"]["command_id"] == "cmd-race-1"


@pytest.mark.asyncio
async def test_ensure_command_for_publish_rejects_cmd_id_with_different_params():
    from fastapi import HTTPException
    from command_routes import _ensure_command_for_publish

    async def _fetch(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from commands where cmd_id = $1" in normalized:
            return [{
                "status": "QUEUED",
                "source": "automation",
                "zone_id": 1,
                "node_id": 1,
                "channel": "default",
                "cmd": "run_pump",
                "params": {"duration_ms": 1000},
            }]
        return []

    with patch("command_routes.fetch", new=AsyncMock(side_effect=_fetch)), \
         patch("command_routes.execute", new=AsyncMock(return_value="OK")):
        with pytest.raises(HTTPException) as exc_info:
            await _ensure_command_for_publish(
                cmd_id="cmd-same-id",
                zone_id=1,
                node_id=1,
                node_uid="nd-irrig-1",
                channel="default",
                cmd_name="run_pump",
                params={"duration_ms": 2000},
                command_source="automation",
            )

    assert exc_info.value.status_code == 409
    assert "params" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_ensure_command_for_publish_allows_empty_params_shape_compat():
    from command_routes import _ensure_command_for_publish

    async def _fetch(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from commands where cmd_id = $1" in normalized:
            return [{
                "status": "QUEUED",
                "source": "automation",
                "zone_id": 1,
                "node_id": 1,
                "channel": "default",
                "cmd": "run_pump",
                "params": [],
            }]
        return []

    with patch("command_routes.fetch", new=AsyncMock(side_effect=_fetch)), \
         patch("command_routes.execute", new=AsyncMock(return_value="OK")):
        response = await _ensure_command_for_publish(
            cmd_id="cmd-empty-shape-compat",
            zone_id=1,
            node_id=1,
            node_uid="nd-irrig-1",
            channel="default",
            cmd_name="run_pump",
            params={},
            command_source="automation",
        )

    assert response is None


@pytest.mark.asyncio
async def test_ensure_command_for_publish_allows_device_ack_stub_without_sent_at():
    """C3: device ACK stub without sent_at must not block MQTT publish."""
    from command_routes import _ensure_command_for_publish

    async def _fetch(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from commands where cmd_id = $1" in normalized:
            return [{
                "status": "ACK",
                "source": "device",
                "sent_at": None,
                "zone_id": 1,
                "node_id": 1,
                "channel": "default",
                "cmd": "run_pump",
                "params": {"duration_ms": 1000},
            }]
        return []

    with patch("command_routes.fetch", new=AsyncMock(side_effect=_fetch)), \
         patch("command_routes.execute", new=AsyncMock(return_value="OK")):
        response = await _ensure_command_for_publish(
            cmd_id="cmd-ack-stub",
            zone_id=1,
            node_id=1,
            node_uid="nd-irrig-1",
            channel="default",
            cmd_name="run_pump",
            params={"duration_ms": 1000},
            command_source="automation",
        )

    assert response is None


@pytest.mark.asyncio
async def test_ensure_command_for_publish_skips_real_ack_with_sent_at():
    from command_routes import _ensure_command_for_publish

    async def _fetch(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from commands where cmd_id = $1" in normalized:
            return [{
                "status": "ACK",
                "source": "device",
                "sent_at": "2026-01-01T00:00:00",
                "zone_id": 1,
                "node_id": 1,
                "channel": "default",
                "cmd": "run_pump",
                "params": {"duration_ms": 1000},
            }]
        return []

    with patch("command_routes.fetch", new=AsyncMock(side_effect=_fetch)), \
         patch("command_routes.execute", new=AsyncMock(return_value="OK")):
        response = await _ensure_command_for_publish(
            cmd_id="cmd-real-ack",
            zone_id=1,
            node_id=1,
            node_uid="nd-irrig-1",
            channel="default",
            cmd_name="run_pump",
            params={"duration_ms": 1000},
            command_source="automation",
        )

    assert response is not None
    assert response["data"]["skipped"] is True


@pytest.mark.asyncio
async def test_mark_command_sent_idempotent_when_ack_already_has_sent_at():
    """ACK + sent_at после publish — идемпотентный success, не MarkCommandSentError."""
    from common.commands import mark_command_sent

    with patch("common.commands.execute", new=AsyncMock(return_value="UPDATE 0")), \
         patch(
             "common.commands.fetch",
             new=AsyncMock(return_value=[{"status": "ACK", "sent_at": "2026-01-01"}]),
         ):
        assert await mark_command_sent("cmd-ack") is True


@pytest.mark.asyncio
async def test_mark_command_sent_fail_closed_on_unknown_status():
    from common.commands import MarkCommandSentError, mark_command_sent

    with patch("common.commands.execute", new=AsyncMock(return_value="UPDATE 0")), \
         patch(
             "common.commands.fetch",
             new=AsyncMock(return_value=[{"status": "RUNNING", "sent_at": None}]),
         ):
        with pytest.raises(MarkCommandSentError):
            await mark_command_sent("cmd-fail")


@pytest.mark.asyncio
async def test_mark_command_sent_idempotent_when_already_sent():
    from common.commands import mark_command_sent

    with patch("common.commands.execute", new=AsyncMock(return_value="UPDATE 0")), \
         patch(
             "common.commands.fetch",
             new=AsyncMock(return_value=[{"status": "SENT", "sent_at": "2026-01-01"}]),
         ):
        assert await mark_command_sent("cmd-sent") is True


@pytest.mark.asyncio
async def test_drain_preserves_signed_payload_metadata():
    from commands.drain import _extract_signed_payload_fields

    params, ts, sig = _extract_signed_payload_fields(
        {"duration_ms": 1000, "__hl_ts": 1737979200, "__hl_sig": "abc123"}
    )

    assert params == {"duration_ms": 1000}
    assert ts == 1737979200
    assert sig == "abc123"


@pytest.mark.asyncio
async def test_drain_abandons_send_failed_with_null_zone_id():
    """Null zone_id rows must leave QUEUED/SEND_FAILED, not keep failing drain cycles."""
    from commands.drain import drain_stale_queued_commands_once

    claim_row = {
        "cmd_id": "6d1032d6-dd37-44bd-840a-911822b0df34",
        "zone_id": None,
        "node_id": 2,
        "channel": "system",
        "cmd": "reset_binding",
        "params": {},
        "status": "SEND_FAILED",
        "source": None,
        "node_uid": "nd-test-ph-1",
    }

    with patch(
        "commands.drain._claim_stale_queued_command_rows",
        new_callable=AsyncMock,
        return_value=[claim_row],
    ), patch(
        "commands.drain._abandon_non_republishable_command",
        new_callable=AsyncMock,
        return_value=True,
    ) as abandon:
        summary = await drain_stale_queued_commands_once(stale_after_seconds=0, limit=10)

    abandon.assert_awaited_once()
    assert abandon.await_args.kwargs["reason"] == "missing_required_publish_fields"
    assert summary == {"scanned": 1, "drained": 0, "skipped": 1, "failed": 0}


@pytest.mark.asyncio
async def test_drain_skips_when_publish_claim_busy():
    """Concurrent drain must not double-publish: busy advisory claim → skip."""
    from contextlib import asynccontextmanager

    from commands.drain import drain_stale_queued_commands_once

    claim_row = {
        "cmd_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "zone_id": 1,
        "node_id": 2,
        "channel": "pump",
        "cmd": "run_pump",
        "params": {"duration_ms": 1000},
        "status": "QUEUED",
        "source": "api",
        "node_uid": "nd-irrig-1",
    }

    @asynccontextmanager
    async def _busy_claim(_cmd_id: str):
        yield False

    with patch(
        "commands.drain._claim_stale_queued_command_rows",
        new_callable=AsyncMock,
        return_value=[claim_row],
    ), patch(
        "commands.drain._try_claim_cmd_for_publish",
        new=_busy_claim,
    ), patch(
        "commands.drain.publish_command_with_retry",
        new_callable=AsyncMock,
    ) as publish:
        summary = await drain_stale_queued_commands_once(stale_after_seconds=0, limit=10)

    publish.assert_not_awaited()
    assert summary == {"scanned": 1, "drained": 0, "skipped": 1, "failed": 0}


@pytest.mark.asyncio
async def test_drain_republish_holds_claim_and_passes_zone_to_secret():
    """Successful drain resolves secret with zone_id under an active publish claim."""
    from contextlib import asynccontextmanager

    from commands.drain import drain_stale_queued_commands_once

    claim_row = {
        "cmd_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        "zone_id": 7,
        "node_id": 3,
        "channel": "pump",
        "cmd": "run_pump",
        "params": {"duration_ms": 500, "__hl_ts": 1737979200, "__hl_sig": "sig"},
        "status": "QUEUED",
        "source": "api",
        "node_uid": "nd-irrig-1",
    }

    @asynccontextmanager
    async def _ok_claim(_cmd_id: str):
        yield True

    with patch(
        "commands.drain._claim_stale_queued_command_rows",
        new_callable=AsyncMock,
        return_value=[claim_row],
    ), patch(
        "commands.drain._try_claim_cmd_for_publish",
        new=_ok_claim,
    ), patch(
        "commands.drain.ensure_command_for_publish",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "commands.drain._get_gh_uid_from_zone_id",
        new_callable=AsyncMock,
        return_value="gh-1",
    ), patch(
        "commands.drain._get_zone_uid_from_id",
        new_callable=AsyncMock,
        return_value="zn-7",
    ), patch(
        "commands.drain._resolve_node_secret",
        new_callable=AsyncMock,
        return_value="d" * 64,
    ) as resolve_secret, patch(
        "commands.drain._create_command_payload",
        return_value={"cmd_id": claim_row["cmd_id"], "cmd": "run_pump"},
    ), patch(
        "commands.drain.publish_command_with_retry",
        new_callable=AsyncMock,
        return_value={"status": "ok"},
    ) as publish:
        summary = await drain_stale_queued_commands_once(stale_after_seconds=0, limit=10)

    resolve_secret.assert_awaited_once_with(
        node_uid="nd-irrig-1",
        node_id=3,
        zone_id=7,
    )
    publish.assert_awaited_once()
    assert summary == {"scanned": 1, "drained": 1, "skipped": 0, "failed": 0}


def test_cmd_publish_advisory_lock_key_is_stable():
    from commands.drain import _cmd_publish_advisory_lock_key

    key_a = _cmd_publish_advisory_lock_key("cmd-stable-1")
    key_b = _cmd_publish_advisory_lock_key("cmd-stable-1")
    key_c = _cmd_publish_advisory_lock_key("cmd-stable-2")
    assert key_a == key_b
    assert key_a != key_c
    assert 0 <= key_a <= 0x7FFFFFFFFFFFFFFF


@pytest.mark.asyncio
async def test_publish_command_success(client, auth_headers, mock_mqtt_client):
    """Test successful command publication via /commands endpoint."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000}
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "command_id" in data["data"]
        
        # Проверяем, что команда была опубликована в MQTT
        # Структура: mqtt_client._client._client.publish()
        assert mock_mqtt_client._client._client.publish.called


@pytest.mark.asyncio
async def test_publish_command_does_not_publish_without_per_node_secret_in_production(
    client, auth_headers, mock_mqtt_client, monkeypatch
):
    monkeypatch.setenv("APP_ENV", "production")
    with patch(
        "command_routes.get_mqtt_client", new_callable=AsyncMock
    ) as mock_get_mqtt, patch("command_routes.get_settings") as mock_settings, patch(
        "command_service.fetch",
        new_callable=AsyncMock,
        return_value=[{"node_secret": None}],
    ):
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")

        response = client.post(
            "/commands",
            json={
                "cmd": "run_pump",
                "greenhouse_uid": "gh-1",
                "zone_id": 1,
                "node_uid": "nd-irrig-1",
                "channel": "default",
                "params": {"duration_ms": 1000},
            },
            headers=auth_headers,
        )

    assert response.status_code == 503
    assert "Per-node command signing secret is not configured" in response.json()["detail"]
    assert not mock_mqtt_client._client._client.publish.called


@pytest.mark.asyncio
async def test_publish_command_returns_500_when_sent_status_not_persisted(client, auth_headers, mock_mqtt_client):
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings, \
         patch("command_routes.mark_command_sent", new_callable=AsyncMock, side_effect=RuntimeError("db write failed")):
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")

        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000},
        }

        response = client.post("/commands", json=payload, headers=auth_headers)

    assert response.status_code == 500
    assert response.json()["detail"] == "published_but_status_not_persisted"


@pytest.mark.asyncio
async def test_publish_command_rejects_node_zone_mismatch(client, auth_headers, mock_mqtt_client):
    """Command must be rejected if node belongs to another zone."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings, \
         patch("command_routes.send_infra_alert", new_callable=AsyncMock) as mock_send_infra_alert, \
         patch("command_routes.create_zone_event", new_callable=AsyncMock) as mock_create_zone_event:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        mock_send_infra_alert.return_value = True

        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-other-zone",
            "channel": "default",
            "params": {"duration_ms": 60000}
        }

        response = client.post("/commands", json=payload, headers=auth_headers)

        assert response.status_code == 409
        assert "assigned to zone 2" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called
        mock_send_infra_alert.assert_awaited_once()
        mock_create_zone_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_command_rejects_pending_assignment(client, auth_headers, mock_mqtt_client):
    """Command must be rejected until pending assignment is confirmed."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")

        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-pending-1",
            "channel": "default",
            "params": {"duration_ms": 60000}
        }

        response = client.post("/commands", json=payload, headers=auth_headers)

        assert response.status_code == 409
        assert "pending assignment confirmation" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called


@pytest.mark.asyncio
async def test_publish_command_legacy_type(client, auth_headers, mock_mqtt_client):
    """Test command publication rejects legacy 'type' even when 'cmd' is present."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "type": "run_pump",  # Legacy format
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000}
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)

        assert response.status_code == 400
        assert "Legacy field 'type'" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_command_missing_fields(client, auth_headers):
    """Test command publication with missing required fields."""
    # Missing greenhouse_uid
    payload = {
        "cmd": "run_pump",
        "zone_id": 1,
        "node_uid": "nd-irrig-1",
        "channel": "default"
    }
    
    response = client.post("/commands", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "greenhouse_uid" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_command_missing_cmd(client, auth_headers):
    """Test command publication without cmd or type."""
    payload = {
        "greenhouse_uid": "gh-1",
        "zone_id": 1,
        "node_uid": "nd-irrig-1",
        "channel": "default"
    }
    
    response = client.post("/commands", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "cmd" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_command_unauthorized(client, mock_mqtt_client):
    """Test command publication without authentication."""
    import os
    original_env = os.environ.get("APP_ENV")
    
    try:
        # Устанавливаем production окружение для проверки авторизации
        os.environ["APP_ENV"] = "production"
        
        with patch("auth.get_settings") as mock_auth_settings, \
             patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
             patch("command_routes.get_settings") as mock_settings:
            
            mock_auth_settings.return_value = Mock(history_logger_api_token="required-token")
            mock_get_mqtt.return_value = mock_mqtt_client
            mock_settings.return_value = Mock(mqtt_zone_format="id")
            
            payload = {
                "cmd": "run_pump",
                "greenhouse_uid": "gh-1",
                "zone_id": 1,
                "node_uid": "nd-irrig-1",
                "channel": "default"
            }
            
            response = client.post("/commands", json=payload)
            assert response.status_code == 401
    finally:
        # Восстанавливаем окружение
        if original_env:
            os.environ["APP_ENV"] = original_env
        elif "APP_ENV" in os.environ:
            del os.environ["APP_ENV"]


@pytest.mark.asyncio
async def test_publish_zone_command_unauthorized_in_production(client, mock_mqtt_client):
    """Zone command endpoint must require token in production."""
    import os
    original_env = os.environ.get("APP_ENV")

    try:
        os.environ["APP_ENV"] = "production"
        with patch("auth.get_settings") as mock_auth_settings, \
             patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
             patch("command_routes.get_settings") as mock_settings:
            mock_auth_settings.return_value = Mock(history_logger_api_token="required-token")
            mock_get_mqtt.return_value = mock_mqtt_client
            mock_settings.return_value = Mock(mqtt_zone_format="id")

            payload = {
                "cmd": "run_pump",
                "greenhouse_uid": "gh-1",
                "node_uid": "nd-irrig-1",
                "channel": "default",
                "params": {"duration_ms": 1000},
            }
            response = client.post("/zones/1/commands", json=payload)
            assert response.status_code == 401
    finally:
        if original_env:
            os.environ["APP_ENV"] = original_env
        elif "APP_ENV" in os.environ:
            del os.environ["APP_ENV"]


@pytest.mark.asyncio
async def test_publish_node_command_unauthorized_in_production(client, mock_mqtt_client):
    """Node command endpoint must require token in production."""
    import os
    original_env = os.environ.get("APP_ENV")

    try:
        os.environ["APP_ENV"] = "production"
        with patch("auth.get_settings") as mock_auth_settings, \
             patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
             patch("command_routes.get_settings") as mock_settings:
            mock_auth_settings.return_value = Mock(history_logger_api_token="required-token")
            mock_get_mqtt.return_value = mock_mqtt_client
            mock_settings.return_value = Mock(mqtt_zone_format="id")

            payload = {
                "cmd": "run_pump",
                "greenhouse_uid": "gh-1",
                "zone_id": 1,
                "channel": "default",
                "params": {"duration_ms": 1000},
            }
            response = client.post("/nodes/nd-irrig-1/commands", json=payload)
            assert response.status_code == 401
    finally:
        if original_env:
            os.environ["APP_ENV"] = original_env
        elif "APP_ENV" in os.environ:
            del os.environ["APP_ENV"]


@pytest.mark.asyncio
async def test_publish_zone_command_success(client, auth_headers, mock_mqtt_client):
    """Test successful command publication via /zones/{zone_id}/commands endpoint."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000}
        }
        
        response = client.post("/zones/1/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "command_id" in data["data"]


@pytest.mark.asyncio
async def test_publish_zone_command_missing_fields(client, auth_headers):
    """Test zone command publication with missing fields."""
    payload = {
        "cmd": "run_pump",
        "greenhouse_uid": "gh-1",
        # Missing node_uid and channel
    }
    
    response = client.post("/zones/1/commands", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "node_uid" in response.json()["detail"] or "channel" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_zone_command_rejects_legacy_type(client, auth_headers, mock_mqtt_client):
    """Zone command endpoint must reject legacy 'type' alias."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "type": "run_pump",
            "greenhouse_uid": "gh-1",
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000}
        }
        
        response = client.post("/zones/1/commands", json=payload, headers=auth_headers)

        assert response.status_code == 400
        assert "Legacy field 'type'" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called


@pytest.mark.asyncio
async def test_publish_node_command_success(client, auth_headers, mock_mqtt_client):
    """Test successful command publication via /nodes/{node_uid}/commands endpoint."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "channel": "default",
            "params": {"duration_ms": 60000}
        }
        
        response = client.post("/nodes/nd-irrig-1/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "command_id" in data["data"]


@pytest.mark.asyncio
async def test_publish_node_command_missing_fields(client, auth_headers):
    """Test node command publication with missing fields."""
    payload = {
        "cmd": "run_pump",
        "greenhouse_uid": "gh-1",
        # Missing zone_id and channel
    }
    
    response = client.post("/nodes/nd-irrig-1/commands", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "zone_id" in response.json()["detail"] or "channel" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_node_command_rejects_legacy_type(client, auth_headers, mock_mqtt_client):
    """Node command endpoint must reject legacy 'type' alias."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "type": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "channel": "default",
            "params": {"duration_ms": 60000}
        }
        
        response = client.post("/nodes/nd-irrig-1/commands", json=payload, headers=auth_headers)

        assert response.status_code == 400
        assert "Legacy field 'type'" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called


@pytest.mark.asyncio
async def test_publish_node_config_missing_zone_id(client, auth_headers):
    """Config publish требует zone_id."""
    payload = {
        "greenhouse_uid": "gh-1",
        "zone_uid": "zn-1",
        "config": {"version": 1},
    }

    response = client.post("/nodes/nd-test/config", json=payload, headers=auth_headers)

    assert response.status_code == 400
    assert "zone_id" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_node_config_success(client, auth_headers, mock_mqtt_client):
    """Config publish использует только параметры теплица/зона."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_service.get_settings") as mock_settings, \
         patch("command_routes.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("command_routes._get_gh_uid_from_zone_id", new_callable=AsyncMock) as mock_get_gh_uid:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="uid")
        mock_fetch.return_value = [
            {"id": 1, "zone_id": 1, "pending_zone_id": None, "hardware_id": "esp32-test"}
        ]
        mock_get_gh_uid.return_value = "gh-canonical"

        payload = {
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "zone_uid": "zn-1",
            "config": {"version": 1},
        }

        response = client.post("/nodes/nd-test/config", json=payload, headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["data"]["greenhouse_uid"] == "gh-canonical"
        assert data["data"]["zone_uid"] == "zn-1"
        assert mock_mqtt_client._client._client.publish.called
        publish_call = mock_mqtt_client._client._client.publish.call_args
        assert publish_call.args[0] == "hydro/gh-canonical/zn-1/nd-test/config"


@pytest.mark.asyncio
async def test_publish_node_config_temp_topic(client, auth_headers, mock_mqtt_client):
    """Config publish в temp-топик при pending_zone_id."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_service.get_settings") as mock_settings, \
         patch("command_routes.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("command_routes._get_gh_uid_from_zone_id", new_callable=AsyncMock) as mock_get_gh_uid:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="uid")
        mock_fetch.return_value = [
            {"id": 1, "zone_id": None, "pending_zone_id": 1, "hardware_id": "esp32-temp"}
        ]
        mock_get_gh_uid.return_value = "gh-canonical"

        payload = {
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "zone_uid": "zn-1",
            "config": {"version": 1},
        }

        response = client.post("/nodes/nd-test/config", json=payload, headers=auth_headers)

        assert response.status_code == 200
        publish_call = mock_mqtt_client._client._client.publish.call_args
        assert publish_call.args[0] == "hydro/gh-temp/zn-temp/esp32-temp/config"


@pytest.mark.asyncio
async def test_publish_node_config_rejects_inconsistent_binding_state(client, auth_headers, mock_mqtt_client):
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_service.get_settings") as mock_settings, \
         patch("command_routes.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("command_routes._get_gh_uid_from_zone_id", new_callable=AsyncMock) as mock_get_gh_uid:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="uid")
        mock_fetch.return_value = [
            {"id": 1, "zone_id": 1, "pending_zone_id": 1, "hardware_id": "esp32-bad"}
        ]
        mock_get_gh_uid.return_value = "gh-canonical"

        payload = {
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "zone_uid": "zn-1",
            "config": {"version": 1},
        }

        response = client.post("/nodes/nd-test/config", json=payload, headers=auth_headers)

        assert response.status_code == 409
        assert "inconsistent node binding state" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called


@pytest.mark.asyncio
async def test_publish_command_with_trace_id(client, auth_headers, mock_mqtt_client):
    """Test command publication with trace_id."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "trace_id": "trace-123"
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_publish_command_with_cmd_id(client, auth_headers, mock_mqtt_client):
    """Test command publication with custom cmd_id."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        
        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "cmd_id": "custom-cmd-id-123"
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["data"]["command_id"] == "custom-cmd-id-123"


@pytest.mark.asyncio
async def test_publish_command_mqtt_error(client, auth_headers, mock_mqtt_client):
    """Test command publication when MQTT publish fails."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings, \
         patch("command_routes.publish_command_mqtt", new_callable=AsyncMock) as mock_publish:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        mock_publish.side_effect = Exception("MQTT publish failed")
        
        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default"
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 500
        assert "Failed to publish command" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_command_zone_uid_format(client, auth_headers, mock_mqtt_client):
    """Test command publication with mqtt_zone_format='uid'."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings, \
         patch("command_routes._get_zone_uid_from_id", new_callable=AsyncMock) as mock_get_uid:
        
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="uid")
        mock_get_uid.return_value = "zn-1"
        
        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default"
        }
        
        response = client.post("/commands", json=payload, headers=auth_headers)
        
        assert response.status_code == 200
        # Проверяем, что zone_uid был получен из БД
        mock_get_uid.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_publish_command_zone_uid_format_fails_closed_when_zone_uid_unresolved(
    client, auth_headers, mock_mqtt_client
):
    """UID-format публикация должна fail-closed завершаться до MQTT, если zone_uid не найден."""
    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings, \
         patch("command_routes._get_zone_uid_from_id", new_callable=AsyncMock) as mock_get_uid:

        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="uid")
        mock_get_uid.return_value = None

        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
        }

        response = client.post("/commands", json=payload, headers=auth_headers)

        assert response.status_code == 409
        assert "zone_uid could not be resolved" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called
        mock_get_uid.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_publish_command_fails_closed_on_db_error_before_publish(
    client, auth_headers, mock_mqtt_client
):
    """Команда не должна публиковаться в MQTT, если БД недоступна при проверке cmd_id."""

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from nodes where uid = $1" in normalized:
            return [{"id": 1, "zone_id": 1, "pending_zone_id": None}]
        if "from commands where cmd_id = $1" in normalized:
            raise Exception("db unavailable")
        return []

    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings, \
         patch("command_routes.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        mock_fetch.side_effect = _fetch_side_effect

        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "params": {"duration_ms": 60000},
        }

        response = client.post("/commands", json=payload, headers=auth_headers)

        assert response.status_code == 503
        assert "Unable to persist command" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called


@pytest.mark.asyncio
async def test_publish_command_rejects_cmd_id_collision(
    client, auth_headers, mock_mqtt_client
):
    """Команда с тем же cmd_id, но другим target должна быть отклонена."""

    async def _fetch_side_effect(query, *args):
        normalized = " ".join(str(query).split()).lower()
        if "from nodes where uid = $1" in normalized:
            return [{"id": 1, "zone_id": 1, "pending_zone_id": None}]
        if "from commands where cmd_id = $1" in normalized:
            return [
                {
                    "status": "QUEUED",
                    "source": "automation",
                    "zone_id": 2,
                    "node_id": 77,
                    "channel": "default",
                    "cmd": "run_pump",
                }
            ]
        return []

    with patch("command_routes.get_mqtt_client", new_callable=AsyncMock) as mock_get_mqtt, \
         patch("command_routes.get_settings") as mock_settings, \
         patch("command_routes.fetch", new_callable=AsyncMock) as mock_fetch:
        mock_get_mqtt.return_value = mock_mqtt_client
        mock_settings.return_value = Mock(mqtt_zone_format="id")
        mock_fetch.side_effect = _fetch_side_effect

        payload = {
            "cmd": "run_pump",
            "greenhouse_uid": "gh-1",
            "zone_id": 1,
            "node_uid": "nd-irrig-1",
            "channel": "default",
            "cmd_id": "collision-cmd-id-1",
            "params": {"duration_ms": 60000},
        }

        response = client.post("/commands", json=payload, headers=auth_headers)

        assert response.status_code == 409
        assert "already belongs to another command" in response.json()["detail"]
        assert not mock_mqtt_client._client._client.publish.called


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/zones/1/fill", {"target_level": 0.9}),
        ("/zones/1/drain", {"target_level": 0.1}),
        ("/zones/1/calibrate-flow", {"node_id": 1, "channel": "flow_sensor"}),
        ("/zones/1/calibrate-pump", {"node_channel_id": 1, "duration_sec": 20}),
    ],
)
def test_legacy_zone_endpoints_are_removed(client, auth_headers, path, payload):
    response = client.post(path, json=payload, headers=auth_headers)

    assert response.status_code == 404
