"""ExecuteTaskUseCase decision snapshot: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.application.services.task_execution_shared import logger
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.errors import (
    TaskExecutionError,
)


@dataclass(frozen=True)
class TaskExecutionDecisionSnapshotPorts:
    correction_authority_repository: Callable[[], Any]
    task_repository: Callable[[], Any]
    global_create_zone_event: Callable[..., Any]
    global_send_service_log: Callable[..., Any]


class TaskExecutionDecisionSnapshot:
    def __init__(self, ports: TaskExecutionDecisionSnapshotPorts) -> None:
        self._ports = ports

    async def lock_irrigation_decision_snapshot_if_needed(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        owner: str,
        now: datetime,
        emit_observability: bool = False,
    ) -> Any:
        if str(getattr(task, "task_type", "") or "").strip().lower() != "irrigation_start":
            return task

        has_persisted_snapshot = str(
            getattr(task, "irrigation_decision_strategy", "") or ""
        ).strip() != "" and isinstance(getattr(task, "irrigation_decision_config", None), Mapping)
        if has_persisted_snapshot:
            # Emit only when the task is still in its initial irrigation_start stage —
            # i.e., snapshot was set at task-creation time and this is the very first
            # claim, before any transition to irrigation_check or subsequent poll
            # re-enqueues.  After each poll, update_stage() resets status to 'pending'
            # and then the task is re-claimed (status='claimed'), making first_run=True
            # on every cycle.  Guarding by current_stage prevents duplicate events on
            # every subsequent re-claim in irrigation_check.
            is_initial_stage = str(getattr(task, "current_stage", "") or "").strip().lower() == "irrigation_start"
            if emit_observability and is_initial_stage:
                await self.emit_irrigation_decision_snapshot_locked(
                    task=task,
                    snapshot=snapshot,
                    strategy=str(getattr(task, "irrigation_decision_strategy", "") or "").strip().lower() or None,
                    bundle_revision=str(getattr(task, "irrigation_bundle_revision", "") or "").strip() or None,
                    config_mapping=dict(getattr(task, "irrigation_decision_config", {}) or {}),
                )
            return task

        runtime = plan.runtime if isinstance(getattr(plan, "runtime", None), RuntimePlan) else None
        decision = runtime.irrigation_decision if runtime is not None else None
        strategy = str(getattr(decision, "strategy", "") or "").strip().lower()
        config = getattr(decision, "config", None)
        config_mapping = config.model_dump(mode="python") if config is not None else {}
        bundle_revision = str(getattr(snapshot, "bundle_revision", "") or "").strip() or None

        if strategy == "" and config_mapping == {} and bundle_revision is None:
            return task

        updated = await self._ports.task_repository().update_irrigation_runtime(
            task_id=int(getattr(task, "id", 0) or 0),
            owner=owner,
            now=now,
            irrigation_decision_strategy=strategy or None,
            irrigation_decision_config=config_mapping or None,
            irrigation_bundle_revision=bundle_revision,
            claim_generation=int(getattr(task, "claim_generation", 0) or 0),
        )
        if updated is None:
            raise TaskExecutionError(
                "irrigation_decision_snapshot_persist_failed",
                f"Не удалось сохранить snapshot решения по поливу для задачи {getattr(task, 'id', None)}",
            )

        await self.emit_irrigation_decision_snapshot_locked(
            task=updated,
            snapshot=snapshot,
            strategy=strategy or None,
            bundle_revision=bundle_revision,
            config_mapping=config_mapping,
        )
        return updated

    async def emit_irrigation_decision_snapshot_locked(
        self,
        *,
        task: Any,
        snapshot: Any,
        strategy: str | None,
        bundle_revision: str | None,
        config_mapping: Mapping[str, Any] | None,
    ) -> None:
        details = {
            "task_id": int(getattr(task, "id", 0) or 0),
            "zone_id": int(getattr(task, "zone_id", 0) or 0),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "current_stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task, "workflow_phase", "") or ""),
            "strategy": strategy,
            "bundle_revision": bundle_revision,
            "config": dict(config_mapping) if isinstance(config_mapping, Mapping) and dict(config_mapping) else None,
            "grow_cycle_id": int(getattr(snapshot, "grow_cycle_id", 0) or 0) or None,
            "phase_name": str(getattr(snapshot, "phase_name", "") or "") or None,
        }
        details = {key: value for key, value in details.items() if value is not None}

        try:
            await self._ports.global_create_zone_event(
                int(getattr(task, "zone_id", 0) or 0),
                "IRRIGATION_DECISION_SNAPSHOT_LOCKED",
                with_runtime_event_contract(details),
            )
        except Exception:
            logger.warning(
                "AE3 не смог записать IRRIGATION_DECISION_SNAPSHOT_LOCKED zone_id=%s task_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                exc_info=True,
            )

        self._ports.global_send_service_log(
            service="automation-engine",
            level="info",
            message="AE3 зафиксировал snapshot decision-controller полива",
            context=details,
        )

    async def mark_correction_config_applied_if_needed(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        repository = self._ports.correction_authority_repository()
        if repository is None:
            return

        topology = str(getattr(plan, "topology", "") or getattr(task, "topology", "")).strip().lower()
        pack = TopologyRegistry().try_pack(topology)
        if pack is None or not pack.tracks_correction_authority:
            return

        correction_config = getattr(snapshot, "correction_config", None)
        if not isinstance(correction_config, dict):
            return
        meta = correction_config.get("meta")
        if not isinstance(meta, dict):
            return
        version = meta.get("version")
        try:
            version_int = int(version)
        except (TypeError, ValueError):
            return
        if version_int <= 0:
            return
        await repository.mark_applied(zone_id=int(snapshot.zone_id), version=version_int, now=now)
