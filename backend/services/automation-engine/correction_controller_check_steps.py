"""Step helpers for CorrectionController.check_and_correct."""

import logging
import time
from typing import Any, Dict, List, Optional

from common.db import create_zone_event
from common.infra_alerts import send_infra_alert
from correction_cooldown import analyze_proactive_correction_signal, should_apply_correction, should_apply_proactive_correction
from services.correction_bounds_policy import apply_target_rate_limit, resolve_bounds, validate_target_with_bounds
from services.resilience_contract import INFRA_CORRECTION_ANOMALY_BLOCK

logger = logging.getLogger(__name__)


async def handle_pending_effect_evaluation(
    controller: Any,
    *,
    zone_id: int,
    target_key: str,
    current_val: float,
    settings: Any,
) -> None:
    pending_eval = controller._evaluate_pending_effect_window(
        zone_id=zone_id,
        current_value=current_val,
        settings=settings,
    )
    if not pending_eval:
        return

    pending = dict(pending_eval.get("pending") or {})
    if pending_eval.get("state") == "effect_confirmed":
        await create_zone_event(
            zone_id,
            f"{controller.event_prefix}_DOSE_EFFECT_CONFIRMED",
            {
                "metric": target_key,
                "reason_code": "dose_effect_confirmed",
                "observed_delta": pending_eval.get("observed_delta"),
                "min_effect_delta": pending_eval.get("min_delta"),
                "previous_streak": pending_eval.get("previous_streak"),
                "correction_type": pending.get("correction_type"),
                "correlation_id": pending.get("correlation_id"),
            },
        )
        return

    if pending_eval.get("state") != "no_effect_detected":
        return

    await create_zone_event(
        zone_id,
        f"{controller.event_prefix}_DOSE_NO_EFFECT",
        {
            "metric": target_key,
            "reason_code": "dose_no_effect",
            "observed_delta": pending_eval.get("observed_delta"),
            "min_effect_delta": pending_eval.get("min_delta"),
            "streak": pending_eval.get("streak"),
            "streak_threshold": pending_eval.get("streak_threshold"),
            "correction_type": pending.get("correction_type"),
            "correlation_id": pending.get("correlation_id"),
        },
    )
    if not bool(pending_eval.get("block_activated")):
        return

    block_until = pending_eval.get("block_until_monotonic")
    block_for_sec = max(0, int(float(block_until or time.monotonic()) - time.monotonic()))
    await create_zone_event(
        zone_id,
        f"{controller.event_prefix}_DOSING_BLOCKED_ANOMALY",
        {
            "metric": target_key,
            "reason_code": "equipment_anomaly_no_effect_streak",
            "streak": pending_eval.get("streak"),
            "streak_threshold": pending_eval.get("streak_threshold"),
            "block_for_seconds": block_for_sec,
            "status": "degraded",
            "correction_type": pending.get("correction_type"),
            "correlation_id": pending.get("correlation_id"),
        },
    )
    await send_infra_alert(
        code=INFRA_CORRECTION_ANOMALY_BLOCK,
        message=f"Zone {zone_id}: {controller.metric_name} dosing blocked due to no-effect streak",
        zone_id=zone_id,
        severity="warning",
        service="automation-engine",
        component="correction_controller",
        details={
            "metric": controller.metric_name,
            "streak": pending_eval.get("streak"),
            "streak_threshold": pending_eval.get("streak_threshold"),
            "block_for_seconds": block_for_sec,
            "reason_code": "equipment_anomaly_no_effect_streak",
        },
    )


async def resolve_safety_target(
    controller: Any,
    *,
    zone_id: int,
    target_key: str,
    target_val: float,
    target_original_val: float,
    current_val: float,
    targets: Dict[str, Any],
    bounds_overrides: Optional[Dict[str, Any]],
    settings: Any,
) -> Optional[Dict[str, Any]]:
    safety_enabled = bool(getattr(settings, "AE_SAFETY_BOUNDS_ENABLED", True))
    safety_kill_switch = bool(getattr(settings, "AE_SAFETY_BOUNDS_KILL_SWITCH", False))
    safety_active = safety_enabled and not safety_kill_switch
    bounds_context: Dict[str, Any] = {}
    rate_limit_result: Dict[str, Any] = {"clamped": False, "target": target_val}

    if not safety_active:
        controller._last_target_by_zone[zone_id] = target_val
        controller._last_target_ts_by_zone[zone_id] = time.monotonic()
        return {
            "target_val": target_val,
            "target_original_val": target_original_val,
            "safety_active": False,
            "bounds_context": bounds_context,
            "rate_limit_result": rate_limit_result,
        }

    bounds_context = resolve_bounds(
        metric=target_key,
        targets=targets,
        bounds_overrides=bounds_overrides,
        settings=settings,
    )
    previous_target = controller._last_target_by_zone.get(zone_id)
    previous_target_ts = controller._last_target_ts_by_zone.get(zone_id)
    now_target_ts = time.monotonic()
    elapsed_seconds = None if previous_target_ts is None else max(0.0, now_target_ts - previous_target_ts)

    bounds_validation = validate_target_with_bounds(
        metric=target_key,
        target=target_val,
        bounds=bounds_context,
        previous_target=previous_target,
    )
    if not bool(bounds_validation.get("valid")):
        reason_code = str(bounds_validation.get("reason_code") or "bounds_validation_failed")
        controller._log_skip(
            zone_id=zone_id,
            reason_code=reason_code,
            target=target_val,
            current=current_val,
            bounds=bounds_context,
            validation=bounds_validation.get("details"),
        )
        await create_zone_event(
            zone_id,
            f"{controller.event_prefix}_CORRECTION_SKIPPED_BOUNDS",
            {
                "metric": target_key,
                "reason_code": reason_code,
                "target": target_val,
                "current": current_val,
                "bounds": bounds_context,
                "validation": bounds_validation.get("details") or {},
            },
        )
        return None

    rate_limit_result = apply_target_rate_limit(
        target=target_val,
        bounds=bounds_context,
        previous_target=previous_target,
        elapsed_seconds=elapsed_seconds,
    )
    target_val = float(rate_limit_result.get("target", target_val))
    if bool(rate_limit_result.get("clamped")):
        await create_zone_event(
            zone_id,
            f"{controller.event_prefix}_TARGET_CLAMPED_RATE_LIMIT",
            {
                "metric": target_key,
                "requested_target": target_original_val,
                "effective_target": target_val,
                "previous_target": previous_target,
                "allowed_delta": rate_limit_result.get("allowed_delta"),
                "elapsed_seconds": rate_limit_result.get("elapsed_seconds"),
                "reason_code": str(rate_limit_result.get("reason_code") or "max_delta_per_min_clamped"),
            },
        )

    controller._last_target_by_zone[zone_id] = target_val
    controller._last_target_ts_by_zone[zone_id] = now_target_ts
    return {
        "target_val": target_val,
        "target_original_val": target_original_val,
        "safety_active": True,
        "bounds_context": bounds_context,
        "rate_limit_result": rate_limit_result,
    }


async def resolve_correction_policy(
    controller: Any,
    *,
    zone_id: int,
    target_key: str,
    current_val: float,
    target_val: float,
    diff: float,
    pid: Any,
    settings: Any,
) -> Optional[Dict[str, Any]]:
    proactive_mode = False
    proactive_payload: Dict[str, Any] = {}
    reason = ""

    if abs(diff) <= pid.config.dead_zone:
        proactive_payload = await analyze_proactive_correction_signal(
            zone_id=zone_id,
            metric_type=controller.metric_name,
            current_value=current_val,
            target_value=target_val,
            dead_zone=pid.config.dead_zone,
            settings=settings,
        )
        if not bool(proactive_payload.get("should_correct")):
            logger.debug(
                "Zone %s: %s correction skipped - diff within dead zone",
                zone_id,
                controller.metric_name,
                extra={
                    "zone_id": zone_id,
                    "metric": controller.metric_name,
                    "diff": diff,
                    "dead_zone": pid.config.dead_zone,
                    "proactive_reason_code": proactive_payload.get("reason_code"),
                },
            )
            return None

        projected_diff = float(proactive_payload.get("predicted_diff") or diff)
        proactive_allowed, proactive_reason = await should_apply_proactive_correction(
            zone_id=zone_id,
            correction_type=target_key,
            projected_diff=projected_diff,
        )
        if not proactive_allowed:
            controller._log_skip(
                zone_id=zone_id,
                reason_code="proactive_policy_blocked",
                level="info",
                diff=diff,
                projected_diff=projected_diff,
                reason=proactive_reason,
            )
            await create_zone_event(
                zone_id,
                f"{controller.event_prefix}_CORRECTION_SKIPPED",
                {
                    f"current_{target_key}": current_val,
                    f"target_{target_key}": target_val,
                    "diff": diff,
                    "reason": proactive_reason,
                    "reason_code": "proactive_policy_blocked",
                    "proactive": proactive_payload,
                },
            )
            return None

        proactive_mode = True
        reason = "Proactive correction triggered (predicted target escape)"
        await create_zone_event(
            zone_id,
            f"{controller.event_prefix}_PROACTIVE_CORRECTION_TRIGGERED",
            {
                "metric": target_key,
                "reason_code": str(proactive_payload.get("reason_code") or "proactive_triggered"),
                "diff": diff,
                "predicted_diff": proactive_payload.get("predicted_diff"),
                "predicted_value": proactive_payload.get("predicted_value"),
                "predicted_deviation": proactive_payload.get("predicted_deviation"),
                "slope_per_min": proactive_payload.get("slope_per_min"),
                "horizon_minutes": proactive_payload.get("horizon_minutes"),
                "samples_count": proactive_payload.get("samples_count"),
            },
        )
    else:
        should_correct, reason = await should_apply_correction(zone_id, target_key, current_val, target_val, diff)
        if not should_correct:
            controller._log_skip(
                zone_id=zone_id,
                reason_code="cooldown_or_trend_policy_blocked",
                level="info",
                reason=reason,
                diff=diff,
            )
            await create_zone_event(
                zone_id,
                f"{controller.event_prefix}_CORRECTION_SKIPPED",
                {
                    f"current_{target_key}": current_val,
                    f"target_{target_key}": target_val,
                    "diff": diff,
                    "reason": reason,
                },
            )
            return None

    return {
        "proactive_mode": proactive_mode,
        "proactive_payload": proactive_payload,
        "reason": reason,
    }

