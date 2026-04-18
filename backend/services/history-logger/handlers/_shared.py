"""Shared constants и helpers между MQTT handlers.

Всё, что ранее было на уровне модуля ``mqtt_handlers`` до первого handler'а —
константы, буферы pending config reports, trace-context helpers, normalisation
утилиты для node_event / command_response.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from collections import OrderedDict
from typing import Any, Dict, Optional

from common.command_status_queue import CommandStatus
from common.db import fetch
from common.trace_context import set_trace_id_from_payload
from common.utils.time import utcnow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config & constants
# ---------------------------------------------------------------------------

PENDING_CONFIG_REPORT_TTL_SEC = int(os.getenv("CONFIG_REPORT_BUFFER_TTL_SEC", "120"))
PENDING_CONFIG_REPORT_MAX = int(os.getenv("CONFIG_REPORT_BUFFER_MAX", "128"))
TRANSIENT_WARNING_TTL_SEC = float(os.getenv("MQTT_HANDLER_TRANSIENT_WARNING_TTL_SEC", "30"))
CONFIG_REPORT_DEFAULT_ALLOW_PRUNE = os.getenv(
    "CONFIG_REPORT_PRUNE_MISSING_CHANNELS", "false"
).strip().lower() in {"1", "true", "yes", "on"}

ZONE_EVENT_TYPE_MAX_LEN = 255
ZONE_EVENT_TYPE_HASH_LEN = 10

PROTECTED_NODE_CHANNEL_CONFIG_KEYS = frozenset(
    {
        "pump_calibration",
        "flow_calibration",
        "pid",
        "pid_config",
        "pid_state",
    }
)

NODE_EVENT_METRIC_FALLBACK = "OTHER"
NODE_EVENT_METRIC_ALLOWED_CODES = {
    "NODE_EVENT",
    "LEVEL_SWITCH_CHANGED",
    "CLEAN_FILL_SOURCE_EMPTY",
    "CLEAN_FILL_STARTED",
    "CLEAN_FILL_COMPLETED",
    "CLEAN_FILL_TIMEOUT",
    "CLEAN_FILL_FAILED",
    "SOLUTION_FILL_SOURCE_EMPTY",
    "SOLUTION_FILL_LEAK_DETECTED",
    "SOLUTION_FILL_STARTED",
    "SOLUTION_FILL_COMPLETED",
    "SOLUTION_FILL_TIMEOUT",
    "SOLUTION_FILL_FAILED",
    "PREPARE_RECIRCULATION_TIMEOUT",
    "RECIRCULATION_SOLUTION_LOW",
    "IRRIGATION_SOLUTION_LOW",
    "EMERGENCY_STOP_ACTIVATED",
    "SOLUTION_PREP_STARTED",
    "SOLUTION_PREP_COMPLETED",
    "SOLUTION_PREP_FAILED",
    "IRRIGATION_STARTED",
    "IRRIGATION_COMPLETED",
    "IRRIGATION_FAILED",
    "IRRIGATION_RECOVERY_STARTED",
    "IRRIGATION_RECOVERY_COMPLETED",
    "IRRIGATION_RECOVERY_FAILED",
}

IRR_STATE_SNAPSHOT_EVENT_TYPE = "IRR_STATE_SNAPSHOT"
IRR_STATE_ALIASES = {
    "clean_level_max": ("clean_level_max", "level_clean_max"),
    "clean_level_min": ("clean_level_min", "level_clean_min"),
    "solution_level_max": ("solution_level_max", "level_solution_max"),
    "solution_level_min": ("solution_level_min", "level_solution_min"),
    "valve_clean_fill": ("valve_clean_fill",),
    "valve_clean_supply": ("valve_clean_supply",),
    "valve_solution_fill": ("valve_solution_fill",),
    "valve_solution_supply": ("valve_solution_supply",),
    "valve_irrigation": ("valve_irrigation",),
    "pump_main": ("pump_main", "main_pump"),
}


# ---------------------------------------------------------------------------
# Module-level state (shared buffers)
# ---------------------------------------------------------------------------

PENDING_CONFIG_REPORTS: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
PENDING_CONFIG_REPORTS_LOCK = asyncio.Lock()
BINDING_COMPLETION_LOCKS: dict[int, asyncio.Lock] = {}
BINDING_COMPLETION_LOCKS_GUARD = asyncio.Lock()
_transient_warning_last_seen: dict[tuple[str, str], float] = {}


# ---------------------------------------------------------------------------
# Transient log helpers (rate-limited warning/info)
# ---------------------------------------------------------------------------


def log_transient_warning(kind: str, entity: str, message: str) -> None:
    now = utcnow().timestamp()
    key = (kind, entity)
    last = _transient_warning_last_seen.get(key)
    if last is not None and (now - last) < TRANSIENT_WARNING_TTL_SEC:
        logger.debug(message)
        return
    _transient_warning_last_seen[key] = now
    logger.warning(message)


def log_transient_info(kind: str, entity: str, message: str) -> None:
    now = utcnow().timestamp()
    key = (kind, entity)
    last = _transient_warning_last_seen.get(key)
    if last is not None and (now - last) < TRANSIENT_WARNING_TTL_SEC:
        logger.debug(message)
        return
    _transient_warning_last_seen[key] = now
    logger.info(message)


# ---------------------------------------------------------------------------
# Command status mapping
# ---------------------------------------------------------------------------


def resolve_stub_insert_status(normalized_status: CommandStatus) -> str:
    """Для unknown cmd_id вставляем pre-terminal status — terminal side-effects
    формируются в Laravel через commandAck, а не теряются на early-return.
    """
    terminal_statuses = {
        CommandStatus.DONE,
        CommandStatus.ERROR,
        CommandStatus.INVALID,
        CommandStatus.BUSY,
        CommandStatus.NO_EFFECT,
        CommandStatus.TIMEOUT,
        CommandStatus.SEND_FAILED,
    }
    if normalized_status in terminal_statuses:
        return CommandStatus.ACK.value
    return normalized_status.value


# ---------------------------------------------------------------------------
# Pending config reports buffer (node hello ↔ config_report race)
# ---------------------------------------------------------------------------


def prune_pending_config_reports_locked(now_ts: float) -> None:
    if not PENDING_CONFIG_REPORTS:
        return
    expired_keys = [
        hardware_id
        for hardware_id, entry in PENDING_CONFIG_REPORTS.items()
        if now_ts - entry.get("ts", now_ts) > PENDING_CONFIG_REPORT_TTL_SEC
    ]
    for hardware_id in expired_keys:
        PENDING_CONFIG_REPORTS.pop(hardware_id, None)


async def store_pending_config_report(hardware_id: str, topic: str, payload: bytes) -> None:
    now_ts = utcnow().timestamp()
    async with PENDING_CONFIG_REPORTS_LOCK:
        prune_pending_config_reports_locked(now_ts)
        PENDING_CONFIG_REPORTS[hardware_id] = {
            "topic": topic,
            "payload": payload,
            "ts": now_ts,
        }
        PENDING_CONFIG_REPORTS.move_to_end(hardware_id)

        while len(PENDING_CONFIG_REPORTS) > PENDING_CONFIG_REPORT_MAX:
            dropped_hardware_id, _ = PENDING_CONFIG_REPORTS.popitem(last=False)
            logger.warning(
                "[CONFIG_REPORT] Dropped buffered config_report due to buffer limit: hardware_id=%s",
                dropped_hardware_id,
            )


async def pop_pending_config_report(hardware_id: str) -> Optional[Dict[str, Any]]:
    now_ts = utcnow().timestamp()
    async with PENDING_CONFIG_REPORTS_LOCK:
        prune_pending_config_reports_locked(now_ts)
        return PENDING_CONFIG_REPORTS.pop(hardware_id, None)


# ---------------------------------------------------------------------------
# Per-node binding lock (avoid concurrent binding completion for same node_id)
# ---------------------------------------------------------------------------


async def get_binding_completion_lock(node_id: int) -> asyncio.Lock:
    async with BINDING_COMPLETION_LOCKS_GUARD:
        lock = BINDING_COMPLETION_LOCKS.get(node_id)
        if lock is None:
            lock = asyncio.Lock()
            BINDING_COMPLETION_LOCKS[node_id] = lock
        return lock


# ---------------------------------------------------------------------------
# Trace + payload normalisation
# ---------------------------------------------------------------------------


def apply_trace_context(
    payload_data: Dict[str, Any], *, fallback_keys: Optional[tuple[str, ...]] = None
) -> None:
    if fallback_keys:
        set_trace_id_from_payload(payload_data, keys=fallback_keys, fallback_generate=False)
    else:
        set_trace_id_from_payload(payload_data, fallback_generate=False)


def normalize_command_response_details(raw_details: Any) -> Dict[str, Any]:
    if raw_details is None:
        return {}
    if isinstance(raw_details, dict):
        return dict(raw_details)
    raise ValueError("'details' must be object when present")


def to_optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def normalize_irr_state_snapshot(raw_snapshot: Any) -> Optional[Dict[str, bool]]:
    if not isinstance(raw_snapshot, dict):
        return None
    snapshot: Dict[str, bool] = {}
    for field, aliases in IRR_STATE_ALIASES.items():
        for alias in aliases:
            if alias not in raw_snapshot:
                continue
            value = to_optional_bool(raw_snapshot.get(alias))
            if value is not None:
                snapshot[field] = value
            break
    if not snapshot:
        return None
    return snapshot


def normalize_node_event_type(raw_event_code: Any) -> str:
    event_code = str(raw_event_code or "").strip().upper()
    if not event_code:
        return "NODE_EVENT"
    normalized = re.sub(r"[^A-Z0-9]+", "_", event_code)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    normalized = normalized or "NODE_EVENT"
    if len(normalized) <= ZONE_EVENT_TYPE_MAX_LEN:
        return normalized
    hash_suffix = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[
        :ZONE_EVENT_TYPE_HASH_LEN
    ].upper()
    trimmed_len = ZONE_EVENT_TYPE_MAX_LEN - ZONE_EVENT_TYPE_HASH_LEN - 1
    return f"{normalized[:trimmed_len]}_{hash_suffix}"


def metric_event_code_label(event_type: str) -> str:
    if event_type in NODE_EVENT_METRIC_ALLOWED_CODES:
        return event_type
    return NODE_EVENT_METRIC_FALLBACK


def normalize_node_event_payload(
    *,
    topic: str,
    gh_uid: Optional[str],
    zone_uid: Optional[str],
    node_uid: Optional[str],
    channel: Optional[str],
    event_code: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    normalized_snapshot = normalize_irr_state_snapshot(data.get("snapshot"))
    if normalized_snapshot is None:
        normalized_snapshot = normalize_irr_state_snapshot(data.get("state"))
    normalized_state = to_optional_bool(data.get("state"))
    normalized_initial = to_optional_bool(data.get("initial"))
    payload: Dict[str, Any] = {
        "source": "node_event",
        "topic": topic,
        "gh_uid": gh_uid,
        "zone_uid": zone_uid,
        "node_uid": node_uid,
        "channel": channel,
        "event_code": event_code,
        "payload": data,
    }
    if normalized_state is not None:
        payload["state"] = normalized_state
    if normalized_initial is not None:
        payload["initial"] = normalized_initial
    if normalized_snapshot is not None:
        payload["snapshot"] = normalized_snapshot
    if data.get("ts") is not None:
        payload["ts"] = data.get("ts")
    cmd_id = str(data.get("cmd_id") or "").strip()
    if cmd_id:
        payload["cmd_id"] = cmd_id
    return payload


def build_node_event_notify_payload(
    *,
    channel: Optional[str],
    event_type: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    notify_payload: Dict[str, Any] = {
        "source": "node_event",
        "channel": channel,
        "event_type": event_type,
    }
    for field_name in ("state", "initial", "node_uid", "topic", "cmd_id", "ts", "snapshot"):
        if field_name in payload:
            notify_payload[field_name] = payload[field_name]
    return notify_payload


async def resolve_zone_id_for_node_event(
    zone_uid: Optional[str], node_uid: Optional[str]
) -> Optional[int]:
    if zone_uid:
        zone_uid_str = str(zone_uid).strip()
        if zone_uid_str.startswith("zn-"):
            try:
                return int(zone_uid_str.split("-", 1)[1])
            except (ValueError, IndexError):
                pass
        else:
            try:
                return int(zone_uid_str)
            except ValueError:
                pass

        zone_rows = await fetch(
            """
            SELECT id
            FROM zones
            WHERE uid = $1
            LIMIT 1
            """,
            zone_uid_str,
        )
        if zone_rows:
            return zone_rows[0].get("id")

    if node_uid:
        node_rows = await fetch(
            """
            SELECT zone_id
            FROM nodes
            WHERE uid = $1
            LIMIT 1
            """,
            node_uid,
        )
        if node_rows:
            return node_rows[0].get("zone_id")

    return None
