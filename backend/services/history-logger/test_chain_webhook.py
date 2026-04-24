"""Smoke-тесты на chain_webhook: HMAC-подпись и обработка ошибок."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

import chain_webhook


@pytest.fixture(autouse=True)
def _reset_webhook_state(monkeypatch):
    """Сбрасываем singleton-конфиг перед каждым тестом."""
    chain_webhook._config = None  # type: ignore[attr-defined]
    chain_webhook._client = None  # type: ignore[attr-defined]
    yield
    chain_webhook._config = None  # type: ignore[attr-defined]


def test_sign_matches_laravel_format():
    """Подпись совпадает с тем, что Laravel middleware ожидает.

    Формат: HMAC_SHA256(secret, "{timestamp}.{raw_body}") → hex.
    """
    signature = chain_webhook._sign(secret="s3cret", timestamp="1700000000", body='{"a":1}')
    expected = hmac.new(b"s3cret", b"1700000000.{\"a\":1}", hashlib.sha256).hexdigest()
    assert signature == expected


def test_config_disabled_without_secret(monkeypatch):
    monkeypatch.delenv("HISTORY_LOGGER_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("HISTORY_LOGGER_WEBHOOK_ENABLED", "1")
    cfg = chain_webhook.WebhookConfig.from_env()
    assert cfg.enabled is False


def test_config_disabled_explicitly(monkeypatch):
    monkeypatch.setenv("HISTORY_LOGGER_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("HISTORY_LOGGER_WEBHOOK_ENABLED", "0")
    cfg = chain_webhook.WebhookConfig.from_env()
    assert cfg.enabled is False


def test_config_enabled_with_secret(monkeypatch):
    monkeypatch.setenv("HISTORY_LOGGER_WEBHOOK_SECRET", "s3cret")
    monkeypatch.delenv("HISTORY_LOGGER_WEBHOOK_ENABLED", raising=False)
    cfg = chain_webhook.WebhookConfig.from_env()
    assert cfg.enabled is True
    assert cfg.base_url.startswith("http")


@pytest.mark.asyncio
async def test_emit_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("HISTORY_LOGGER_WEBHOOK_SECRET", raising=False)
    result = await chain_webhook.emit_execution_step(
        zone_id=42,
        execution_id="401",
        step="DISPATCH",
        ref="cmd-9931",
        status="ok",
    )
    assert result is False


@pytest.mark.asyncio
async def test_emit_sends_signed_request(monkeypatch):
    monkeypatch.setenv("HISTORY_LOGGER_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("LARAVEL_URL", "http://laravel:8080")
    monkeypatch.setenv("HISTORY_LOGGER_WEBHOOK_ENABLED", "1")

    captured: dict = {}

    class _FakeResponse:
        status_code = 200
        text = "{\"status\":\"ok\"}"

    class _FakeClient:
        def __init__(self, *_, **__):
            pass

        async def post(self, url, content, headers):
            captured["url"] = url
            captured["body"] = content
            captured["headers"] = headers
            return _FakeResponse()

        async def aclose(self):
            pass

    monkeypatch.setattr(chain_webhook.httpx, "AsyncClient", _FakeClient)

    ok = await chain_webhook.emit_execution_step(
        zone_id=42,
        execution_id="401",
        step="DISPATCH",
        ref="cmd-9931",
        status="ok",
        detail="pump_acid/cmd",
        live=False,
    )
    assert ok is True
    assert captured["url"].endswith("/api/internal/webhooks/history-logger/execution-event")
    headers = captured["headers"]
    assert "X-Hydro-Signature" in headers
    assert "X-Hydro-Timestamp" in headers
    body = captured["body"]
    payload = json.loads(body)
    assert payload["zone_id"] == 42
    assert payload["execution_id"] == "401"
    assert payload["step"] == "DISPATCH"
    # Подпись детерминирована при фиксированных тimestamp+body:
    assert headers["X-Hydro-Signature"] == chain_webhook._sign(
        secret="s3cret",
        timestamp=headers["X-Hydro-Timestamp"],
        body=body,
    )
