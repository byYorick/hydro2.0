"""Core check_and_correct flow extracted from CorrectionController."""

import logging
import time
from typing import Any, Dict, List, Optional

from prometheus_client import Gauge

from common.db import create_zone_event
from config.settings import get_settings
from correction_freshness import validate_freshness_or_skip
from correction_state_machine import CorrectionStateMachine
from services.targets_accessor import get_ec_target, get_ph_target

from correction_controller_signals import (
    emit_correction_actuator_unavailable_signal,
    emit_ec_batch_unavailable_signal,
    emit_ph_batch_unavailable_signal,
)
from correction_controller_check_steps import (
    handle_pending_effect_evaluation,
    resolve_correction_policy,
    resolve_safety_target,
)

logger = logging.getLogger(__name__)
PID_SATURATION_RATIO = Gauge(
    "pid_saturation_ratio",
    "Share of PID computations that hit output saturation",
    ["zone_id", "metric"],
)


async def check_and_correct_core(
    controller: Any,
    zone_id: int,
    targets: Dict[str, Any],
    telemetry: Dict[str, Optional[float]],
    telemetry_timestamps: Optional[Dict[str, Any]] = None,
    nodes: Dict[str, Dict[str, Any]] = None,
    water_level_ok: bool = True,
    actuators: Optional[Dict[str, Dict[str, Any]]] = None,
    bounds_overrides: Optional[Dict[str, Any]] = None,
    allowed_ec_components: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Проверка и корректировка параметра (pH или EC).
    """
    target_key = controller.correction_type.value
    state_machine = CorrectionStateMachine(zone_id=zone_id, metric=target_key, state="sense")
    current = telemetry.get(controller.metric_name) or telemetry.get(target_key)
    if controller.correction_type.value == "ph":
        target, target_min, target_max = get_ph_target(targets, zone_id=zone_id)
    else:
        target, target_min, target_max = get_ec_target(targets, zone_id=zone_id)

    if target is None or current is None:
        await state_machine.transition(
            "cooldown",
            "sense_missing_inputs",
            {"target": target, "current": current},
        )
        logger.debug(
            "Zone %s: %s correction skipped due to missing target/current",
            zone_id,
            controller.metric_name,
            extra={
                "zone_id": zone_id,
                "metric": controller.metric_name,
                "current": current,
                "target": target,
            },
        )
        return None

    logger.debug(
        "Zone %s: evaluating %s correction",
        zone_id,
        controller.metric_name,
        extra={
            "zone_id": zone_id,
            "metric": controller.metric_name,
            "current": current,
            "target": target,
            "target_min": target_min,
            "target_max": target_max,
            "water_level_ok": water_level_ok,
            "allowed_ec_components": allowed_ec_components,
            "bounds_overrides": bounds_overrides,
        },
    )

    freshness_ok = await validate_freshness_or_skip(
        zone_id=zone_id,
        metric_name=controller.metric_name,
        target_key=target_key,
        correction_type=controller.correction_type.value,
        current=current,
        target=target,
        telemetry_timestamps=telemetry_timestamps,
        freshness_check_failure_count=controller._freshness_check_failure_count,
        event_prefix=controller.event_prefix,
    )
    if not freshness_ok:
        await state_machine.transition("cooldown", "gate_freshness_failed")
        return None

    try:
        target_val = float(target)
        current_val = float(current)
    except (ValueError, TypeError) as exc:
        await state_machine.transition("cooldown", "sense_invalid_target_or_current")
        controller._log_skip(
            zone_id=zone_id,
            reason_code="invalid_target_or_current",
            target=target,
            current=current,
            error=str(exc),
        )
        return None

    target_original_val = target_val
    settings = get_settings()
    await handle_pending_effect_evaluation(
        controller,
        zone_id=zone_id,
        target_key=target_key,
        current_val=current_val,
        settings=settings,
    )

    safety_result = await resolve_safety_target(
        controller,
        zone_id=zone_id,
        target_key=target_key,
        target_val=target_val,
        target_original_val=target_original_val,
        current_val=current_val,
        targets=targets,
        bounds_overrides=bounds_overrides,
        settings=settings,
    )
    if safety_result is None:
        await state_machine.transition("cooldown", "gate_safety_target_blocked")
        return None
    target_val = float(safety_result["target_val"])
    safety_active = bool(safety_result["safety_active"])
    bounds_context = dict(safety_result["bounds_context"] or {})
    rate_limit_result = dict(safety_result["rate_limit_result"] or {})

    if target_min is not None and target_max is not None and target_min <= current_val <= target_max:
        await state_machine.transition("cooldown", "gate_target_in_range")
        logger.debug(
            "Zone %s: %s correction skipped - value inside target range",
            zone_id,
            controller.metric_name,
            extra={
                "zone_id": zone_id,
                "metric": controller.metric_name,
                "current": current_val,
                "target_min": target_min,
                "target_max": target_max,
            },
        )
        return None

    diff = current_val - target_val
    pid = await controller._get_pid(zone_id, target_val)
    policy_result = await resolve_correction_policy(
        controller,
        zone_id=zone_id,
        target_key=target_key,
        current_val=current_val,
        target_val=target_val,
        diff=diff,
        pid=pid,
        settings=settings,
    )
    if policy_result is None:
        await state_machine.transition("cooldown", "gate_policy_blocked")
        return None
    proactive_mode = bool(policy_result["proactive_mode"])
    proactive_payload = dict(policy_result["proactive_payload"] or {})
    reason = str(policy_result["reason"] or "")

    if not water_level_ok:
        await state_machine.transition("cooldown", "gate_water_level_not_ok")
        controller._log_skip(zone_id=zone_id, reason_code="water_level_not_ok")
        return None

    correction_type_diff = float(proactive_payload.get("predicted_diff") or diff)
    correction_type = controller._determine_correction_type(correction_type_diff)
    blocked_until = controller._resolve_anomaly_block_until(zone_id)
    if blocked_until is not None:
        block_remaining_sec = max(0, int(blocked_until - time.monotonic()))
        anomaly_override_enabled = bool(
            getattr(settings, "AE_EQUIPMENT_ANOMALY_CRITICAL_OVERRIDE_ENABLED", True)
        )
        override_diff_threshold = (
            float(getattr(settings, "AE_EQUIPMENT_ANOMALY_PH_OVERRIDE_DIFF", 0.45))
            if controller.correction_type.value == "ph"
            else float(getattr(settings, "AE_EQUIPMENT_ANOMALY_EC_OVERRIDE_DIFF", 0.6))
        )
        critical_override = anomaly_override_enabled and abs(correction_type_diff) >= max(
            0.0,
            override_diff_threshold,
        )
        if critical_override:
            logger.warning(
                "Zone %s: anomaly block overridden for critical %s deviation",
                zone_id,
                controller.metric_name,
                extra={
                    "zone_id": zone_id,
                    "metric": controller.metric_name,
                    "correction_type": correction_type,
                    "diff": correction_type_diff,
                    "threshold": override_diff_threshold,
                    "block_remaining_sec": block_remaining_sec,
                    "reason_code": "equipment_anomaly_block_override_critical_diff",
                },
            )
            await create_zone_event(
                zone_id,
                f"{controller.event_prefix}_CORRECTION_ANOMALY_OVERRIDE",
                {
                    "metric": target_key,
                    "reason_code": "equipment_anomaly_block_override_critical_diff",
                    "correction_type": correction_type,
                    "diff": correction_type_diff,
                    "threshold": override_diff_threshold,
                    "block_remaining_sec": block_remaining_sec,
                    "status": "warning",
                },
            )
        else:
            await state_machine.transition("cooldown", "gate_equipment_anomaly_block_active")
            controller._log_skip(
                zone_id=zone_id,
                reason_code="equipment_anomaly_block_active",
                correction_type=correction_type,
                block_remaining_sec=block_remaining_sec,
            )
            await create_zone_event(
                zone_id,
                f"{controller.event_prefix}_CORRECTION_SKIPPED_ANOMALY",
                {
                    "metric": target_key,
                    "reason_code": "equipment_anomaly_block_active",
                    "block_remaining_sec": block_remaining_sec,
                    "correction_type": correction_type,
                    "status": "degraded",
                },
            )
            return None

    await state_machine.transition("plan", "gate_passed")
    actuator = controller._select_actuator(correction_type=correction_type, actuators=actuators, nodes=nodes)
    if not actuator:
        await state_machine.transition("cooldown", "plan_actuator_unavailable")
        available_roles = sorted(list((actuators or {}).keys()))
        controller._log_skip(
            zone_id=zone_id,
            reason_code="actuator_unavailable",
            correction_type=correction_type,
            available_roles=available_roles,
        )
        if controller.correction_type.value == "ph":
            await emit_ph_batch_unavailable_signal(
                zone_id=zone_id,
                correction_type=correction_type,
                target_ph=target_val,
                current_ph=current_val,
                actuators=actuators,
            )
        else:
            await emit_correction_actuator_unavailable_signal(
                zone_id=zone_id,
                metric_name=target_key,
                correction_type=correction_type,
                available_roles=available_roles,
            )
        return None

    dt_seconds = controller._get_dt_seconds(zone_id)
    amount = pid.compute(current_val, dt_seconds)
    compute_count = max(1, int(getattr(pid.stats, "compute_count", 0)))
    saturation_count = int(getattr(pid.stats, "saturation_count", 0))
    saturation_ratio = float(saturation_count) / float(compute_count)
    PID_SATURATION_RATIO.labels(zone_id=str(zone_id), metric=controller.metric_name).set(saturation_ratio)
    logger.debug(
        "Zone %s: %s PID calculation",
        zone_id,
        controller.metric_name,
        extra={
            "zone_id": zone_id,
            "metric": controller.metric_name,
            "current": current_val,
            "target": target_val,
            "error": diff,
            "pid_zone": pid.get_zone().value,
            "pid_output": amount,
            "pid_integral": pid.integral,
            "pid_prev_error": pid.prev_error,
            "pid_dt": dt_seconds,
            "pid_saturation_ratio": saturation_ratio,
            "pid_config": {
                "dead_zone": pid.config.dead_zone,
                "close_zone": pid.config.close_zone,
                "far_zone": pid.config.far_zone,
                "kp": pid.config.zone_coeffs[pid.get_zone()].kp,
                "ki": pid.config.zone_coeffs[pid.get_zone()].ki,
                "kd": pid.config.zone_coeffs[pid.get_zone()].kd,
            },
        },
    )

    if amount > 0:
        await create_zone_event(
            zone_id,
            "PID_OUTPUT",
            {
                "type": controller.correction_type.value,
                "zone_state": pid.get_zone().value,
                "output": amount,
                "error": diff,
                "dt_seconds": dt_seconds,
                "current": current_val,
                "target": target_val,
                "safety_skip_reason": None,
            },
        )
    else:
        await state_machine.transition("cooldown", "plan_pid_output_zero")
        controller._log_skip(
            zone_id=zone_id,
            reason_code="pid_output_zero",
            level="info",
            pid_zone=pid.get_zone().value,
            pid_dt_seconds=dt_seconds,
        )
        return None

    payload = controller._build_correction_command(actuator, correction_type, amount)
    batch_commands: List[Dict[str, Any]] = []
    if controller.correction_type.value == "ec" and correction_type == "add_nutrients":
        batch_commands = controller._build_ec_component_batch(
            targets=targets,
            actuators=actuators,
            total_ml=amount,
            current_ec=current_val,
            target_ec=target_val,
            allowed_ec_components=allowed_ec_components,
        )
        if not batch_commands:
            await emit_ec_batch_unavailable_signal(
                zone_id=zone_id,
                allowed_ec_components=allowed_ec_components,
                target_ec=target_val,
                current_ec=current_val,
                total_ml=amount,
                actuators=actuators,
            )
            return None

    command: Dict[str, Any] = {
        "node_uid": actuator["node_uid"],
        "channel": actuator["channel"],
        "cmd": payload["cmd"],
        "params": payload["params"],
        "event_type": controller._get_correction_event_type(),
        "event_details": {
            "correction_type": correction_type,
            f"current_{target_key}": current_val,
            f"target_{target_key}": target_val,
            f"target_{target_key}_original": target_original_val,
            "diff": diff,
            "ml": amount,
            "binding_role": actuator.get("role"),
            "pid_zone": pid.get_zone().value,
            "pid_dt_seconds": dt_seconds,
            "safety_bounds_active": safety_active,
            "target_rate_limited": bool(rate_limit_result.get("clamped")),
            "proactive_mode": proactive_mode,
        },
        "zone_id": zone_id,
        "correction_type_str": target_key,
        "current_value": current_val,
        "target_value": target_val,
        "reason": reason,
    }

    nutrition_control = controller._extract_nutrition_control(targets)
    if nutrition_control:
        command["nutrition_control"] = nutrition_control
    if batch_commands:
        command["batch_commands"] = batch_commands
        command["event_details"]["component_dosing"] = [
            {
                "component": item.get("component"),
                "binding_role": item.get("role"),
                "ml": item.get("ml"),
                "ratio_pct": item.get("ratio_pct"),
                "mode": item.get("mode"),
                "k_ms_per_ml_l": item.get("k_ms_per_ml_l"),
                "channel": item.get("channel"),
            }
            for item in batch_commands
        ]
    if bounds_context:
        command["event_details"]["bounds"] = {
            "hard_pct": bounds_context.get("hard_pct"),
            "abs_min": bounds_context.get("abs_min"),
            "abs_max": bounds_context.get("abs_max"),
            "max_delta_per_min": bounds_context.get("max_delta_per_min"),
        }
    if proactive_mode:
        command["event_details"]["proactive"] = {
            "reason_code": proactive_payload.get("reason_code"),
            "slope_per_min": proactive_payload.get("slope_per_min"),
            "predicted_diff": proactive_payload.get("predicted_diff"),
            "predicted_value": proactive_payload.get("predicted_value"),
            "predicted_deviation": proactive_payload.get("predicted_deviation"),
            "horizon_minutes": proactive_payload.get("horizon_minutes"),
            "samples_count": proactive_payload.get("samples_count"),
        }

    command["state_machine"] = {"state": state_machine.state, "reason_code": "plan_ready"}

    return command
