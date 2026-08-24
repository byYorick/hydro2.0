"""Unit-тесты MQTT live-status probe и GET /nodes/{uid}/live-status (без живого брокера)."""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app import app
from live_status_probe import probe_node_status


class _FakeMqttMessage:
    def __init__(self, topic: str, payload: bytes, retain: bool = False):
        self.topic = topic
        self.payload = payload
        self.retain = retain


class _FakeMqttClient:
    instances: list["_FakeMqttClient"] = []

    def __init__(self, *args, **kwargs):
        self.on_connect = None
        self.on_message = None
        self.subscribed: list[tuple[str, int]] = []
        self.publish_calls: list[tuple] = []
        self.loop_started = False
        self.disconnected = False
        self._pending: list[_FakeMqttMessage] = []
        _FakeMqttClient.instances.append(self)

    def username_pw_set(self, *args, **kwargs):
        return None

    def tls_set(self, *args, **kwargs):
        return None

    def connect(self, host, port, keepalive=60):  # noqa: ANN001
        if self.on_connect:
            self.on_connect(self, None, {}, 0)
        return 0

    def subscribe(self, topic, qos=0):  # noqa: ANN001
        self.subscribed.append((topic, qos))
        return (0, 1)

    def publish(self, *args, **kwargs):
        self.publish_calls.append((args, kwargs))
        return Mock(rc=0)

    def loop_start(self):
        self.loop_started = True
        if self.on_message:
            for msg in self._pending:
                self.on_message(self, None, msg)

    def loop_stop(self):
        return None

    def disconnect(self):
        self.disconnected = True


@pytest.fixture
def mock_probe_settings():
    settings = SimpleNamespace(
        mqtt_host="mqtt",
        mqtt_port=1883,
        mqtt_user="history_logger",
        mqtt_pass="logger_pass",
        mqtt_tls=False,
        mqtt_ca_file=None,
        node_offline_timeout_sec=120,
    )
    with patch("live_status_probe.get_settings", return_value=settings):
        yield settings


@pytest.fixture
def fake_mqtt_client(mock_probe_settings):  # noqa: ARG001
    _FakeMqttClient.instances.clear()
    with patch("live_status_probe.mqtt.Client", side_effect=_FakeMqttClient):
        yield _FakeMqttClient


@pytest.fixture
def fast_probe_wait(monkeypatch):
    """Не ждать реальный timeout_sec (минимум 1 с) в unit-тестах."""
    original_wait = threading.Event.wait

    def wait0(self, timeout=None):  # noqa: ANN001, ARG001
        return original_wait(self, 0)

    monkeypatch.setattr(threading.Event, "wait", wait0)


def _status_payload(status: str, ts: int | None = None) -> bytes:
    body: dict = {"status": status}
    if ts is not None:
        body["ts"] = ts
    return json.dumps(body).encode("utf-8")


def test_probe_live_non_retained_online_is_reachable(fake_mqtt_client, fast_probe_wait):
    client_cls = fake_mqtt_client

    def _client_factory(*args, **kwargs):
        client = client_cls(*args, **kwargs)
        client._pending = [
            _FakeMqttMessage(
                "hydro/gh-1/zn-7/nd-1/status",
                _status_payload("ONLINE", int(time.time())),
                retain=False,
            )
        ]
        return client

    with patch("live_status_probe.mqtt.Client", side_effect=_client_factory):
        result = probe_node_status("gh-1", "zn-7", "nd-1", timeout_sec=2.0)

    assert result["reachable"] is True
    assert result["mqtt_status"] == "ONLINE"
    assert result["reason"] is None
    assert result["topic"] == "hydro/gh-1/zn-7/nd-1/status"
    inst = client_cls.instances[-1]
    assert inst.publish_calls == []
    topics = {t for t, _qos in inst.subscribed}
    assert "hydro/gh-1/zn-7/nd-1/status" in topics
    assert "hydro/gh-1/zn-7/nd-1/lwt" in topics


def test_probe_offline_lwt_overrides_online(fake_mqtt_client, fast_probe_wait):
    client_cls = fake_mqtt_client

    def _client_factory(*args, **kwargs):
        client = client_cls(*args, **kwargs)
        client._pending = [
            _FakeMqttMessage(
                "hydro/gh-1/zn-7/nd-1/status",
                _status_payload("ONLINE", int(time.time())),
                retain=False,
            ),
            _FakeMqttMessage(
                "hydro/gh-1/zn-7/nd-1/lwt",
                _status_payload("OFFLINE"),
                retain=True,
            ),
        ]
        return client

    with patch("live_status_probe.mqtt.Client", side_effect=_client_factory):
        result = probe_node_status("gh-1", "zn-7", "nd-1", timeout_sec=2.0)

    assert result["reachable"] is False
    assert result["reason"] == "offline_lwt"
    assert result["lwt_status"] == "OFFLINE"
    assert client_cls.instances[-1].publish_calls == []


def test_probe_retained_online_waits_for_live_signal(fake_mqtt_client, fast_probe_wait):
    client_cls = fake_mqtt_client

    def _client_factory(*args, **kwargs):
        client = client_cls(*args, **kwargs)
        client._pending = [
            _FakeMqttMessage(
                "hydro/gh-1/zn-7/nd-1/status",
                _status_payload("ONLINE", int(time.time())),
                retain=True,
            )
        ]
        return client

    with patch("live_status_probe.mqtt.Client", side_effect=_client_factory):
        result = probe_node_status("gh-1", "zn-7", "nd-1", timeout_sec=2.0)

    assert result["reachable"] is False
    assert result["reason"] == "retained_online_waiting_live_signal"
    assert result["retained"] is True


def test_probe_timeout_without_messages(fake_mqtt_client, fast_probe_wait):
    result = probe_node_status("gh-1", "zn-7", "nd-1", timeout_sec=2.0)

    assert result["reachable"] is False
    assert result["reason"] == "timeout"
    assert fake_mqtt_client.instances[-1].publish_calls == []


def test_probe_mqtt_connect_error_sets_mqtt_error(fake_mqtt_client, fast_probe_wait):
    def _boom(*args, **kwargs):
        client = fake_mqtt_client(*args, **kwargs)

        def _fail_connect(*_a, **_k):
            raise OSError("broker unreachable")

        client.connect = _fail_connect
        return client

    with patch("live_status_probe.mqtt.Client", side_effect=_boom):
        result = probe_node_status("gh-1", "zn-7", "nd-1", timeout_sec=2.0)

    assert result["reason"] == "mqtt_error"
    assert "broker unreachable" in result["error"]


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def bypass_live_status_auth():
    with patch("command_routes._auth_ingest", return_value=None):
        yield


def test_live_status_route_returns_ok_envelope(client, bypass_live_status_auth):
    probe_result = {
        "topic": "hydro/gh-1/zn-7/nd-1/status",
        "reachable": True,
        "mqtt_status": "ONLINE",
        "reason": None,
    }
    with patch("command_routes.probe_node_status", return_value=probe_result) as mocked:
        response = client.get(
            "/nodes/nd-1/live-status",
            params={
                "greenhouse_uid": "gh-1",
                "zone_segment": "zn-7",
                "timeout_sec": 3,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "data": probe_result}
    mocked.assert_called_once_with("gh-1", "zn-7", "nd-1", 3.0)


def test_live_status_route_requires_query_params(client, bypass_live_status_auth):
    response = client.get("/nodes/nd-1/live-status")
    assert response.status_code == 422


def test_live_status_route_probe_failure_is_500(client, bypass_live_status_auth):
    with patch("command_routes.probe_node_status", side_effect=RuntimeError("boom")):
        response = client.get(
            "/nodes/nd-1/live-status",
            params={"greenhouse_uid": "gh-1", "zone_segment": "zn-7"},
        )

    assert response.status_code == 500
    detail = response.json().get("detail", "")
    assert "live_status_probe_failed" in str(detail)
