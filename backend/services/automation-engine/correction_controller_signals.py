"""Signals for correction branches where execution is skipped."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Awaitable, Callable, Dict, Optional

from common.db import create_zone_event
from common.infra_alerts import send_infra_alert
from services.resilience_contract import (
    INFRA_CORRECTION_ACTUATOR_UNAVAILABLE,
    INFRA_CORRECTION_EC_BATCH_UNAVAILABLE,
    INFRA_CORRECTION_PH_BATCH_UNAVAILABLE,
)

CreateZoneEventFn = Callable[[int, str, Dict[str, Any]], Awaitable[Any]]
SendInfraAlertFn = Callable[..., Awaitable[bool]]

_EC_COMPONENT_ROLES = (
    "ec_npk_pump",
    "ec_calcium_pump",
    "ec_magnesium_pump",
    "ec_micro_pump",
)
_PH_COMPONENT_ROLES = ("ph_acid_pump", "ph_base_pump")


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def build_ec_batch_debug_payload(actuators: Optional[Dict[str, Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    payload: Dict[str, Dict[str, Any]] = {}
    for role in _EC_COMPONENT_ROLES:
        actuator_info = (actuators or {}).get(role)
        if not isinstance(actuator_info, dict):
            continue
        payload[role] = {
            "node_uid": _json_safe(actuator_info.get("node_uid")),
            "channel": _json_safe(actuator_info.get("channel")),
            "ml_per_sec": _json_safe(actuator_info.get("ml_per_sec")),
            "pump_calibration": _json_safe(actuator_info.get("pump_calibration")),
        }
    return payload


def build_ph_batch_debug_payload(actuators: Optional[Dict[str, Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    payload: Dict[str, Dict[str, Any]] = {}
    for role in _PH_COMPONENT_ROLES:
        actuator_info = (actuators or {}).get(role)
        if not isinstance(actuator_info, dict):
            continue
        payload[role] = {
            "node_uid": _json_safe(actuator_info.get("node_uid")),
            "channel": _json_safe(actuator_info.get("channel")),
            "ml_per_sec": _json_safe(actuator_info.get("ml_per_sec")),
            "pump_calibration": _json_safe(actuator_info.get("pump_calibration")),
        }
    return payload


async def emit_correction_actuator_unavailable_signal(
    *,
    zone_id: int,
    metric_name: str,
    correction_type: str,
    available_roles: list[str],
    send_infra_alert_fn: SendInfraAlertFn = send_infra_alert,
) -> None:
    details = _json_safe(
        {
            "metric": metric_name,
            "correction_type": correction_type,
            "available_roles": available_roles,
            "reason_code": "actuator_unavailable",
        }
    )
    await send_infra_alert_fn(
        code=INFRA_CORRECTION_ACTUATOR_UNAVAILABLE,
        alert_type="Correction Actuator Unavailable",
        message=(
            f"Zone {zone_id}: {metric_name} correction skipped - "
            f"actuator unavailable for {correction_type}"
        ),
        severity="warning",
        zone_id=zone_id,
        service="automation-engine",
        component="correction_controller",
        error_type="actuator_unavailable",
        details=details,
    )


async def emit_ec_batch_unavailable_signal(
    *,
    zone_id: int,
    allowed_ec_components: Optional[list[str]],
    target_ec: float,
    current_ec: float,
    total_ml: float,
    actuators: Optional[Dict[str, Dict[str, Any]]],
    create_zone_event_fn: CreateZoneEventFn = create_zone_event,
    send_infra_alert_fn: SendInfraAlertFn = send_infra_alert,
) -> None:
    available_roles = sorted(list((actuators or {}).keys()))
    ec_batch_debug = build_ec_batch_debug_payload(actuators)
    event_details = _json_safe(
        {
            "reason": "ec_component_batch_unavailable",
            "available_roles": available_roles,
            "allowed_ec_components": allowed_ec_components,
            "ec_batch_debug": ec_batch_debug,
            "target_ec": target_ec,
            "current_ec": current_ec,
            "total_ml": total_ml,
        }
    )

    await create_zone_event_fn(
        zone_id,
        "EC_CORRECTION_SKIPPED",
        event_details,
    )

    alert_details = _json_safe(
        {
            "metric": "ec",
            "reason_code": "ec_component_batch_unavailable",
            "available_roles": available_roles,
            "allowed_ec_components": allowed_ec_components,
            "ec_batch_debug": ec_batch_debug,
            "target_ec": target_ec,
            "current_ec": current_ec,
            "total_ml": total_ml,
        }
    )
    await send_infra_alert_fn(
        code=INFRA_CORRECTION_EC_BATCH_UNAVAILABLE,
        alert_type="EC Component Batch Unavailable",
        message=f"Zone {zone_id}: EC correction skipped - no dosing batch resolved",
        severity="warning",
        zone_id=zone_id,
        service="automation-engine",
        component="correction_controller",
        error_type="ec_component_batch_unavailable",
        details=alert_details,
    )


async def emit_ph_batch_unavailable_signal(
    *,
    zone_id: int,
    correction_type: str,
    target_ph: float,
    current_ph: float,
    actuators: Optional[Dict[str, Dict[str, Any]]],
    create_zone_event_fn: CreateZoneEventFn = create_zone_event,
    send_infra_alert_fn: SendInfraAlertFn = send_infra_alert,
) -> None:
    available_roles = sorted(list((actuators or {}).keys()))
    ph_batch_debug = build_ph_batch_debug_payload(actuators)
    event_details = _json_safe(
        {
            "reason": "ph_component_batch_unavailable",
            "correction_type": correction_type,
            "available_roles": available_roles,
            "ph_batch_debug": ph_batch_debug,
            "target_ph": target_ph,
            "current_ph": current_ph,
        }
    )

    await create_zone_event_fn(
        zone_id,
        "PH_CORRECTION_SKIPPED",
        event_details,
    )

    alert_details = _json_safe(
        {
            "metric": "ph",
            "reason_code": "ph_component_batch_unavailable",
            "correction_type": correction_type,
            "available_roles": available_roles,
            "ph_batch_debug": ph_batch_debug,
            "target_ph": target_ph,
            "current_ph": current_ph,
        }
    )
    await send_infra_alert_fn(
        code=INFRA_CORRECTION_PH_BATCH_UNAVAILABLE,
        alert_type="PH Component Batch Unavailable",
        message=f"Zone {zone_id}: PH correction skipped - no dosing batch resolved",
        severity="warning",
        zone_id=zone_id,
        service="automation-engine",
        component="correction_controller",
        error_type="ph_component_batch_unavailable",
        details=alert_details,
    )
