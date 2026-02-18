"""Safety bounds policy for pH/EC correction targets."""

from __future__ import annotations

from typing import Any, Dict, Optional


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _merge_metric_bounds(target: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(target)
    for key in ("hard_pct", "abs_min", "abs_max", "max_delta_per_min"):
        if key in incoming:
            merged[key] = incoming[key]
    return merged


def extract_bounds_overrides(targets: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract optional bounds overrides from known runtime paths."""
    root = _as_dict(targets)
    diagnostics = _as_dict(root.get("diagnostics"))
    diagnostics_execution = _as_dict(diagnostics.get("execution"))
    execution = _as_dict(root.get("execution"))
    extensions = _as_dict(root.get("extensions"))
    safety = _as_dict(extensions.get("safety"))

    candidates = (
        _as_dict(root.get("bounds")),
        _as_dict(execution.get("bounds")),
        _as_dict(diagnostics_execution.get("bounds")),
        _as_dict(safety.get("bounds")),
    )

    result: Dict[str, Dict[str, Any]] = {"ph": {}, "ec": {}}
    for candidate in candidates:
        for metric in ("ph", "ec"):
            metric_bounds = _as_dict(candidate.get(metric))
            if not metric_bounds:
                continue
            result[metric] = _merge_metric_bounds(result[metric], metric_bounds)

    return result


def _default_metric_bounds(metric: str, settings: Any) -> Dict[str, Any]:
    if metric == "ph":
        return {
            "hard_pct": float(getattr(settings, "AE_SAFETY_PH_HARD_PCT", 20.0)),
            "abs_min": float(getattr(settings, "AE_SAFETY_PH_ABS_MIN", 5.2)),
            "abs_max": float(getattr(settings, "AE_SAFETY_PH_ABS_MAX", 6.8)),
            "max_delta_per_min": float(getattr(settings, "AE_SAFETY_PH_MAX_DELTA_PER_MIN", 0.15)),
        }
    return {
        "hard_pct": float(getattr(settings, "AE_SAFETY_EC_HARD_PCT", 20.0)),
        "abs_min": float(getattr(settings, "AE_SAFETY_EC_ABS_MIN", 0.6)),
        "abs_max": float(getattr(settings, "AE_SAFETY_EC_ABS_MAX", 2.8)),
        "max_delta_per_min": float(getattr(settings, "AE_SAFETY_EC_MAX_DELTA_PER_MIN", 0.2)),
    }


def _extract_metric_candidates(metric: str, targets: Dict[str, Any], bounds_overrides: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    target_metric = _as_dict(_as_dict(targets).get(metric))
    target_bounds = _as_dict(target_metric.get("bounds"))
    target_candidate = {
        "hard_pct": target_metric.get("hard_pct", target_bounds.get("hard_pct")),
        "abs_min": target_metric.get("abs_min", target_metric.get("min", target_bounds.get("abs_min"))),
        "abs_max": target_metric.get("abs_max", target_metric.get("max", target_bounds.get("abs_max"))),
        "max_delta_per_min": target_metric.get(
            "max_delta_per_min",
            target_bounds.get("max_delta_per_min"),
        ),
    }

    overrides_metric = _as_dict(_as_dict(bounds_overrides).get(metric))
    return {
        "targets": target_candidate,
        "overrides": overrides_metric,
    }


def resolve_bounds(
    metric: str,
    targets: Dict[str, Any],
    bounds_overrides: Optional[Dict[str, Any]],
    settings: Any,
) -> Dict[str, Any]:
    """Resolve bounds with precedence override -> targets -> defaults."""
    metric_key = str(metric or "").strip().lower()
    defaults = _default_metric_bounds(metric_key, settings)
    candidates = _extract_metric_candidates(metric_key, targets, bounds_overrides)

    resolved: Dict[str, Any] = {
        "metric": metric_key,
        "hard_pct": defaults["hard_pct"],
        "abs_min": defaults["abs_min"],
        "abs_max": defaults["abs_max"],
        "max_delta_per_min": defaults["max_delta_per_min"],
        "config_errors": [],
    }

    for source in ("targets", "overrides"):
        candidate = _as_dict(candidates.get(source))
        for field in ("hard_pct", "abs_min", "abs_max", "max_delta_per_min"):
            if field not in candidate:
                continue
            raw_value = candidate.get(field)
            if raw_value is None:
                continue
            parsed = _to_float(raw_value)
            if parsed is None:
                resolved["config_errors"].append(f"{source}_{field}_not_numeric")
                continue
            resolved[field] = parsed

    if resolved["hard_pct"] <= 0:
        resolved["config_errors"].append("hard_pct_must_be_positive")
    if resolved["max_delta_per_min"] <= 0:
        resolved["config_errors"].append("max_delta_per_min_must_be_positive")
    if resolved["abs_min"] > resolved["abs_max"]:
        resolved["config_errors"].append("abs_min_gt_abs_max")

    return resolved


def validate_target_with_bounds(
    *,
    metric: str,
    target: float,
    bounds: Dict[str, Any],
    previous_target: Optional[float] = None,
) -> Dict[str, Any]:
    """Validate target against safety bounds and hard_pct rule."""
    if bounds.get("config_errors"):
        return {
            "valid": False,
            "reason_code": "bounds_config_invalid",
            "details": {"config_errors": list(bounds.get("config_errors") or [])},
        }

    abs_min = _to_float(bounds.get("abs_min"))
    abs_max = _to_float(bounds.get("abs_max"))
    if abs_min is not None and target < abs_min:
        return {
            "valid": False,
            "reason_code": "target_below_abs_min",
            "details": {"metric": metric, "target": target, "abs_min": abs_min, "abs_max": abs_max},
        }
    if abs_max is not None and target > abs_max:
        return {
            "valid": False,
            "reason_code": "target_above_abs_max",
            "details": {"metric": metric, "target": target, "abs_min": abs_min, "abs_max": abs_max},
        }

    hard_pct = _to_float(bounds.get("hard_pct"))
    if hard_pct is not None and previous_target is not None:
        base = abs(previous_target) if abs(previous_target) > 0 else max(abs(target), 1.0)
        allowed_delta = base * hard_pct / 100.0
        safe_min = previous_target - allowed_delta
        safe_max = previous_target + allowed_delta
        if target < safe_min or target > safe_max:
            return {
                "valid": False,
                "reason_code": "target_hard_pct_violation",
                "details": {
                    "metric": metric,
                    "target": target,
                    "previous_target": previous_target,
                    "hard_pct": hard_pct,
                    "safe_min": safe_min,
                    "safe_max": safe_max,
                },
            }

    return {"valid": True, "reason_code": None, "details": {}}


def apply_target_rate_limit(
    *,
    target: float,
    bounds: Dict[str, Any],
    previous_target: Optional[float],
    elapsed_seconds: Optional[float],
) -> Dict[str, Any]:
    """Clamp target change speed by max_delta_per_min."""
    if previous_target is None or elapsed_seconds is None or elapsed_seconds <= 0:
        return {"target": target, "clamped": False}

    max_delta_per_min = _to_float(bounds.get("max_delta_per_min"))
    if max_delta_per_min is None or max_delta_per_min <= 0:
        return {"target": target, "clamped": False}

    allowed_delta = max_delta_per_min * (elapsed_seconds / 60.0)
    delta = target - previous_target
    if abs(delta) <= allowed_delta:
        return {"target": target, "clamped": False, "allowed_delta": allowed_delta}

    clamped_target = previous_target + allowed_delta * (1.0 if delta > 0 else -1.0)
    return {
        "target": clamped_target,
        "clamped": True,
        "reason_code": "max_delta_per_min_clamped",
        "requested_target": target,
        "previous_target": previous_target,
        "allowed_delta": allowed_delta,
        "elapsed_seconds": elapsed_seconds,
    }


__all__ = [
    "apply_target_rate_limit",
    "extract_bounds_overrides",
    "resolve_bounds",
    "validate_target_with_bounds",
]
