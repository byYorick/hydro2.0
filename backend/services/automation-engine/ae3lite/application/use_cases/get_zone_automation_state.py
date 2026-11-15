"""Собирает полное automation state зоны для endpoint'а /zones/{id}/state."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional

from ae3lite.application.level_monitor import (
    coarse_clean_tank_level_percent,
    coarse_solution_tank_level_percent,
    load_zone_level_monitor_config,
    summarize_zone_telemetry_rows,
)
from ae3lite.application.services.automation_observability import build_automation_observability
from ae3lite.domain.services.workflow_failure_rollback import resolve_diagnostic_stage_after_rollback
from common.observability_thresholds import load_system_observability_thresholds
from ae3lite.application.use_cases.manual_control_contract import (
    AVAILABLE_CONTROL_MODES,
    allowed_manual_steps_for_task,
    normalize_control_mode,
)
from ae3lite.domain.services.zone_node_availability import ZONE_NODES_DIAG_SQL


# Соответствие (from_stage, to_stage) → (event_code, human label)


# Порядок подэтапов cycle_start / irrigation для оценки progress_percent в UI.


# Подэтапы полива: progress_percent считаем по stage_deadline, а не по индексу в cycle_start.


from ae3lite.application.services.zone_state_shared import (
    logger,
    _WORKFLOW_PHASE_TO_STATE,
    _STATE_LABELS,
    _STAGE_LABELS,
    _TRANSITION_EVENT_MAP,
    _EC_CORRECTION_STEPS,
    _PH_CORRECTION_STEPS,
    _TIMELINE_NODE_EVENT_TYPES,
    _LEVEL_CHANNEL_LABELS,
    _NODE_EVENT_LABELS,
    _IDLE_NODE_EVENT_LOOKBACK_SEC,
    _CYCLE_START_STAGE_ORDER,
    _WORKFLOW_PHASE_PROGRESS,
    _IRRIGATION_STAGE_PREFIX,
    _TERMINAL_COMPLETED_STAGES,
)

from ae3lite.application.services.zone_state_coordination import ZoneStateCoordination, ZoneStateCoordinationPorts
from ae3lite.application.services.zone_state_queries import ZoneStateQueries, ZoneStateQueriesPorts
from ae3lite.application.services.zone_state_timeline import ZoneStateTimeline, ZoneStateTimelinePorts
from ae3lite.application.services.zone_state_presentation import ZoneStatePresentation, ZoneStatePresentationPorts
from ae3lite.application.services.zone_state_failure_overlay import (
    ZoneStateFailureOverlay,
    ZoneStateFailureOverlayPorts,
)
from ae3lite.application.services.zone_state_state_views import ZoneStateStateViews, ZoneStateStateViewsPorts
from ae3lite.application.services.zone_state_doses import ZoneStateDoses, ZoneStateDosesPorts
from ae3lite.application.services.zone_state_observability import ZoneStateObservability, ZoneStateObservabilityPorts
from ae3lite.application.services.zone_state_time_values import ZoneStateTimeValues, ZoneStateTimeValuesPorts


class GetZoneAutomationStateUseCase:
    """Возвращает полный payload зоны в формате AutomationState.

    Читает последнюю задачу, включая failed/completed, и маппит её в структуру,
    которую ожидает Laravel frontend. Дополняет ответ переходами между stage
    и живой телеметрией.
    """

    def __init__(
        self,
        *,
        task_repository: Any,
        workflow_repository: Any | None = None,
        fetch_fn: Callable | None = None,
        startup_reset_guard_use_case: Any | None = None,
    ) -> None:
        self._task_repository = task_repository
        self._fetch_fn = fetch_fn
        self._workflow_repository = workflow_repository
        self._startup_reset_guard_use_case = startup_reset_guard_use_case
        self._zone_state_coordination = ZoneStateCoordination(
            ZoneStateCoordinationPorts(
                build_state=lambda *args, **kwargs: self._build_state(*args, **kwargs),
                build_workflow_state=lambda *args, **kwargs: self._build_workflow_state(*args, **kwargs),
                fetch_fn=lambda *args, **kwargs: self._fetch_fn(*args, **kwargs),
                fetch_zone_nodes_diag=lambda *args, **kwargs: self._fetch_zone_nodes_diag(*args, **kwargs),
                fetch_zone_telemetry=lambda *args, **kwargs: self._fetch_zone_telemetry(*args, **kwargs),
                merge_last_failed_task_into_workflow_view=lambda *args, **kwargs: (
                    self._merge_last_failed_task_into_workflow_view(*args, **kwargs)
                ),
                normalize_solution_tank_guard=lambda *args, **kwargs: self._normalize_solution_tank_guard(
                    *args, **kwargs
                ),
                now=lambda *args, **kwargs: self._now(*args, **kwargs),
                should_prefer_workflow_state=lambda *args, **kwargs: self._should_prefer_workflow_state(
                    *args, **kwargs
                ),
                startup_reset_guard_use_case=lambda: self._startup_reset_guard_use_case,
                task_repository=lambda: self._task_repository,
                workflow_repository=lambda: self._workflow_repository,
                workflow_state_is_stale=lambda *args, **kwargs: self._workflow_state_is_stale(*args, **kwargs),
            )
        )
        self._zone_state_queries = ZoneStateQueries(
            ZoneStateQueriesPorts(
                build_node_runtime_timeline_event=lambda *args, **kwargs: self._build_node_runtime_timeline_event(
                    *args, **kwargs
                ),
                fetch_fn=lambda *args, **kwargs: self._fetch_fn(*args, **kwargs),
                task_repository=lambda: self._task_repository,
            )
        )
        self._zone_state_timeline = ZoneStateTimeline(
            ZoneStateTimelinePorts(
                fetch_recent_node_runtime_events=lambda *args, **kwargs: self._fetch_recent_node_runtime_events(
                    *args, **kwargs
                ),
                normalize_utc_naive=lambda *args, **kwargs: self._normalize_utc_naive(*args, **kwargs),
                now=lambda *args, **kwargs: self._now(*args, **kwargs),
            )
        )
        self._zone_state_presentation = ZoneStatePresentation(
            ZoneStatePresentationPorts(
                fetch_fn=lambda *args, **kwargs: self._fetch_fn(*args, **kwargs),
                iso_or_none=lambda *args, **kwargs: self._iso_or_none(*args, **kwargs),
                normalize_utc_naive=lambda *args, **kwargs: self._normalize_utc_naive(*args, **kwargs),
                now=lambda *args, **kwargs: self._now(*args, **kwargs),
            )
        )
        self._zone_state_failure_overlay = ZoneStateFailureOverlay(
            ZoneStateFailureOverlayPorts(
                normalize_utc_naive=lambda *args, **kwargs: self._normalize_utc_naive(*args, **kwargs),
                primary_automation_state_label=lambda *args, **kwargs: self._primary_automation_state_label(
                    *args, **kwargs
                ),
            )
        )
        self._zone_state_state_views = ZoneStateStateViews(
            ZoneStateStateViewsPorts(
                attach_observability=lambda *args, **kwargs: self._attach_observability(*args, **kwargs),
                build_active_processes=lambda *args, **kwargs: self._build_active_processes(*args, **kwargs),
                build_decision=lambda *args, **kwargs: self._build_decision(*args, **kwargs),
                build_state_details=lambda *args, **kwargs: self._build_state_details(*args, **kwargs),
                build_timeline=lambda *args, **kwargs: self._build_timeline(*args, **kwargs),
                control_mode_context=lambda *args, **kwargs: self._control_mode_context(*args, **kwargs),
                idle_timeline_since=lambda *args, **kwargs: self._idle_timeline_since(*args, **kwargs),
                normalize_utc_naive=lambda *args, **kwargs: self._normalize_utc_naive(*args, **kwargs),
                primary_automation_state_label=lambda *args, **kwargs: self._primary_automation_state_label(
                    *args, **kwargs
                ),
                solution_tank_guard_from_payload=lambda *args, **kwargs: self._solution_tank_guard_from_payload(
                    *args, **kwargs
                ),
                timeline_since=lambda *args, **kwargs: self._timeline_since(*args, **kwargs),
                timeline_since_workflow=lambda *args, **kwargs: self._timeline_since_workflow(*args, **kwargs),
                workflow_failure_rollback_applied=lambda *args, **kwargs: self._workflow_failure_rollback_applied(
                    *args, **kwargs
                ),
            )
        )
        self._zone_state_doses = ZoneStateDoses(ZoneStateDosesPorts())
        self._zone_state_observability = ZoneStateObservability(
            ZoneStateObservabilityPorts(
                latest_irrigation_task=lambda *args, **kwargs: self._latest_irrigation_task(*args, **kwargs),
                now=lambda *args, **kwargs: self._now(*args, **kwargs),
            )
        )
        self._zone_state_time_values = ZoneStateTimeValues(ZoneStateTimeValuesPorts())

    async def run(self, *, zone_id: int) -> dict[str, Any]:
        # Сначала пробуем активную задачу, затем последнюю terminal-задачу
        return await self._zone_state_coordination.run(zone_id=zone_id)

    async def _fetch_zone_telemetry(self, *, zone_id: int) -> tuple[dict[str, Any], bool]:
        return await self._zone_state_queries.fetch_zone_telemetry(zone_id=zone_id)

    async def _fetch_zone_nodes_diag(self, *, zone_id: int) -> list[dict[str, Any]]:
        return await self._zone_state_queries.fetch_zone_nodes_diag(zone_id=zone_id)

    async def _fetch_recent_node_runtime_events(
        self, *, zone_id: int, since_ts: datetime | None
    ) -> list[dict[str, Any]]:
        return await self._zone_state_queries.fetch_recent_node_runtime_events(zone_id=zone_id, since_ts=since_ts)

    def _build_node_runtime_timeline_event(self, row: Mapping[str, Any]) -> dict[str, Any] | None:
        return self._zone_state_timeline.build_node_runtime_timeline_event(row=row)

    async def _build_timeline(
        self,
        *,
        zone_id: int,
        transitions: list[dict],
        since_ts: datetime | None,
    ) -> list[dict]:
        return await self._zone_state_timeline.build_timeline(
            zone_id=zone_id, transitions=transitions, since_ts=since_ts
        )

    def _primary_automation_state_label(
        self,
        *,
        workflow_phase: str,
        mapped_macro_state: str,
        current_stage: str,
        is_terminal_failed: bool,
    ) -> str:
        return self._zone_state_presentation.primary_automation_state_label(
            workflow_phase=workflow_phase,
            mapped_macro_state=mapped_macro_state,
            current_stage=current_stage,
            is_terminal_failed=is_terminal_failed,
        )

    def _estimate_progress_percent(self, *, current_stage: str, workflow_phase: str) -> int:
        return self._zone_state_presentation.estimate_progress_percent(
            current_stage=current_stage, workflow_phase=workflow_phase
        )

    def _timed_irrigation_metrics(
        self,
        *,
        stage_entered_at: datetime | None,
        stage_deadline_at: datetime | None,
        irrigation_requested_duration_sec: Any,
        current_stage: str,
        task_created_at: datetime | None = None,
        task_type: str = "",
    ) -> tuple[int | None, int | None]:
        return self._zone_state_presentation.timed_irrigation_metrics(
            stage_entered_at=stage_entered_at,
            stage_deadline_at=stage_deadline_at,
            irrigation_requested_duration_sec=irrigation_requested_duration_sec,
            current_stage=current_stage,
            task_created_at=task_created_at,
            task_type=task_type,
        )

    def _elapsed_sec_since(self, entered_at: datetime | None) -> int:
        return self._zone_state_presentation.elapsed_sec_since(entered_at=entered_at)

    def _iso_or_none(self, value: Any) -> str | None:
        return self._zone_state_time_values.iso_or_none(value=value)

    def _build_state_details(
        self,
        *,
        is_failed: bool,
        error_code: Any = None,
        error_message: Any = None,
        stage_entered_at: datetime | None = None,
        task_created_at: datetime | None = None,
        current_stage: str = "",
        workflow_phase: str = "idle",
        workflow_started_at: datetime | None = None,
        stage_deadline_at: datetime | None = None,
        irrigation_requested_duration_sec: Any = None,
        task_status: str = "",
        task_type: str = "",
        completed_at: datetime | None = None,
    ) -> dict[str, Any]:
        return self._zone_state_presentation.build_state_details(
            is_failed=is_failed,
            error_code=error_code,
            error_message=error_message,
            stage_entered_at=stage_entered_at,
            task_created_at=task_created_at,
            current_stage=current_stage,
            workflow_phase=workflow_phase,
            workflow_started_at=workflow_started_at,
            stage_deadline_at=stage_deadline_at,
            irrigation_requested_duration_sec=irrigation_requested_duration_sec,
            task_status=task_status,
            task_type=task_type,
            completed_at=completed_at,
        )

    def _should_overlay_failed_task_on_workflow(
        self,
        *,
        workflow_state: Optional[Any],
        last_task: Any,
    ) -> bool:
        return self._zone_state_failure_overlay.should_overlay_failed_task_on_workflow(
            workflow_state=workflow_state, last_task=last_task
        )

    def _observability_after_failure_rollback(
        self,
        observability: Any,
        *,
        last_task: Any,
        failed_stage: str,
    ) -> dict[str, Any]:
        return self._zone_state_failure_overlay.observability_after_failure_rollback(
            observability=observability, last_task=last_task, failed_stage=failed_stage
        )

    def _merge_last_failed_task_into_workflow_view(
        self,
        payload: dict[str, Any],
        last_task: Optional[Any],
        workflow_state: Optional[Any] = None,
    ) -> dict[str, Any]:
        return self._zone_state_failure_overlay.merge_last_failed_task_into_workflow_view(
            payload=payload, last_task=last_task, workflow_state=workflow_state
        )

    async def _control_mode_context(
        self,
        *,
        zone_id: int,
        current_stage: str | None,
        task_type: str | None = None,
        pending_manual_step: str | None = None,
    ) -> dict[str, Any]:
        return await self._zone_state_presentation.control_mode_context(
            zone_id=zone_id, current_stage=current_stage, task_type=task_type, pending_manual_step=pending_manual_step
        )

    async def _build_state(
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
        return await self._zone_state_state_views.build_state(
            zone_id=zone_id,
            task=task,
            transitions=transitions,
            telemetry=telemetry,
            telemetry_fetch_ok=telemetry_fetch_ok,
            solution_tank_guard=solution_tank_guard,
            workflow_state=workflow_state,
            node_rows=node_rows,
            observability_thresholds=observability_thresholds,
        )

    async def _build_workflow_state(
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
        return await self._zone_state_state_views.build_workflow_state(
            zone_id=zone_id,
            workflow_state=workflow_state,
            telemetry=telemetry,
            telemetry_fetch_ok=telemetry_fetch_ok,
            solution_tank_guard=solution_tank_guard,
            node_rows=node_rows,
            observability_thresholds=observability_thresholds,
        )

    async def _idle_state(
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
        return await self._zone_state_state_views.idle_state(
            zone_id=zone_id,
            telemetry=telemetry,
            telemetry_fetch_ok=telemetry_fetch_ok,
            solution_tank_guard=solution_tank_guard,
            workflow_state=workflow_state,
            node_rows=node_rows,
            observability_thresholds=observability_thresholds,
        )

    async def _latest_irrigation_task(self, *, zone_id: int, task: Optional[Any]) -> Any | None:
        return await self._zone_state_queries.latest_irrigation_task(zone_id=zone_id, task=task)

    async def _attach_observability(
        self,
        payload: dict[str, Any],
        *,
        zone_id: int,
        task: Optional[Any],
        workflow_state: Optional[Any],
        telemetry: Mapping[str, Any],
        telemetry_fetch_ok: bool,
        node_rows: list[dict[str, Any]] | None,
        observability_thresholds: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        return await self._zone_state_observability.attach_observability(
            payload=payload,
            zone_id=zone_id,
            task=task,
            workflow_state=workflow_state,
            telemetry=telemetry,
            telemetry_fetch_ok=telemetry_fetch_ok,
            node_rows=node_rows,
            observability_thresholds=observability_thresholds,
        )

    def _build_active_processes(
        self,
        *,
        workflow_phase: str,
        is_active: bool,
        correction: Any | None,
    ) -> dict[str, Any]:
        return self._zone_state_doses.build_active_processes(
            workflow_phase=workflow_phase, is_active=is_active, correction=correction
        )

    def _build_active_doses(
        self,
        *,
        is_active: bool,
        correction: Any | None,
        corr_step: str,
    ) -> list[dict[str, Any]]:
        return self._zone_state_doses.build_active_doses(
            is_active=is_active, correction=correction, corr_step=corr_step
        )

    def _build_active_ec_doses(self, correction: Any) -> list[dict[str, Any]]:
        return self._zone_state_doses.build_active_ec_doses(correction=correction)

    def _build_active_ph_doses(self, correction: Any) -> list[dict[str, Any]]:
        return self._zone_state_doses.build_active_ph_doses(correction=correction)

    _parse_ec_dose_sequence = staticmethod(ZoneStateDoses.parse_ec_dose_sequence)

    _dose_entry = staticmethod(ZoneStateDoses.dose_entry)

    def _should_prefer_workflow_state(self, workflow_state: Optional[Any]) -> bool:
        return self._zone_state_state_views.should_prefer_workflow_state(workflow_state=workflow_state)

    def _workflow_failure_rollback_applied(self, workflow_state: Optional[Any]) -> bool:
        return self._zone_state_failure_overlay.workflow_failure_rollback_applied(workflow_state=workflow_state)

    def _workflow_state_is_stale(self, *, workflow_state: Optional[Any], last_task: Optional[Any]) -> bool:
        return self._zone_state_state_views.workflow_state_is_stale(workflow_state=workflow_state, last_task=last_task)

    def _timeline_since(self, *, task: Any | None) -> datetime | None:
        return self._zone_state_timeline.timeline_since(task=task)

    def _timeline_since_workflow(self, *, workflow_state: Any | None) -> datetime | None:
        return self._zone_state_timeline.timeline_since_workflow(workflow_state=workflow_state)

    def _idle_timeline_since(self) -> datetime:
        return self._zone_state_timeline.idle_timeline_since()

    def _now(self) -> Any:
        return self._zone_state_time_values.now()

    def _normalize_utc_naive(self, value: Any) -> Any:
        return self._zone_state_time_values.normalize_utc_naive(value=value)

    def _normalize_solution_tank_guard(self, guard_result: Any) -> dict[str, Any] | None:
        return self._zone_state_observability.normalize_solution_tank_guard(guard_result=guard_result)

    def _solution_tank_guard_from_payload(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        return self._zone_state_observability.solution_tank_guard_from_payload(payload=payload)

    def _build_decision(self, task: Any) -> dict[str, Any] | None:
        return self._zone_state_observability.build_decision(task=task)
