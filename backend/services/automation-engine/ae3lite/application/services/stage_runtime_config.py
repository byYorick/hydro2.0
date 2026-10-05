"""Разрешение phase/targets/observe из RuntimePlan без SQL и команд.

Объект не кеширует runtime: каждый вызов получает актуальный plan после checkpoint.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError

_MISSING_CONFIG = object()


class StageRuntimeConfig:
    """Приоритеты конфигурации, проверка обязательных полей и phase targets."""

    @staticmethod
    def mapping_value(mapping: Any, key: str) -> Any:
        if isinstance(mapping, Mapping):
            if key not in mapping:
                return _MISSING_CONFIG
            return mapping[key]
        if mapping is None or not hasattr(mapping, key):
            return _MISSING_CONFIG
        return getattr(mapping, key)


    @staticmethod
    def mapping_view(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping):
            return value
        if value is not None and hasattr(value, "model_dump"):
            dumped = value.model_dump(mode="python")
            if isinstance(dumped, Mapping):
                return dumped
        return {}


    def required_config_int(
        self,
        *,
        field_name: str,
        candidates: Sequence[tuple[str, Any]],
        minimum: int,
        error_code: str = ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
    ) -> int:
        for source_name, raw in candidates:
            if raw is _MISSING_CONFIG:
                continue
            if raw is None or isinstance(raw, bool):
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}",
                )
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}",
                ) from None
            if value < minimum:
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}: требуется >= {minimum}",
                )
            return value

        raise TaskExecutionError(
            error_code,
            f"Отсутствует обязательный параметр {field_name}",
        )


    def required_config_float(
        self,
        *,
        field_name: str,
        candidates: Sequence[tuple[str, Any]],
        minimum: float,
        error_code: str = ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
    ) -> float:
        for source_name, raw in candidates:
            if raw is _MISSING_CONFIG:
                continue
            if raw is None or isinstance(raw, bool):
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}",
                )
            try:
                value = float(raw)
            except (TypeError, ValueError):
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}",
                ) from None
            if not math.isfinite(value) or value < minimum:
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}: требуется >= {minimum}",
                )
            return value

        raise TaskExecutionError(
            error_code,
            f"Отсутствует обязательный параметр {field_name}",
        )


    def required_correction_int(
        self,
        *,
        correction_cfg: Mapping[str, Any],
        key: str,
        minimum: int = 1,
    ) -> int:
        return self.required_config_int(
            field_name=f"correction.{key}",
            candidates=((f"correction.{key}", self.mapping_value(correction_cfg, key)),),
            minimum=minimum,
        )


    def required_prepare_tolerance_pct(
        self,
        *,
        tolerance: Mapping[str, Any],
        key: str,
    ) -> float:
        return self.required_config_float(
            field_name=f"prepare_tolerance.{key}",
            candidates=((f"prepare_tolerance.{key}", self.mapping_value(tolerance, key)),),
            minimum=0.1,
        )


    def prepare_tolerance_for_task(self, *, task: Any, runtime: RuntimePlan) -> Any:
        phase_key = self.runtime_phase_key(task=task)
        phase_cfg = runtime.prepare_tolerance_by_phase.get(phase_key)
        if phase_cfg is not None:
            return self.mapping_view(phase_cfg)
        generic_cfg = runtime.prepare_tolerance_by_phase.get("generic")
        if generic_cfg is not None:
            return self.mapping_view(generic_cfg)
        if runtime.prepare_tolerance is not None:
            return self.mapping_view(runtime.prepare_tolerance)
        raise TaskExecutionError(
            ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
            f"Отсутствует обязательный prepare_tolerance для phase={self.runtime_phase_key(task=task)}",
        )


    def correction_config_for_task(self, *, task: Any, runtime: RuntimePlan) -> Any:
        phase_key = self.runtime_phase_key(task=task)
        phase_cfg = runtime.correction_by_phase.get(phase_key)
        if phase_cfg is not None:
            return self.mapping_view(phase_cfg)
        generic_cfg = runtime.correction_by_phase.get("generic")
        if generic_cfg is not None:
            return self.mapping_view(generic_cfg)
        if runtime.correction is not None:
            return self.mapping_view(runtime.correction)
        raise TaskExecutionError(
            ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
            f"Отсутствует обязательный correction runtime для phase={self.runtime_phase_key(task=task)}",
        )


    def full_ec_component_ratios(
        self,
        *,
        runtime: RuntimePlan,
        correction_cfg: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Full recipe Ca/Mg/NPK/Micro ratios for cumulative T_* / dilute math.

        Prefer tank_recirc ratios over fill calcium-only and runtime fallback.
        """
        by_phase = getattr(runtime, "correction_by_phase", None) or {}
        tank_recirc = by_phase.get("tank_recirc") if isinstance(by_phase, Mapping) else None
        if tank_recirc is not None:
            ratios = getattr(tank_recirc, "ec_component_ratios", None)
            if isinstance(tank_recirc, Mapping):
                ratios = tank_recirc.get("ec_component_ratios")
            if isinstance(ratios, Mapping) and ratios:
                return ratios
            view = self.mapping_view(tank_recirc)
            ratios = view.get("ec_component_ratios") if isinstance(view, Mapping) else None
            if isinstance(ratios, Mapping) and ratios:
                return ratios
        ratios = getattr(runtime, "ec_component_ratios", None) or {}
        if isinstance(ratios, Mapping) and ratios:
            return ratios
        if isinstance(correction_cfg, Mapping):
            ratios = correction_cfg.get("ec_component_ratios") or {}
            if isinstance(ratios, Mapping) and ratios:
                return ratios
        return {}


    def process_cfg_for_task(self, *, task: Any, runtime: RuntimePlan) -> Any:
        process_calibrations = runtime.process_calibrations
        phase_key = self.runtime_phase_key(task=task)
        process_cfg = process_calibrations.get(phase_key)
        if process_cfg is not None:
            return self.mapping_view(process_cfg)
        generic_cfg = process_calibrations.get("generic")
        if generic_cfg is not None:
            return self.mapping_view(generic_cfg)
        if phase_key == "irrigation":
            solution_fill_cfg = process_calibrations.get("solution_fill")
            if solution_fill_cfg is not None:
                return self.mapping_view(solution_fill_cfg)
        return {}


    def observation_config(
        self,
        *,
        kind: str,
        correction_cfg: Mapping[str, Any],
        process_cfg: Mapping[str, Any],
        pid_entry: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        controllers_raw = self.mapping_value(correction_cfg, "controllers")
        controllers = controllers_raw if isinstance(controllers_raw, Mapping) else {}
        controller_raw = controllers.get(kind)
        controller_cfg = controller_raw if isinstance(controller_raw, Mapping) else {}
        controller_observe_raw = self.mapping_value(controller_cfg, "observe")
        controller_observe_cfg = controller_observe_raw if isinstance(controller_observe_raw, Mapping) else {}
        process_meta_raw = self.mapping_value(process_cfg, "meta")
        process_meta = process_meta_raw if isinstance(process_meta_raw, Mapping) else {}
        observe_cfg = process_meta.get("observe") if isinstance(process_meta.get("observe"), Mapping) else {}

        telemetry_period_sec = self.required_config_int(
            field_name=f"{kind}.observe.telemetry_period_sec",
            candidates=(
                ("process_calibration.meta.observe.telemetry_period_sec", self.mapping_value(observe_cfg, "telemetry_period_sec")),
                (f"correction.controllers.{kind}.observe.telemetry_period_sec", self.mapping_value(controller_observe_cfg, "telemetry_period_sec")),
                (f"correction.controllers.{kind}.telemetry_period_sec", self.mapping_value(controller_cfg, "telemetry_period_sec")),
            ),
            minimum=1,
        )
        window_min_samples = self.required_config_int(
            field_name=f"{kind}.observe.window_min_samples",
            candidates=(
                ("process_calibration.meta.observe.window_min_samples", self.mapping_value(observe_cfg, "window_min_samples")),
                (f"correction.controllers.{kind}.observe.window_min_samples", self.mapping_value(controller_observe_cfg, "window_min_samples")),
                (f"correction.controllers.{kind}.window_min_samples", self.mapping_value(controller_cfg, "window_min_samples")),
            ),
            minimum=2,  # config-literal: decision window needs at least two samples
        )
        explicit_decision_window_sec = self.required_config_int(
            field_name=f"{kind}.observe.decision_window_sec",
            candidates=(
                ("process_calibration.meta.observe.decision_window_sec", self.mapping_value(observe_cfg, "decision_window_sec")),
                (f"correction.controllers.{kind}.observe.decision_window_sec", self.mapping_value(controller_observe_cfg, "decision_window_sec")),
                (f"correction.controllers.{kind}.decision_window_sec", self.mapping_value(controller_cfg, "decision_window_sec")),
            ),
            minimum=1,
        )
        decision_window_sec = max(
            telemetry_period_sec * window_min_samples,
            explicit_decision_window_sec,
        )
        transport_delay_sec = self.required_config_int(
            field_name=f"{kind}.process_calibration.transport_delay_sec",
            candidates=(
                ("process_calibration.transport_delay_sec", self.mapping_value(process_cfg, "transport_delay_sec")),
                (f"correction.controllers.{kind}.observe.transport_delay_sec", self.mapping_value(controller_observe_cfg, "transport_delay_sec")),
                (f"correction.controllers.{kind}.transport_delay_sec", self.mapping_value(controller_cfg, "transport_delay_sec")),
            ),
            minimum=1,
            error_code="corr_process_calibration_missing",
        )
        settle_sec = self.required_config_int(
            field_name=f"{kind}.process_calibration.settle_sec",
            candidates=(
                ("process_calibration.settle_sec", self.mapping_value(process_cfg, "settle_sec")),
                (f"correction.controllers.{kind}.observe.settle_sec", self.mapping_value(controller_observe_cfg, "settle_sec")),
                (f"correction.controllers.{kind}.settle_sec", self.mapping_value(controller_cfg, "settle_sec")),
            ),
            minimum=1,
            error_code="corr_process_calibration_missing",
        )

        adaptive_timing = self.adaptive_observation_timing(pid_entry=pid_entry)
        learned_transport = adaptive_timing.get("transport_delay_sec")
        learned_settle = adaptive_timing.get("settle_sec")
        if learned_transport is not None:
            transport_delay_sec = max(transport_delay_sec, learned_transport)
        if learned_settle is not None:
            settle_sec = max(settle_sec, learned_settle)
        return {
            "transport_delay_sec": transport_delay_sec,
            "settle_sec": settle_sec,
            "hold_window_sec": transport_delay_sec + settle_sec,
            "telemetry_period_sec": telemetry_period_sec,
            "window_min_samples": window_min_samples,
            "decision_window_sec": decision_window_sec,
            "observe_poll_sec": self.required_config_int(
                field_name=f"{kind}.observe.observe_poll_sec",
                candidates=(
                    ("process_calibration.meta.observe.observe_poll_sec", self.mapping_value(observe_cfg, "observe_poll_sec")),
                    (f"correction.controllers.{kind}.observe.observe_poll_sec", self.mapping_value(controller_observe_cfg, "observe_poll_sec")),
                    (f"correction.controllers.{kind}.observe_poll_sec", self.mapping_value(controller_cfg, "observe_poll_sec")),
                ),
                minimum=1,
            ),
            "min_effect_fraction": self.required_config_float(
                field_name=f"{kind}.observe.min_effect_fraction",
                candidates=(
                    ("process_calibration.meta.observe.min_effect_fraction", self.mapping_value(observe_cfg, "min_effect_fraction")),
                    (f"correction.controllers.{kind}.observe.min_effect_fraction", self.mapping_value(controller_observe_cfg, "min_effect_fraction")),
                    (f"correction.controllers.{kind}.min_effect_fraction", self.mapping_value(controller_cfg, "min_effect_fraction")),
                ),
                minimum=0.01,
            ),
            "stability_max_slope": self.required_config_float(
                field_name=f"{kind}.observe.stability_max_slope",
                candidates=(
                    ("process_calibration.meta.observe.stability_max_slope", self.mapping_value(observe_cfg, "stability_max_slope")),
                    (f"correction.controllers.{kind}.observe.stability_max_slope", self.mapping_value(controller_observe_cfg, "stability_max_slope")),
                    (f"correction.controllers.{kind}.stability_max_slope", self.mapping_value(controller_cfg, "stability_max_slope")),
                ),
                minimum=0.0001,
            ),
            "no_effect_limit": self.required_config_int(
                field_name=f"{kind}.observe.no_effect_consecutive_limit",
                candidates=(
                    ("process_calibration.meta.observe.no_effect_consecutive_limit", self.mapping_value(observe_cfg, "no_effect_consecutive_limit")),
                    (f"correction.controllers.{kind}.observe.no_effect_consecutive_limit", self.mapping_value(controller_observe_cfg, "no_effect_consecutive_limit")),
                    (f"correction.controllers.{kind}.no_effect_consecutive_limit", self.mapping_value(controller_cfg, "no_effect_consecutive_limit")),
                ),
                minimum=1,
            ),
        }


    def adaptive_observation_timing(self, *, pid_entry: Mapping[str, Any] | None) -> dict[str, int]:
        if not isinstance(pid_entry, Mapping):
            return {}
        stats = pid_entry.get("stats")
        if not isinstance(stats, Mapping):
            return {}
        adaptive = stats.get("adaptive")
        if not isinstance(adaptive, Mapping):
            return {}
        timing = adaptive.get("timing")
        if not isinstance(timing, Mapping):
            return {}
        try:
            observations = int(timing.get("observations") or adaptive.get("observations") or 0)
        except (TypeError, ValueError):
            observations = 0
        if observations < 3:
            return {}

        result: dict[str, int] = {}
        for key in ("transport_delay_sec", "settle_sec"):
            raw = timing.get(f"{key}_ema")
            try:
                value = int(round(float(raw)))
            except (TypeError, ValueError):
                continue
            if value > 0:
                result[key] = value
        return result


    def irrigation_ec_target(self, *, runtime: RuntimePlan) -> float:
        """Полный irrigation EC target (day/night), без NPK prepare-share."""
        base_full = float(runtime.target_ec)
        return self.day_night_override(runtime, "ec", "target", default=base_full)


    def irrigation_ec_min(self, *, runtime: RuntimePlan) -> float | None:
        base_val = self.coerce_float(runtime.target_ec_min)
        if base_val is None:
            return None
        return self.day_night_override(runtime, "ec", "min", default=base_val)


    def irrigation_ec_max(self, *, runtime: RuntimePlan) -> float | None:
        base_val = self.coerce_float(runtime.target_ec_max)
        if base_val is None:
            return None
        return self.day_night_override(runtime, "ec", "max", default=base_val)


    def effective_ec_target(self, *, task: Any, runtime: RuntimePlan) -> float:
        """EC target с учётом фазы и water-baseline cumulative T_*.

        solution_fill / tank_recirc → T_step из corr.component_targets (если есть),
        иначе deprecated pre-baseline calcium share (target_ec_prepare).
        irrigation → EC off на уровне planner; accessor возвращает full target.
        """
        from ae3lite.domain.services.nutrient_pipeline import (
            ComponentTargets,
            active_ec_target_for_corr,
        )

        phase = self.runtime_phase_key(task=task)
        base_full = float(runtime.target_ec)
        full_target = self.irrigation_ec_target(runtime=runtime)
        corr = getattr(task, "correction", None)
        if corr is not None and phase in ("solution_fill", "tank_recirc"):
            targets = ComponentTargets.from_json(getattr(corr, "component_targets_json", None))
            if targets is not None:
                return active_ec_target_for_corr(
                    pipeline_phase=getattr(corr, "pipeline_phase", None),
                    active_component=getattr(corr, "active_component", None),
                    targets=targets,
                    fallback_target_ec=full_target,
                )
        if phase in ("solution_fill", "tank_recirc"):
            prepare = runtime.target_ec_prepare
            if prepare is not None:
                if full_target != base_full and base_full > 0:
                    share = float(runtime.npk_ec_share or (float(prepare) / base_full))
                    return round(full_target * share, 4)
                return float(prepare)
        return full_target


    def effective_ec_min(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        phase = self.runtime_phase_key(task=task)
        if phase in ("solution_fill", "tank_recirc"):
            base = runtime.target_ec_prepare_min
            if base is not None:
                scaled = self.day_night_override_scaled(
                    runtime, "ec", "min", default=float(base), phase_key="prepare",
                )
                return scaled if scaled is not None else float(base)
        return self.irrigation_ec_min(runtime=runtime)


    def effective_ec_max(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        phase = self.runtime_phase_key(task=task)
        if phase in ("solution_fill", "tank_recirc"):
            base = runtime.target_ec_prepare_max
            if base is not None:
                scaled = self.day_night_override_scaled(
                    runtime, "ec", "max", default=float(base), phase_key="prepare",
                )
                return scaled if scaled is not None else float(base)
        return self.irrigation_ec_max(runtime=runtime)


    def effective_ph_target(self, *, task: Any, runtime: RuntimePlan) -> float:
        base = float(runtime.target_ph)
        return self.day_night_override(runtime, "ph", "target", default=base)


    def effective_ph_min(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        base_val = self.coerce_float(runtime.target_ph_min)
        if base_val is None:
            return None
        return self.day_night_override(runtime, "ph", "min", default=base_val)


    def effective_ph_max(self, *, task: Any, runtime: RuntimePlan) -> float | None:
        base_val = self.coerce_float(runtime.target_ph_max)
        if base_val is None:
            return None
        return self.day_night_override(runtime, "ph", "max", default=base_val)


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
        is_day = self.is_day_now(config)
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
        base_full = self.coerce_float(getattr(runtime, f"target_ec_{kind}", None))
        if base_full is None or base_full <= 0:
            return default
        overridden_full = self.day_night_override(runtime, metric, kind, default=base_full)
        if overridden_full == base_full:
            return default
        share = float(runtime.npk_ec_share or (default / base_full))
        return round(overridden_full * share, 4)


    @staticmethod
    def is_day_now(day_night_config: Any) -> bool:
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
        now_local = datetime.now(tz)

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


    def coerce_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

