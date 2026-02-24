"""Helpers for ventilation climate safety guards."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

from domain.models.decision_models import DecisionOutcome

ReadLatestMetricFn = Callable[..., Awaitable[Dict[str, Any]]]
ToOptionalFloatFn = Callable[[Any], Optional[float]]
WithDecisionDetailsFn = Callable[[DecisionOutcome, Dict[str, Any]], DecisionOutcome]


def _extract_guard_thresholds(payload: Dict[str, Any], to_optional_float_fn: ToOptionalFloatFn) -> tuple[Optional[float], Optional[float]]:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    limits = execution.get("limits") if isinstance(execution.get("limits"), dict) else {}
    external_guard = execution.get("external_guard") if isinstance(execution.get("external_guard"), dict) else {}

    strong_wind_mps = to_optional_float_fn(
        execution.get("strong_wind_mps")
        or limits.get("strong_wind_mps")
        or external_guard.get("strong_wind_mps")
        or external_guard.get("wind_max")
    )
    low_outside_temp_c = to_optional_float_fn(
        execution.get("low_outside_temp_c")
        or execution.get("low_outside_temperature_c")
        or limits.get("low_outside_temp_c")
        or limits.get("low_outside_temperature_c")
        or external_guard.get("low_outside_temp_c")
        or external_guard.get("temp_min")
    )
    return strong_wind_mps, low_outside_temp_c


async def apply_ventilation_climate_guards(
    *,
    zone_id: int,
    payload: Dict[str, Any],
    decision: DecisionOutcome,
    read_latest_metric_fn: ReadLatestMetricFn,
    to_optional_float_fn: ToOptionalFloatFn,
    with_decision_details_fn: WithDecisionDetailsFn,
    wind_blocked_reason: str,
    outside_temp_blocked_reason: str,
) -> DecisionOutcome:
    if not decision.action_required:
        return decision

    strong_wind_mps, low_outside_temp_c = _extract_guard_thresholds(payload, to_optional_float_fn)
    fallback_reasons: List[str] = []

    if strong_wind_mps is not None:
        wind = await read_latest_metric_fn(zone_id=zone_id, sensor_type="WIND_SPEED")
        wind_value = to_optional_float_fn(wind.get("value"))
        if wind.get("has_value") and not wind.get("is_stale") and wind_value is not None and wind_value >= strong_wind_mps:
            return DecisionOutcome(
                action_required=False,
                decision="skip",
                reason_code=wind_blocked_reason,
                reason=(
                    f"Вентиляция заблокирована: скорость ветра {wind_value:.2f} м/с "
                    f"выше порога {strong_wind_mps:.2f} м/с"
                ),
            )
        if not wind.get("has_value") or wind.get("is_stale") or wind_value is None:
            fallback_reasons.append("wind_metric_unavailable")

    if low_outside_temp_c is not None:
        outside = await read_latest_metric_fn(zone_id=zone_id, sensor_type="OUTSIDE_TEMP")
        outside_temp = to_optional_float_fn(outside.get("value"))
        if (
            outside.get("has_value")
            and not outside.get("is_stale")
            and outside_temp is not None
            and outside_temp <= low_outside_temp_c
        ):
            return DecisionOutcome(
                action_required=False,
                decision="skip",
                reason_code=outside_temp_blocked_reason,
                reason=(
                    f"Вентиляция заблокирована: наружная температура {outside_temp:.2f}°C "
                    f"ниже порога {low_outside_temp_c:.2f}°C"
                ),
            )
        if not outside.get("has_value") or outside.get("is_stale") or outside_temp is None:
            fallback_reasons.append("outside_temp_metric_unavailable")

    if fallback_reasons:
        fallback_decision = DecisionOutcome(
            action_required=decision.action_required,
            decision=decision.decision,
            reason_code="climate_external_nodes_unavailable",
            reason="Внешние climate-метрики недоступны, применен fallback режим",
            details=decision.details,
        )
        return with_decision_details_fn(
            fallback_decision,
            {
                "safety_flags": ["climate_external_nodes_unavailable"],
                "fallback_source_reason_code": decision.reason_code,
                "fallback_source_reason": decision.reason,
                "climate_fallback": {
                    "active": True,
                    "reasons": fallback_reasons,
                },
            },
        )

    return decision


__all__ = ["apply_ventilation_climate_guards"]
