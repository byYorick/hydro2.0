"""
Утилиты для работы со временем.
"""

import time
from typing import Optional


def current_timestamp_ms() -> int:
    """
    Получить текущий timestamp в миллисекундах.
    
    Returns:
        Unix timestamp в миллисекундах
    """
    return int(time.time() * 1000)


def current_timestamp_s() -> int:
    """
    Получить текущий timestamp в секундах.
    
    Returns:
        Unix timestamp в секундах
    """
    return int(time.time())


def sleep_ms(milliseconds: int):
    """
    Заснуть на указанное количество миллисекунд.
    
    Args:
        milliseconds: Количество миллисекунд
    """
    time.sleep(milliseconds / 1000.0)


def format_duration_ms(duration_ms: int) -> str:
    """
    Форматировать длительность в миллисекундах в читаемый вид.
    
    Args:
        duration_ms: Длительность в миллисекундах
    
    Returns:
        Отформатированная строка
    """
    if duration_ms < 1000:
        return f"{duration_ms}ms"
    elif duration_ms < 60000:
        return f"{duration_ms / 1000:.1f}s"
    else:
        minutes = duration_ms // 60000
        seconds = (duration_ms % 60000) // 1000
        return f"{minutes}m{seconds}s"

