"""ExecuteTaskUseCase readiness: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.application.services.task_execution_shared import logger


@dataclass(frozen=True)
class TaskExecutionReadinessPorts:
    latest_chemistry_diagnostics: Callable[..., Awaitable[Any]]
    global_create_zone_event: Callable[..., Any]
    global_send_service_log: Callable[..., Any]


class TaskExecutionReadiness:
    def __init__(self, ports: TaskExecutionReadinessPorts) -> None:
        self._ports = ports

    async def emit_start_readiness_confirmed(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
    ) -> None:
        details = self.build_start_readiness_details(task=task, snapshot=snapshot, plan=plan)
        try:
            await self._ports.global_create_zone_event(
                int(getattr(task, "zone_id", 0) or 0),
                "AE_TASK_STARTED",
                with_runtime_event_contract(details),
            )
        except Exception:
            logger.warning(
                "AE3 не смог записать readiness event AE_TASK_STARTED zone_id=%s task_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                exc_info=True,
            )
        self._ports.global_send_service_log(
            service="automation-engine",
            level="info",
            message="AE3 подтвердил готовность к старту задачи",
            context=details,
        )

    def emit_start_readiness_failed(
        self,
        *,
        task: Any,
        snapshot: Any,
        error_code: str,
        error: Exception,
    ) -> None:
        details = self.build_start_failure_details(
            task=task,
            snapshot=snapshot,
            error_code=error_code,
            error=error,
        )
        self._ports.global_send_service_log(
            service="automation-engine",
            level="error",
            message="AE3 не подтвердил готовность к старту задачи",
            context=details,
        )

    def build_start_readiness_details(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
    ) -> dict[str, Any]:
        correction_config = getattr(snapshot, "correction_config", None)
        correction_meta = correction_config.get("meta") if isinstance(correction_config, Mapping) else None
        command_plans = getattr(snapshot, "command_plans", None)
        phase_targets = getattr(snapshot, "phase_targets", None)
        details: dict[str, Any] = {
            "task_id": int(getattr(task, "id", 0) or 0),
            "zone_id": int(getattr(task, "zone_id", 0) or 0),
            "topology": str(getattr(plan, "topology", "") or getattr(task, "topology", "") or ""),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task, "workflow_phase", "") or ""),
            "intent_trigger": str(getattr(task, "intent_trigger", "") or "") or None,
            "automation_runtime": str(getattr(snapshot, "automation_runtime", "") or ""),
            "bundle_revision": str(getattr(snapshot, "bundle_revision", "") or "") or None,
            "grow_cycle_id": int(getattr(snapshot, "grow_cycle_id", 0) or 0) or None,
            "current_phase_id": int(getattr(snapshot, "current_phase_id", 0) or 0) or None,
            "phase_name": str(getattr(snapshot, "phase_name", "") or "") or None,
            "actuator_count": len(getattr(snapshot, "actuators", ()) or ()),
            "pid_config_count": len(getattr(snapshot, "pid_configs", {}) or {}),
            "process_calibration_count": len(getattr(snapshot, "process_calibrations", {}) or {}),
            "command_plan_schema_version": (
                str(command_plans.get("schema_version") or "").strip() if isinstance(command_plans, Mapping) else None
            ),
            "plan_steps_count": len(getattr(plan, "steps", ()) or ()),
            "target_ph": self.extract_phase_target(phase_targets=phase_targets, key="ph"),
            "target_ec": self.extract_phase_target(phase_targets=phase_targets, key="ec"),
            "correction_config_version": (
                int(correction_meta.get("version", 0) or 0) or None if isinstance(correction_meta, Mapping) else None
            ),
            "irrigation_decision_strategy": str(getattr(task, "irrigation_decision_strategy", "") or "") or None,
            "irrigation_bundle_revision": str(getattr(task, "irrigation_bundle_revision", "") or "") or None,
        }
        return {key: value for key, value in details.items() if value is not None}

    def build_start_failure_details(
        self,
        *,
        task: Any,
        snapshot: Any,
        error_code: str,
        error: Exception,
    ) -> dict[str, Any]:
        details: dict[str, Any] = {
            "task_id": int(getattr(task, "id", 0) or 0),
            "zone_id": int(getattr(task, "zone_id", 0) or 0),
            "topology": str(getattr(task, "topology", "") or ""),
            "stage": str(getattr(task, "current_stage", "") or ""),
            "workflow_phase": str(getattr(task, "workflow_phase", "") or ""),
            "intent_trigger": str(getattr(task, "intent_trigger", "") or "") or None,
            "error_code": str(error_code or "ae3_task_execution_failed"),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "snapshot_loaded": snapshot is not None,
        }
        if snapshot is not None:
            details.update(
                {
                    "automation_runtime": str(getattr(snapshot, "automation_runtime", "") or "") or None,
                    "grow_cycle_id": int(getattr(snapshot, "grow_cycle_id", 0) or 0) or None,
                    "current_phase_id": int(getattr(snapshot, "current_phase_id", 0) or 0) or None,
                    "phase_name": str(getattr(snapshot, "phase_name", "") or "") or None,
                }
            )
        return {key: value for key, value in details.items() if value is not None}

    def extract_phase_target(self, *, phase_targets: Any, key: str) -> float | None:
        if not isinstance(phase_targets, Mapping):
            return None
        candidate = phase_targets.get(key)
        if isinstance(candidate, Mapping):
            candidate = candidate.get("target")
        if candidate is None:
            candidate = phase_targets.get(f"{key}_target")
        try:
            return float(candidate)
        except (TypeError, ValueError):
            return None

    async def emit_task_completed_event(self, *, task: Any) -> None:
        chemistry = await self._ports.latest_chemistry_diagnostics(task=task)
        payload = {
            "task_id": task.id,
            "topology": str(getattr(task, "topology", "") or ""),
            "stage": str(getattr(task, "current_stage", "") or ""),
        }
        if isinstance(chemistry, Mapping):
            payload.update(
                {
                    "chemistry_outcome": str(chemistry.get("chemistry_outcome") or "unknown"),
                    "chemistry_diagnostics": chemistry,
                }
            )
        try:
            await self._ports.global_create_zone_event(task.zone_id, "AE_TASK_COMPLETED", payload)
        except Exception:
            logger.warning(
                "AE3 не смог записать событие AE_TASK_COMPLETED zone_id=%s task_id=%s",
                task.zone_id,
                task.id,
                exc_info=True,
            )
