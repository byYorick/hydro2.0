"""CommandBus dedupe helpers."""

import hashlib
import json
import time
from typing import Any, Dict, Optional

from common.commands import new_command_id

from .command_bus_shared import (
    _MAX_COMMAND_DEDUPE_ENTRIES,
    COMMAND_DEDUPE_DECISIONS,
    COMMAND_DEDUPE_HITS,
    COMMAND_DEDUPE_RESERVE_CONFLICTS,
)


def resolve_dedupe_ttl_sec(command_bus: Any, params: Optional[Dict[str, Any]] = None) -> int:
    ttl_raw: Any = None
    if isinstance(params, dict):
        ttl_raw = params.get("dedupe_ttl_sec")
    try:
        ttl_value = int(ttl_raw) if ttl_raw is not None else int(command_bus.command_dedupe_ttl_sec)
    except Exception:
        ttl_value = int(command_bus.command_dedupe_ttl_sec)
    return max(10, ttl_value)


def normalized_json_payload(payload: Any) -> str:
    try:
        return json.dumps(payload if payload is not None else {}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except Exception:
        return json.dumps({"__repr__": repr(payload)}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_dedupe_reference_key(
    command_bus: Any,
    *,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    params: Optional[Dict[str, Any]],
) -> str:
    material = "|".join(
        [
            str(int(zone_id)),
            str(node_uid or "").strip().lower(),
            str(channel or "").strip().lower(),
            str(cmd or "").strip().lower(),
            command_bus._normalized_json_payload(params),
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"zone:{int(zone_id)}:cmd:{digest}"


def build_dedupe_scope_key(
    command_bus: Any,
    *,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
) -> str:
    # Scope key groups commands by actuator endpoint regardless of params.
    # This lets us invalidate stale dedupe entries after a state-flip command.
    return "|".join(
        [
            str(int(zone_id)),
            str(node_uid or "").strip().lower(),
            str(channel or "").strip().lower(),
            str(cmd or "").strip().lower(),
        ]
    )


def evict_conflicting_scope_entries_locked(
    command_bus: Any,
    *,
    scope_key: str,
    reference_key: str,
) -> None:
    if not scope_key:
        return
    stale_keys = [
        key
        for key, entry in command_bus._dedupe_store.items()
        if key != reference_key and str(entry.get("scope_key") or "") == scope_key
    ]
    for key in stale_keys:
        command_bus._dedupe_store.pop(key, None)


def prune_dedupe_store_locked(command_bus: Any, now_monotonic: float) -> None:
    stale_keys = [
        key
        for key, entry in command_bus._dedupe_store.items()
        if float(entry.get("expires_at_monotonic", 0.0)) <= now_monotonic
    ]
    for key in stale_keys:
        command_bus._dedupe_store.pop(key, None)
    if len(command_bus._dedupe_store) <= _MAX_COMMAND_DEDUPE_ENTRIES:
        return

    sorted_items = sorted(
        command_bus._dedupe_store.items(),
        key=lambda item: float(item[1].get("expires_at_monotonic", now_monotonic)),
    )
    overflow = len(command_bus._dedupe_store) - _MAX_COMMAND_DEDUPE_ENTRIES
    for key, _ in sorted_items[:overflow]:
        command_bus._dedupe_store.pop(key, None)


async def reserve_command_dedupe(
    command_bus: Any,
    *,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    params: Optional[Dict[str, Any]],
    cmd_id: Optional[str],
    dedupe_ttl_sec: int,
) -> Dict[str, Any]:
    reference_key = command_bus._build_dedupe_reference_key(
        zone_id=zone_id,
        node_uid=node_uid,
        channel=channel,
        cmd=cmd,
        params=params,
    )
    scope_key = command_bus._build_dedupe_scope_key(
        zone_id=zone_id,
        node_uid=node_uid,
        channel=channel,
        cmd=cmd,
    )
    if not command_bus.command_dedupe_enabled:
        return {
            "decision": "new",
            "reference_key": reference_key,
            "scope_key": scope_key,
            "dedupe_ttl_sec": dedupe_ttl_sec,
            "reservation_token": None,
            "effective_cmd_id": cmd_id,
        }

    now_monotonic = time.monotonic()
    now_iso = time.time()
    async with command_bus._dedupe_lock:
        command_bus._prune_dedupe_store_locked(now_monotonic)
        command_bus._evict_conflicting_scope_entries_locked(
            scope_key=scope_key,
            reference_key=reference_key,
        )
        existing = command_bus._dedupe_store.get(reference_key)
        if existing is not None and float(existing.get("expires_at_monotonic", 0.0)) > now_monotonic:
            status = str(existing.get("status") or "").strip().lower()
            effective_cmd_id = str(existing.get("cmd_id") or "").strip() or None
            if status == "reserved":
                COMMAND_DEDUPE_DECISIONS.labels(outcome="duplicate_blocked").inc()
                COMMAND_DEDUPE_HITS.labels(outcome="duplicate_blocked").inc()
                COMMAND_DEDUPE_RESERVE_CONFLICTS.inc()
                return {
                    "decision": "duplicate_blocked",
                    "reference_key": reference_key,
                    "scope_key": scope_key,
                    "dedupe_ttl_sec": dedupe_ttl_sec,
                    "reservation_token": None,
                    "effective_cmd_id": effective_cmd_id,
                }
            COMMAND_DEDUPE_DECISIONS.labels(outcome="duplicate_no_effect").inc()
            COMMAND_DEDUPE_HITS.labels(outcome="duplicate_no_effect").inc()
            return {
                "decision": "duplicate_no_effect",
                "reference_key": reference_key,
                "scope_key": scope_key,
                "dedupe_ttl_sec": dedupe_ttl_sec,
                "reservation_token": None,
                "effective_cmd_id": effective_cmd_id,
            }

        reservation_token = hashlib.sha256(f"{reference_key}:{now_iso}:{new_command_id()}".encode("utf-8")).hexdigest()
        command_bus._dedupe_store[reference_key] = {
            "status": "reserved",
            "reservation_token": reservation_token,
            "created_at_monotonic": now_monotonic,
            "expires_at_monotonic": now_monotonic + float(dedupe_ttl_sec),
            "cmd_id": str(cmd_id or "").strip() or None,
            "scope_key": scope_key,
        }
        COMMAND_DEDUPE_DECISIONS.labels(outcome="new").inc()
        return {
            "decision": "new",
            "reference_key": reference_key,
            "scope_key": scope_key,
            "dedupe_ttl_sec": dedupe_ttl_sec,
            "reservation_token": reservation_token,
            "effective_cmd_id": str(cmd_id or "").strip() or None,
        }


async def bind_dedupe_cmd_id(command_bus: Any, dedupe_state: Optional[Dict[str, Any]], cmd_id: Optional[str]) -> None:
    if not dedupe_state or not command_bus.command_dedupe_enabled:
        return
    reservation_token = str(dedupe_state.get("reservation_token") or "").strip()
    reference_key = str(dedupe_state.get("reference_key") or "").strip()
    resolved_cmd_id = str(cmd_id or "").strip()
    if not reservation_token or not reference_key or not resolved_cmd_id:
        return

    now_monotonic = time.monotonic()
    async with command_bus._dedupe_lock:
        entry = command_bus._dedupe_store.get(reference_key)
        if entry is None:
            return
        if str(entry.get("reservation_token") or "") != reservation_token:
            return
        entry["cmd_id"] = resolved_cmd_id
        entry["expires_at_monotonic"] = max(float(entry.get("expires_at_monotonic", now_monotonic)), now_monotonic)


async def complete_command_dedupe(
    command_bus: Any,
    dedupe_state: Optional[Dict[str, Any]],
    *,
    success: bool,
) -> None:
    if not dedupe_state or not command_bus.command_dedupe_enabled:
        return
    reference_key = str(dedupe_state.get("reference_key") or "").strip()
    reservation_token = str(dedupe_state.get("reservation_token") or "").strip()
    dedupe_ttl_sec = int(dedupe_state.get("dedupe_ttl_sec") or command_bus.command_dedupe_ttl_sec)
    if not reference_key or not reservation_token:
        return

    now_monotonic = time.monotonic()
    async with command_bus._dedupe_lock:
        entry = command_bus._dedupe_store.get(reference_key)
        if entry is None:
            return
        if str(entry.get("reservation_token") or "") != reservation_token:
            return
        if success:
            entry["status"] = "published"
            entry["expires_at_monotonic"] = now_monotonic + float(max(10, dedupe_ttl_sec))
        else:
            command_bus._dedupe_store.pop(reference_key, None)
