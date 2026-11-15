"""Полив radiation_sum_v1: импульс по сумме PAR внутри теплицы.

Интеграл — ``dli_integral.integrate_ppfd`` (разрыв длиннее gap не интерполируется).
Окно — местное окно теплицы. Суточные счётчики приходят из истории команд,
не из памяти процесса. EC по дренажу здесь не применяется.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from ae3lite.config.schema.runtime_plan import RadiationSumConfig
from ae3lite.domain.services.dli_integral import integrate_ppfd
from ae3lite.domain.services.greenhouse_clock import (
    DEFAULT_GREENHOUSE_TIMEZONE,
    InvalidGreenhouseTimezone,
    as_aware_utc,
    greenhouse_local_date,
)
from ae3lite.domain.services.irrigation_window import LocalWindow, resolve_local_window

logger = logging.getLogger(__name__)

REASON_NIGHT = "radiation_sum_night"
REASON_MIN_INTERVAL = "radiation_sum_min_interval"
REASON_BELOW = "radiation_sum_below_threshold"
REASON_DAILY_CAP = "radiation_sum_daily_cap"
REASON_THRESHOLD = "radiation_sum_threshold_reached"
REASON_MAX_INTERVAL = "radiation_sum_max_interval"
REASON_FALLBACK = "radiation_sum_fallback_timer"
REASON_FALLBACK_WAIT = "radiation_sum_fallback_wait"
REASON_LUX = "radiation_sum_lux_proxy"
REASON_CONFIG = "radiation_sum_config_invalid"
REASON_WINDOW = "radiation_sum_window_missing"
REASON_LEDGER = "radiation_sum_ledger_unavailable"
REASON_TIMEZONE = "radiation_sum_timezone_mismatch"

ALERT_SENSOR_SILENT = "biz_sensor_silent"
ALERT_DAILY_CAP = "biz_irrigation_daily_cap"
ALERT_DEGRADED = "biz_irrigation_decision_degraded"

QUIET_SKIP_REASONS = frozenset({
    REASON_MIN_INTERVAL,
    REASON_BELOW,
    REASON_NIGHT,
    REASON_DAILY_CAP,
    REASON_FALLBACK_WAIT,
})


def radiation_config_error(payload: Mapping[str, Any] | None) -> str | None:
    """None, если конфиг принят. Иначе текст отказа. Значения не клампятся."""
    try:
        RadiationSumConfig.model_validate(dict(payload or {}))
    except ValidationError as exc:
        messages = [str(item.get("msg") or "invalid") for item in exc.errors()]
        return "; ".join(messages)[:500]
    return None


def placeholder_radiation_config() -> dict[str, Any]:
    """Валидный каркас, чтобы план зоны собрался. Стратегия его не исполняет."""
    return RadiationSumConfig.model_validate(
        {
            "threshold_par_mol_m2": 1.3,
            "max_interval_sec": 5400,
            "fallback_interval_sec": 2700,
            "max_daily_volume_l": 1.0,
        }
    ).model_dump(mode="python")


def build_radiation_decision(raw_config: Mapping[str, Any] | None) -> dict[str, Any]:
    error = radiation_config_error(raw_config)
    if error:
        return {
            "strategy": "radiation_sum_v1",
            "config": placeholder_radiation_config(),
            "config_error": error,
        }
    model = RadiationSumConfig.model_validate(dict(raw_config or {}))
    return {
        "strategy": "radiation_sum_v1",
        "config": model.model_dump(mode="python"),
        "config_error": None,
    }


def configured_pulse_liters(config: RadiationSumConfig) -> float:
    plants = float(config.plant_count) if config.plant_count else 1.0
    return float(config.pulse_ml_per_plant) * plants / 1000.0


def pulse_liters_from_mapping(raw: Any, *, fallback_liters: float) -> float:
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return float(fallback_liters)
    if not isinstance(raw, Mapping):
        return float(fallback_liters)
    try:
        ml = float(raw["pulse_ml_per_plant"])
    except (KeyError, TypeError, ValueError):
        return float(fallback_liters)
    plants = 1.0
    if raw.get("plant_count") is not None:
        try:
            plants = float(raw["plant_count"])
        except (TypeError, ValueError):
            return float(fallback_liters)
    if ml <= 0 or plants <= 0:
        return float(fallback_liters)
    return ml * plants / 1000.0


def select_local_day_pulses(
    pulses: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    timezone_name: str,
) -> list[Mapping[str, Any]]:
    day = greenhouse_local_date(now, timezone_name)
    selected: list[Mapping[str, Any]] = []
    for pulse in pulses:
        moment = pulse.get("finished_at")
        if not isinstance(moment, datetime):
            continue
        if greenhouse_local_date(moment, timezone_name) == day:
            selected.append(pulse)
    return selected


def _alert(code: str, message: str, severity: str, dedupe_key: str) -> dict[str, str]:
    return {"code": code, "message": message, "severity": severity, "dedupe_key": dedupe_key}


def sensor_silent_alert(zone_id: int) -> dict[str, str]:
    return _alert(
        ALERT_SENSOR_SILENT,
        "PAR молчит, равен нулю днём или в ряде дыра. Полив перешёл на резерв.",
        "warning",
        f"ae3_radiation_sum|sensor_silent|z{int(zone_id)}",
    )


def daily_cap_alert(zone_id: int) -> dict[str, str]:
    return _alert(
        ALERT_DAILY_CAP,
        "Суточный лимит полива исчерпан: новые импульсы не запускаются.",
        "error",
        f"ae3_radiation_sum|daily_cap|z{int(zone_id)}",
    )


def _degraded_alert(zone_id: int, reason: str) -> dict[str, str]:
    return _alert(
        ALERT_DEGRADED,
        "Полив по сумме PAR снова идёт по датчику.",
        "warning",
        f"ae3_irrigation_decision|degraded_run|z{int(zone_id)}|{reason}",
    )


def recovery_alerts(zone_id: int, *, clear_cap: bool) -> list[dict[str, str]]:
    alerts = [
        sensor_silent_alert(zone_id),
        _degraded_alert(zone_id, REASON_FALLBACK),
        _degraded_alert(zone_id, REASON_LUX),
    ]
    if clear_cap:
        alerts.append(daily_cap_alert(zone_id))
    return alerts


def _decision(
    *,
    outcome: str,
    reason: str,
    degraded: bool = False,
    details: dict[str, Any] | None = None,
) -> Any:
    from ae3lite.domain.services.irrigation_decision_controller import IrrigationDecision

    return IrrigationDecision(outcome=outcome, reason_code=reason, degraded=degraded, details=details or {})


def parse_samples(raw: Any) -> list[tuple[datetime, float]]:
    rows: Any
    if isinstance(raw, Mapping):
        rows = raw.get("samples")
    else:
        rows = raw
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    points: list[tuple[datetime, float]] = []
    for row in rows:
        if isinstance(row, Mapping):
            moment = row.get("ts")
            value = row.get("value")
        elif isinstance(row, tuple) and len(row) >= 2:
            moment, value = row[0], row[1]
        else:
            continue
        if not isinstance(moment, datetime):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        points.append((as_aware_utc(moment), number))
    points.sort(key=lambda item: item[0])
    return points


def _series_mol(
    samples: Sequence[tuple[datetime, float]],
    *,
    now: datetime,
    anchor: datetime,
    stale_after_sec: int,
    gap_sec: int,
    zero_as_stale: bool,
) -> tuple[str, float | None]:
    if not samples:
        return "stale", None
    latest_ts, latest_value = samples[-1]
    age = (as_aware_utc(now) - as_aware_utc(latest_ts)).total_seconds()
    if age > float(stale_after_sec):
        return "stale", None
    if zero_as_stale and latest_value == 0.0:
        return "stale", None
    mol, status = integrate_ppfd(samples, gap_sec=gap_sec, window_start=anchor, window_end=now)
    if status != "ok" or mol is None:
        return "stale", None
    return "ok", float(mol)


def resolve_radiation_window(
    *,
    runtime: Any,
    config: RadiationSumConfig,
    now: datetime,
) -> tuple[LocalWindow | None, str, str | None]:
    """(окно, timezone, код отказа). Отказ не запускает полив."""
    lighting = getattr(getattr(runtime, "day_night_config", None), "lighting", None)
    greenhouse_tz = str(getattr(lighting, "timezone", "") or "").strip() or None
    config_tz = config.timezone
    if greenhouse_tz and config_tz and greenhouse_tz != config_tz:
        return None, greenhouse_tz, REASON_TIMEZONE
    timezone_name = greenhouse_tz or config_tz or DEFAULT_GREENHOUSE_TIMEZONE
    start = str(getattr(lighting, "day_start_time", "") or "").strip() or None
    hours_raw = getattr(lighting, "day_hours", None)
    try:
        hours = float(hours_raw) if hours_raw is not None else None
    except (TypeError, ValueError):
        hours = None
    if not start or hours is None or not (0.0 < hours < 24.0):
        return LocalWindow(inside=False, invalid=True, start_utc=None), timezone_name, REASON_WINDOW
    try:
        window = resolve_local_window(
            now=now,
            day_start_time=start,
            day_hours=hours,
            timezone_name=timezone_name,
        )
    except InvalidGreenhouseTimezone:
        return None, timezone_name, REASON_TIMEZONE
    if window.invalid or (window.inside and window.start_utc is None):
        return window, timezone_name, REASON_WINDOW
    return window, timezone_name, None


def _latest_pulse(pulses: Sequence[Mapping[str, Any]]) -> datetime | None:
    latest: datetime | None = None
    for pulse in pulses:
        moment = pulse.get("finished_at")
        if not isinstance(moment, datetime):
            continue
        aware = as_aware_utc(moment)
        if latest is None or aware > latest:
            latest = aware
    return latest


def decide_radiation_sum(
    *,
    config: RadiationSumConfig,
    now: datetime,
    zone_id: int,
    timezone_name: str,
    window: LocalWindow,
    pulses: Sequence[Mapping[str, Any]],
    par_samples: Sequence[tuple[datetime, float]] | None,
    lux_samples: Sequence[tuple[datetime, float]] | None,
) -> Any:
    """Чистое решение. ``par_samples is None`` — ряд прочитать не удалось, это stale."""
    now_utc = as_aware_utc(now)
    if not window.inside or window.start_utc is None:
        return _decision(
            outcome="skip",
            reason=REASON_NIGHT,
            details={"timezone": timezone_name},
        )

    anchor = as_aware_utc(window.start_utc)
    last_pulse = _latest_pulse(pulses)
    if last_pulse is not None and last_pulse > anchor:
        anchor = last_pulse
    elapsed = max(0.0, (now_utc - anchor).total_seconds())
    next_liters = configured_pulse_liters(config)
    day_pulses = select_local_day_pulses(pulses, now=now_utc, timezone_name=timezone_name)
    used_liters = 0.0
    for pulse in day_pulses:
        try:
            used_liters += float(pulse.get("liters") or 0.0)
        except (TypeError, ValueError):
            used_liters += next_liters
    capped = len(day_pulses) >= int(config.max_daily_pulses) or (
        used_liters + next_liters > float(config.max_daily_volume_l) + 1e-9
    )

    par_state, par_mol = ("stale", None)
    if par_samples is not None:
        par_state, par_mol = _series_mol(
            par_samples,
            now=now_utc,
            anchor=anchor,
            stale_after_sec=int(config.stale_after_sec),
            gap_sec=int(config.max_gap_sec),
            zero_as_stale=bool(config.zero_daytime_as_stale),
        )

    base = {
        "timezone": timezone_name,
        "elapsed_sec": round(elapsed, 3),
        "sum_par_mol_m2": par_mol,
        "pulse_liters": next_liters,
        "daily_pulses": len(day_pulses),
        "daily_liters": round(used_liters, 6),
        "approx": False,
        "anchor": anchor.isoformat(),
    }

    if capped:
        details = dict(base)
        details["raise_alerts"] = [daily_cap_alert(zone_id)]
        if par_state == "ok":
            details["resolve_alerts"] = recovery_alerts(zone_id, clear_cap=False)
        return _decision(outcome="skip", reason=REASON_DAILY_CAP, details=details)

    if par_state == "ok":
        details = dict(base)
        details["resolve_alerts"] = recovery_alerts(zone_id, clear_cap=True)
        if elapsed < float(config.min_interval_sec):
            return _decision(outcome="skip", reason=REASON_MIN_INTERVAL, details=details)
        if par_mol is not None and par_mol >= float(config.threshold_par_mol_m2):
            return _decision(outcome="run", reason=REASON_THRESHOLD, details=details)
        if elapsed >= float(config.max_interval_sec):
            return _decision(outcome="run", reason=REASON_MAX_INTERVAL, details=details)
        return _decision(outcome="skip", reason=REASON_BELOW, details=details)

    lux_state, lux_mol = ("stale", None)
    if config.allow_lux_proxy and lux_samples:
        converted = [(moment, value * float(config.lux_proxy_umol_per_lux)) for moment, value in lux_samples]
        lux_state, lux_mol = _series_mol(
            converted,
            now=now_utc,
            anchor=anchor,
            stale_after_sec=int(config.stale_after_sec),
            gap_sec=int(config.max_gap_sec),
            zero_as_stale=True,
        )

    details = dict(base)
    details["raise_alerts"] = [sensor_silent_alert(zone_id)]
    details["source"] = "par"
    if lux_state == "ok":
        details["approx"] = True
        details["sum_par_mol_m2"] = lux_mol
        details["source"] = "lux_proxy"
        if elapsed < float(config.min_interval_sec):
            return _decision(outcome="skip", reason=REASON_MIN_INTERVAL, degraded=True, details=details)
        if lux_mol is not None and (
            lux_mol >= float(config.threshold_par_mol_m2) or elapsed >= float(config.max_interval_sec)
        ):
            return _decision(outcome="degraded_run", reason=REASON_LUX, degraded=True, details=details)
        return _decision(outcome="skip", reason=REASON_BELOW, degraded=True, details=details)

    if elapsed >= float(config.fallback_interval_sec):
        details["source"] = "fallback_timer"
        return _decision(outcome="degraded_run", reason=REASON_FALLBACK, degraded=True, details=details)
    details["source"] = "fallback_timer"
    return _decision(outcome="skip", reason=REASON_FALLBACK_WAIT, degraded=True, details=details)


class RadiationSumDecisionStrategy:
    async def evaluate(
        self,
        *,
        zone_id: int,
        runtime_monitor: Any,
        runtime: Any,
        requested_duration_sec: int | None,
        now: datetime,
    ) -> Any:
        decision_model = runtime.irrigation_decision
        config_error = str(getattr(decision_model, "config_error", "") or "").strip()
        config = getattr(decision_model, "config", None)
        if config_error or not isinstance(config, RadiationSumConfig):
            return _decision(
                outcome="fail",
                reason=REASON_CONFIG,
                details={
                    "config_error": config_error or "radiation_sum config is not RadiationSumConfig",
                    "requested_duration_sec": requested_duration_sec,
                },
            )
        try:
            window, timezone_name, window_error = resolve_radiation_window(
                runtime=runtime,
                config=config,
                now=now,
            )
        except InvalidGreenhouseTimezone as exc:
            return _decision(outcome="fail", reason=REASON_TIMEZONE, details={"timezone": exc.name})
        if window_error or window is None:
            return _decision(
                outcome="fail",
                reason=window_error or REASON_WINDOW,
                details={"requested_duration_sec": requested_duration_sec},
            )
        if not window.inside:
            return _decision(
                outcome="skip",
                reason=REASON_NIGHT,
                details={"timezone": timezone_name, "requested_duration_sec": requested_duration_sec},
            )

        ledger = getattr(runtime_monitor, "read_irrigation_pulses", None)
        if not callable(ledger):
            return _decision(outcome="fail", reason=REASON_LEDGER, details={"timezone": timezone_name})
        try:
            raw_pulses = await ledger(zone_id=int(zone_id))
        except Exception:
            logger.warning("AE3 radiation_sum не прочитал историю импульсов zone_id=%s", zone_id, exc_info=True)
            return _decision(outcome="fail", reason=REASON_LEDGER, details={"timezone": timezone_name})

        fallback_liters = configured_pulse_liters(config)
        pulses: list[dict[str, Any]] = []
        for row in raw_pulses or []:
            if not isinstance(row, Mapping):
                continue
            moment = row.get("finished_at")
            if not isinstance(moment, datetime):
                continue
            liters = row.get("liters")
            if liters is None:
                liters = pulse_liters_from_mapping(row.get("config"), fallback_liters=fallback_liters)
            try:
                liters_value = float(liters)
            except (TypeError, ValueError):
                liters_value = fallback_liters
            pulses.append({"finished_at": moment, "liters": liters_value})

        anchor = window.start_utc or as_aware_utc(now)
        last_pulse = _latest_pulse(pulses)
        if last_pulse is not None and last_pulse > as_aware_utc(anchor):
            anchor = last_pulse
        par_samples = await _read_series(
            runtime_monitor,
            zone_id=int(zone_id),
            label=str(config.source_channel or "par"),
            since_ts=anchor,
            until_ts=now,
        )
        lux_samples: list[tuple[datetime, float]] | None = None
        if config.allow_lux_proxy:
            lux_samples = await _read_series(
                runtime_monitor,
                zone_id=int(zone_id),
                label="light",
                since_ts=anchor,
                until_ts=now,
            )
        decision = decide_radiation_sum(
            config=config,
            now=now,
            zone_id=int(zone_id),
            timezone_name=timezone_name,
            window=window,
            pulses=pulses,
            par_samples=par_samples,
            lux_samples=lux_samples,
        )
        if isinstance(decision.details, dict):
            decision.details["requested_duration_sec"] = requested_duration_sec
        return decision


async def _read_series(
    runtime_monitor: Any,
    *,
    zone_id: int,
    label: str,
    since_ts: datetime,
    until_ts: datetime,
) -> list[tuple[datetime, float]] | None:
    reader = getattr(runtime_monitor, "read_channel_samples", None)
    if not callable(reader):
        return None
    try:
        payload = await reader(zone_id=zone_id, label=label, since_ts=since_ts, until_ts=until_ts)
    except Exception:
        logger.warning(
            "AE3 radiation_sum не прочитал канал %s zone_id=%s",
            label,
            zone_id,
            exc_info=True,
        )
        return None
    return parse_samples(payload)
