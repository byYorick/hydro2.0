"""
Единый HTTP клиент пул для всех запросов к Laravel API.

Обеспечивает:
- Единый httpx.AsyncClient на процесс для переиспользования соединений
- Semaphore для лимита параллелизма (backpressure)
- Exponential backoff с jitter
- Метрики для мониторинга
"""
import asyncio
import logging
import random
from typing import Optional
import httpx
from prometheus_client import Counter, Histogram, Gauge

from .env import get_settings

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

# Глобальный HTTP клиент
_http_client: Optional[httpx.AsyncClient] = None

# Semaphore для лимита параллелизма (backpressure)
# По умолчанию 50 одновременных запросов
MAX_CONCURRENT_REQUESTS = 50
_http_semaphore: Optional[asyncio.Semaphore] = None


def get_max_concurrent_requests() -> int:
    """Получить максимальное количество параллельных запросов из настроек."""
    s = get_settings()
    if hasattr(s, 'http_max_concurrent_requests'):
        return s.http_max_concurrent_requests
    return MAX_CONCURRENT_REQUESTS


async def get_http_client() -> httpx.AsyncClient:
    """
    Возвращает единый глобальный httpx.AsyncClient для процесса.
    Создаёт клиент при первом вызове.
    """
    global _http_client, _http_semaphore
    
    if _http_client is None:
        s = get_settings()
        timeout = httpx.Timeout(10.0, connect=5.0)
        limits = httpx.Limits(
            max_keepalive_connections=20,
            max_connections=100,
            keepalive_expiry=30.0
        )
        _http_client = httpx.AsyncClient(
            timeout=timeout,
            limits=limits
        )
        logger.info("Created unified httpx.AsyncClient for Laravel API")
    
    if _http_semaphore is None:
        max_concurrent = get_max_concurrent_requests()
        _http_semaphore = asyncio.Semaphore(max_concurrent)
        logger.info(f"Created HTTP semaphore with max_concurrent={max_concurrent}")
    
    return _http_client


async def close_http_client():
    """Закрывает единый HTTP клиент."""
    global _http_client, _http_semaphore
    
    if _http_client is not None:
        try:
            await _http_client.aclose()
            logger.info("Closed unified httpx.AsyncClient")
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.warning("HTTP client close skipped: event loop is closed")
            else:
                raise
        finally:
            _http_client = None
    
    _http_semaphore = None


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
    Выполняет HTTP запрос с использованием единого клиента и semaphore.
    
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
    semaphore = _http_semaphore
    
    if semaphore is None:
        # Fallback если semaphore не инициализирован
        semaphore = asyncio.Semaphore(get_max_concurrent_requests())
    
    # Ждём слот в semaphore (backpressure)
    wait_start = asyncio.get_event_loop().time()
    async with semaphore:
        wait_duration = asyncio.get_event_loop().time() - wait_start
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
            headers_info = kwargs.get('headers', {})
            json_info = kwargs.get('json', {})
            logger.info(
                f"[HTTP_CLIENT] Sending request: {method} {url}, endpoint={endpoint}, "
                f"has_auth_header={bool(headers_info.get('Authorization'))}, "
                f"json_keys={list(json_info.keys()) if json_info else 'none'}"
            )
            
            request_start = asyncio.get_event_loop().time()
            method_func = getattr(client, method.lower())
            response = await method_func(url, **kwargs)
            request_duration = asyncio.get_event_loop().time() - request_start
            
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
