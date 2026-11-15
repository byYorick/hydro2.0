"""ExecuteTaskUseCase preflight: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ae3lite.application.services.task_execution_shared import logger
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.domain.errors import (
    ErrorCodes,
    SnapshotBuildError,
)


@dataclass(frozen=True)
class TaskExecutionPreflightPorts:
    workflow_router: Callable[[], Any]


class TaskExecutionPreflight:
    def __init__(self, ports: TaskExecutionPreflightPorts) -> None:
        self._ports = ports

    async def preflight_required_nodes_online(self, *, task: Any) -> None:
        from ae3lite.domain.services.zone_node_availability import (
            assert_required_nodes_available,
            fetch_zone_nodes_diagnostics,
        )

        zone_id = int(getattr(task, "zone_id", 0) or 0)
        if zone_id <= 0:
            return
        topology = str(getattr(task, "topology", "") or "")
        diagnostics = await fetch_zone_nodes_diagnostics(zone_id=zone_id)
        assert_required_nodes_available(
            zone_id=zone_id,
            topology=topology,
            diagnostics=diagnostics,
            persistent_only=False,
            task_type=str(getattr(task, "task_type", "") or "") or None,
            current_stage=str(getattr(task, "current_stage", "") or "") or None,
        )

    def extract_irrig_node_uid(self, snapshot: Any) -> str | None:
        from ae3lite.domain.services.zone_node_availability import extract_irrig_node_uid_from_actuators

        if snapshot is None:
            return None
        return extract_irrig_node_uid_from_actuators(getattr(snapshot, "actuators", ()) or ())

    async def resolve_offline_failure_instead_of_guard(
        self,
        *,
        task: Any,
        original_error_code: str,
        original_error_message: str = "",
        node_uid: str | None = None,
    ) -> Any | None:
        """Если transport-ошибка вызвана offline-нодой — вернуть понятный код вместо lease/timeout/send."""
        from ae3lite.domain.services.zone_node_availability import (
            resolve_task_error_with_node_offline,
        )

        zone_id = int(getattr(task, "zone_id", 0) or 0)
        if zone_id <= 0:
            return None
        try:
            return await resolve_task_error_with_node_offline(
                zone_id=zone_id,
                topology=str(getattr(task, "topology", "") or ""),
                error_code=original_error_code,
                error_message=original_error_message,
                node_uid=node_uid,
                runtime_monitor=getattr(self._ports.workflow_router(), "_runtime_monitor", None),
                task_type=str(getattr(task, "task_type", "") or "") or None,
                current_stage=str(getattr(task, "current_stage", "") or "") or None,
            )
        except Exception:
            logger.warning(
                "AE3 не смог проверить доступность нод при remap zone_id=%s task_id=%s",
                zone_id,
                int(getattr(task, "id", 0) or 0),
                exc_info=True,
            )
            return None

    def verify_topology_required_node_types(self, *, task: Any, snapshot: Any) -> None:
        """Проверяет наличие actuator-нод обязательных типов для текущей топологии.

        Для two-tank-топологий обязательны ``irrig`` (клапаны/насос полива),
        ``ph`` и ``ec`` (дозирующие насосы коррекции). Если хотя бы один
        ``node_type`` не представлен ни одним actuator'ом — fail-closed
        с конкретным кодом ``ae3_snapshot_required_node_type_missing``,
        чтобы оператор не получал общую ошибку «no online actuator channels».
        """
        topology = str(getattr(task, "topology", "") or "").strip().lower()
        pack = TopologyRegistry().try_pack(topology)
        if pack is None or pack.execution_mode != "workflow" or not pack.required_node_types:
            return
        actuators = getattr(snapshot, "actuators", ()) or ()
        present_types = {str(getattr(actuator, "node_type", "") or "").strip().lower() for actuator in actuators}
        present_types.discard("")
        missing = sorted(pack.required_node_types - present_types)
        if not missing:
            return
        zone_id = int(getattr(snapshot, "zone_id", 0) or 0) or int(getattr(task, "zone_id", 0) or 0)
        raise SnapshotBuildError(
            f"У зоны {zone_id} нет actuator-нод требуемых типов: {missing}",
            code=ErrorCodes.AE3_SNAPSHOT_REQUIRED_NODE_TYPE_MISSING,
            details={
                "zone_id": zone_id,
                "topology": topology,
                "missing_node_types": missing,
                "present_node_types": sorted(present_types),
                "required_node_types": sorted(pack.required_node_types),
            },
        )
