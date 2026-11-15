"""StageRuntimeConfig schedule: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from ae3lite.config.schema import RuntimePlan


@dataclass(frozen=True)
class StageConfigSchedulePorts:
    coerce_float: Callable[..., Any]
    is_day_now: Callable[[Any], bool]


class StageConfigSchedule:
    def __init__(self, ports: StageConfigSchedulePorts) -> None:
        self._ports = ports

    def day_night_override(
        self,
        runtime: RuntimePlan,
        metric: str,
        kind: str,
        *,
        default: float,
    ) -> float:
        """Возвращает day- или night-значение для metric (ph/ec) и kind (target/min/max).

        Если day_night_enabled=False или значение не задано — возвращает default.
        Day-значение из day_night также используется если задано; иначе — default (что
        соответствует base-таргету фазы, т.е. конвенция: базовый target == day).
        """
        config = runtime.day_night_config
        if config is None or not bool(config.enabled):
            return default
        section = getattr(config, metric, None)
        if not section:
            return default
        is_day = self._ports.is_day_now(config)
        if is_day:
            if kind == "target":
                key = "day"
            else:
                key = f"day_{kind}"
        else:
            if kind == "target":
                key = "night"
            else:
                key = f"night_{kind}"
        value = getattr(section, key, None)
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def day_night_override_scaled(
        self,
        runtime: RuntimePlan,
        metric: str,
        kind: str,
        *,
        default: float,
        phase_key: str,
    ) -> float | None:
        """Для prepare-фазы (solution_fill/tank_recirc) возвращает min/max, масштабированный NPK share."""
        if phase_key != "prepare":
            return default
        base_full = self._ports.coerce_float(getattr(runtime, f"target_ec_{kind}", None))
        if base_full is None or base_full <= 0:
            return default
        overridden_full = self.day_night_override(runtime, metric, kind, default=base_full)
        if overridden_full == base_full:
            return default
        share = float(runtime.npk_ec_share or (default / base_full))
        return round(overridden_full * share, 4)

    @staticmethod
    def is_day_now(day_night_config: Any, *, now_fn: Callable[[Any], datetime] | None = None) -> bool:
        """Возвращает True если текущее локальное время теплицы попадает в
        дневной интервал.

        Использует day_start_time (HH:MM) + day_hours + timezone (IANA-имя,
        например "Europe/Moscow") из config. Если timezone не задан — fallback
        на UTC. Если day_start_time/day_hours невалидны — возвращает True.
        """

        # Поддерживаем и Pydantic-like объекты (runtime plan), и dict-конфиги
        # (тесты, legacy call sites). Без dual-access тесты,
        # собирающие `{"lighting": {...}}` литерально, получают `lighting=None`
        # и проваливаются в fail-safe ветку `return True`.
        def _pick(obj: Any, key: str) -> Any:
            if obj is None:
                return None
            if isinstance(obj, Mapping):
                return obj.get(key)
            return getattr(obj, key, None)

        lighting = _pick(day_night_config, "lighting")
        raw_start = _pick(lighting, "day_start_time")
        day_hours = _pick(lighting, "day_hours")
        if not isinstance(raw_start, str) or not raw_start.strip() or day_hours is None:
            return True
        parts = raw_start.strip().split(":")
        if len(parts) < 2:
            return True
        try:
            start_h = int(parts[0])
            start_m = int(parts[1])
            hours = float(day_hours)
        except (TypeError, ValueError):
            return True
        if not (0 <= start_h <= 23 and 0 <= start_m <= 59):
            return True
        if hours <= 0:
            return False
        if hours >= 24:
            return True

        # Резолвим now в локальном TZ теплицы. `day_start_time` хранится как
        # HH:MM в локальном времени teplicy, поэтому сравнение должно идти в
        # том же TZ. Иначе при UTC-контейнере и TZ=МСК night-targets смещаются
        # на часы разницы.
        tz_raw = _pick(lighting, "timezone")
        tz_name = tz_raw if isinstance(tz_raw, str) else None
        tz: Any = timezone.utc
        if tz_name:
            try:
                from zoneinfo import ZoneInfo

                tz = ZoneInfo(tz_name)
            except Exception:
                tz = timezone.utc
        now_local = (now_fn or datetime.now)(tz)

        start_min = start_h * 60 + start_m
        end_min = (start_min + int(round(hours * 60))) % (24 * 60)
        now_min = now_local.hour * 60 + now_local.minute
        if start_min == end_min:
            return True
        if start_min < end_min:
            return start_min <= now_min < end_min
        return now_min >= start_min or now_min < end_min

    def runtime_phase_key(self, *, task: Any) -> str:
        workflow = getattr(task, "workflow", None)
        workflow_phase = getattr(workflow, "workflow_phase", None)
        phase = str(workflow_phase or getattr(task, "workflow_phase", "") or "").strip().lower()
        if phase in {"tank_filling", "solution_fill"}:
            return "solution_fill"
        if phase in {"tank_recirc", "prepare_recirculation"}:
            return "tank_recirc"
        if phase in {"irrigating", "irrigation", "irrig_recirc"}:
            return "irrigation"
        stage = str(getattr(task, "current_stage", "") or "").strip().lower()
        if stage.startswith("solution_fill"):
            return "solution_fill"
        if stage.startswith("prepare_recirculation"):
            return "tank_recirc"
        return "generic"
