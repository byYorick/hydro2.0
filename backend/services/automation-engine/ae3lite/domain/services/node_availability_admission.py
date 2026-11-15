"""node availability admission: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.domain.errors import ErrorCodes, SnapshotBuildError
from ae3lite.domain.services.node_availability_records import OfflineFailure


@dataclass(frozen=True)
class NodeAvailabilityAdmissionPorts:
    correction_stage_prefixes: Callable[..., Any]
    irrigation_task_types: Callable[..., Any]
    format_offline_nodes_message: Callable[..., Any]
    offline_nodes_for_required_types: Callable[..., Any]
    required_node_types_for_task: Callable[..., Any]
    resolve_required_nodes_offline_failure: Callable[..., Any]


class NodeAvailabilityAdmission:
    def __init__(self, ports: NodeAvailabilityAdmissionPorts) -> None:
        self._ports = ports

    def format_offline_nodes_message(self, *, offline_nodes: Sequence[Mapping[str, Any]]) -> str:
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

    def offline_nodes_for_required_types(
        self, *, diagnostics: Mapping[str, Any], required_types: frozenset[str], persistent_only: bool
    ) -> list[dict[str, Any]]:
        zone_nodes = diagnostics.get("zone_nodes")
        if not isinstance(zone_nodes, list):
            return []

        persistent_uids = {
            str(uid).strip() for uid in (diagnostics.get("persistently_offline_uids") or []) if str(uid).strip()
        }
        transient_uids = {
            str(uid).strip() for uid in (diagnostics.get("transiently_offline_uids") or []) if str(uid).strip()
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
        self, *, topology: str, task_type: str | None, current_stage: str | None
    ) -> frozenset[str]:
        """Stage-scoped preflight: полив требует только irrig, коррекция — ph/ec."""
        normalized_topology = str(topology or "").strip().lower()
        normalized_task_type = str(task_type or "").strip().lower()
        normalized_stage = str(current_stage or "").strip().lower()
        pack = TopologyRegistry().try_pack(normalized_topology)
        required = pack.required_node_types if pack is not None else frozenset({"irrig"})

        if normalized_task_type in self._ports.irrigation_task_types() and "irrig" in required:
            return frozenset({"irrig"})

        if normalized_stage.startswith(self._ports.correction_stage_prefixes()):
            chemical = required & frozenset({"ph", "ec"})
            return chemical

        return required

    def resolve_required_nodes_offline_failure(
        self,
        *,
        zone_id: int,
        topology: str,
        diagnostics: Mapping[str, Any],
        persistent_only: bool,
        task_type: str | None,
        current_stage: str | None,
        required_types: frozenset[str] | None,
    ) -> OfflineFailure | None:
        """Возвращает fail-closed ошибку, если обязательные для топологии ноды offline."""
        normalized_topology = str(topology or "").strip().lower()
        if required_types is None:
            required_types = self._ports.required_node_types_for_task(
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

        offline_nodes = self._ports.offline_nodes_for_required_types(
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

        persistent_uids = [
            str(n.get("uid") or "")
            for n in offline_nodes
            if str(n.get("uid") or "") in set(diagnostics.get("persistently_offline_uids") or [])
        ]
        if persistent_uids and (persistent_only or len(persistent_uids) == len(offline_nodes)):
            return OfflineFailure(
                code=ErrorCodes.AE3_SNAPSHOT_REQUIRED_NODE_PERSISTENTLY_OFFLINE,
                message=self._ports.format_offline_nodes_message(offline_nodes=offline_nodes),
                details=details,
            )

        return OfflineFailure(
            code=ErrorCodes.AE3_REQUIRED_NODE_OFFLINE,
            message=self._ports.format_offline_nodes_message(offline_nodes=offline_nodes),
            details=details,
        )

    def assert_required_nodes_available(
        self,
        *,
        zone_id: int,
        topology: str,
        diagnostics: Mapping[str, Any],
        persistent_only: bool,
        task_type: str | None,
        current_stage: str | None,
    ) -> None:
        failure = self._ports.resolve_required_nodes_offline_failure(
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
