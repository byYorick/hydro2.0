from typing import Any, Dict, List, Optional, Callable, Awaitable
import logging

from executor.correction_ec_batch_utils import (
    extract_nutrition_control,
    get_latest_ec_value,
    resolve_batch_dose_control,
    resolve_nutrition_mode,
    resolve_solution_volume_l,
)
from services.targets_accessor import get_nutrition_components

logger = logging.getLogger(__name__)


def build_ec_component_batch(
    *,
    targets: Dict[str, Any],
    actuators: Optional[Dict[str, Dict[str, Any]]],
    total_ml: float,
    current_ec: float,
    target_ec: float,
    allowed_ec_components: Optional[List[str]],
    build_correction_command: Callable[[Dict[str, Any], str, float], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not actuators or total_ml <= 0:
        logger.debug(
            "EC component batch skipped before build",
            extra={
                "reason": "missing_actuators_or_zero_total_ml",
                "has_actuators": bool(actuators),
                "total_ml": total_ml,
                "allowed_ec_components": allowed_ec_components,
            },
        )
        return []

    all_components = ["npk", "calcium", "magnesium", "micro"]
    requested_components: Optional[set[str]] = None
    required_components = all_components
    if allowed_ec_components is not None:
        requested = {
            str(component).strip().lower()
            for component in allowed_ec_components
            if str(component).strip()
        }
        requested_components = requested
        required_components = [component for component in all_components if component in requested]
        if not required_components:
            logger.warning(
                "EC component batch skipped: policy filtered out all components",
                extra={
                    "allowed_ec_components": allowed_ec_components,
                    "requested_components": sorted(list(requested)),
                    "all_components": all_components,
                },
            )
            return []

    logger.debug(
        "EC component batch policy resolved",
        extra={
            "allowed_ec_components": allowed_ec_components,
            "required_components": required_components,
            "total_ml": total_ml,
            "current_ec": current_ec,
            "target_ec": target_ec,
        },
    )

    role_map = {
        "npk": "ec_npk_pump",
        "calcium": "ec_calcium_pump",
        "magnesium": "ec_magnesium_pump",
        "micro": "ec_micro_pump",
    }
    missing_roles = [
        role_map[component]
        for component in required_components
        if role_map[component] not in actuators
    ]
    if missing_roles:
        npk_role = role_map["npk"]
        can_fallback_to_npk = (
            npk_role in (actuators or {})
            and npk_role not in missing_roles
            and required_components != ["npk"]
            and (requested_components is None or "npk" in requested_components)
        )
        if can_fallback_to_npk:
            logger.warning(
                "EC component batch fallback to npk-only: required multi-component roles missing",
                extra={
                    "required_components": required_components,
                    "missing_roles": missing_roles,
                    "available_roles": sorted(list((actuators or {}).keys())),
                },
            )
            required_components = ["npk"]
            missing_roles = []

    if missing_roles:
        logger.warning(
            "EC component batch skipped: required actuator roles missing",
            extra={
                "required_components": required_components,
                "missing_roles": missing_roles,
                "available_roles": sorted(list((actuators or {}).keys())),
            },
        )
        return []

    component_actuators: Dict[str, Dict[str, Any]] = {
        component: actuators[role_map[component]]
        for component in required_components
    }
    actuator_identity_to_component: Dict[str, str] = {}
    duplicate_actuator_bindings: List[Dict[str, str]] = []
    for component in required_components:
        actuator = component_actuators[component]
        identity = build_actuator_identity(actuator)
        previous_component = actuator_identity_to_component.get(identity)
        if previous_component is None:
            actuator_identity_to_component[identity] = component
            continue
        duplicate_actuator_bindings.append(
            {
                "identity": identity,
                "component_a": previous_component,
                "component_b": component,
            }
        )
    if duplicate_actuator_bindings:
        logger.warning(
            "EC component pumps must be unique per component; duplicate actuator bindings detected",
            extra={"duplicates": duplicate_actuator_bindings},
        )
        return []

    ml_per_sec_by_component: Dict[str, float] = {}
    calibration_snapshot: Dict[str, Dict[str, Any]] = {}
    for component in required_components:
        actuator = component_actuators[component]
        ml_per_sec_raw = actuator.get("ml_per_sec")
        calibration_snapshot[component] = {
            "role": actuator.get("role"),
            "node_uid": actuator.get("node_uid"),
            "channel": actuator.get("channel"),
            "ml_per_sec_raw": ml_per_sec_raw,
            "k_ms_per_ml_l": actuator.get("k_ms_per_ml_l"),
            "pump_calibration": actuator.get("pump_calibration"),
        }
        try:
            ml_per_sec = float(ml_per_sec_raw)
        except (TypeError, ValueError):
            ml_per_sec = 0.0
        if ml_per_sec <= 0:
            logger.warning(
                "EC component batch skipped due to invalid pump calibration",
                extra={
                    "component": component,
                    "role": actuator.get("role"),
                    "node_uid": actuator.get("node_uid"),
                    "channel": actuator.get("channel"),
                    "ml_per_sec": ml_per_sec_raw,
                    "calibration_snapshot": calibration_snapshot,
                },
            )
            return []
        ml_per_sec_by_component[component] = ml_per_sec

    logger.debug(
        "EC component calibration snapshot accepted",
        extra={
            "required_components": required_components,
            "calibration_snapshot": calibration_snapshot,
        },
    )

    nutrition = targets.get("nutrition") if isinstance(targets.get("nutrition"), dict) else {}
    components_cfg = get_nutrition_components(targets)
    legacy_single_component_mode = False
    if any(component not in components_cfg for component in required_components):
        # Backward compatibility for legacy recipes where nutrition.components
        # is absent, but phase policy allows only npk dosing.
        if required_components == ["npk"]:
            legacy_single_component_mode = True
            logger.warning(
                "EC component batch fallback: legacy npk-only mode without nutrition.components",
                extra={
                    "required_components": required_components,
                    "available_nutrition_components": sorted(list(components_cfg.keys())),
                    "total_ml": total_ml,
                },
            )
        else:
            logger.warning(
                "EC component batch skipped: nutrition config missing for required components",
                extra={
                    "required_components": required_components,
                    "available_nutrition_components": sorted(list(components_cfg.keys())),
                },
            )
            return []

    components_order = required_components
    component_ml_map: Dict[str, float] = {}
    mode = ""
    ratios: Dict[str, float] = {}
    k_values: Dict[str, Optional[float]] = {}

    if legacy_single_component_mode:
        mode = "legacy_single_component"
        ratios = {"npk": 100.0}
        component_ml_map = {"npk": round(max(0.0, float(total_ml)), 3)}
    else:
        components_order = required_components
        ratios = resolve_ec_component_ratios(targets, components_order)
        if not ratios:
            logger.warning(
                "EC component batch skipped: invalid or empty component ratios",
                extra={
                    "components_order": components_order,
                    "nutrition_mode_raw": nutrition.get("mode"),
                },
            )
            return []

        mode = resolve_nutrition_mode(nutrition)
        solution_volume_l = resolve_solution_volume_l(nutrition)

        for component in components_order:
            cfg_k = components_cfg.get(component, {}).get("k_ms_per_ml_l")
            act_k = component_actuators[component].get("k_ms_per_ml_l")
            try:
                k_candidate = float(cfg_k if cfg_k is not None else act_k)
            except (TypeError, ValueError):
                k_candidate = None
            if k_candidate is not None and k_candidate > 0:
                k_values[component] = k_candidate
            else:
                k_values[component] = None

        if mode == "dose_ml_l_only":
            if solution_volume_l is None or solution_volume_l <= 0:
                logger.warning(
                    "EC component batch skipped: dose_ml_l_only requires positive solution volume",
                    extra={"solution_volume_l": solution_volume_l},
                )
                return []
            for component in components_order:
                dose_ml_l = components_cfg.get(component, {}).get("dose_ml_per_l")
                try:
                    dose_value = float(dose_ml_l)
                except (TypeError, ValueError):
                    dose_value = 0.0
                if dose_value <= 0:
                    logger.warning(
                        "EC component batch skipped: invalid dose_ml_per_l for component",
                        extra={"component": component, "dose_ml_per_l": dose_ml_l},
                    )
                    return []
                component_ml_map[component] = round(dose_value * solution_volume_l, 3)

        if mode == "delta_ec_by_k":
            delta_ec = max(0.0, target_ec - current_ec)
            has_all_k = all((k_values.get(component) or 0) > 0 for component in components_order)
            if delta_ec <= 0 or solution_volume_l is None or solution_volume_l <= 0 or not has_all_k:
                logger.warning(
                    "EC component batch skipped: delta_ec_by_k prerequisites not met",
                    extra={
                        "delta_ec": delta_ec,
                        "solution_volume_l": solution_volume_l,
                        "has_all_k": has_all_k,
                        "k_values": k_values,
                    },
                )
                return []
            for component in components_order:
                ratio_pct = float(ratios.get(component, 0.0))
                k_value = float(k_values[component] or 0.0)
                delta_ec_component = delta_ec * (ratio_pct / 100.0)
                ml_per_l = delta_ec_component / k_value if k_value > 0 else 0.0
                component_ml_map[component] = round(max(0.0, ml_per_l * solution_volume_l), 3)

        if mode == "ratio_ec_pid":
            has_all_k = all((k_values.get(component) or 0) > 0 for component in components_order)
            if has_all_k:
                weighted = {
                    component: float(ratios.get(component, 0.0)) / float(k_values[component] or 1.0)
                    for component in components_order
                }
                weighted_sum = sum(weighted.values())
                if weighted_sum <= 0:
                    logger.warning(
                        "EC component batch skipped: weighted_sum <= 0 in ratio_ec_pid mode",
                        extra={"weighted": weighted, "k_values": k_values, "ratios": ratios},
                    )
                    return []
                for component in components_order:
                    component_ml_map[component] = round(max(0.0, total_ml * (weighted[component] / weighted_sum)), 3)
            else:
                remaining_ml = float(total_ml)
                for idx, component in enumerate(components_order):
                    ratio_pct = float(ratios.get(component, 0.0))
                    if idx == len(components_order) - 1:
                        component_ml = max(0.0, round(remaining_ml, 3))
                    else:
                        component_ml = max(0.0, round((total_ml * ratio_pct) / 100.0, 3))
                        remaining_ml -= component_ml
                    component_ml_map[component] = component_ml

        if not component_ml_map:
            logger.warning(
                "EC component batch skipped: component_ml_map is empty after mode calculation",
                extra={
                    "mode": mode,
                    "components_order": components_order,
                    "total_ml": total_ml,
                    "ratios": ratios,
                },
            )
            return []

    commands: List[Dict[str, Any]] = []

    for component in components_order:
        ratio_pct = float(ratios.get(component, 0.0))
        component_ml = max(0.0, float(component_ml_map.get(component, 0.0)))
        if component_ml <= 0:
            continue

        actuator = component_actuators[component]
        actuator_with_calibration = dict(actuator)
        actuator_with_calibration["ml_per_sec"] = ml_per_sec_by_component[component]
        payload = build_correction_command(actuator_with_calibration, "add_nutrients", component_ml)
        payload["params"]["component"] = component
        payload["params"]["ratio_pct"] = round(ratio_pct, 2)

        commands.append(
            {
                "node_uid": actuator["node_uid"],
                "channel": actuator["channel"],
                "cmd": payload["cmd"],
                "params": payload["params"],
                "component": component,
                "role": actuator.get("role"),
                "ml": component_ml,
                "ratio_pct": round(ratio_pct, 2),
                "mode": mode,
                "k_ms_per_ml_l": k_values.get(component),
            }
        )

    logger.debug(
        "EC component batch built",
        extra={
            "mode": mode,
            "components_order": components_order,
            "commands_count": len(commands),
            "total_component_ml": round(sum(item["ml"] for item in commands), 3),
            "component_ml_map": component_ml_map,
        },
    )
    return commands


def build_actuator_identity(actuator: Dict[str, Any]) -> str:
    node_channel_id = actuator.get("node_channel_id")
    if node_channel_id is not None:
        return f"node_channel:{node_channel_id}"

    node_uid = actuator.get("node_uid")
    channel = actuator.get("channel")
    if node_uid is not None and channel is not None:
        return f"node_uid:{node_uid}|channel:{channel}"

    node_id = actuator.get("node_id")
    if node_id is not None and channel is not None:
        return f"node_id:{node_id}|channel:{channel}"

    role = actuator.get("role")
    if role is not None:
        return f"role:{role}"

    return "unknown"


def resolve_ec_component_ratios(
    targets: Dict[str, Any],
    available_components: List[str],
) -> Dict[str, float]:
    components = get_nutrition_components(targets)
    if not components:
        return {}

    raw_ratios: Dict[str, float] = {}
    for component in available_components:
        ratio = components.get(component, {}).get("ratio_pct")
        if ratio is None:
            return {}
        try:
            ratio_value = float(ratio)
        except (TypeError, ValueError):
            return {}
        if ratio_value < 0:
            return {}
        raw_ratios[component] = ratio_value

    total = sum(raw_ratios.values())
    if total <= 0:
        return {}

    normalized: Dict[str, float] = {}
    for component in available_components:
        normalized[component] = round((raw_ratios[component] / total) * 100.0, 2)
    return normalized
