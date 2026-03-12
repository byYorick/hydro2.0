"""
Утилиты для отправки логов сервисов в Laravel API (/api/python/logs).
Используется лёгкий фоновой пост-запрос, чтобы не блокировать основные петли.
"""
import logging
import threading
from typing import Any, Dict, Optional

from common.env import get_settings

logger = logging.getLogger(__name__)

try:
    import httpx
except ImportError:  # pragma: no cover - httpx обязателен в сервисах, но защищаемся от dev-окружений
    httpx = None
    logger.warning("httpx is not installed; service log forwarding disabled")


def _build_token(settings) -> Optional[str]:
    # Предпочитаем ingest/history токен, fallback на bridge
    for candidate in (
        getattr(settings, "history_logger_api_token", None),
        getattr(settings, "ingest_token", None),
        getattr(settings, "bridge_api_token", None),
    ):
        if candidate:
            return candidate
    return None


def _send_request(url: str, token: str, payload: Dict[str, Any], timeout: float = 5.0) -> None:
    if not httpx:
        return
    try:
        httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
    except Exception:
        # Не ломаем сервис, если отправка не удалась
        logger.debug("Failed to push service log to Laravel", exc_info=True)


def send_service_log(
    service: str,
    level: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
    *,
    async_mode: bool = True,
) -> None:
    """
    Отправить лог сервисов в Laravel (/api/python/logs).

    Args:
        service: Имя сервиса (automation-engine | history-logger | mqtt-bridge | scheduler | laravel | system)
        level: Уровень (info, warning, error, critical, debug)
        message: Текст сообщения
        context: Доп. контекст (должен быть JSON-serializable)
        async_mode: отправлять в отдельном потоке, чтобы не блокировать цикл
    """
    settings = get_settings()
    base_url = getattr(settings, "laravel_api_url", "").rstrip("/")
    token = _build_token(settings)

    if not base_url or not token:
        logger.debug(
            "Service log skipped: laravel_api_url or token not configured",
            extra={"base_url": base_url, "token_present": bool(token)},
        )
        return

    url = f"{base_url}/api/python/logs"
    payload = {
        "service": service,
        "level": level,
        "message": message,
        "context": context or {},
    }

    if async_mode:
        threading.Thread(target=_send_request, args=(url, token, payload), daemon=True).start()
    else:
        _send_request(url, token, payload)
