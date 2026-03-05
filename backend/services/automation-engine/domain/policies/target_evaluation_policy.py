"""Policy helpers for PH/EC target evaluation."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

ReadMetricFn = Callable[..., Awaitable[Dict[str, Any]]]


def is_value_within_pct(*, value: float, target: float, tolerance_pct: float) -> bool:
    if target <= 0:
        return abs(value - target) <= max(0.1, tolerance_pct / 100.0)
    tolerance_abs = abs(target) * (tolerance_pct / 100.0)
    return abs(value - target) <= tolerance_abs


def is_value_within_abs(*, value: float, target: float, tolerance_abs: float) -> bool:
    return abs(value - target) <= max(0.0, float(tolerance_abs))


def is_value_within_hard_bounds(
    *,
    value: float,
    target: float,
    lower_bound: Optional[float],
    upper_bound: Optional[float],
    fallback_abs_tolerance: Optional[float],
    fallback_pct_ok: bool,
) -> bool:
    lower = lower_bound
    upper = upper_bound

    if lower is None and upper is None:
        if fallback_abs_tolerance is not None:
            return is_value_within_abs(value=value, target=target, tolerance_abs=float(fallback_abs_tolerance))
        return bool(fallback_pct_ok)

    if lower is None:
        lower = target - max(0.0, float(fallback_abs_tolerance or 0.0))
    if upper is None:
        upper = target + max(0.0, float(fallback_abs_tolerance or 0.0))
    if lower > upper:
        lower, upper = upper, lower
    return float(lower) <= value <= float(upper)


async def evaluate_ph_ec_targets(
    *,
    read_metric: ReadMetricFn,
    zone_id: int,
    target_ph: float,
    target_ec: float,
    tolerance: Dict[str, float],
    telemetry_freshness_enforce: bool,
    absolute_tolerance: Optional[Dict[str, float]] = None,
    hard_bounds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    ph_sample = await read_metric(zone_id=zone_id, sensor_type="PH")
    ec_sample = await read_metric(zone_id=zone_id, sensor_type="EC")

    if not ph_sample["has_value"] or not ec_sample["has_value"]:
        return {
            "has_data": False,
            "is_stale": bool(ph_sample["is_stale"] or ec_sample["is_stale"]),
            "targets_reached": False,
            "ph": ph_sample,
            "ec": ec_sample,
        }

    if telemetry_freshness_enforce and (ph_sample["is_stale"] or ec_sample["is_stale"]):
        return {
            "has_data": True,
            "is_stale": True,
            "targets_reached": False,
            "ph": ph_sample,
            "ec": ec_sample,
        }

    ph_ok_pct = is_value_within_pct(
        value=float(ph_sample["value"]),
        target=target_ph,
        tolerance_pct=float(tolerance.get("ph_pct", 5.0)),
    )
    ec_ok_pct = is_value_within_pct(
        value=float(ec_sample["value"]),
        target=target_ec,
        tolerance_pct=float(tolerance.get("ec_pct", 10.0)),
    )
    abs_cfg = absolute_tolerance if isinstance(absolute_tolerance, dict) else {}
    bounds_cfg = hard_bounds if isinstance(hard_bounds, dict) else {}
    ph_abs = abs_cfg.get("ph_abs")
    ec_abs = abs_cfg.get("ec_abs")
    ph_ok = is_value_within_hard_bounds(
        value=float(ph_sample["value"]),
        target=target_ph,
        lower_bound=bounds_cfg.get("ph_min"),
        upper_bound=bounds_cfg.get("ph_max"),
        fallback_abs_tolerance=float(ph_abs) if ph_abs is not None else None,
        fallback_pct_ok=ph_ok_pct,
    )
    ec_ok = is_value_within_hard_bounds(
        value=float(ec_sample["value"]),
        target=target_ec,
        lower_bound=bounds_cfg.get("ec_min"),
        upper_bound=bounds_cfg.get("ec_max"),
        fallback_abs_tolerance=float(ec_abs) if ec_abs is not None else None,
        fallback_pct_ok=ec_ok_pct,
    )
    return {
        "has_data": True,
        "is_stale": False,
        "targets_reached": bool(ph_ok and ec_ok),
        "ph_ok": ph_ok,
        "ec_ok": ec_ok,
        "ph_ok_pct": ph_ok_pct,
        "ec_ok_pct": ec_ok_pct,
        "ph": ph_sample,
        "ec": ec_sample,
        "target_ph": target_ph,
        "target_ec": target_ec,
        "tolerance": tolerance,
        "absolute_tolerance": abs_cfg,
        "hard_bounds": bounds_cfg,
    }


__all__ = ["evaluate_ph_ec_targets", "is_value_within_pct", "is_value_within_abs", "is_value_within_hard_bounds"]
