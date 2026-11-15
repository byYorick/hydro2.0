"""Локальные окна теплицы.

Внутренние метки остаются timezone-aware UTC. В пояс теплицы конвертируется
только момент сравнения с окном HH:MM или местной датой. Naive datetime явно
считается UTC (контракт ``utcnow_naive``), а не локальным временем процесса.
Невалидное IANA-имя отклоняет конфиг: тихого отката на UTC нет.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_GREENHOUSE_TIMEZONE = "Europe/Simferopol"


class InvalidGreenhouseTimezone(ValueError):
    """IANA-имя в конфиге не резолвится. Команды по такому конфигу не публикуются."""

    def __init__(self, name: object) -> None:
        self.name = name
        super().__init__(f"invalid greenhouse timezone: {name!r}")


def zoneinfo_for(name: object | None) -> ZoneInfo:
    """Пустое имя → Europe/Simferopol. Невалидное имя → InvalidGreenhouseTimezone."""
    if name is None or (isinstance(name, str) and not name.strip()):
        text = DEFAULT_GREENHOUSE_TIMEZONE
    elif isinstance(name, str):
        text = name.strip()
    else:
        raise InvalidGreenhouseTimezone(name)
    try:
        return ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidGreenhouseTimezone(text) from exc


def canonical_timezone_name(name: object | None) -> str:
    """Каноническое IANA-имя. Пустое значение заменяется дефолтом теплицы."""
    if name is None or (isinstance(name, str) and not name.strip()):
        text = DEFAULT_GREENHOUSE_TIMEZONE
    elif isinstance(name, str):
        text = name.strip()
    else:
        raise InvalidGreenhouseTimezone(name)
    zoneinfo_for(text)
    return text


def optional_timezone_name(name: object | None) -> str | None:
    """None и пустая строка остаются незаданными. Непустое имя обязано быть IANA."""
    if name is None:
        return None
    if not isinstance(name, str):
        raise InvalidGreenhouseTimezone(name)
    text = name.strip()
    if not text:
        return None
    zoneinfo_for(text)
    return text


def as_aware_utc(moment: datetime) -> datetime:
    """Naive datetime явно помечается как UTC. Aware конвертируется в UTC."""
    if not isinstance(moment, datetime):
        raise TypeError("moment must be datetime")
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def greenhouse_local(moment: datetime, timezone_name: object | None) -> datetime:
    """Локальное время теплицы для сравнения окон. Исходный moment не меняется."""
    return as_aware_utc(moment).astimezone(zoneinfo_for(timezone_name))


def local_minutes(moment: datetime, timezone_name: object | None) -> int:
    local = greenhouse_local(moment, timezone_name)
    return local.hour * 60 + local.minute


def greenhouse_local_date(moment: datetime, timezone_name: object | None) -> str:
    return greenhouse_local(moment, timezone_name).date().isoformat()


def greenhouse_local_midnight_utc(moment: datetime, timezone_name: object | None) -> datetime:
    """Местная полночь как timezone-aware UTC."""
    local = greenhouse_local(moment, timezone_name)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc)
