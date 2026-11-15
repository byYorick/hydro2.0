"""CreateTaskFromIntentUseCase solution change: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ae3lite.domain.errors import TaskCreateError


@dataclass(frozen=True)
class IntentTaskSolutionChangePorts:
    pass


class IntentTaskSolutionChange:
    def __init__(self, ports: IntentTaskSolutionChangePorts) -> None:
        self._ports = ports

    async def ensure_solution_change_preconditions(
        self,
        *,
        zone_id: int,
        meta: Any,
        conn: Any,
    ) -> None:
        if str(getattr(meta, "task_type", "") or "").strip().lower() != "solution_change":
            return

        topology = str(getattr(meta, "topology", "") or "").strip().lower()
        from ae3lite.application.services.workflow_topology import TopologyRegistry

        change_pack = TopologyRegistry().try_pack(topology)
        if change_pack is None or "await_operator_drain_confirm" not in change_pack.stages:
            raise TaskCreateError(
                "solution_change_topology_unsupported",
                f"Подмена раствора не описана в пакете topology, получено: {topology or 'empty'}",
                details={"topology": topology or "empty"},
            )

        workflow_row = await conn.fetchrow(
            """
            SELECT workflow_phase
            FROM zone_workflow_state
            WHERE zone_id = $1
            LIMIT 1
            """,
            zone_id,
        )
        workflow_phase = str((workflow_row or {}).get("workflow_phase") or "").strip().lower()
        if workflow_phase != "ready":
            raise TaskCreateError(
                "solution_change_zone_not_ready",
                f"Подмена раствора доступна только в ready, текущая фаза: {workflow_phase or 'missing'}",
                details={"workflow_phase": workflow_phase or "missing"},
            )

        active_irrigation_row = await conn.fetchrow(
            """
            SELECT id, status
            FROM ae_tasks
            WHERE zone_id = $1
              AND task_type = 'irrigation_start'
              AND status IN ('pending', 'claimed', 'running', 'waiting_command')
            ORDER BY id DESC
            LIMIT 1
            """,
            zone_id,
        )
        if active_irrigation_row is not None:
            raise TaskCreateError(
                "solution_change_active_irrigation",
                "Подмена раствора запрещена во время активного полива",
                details={
                    "active_irrigation_task_id": int(active_irrigation_row.get("id") or 0) or None,
                    "active_irrigation_task_status": str(active_irrigation_row.get("status") or "").strip().lower()
                    or None,
                },
            )

        enabled = await self.resolve_solution_change_enabled_from_bundle(zone_id=zone_id, conn=conn)
        if not enabled:
            raise TaskCreateError(
                "solution_change_disabled",
                "Подсистема solution_change отключена в effective targets",
                details={"zone_id": zone_id},
            )

        # Current storage_irrigation_node firmware map has no valve_drain GPIO.
        # Fail-closed until irrig node exposes the channel (test_node / future HW).
        has_drain_channel = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM nodes n
                JOIN node_channels nc ON nc.node_id = n.id
                WHERE n.zone_id = $1
                  AND LOWER(COALESCE(n.type, '')) = 'irrig'
                  AND LOWER(COALESCE(nc.channel, '')) = 'valve_drain'
                  AND UPPER(COALESCE(nc.type, '')) IN ('ACTUATOR', 'SERVICE')
                  AND COALESCE(nc.is_active, TRUE) = TRUE
            )
            """,
            zone_id,
        )
        if not bool(has_drain_channel):
            raise TaskCreateError(
                "solution_change_drain_channel_missing",
                "Подмена раствора требует канал valve_drain на irrig-ноде; "
                "в текущем firmware map storage_irrigation_node канал отсутствует",
                details={
                    "zone_id": zone_id,
                    "required_channel": "valve_drain",
                    "node_type": "irrig",
                },
            )

    async def resolve_solution_change_enabled_from_bundle(self, *, zone_id: int, conn: Any) -> bool:
        row = await conn.fetchrow(
            """
            SELECT aeb.config
            FROM grow_cycles gc
            JOIN automation_effective_bundles aeb
              ON aeb.scope_type = 'grow_cycle'
             AND aeb.scope_id = gc.id
            WHERE gc.zone_id = $1
              AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
            ORDER BY
                CASE gc.status
                    WHEN 'RUNNING' THEN 0
                    WHEN 'PAUSED' THEN 1
                    ELSE 2
                END,
                gc.id DESC
            LIMIT 1
            """,
            zone_id,
        )
        config = (row or {}).get("config")
        if not isinstance(config, Mapping):
            return False
        zone_bundle = config.get("zone")
        if not isinstance(zone_bundle, Mapping):
            return False
        logic_profile = zone_bundle.get("logic_profile")
        if not isinstance(logic_profile, Mapping):
            return False
        active_profile = logic_profile.get("active_profile")
        if not isinstance(active_profile, Mapping):
            return False
        subsystems = active_profile.get("subsystems")
        if not isinstance(subsystems, Mapping):
            return False
        solution_change = subsystems.get("solution_change")
        if isinstance(solution_change, Mapping) and solution_change.get("enabled") is not None:
            return bool(solution_change.get("enabled"))
        return False
