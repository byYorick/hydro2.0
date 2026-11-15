"""Окно полива в местном времени теплицы.

Та же минутная арифметика, что у day/night smart_soil: начало включительно,
конец исключительно, окно может пересекать полночь. Naive datetime — UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ae3lite.domain.services.greenhouse_clock import greenhouse_local, local_minutes


@dataclass(frozen=True)
class LocalWindow:
    inside: bool
    invalid: bool
    start_utc: datetime | None


def resolve_local_window(
    *,
    now: datetime,
    day_start_time: str | None,
    day_hours: float | None,
    timezone_name: str | None,
) -> LocalWindow:
    if not day_start_time or day_hours is None:
        return LocalWindow(inside=True, invalid=False, start_utc=None)

    raw = str(day_start_time).strip()
    if not raw:
        return LocalWindow(inside=True, invalid=False, start_utc=None)

    parts = raw.split(":")
    if len(parts) < 2:
        return LocalWindow(inside=False, invalid=True, start_utc=None)

    try:
        start_h = int(parts[0])
        start_m = int(parts[1])
    except ValueError:
        return LocalWindow(inside=False, invalid=True, start_utc=None)

    if start_h < 0 or start_h > 23 or start_m < 0 or start_m > 59:
        return LocalWindow(inside=False, invalid=True, start_utc=None)

    try:
        hours = float(day_hours)
    except (TypeError, ValueError):
        return LocalWindow(inside=False, invalid=True, start_utc=None)

    if hours <= 0:
        return LocalWindow(inside=False, invalid=False, start_utc=None)
    if hours >= 24:
        return LocalWindow(inside=True, invalid=False, start_utc=None)

    start_min = start_h * 60 + start_m
    end_min = (start_min + int(round(hours * 60))) % (24 * 60)
    now_min = local_minutes(now, timezone_name)

    if start_min == end_min:
        return LocalWindow(inside=False, invalid=True, start_utc=None)
    if start_min < end_min:
        inside = start_min <= now_min < end_min
    else:
        inside = now_min >= start_min or now_min < end_min
    if not inside:
        return LocalWindow(inside=False, invalid=False, start_utc=None)

    local = greenhouse_local(now, timezone_name)
    start_local = local.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    if start_min > end_min and now_min < end_min:
        start_local = start_local - timedelta(days=1)
    return LocalWindow(inside=True, invalid=False, start_utc=start_local.astimezone(timezone.utc))


def resolve_effective_irrigation_window(
    *,
    now: datetime,
    day_start_time: str | None,
    day_hours: float | None,
    timezone_name: str | None,
    inset_start_sec: int,
    inset_end_sec: int,
) -> LocalWindow:
    """Окно полива: day_start … day_start+day_hours, сдвинутое отступами.

    Начало сдвигается на ``inset_start_sec`` вперёд, конец — на ``inset_end_sec``
    назад. Пустой результат (отступы съели окно) — invalid.
    """
    base = resolve_local_window(
        now=now,
        day_start_time=day_start_time,
        day_hours=day_hours,
        timezone_name=timezone_name,
    )
    if base.invalid or not day_start_time or day_hours is None:
        return LocalWindow(inside=False, invalid=True, start_utc=None)
    try:
        hours = float(day_hours)
    except (TypeError, ValueError):
        return LocalWindow(inside=False, invalid=True, start_utc=None)
    if not (0.0 < hours < 24.0):
        return LocalWindow(inside=False, invalid=True, start_utc=None)
    duration_sec = int(round(hours * 60)) * 60
    if inset_start_sec < 0 or inset_end_sec < 0 or inset_start_sec + inset_end_sec >= duration_sec:
        return LocalWindow(inside=False, invalid=True, start_utc=None)

    parts = str(day_start_time).strip().split(":")
    start_h = int(parts[0])
    start_m = int(parts[1])
    local = greenhouse_local(now, timezone_name)
    start_clock = local.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    for shift in (-1, 0, 1):
        base_start = start_clock + timedelta(days=shift)
        effective_start = base_start + timedelta(seconds=int(inset_start_sec))
        effective_end = base_start + timedelta(seconds=duration_sec - int(inset_end_sec))
        if effective_start <= local < effective_end:
            return LocalWindow(
                inside=True,
                invalid=False,
                start_utc=effective_start.astimezone(timezone.utc),
            )
    return LocalWindow(inside=False, invalid=False, start_utc=None)
