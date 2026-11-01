"""Wire-format контракт node_secret_enc (без брокера и БД)."""

import base64
import json

from commands.node_secret_wire import (
    prepare_node_config_for_mqtt,
    unwrap_node_secret,
    wrap_node_secret,
)


def test_wrap_roundtrip_and_fixed_nonce():
    secret = "b" * 64
    passphrase = "esp32_pass"
    node_uid = "nd-ph-1"
    nonce = bytes(range(12))
    token = wrap_node_secret(secret, passphrase, node_uid, nonce=nonce)
    assert unwrap_node_secret(token, passphrase, node_uid) == secret
    raw = base64.b64decode(token)
    assert raw[:12] == nonce


def test_wrap_rejects_wrong_passphrase():
    token = wrap_node_secret("secret-value-32-bytes-padding!!", "esp32_pass", "nd-1")
    try:
        unwrap_node_secret(token, "wrong-pass", "nd-1")
    except Exception:
        return
    raise AssertionError("wrong passphrase must not decrypt")


def test_prepare_strips_plaintext_and_sets_enc(monkeypatch):
    monkeypatch.setenv("NODE_SECRET_WRAP_PASSPHRASE", "esp32_pass")
    monkeypatch.delenv("MQTT_ESP32_NODE_PASS", raising=False)
    config = prepare_node_config_for_mqtt(
        {"node_id": "nd-1", "node_secret": "super-secret-value", "version": 3},
        node_uid="nd-1",
        node_secret="db-secret-value-not-plaintext",
    )
    assert "node_secret" not in config
    assert unwrap_node_secret(config["node_secret_enc"], "esp32_pass", "nd-1") == (
        "db-secret-value-not-plaintext"
    )
    encoded = json.dumps(config)
    assert "super-secret-value" not in encoded
    assert "db-secret-value-not-plaintext" not in encoded


def test_prepare_omits_enc_without_passphrase(monkeypatch):
    monkeypatch.delenv("NODE_SECRET_WRAP_PASSPHRASE", raising=False)
    monkeypatch.delenv("MQTT_ESP32_NODE_PASS", raising=False)
    config = prepare_node_config_for_mqtt(
        {"node_secret": "plain-secret"},
        node_uid="nd-1",
        node_secret="plain-secret",
    )
    assert "node_secret" not in config
    assert "node_secret_enc" not in config
