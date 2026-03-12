"""
Retry механизм для критических операций.
"""
import asyncio
import logging
from typing import Callable, Awaitable, TypeVar, Optional, List, Type
from functools import wraps

# tenacity опционален - если не установлен, используется простая реализация
try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        RetryError,
    )
    HAS_TENACITY = True
except ImportError:
    HAS_TENACITY = False

logger = logging.getLogger(__name__)

T = TypeVar('T')


def retry_with_backoff(
    max_attempts: int = 3,
    initial_wait: float = 1.0,
    max_wait: float = 10.0,
    exponential_base: float = 2.0,
    retry_on: Optional[List[Type[Exception]]] = None
):
    """
    Декоратор для retry с экспоненциальной задержкой.
    
    Args:
        max_attempts: Максимальное количество попыток
        initial_wait: Начальная задержка в секундах
        max_wait: Максимальная задержка в секундах
        exponential_base: База для экспоненциальной задержки
        retry_on: Список типов исключений для retry (по умолчанию все)
    
    Example:
        @retry_with_backoff(max_attempts=3, initial_wait=1.0)
        async def fetch_data():
            # ...
    """
    if retry_on is None:
        retry_on = [Exception]
    
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except tuple(retry_on) as e:
                    last_exception = e
                    
                    if attempt < max_attempts:
                        # Вычисляем задержку с экспоненциальным ростом
                        wait_time = min(
                            initial_wait * (exponential_base ** (attempt - 1)),
                            max_wait
                        )
                        
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}. "
                            f"Retrying in {wait_time:.2f}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
            
            # Если все попытки исчерпаны, пробрасываем последнее исключение
            raise last_exception
        
        return wrapper
    
    return decorator


# Упрощенная версия без tenacity (если библиотека недоступна)
def simple_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    retry_on: Optional[List[Type[Exception]]] = None
):
    """
    Простой retry декоратор без зависимостей.
    
    Args:
        max_attempts: Максимальное количество попыток
        delay: Задержка между попытками в секундах
        retry_on: Список типов исключений для retry
    """
    if retry_on is None:
        retry_on = [Exception]
    
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except tuple(retry_on) as e:
                    last_exception = e
                    
                    if attempt < max_attempts:
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}. "
                            f"Retrying in {delay}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
            
            raise last_exception
        
        return wrapper
    
    return decorator

