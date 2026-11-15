"""node availability error resolution: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ae3lite.domain.services.node_availability_records import OfflineFailure


@dataclass(frozen=True)
class NodeAvailabilityErrorResolutionPorts:
    fetch_zone_nodes_diagnostics: Callable[..., Any]
    offline_failure_for_command_transport: Callable[..., Any]
    offline_failure_for_node_liveness: Callable[..., Any]
    offline_failure_for_node_uid: Callable[..., Any]
    resolve_required_nodes_offline_failure: Callable[..., Any]
    should_remap_error_for_node_check: Callable[..., Any]


class NodeAvailabilityErrorResolution:
    def __init__(self, ports: NodeAvailabilityErrorResolutionPorts) -> None:
        self._ports = ports

    async def resolve_task_error_with_node_offline(
        self,
        *,
        zone_id: int,
        topology: str,
        error_code: str,
        error_message: str,
        node_uid: str | None,
        runtime_monitor: Any | None,
        diagnostics: Mapping[str, Any] | None,
        task_type: str | None,
        current_stage: str | None,
    ) -> OfflineFailure | None:
        """Если transport-ошибка вызвана offline-нодой — вернуть понятный OfflineFailure."""
        if not self._ports.should_remap_error_for_node_check(error_code):
            return None

        if runtime_monitor is not None and node_uid:
            node_failure = await self._ports.offline_failure_for_node_liveness(
                zone_id=zone_id,
                node_uid=node_uid,
                runtime_monitor=runtime_monitor,
            )
            if node_failure is not None:
                return node_failure

        diag = diagnostics
        if diag is None:
            try:
                diag = await self._ports.fetch_zone_nodes_diagnostics(zone_id=zone_id)
            except Exception:
                return None

        if node_uid:
            node_failure = self._ports.offline_failure_for_node_uid(
                zone_id=zone_id,
                node_uid=node_uid,
                diagnostics=diag,
            )
            if node_failure is not None:
                return node_failure

            transport_failure = self._ports.offline_failure_for_command_transport(
                zone_id=zone_id,
                node_uid=node_uid,
                error_code=error_code,
                diagnostics=diag,
            )
            if transport_failure is not None:
                return transport_failure

        required_failure = self._ports.resolve_required_nodes_offline_failure(
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
