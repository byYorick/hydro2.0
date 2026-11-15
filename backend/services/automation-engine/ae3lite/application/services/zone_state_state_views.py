"""GetZoneAutomationStateUseCase state views: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Optional

from ae3lite.application.level_monitor import (
    coarse_clean_tank_level_percent,
    coarse_solution_tank_level_percent,
)
from ae3lite.application.services.zone_state_shared import _STAGE_LABELS, _WORKFLOW_PHASE_TO_STATE
from ae3lite.domain.services.workflow_failure_rollback import resolve_diagnostic_stage_after_rollback


@dataclass(frozen=True)
class ZoneStateStateViewsPorts:
    attach_observability: Callable[..., Awaitable[Any]]
    build_active_processes: Callable[..., Any]
    build_decision: Callable[..., Any]
    build_state_details: Callable[..., Any]
    build_timeline: Callable[..., Awaitable[Any]]
    control_mode_context: Callable[..., Awaitable[Any]]
    idle_timeline_since: Callable[..., Any]
    normalize_utc_naive: Callable[..., Any]
    primary_automation_state_label: Callable[..., Any]
    solution_tank_guard_from_payload: Callable[..., Any]
    timeline_since: Callable[..., Any]
    timeline_since_workflow: Callable[..., Any]
    workflow_failure_rollback_applied: Callable[..., Any]


class ZoneStateStateViews:
    def __init__(self, ports: ZoneStateStateViewsPorts) -> None:
        self._ports = ports

    async def build_state(
        self,
        *,
        zone_id: int,
        task: Optional[Any],
        transitions: list[dict],
        telemetry: dict[str, Any],
        telemetry_fetch_ok: bool = True,
        solution_tank_guard: dict[str, Any] | None = None,
        workflow_state: Optional[Any] = None,
        node_rows: list[dict[str, Any]] | None = None,
        observability_thresholds: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        if task is None:
            return await self.idle_state(
                zone_id=zone_id,
                telemetry=telemetry,
                telemetry_fetch_ok=telemetry_fetch_ok,
                solution_tank_guard=solution_tank_guard,
                workflow_state=workflow_state,
                node_rows=node_rows,
                observability_thresholds=observability_thresholds,
            )

        status = str(getattr(task, "status", "") or "").strip().lower()
        wf = getattr(task, "workflow", None)
        workflow_phase = str(getattr(wf, "workflow_phase", None) or "idle").strip().lower()
        current_stage = getattr(wf, "current_stage", None)
        error_code = getattr(task, "error_code", None)
        error_message = getattr(task, "error_message", None)

        is_failed = status == "failed"
        is_active = status in ("pending", "claimed", "running", "waiting_command")

        mapped_macro = _WORKFLOW_PHASE_TO_STATE.get(workflow_phase, "IDLE")
        state = "IDLE" if is_failed else mapped_macro

        timeline = await self._ports.build_timeline(
            zone_id=zone_id,
            transitions=transitions,
            since_ts=self._ports.timeline_since(task=task),
        )
        active_processes = self._ports.build_active_processes(
            workflow_phase=workflow_phase,
            is_active=is_active,
            correction=getattr(task, "correction", None),
        )
        pending_manual_step = None
        if wf is not None:
            raw_pending = getattr(wf, "pending_manual_step", None)
            if raw_pending is not None and str(raw_pending).strip() != "":
                pending_manual_step = str(raw_pending).strip()
        control_ctx = await self._ports.control_mode_context(
            zone_id=zone_id,
            current_stage=str(current_stage) if current_stage is not None else None,
            task_type=str(getattr(task, "task_type", "") or ""),
            pending_manual_step=pending_manual_step,
        )

        state_details = self._ports.build_state_details(
            is_failed=is_failed,
            error_code=error_code,
            error_message=error_message,
            stage_entered_at=getattr(wf, "stage_entered_at", None) if wf is not None else None,
            task_created_at=getattr(task, "created_at", None),
            current_stage=str(current_stage or ""),
            workflow_phase=workflow_phase,
            stage_deadline_at=getattr(wf, "stage_deadline_at", None) if wf is not None else None,
            irrigation_requested_duration_sec=getattr(task, "irrigation_requested_duration_sec", None),
            task_status=status,
            task_type=str(getattr(task, "task_type", "") or ""),
            completed_at=getattr(task, "completed_at", None),
        )

        return await self._ports.attach_observability(
            {
                "zone_id": zone_id,
                "state": state,
                "state_label": self._ports.primary_automation_state_label(
                    workflow_phase=workflow_phase,
                    mapped_macro_state=mapped_macro,
                    current_stage=str(current_stage) if current_stage is not None else "",
                    is_terminal_failed=is_failed,
                ),
                "state_details": state_details,
                "workflow_phase": workflow_phase,
                "current_stage": current_stage,
                "current_stage_label": _STAGE_LABELS.get(str(current_stage or ""), None),
                "system_config": {
                    "tanks_count": 2,
                    "system_type": "drip",
                    "clean_tank_capacity_l": None,
                    "nutrient_tank_capacity_l": None,
                },
                "current_levels": {
                    "clean_tank_level_percent": telemetry.get(
                        "clean_tank_level_percent",
                        coarse_clean_tank_level_percent(clean_max_triggered=False) or 0,
                    ),
                    "nutrient_tank_level_percent": telemetry.get(
                        "nutrient_tank_level_percent",
                        coarse_solution_tank_level_percent(
                            solution_max_triggered=False,
                            solution_min_triggered=False,
                        )
                        or 0,
                    ),
                    "buffer_tank_level_percent": None,
                    "ph": telemetry.get("ph"),
                    "ec": telemetry.get("ec"),
                },
                "active_processes": active_processes,
                "timeline": timeline,
                "next_state": None,
                "estimated_completion_sec": state_details.get("stage_deadline_remaining_sec"),
                "irr_node_state": None,
                "solution_tank_guard": solution_tank_guard,
                "decision": self._ports.build_decision(task),
                "telemetry_fetch_ok": telemetry_fetch_ok,
                **control_ctx,
            },
            zone_id=zone_id,
            task=task,
            workflow_state=workflow_state,
            telemetry=telemetry,
            telemetry_fetch_ok=telemetry_fetch_ok,
            node_rows=node_rows,
            observability_thresholds=observability_thresholds,
        )

    async def build_workflow_state(
        self,
        *,
        zone_id: int,
        workflow_state: Any,
        telemetry: dict[str, Any],
        telemetry_fetch_ok: bool = True,
        solution_tank_guard: dict[str, Any] | None = None,
        node_rows: list[dict[str, Any]] | None = None,
        observability_thresholds: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        workflow_phase = str(getattr(workflow_state, "workflow_phase", None) or "idle").strip().lower()
        payload = getattr(workflow_state, "payload", None)
        normalized_payload = payload if isinstance(payload, Mapping) else {}
        raw_stage = str(normalized_payload.get("ae3_cycle_start_stage") or "").strip() or None
        current_stage = resolve_diagnostic_stage_after_rollback(
            workflow_phase=workflow_phase,
            payload=normalized_payload,
            raw_stage=raw_stage,
        )
        workflow_guard = self._ports.solution_tank_guard_from_payload(normalized_payload)
        if solution_tank_guard is None:
            solution_tank_guard = workflow_guard
        elif workflow_guard is not None:
            solution_tank_guard = {
                **workflow_guard,
                **{k: v for k, v in solution_tank_guard.items() if v is not None},
            }
        state = _WORKFLOW_PHASE_TO_STATE.get(workflow_phase, "IDLE")
        state_label = self._ports.primary_automation_state_label(
            workflow_phase=workflow_phase,
            mapped_macro_state=state,
            current_stage=str(current_stage or ""),
            is_terminal_failed=False,
        )
        timeline = await self._ports.build_timeline(
            zone_id=zone_id,
            transitions=[],
            since_ts=self._ports.timeline_since_workflow(workflow_state=workflow_state),
        )
        pending_manual_step = None
        raw_pending = normalized_payload.get("pending_manual_step")
        if raw_pending is not None and str(raw_pending).strip() != "":
            pending_manual_step = str(raw_pending).strip()
        else:
            wf_pending = getattr(workflow_state, "pending_manual_step", None)
            if wf_pending is not None and str(wf_pending).strip() != "":
                pending_manual_step = str(wf_pending).strip()
        control_ctx = await self._ports.control_mode_context(
            zone_id=zone_id,
            current_stage=current_stage,
            pending_manual_step=pending_manual_step,
        )

        return await self._ports.attach_observability(
            {
                "zone_id": zone_id,
                "state": state,
                "state_label": state_label,
                "state_details": self._ports.build_state_details(
                    is_failed=False,
                    stage_entered_at=getattr(workflow_state, "updated_at", None),
                    current_stage=str(current_stage or ""),
                    workflow_phase=workflow_phase,
                    workflow_started_at=getattr(workflow_state, "started_at", None),
                ),
                "workflow_phase": workflow_phase,
                "current_stage": current_stage,
                "current_stage_label": _STAGE_LABELS.get(str(current_stage or ""), None),
                "system_config": {
                    "tanks_count": 2,
                    "system_type": "drip",
                    "clean_tank_capacity_l": None,
                    "nutrient_tank_capacity_l": None,
                },
                "current_levels": {
                    "clean_tank_level_percent": telemetry.get(
                        "clean_tank_level_percent",
                        coarse_clean_tank_level_percent(clean_max_triggered=False) or 0,
                    ),
                    "nutrient_tank_level_percent": telemetry.get(
                        "nutrient_tank_level_percent",
                        coarse_solution_tank_level_percent(
                            solution_max_triggered=False,
                            solution_min_triggered=False,
                        )
                        or 0,
                    ),
                    "buffer_tank_level_percent": None,
                    "ph": telemetry.get("ph"),
                    "ec": telemetry.get("ec"),
                },
                "active_processes": {
                    "pump_in": workflow_phase == "tank_filling",
                    "circulation_pump": workflow_phase == "tank_recirc",
                    "ph_correction": False,
                    "ec_correction": False,
                    "active_doses": [],
                },
                "timeline": timeline,
                "next_state": None,
                "estimated_completion_sec": None,
                "irr_node_state": None,
                "solution_tank_guard": solution_tank_guard,
                "decision": None,
                "telemetry_fetch_ok": telemetry_fetch_ok,
                **control_ctx,
            },
            zone_id=zone_id,
            task=None,
            workflow_state=workflow_state,
            telemetry=telemetry,
            telemetry_fetch_ok=telemetry_fetch_ok,
            node_rows=node_rows,
            observability_thresholds=observability_thresholds,
        )

    async def idle_state(
        self,
        *,
        zone_id: int,
        telemetry: dict[str, Any] | None = None,
        telemetry_fetch_ok: bool = True,
        solution_tank_guard: dict[str, Any] | None = None,
        workflow_state: Optional[Any] = None,
        node_rows: list[dict[str, Any]] | None = None,
        observability_thresholds: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        telemetry = telemetry or {}
        timeline = await self._ports.build_timeline(
            zone_id=zone_id,
            transitions=[],
            since_ts=self._ports.idle_timeline_since(),
        )
        control_ctx = await self._ports.control_mode_context(zone_id=zone_id, current_stage=None)
        return await self._ports.attach_observability(
            {
                "zone_id": zone_id,
                "state": "IDLE",
                "state_label": "Ожидание",
                "state_details": {
                    "started_at": None,
                    "elapsed_sec": 0,
                    "progress_percent": 0,
                    "failed": False,
                    "error_code": None,
                    "error_message": None,
                },
                "workflow_phase": "idle",
                "current_stage": None,
                "current_stage_label": None,
                "system_config": {
                    "tanks_count": 2,
                    "system_type": "drip",
                    "clean_tank_capacity_l": None,
                    "nutrient_tank_capacity_l": None,
                },
                "current_levels": {
                    "clean_tank_level_percent": telemetry.get(
                        "clean_tank_level_percent",
                        coarse_clean_tank_level_percent(clean_max_triggered=False) or 0,
                    ),
                    "nutrient_tank_level_percent": telemetry.get(
                        "nutrient_tank_level_percent",
                        coarse_solution_tank_level_percent(
                            solution_max_triggered=False,
                            solution_min_triggered=False,
                        )
                        or 0,
                    ),
                    "buffer_tank_level_percent": None,
                    "ph": telemetry.get("ph"),
                    "ec": telemetry.get("ec"),
                },
                "active_processes": {
                    "pump_in": False,
                    "circulation_pump": False,
                    "ph_correction": False,
                    "ec_correction": False,
                    "active_doses": [],
                },
                "timeline": timeline,
                "next_state": None,
                "estimated_completion_sec": None,
                "irr_node_state": None,
                "solution_tank_guard": solution_tank_guard,
                "decision": None,
                "telemetry_fetch_ok": telemetry_fetch_ok,
                **control_ctx,
            },
            zone_id=zone_id,
            task=None,
            workflow_state=workflow_state,
            telemetry=telemetry,
            telemetry_fetch_ok=telemetry_fetch_ok,
            node_rows=node_rows,
            observability_thresholds=observability_thresholds,
        )

    def should_prefer_workflow_state(self, workflow_state: Optional[Any]) -> bool:
        if workflow_state is None:
            return False
        workflow_phase = str(getattr(workflow_state, "workflow_phase", None) or "idle").strip().lower()
        payload = getattr(workflow_state, "payload", None)
        normalized_payload = payload if isinstance(payload, Mapping) else {}
        current_stage = str(normalized_payload.get("ae3_cycle_start_stage") or "").strip().lower()
        if self._ports.workflow_failure_rollback_applied(workflow_state):
            return True
        # irrig_recirc: legacy compat only for old zone_workflow_state rows.
        return (
            workflow_phase in {"tank_filling", "tank_recirc", "ready", "irrigating", "irrig_recirc"}
            or current_stage == "startup"
        )

    def workflow_state_is_stale(self, *, workflow_state: Optional[Any], last_task: Optional[Any]) -> bool:
        if workflow_state is None or last_task is None:
            return False
        if bool(getattr(last_task, "is_active", False)):
            return False
        if self._ports.workflow_failure_rollback_applied(workflow_state):
            return False

        scheduler_task_id = str(getattr(workflow_state, "scheduler_task_id", "") or "").strip()
        if scheduler_task_id and scheduler_task_id == str(getattr(last_task, "id", "") or ""):
            return True

        workflow_updated_at = getattr(workflow_state, "updated_at", None)
        task_updated_at = getattr(last_task, "updated_at", None)
        if workflow_updated_at is None or task_updated_at is None:
            return False

        workflow_cmp = self._ports.normalize_utc_naive(workflow_updated_at)
        task_cmp = self._ports.normalize_utc_naive(task_updated_at)
        return task_cmp >= workflow_cmp
