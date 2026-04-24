"""HTTP-клиент для отправки событий causal chain cockpit-UI в Laravel.

Этот модуль добавлен в рамках Phase 2 редизайна Scheduler Cockpit UI. Он
ретранслирует ключевые переходы состояния команды (DISPATCH/RUNNING/COMPLETE
/FAIL) в Laravel-вебхук ``/api/internal/webhooks/history-logger/execution-event``,
чтобы фронт мог отрисовывать живую цепочку решений для конкретного исполнения.

Контракт webhook фиксирован в
``doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`` (раздел "history-logger
webhook → Laravel").

Хуки вызова тонкие и idempotent: ошибка webhook **не** меняет основной поток
публикации команд; чтобы не уронить команду из-за проблем в Laravel или WS,
все ошибки логируются и глотаются. Debouncing выполняется на стороне Laravel.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Literal, Optional

import httpx

logger = logging.getLogger(__name__)

ChainStatus = Literal["ok", "err", "skip", "run", "warn"]
ChainStep = Literal[
    "SNAPSHOT",
    "DECISION",
    "TASK",
    "DISPATCH",
    "RUNNING",
    "COMPLETE",
    "FAIL",
    "SKIP",
]


@dataclass(frozen=True)
class WebhookConfig:
    """Конфигурация вебхука. Создаётся один раз при старте сервиса."""

    base_url: str
    secret: str
    enabled: bool
    timeout_sec: float = 2.0

    @classmethod
    def from_env(cls) -> "WebhookConfig":
        base_url = os.environ.get("LARAVEL_URL") or os.environ.get(
            "LARAVEL_API_URL", "http://laravel:8080"
        )
        secret = os.environ.get("HISTORY_LOGGER_WEBHOOK_SECRET", "")
        enabled = bool(secret) and (
            os.environ.get("HISTORY_LOGGER_WEBHOOK_ENABLED", "1") != "0"
        )
        timeout_sec = float(os.environ.get("HISTORY_LOGGER_WEBHOOK_TIMEOUT_SEC", "2.0"))
        return cls(
            base_url=base_url.rstrip("/"),
            secret=secret,
            enabled=enabled,
            timeout_sec=timeout_sec,
        )


_config: Optional[WebhookConfig] = None
_client: Optional[httpx.AsyncClient] = None


def get_config() -> WebhookConfig:
    """Возвращает singleton-конфигурацию (создаётся лениво)."""
    global _config
    if _config is None:
        _config = WebhookConfig.from_env()
    return _config


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=get_config().timeout_sec)
    return _client


def _sign(secret: str, timestamp: str, body: str) -> str:
    """Формирует HMAC-SHA256 подпись в том же формате, что и Laravel middleware."""
    mac = hmac.new(secret.encode("utf-8"), msg=f"{timestamp}.{body}".encode("utf-8"), digestmod=hashlib.sha256)
    return mac.hexdigest()


async def emit_execution_step(
    *,
    zone_id: int,
    step: ChainStep,
    ref: str,
    status: ChainStatus,
    execution_id: Optional[str] = None,
    cmd_id: Optional[str] = None,
    detail: str = "",
    at_iso: Optional[str] = None,
    live: Optional[bool] = None,
) -> bool:
    """Отправляет один шаг causal chain в Laravel.

    Обязательно передать **либо** ``execution_id`` (= ``ae_tasks.id``),
    **либо** ``cmd_id`` — Laravel сам резолвит execution_id из cmd_id через
    связи таблиц ``commands`` + ``ae_tasks``.

    Возвращает True при успехе (HTTP 2xx), иначе False. Исключения не
    пробрасываются — они логируются и поглощаются, чтобы не ломать основной
    поток публикации команды.
    """
    if execution_id is None and cmd_id is None:
        logger.warning("chain_webhook: both execution_id and cmd_id are empty, skipping")
        return False

    config = get_config()
    if not config.enabled:
        return False

    payload: dict = {
        "zone_id": int(zone_id),
        "step": step,
        "ref": ref,
        "status": status,
        "detail": detail,
    }
    if execution_id is not None:
        payload["execution_id"] = str(execution_id)
    if cmd_id is not None:
        payload["cmd_id"] = str(cmd_id)
    if at_iso:
        payload["at"] = at_iso
    if live is not None:
        payload["live"] = bool(live)

    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    timestamp = str(int(time.time()))
    signature = _sign(config.secret, timestamp, body)

    url = f"{config.base_url}/api/internal/webhooks/history-logger/execution-event"
    headers = {
        "Content-Type": "application/json",
        "X-Hydro-Timestamp": timestamp,
        "X-Hydro-Signature": signature,
    }

    try:
        response = await _get_client().post(url, content=body, headers=headers)
        if response.status_code >= 400:
            logger.warning(
                "chain_webhook: non-2xx response",
                extra={
                    "status_code": response.status_code,
                    "body": response.text[:200],
                    "execution_id": execution_id,
                    "step": step,
                },
            )
            return False
        return True
    except httpx.HTTPError as exc:
        logger.warning(
            "chain_webhook: HTTP error sending webhook",
            extra={"error": str(exc), "execution_id": execution_id, "step": step},
        )
        return False
    except Exception as exc:  # pragma: no cover — защитный catch-all.
        logger.exception(
            "chain_webhook: unexpected error sending webhook",
            extra={"error": str(exc), "execution_id": execution_id, "step": step},
        )
        return False


async def shutdown() -> None:
    """Закрыть httpx-клиент на shutdown сервиса."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
