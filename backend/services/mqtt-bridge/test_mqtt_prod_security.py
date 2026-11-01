"""Контракт prod MQTT: TLS-entrypoint и ACL без широкого доступа сервисов."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_entrypoint_adds_tls_listener_and_can_drop_plaintext():
    text = (ROOT / "mosquitto-entrypoint.sh").read_text(encoding="utf-8")
    assert "listener 8883" in text
    assert "MQTT_PLAINTEXT_ENABLED" in text
    assert "server.crt" in text
    assert "allow_anonymous false" in (ROOT / "mosquitto.prod.conf").read_text(encoding="utf-8")


def test_service_accounts_are_not_broad_except_history_logger():
    lines = (ROOT / "acl").read_text(encoding="utf-8").splitlines()
    broad = []
    current = None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("user "):
            current = stripped.split()[1]
            continue
        if stripped.startswith("pattern "):
            current = None
            continue
        if "readwrite hydro/#" in stripped:
            broad.append(current)
    assert broad == ["history_logger"]


def test_esp32_acl_is_per_client_id():
    text = (ROOT / "acl").read_text(encoding="utf-8")
    assert "pattern read hydro/+/+/%c/config" in text
    assert "pattern read hydro/+/+/%c/+/command" in text
    assert "pattern write hydro/+/+/%c/+/telemetry" in text
    assert "pattern readwrite hydro/+/+/%c/#" not in text
    assert "topic write hydro/gh-temp/zn-temp/#" not in text
    assert "topic read hydro/time/response" in text
    assert "topic write hydro/time/request" in text
    node_section = text.split("user esp32_node", 1)[-1]
    assert "topic readwrite hydro/#" not in node_section
    for line in node_section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("pattern "):
            continue
        if "/command" in stripped and "command_response" not in stripped:
            assert stripped.startswith("pattern read ")
        if stripped.endswith("/config"):
            assert stripped.startswith("pattern read ")


def test_prod_compose_publishes_tls_port_and_wires_clients():
    compose = Path(__file__).resolve().parents[2] / "docker-compose.prod.yml"
    text = compose.read_text(encoding="utf-8")
    assert "8883:8883" in text
    assert "MQTT_TLS=${MQTT_TLS:-0}" in text
    assert "/etc/mqtt/certs" in text
    assert "/mosquitto/certs" in text
