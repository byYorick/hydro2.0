"""Correction domain policy: calibration."""

from __future__ import annotations

from typing import Any, Mapping

from ae3lite.domain.errors import PlannerConfigurationError
from ae3lite.domain.services.correction_math_defaults import _DEFAULT_MAX_DOSE_MS, _logger
from ae3lite.domain.services.correction_primitives import _positive_float, _positive_int


def _require_solution_volume_l(correction_config: Mapping[str, Any]) -> float:
    """Validate ``solution_volume_l`` for config completeness (metadata/UI).

    The value is required in zone correction config but does not participate
    in PID dose ml calculations in ``_compute_amount_ml``.
    """
    raw = correction_config.get("solution_volume_l")
    if raw is None:
        raise PlannerConfigurationError("В correction_config отсутствует solution_volume_l")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise PlannerConfigurationError(f"correction_config.solution_volume_l некорректен: {raw!r}")
    if value <= 0:
        raise PlannerConfigurationError(f"correction_config.solution_volume_l должно быть > 0, получено {value}")
    return value


def _absorb_dual_calibration_mismatches(
    sink: list[dict[str, Any]],
    details: Mapping[str, Any],
) -> None:
    raw = details.get("dual_calibration_mismatches")
    if not isinstance(raw, list):
        return
    seen_fields = {str(item.get("field")) for item in sink if item.get("field")}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        field = str(item.get("field") or "").strip()
        if field and field in seen_fields:
            continue
        sink.append(dict(item))
        if field:
            seen_fields.add(field)


def _resolve_dose_duration(
    *,
    requested_ml: float,
    calibration: Mapping[str, Any],
    correction_config: Mapping[str, Any],
    log_context: Mapping[str, Any] | None = None,
) -> tuple[float, float, int, str, Mapping[str, Any]]:
    """Convert requested dose volume to effective ml + pump duration."""
    duration_ms, reason, details = _dose_ml_to_ms(
        requested_ml,
        calibration,
        correction_config,
        log_context=log_context,
    )
    effective_ml = float(requested_ml)
    if reason == "clamped_to_max_dose_ms":
        clamped_effective = details.get("effective_ml")
        if clamped_effective is not None:
            effective_ml = float(clamped_effective)
    return effective_ml, float(requested_ml), duration_ms, reason, details


def _effective_log_context(log_context: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if log_context:
        return log_context
    try:
        from ae3lite.infrastructure.log_context import get_log_context

        return get_log_context()
    except ImportError:
        return {}


def _dose_ml_to_ms(
    dose_ml: float,
    calibration: Mapping[str, Any],
    correction_config: Mapping[str, Any],
    *,
    log_context: Mapping[str, Any] | None = None,
) -> tuple[int, str, Mapping[str, Any]]:
    pump_calibration = correction_config.get("pump_calibration")
    if not isinstance(pump_calibration, Mapping):
        raise PlannerConfigurationError("В correction_config отсутствует pump_calibration")
    dual_mismatches = _collect_dual_calibration_mismatches(
        calibration,
        pump_calibration,
    )
    if dual_mismatches:
        mismatch_fail_closed = bool(pump_calibration.get("ml_per_sec_mismatch_fail_closed", True))
        if mismatch_fail_closed:
            raise PlannerConfigurationError(
                "Расхождение dual calibration между pump_calibrations и NodeConfig: "
                + "; ".join(item["message"] for item in dual_mismatches),
                code="pump_calibration_dual_source_mismatch",
            )
        for item in dual_mismatches:
            _logger.warning(
                "Dual calibration mismatch (%s): %s",
                item.get("field"),
                item.get("message"),
            )
    min_dose_ms = _positive_int(pump_calibration.get("min_dose_ms"), 0)
    ml_min = _positive_float(pump_calibration.get("ml_per_sec_min"), 0.0)
    ml_max = _positive_float(pump_calibration.get("ml_per_sec_max"), 0.0)
    # Hard-cap на максимальную длительность одной дозы. Защищает от runaway
    # pump и от рассинхрона с firmware: нода исполняет dose по NodeConfig
    # `ml_per_second` и режет duration по `safe_limits.max_duration_ms`.
    # Источники cap (берётся min):
    # - zone: `pump_calibration.max_dose_ms` (default `_DEFAULT_MAX_DOSE_MS`)
    # - per-pump: `calibration.max_duration_ms` / `calibration.node_max_dose_ms`
    max_dose_ms = _resolve_max_dose_ms(pump_calibration, calibration)
    if min_dose_ms <= 0 or ml_min <= 0 or ml_max <= 0 or ml_max < ml_min:
        raise PlannerConfigurationError(
            "Некорректный pump_calibration; ожидаются min_dose_ms/ml_per_sec_min/ml_per_sec_max"
        )
    if max_dose_ms <= 0 or max_dose_ms < min_dose_ms:
        raise PlannerConfigurationError(
            f"pump_calibration.max_dose_ms={max_dose_ms} должно быть положительным и >= min_dose_ms={min_dose_ms}"
        )
    raw = calibration.get("ml_per_sec")
    if raw is None:
        raise PlannerConfigurationError(
            "В калибровке насоса отсутствует ml_per_sec; невозможно вычислить длительность дозы"
        )
    try:
        ml_per_sec = float(raw)
    except (TypeError, ValueError):
        raise PlannerConfigurationError(f"Калибровка насоса ml_per_sec не является числом: {raw!r}")
    if ml_per_sec <= 0:
        raise PlannerConfigurationError(
            f"Калибровка насоса ml_per_sec должна быть положительной, получено {ml_per_sec}"
        )
    if not (ml_min <= ml_per_sec <= ml_max):
        raise PlannerConfigurationError(
            f"Калибровка насоса ml_per_sec={ml_per_sec} вне допустимого диапазона "
            f"[{ml_min}, {ml_max}]; проверьте данные калибровки насоса"
        )
    ctx = _effective_log_context(log_context)
    duration_ms = int(dose_ml / ml_per_sec * 1000)
    if duration_ms <= 0:
        return (0, "", {})
    if duration_ms < min_dose_ms:
        log_suffix = ""
        if ctx:
            log_suffix = " task_id=%s correction_window_id=%s zone_id=%s" % (
                ctx.get("task_id"),
                ctx.get("correction_window_id"),
                ctx.get("zone_id"),
            )
        _logger.warning(
            "Dose discarded: computed duration %dms is below minimum %dms "
            "(dose_ml=%.4f, ml_per_sec=%.4f). "
            "Check pump calibration or min_effective_ml setting.%s",
            duration_ms,
            min_dose_ms,
            dose_ml,
            ml_per_sec,
            log_suffix,
        )
        return (
            0,
            "below_min_dose_ms",
            {
                "computed_duration_ms": duration_ms,
                "min_dose_ms": min_dose_ms,
                "dose_ml": round(dose_ml, 4),
                "ml_per_sec": ml_per_sec,
                **({"dual_calibration_mismatches": dual_mismatches} if dual_mismatches else {}),
            },
        )
    if duration_ms > max_dose_ms:
        clamped_ms = max_dose_ms
        effective_ml = ml_per_sec * clamped_ms / 1000.0
        log_suffix = ""
        if ctx:
            log_suffix = " task_id=%s correction_window_id=%s zone_id=%s" % (
                ctx.get("task_id"),
                ctx.get("correction_window_id"),
                ctx.get("zone_id"),
            )
        _logger.warning(
            "Dose duration clamped to max_dose_ms: computed %dms > max %dms "
            "(requested_ml=%.4f, effective_ml=%.4f, ml_per_sec=%.4f). "
            "Possible calibration drift or oversized dose command.%s",
            duration_ms,
            max_dose_ms,
            dose_ml,
            effective_ml,
            ml_per_sec,
            log_suffix,
        )
        clamp_details: dict[str, Any] = {
            "computed_duration_ms": duration_ms,
            "max_dose_ms": max_dose_ms,
            "requested_ml": round(dose_ml, 4),
            "effective_ml": round(effective_ml, 4),
            "dose_ml": round(effective_ml, 4),
            "ml_per_sec": ml_per_sec,
        }
        node_cap = _positive_int(calibration.get("max_duration_ms"), 0)
        if node_cap <= 0:
            node_cap = _positive_int(calibration.get("node_max_dose_ms"), 0)
        if node_cap > 0:
            clamp_details["node_max_dose_ms"] = node_cap
        if dual_mismatches:
            clamp_details["dual_calibration_mismatches"] = dual_mismatches
        return (
            clamped_ms,
            "clamped_to_max_dose_ms",
            clamp_details,
        )
    details_ok: dict[str, Any] = {}
    if dual_mismatches:
        details_ok["dual_calibration_mismatches"] = dual_mismatches
    return (duration_ms, "", details_ok)


def _relative_pct_delta(left: float, right: float) -> float:
    baseline = max(abs(left), abs(right), 1e-9)
    return abs(left - right) / baseline * 100.0


def _collect_dual_calibration_mismatches(
    calibration: Mapping[str, Any],
    pump_calibration: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Compare DB pump_calibrations vs NodeConfig actuator mirror when both are present."""
    threshold_pct = _positive_float(
        pump_calibration.get("ml_per_sec_mismatch_pct"),
        10.0,
    )
    mismatches: list[dict[str, Any]] = []

    db_ml = calibration.get("ml_per_sec")
    node_ml = calibration.get("node_ml_per_second")
    if db_ml is not None and node_ml is not None:
        db_value = float(db_ml)
        node_value = float(node_ml)
        if db_value > 0 and node_value > 0:
            delta_pct = _relative_pct_delta(db_value, node_value)
            if delta_pct > threshold_pct:
                mismatches.append(
                    {
                        "field": "ml_per_sec",
                        "db_value": round(db_value, 6),
                        "node_value": round(node_value, 6),
                        "delta_pct": round(delta_pct, 4),
                        "threshold_pct": threshold_pct,
                        "message": (
                            f"ml_per_sec={db_value:.4f} vs node ml_per_second={node_value:.4f} "
                            f"(delta {delta_pct:.2f}% > {threshold_pct:.2f}%)"
                        ),
                    }
                )

    # Не сравниваем zone max_dose_ms с node safe_limits.max_duration_ms:
    # это разные семантики (policy cap vs hardware hard-limit). Enforcement
    # через min(zone, node) в _resolve_max_dose_ms остаётся; dual-mirror
    # mismatch только для сопоставимых калибровочных полей (ml_per_sec).

    return mismatches


def _resolve_max_dose_ms(
    pump_calibration: Mapping[str, Any],
    calibration: Mapping[str, Any],
) -> int:
    """Effective per-dose duration cap: min(zone policy, per-pump NodeConfig mirror)."""
    zone_cap = _positive_int(pump_calibration.get("max_dose_ms"), _DEFAULT_MAX_DOSE_MS)
    per_pump_cap = _positive_int(calibration.get("max_duration_ms"), 0)
    if per_pump_cap <= 0:
        per_pump_cap = _positive_int(calibration.get("node_max_dose_ms"), 0)
    if per_pump_cap > 0:
        return min(zone_cap, per_pump_cap)
    return zone_cap


def resolve_dose_feedback_from_response(
    *,
    planned_ml: float,
    planned_duration_ms: int,
    ml_per_sec: float,
    response_details: Mapping[str, Any] | None,
) -> tuple[float, int, bool]:
    """Согласовать план дозы с ACK/DONE feedback ноды (duration_limited / actual duration).

    Возвращает ``(effective_ml, actual_duration_ms, adjusted)``.
    Без ``response_details`` — planned values, ``adjusted=False`` (backward compatible).
    """
    planned_ml_f = max(0.0, float(planned_ml))
    planned_ms = max(0, int(planned_duration_ms))
    if not isinstance(response_details, Mapping) or not response_details:
        return planned_ml_f, planned_ms, False

    actual_ms = 0
    raw_actual = response_details.get("duration_ms")
    if raw_actual is not None:
        try:
            actual_ms = max(0, int(raw_actual))
        except (TypeError, ValueError):
            actual_ms = 0

    duration_limited = bool(response_details.get("duration_limited"))
    if not duration_limited and actual_ms > 0 and planned_ms > 0 and actual_ms < planned_ms:
        duration_limited = True

    if not duration_limited:
        resolved_ms = actual_ms if actual_ms > 0 else planned_ms
        return planned_ml_f, resolved_ms, False

    sec = max(0.0, float(ml_per_sec))
    if sec <= 0.0:
        node_mps = response_details.get("ml_per_second")
        if node_mps is None:
            node_mps = response_details.get("ml_per_sec")
        if node_mps is not None:
            try:
                sec = max(0.0, float(node_mps))
            except (TypeError, ValueError):
                sec = 0.0

    effective_ml = planned_ml_f
    if sec > 0.0 and actual_ms > 0:
        effective_ml = sec * actual_ms / 1000.0
    else:
        reported_ml = response_details.get("ml")
        if reported_ml is not None:
            try:
                effective_ml = float(reported_ml)
            except (TypeError, ValueError):
                effective_ml = planned_ml_f

    effective_ml = min(planned_ml_f, max(0.0, effective_ml))
    resolved_ms = actual_ms if actual_ms > 0 else planned_ms
    return round(effective_ml, 4), resolved_ms, True
