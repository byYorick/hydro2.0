"""runtime plan validation: one cohesive policy."""

from __future__ import annotations

from typing import Any, Mapping

from ae3lite.config.runtime_plan_values import _REQUIRED_ZONE_CORRECTION_TEMPLATE
from ae3lite.config.runtime_plan_values_policy import _resolve_int, _to_mapping
from ae3lite.domain.errors import ErrorCodes, PlannerConfigurationError


def _require_pid_configs(*, snapshot: Any, zone_id: int) -> None:
    pid_configs = getattr(snapshot, "pid_configs", None)
    if not isinstance(pid_configs, Mapping):
        raise PlannerConfigurationError(
            f"У зоны {zone_id} отсутствует mapping PID authority; критические параметры коррекции переведены в fail-closed режим",
            code=ErrorCodes.ZONE_PID_CONFIG_MISSING_CRITICAL,
        )

    missing_types: list[str] = []
    for pid_type in ("ph", "ec"):
        entry = pid_configs.get(pid_type)
        config = entry.get("config") if isinstance(entry, Mapping) else None
        if not isinstance(config, Mapping) or not config:
            missing_types.append(pid_type)

    if missing_types:
        raise PlannerConfigurationError(
            f"У зоны {zone_id} отсутствуют обязательные PID authority-документы для pid_type={', '.join(sorted(missing_types))}; "
            "критические параметры коррекции переведены в fail-closed режим",
            code=ErrorCodes.ZONE_PID_CONFIG_MISSING_CRITICAL,
        )


def _require_zone_correction_contract(*, zone_id: int, config: Mapping[str, Any], config_name: str) -> None:
    missing_paths = _collect_missing_paths(config=config, template=_REQUIRED_ZONE_CORRECTION_TEMPLATE)
    if missing_paths:
        raise PlannerConfigurationError(
            f"У зоны {zone_id} в correction_config.{config_name} отсутствуют обязательные поля: {', '.join(missing_paths)}; "
            "критические параметры коррекции переведены в fail-closed режим",
            code=ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
        )


def _collect_missing_paths(*, config: Mapping[str, Any], template: Mapping[str, Any], prefix: str = "") -> list[str]:
    missing: list[str] = []
    for key, expected in template.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if key not in config:
            missing.append(path)
            continue
        actual = config.get(key)
        if isinstance(expected, Mapping):
            if not isinstance(actual, Mapping):
                missing.append(path)
                continue
            missing.extend(_collect_missing_paths(config=actual, template=expected, prefix=path))
    return missing


def _validate_prepare_recirculation_timing(runtime: dict[str, Any]) -> None:
    """Выбрасывает `PlannerConfigurationError`, если окно `prepare_recirculation` слишком короткое для одного цикла коррекции."""
    timeout_sec = runtime["prepare_recirculation_timeout_sec"]
    correction_by_phase = _to_mapping(runtime.get("correction_by_phase"))
    correction = correction_by_phase.get("tank_recirc")
    if not isinstance(correction, dict):
        correction = runtime.get("correction", {})
    stabilization_sec = correction.get("stabilization_sec", 0)
    tank_recirc_process_cfg = _to_mapping(_to_mapping(runtime.get("process_calibrations")).get("tank_recirc"))
    observe_window_sec = _tank_recirc_observe_window_sec(correction=correction, process_cfg=tank_recirc_process_cfg)
    minimum_needed = stabilization_sec + observe_window_sec
    if timeout_sec < minimum_needed:
        raise PlannerConfigurationError(
            f"prepare_recirculation_timeout_sec={timeout_sec} с меньше, чем "
            f"stabilization_sec + observe_window_sec = {stabilization_sec} + {observe_window_sec} = {minimum_needed} с; "
            "окно коррекции слишком короткое для одного observation-driven цикла"
        )


def _tank_recirc_observe_window_sec(*, correction: Mapping[str, Any], process_cfg: Mapping[str, Any]) -> int:
    transport_delay_sec = _resolve_int(process_cfg.get("transport_delay_sec"), 0, 0)
    settle_sec = _resolve_int(process_cfg.get("settle_sec"), 0, 0)
    if transport_delay_sec > 0 and settle_sec > 0:
        return transport_delay_sec + settle_sec
    raise PlannerConfigurationError("process calibration tank_recirc должна содержать transport_delay_sec и settle_sec")
