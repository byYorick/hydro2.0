import hmac
import logging
import os
import time
from collections import defaultdict
from typing import Dict, List

from fastapi import HTTPException, Request

from common.env import get_settings
from metrics import INGEST_AUTH_FAILED


AE_COMMAND_PRINCIPAL = "automation-engine"
API_COMMAND_PRINCIPAL = "laravel"


def _tokens_equal(provided: str, expected: str) -> bool:
    """Timing-safe сравнение Bearer-токенов.

    Использует ``hmac.compare_digest``, чтобы исключить timing side-channel при
    проверке `Authorization: Bearer …` против ожидаемого значения. Также безопасен
    для пустых/None входов и строк разной длины.
    """
    if not provided or not expected:
        return False
    if len(provided) != len(expected):
        return False
    return hmac.compare_digest(provided, expected)

logger = logging.getLogger(__name__)

# Rate limiting для HTTP ingest endpoint
_ingest_rate_limiter: Dict[str, List[float]] = defaultdict(list)
INGEST_RATE_LIMIT_REQUESTS = 100
INGEST_RATE_LIMIT_WINDOW_SEC = 60


def _auth_ingest(request: Request) -> None:
    """
    Проверка токена аутентификации для HTTP ingest endpoint.
    Использует HISTORY_LOGGER_API_TOKEN или PY_INGEST_TOKEN (через get_settings).
    В production токен обязателен всегда.
    """
    s = get_settings()

    app_env = os.getenv("APP_ENV", "").lower().strip()
    is_prod = app_env in ("production", "prod") and app_env != ""

    if is_prod:
        if not s.history_logger_api_token:
            logger.error(
                "HISTORY_LOGGER_API_TOKEN or PY_INGEST_TOKEN must be set in production environment"
            )
            INGEST_AUTH_FAILED.inc()
            raise HTTPException(
                status_code=500,
                detail="Server configuration error: ingest token not configured",
            )

        token = request.headers.get("Authorization", "")
        expected_token = f"Bearer {s.history_logger_api_token}"

        if not _tokens_equal(token, expected_token):
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(
                "Invalid or missing token for HTTP ingest in production: "
                f"token_present={bool(token)}, client_ip={client_ip}"
            )
            INGEST_AUTH_FAILED.inc()
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: token required in production",
            )
        return

    if s.history_logger_api_token:
        token = request.headers.get("Authorization", "")
        expected_token = f"Bearer {s.history_logger_api_token}"

        if not _tokens_equal(token, expected_token):
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(
                "Invalid or missing token for HTTP ingest: "
                f"token_present={bool(token)}, client_ip={client_ip}"
            )
            INGEST_AUTH_FAILED.inc()
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: invalid or missing token",
            )
        return

    client_ip = request.client.host if request.client else ""
    is_localhost = client_ip in ["127.0.0.1", "::1", "localhost"]

    if not is_localhost:
        logger.warning(
            "Rejecting non-localhost request without token: "
            f"client_ip={client_ip}. Token is required in production. "
            "Set HISTORY_LOGGER_API_TOKEN or PY_INGEST_TOKEN environment variable."
        )
        INGEST_AUTH_FAILED.inc()
        raise HTTPException(
            status_code=401,
            detail=(
                "Unauthorized: token required. Set HISTORY_LOGGER_API_TOKEN or "
                "PY_INGEST_TOKEN environment variable."
            ),
        )

    logger.debug(f"Allowing localhost request without token (dev mode): client_ip={client_ip}")


def resolve_command_principal(request: Request) -> str:
    """Кто публикует команду: только по Bearer, никогда по полю body ``source``.

    ``HISTORY_LOGGER_AE_TOKEN`` даёт principal ``automation-engine`` и обязан
    отличаться от общего ingest-токена. Совпадение или отсутствие AE-токена
    оставляет вызывающего обычным API-клиентом (``laravel``).
    """
    settings = get_settings()
    general = str(getattr(settings, "history_logger_api_token", "") or "").strip()
    ae_token = os.getenv("HISTORY_LOGGER_AE_TOKEN", "").strip()
    provided = request.headers.get("Authorization", "")

    if (
        ae_token
        and general
        and ae_token != general
        and _tokens_equal(provided, f"Bearer {ae_token}")
    ):
        return AE_COMMAND_PRINCIPAL

    _auth_ingest(request)
    return API_COMMAND_PRINCIPAL


def _check_rate_limit(client_id: str) -> bool:
    """Проверка rate limit для клиента."""
    current_time = time.time()

    window_start = current_time - INGEST_RATE_LIMIT_WINDOW_SEC
    _ingest_rate_limiter[client_id] = [
        ts for ts in _ingest_rate_limiter[client_id] if ts > window_start
    ]

    if len(_ingest_rate_limiter[client_id]) >= INGEST_RATE_LIMIT_REQUESTS:
        return False

    _ingest_rate_limiter[client_id].append(current_time)
    return True
