"""Signal helpers for correction-gating alerts in zone automation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List


ResolveCorrectionSensorNodesFn = Callable[[Dict[str, Dict[str, Any]]], List[Dict[str, Any]]]
SendInfraAlertFn = Callable[..., Awaitable[bool]]
UtcNowFn = Callable[[], datetime]


async def emit_correction_missing_flags_signal(
    *,
    zone_id: int,
    gating_state: Dict[str, Any],
    nodes: Dict[str, Dict[str, Any]],
    zone_state: Dict[str, Any],
    utcnow_fn: UtcNowFn,
    resolve_correction_sensor_nodes_fn: ResolveCorrectionSensorNodesFn,
    send_infra_alert_fn: SendInfraAlertFn,
    correction_flags_missing_alert_throttle_seconds: int,
    logger: Any,
) -> None:
    now = utcnow_fn()
    last_reported = zone_state.get("last_missing_correction_flags_report_at")
    if isinstance(last_reported, datetime) and (
        now - last_reported
    ).total_seconds() < correction_flags_missing_alert_throttle_seconds:
        return

    missing_flags = list(gating_state.get("missing_flags") or [])
    correction_flags = gating_state.get("flags") if isinstance(gating_state.get("flags"), dict) else {}
    sensor_nodes = [node.get("node_uid") for node in resolve_correction_sensor_nodes_fn(nodes)]

    logger.warning(
        "Zone %s: correction skipped, missing flags=%s, sensor_nodes=%s",
        zone_id,
        missing_flags,
        sensor_nodes,
        extra={
            "zone_id": zone_id,
            "missing_flags": missing_flags,
            "sensor_nodes": sensor_nodes,
            "correction_flags": correction_flags,
        },
    )

    alert_sent = await send_infra_alert_fn(
        code="infra_correction_flags_missing",
        alert_type="Correction Flags Missing",
        message=f"Zone {zone_id} skipped correction due to missing sensor-mode flags",
        severity="warning",
        zone_id=zone_id,
        service="automation-engine",
        component="correction_gating",
        error_type="missing_flags",
        details={
            "missing_flags": missing_flags,
            "correction_flags": correction_flags,
            "sensor_nodes": sensor_nodes,
            "throttle_seconds": correction_flags_missing_alert_throttle_seconds,
        },
    )
    if alert_sent:
        zone_state["last_missing_correction_flags_report_at"] = now


async def emit_correction_stale_flags_signal(
    *,
    zone_id: int,
    gating_state: Dict[str, Any],
    nodes: Dict[str, Dict[str, Any]],
    zone_state: Dict[str, Any],
    utcnow_fn: UtcNowFn,
    resolve_correction_sensor_nodes_fn: ResolveCorrectionSensorNodesFn,
    send_infra_alert_fn: SendInfraAlertFn,
    correction_flags_stale_alert_throttle_seconds: int,
    logger: Any,
) -> None:
    now = utcnow_fn()
    last_reported = zone_state.get("last_stale_correction_flags_report_at")
    if isinstance(last_reported, datetime) and (
        now - last_reported
    ).total_seconds() < correction_flags_stale_alert_throttle_seconds:
        return

    stale_flags = list(gating_state.get("stale_flags") or [])
    stale_flag_reasons = (
        gating_state.get("stale_flag_reasons") if isinstance(gating_state.get("stale_flag_reasons"), dict) else {}
    )
    correction_flags = gating_state.get("flags") if isinstance(gating_state.get("flags"), dict) else {}
    flag_age_seconds = gating_state.get("flag_age_seconds") if isinstance(gating_state.get("flag_age_seconds"), dict) else {}
    timestamp_diagnostics = (
        gating_state.get("timestamp_diagnostics") if isinstance(gating_state.get("timestamp_diagnostics"), dict) else {}
    )
    require_timestamps = bool(gating_state.get("require_timestamps"))
    sensor_nodes = [node.get("node_uid") for node in resolve_correction_sensor_nodes_fn(nodes)]

    logger.warning(
        "Zone %s: correction skipped, stale flags=%s, sensor_nodes=%s",
        zone_id,
        stale_flags,
        sensor_nodes,
        extra={
            "zone_id": zone_id,
            "stale_flags": stale_flags,
            "stale_flag_reasons": stale_flag_reasons,
            "sensor_nodes": sensor_nodes,
            "flag_age_seconds": flag_age_seconds,
            "timestamp_diagnostics": timestamp_diagnostics,
            "require_timestamps": require_timestamps,
            "correction_flags": correction_flags,
        },
    )

    alert_sent = await send_infra_alert_fn(
        code="infra_correction_flags_stale",
        alert_type="Correction Flags Stale",
        message=f"Zone {zone_id} skipped correction due to stale sensor-mode flags",
        severity="warning",
        zone_id=zone_id,
        service="automation-engine",
        component="correction_gating",
        error_type="stale_flags",
        details={
            "stale_flags": stale_flags,
            "stale_flag_reasons": stale_flag_reasons,
            "flag_age_seconds": flag_age_seconds,
            "timestamp_diagnostics": timestamp_diagnostics,
            "require_timestamps": require_timestamps,
            "correction_flags": correction_flags,
            "sensor_nodes": sensor_nodes,
            "throttle_seconds": correction_flags_stale_alert_throttle_seconds,
        },
    )
    if alert_sent:
        zone_state["last_stale_correction_flags_report_at"] = now


__all__ = [
    "emit_correction_missing_flags_signal",
    "emit_correction_stale_flags_signal",
]
