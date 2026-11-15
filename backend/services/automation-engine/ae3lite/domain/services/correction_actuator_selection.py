"""Correction domain policy: actuator selection."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.correction_math_defaults import _EC_COMPONENT_DEFAULT_ORDER, _EC_COMPONENT_LEGACY_ALIAS_MAP


def _assert_distinct_parallel_actuators(ec_actuators: Mapping[str, Any]) -> None:
    """Fail-closed: в multi_parallel каждый компонент должен быть на своём канале.

    Если два компонента (calcium/magnesium/micro/npk) делят один (node_uid,
    channel), parallel-команды для них вызовут суперпозицию на pump'е —
    реальный поток распределится непредсказуемо → неверные дозы. В
    sequential режиме это допустимо (насосы работают по очереди).
    """
    seen: dict[tuple[str, str], tuple[str, str]] = {}
    for name, actuator in ec_actuators.items():
        if not isinstance(actuator, Mapping):
            continue
        node_uid = str(actuator.get("node_uid") or "").strip().lower()
        channel = str(actuator.get("channel") or "").strip().lower()
        if not node_uid or not channel:
            continue
        identity = _ec_actuator_identity(name=name, actuator=actuator)
        key = (node_uid, channel)
        if key in seen:
            seen_identity, seen_name = seen[key]
            if identity == seen_identity:
                continue
            raise PlannerConfigurationError(
                f"Режим multi_parallel EC требует distinct (node_uid, channel) для каждого "
                f"компонента, но '{name}' и '{seen_name}' используют ({node_uid}, {channel})"
            )
        seen[key] = (identity, str(name))


def _ec_actuator_identity(*, name: str, actuator: Mapping[str, Any]) -> str:
    calibration = actuator.get("calibration")
    component = ""
    if isinstance(calibration, Mapping):
        component = _normalize_ec_component_alias(calibration.get("component"))
    if component:
        return component
    return _normalize_ec_component_alias(name) or str(name).strip().lower()


def _normalize_ec_component_alias(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return ""
    if value.startswith("ec_"):
        return _normalize_ec_component_alias(value.removeprefix("ec_").removesuffix("_pump"))
    if value.startswith("dose_ec_"):
        suffix = value.removeprefix("dose_ec_")
        return _EC_COMPONENT_LEGACY_ALIAS_MAP.get(suffix, _normalize_ec_component_alias(suffix))
    if value.startswith("pump_"):
        suffix = value.removeprefix("pump_")
        return _EC_COMPONENT_LEGACY_ALIAS_MAP.get(suffix, value)
    return _EC_COMPONENT_LEGACY_ALIAS_MAP.get(value, value)


def _find_ec_component_actuator(
    *,
    ec_actuators: Mapping[str, Any],
    component: str,
) -> Mapping[str, Any] | None:
    """Пытается найти actuator EC-компонента по нормализованному имени.

    Resolve order: direct component key → ec_* → pump channel map (pump_b↔calcium)
    → scan calibration.component / channel / role aliases.
    """
    from ae3lite.domain.services.nutrient_pipeline import CHANNEL_TO_COMPONENT, COMPONENT_TO_CHANNEL

    want = str(component).strip().lower()
    if not want:
        return None
    want = _normalize_ec_component_alias(want) or want

    direct = ec_actuators.get(want)
    if isinstance(direct, Mapping):
        return direct
    alt = ec_actuators.get(f"ec_{want}")
    if isinstance(alt, Mapping):
        return alt
    channel = COMPONENT_TO_CHANNEL.get(want)
    if channel:
        by_channel = ec_actuators.get(channel)
        if isinstance(by_channel, Mapping):
            return by_channel

    for name, actuator in ec_actuators.items():
        if not isinstance(actuator, Mapping):
            continue
        key = _normalize_ec_component_alias(name) or str(name).strip().lower()
        if key == want:
            return actuator
        calibration = actuator.get("calibration")
        if isinstance(calibration, Mapping):
            cal_comp = _normalize_ec_component_alias(calibration.get("component"))
            if cal_comp == want:
                return actuator
        # channel/role identity on the actuator payload itself
        act_channel = str(actuator.get("channel") or "").strip().lower()
        if CHANNEL_TO_COMPONENT.get(act_channel) == want:
            return actuator
        if act_channel == want or act_channel == channel:
            return actuator
    return None


def _resolve_ec_actuator(
    *,
    ec_actuator: Optional[Mapping[str, Any]],
    ec_actuators: Optional[Mapping[str, Any]],
    ec_component_policy: Optional[Mapping[str, Any]],
    phase_key: str,
    default_channel: str,
) -> tuple[str, Mapping[str, Any]]:
    if isinstance(ec_actuator, Mapping):
        return "", ec_actuator

    if not isinstance(ec_actuators, Mapping) or not ec_actuators:
        raise PlannerConfigurationError(f"Требуется коррекция EC, но не найден actuator для channel={default_channel}")

    phase_policy = ec_component_policy.get(phase_key) if isinstance(ec_component_policy, Mapping) else None
    phase_policy = phase_policy if isinstance(phase_policy, Mapping) else {}
    has_explicit_policy = bool(phase_policy)
    ranked: list[tuple[float, int, str, Mapping[str, Any]]] = []
    for name, actuator in ec_actuators.items():
        if not isinstance(actuator, Mapping):
            continue
        component = str(name).strip().lower()
        component = component[3:] if component.startswith("ec_") else component
        if has_explicit_policy:
            weight = float(phase_policy.get(component) or phase_policy.get(name) or 0.0)
            order_idx = 0  # explicit policy overrides default ordering
        else:
            weight = 0.0
            # Использовать _EC_COMPONENT_DEFAULT_ORDER для детерминированного
            # и агрономически осмысленного выбора.
            try:
                order_idx = _EC_COMPONENT_DEFAULT_ORDER.index(component)
            except ValueError:
                order_idx = len(_EC_COMPONENT_DEFAULT_ORDER)
        ranked.append((weight, order_idx, component, actuator))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    chosen = ranked[0] if ranked else None
    if chosen is None:
        raise PlannerConfigurationError(f"Требуется коррекция EC, но не найден actuator для channel={default_channel}")
    return chosen[2], chosen[3]
