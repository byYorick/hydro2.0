"""
Утилиты для работы со временем.
Обеспечивает единообразное использование timezone-aware UTC datetime.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """
    Возвращает текущее время в UTC как timezone-aware datetime.
    
    Замена для datetime.utcnow() (deprecated) и datetime.now().
    Всегда возвращает aware datetime с timezone.utc.
    
    Returns:
        datetime: Текущее время в UTC с timezone.utc
    """
    return datetime.now(timezone.utc)

