"""Общие фикстуры для unit-тестов ae4 волны 1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ae4.domain.planting import LightIntegralCursor, PhaseTargets, TelemetrySample

TZ = "Europe/Moscow"
UTC = timezone.utc


def phase(**kwargs: object) -> PhaseTargets:
    started = kwargs.pop("started_at", datetime(2026, 6, 1, 6, 0, tzinfo=UTC))
    defaults: dict[str, object] = {
        "phase_id": 1,
        "started_at": started,
        "interval_sec": 3600,
        "duration_sec": 60,
    }
    defaults.update(kwargs)
    return PhaseTargets(**defaults)  # type: ignore[arg-type]


def fresh_cursor(*, at: datetime | None = None) -> LightIntegralCursor:
    return LightIntegralCursor(
        accumulated=0.0,
        last_accounted_ts=at,
        unit="lux·s",
        status="ok",
        last_value=None,
    )


def sample(
    *,
    metric_type: str,
    channel: str,
    value: float,
    ts: datetime,
    unit: str | None = None,
) -> TelemetrySample:
    return TelemetrySample(
        metric_type=metric_type,
        channel=channel,
        value=value,
        ts=ts,
        unit=unit,
    )


def later(base: datetime, **delta: int) -> datetime:
    return base + timedelta(**delta)
