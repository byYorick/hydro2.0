"""
Централизованная обработка ошибок для automation engine.
"""
import logging
import traceback
from typing import Optional, Dict, Any, Callable, Awaitable
from functools import wraps
from prometheus_client import Counter

from exceptions import (
    AutomationError,
    ZoneNotFoundError,
    InvalidConfigurationError,
    InvalidZoneDataError,
    NodeNotFoundError,
    TelemetryError,
    CommandPublishError,
    DatabaseError,
    MQTTError,
)

logger = logging.getLogger(__name__)

# Метрики для отслеживания ошибок
ERROR_COUNTER = Counter(
    "automation_errors_total",
    "Total automation errors by type",
    ["error_type", "zone_id"]
)


def handle_zone_error(
    zone_id: int,
    error: Exception,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Централизованная обработка ошибок зоны.
    
    Args:
        zone_id: ID зоны
        error: Исключение
        context: Дополнительный контекст
    """
    error_type = type(error).__name__
    ERROR_COUNTER.labels(error_type=error_type, zone_id=str(zone_id)).inc()
    
    context_str = f" Context: {context}" if context else ""
    
    if isinstance(error, AutomationError):
        # Обработка кастомных исключений
        logger.error(
            f"Zone {zone_id}: {error.message}{context_str}",
            extra={
                "zone_id": zone_id,
                "error_type": error_type,
                "error_details": error.details,
                "context": context,
            },
            exc_info=True
        )
    else:
        # Обработка стандартных исключений
        logger.error(
            f"Zone {zone_id}: Unexpected error: {error}{context_str}",
            extra={
                "zone_id": zone_id,
                "error_type": error_type,
                "context": context,
            },
            exc_info=True
        )


def handle_automation_error(
    error: Exception,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Централизованная обработка общих ошибок автоматизации.
    
    Args:
        error: Исключение
        context: Дополнительный контекст
    """
    error_type = type(error).__name__
    ERROR_COUNTER.labels(error_type=error_type, zone_id="global").inc()
    
    context_str = f" Context: {context}" if context else ""
    
    if isinstance(error, AutomationError):
        logger.error(
            f"Automation error: {error.message}{context_str}",
            extra={
                "error_type": error_type,
                "error_details": error.details,
                "context": context,
            },
            exc_info=True
        )
    else:
        logger.error(
            f"Unexpected automation error: {error}{context_str}",
            extra={
                "error_type": error_type,
                "context": context,
            },
            exc_info=True
        )


def error_handler(
    zone_id: Optional[int] = None,
    default_return: Any = None,
    reraise: bool = False
):
    """
    Декоратор для обработки ошибок в функциях обработки зон.
    
    Args:
        zone_id: ID зоны (если None, будет извлечен из аргументов функции)
        default_return: Значение по умолчанию при ошибке
        reraise: Пробросить исключение после логирования
    
    Example:
        @error_handler(zone_id=1, default_return=None)
        async def process_zone(zone_id: int):
            # ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Извлекаем zone_id из аргументов, если не указан
                actual_zone_id = zone_id
                if actual_zone_id is None:
                    # Пытаемся найти zone_id в аргументах
                    if args and isinstance(args[0], int):
                        actual_zone_id = args[0]
                    elif 'zone_id' in kwargs:
                        actual_zone_id = kwargs['zone_id']
                
                if actual_zone_id:
                    handle_zone_error(actual_zone_id, e, {"function": func.__name__})
                else:
                    handle_automation_error(e, {"function": func.__name__})
                
                if reraise:
                    raise
                return default_return
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                actual_zone_id = zone_id
                if actual_zone_id is None:
                    if args and isinstance(args[0], int):
                        actual_zone_id = args[0]
                    elif 'zone_id' in kwargs:
                        actual_zone_id = kwargs['zone_id']
                
                if actual_zone_id:
                    handle_zone_error(actual_zone_id, e, {"function": func.__name__})
                else:
                    handle_automation_error(e, {"function": func.__name__})
                
                if reraise:
                    raise
                return default_return
        
        # Определяем, асинхронная ли функция
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

