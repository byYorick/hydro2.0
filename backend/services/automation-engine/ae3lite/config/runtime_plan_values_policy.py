"""runtime plan values policy: one cohesive policy."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ae3lite.domain.errors import PlannerConfigurationError


def _normalize_node_types(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes, bytearray)):
        return []
    result: list[str] = []
    for item in raw_value:
        normalized = str(item or "").strip().lower()
        if normalized:
            result.append(normalized)
    return result


def _normalize_required_node_types(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        return [normalized] if normalized else []
    return _normalize_node_types(raw_value)


def _normalize_labels(raw_value: Any, default_labels: Sequence[str]) -> list[str]:
    if isinstance(raw_value, str):
        raw_value = (raw_value,)
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes, bytearray)):
        raw_value = default_labels
    result: list[str] = []
    for item in raw_value:
        normalized = str(item or "").strip().lower()
        if normalized:
            result.append(normalized)
    return result


def _require_labels(raw_value: Any, *, path: str) -> list[str]:
    labels = _normalize_labels(raw_value, ())
    if labels:
        return labels
    raise PlannerConfigurationError(f"Отсутствует обязательное поле correction_config: {path}")


def _resolve_int(raw_value: Any, default: int, minimum: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(int(minimum), value)


def _resolve_bounded_int(raw_value: Any, default: int, minimum: int, maximum: int) -> int:
    return min(int(maximum), _resolve_int(raw_value, default, minimum))


def _resolve_float(raw_value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(float(minimum), min(float(maximum), value))


def _require_int(raw_value: Any, *, path: str, minimum: int, maximum: int | None = None) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise PlannerConfigurationError(f"Отсутствует или некорректно поле correction_config: {path}") from None
    if value < minimum:
        raise PlannerConfigurationError(f"Поле correction_config {path} должно быть >= {minimum}, получено {value}")
    if maximum is not None and value > maximum:
        raise PlannerConfigurationError(f"Поле correction_config {path} должно быть <= {maximum}, получено {value}")
    return int(value)


def _require_float(raw_value: Any, *, path: str, minimum: float, maximum: float | None = None) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        raise PlannerConfigurationError(f"Отсутствует или некорректно поле correction_config: {path}") from None
    if value < minimum:
        raise PlannerConfigurationError(f"Поле correction_config {path} должно быть >= {minimum}, получено {value}")
    if maximum is not None and value > maximum:
        raise PlannerConfigurationError(f"Поле correction_config {path} должно быть <= {maximum}, получено {value}")
    return value


def _require_str(raw_value: Any, *, path: str) -> str:
    value = str(raw_value or "").strip().lower()
    if value:
        return value
    raise PlannerConfigurationError(f"Отсутствует обязательное поле correction_config: {path}")


def _normalize_controllers(raw_value: Any) -> dict[str, Any]:
    if not isinstance(raw_value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for kind in ("ec", "ph"):
        controller = raw_value.get(kind)
        if isinstance(controller, Mapping):
            result[kind] = dict(controller)
    return result


def _normalize_component_policy(raw_value: Any) -> dict[str, Any]:
    if not isinstance(raw_value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for phase, policy in raw_value.items():
        if isinstance(policy, Mapping):
            result[str(phase).strip().lower()] = dict(policy)
    return result


def _to_mapping(raw_value: Any) -> dict[str, Any]:
    return dict(raw_value) if isinstance(raw_value, Mapping) else {}


def _merge_recursive(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _merge_recursive(current, value)
            continue
        merged[key] = value
    return merged


def _first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _optional_float(raw_value: Any) -> float | None:
    try:
        return float(raw_value) if raw_value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_bool(raw_value: Any, default: bool) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, (int, float)):
        return int(raw_value) == 1
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return default


def _irrigation_subsystem(snapshot: Any) -> dict[str, Any]:
    targets = _to_mapping(getattr(snapshot, "targets", None))
    extensions = _to_mapping(targets.get("extensions"))
    subsystems = _to_mapping(extensions.get("subsystems"))
    return _to_mapping(subsystems.get("irrigation"))
