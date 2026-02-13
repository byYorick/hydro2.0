"""
Единый HTTP клиент пул для всех запросов к Laravel API.

Обеспечивает:
- Один httpx.AsyncClient на event loop для переиспользования соединений
- Semaphore для лимита параллелизма (backpressure)
- Exponential backoff с jitter
- Метрики для мониторинга
"""
import asyncio
import logging
import random
import threading
import weakref
from typing import Optional
import httpx
from prometheus_client import Counter, Histogram, Gauge

from .env import get_settings
from .trace_context import inject_trace_id_header

logger = logging.getLogger(__name__)

# Метрики
HTTP_REQUESTS_TOTAL = Counter(
    "http_client_requests_total",
    "Total HTTP requests",
    ["method", "status", "endpoint"]
)
HTTP_REQUEST_DURATION = Histogram(
    "http_client_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"]
)
HTTP_REQUEST_ERRORS = Counter(
    "http_client_errors_total",
    "HTTP request errors",
    ["error_type", "endpoint"]
)
HTTP_SEMAPHORE_WAIT = Histogram(
    "http_client_semaphore_wait_seconds",
    "Time waiting for semaphore slot",
    ["endpoint"]
)
HTTP_CONCURRENT_REQUESTS = Gauge(
    "http_client_concurrent_requests",
    "Current number of concurrent HTTP requests"
)

# HTTP клиенты и semaphore храним отдельно для каждого event loop.
# Это предотвращает cross-loop ошибки в сервисах с несколькими loop/потоками.
_state_lock = threading.Lock()
_http_clients: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient]" = weakref.WeakKeyDictionary()
_http_semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()

# Дефолт намеренно консервативный, чтобы не перегружать Laravel/DB каскадными ретраями.
MAX_CONCURRENT_REQUESTS = 20


def get_max_concurrent_requests() -> int:
    """Получить максимальное количество параллельных запросов из настроек."""
    s = get_settings()
    return max(1, int(getattr(s, "http_max_concurrent_requests", MAX_CONCURRENT_REQUESTS)))


async def get_http_client() -> httpx.AsyncClient:
    """
    Возвращает httpx.AsyncClient для текущего event loop.
    Создаёт клиент и semaphore при первом вызове в рамках loop.
    """
    loop = asyncio.get_running_loop()

    with _state_lock:
        client = _http_clients.get(loop)

    if client is None:
        s = get_settings()
        request_timeout = float(getattr(s, "laravel_api_timeout_sec", 10.0))
        timeout = httpx.Timeout(request_timeout, connect=min(5.0, request_timeout))
        max_keepalive_connections = max(1, int(getattr(s, "http_max_keepalive_connections", 10)))
        max_connections = max(max_keepalive_connections, int(getattr(s, "http_max_connections", 30)))
        keepalive_expiry = max(1.0, float(getattr(s, "http_keepalive_expiry_sec", 15.0)))
        limits = httpx.Limits(
            max_keepalive_connections=max_keepalive_connections,
            max_connections=max_connections,
            keepalive_expiry=keepalive_expiry,
        )
        client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits
        )
        with _state_lock:
            _http_clients[loop] = client
        logger.info(
            "Created loop-scoped httpx.AsyncClient for Laravel API "
            "(max_connections=%s, max_keepalive=%s, keepalive_expiry=%ss, timeout=%ss)",
            max_connections,
            max_keepalive_connections,
            keepalive_expiry,
            request_timeout,
        )

    with _state_lock:
        semaphore = _http_semaphores.get(loop)
    if semaphore is None:
        max_concurrent = get_max_concurrent_requests()
        semaphore = asyncio.Semaphore(max_concurrent)
        with _state_lock:
            _http_semaphores[loop] = semaphore
        logger.info(
            "Created loop-scoped HTTP semaphore with max_concurrent=%s",
            max_concurrent,
        )

    return client


async def close_http_client():
    """Закрывает HTTP клиент текущего event loop."""
    loop = asyncio.get_running_loop()
    with _state_lock:
        client = _http_clients.pop(loop, None)
        _http_semaphores.pop(loop, None)

    if client is not None:
        try:
            await client.aclose()
            logger.info("Closed loop-scoped httpx.AsyncClient")
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.warning("HTTP client close skipped: event loop is closed")
            else:
                raise


def calculate_backoff_with_jitter(
    retry_count: int,
    base_delay: float = 1.0,
    max_delay: float = 300.0,
    jitter_factor: float = 0.1
) -> float:
    """
    Вычисляет задержку для exponential backoff с jitter.
    
    Args:
        retry_count: Номер попытки (0-based)
        base_delay: Базовая задержка в секундах
        max_delay: Максимальная задержка в секундах
        jitter_factor: Коэффициент jitter (0.1 = ±10%)
        
    Returns:
        Задержка в секундах с jitter
    """
    delay = base_delay * (2 ** min(retry_count, 10))  # Ограничиваем экспоненту
    delay = min(delay, max_delay)
    
    # Добавляем jitter: ±jitter_factor от delay
    jitter = delay * jitter_factor * (2 * random.random() - 1)  # От -jitter_factor до +jitter_factor
    final_delay = delay + jitter
    
    # Гарантируем, что задержка не отрицательная и не превышает max_delay
    return max(0.0, min(final_delay, max_delay))


async def make_request(
    method: str,
    url: str,
    endpoint: str = "unknown",
    **kwargs
) -> httpx.Response:
    """
    Выполняет HTTP запрос с использованием loop-scoped клиента и semaphore.
    
    Args:
        method: HTTP метод (get, post, put, patch, delete)
        url: URL для запроса
        endpoint: Имя endpoint для метрик (например, 'telemetry_broadcast', 'command_ack')
        **kwargs: Дополнительные аргументы для httpx (headers, json, etc.)
        
    Returns:
        httpx.Response
        
    Raises:
        httpx.HTTPError: При ошибках HTTP запроса
    """
    client = await get_http_client()
    loop = asyncio.get_running_loop()
    with _state_lock:
        semaphore = _http_semaphores.get(loop)

    if semaphore is None:
        # Fallback если semaphore не инициализирован
        semaphore = asyncio.Semaphore(get_max_concurrent_requests())
        with _state_lock:
            _http_semaphores[loop] = semaphore
    
    # Ждём слот в semaphore (backpressure)
    wait_start = loop.time()
    async with semaphore:
        wait_duration = loop.time() - wait_start
        if wait_duration > 0.1:  # Логируем только если ждали более 100ms
            logger.warning(
                f"[HTTP_CLIENT] Waited {wait_duration:.2f}s for semaphore slot, "
                f"endpoint={endpoint}"
            )
        HTTP_SEMAPHORE_WAIT.labels(endpoint=endpoint).observe(wait_duration)
        
        # Отслеживаем количество параллельных запросов
        HTTP_CONCURRENT_REQUESTS.inc()
        try:
            # Логируем начало запроса с деталями
            headers_info = inject_trace_id_header(kwargs.get('headers'))
            kwargs["headers"] = headers_info
            json_info = kwargs.get('json', {})
            logger.info(
                f"[HTTP_CLIENT] Sending request: {method} {url}, endpoint={endpoint}, "
                f"has_auth_header={bool(headers_info.get('Authorization'))}, "
                f"json_keys={list(json_info.keys()) if json_info else 'none'}"
            )
            
            request_start = loop.time()
            method_func = getattr(client, method.lower())
            response = await method_func(url, **kwargs)
            request_duration = loop.time() - request_start
            
            logger.info(
                f"[HTTP_CLIENT] Received response: {method} {url}, status={response.status_code}, "
                f"duration={request_duration:.3f}s, endpoint={endpoint}"
            )
            
            # Метрики
            HTTP_REQUESTS_TOTAL.labels(
                method=method.upper(),
                status=str(response.status_code),
                endpoint=endpoint
            ).inc()
            HTTP_REQUEST_DURATION.labels(
                method=method.upper(),
                endpoint=endpoint
            ).observe(request_duration)
            
            # Логируем медленные запросы (> 5 секунд)
            if request_duration > 5.0:
                logger.warning(
                    f"[HTTP_CLIENT] Slow request: {method} {url} took {request_duration:.2f}s, "
                    f"status={response.status_code}, endpoint={endpoint}"
                )
            
            return response
        except (httpx.TimeoutException, httpx.RequestError, httpx.NetworkError) as e:
            error_type = type(e).__name__
            HTTP_REQUEST_ERRORS.labels(error_type=error_type, endpoint=endpoint).inc()
            logger.error(
                f"[HTTP_CLIENT] Request error: {method} {url}, error={error_type}, "
                f"endpoint={endpoint}, error_msg={str(e)}",
                exc_info=True
            )
            raise
        except Exception as e:
            error_type = type(e).__name__
            HTTP_REQUEST_ERRORS.labels(error_type=error_type, endpoint=endpoint).inc()
            logger.error(
                f"[HTTP_CLIENT] Unexpected error: {method} {url}, error={error_type}, endpoint={endpoint}",
                exc_info=True
            )
            raise
        finally:
            HTTP_CONCURRENT_REQUESTS.dec()
