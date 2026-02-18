"""Policy helpers for PH/EC target evaluation."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

ReadMetricFn = Callable[..., Awaitable[Dict[str, Any]]]


def is_value_within_pct(*, value: float, target: float, tolerance_pct: float) -> bool:
    if target <= 0:
        return abs(value - target) <= max(0.1, tolerance_pct / 100.0)
    tolerance_abs = abs(target) * (tolerance_pct / 100.0)
    return abs(value - target) <= tolerance_abs


async def evaluate_ph_ec_targets(
    *,
    read_metric: ReadMetricFn,
    zone_id: int,
    target_ph: float,
    target_ec: float,
    tolerance: Dict[str, float],
    telemetry_freshness_enforce: bool,
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

    ph_ok = is_value_within_pct(
        value=float(ph_sample["value"]),
        target=target_ph,
        tolerance_pct=float(tolerance.get("ph_pct", 5.0)),
    )
    ec_ok = is_value_within_pct(
        value=float(ec_sample["value"]),
        target=target_ec,
        tolerance_pct=float(tolerance.get("ec_pct", 10.0)),
    )
    return {
        "has_data": True,
        "is_stale": False,
        "targets_reached": bool(ph_ok and ec_ok),
        "ph_ok": ph_ok,
        "ec_ok": ec_ok,
        "ph": ph_sample,
        "ec": ec_sample,
        "target_ph": target_ph,
        "target_ec": target_ec,
        "tolerance": tolerance,
    }


__all__ = ["evaluate_ph_ec_targets", "is_value_within_pct"]
