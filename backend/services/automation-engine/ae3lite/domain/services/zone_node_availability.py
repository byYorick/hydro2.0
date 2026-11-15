"""Диагностика доступности нод зоны для fail-closed AE3."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.domain.errors import ErrorCodes, SnapshotBuildError

TWO_TANK_REQUIRED_NODE_TYPES = TopologyRegistry().pack("two_tank").required_node_types
TWO_TANK_TOPOLOGIES = frozenset(
    pack_id for pack_id in TopologyRegistry().ids() if TopologyRegistry().pack(pack_id).plan_profile == "two_tank"
)
IRRIGATION_TASK_TYPES = frozenset({"irrigation_start"})
CORRECTION_STAGE_PREFIXES = ("ph_", "ec_", "correction_", "prepare_recirc", "await_ready")

# Коды, при которых перед fail-closed проверяем, не offline ли целевая/обязательная нода.
NODE_TRANSPORT_ERROR_CODES = frozenset(
    {
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
    }
)

IRR_COMMAND_TRANSPORT_CODES = frozenset(
    {
        ErrorCodes.IRR_STATE_UNAVAILABLE,
        "irr_state_unavailable",
        ErrorCodes.IRR_STATE_STALE,
        "irr_state_stale",
        ErrorCodes.COMMAND_SEND_FAILED,
        "command_send_failed",
        "command_timeout",
        ErrorCodes.AE3_COMMAND_POLL_DEADLINE_EXCEEDED,
        "ae3_command_poll_deadline_exceeded",
    }
)

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


from ae3lite.domain.services.node_availability_records import OfflineFailure
from ae3lite.domain.services.node_availability_diagnostics import (
    NodeAvailabilityDiagnostics,
    NodeAvailabilityDiagnosticsPorts,
)


def _node_availability_diagnostics() -> NodeAvailabilityDiagnostics:
    return NodeAvailabilityDiagnostics(
        NodeAvailabilityDiagnosticsPorts(
            zone_nodes_diag_sql=lambda: ZONE_NODES_DIAG_SQL,
            classify_zone_nodes=lambda *args, **kwargs: classify_zone_nodes(*args, **kwargs),
            node_persistent_dead_sec=lambda *args, **kwargs: node_persistent_dead_sec(*args, **kwargs),
        )
    )


from ae3lite.domain.services.node_availability_admission import (
    NodeAvailabilityAdmission,
    NodeAvailabilityAdmissionPorts,
)


def _node_availability_admission() -> NodeAvailabilityAdmission:
    return NodeAvailabilityAdmission(
        NodeAvailabilityAdmissionPorts(
            correction_stage_prefixes=lambda: CORRECTION_STAGE_PREFIXES,
            irrigation_task_types=lambda: IRRIGATION_TASK_TYPES,
            format_offline_nodes_message=lambda *args, **kwargs: _format_offline_nodes_message(*args, **kwargs),
            offline_nodes_for_required_types=lambda *args, **kwargs: _offline_nodes_for_required_types(*args, **kwargs),
            required_node_types_for_task=lambda *args, **kwargs: required_node_types_for_task(*args, **kwargs),
            resolve_required_nodes_offline_failure=lambda *args, **kwargs: resolve_required_nodes_offline_failure(
                *args, **kwargs
            ),
        )
    )


from ae3lite.domain.services.node_availability_liveness import NodeAvailabilityLiveness, NodeAvailabilityLivenessPorts


def _node_availability_liveness() -> NodeAvailabilityLiveness:
    return NodeAvailabilityLiveness(
        NodeAvailabilityLivenessPorts(
            format_offline_nodes_message=lambda *args, **kwargs: _format_offline_nodes_message(*args, **kwargs),
            liveness_is_unreachable=lambda *args, **kwargs: liveness_is_unreachable(*args, **kwargs),
            node_persistent_dead_sec=lambda *args, **kwargs: node_persistent_dead_sec(*args, **kwargs),
            offline_failure_from_liveness=lambda *args, **kwargs: offline_failure_from_liveness(*args, **kwargs),
        )
    )


from ae3lite.domain.services.node_availability_command_transport import (
    NodeAvailabilityCommandTransport,
    NodeAvailabilityCommandTransportPorts,
)


def _node_availability_command_transport() -> NodeAvailabilityCommandTransport:
    return NodeAvailabilityCommandTransport(
        NodeAvailabilityCommandTransportPorts(
            irr_command_transport_codes=lambda: IRR_COMMAND_TRANSPORT_CODES,
            node_transport_error_codes=lambda: NODE_TRANSPORT_ERROR_CODES,
        )
    )


from ae3lite.domain.services.node_availability_error_resolution import (
    NodeAvailabilityErrorResolution,
    NodeAvailabilityErrorResolutionPorts,
)


def _node_availability_error_resolution() -> NodeAvailabilityErrorResolution:
    return NodeAvailabilityErrorResolution(
        NodeAvailabilityErrorResolutionPorts(
            fetch_zone_nodes_diagnostics=lambda *args, **kwargs: fetch_zone_nodes_diagnostics(*args, **kwargs),
            offline_failure_for_command_transport=lambda *args, **kwargs: offline_failure_for_command_transport(
                *args, **kwargs
            ),
            offline_failure_for_node_liveness=lambda *args, **kwargs: offline_failure_for_node_liveness(
                *args, **kwargs
            ),
            offline_failure_for_node_uid=lambda *args, **kwargs: offline_failure_for_node_uid(*args, **kwargs),
            resolve_required_nodes_offline_failure=lambda *args, **kwargs: resolve_required_nodes_offline_failure(
                *args, **kwargs
            ),
            should_remap_error_for_node_check=lambda *args, **kwargs: should_remap_error_for_node_check(
                *args, **kwargs
            ),
        )
    )


def node_persistent_dead_sec() -> int:
    return _node_availability_diagnostics().node_persistent_dead_sec()


def classify_zone_nodes(
    *,
    zone_id: int,
    diag_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return _node_availability_diagnostics().classify_zone_nodes(zone_id=zone_id, diag_rows=diag_rows)


async def fetch_zone_nodes_diagnostics(
    *,
    zone_id: int,
    conn: Any | None = None,
) -> dict[str, Any]:
    return await _node_availability_diagnostics().fetch_zone_nodes_diagnostics(zone_id=zone_id, conn=conn)


def _format_offline_nodes_message(*, offline_nodes: Sequence[Mapping[str, Any]]) -> str:
    return _node_availability_admission().format_offline_nodes_message(offline_nodes=offline_nodes)


def _offline_nodes_for_required_types(
    *,
    diagnostics: Mapping[str, Any],
    required_types: frozenset[str],
    persistent_only: bool,
) -> list[dict[str, Any]]:
    return _node_availability_admission().offline_nodes_for_required_types(
        diagnostics=diagnostics, required_types=required_types, persistent_only=persistent_only
    )


def required_node_types_for_task(
    *,
    topology: str,
    task_type: str | None = None,
    current_stage: str | None = None,
) -> frozenset[str]:
    return _node_availability_admission().required_node_types_for_task(
        topology=topology, task_type=task_type, current_stage=current_stage
    )


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
    return _node_availability_admission().resolve_required_nodes_offline_failure(
        zone_id=zone_id,
        topology=topology,
        diagnostics=diagnostics,
        persistent_only=persistent_only,
        task_type=task_type,
        current_stage=current_stage,
        required_types=required_types,
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
    return _node_availability_admission().assert_required_nodes_available(
        zone_id=zone_id,
        topology=topology,
        diagnostics=diagnostics,
        persistent_only=persistent_only,
        task_type=task_type,
        current_stage=current_stage,
    )


def liveness_is_unreachable(
    liveness: Mapping[str, Any] | None,
    *,
    heartbeat_age_limit_sec: float = 30.0,
) -> bool:
    return _node_availability_liveness().liveness_is_unreachable(
        liveness=liveness, heartbeat_age_limit_sec=heartbeat_age_limit_sec
    )


def should_remap_error_for_node_check(error_code: str) -> bool:
    return _node_availability_command_transport().should_remap_error_for_node_check(error_code=error_code)


def offline_failure_for_node_uid(
    *,
    zone_id: int,
    node_uid: str,
    diagnostics: Mapping[str, Any],
) -> OfflineFailure | None:
    return _node_availability_liveness().offline_failure_for_node_uid(
        zone_id=zone_id, node_uid=node_uid, diagnostics=diagnostics
    )


def extract_irrig_node_uid_from_actuators(actuators: Any) -> str | None:
    return _node_availability_command_transport().extract_irrig_node_uid_from_actuators(actuators=actuators)


async def offline_failure_for_node_liveness(
    *,
    zone_id: int,
    node_uid: str,
    runtime_monitor: Any,
    heartbeat_age_limit_sec: float = 30.0,
) -> OfflineFailure | None:
    return await _node_availability_liveness().offline_failure_for_node_liveness(
        zone_id=zone_id,
        node_uid=node_uid,
        runtime_monitor=runtime_monitor,
        heartbeat_age_limit_sec=heartbeat_age_limit_sec,
    )


def offline_failure_for_command_transport(
    *,
    zone_id: int,
    node_uid: str,
    error_code: str,
    diagnostics: Mapping[str, Any],
) -> OfflineFailure | None:
    return _node_availability_command_transport().offline_failure_for_command_transport(
        zone_id=zone_id, node_uid=node_uid, error_code=error_code, diagnostics=diagnostics
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
    return await _node_availability_error_resolution().resolve_task_error_with_node_offline(
        zone_id=zone_id,
        topology=topology,
        error_code=error_code,
        error_message=error_message,
        node_uid=node_uid,
        runtime_monitor=runtime_monitor,
        diagnostics=diagnostics,
        task_type=task_type,
        current_stage=current_stage,
    )


def offline_failure_from_liveness(
    *,
    zone_id: int,
    node_uid: str,
    liveness: Mapping[str, Any],
) -> OfflineFailure:
    return _node_availability_liveness().offline_failure_from_liveness(
        zone_id=zone_id, node_uid=node_uid, liveness=liveness
    )
