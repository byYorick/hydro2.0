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


def to_naive_utc(dt: datetime) -> datetime:
    """Привести datetime к naive UTC (для PostgreSQL TIMESTAMP WITHOUT TIME ZONE).

    - aware datetime → конвертируется в UTC и tzinfo сбрасывается;
    - naive datetime → возвращается как есть (предполагается уже UTC).
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def utcnow_naive() -> datetime:
    """
    Возвращает текущее время в UTC как naive datetime (без tzinfo).

    Используется в местах, где БД или внешний контракт ожидает naive UTC
    (PostgreSQL TIMESTAMP WITHOUT TIME ZONE).

    Returns:
        datetime: Текущее время в UTC без tzinfo
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

