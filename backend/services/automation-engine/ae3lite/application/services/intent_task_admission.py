"""CreateTaskFromIntentUseCase admission: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ae3lite.domain.errors import ErrorCodes, SnapshotBuildError, TaskCreateError


@dataclass(frozen=True)
class IntentTaskAdmissionPorts:
    hard_blocking_alert_codes: Callable[[], Any]
    zone_alert_repository: Callable[[], Any]


class IntentTaskAdmission:
    def __init__(self, ports: IntentTaskAdmissionPorts) -> None:
        self._ports = ports

    async def assert_required_nodes_available_for_task(
        self,
        *,
        zone_id: int,
        topology: str,
        conn: Any,
        task_type: str | None = None,
        current_stage: str | None = None,
    ) -> None:
        from ae3lite.domain.services.zone_node_availability import (
            assert_required_nodes_available,
            fetch_zone_nodes_diagnostics,
        )

        diagnostics = await fetch_zone_nodes_diagnostics(zone_id=zone_id, conn=conn)
        try:
            assert_required_nodes_available(
                zone_id=zone_id,
                topology=topology,
                diagnostics=diagnostics,
                persistent_only=False,
                task_type=task_type,
                current_stage=current_stage,
            )
        except SnapshotBuildError as exc:
            code = str(getattr(exc, "code", "") or ErrorCodes.AE3_REQUIRED_NODE_OFFLINE)
            details = exc.details if isinstance(getattr(exc, "details", None), dict) else {}
            raise TaskCreateError(code, str(exc), details=details) from exc

    async def find_blocking_alert(self, *, zone_id: int, conn: Any | None = None) -> dict[str, Any] | None:
        repository = self._ports.zone_alert_repository()
        if repository is None:
            return None
        finder = getattr(repository, "find_first_active_by_codes", None)
        if not callable(finder):
            return None
        if conn is not None:
            try:
                alert = await finder(zone_id=zone_id, codes=self._ports.hard_blocking_alert_codes(), conn=conn)
            except TypeError:
                alert = await finder(zone_id=zone_id, codes=self._ports.hard_blocking_alert_codes())
        else:
            alert = await finder(zone_id=zone_id, codes=self._ports.hard_blocking_alert_codes())
        return dict(alert) if isinstance(alert, Mapping) else None

    async def ensure_runtime_cycle_preconditions(
        self,
        *,
        zone_id: int,
        meta: Any,
        conn: Any,
    ) -> None:
        task_type = str(getattr(meta, "task_type", "") or "").strip().lower()
        if task_type not in {"cycle_start", "irrigation_start"}:
            return

        grow_cycle_row = await conn.fetchrow(
            """
            SELECT
                gc.id AS grow_cycle_id,
                gc.current_phase_id
            FROM grow_cycles gc
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
        if grow_cycle_row is None:
            raise TaskCreateError(
                ErrorCodes.AE3_SNAPSHOT_NO_ACTIVE_GROW_CYCLE,
                f"У зоны {zone_id} отсутствует активный grow_cycle",
                details={"zone_id": zone_id},
            )
        if grow_cycle_row.get("current_phase_id") is None:
            raise TaskCreateError(
                ErrorCodes.AE3_SNAPSHOT_MISSING_CURRENT_PHASE,
                f"У зоны {zone_id} отсутствует current_phase_id для активного grow_cycle",
                details={
                    "zone_id": zone_id,
                    "grow_cycle_id": int(grow_cycle_row.get("grow_cycle_id") or 0) or None,
                },
            )
