"""Required-node online recovery gate for ZoneAutomationService."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List


CheckRequiredNodesOnlineFn = Callable[[int, List[str]], Awaitable[Dict[str, Any]]]
EmitRequiredNodesOfflineSignalFn = Callable[..., Awaitable[None]]
EmitRequiredNodesRecoveredSignalFn = Callable[..., Awaitable[None]]
UtcNowFn = Callable[[], Any]


def derive_required_node_types(capabilities: Dict[str, Any]) -> List[str]:
    required: List[str] = []
    if bool((capabilities or {}).get("ph_control")):
        required.append("ph")
    if bool((capabilities or {}).get("ec_control")):
        required.append("ec")
    if bool((capabilities or {}).get("climate_control")):
        required.append("climate")
    if bool((capabilities or {}).get("light_control")):
        required.append("light")
    if bool((capabilities or {}).get("irrigation_control")) or bool((capabilities or {}).get("recirculation")):
        required.append("irrig")
    return sorted(set(required))


async def evaluate_required_nodes_recovery_gate(
    *,
    zone_id: int,
    capabilities: Dict[str, Any],
    zone_state: Dict[str, Any],
    check_required_nodes_online_fn: CheckRequiredNodesOnlineFn,
    emit_required_nodes_offline_signal_fn: EmitRequiredNodesOfflineSignalFn,
    emit_required_nodes_recovered_signal_fn: EmitRequiredNodesRecoveredSignalFn,
    utcnow_fn: UtcNowFn,
    throttle_seconds: int,
    logger: Any,
) -> bool:
    required_types = derive_required_node_types(capabilities)
    if not required_types:
        return True

    online_state = await check_required_nodes_online_fn(zone_id, required_types)
    missing_types = [str(item).strip().lower() for item in (online_state.get("missing_types") or []) if str(item).strip()]
    online_counts = dict(online_state.get("online_counts") or {})
    last_reported = zone_state.get("last_required_nodes_offline_report_at")
    previous_missing = [
        str(item).strip().lower()
        for item in (zone_state.get("required_nodes_offline_missing_types") or [])
        if str(item).strip()
    ]
    now = utcnow_fn()

    if missing_types:
        should_emit = False
        if last_reported is None:
            should_emit = True
        else:
            try:
                elapsed = (now - last_reported).total_seconds()
                should_emit = elapsed >= max(1, int(throttle_seconds))
            except Exception:
                should_emit = True
        if sorted(missing_types) != sorted(previous_missing):
            should_emit = True

        zone_state["required_nodes_offline_active"] = True
        zone_state["required_nodes_offline_missing_types"] = sorted(missing_types)
        zone_state["required_nodes_offline_required_types"] = sorted(required_types)
        if zone_state.get("required_nodes_offline_since") is None:
            zone_state["required_nodes_offline_since"] = now
        if should_emit:
            await emit_required_nodes_offline_signal_fn(
                zone_id=zone_id,
                required_types=required_types,
                online_counts=online_counts,
                missing_types=sorted(missing_types),
            )
            zone_state["last_required_nodes_offline_report_at"] = now
        else:
            logger.debug(
                "Zone %s: required-node offline signal throttled",
                zone_id,
                extra={"zone_id": zone_id, "missing_types": sorted(missing_types)},
            )
        return False

    if zone_state.get("required_nodes_offline_active"):
        await emit_required_nodes_recovered_signal_fn(
            zone_id=zone_id,
            previous_missing_types=zone_state.get("required_nodes_offline_missing_types") or [],
            required_types=zone_state.get("required_nodes_offline_required_types") or required_types,
            online_counts=online_counts,
        )
        zone_state["required_nodes_offline_active"] = False
        zone_state["required_nodes_offline_missing_types"] = []
        zone_state["required_nodes_offline_required_types"] = sorted(required_types)
        zone_state["required_nodes_offline_since"] = None
        zone_state["last_required_nodes_offline_report_at"] = None

    return True


__all__ = [
    "derive_required_node_types",
    "evaluate_required_nodes_recovery_gate",
]
