"""Runtime/state methods for ZoneAutomationService."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from common.db import create_zone_event, fetch
from common.simulation_clock import SimulationClock
from common.utils.time import utcnow
from common.water_flow import check_water_level, ensure_water_level_alert
from services.zone_process_cycle import process_zone_cycle as policy_process_zone_cycle
from services.zone_runtime_backoff import (
    calculate_backoff_seconds as policy_calculate_backoff_seconds,
    is_degraded_mode as policy_is_degraded_mode,
    record_zone_error as policy_record_zone_error,
    reset_zone_error_streak as policy_reset_zone_error_streak,
    should_process_zone as policy_should_process_zone,
)
from services.zone_state_runtime import (
    get_or_restore_workflow_phase as policy_get_or_restore_workflow_phase,
    get_zone_state as policy_get_zone_state,
    normalize_workflow_phase as policy_normalize_workflow_phase,
    reset_zone_pid_state as policy_reset_zone_pid_state,
    resolve_allowed_ec_components as policy_resolve_allowed_ec_components,
    restore_workflow_phase_from_events as policy_restore_workflow_phase_from_events,
    sync_sensor_mode_cache_with_workflow_phase as policy_sync_sensor_mode_cache_with_workflow_phase,
    update_workflow_phase as policy_update_workflow_phase,
)

from services.zone_automation_constants import (
    BACKOFF_MULTIPLIER,
    CHECK_LAT,
    DEGRADED_MODE_THRESHOLD,
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
    WORKFLOW_EC_COMPONENTS_BY_PHASE,
    WORKFLOW_PHASE_EVENT_TYPE,
    WORKFLOW_PHASE_VALUES,
    WORKFLOW_SENSOR_MODE_EXTERNAL_PHASES,
    ZONE_CHECKS,
)

logger = logging.getLogger(__name__)


async def save_all_pid_states(self) -> None:
    """Сохранить состояние всех PID контроллеров."""
    await self.ph_controller.save_all_states()
    await self.ec_controller.save_all_states()


def serialize_dt(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def deserialize_dt(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def export_runtime_state(self) -> Dict[str, Any]:
    zone_states: Dict[str, Any] = {}
    for zone_id, state in self._zone_states.items():
        if not isinstance(state, dict):
            continue
        serialized_state = dict(state)
        for key, raw_value in list(serialized_state.items()):
            if isinstance(raw_value, datetime):
                serialized_state[key] = raw_value.isoformat()
        zone_states[str(zone_id)] = serialized_state

    def _serialize_controller_map(raw: Dict[tuple[int, str], datetime]) -> Dict[str, str]:
        payload: Dict[str, str] = {}
        for (zone_id, controller_name), dt_value in raw.items():
            if isinstance(dt_value, datetime):
                payload[f"{int(zone_id)}::{str(controller_name)}"] = dt_value.isoformat()
        return payload

    return {
        "zone_states": zone_states,
        "controller_failures": _serialize_controller_map(self._controller_failures),
        "controller_cooldown_reported_at": _serialize_controller_map(self._controller_cooldown_reported_at),
        "controller_circuit_open_reported_at": _serialize_controller_map(self._controller_circuit_open_reported_at),
        "correction_sensor_mode_state": {
            str(zone_id): bool(value)
            for zone_id, value in self._correction_sensor_mode_state.items()
        },
        "ph_controller": self.ph_controller.export_runtime_state(),
        "ec_controller": self.ec_controller.export_runtime_state(),
    }


def restore_runtime_state(self, raw_state: Optional[Dict[str, Any]]) -> None:
    state = raw_state or {}

    zone_states: Dict[int, Dict[str, Any]] = {}
    raw_zone_states = state.get("zone_states")
    if isinstance(raw_zone_states, dict):
        for key, payload in raw_zone_states.items():
            if not isinstance(payload, dict):
                continue
            try:
                zone_id = int(key)
            except (TypeError, ValueError):
                continue
            normalized = dict(payload)
            for field in (
                "next_allowed_run_at",
                "last_backoff_reported_until",
                "last_missing_targets_report_at",
                "last_missing_correction_flags_report_at",
                "last_stale_correction_flags_report_at",
                "last_correction_skip_event_at",
                "required_nodes_offline_since",
                "last_required_nodes_offline_report_at",
                "workflow_phase_updated_at",
            ):
                normalized[field] = self._deserialize_dt(normalized.get(field))
            zone_states[zone_id] = normalized
    self._zone_states = zone_states

    def _deserialize_controller_map(raw: Any) -> Dict[tuple[int, str], datetime]:
        result: Dict[tuple[int, str], datetime] = {}
        if not isinstance(raw, dict):
            return result
        for key, value in raw.items():
            if not isinstance(key, str) or "::" not in key:
                continue
            zone_part, controller_name = key.split("::", 1)
            dt_value = self._deserialize_dt(value)
            if dt_value is None:
                continue
            try:
                zone_id = int(zone_part)
            except (TypeError, ValueError):
                continue
            result[(zone_id, controller_name)] = dt_value
        return result

    self._controller_failures = _deserialize_controller_map(state.get("controller_failures"))
    self._controller_cooldown_reported_at = _deserialize_controller_map(state.get("controller_cooldown_reported_at"))
    self._controller_circuit_open_reported_at = _deserialize_controller_map(state.get("controller_circuit_open_reported_at"))

    raw_sensor_mode = state.get("correction_sensor_mode_state")
    sensor_mode: Dict[int, bool] = {}
    if isinstance(raw_sensor_mode, dict):
        for key, value in raw_sensor_mode.items():
            try:
                sensor_mode[int(key)] = bool(value)
            except (TypeError, ValueError):
                continue
    self._correction_sensor_mode_state = sensor_mode

    self.ph_controller.restore_runtime_state(state.get("ph_controller"))
    self.ec_controller.restore_runtime_state(state.get("ec_controller"))


async def process_zone(self, zone_id: int, sim_clock: Optional[SimulationClock] = None) -> None:
    async def _load_zone_control_mode_for_cycle(target_zone_id: int) -> str:
        rows = await fetch(
            """
            SELECT payload
            FROM zone_workflow_state
            WHERE zone_id = $1
            LIMIT 1
            """,
            target_zone_id,
        )
        if not rows:
            return "auto"
        raw_payload = rows[0].get("payload")
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        mode = str(payload.get("control_mode") or "").strip().lower()
        return mode if mode in {"auto", "semi", "manual"} else "auto"

    async def _load_latest_zone_task_for_cycle(target_zone_id: int) -> Optional[Dict[str, Any]]:
        rows = await fetch(
            """
            SELECT task_id, status, accepted_at, terminal_at
            FROM laravel_scheduler_active_tasks
            WHERE zone_id = $1
              AND terminal_at IS NULL
              AND status IN ('accepted', 'running')
            ORDER BY accepted_at DESC, id DESC
            LIMIT 1
            """,
            target_zone_id,
        )
        if not rows:
            fallback_rows = await fetch(
                """
                SELECT
                    details->>'task_id' AS task_id,
                    status,
                    created_at AS accepted_at,
                    NULL::timestamp AS terminal_at
                FROM scheduler_logs
                WHERE details->>'zone_id' = $1::text
                  AND task_name LIKE 'ae_scheduler_task_%'
                ORDER BY id DESC
                LIMIT 1
                """,
                str(target_zone_id),
            )
            if not fallback_rows:
                return None
            fallback_task = dict(fallback_rows[0])
            fallback_status = str(fallback_task.get("status") or "").strip().lower()
            if fallback_status in {"accepted", "running"}:
                return fallback_task
            return None
        return dict(rows[0])

    await policy_process_zone_cycle(
        zone_id=zone_id,
        sim_clock=sim_clock,
        should_process_zone_fn=self._should_process_zone,
        emit_backoff_skip_signal_fn=self._emit_backoff_skip_signal,
        is_degraded_mode_fn=self._is_degraded_mode,
        check_zone_deletion_fn=self._check_zone_deletion,
        check_pid_config_updates_fn=self._check_pid_config_updates,
        check_phase_transitions_fn=self._check_phase_transitions,
        grow_cycle_repo=self.grow_cycle_repo,
        recipe_repo=self.recipe_repo,
        infrastructure_repo=self.infrastructure_repo,
        actuator_registry=self.actuator_registry,
        record_zone_error_fn=self._record_zone_error,
        emit_zone_data_unavailable_signal_fn=self._emit_zone_data_unavailable_signal,
        get_or_restore_workflow_phase_fn=self._get_or_restore_workflow_phase,
        safe_process_controller_fn=self._safe_process_controller,
        process_light_controller_fn=self._process_light_controller,
        process_climate_controller_fn=self._process_climate_controller,
        process_irrigation_controller_fn=self._process_irrigation_controller,
        process_recirculation_controller_fn=self._process_recirculation_controller,
        process_correction_controllers_fn=self._process_correction_controllers,
        load_zone_control_mode_fn=_load_zone_control_mode_for_cycle,
        load_latest_zone_task_fn=_load_latest_zone_task_for_cycle,
        evaluate_required_nodes_recovery_gate_fn=self._evaluate_required_nodes_recovery_gate,
        update_zone_health_fn=self._update_zone_health,
        emit_missing_targets_signal_fn=self._emit_missing_targets_signal,
        emit_degraded_mode_signal_fn=self._emit_degraded_mode_signal,
        reset_zone_error_streak_fn=self._reset_zone_error_streak,
        emit_zone_recovered_signal_fn=self._emit_zone_recovered_signal,
        get_error_streak_fn=self._get_error_streak,
        get_next_allowed_run_at_fn=self._get_next_allowed_run_at,
        create_zone_event_fn=create_zone_event,
        check_water_level_fn=check_water_level,
        ensure_water_level_alert_fn=ensure_water_level_alert,
        utcnow_fn=utcnow,
        check_latency_metric=CHECK_LAT,
        zone_checks_metric=ZONE_CHECKS,
        logger=logger,
    )


def get_zone_state(self, zone_id: int) -> Dict[str, Any]:
    return policy_get_zone_state(
        zone_id=zone_id,
        zone_states=self._zone_states,
        logger=logger,
    )


def get_error_streak(self, zone_id: int) -> int:
    return self._get_zone_state(zone_id)["error_streak"]


def get_next_allowed_run_at(self, zone_id: int) -> Optional[datetime]:
    return self._get_zone_state(zone_id)["next_allowed_run_at"]


def normalize_workflow_phase(raw: Any) -> str:
    return policy_normalize_workflow_phase(raw, workflow_phase_values=WORKFLOW_PHASE_VALUES)


async def restore_workflow_phase_from_events(self, zone_id: int) -> str:
    return await policy_restore_workflow_phase_from_events(
        zone_id=zone_id,
        fetch_fn=fetch,
        workflow_phase_event_type=WORKFLOW_PHASE_EVENT_TYPE,
        normalize_workflow_phase_fn=self._normalize_workflow_phase,
        logger=logger,
    )


async def get_or_restore_workflow_phase(self, zone_id: int) -> str:
    return await policy_get_or_restore_workflow_phase(
        zone_id=zone_id,
        state=self._get_zone_state(zone_id),
        restore_workflow_phase_from_events_fn=self._restore_workflow_phase_from_events,
        normalize_workflow_phase_fn=self._normalize_workflow_phase,
        utcnow_fn=utcnow,
        logger=logger,
    )


def reset_zone_pid_state(self, zone_id: int) -> None:
    policy_reset_zone_pid_state(
        zone_id=zone_id,
        ph_controller=self.ph_controller,
        ec_controller=self.ec_controller,
        logger=logger,
    )


def sync_sensor_mode_cache_with_workflow_phase(
    self,
    *,
    zone_id: int,
    previous_phase: str,
    normalized_phase: str,
) -> None:
    policy_sync_sensor_mode_cache_with_workflow_phase(
        zone_id=zone_id,
        previous_phase=previous_phase,
        normalized_phase=normalized_phase,
        correction_sensor_mode_state=self._correction_sensor_mode_state,
        workflow_sensor_mode_external_phases=WORKFLOW_SENSOR_MODE_EXTERNAL_PHASES,
        logger=logger,
    )


async def update_workflow_phase(
    self,
    *,
    zone_id: int,
    workflow_phase: str,
    workflow_stage: Optional[str] = None,
    source: str = "scheduler",
    reason_code: Optional[str] = None,
    force_event: bool = False,
) -> str:
    return await policy_update_workflow_phase(
        zone_id=zone_id,
        workflow_phase=workflow_phase,
        workflow_stage=workflow_stage,
        source=source,
        reason_code=reason_code,
        force_event=force_event,
        state=self._get_zone_state(zone_id),
        normalize_workflow_phase_fn=self._normalize_workflow_phase,
        utcnow_fn=utcnow,
        reset_zone_pid_state_fn=self._reset_zone_pid_state,
        sync_sensor_mode_cache_with_workflow_phase_fn=self._sync_sensor_mode_cache_with_workflow_phase,
        create_zone_event_fn=create_zone_event,
        workflow_phase_event_type=WORKFLOW_PHASE_EVENT_TYPE,
        logger=logger,
    )


def resolve_allowed_ec_components(workflow_phase: str) -> Optional[list[str]]:
    return policy_resolve_allowed_ec_components(
        workflow_phase=workflow_phase,
        normalize_workflow_phase_fn=normalize_workflow_phase,
        workflow_ec_components_by_phase=WORKFLOW_EC_COMPONENTS_BY_PHASE,
    )


def should_process_zone(self, zone_id: int) -> bool:
    return policy_should_process_zone(
        zone_id=zone_id,
        next_allowed_run_at=self._get_next_allowed_run_at(zone_id),
        utcnow_fn=utcnow,
        logger=logger,
    )


def is_degraded_mode(self, zone_id: int) -> bool:
    return policy_is_degraded_mode(
        error_streak=self._get_error_streak(zone_id),
        degraded_mode_threshold=DEGRADED_MODE_THRESHOLD,
    )


def calculate_backoff_seconds(self, error_streak: int) -> int:
    _ = self
    return policy_calculate_backoff_seconds(
        error_streak=error_streak,
        initial_backoff_seconds=INITIAL_BACKOFF_SECONDS,
        backoff_multiplier=BACKOFF_MULTIPLIER,
        max_backoff_seconds=MAX_BACKOFF_SECONDS,
    )


def record_zone_error(self, zone_id: int) -> None:
    policy_record_zone_error(
        zone_id=zone_id,
        get_zone_state_fn=self._get_zone_state,
        calculate_backoff_seconds_fn=self._calculate_backoff_seconds,
        utcnow_fn=utcnow,
        logger=logger,
    )


def reset_zone_error_streak(self, zone_id: int) -> int:
    return policy_reset_zone_error_streak(
        zone_id=zone_id,
        get_zone_state_fn=self._get_zone_state,
        logger=logger,
    )
