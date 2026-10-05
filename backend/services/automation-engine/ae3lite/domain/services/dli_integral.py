"""Потолок DLI по колонке фазы dli_target.

dli_mol = sum(ppfd * dt_sec) / 1_000_000.
dt_sec — до следующего образца и не больше dli_stale_gap_sec (дефолт 600).
Люкс не конвертируется. Общего писателя с Laravel нет.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

DLI_STALE_GAP_SEC = 600
DLI_CHECK_INTERVAL_SEC = 900
PPFD_UNITS = frozenset({"ppfd", "umol_m2_s"})
LUX_MAIN_CHANNELS = ("light", "light_level", "lux_main")
EXPLICIT_LIGHT_CHANNEL_KEYS = ("sensor_channel", "light_channel", "source_channel", "outside_channel")


@dataclass(frozen=True)
class DliTickDecision:
    duty: int
    status: str
    dli_mol: float | None
    local_date: str


def positive_dli_target(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0 or value != value:
        return None
    return value


def configured_channel_unit(column_unit: Any, config: Any) -> str:
    column = str(column_unit or "").strip()
    parsed = config
    if isinstance(parsed, str) and parsed.strip():
        import json

        try:
            parsed = json.loads(parsed)
        except (TypeError, ValueError):
            parsed = None
    config_unit = ""
    if isinstance(parsed, Mapping):
        raw = parsed.get("unit")
        if raw is not None and not isinstance(raw, (Mapping, list)):
            config_unit = str(raw).strip()
    if column and config_unit and column != config_unit:
        return "mixed"
    return column or config_unit


def explicit_light_channel(lighting_targets: Mapping[str, Any] | None) -> str | None:
    if not isinstance(lighting_targets, Mapping):
        return None
    for key in EXPLICIT_LIGHT_CHANNEL_KEYS:
        raw = lighting_targets.get(key)
        if raw is None:
            continue
        name = str(raw).strip().lower()
        if name:
            return name
    return None


def _channel_name(row: Mapping[str, Any]) -> str:
    return str(row.get("channel") or "").strip().lower()


def _metric(row: Mapping[str, Any]) -> str:
    return str(row.get("metric") or "").strip().upper()


def _scope(row: Mapping[str, Any]) -> str:
    return str(row.get("scope") or "").strip().lower()


def _is_outside_row(row: Mapping[str, Any]) -> bool:
    name = _channel_name(row)
    return (
        name in {"outside_light", "out_light", "outdoor_light"}
        or _metric(row) == "OUTSIDE_LIGHT"
        or _scope(row) == "outside"
    )


def _is_lux_main_row(row: Mapping[str, Any]) -> bool:
    if _is_outside_row(row):
        return False
    name = _channel_name(row)
    return name in LUX_MAIN_CHANNELS or _metric(row) == "LIGHT_INTENSITY"


def select_light_channel_row(
    rows: Sequence[Mapping[str, Any]],
    *,
    explicit_channel: str | None,
) -> Mapping[str, Any] | None:
    ranked: list[tuple[int, int, Mapping[str, Any]]] = []
    explicit = (explicit_channel or "").strip().lower()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) and not hasattr(row, "get"):
            continue
        name = _channel_name(row)
        metric = _metric(row)
        if explicit:
            if name != explicit and metric != explicit.upper() and name != explicit.replace(" ", "_"):
                continue
        elif not _is_lux_main_row(row):
            continue
        preference = LUX_MAIN_CHANNELS.index(name) if name in LUX_MAIN_CHANNELS else len(LUX_MAIN_CHANNELS)
        row_id = row.get("id")
        try:
            sort_id = int(row_id) if row_id is not None else index
        except (TypeError, ValueError):
            sort_id = index
        ranked.append((preference, sort_id, row))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]))
    return ranked[0][2]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_ts(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return _as_utc(raw)
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        return _as_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def zone_timezone(name: Any) -> ZoneInfo | timezone:
    if isinstance(name, str) and name.strip():
        try:
            return ZoneInfo(name.strip())
        except Exception:
            return timezone.utc
    return timezone.utc


def local_date_of(moment: datetime, timezone_name: Any) -> str:
    return _as_utc(moment).astimezone(zone_timezone(timezone_name)).date().isoformat()


def integrate_ppfd(
    samples: Sequence[tuple[datetime, float]],
    *,
    gap_sec: int = DLI_STALE_GAP_SEC,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> tuple[float | None, str]:
    """Возвращает (моль, status) status = ok | gap | sensor_unavailable.

    100 µmol/м²/с на 10 000 с = 1.0 моль/м², если дыра не больше gap_sec.
    """
    gap = max(0, int(gap_sec))
    start = _as_utc(window_start) if window_start is not None else None
    end = _as_utc(window_end) if window_end is not None else None
    points: list[tuple[datetime, float]] = []
    for ts, value in samples:
        moment = _as_utc(ts)
        if start is not None and moment < start:
            continue
        if end is not None and moment > end:
            continue
        try:
            ppfd = float(value)
        except (TypeError, ValueError):
            continue
        points.append((moment, ppfd))
    points.sort(key=lambda item: item[0])
    if not points:
        return None, "sensor_unavailable"

    total = 0.0
    for index, (moment, ppfd) in enumerate(points[:-1]):
        dt = (points[index + 1][0] - moment).total_seconds()
        if dt > gap:
            return None, "gap"
        if dt > 0:
            total += ppfd * dt
    return round(total / 1_000_000, 6), "ok"


def decide_on_tick_duty(
    *,
    requested_duty: int,
    dli_target: float | None,
    unit: str | None,
    samples: Sequence[tuple[datetime, float]],
    gap_sec: int = DLI_STALE_GAP_SEC,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    timezone_name: Any = "UTC",
) -> DliTickDecision:
    moment = window_end or datetime.now(timezone.utc)
    local_date = local_date_of(moment, timezone_name)
    duty = max(0, min(100, int(requested_duty)))
    target = positive_dli_target(dli_target)
    if target is None:
        mol, series_status = _series_mol(unit, samples, gap_sec=gap_sec, window_start=window_start, window_end=window_end)
        return DliTickDecision(
            duty=duty,
            status="not_configured",
            dli_mol=mol if series_status == "ok" else None,
            local_date=local_date,
        )

    mol, series_status = _series_mol(unit, samples, gap_sec=gap_sec, window_start=window_start, window_end=window_end)
    if series_status == "sensor_unavailable":
        return DliTickDecision(duty=duty, status="sensor_unavailable", dli_mol=None, local_date=local_date)
    if series_status == "gap":
        return DliTickDecision(duty=duty, status="gap", dli_mol=None, local_date=local_date)
    assert mol is not None
    if mol >= target:
        return DliTickDecision(duty=0, status="capped", dli_mol=mol, local_date=local_date)
    return DliTickDecision(duty=duty, status="within_target", dli_mol=mol, local_date=local_date)


def _series_mol(
    unit: str | None,
    samples: Sequence[tuple[datetime, float]],
    *,
    gap_sec: int,
    window_start: datetime | None,
    window_end: datetime | None,
) -> tuple[float | None, str]:
    token = str(unit or "").strip()
    if token not in PPFD_UNITS:
        return None, "sensor_unavailable"
    return integrate_ppfd(samples, gap_sec=gap_sec, window_start=window_start, window_end=window_end)


def parse_dli_moment(raw: Any) -> datetime | None:
    return _parse_ts(raw)


def parse_observation_samples(observation: Mapping[str, Any] | None) -> list[tuple[datetime, float]]:
    if not isinstance(observation, Mapping):
        return []
    raw_samples = observation.get("samples")
    if not isinstance(raw_samples, Sequence) or isinstance(raw_samples, (str, bytes)):
        return []
    points: list[tuple[datetime, float]] = []
    for item in raw_samples:
        if isinstance(item, Mapping):
            moment = _parse_ts(item.get("ts"))
            raw_value = item.get("value")
        elif isinstance(item, Sequence) and len(item) >= 2:
            moment = _parse_ts(item[0]) if not isinstance(item[0], datetime) else _as_utc(item[0])
            raw_value = item[1]
        else:
            continue
        if moment is None:
            continue
        try:
            points.append((moment, float(raw_value)))
        except (TypeError, ValueError):
            continue
    return points
