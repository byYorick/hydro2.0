"""Диагностика доступности нод зоны для fail-closed AE3."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ae3lite.domain.errors import ErrorCodes, SnapshotBuildError

TWO_TANK_TOPOLOGIES = frozenset({"two_tank", "two_tank_drip_substrate_trays"})
TWO_TANK_REQUIRED_NODE_TYPES = frozenset({"irrig", "ph", "ec"})
IRRIGATION_TASK_TYPES = frozenset({"irrigation_start"})
CORRECTION_STAGE_PREFIXES = ("ph_", "ec_", "correction_", "prepare_recirc", "await_ready")

# Коды, при которых перед fail-closed проверяем, не offline ли целевая/обязательная нода.
NODE_TRANSPORT_ERROR_CODES = frozenset({
    "ae3_zone_lease_lost",
    "ae3_task_execution_timeout",
    ErrorCodes.COMMAND_SEND_FAILED,
    "command_send_failed",
    ErrorCodes.IRR_STATE_UNAVAILABLE,
    "irr_state_unavailable",
    ErrorCodes.IRR_STATE_STALE,
    "irr_state_stale",
    ErrorCodes.AE3_COMMAND_POLL_DEADLINE_EXCEEDED,
    "ae3_command_poll_deadline_exceeded",
    ErrorCodes.AE3_MISSING_AE_COMMAND,
    "ae3_missing_ae_command",
    ErrorCodes.TWO_TANK_CLEAN_LEVEL_UNAVAILABLE,
    "two_tank_clean_level_unavailable",
    ErrorCodes.TWO_TANK_CLEAN_LEVEL_STALE,
    "two_tank_clean_level_stale",
    ErrorCodes.TWO_TANK_SOLUTION_LEVEL_UNAVAILABLE,
    "two_tank_solution_level_unavailable",
    ErrorCodes.TWO_TANK_SOLUTION_LEVEL_STALE,
    "two_tank_solution_level_stale",
    ErrorCodes.TWO_TANK_CLEAN_MIN_LEVEL_UNAVAILABLE,
    "two_tank_clean_min_level_unavailable",
    ErrorCodes.TWO_TANK_SOLUTION_MIN_LEVEL_UNAVAILABLE,
    "two_tank_solution_min_level_unavailable",
    "irrigation_recovery_probe_exhausted",
    "biz_irr_probe_streak_exhausted",
    "command_timeout",
})

IRR_COMMAND_TRANSPORT_CODES = frozenset({
    ErrorCodes.IRR_STATE_UNAVAILABLE,
    "irr_state_unavailable",
    ErrorCodes.IRR_STATE_STALE,
    "irr_state_stale",
    ErrorCodes.COMMAND_SEND_FAILED,
    "command_send_failed",
    "command_timeout",
    ErrorCodes.AE3_COMMAND_POLL_DEADLINE_EXCEEDED,
    "ae3_command_poll_deadline_exceeded",
})

ZONE_NODES_DIAG_SQL = """
SELECT
    n.uid AS node_uid,
    LOWER(COALESCE(n.type, '')) AS node_type,
    LOWER(TRIM(COALESCE(n.status, ''))) AS status,
    EXTRACT(
        EPOCH FROM (
            NOW() - COALESCE(
                n.last_seen_at,
                n.last_heartbeat_at,
                n.updated_at
            )
        )
    )::BIGINT AS last_seen_age_sec,
    COUNT(nc.id) FILTER (
        WHERE UPPER(TRIM(COALESCE(nc.type, ''))) IN ('ACTUATOR', 'SERVICE')
          AND COALESCE(nc.is_active, TRUE) = TRUE
    ) AS active_actuator_count
FROM nodes n
LEFT JOIN node_channels nc
    ON nc.node_id = n.id
WHERE n.zone_id = $1
GROUP BY n.id
ORDER BY n.id ASC
"""


def node_persistent_dead_sec() -> int:
    return max(60, int(os.getenv("AE3_NODE_PERSISTENT_DEAD_SEC", "600")))


@dataclass(frozen=True)
class OfflineFailure:
    code: str
    message: str
    details: dict[str, Any]


def classify_zone_nodes(
    *,
    zone_id: int,
    diag_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Классифицирует ноды зоны по transient/persistent offline (как snapshot read-model)."""
    persistent_threshold = node_persistent_dead_sec()
    zone_nodes: list[dict[str, Any]] = []
    persistently_offline_uids: list[str] = []
    transiently_offline_uids: list[str] = []

    for row in diag_rows:
        uid = str(row.get("node_uid") or "").strip()
        if not uid:
            continue
        node_type = str(row.get("node_type") or "").strip().lower() or None
        status = str(row.get("status") or "").strip().lower() or None
        try:
            last_seen_age_sec = (
                int(row.get("last_seen_age_sec"))
                if row.get("last_seen_age_sec") is not None
                else None
            )
        except (TypeError, ValueError):
            last_seen_age_sec = None
        try:
            active_actuator_count = int(row.get("active_actuator_count") or 0)
        except (TypeError, ValueError):
            active_actuator_count = 0

        zone_nodes.append({
            "uid": uid,
            "type": node_type,
            "status": status,
            "last_seen_age_sec": last_seen_age_sec,
            "active_actuator_count": active_actuator_count,
        })

        if status == "online":
            continue
        if last_seen_age_sec is not None and last_seen_age_sec >= persistent_threshold:
            persistently_offline_uids.append(uid)
        else:
            transiently_offline_uids.append(uid)

    return {
        "zone_id": int(zone_id),
        "zone_nodes": zone_nodes,
        "persistently_offline_uids": persistently_offline_uids,
        "transiently_offline_uids": transiently_offline_uids,
        "persistent_dead_threshold_sec": persistent_threshold,
    }


async def fetch_zone_nodes_diagnostics(
    *,
    zone_id: int,
    conn: Any | None = None,
) -> dict[str, Any]:
    if conn is not None:
        rows = await conn.fetch(ZONE_NODES_DIAG_SQL, zone_id)
        return classify_zone_nodes(zone_id=zone_id, diag_rows=rows)

    from common.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as acquired:
        rows = await acquired.fetch(ZONE_NODES_DIAG_SQL, zone_id)
    return classify_zone_nodes(zone_id=zone_id, diag_rows=rows)


def _format_offline_nodes_message(*, offline_nodes: Sequence[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    for node in offline_nodes:
        uid = str(node.get("uid") or "").strip()
        node_type = str(node.get("type") or "").strip()
        status = str(node.get("status") or "offline").strip()
        age = node.get("last_seen_age_sec")
        suffix = f", последняя активность {age} с назад" if age is not None else ""
        label = f"{uid} ({node_type})" if node_type else uid
        parts.append(f"{label}: {status}{suffix}")
    return "Узел зоны недоступен (offline): " + "; ".join(parts)


def _offline_nodes_for_required_types(
    *,
    diagnostics: Mapping[str, Any],
    required_types: frozenset[str],
    persistent_only: bool,
) -> list[dict[str, Any]]:
    zone_nodes = diagnostics.get("zone_nodes")
    if not isinstance(zone_nodes, list):
        return []

    persistent_uids = {
        str(uid).strip()
        for uid in (diagnostics.get("persistently_offline_uids") or [])
        if str(uid).strip()
    }
    transient_uids = {
        str(uid).strip()
        for uid in (diagnostics.get("transiently_offline_uids") or [])
        if str(uid).strip()
    }

    offline: list[dict[str, Any]] = []
    for node in zone_nodes:
        if not isinstance(node, Mapping):
            continue
        node_type = str(node.get("type") or "").strip().lower()
        if node_type not in required_types:
            continue
        uid = str(node.get("uid") or "").strip()
        if not uid:
            continue
        status = str(node.get("status") or "").strip().lower()
        if status == "online":
            continue
        if persistent_only and uid not in persistent_uids:
            continue
        if not persistent_only and uid not in persistent_uids and uid not in transient_uids:
            continue
        offline.append(dict(node))
    return offline


def required_node_types_for_task(
    *,
    topology: str,
    task_type: str | None = None,
    current_stage: str | None = None,
) -> frozenset[str]:
    """Stage-scoped preflight: полив требует только irrig, коррекция — ph/ec."""
    normalized_topology = str(topology or "").strip().lower()
    normalized_task_type = str(task_type or "").strip().lower()
    normalized_stage = str(current_stage or "").strip().lower()

    if normalized_task_type in IRRIGATION_TASK_TYPES:
        return frozenset({"irrig"})

    if normalized_stage.startswith(CORRECTION_STAGE_PREFIXES):
        if normalized_topology in TWO_TANK_TOPOLOGIES:
            return frozenset({"ph", "ec"})
        return frozenset()

    if normalized_topology in TWO_TANK_TOPOLOGIES:
        return TWO_TANK_REQUIRED_NODE_TYPES

    return frozenset({"irrig"})


def resolve_required_nodes_offline_failure(
    *,
    zone_id: int,
    topology: str,
    diagnostics: Mapping[str, Any],
    persistent_only: bool = False,
    task_type: str | None = None,
    current_stage: str | None = None,
    required_types: frozenset[str] | None = None,
) -> OfflineFailure | None:
    """Возвращает fail-closed ошибку, если обязательные для топологии ноды offline."""
    normalized_topology = str(topology or "").strip().lower()
    if required_types is None:
        required_types = required_node_types_for_task(
            topology=normalized_topology,
            task_type=task_type,
            current_stage=current_stage,
        )

    zone_nodes = diagnostics.get("zone_nodes")
    if isinstance(zone_nodes, list):
        present_types = {
            str(node.get("type") or "").strip().lower()
            for node in zone_nodes
            if isinstance(node, Mapping) and str(node.get("type") or "").strip()
        }
        missing_types = sorted(required_types - present_types)
        if missing_types:
            return OfflineFailure(
                code=ErrorCodes.AE3_SNAPSHOT_REQUIRED_NODE_TYPE_MISSING,
                message=f"У зоны {zone_id} нет actuator-нод требуемых типов: {missing_types}",
                details={
                    "zone_id": zone_id,
                    "topology": normalized_topology,
                    "missing_node_types": missing_types,
                    "required_node_types": sorted(required_types),
                    **dict(diagnostics),
                },
            )

    offline_nodes = _offline_nodes_for_required_types(
        diagnostics=diagnostics,
        required_types=required_types,
        persistent_only=persistent_only,
    )
    if not offline_nodes:
        return None

    details = dict(diagnostics)
    details["offline_required_nodes"] = offline_nodes
    details["topology"] = normalized_topology
    details["required_node_types"] = sorted(required_types)

    persistent_uids = [str(n.get("uid") or "") for n in offline_nodes if str(n.get("uid") or "") in set(
        diagnostics.get("persistently_offline_uids") or []
    )]
    if persistent_uids and (persistent_only or len(persistent_uids) == len(offline_nodes)):
        return OfflineFailure(
            code=ErrorCodes.AE3_SNAPSHOT_REQUIRED_NODE_PERSISTENTLY_OFFLINE,
            message=_format_offline_nodes_message(offline_nodes=offline_nodes),
            details=details,
        )

    return OfflineFailure(
        code=ErrorCodes.AE3_REQUIRED_NODE_OFFLINE,
        message=_format_offline_nodes_message(offline_nodes=offline_nodes),
        details=details,
    )


def assert_required_nodes_available(
    *,
    zone_id: int,
    topology: str,
    diagnostics: Mapping[str, Any],
    persistent_only: bool = False,
    task_type: str | None = None,
    current_stage: str | None = None,
) -> None:
    failure = resolve_required_nodes_offline_failure(
        zone_id=zone_id,
        topology=topology,
        diagnostics=diagnostics,
        persistent_only=persistent_only,
        task_type=task_type,
        current_stage=current_stage,
    )
    if failure is None:
        return
    raise SnapshotBuildError(
        failure.message,
        code=failure.code,
        details=failure.details,
    )


def liveness_is_unreachable(
    liveness: Mapping[str, Any] | None,
    *,
    heartbeat_age_limit_sec: float = 30.0,
) -> bool:
    if not isinstance(liveness, Mapping):
        return False
    if liveness.get("found") is not True:
        return False
    status = str(liveness.get("status") or "").strip().lower()
    if status == "offline":
        return True
    heartbeat_age = liveness.get("heartbeat_age_sec")
    if heartbeat_age is not None and float(heartbeat_age) > float(heartbeat_age_limit_sec):
        return True
    return False


def should_remap_error_for_node_check(error_code: str) -> bool:
    normalized = str(error_code or "").strip().lower()
    if normalized in NODE_TRANSPORT_ERROR_CODES:
        return True
    if normalized.endswith("_unavailable") or normalized.endswith("_stale"):
        return True
    if "probe_exhausted" in normalized or "probe_streak" in normalized:
        return True
    return False


def offline_failure_for_node_uid(
    *,
    zone_id: int,
    node_uid: str,
    diagnostics: Mapping[str, Any],
) -> OfflineFailure | None:
    uid = str(node_uid or "").strip()
    if not uid:
        return None
    zone_nodes = diagnostics.get("zone_nodes")
    if not isinstance(zone_nodes, list):
        return None
    for node in zone_nodes:
        if not isinstance(node, Mapping):
            continue
        if str(node.get("uid") or "").strip() != uid:
            continue
        status = str(node.get("status") or "").strip().lower()
        if status == "online":
            return None
        return OfflineFailure(
            code=(
                ErrorCodes.AE3_SNAPSHOT_REQUIRED_NODE_PERSISTENTLY_OFFLINE
                if uid in set(diagnostics.get("persistently_offline_uids") or [])
                else ErrorCodes.AE3_REQUIRED_NODE_OFFLINE
            ),
            message=_format_offline_nodes_message(offline_nodes=[dict(node)]),
            details={
                "zone_id": zone_id,
                "node_uid": uid,
                "offline_required_nodes": [dict(node)],
                **dict(diagnostics),
            },
        )
    return None


def extract_irrig_node_uid_from_actuators(actuators: Any) -> str | None:
    for actuator in actuators or ():
        node_type = str(getattr(actuator, "node_type", "") or "").strip().lower()
        if node_type != "irrig":
            continue
        uid = str(getattr(actuator, "node_uid", "") or "").strip()
        if uid:
            return uid
    return None


async def offline_failure_for_node_liveness(
    *,
    zone_id: int,
    node_uid: str,
    runtime_monitor: Any,
    heartbeat_age_limit_sec: float = 30.0,
) -> OfflineFailure | None:
    read_node_liveness = getattr(runtime_monitor, "read_node_liveness", None)
    if not callable(read_node_liveness):
        return None
    uid = str(node_uid or "").strip()
    if not uid:
        return None
    liveness = await read_node_liveness(node_uid=uid)
    if not isinstance(liveness, Mapping) or not liveness_is_unreachable(
        liveness,
        heartbeat_age_limit_sec=heartbeat_age_limit_sec,
    ):
        return None
    return offline_failure_from_liveness(zone_id=zone_id, node_uid=uid, liveness=liveness)


def offline_failure_for_command_transport(
    *,
    zone_id: int,
    node_uid: str,
    error_code: str,
    diagnostics: Mapping[str, Any],
) -> OfflineFailure | None:
    """Fail-closed, когда transport-команда к ноде не проходит (в т.ч. stale-online)."""
    uid = str(node_uid or "").strip()
    if not uid:
        return None
    normalized = str(error_code or "").strip().lower()
    if normalized not in {str(code).strip().lower() for code in IRR_COMMAND_TRANSPORT_CODES}:
        return None

    node_type = "irrig"
    node_status = "unknown"
    last_seen_age_sec: int | None = None
    zone_nodes = diagnostics.get("zone_nodes")
    if isinstance(zone_nodes, list):
        for node in zone_nodes:
            if not isinstance(node, Mapping):
                continue
            if str(node.get("uid") or "").strip() != uid:
                continue
            node_type = str(node.get("type") or node_type).strip().lower() or node_type
            node_status = str(node.get("status") or node_status).strip().lower() or node_status
            try:
                last_seen_age_sec = (
                    int(node.get("last_seen_age_sec"))
                    if node.get("last_seen_age_sec") is not None
                    else None
                )
            except (TypeError, ValueError):
                last_seen_age_sec = None
            break

    # Transport/probe races with a freshly-online node are usually stage timing
    # (short fill timeout, concurrent cleanup, delayed irr snapshot), not true offline.
    # Keep the original error so probe-backoff / stage handlers can retry.
    _fresh_online_skip_codes = frozenset({
        "ae3_command_poll_deadline_exceeded",
        "irr_state_unavailable",
        "irr_state_stale",
    })
    if (
        normalized in _fresh_online_skip_codes
        and node_status == "online"
        and (last_seen_age_sec is None or last_seen_age_sec < 60)
    ):
        return None

    offline_node = {
        "uid": uid,
        "type": node_type,
        "status": node_status,
        "last_seen_age_sec": last_seen_age_sec,
    }
    return OfflineFailure(
        code=ErrorCodes.AE3_REQUIRED_NODE_OFFLINE,
        message=(
            f"Узел {uid} ({node_type}) не отвечает на команды — возможна потеря связи. "
            "Проверьте питание, Wi‑Fi и MQTT."
        ),
        details={
            "zone_id": zone_id,
            "node_uid": uid,
            "node_status": node_status,
            "transport_error_code": normalized,
            "offline_required_nodes": [offline_node],
            **dict(diagnostics),
        },
    )


async def resolve_task_error_with_node_offline(
    *,
    zone_id: int,
    topology: str,
    error_code: str,
    error_message: str,
    node_uid: str | None = None,
    runtime_monitor: Any | None = None,
    diagnostics: Mapping[str, Any] | None = None,
    task_type: str | None = None,
    current_stage: str | None = None,
) -> OfflineFailure | None:
    """Если transport-ошибка вызвана offline-нодой — вернуть понятный OfflineFailure."""
    if not should_remap_error_for_node_check(error_code):
        return None

    if runtime_monitor is not None and node_uid:
        node_failure = await offline_failure_for_node_liveness(
            zone_id=zone_id,
            node_uid=node_uid,
            runtime_monitor=runtime_monitor,
        )
        if node_failure is not None:
            return node_failure

    diag = diagnostics
    if diag is None:
        try:
            diag = await fetch_zone_nodes_diagnostics(zone_id=zone_id)
        except Exception:
            return None

    if node_uid:
        node_failure = offline_failure_for_node_uid(
            zone_id=zone_id,
            node_uid=node_uid,
            diagnostics=diag,
        )
        if node_failure is not None:
            return node_failure

        transport_failure = offline_failure_for_command_transport(
            zone_id=zone_id,
            node_uid=node_uid,
            error_code=error_code,
            diagnostics=diag,
        )
        if transport_failure is not None:
            return transport_failure

    required_failure = resolve_required_nodes_offline_failure(
        zone_id=zone_id,
        topology=topology,
        diagnostics=diag,
        persistent_only=False,
        task_type=task_type,
        current_stage=current_stage,
    )
    if required_failure is not None:
        return required_failure

    return None


def offline_failure_from_liveness(
    *,
    zone_id: int,
    node_uid: str,
    liveness: Mapping[str, Any],
) -> OfflineFailure:
    status = str(liveness.get("status") or "offline").strip().lower() or "offline"
    heartbeat_age = liveness.get("heartbeat_age_sec")
    last_seen_age = liveness.get("last_seen_age_sec")
    age = last_seen_age if last_seen_age is not None else heartbeat_age
    node = {
        "uid": node_uid,
        "type": str(liveness.get("node_type") or "irrig").strip().lower() or "irrig",
        "status": status,
        "last_seen_age_sec": age,
    }
    persistent_threshold = node_persistent_dead_sec()
    code = ErrorCodes.AE3_REQUIRED_NODE_OFFLINE
    if age is not None and int(age) >= persistent_threshold:
        code = ErrorCodes.AE3_SNAPSHOT_REQUIRED_NODE_PERSISTENTLY_OFFLINE
    message = _format_offline_nodes_message(offline_nodes=[node])
    return OfflineFailure(
        code=code,
        message=message,
        details={
            "zone_id": zone_id,
            "node_uid": node_uid,
            "node_status": status,
            "heartbeat_age_sec": heartbeat_age,
            "last_seen_age_sec": last_seen_age,
            "offline_required_nodes": [node],
        },
    )
