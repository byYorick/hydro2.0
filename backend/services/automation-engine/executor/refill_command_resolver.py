"""Helpers for cycle-start refill command resolution."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

ExtractRefillConfigFn = Callable[[Dict[str, Any]], Dict[str, Any]]
NormalizeNodeTypeListFn = Callable[[Any, Sequence[str]], List[str]]
NormalizeTextListFn = Callable[[Any, Sequence[str]], List[str]]
ResolveRefillNodeFn = Callable[..., Awaitable[Dict[str, Any] | None]]
ResolveRefillDurationMsFn = Callable[[Dict[str, Any]], int]


async def resolve_refill_command(
    *,
    zone_id: int,
    payload: Dict[str, Any],
    extract_refill_config_fn: ExtractRefillConfigFn,
    normalize_node_type_list_fn: NormalizeNodeTypeListFn,
    normalize_text_list_fn: NormalizeTextListFn,
    resolve_refill_node_fn: ResolveRefillNodeFn,
    resolve_refill_duration_ms_fn: ResolveRefillDurationMsFn,
) -> Optional[Dict[str, Any]]:
    refill_cfg = extract_refill_config_fn(payload)
    requested_channel = str(refill_cfg.get("channel") or "").strip().lower()
    node_types = normalize_node_type_list_fn(refill_cfg.get("node_types"), ("irrig",))
    preferred_channels = normalize_text_list_fn(
        refill_cfg.get("preferred_channels"),
        (
            "valve_clean_fill",
            "pump_in",
            "fill_valve",
            "pump_main",
            "main_pump",
            "water_control",
            "default",
        ),
    )
    selected = await resolve_refill_node_fn(
        zone_id=zone_id,
        node_types=node_types,
        preferred_channels=preferred_channels,
        requested_channel=requested_channel,
    )
    if selected is None:
        return None

    cmd = str(refill_cfg.get("cmd") or "run_pump").strip() or "run_pump"
    params = dict(refill_cfg.get("params") if isinstance(refill_cfg.get("params"), dict) else {})
    if cmd == "run_pump" and "duration_ms" not in params:
        params["duration_ms"] = resolve_refill_duration_ms_fn(payload)
    if cmd == "set_relay" and "state" not in params:
        params["state"] = True

    return {"node": selected, "cmd": cmd, "params": params}


__all__ = ["resolve_refill_command"]
