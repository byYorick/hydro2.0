"""Zone automation orchestration service."""

from datetime import datetime
from typing import Any, Dict, Optional

from actuator_registry import ActuatorRegistry
from correction_controller import CorrectionController, CorrectionType
from infrastructure.command_bus import CommandBus
from infrastructure.command_gateway import CommandGateway
from repositories import (
    GrowCycleRepository,
    InfrastructureRepository,
    NodeRepository,
    RecipeRepository,
    TelemetryRepository,
    ZoneRepository,
)
from services.pid_state_manager import PidStateManager
from services.zone_automation_constants import (
    BACKOFF_MULTIPLIER,
    CHECK_LAT,
    CONTROLLER_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS,
    CONTROLLER_COOLDOWN_SECONDS,
    COOLDOWN_SKIP_REPORT_THROTTLE_SECONDS,
    CORRECTION_FLAGS_MAX_AGE_SECONDS,
    CORRECTION_FLAGS_MISSING_ALERT_THROTTLE_SECONDS,
    CORRECTION_FLAGS_REQUIRE_TIMESTAMPS,
    CORRECTION_FLAGS_STALE_ALERT_THROTTLE_SECONDS,
    CORRECTION_REQUIRED_FLAG_NAMES,
    CORRECTION_SKIP_EVENT_THROTTLE_SECONDS,
    DEGRADED_MODE_THRESHOLD,
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
    REQUIRED_NODES_OFFLINE_ALERT_THROTTLE_SECONDS,
    SENSOR_MODE_POLICY,
    SKIP_REPORT_THROTTLE_SECONDS,
    WORKFLOW_CORRECTION_OPEN_PHASES,
    WORKFLOW_EC_COMPONENTS_BY_PHASE,
    WORKFLOW_PHASE_EVENT_TYPE,
    WORKFLOW_PHASE_VALUES,
    WORKFLOW_SENSOR_MODE_EXTERNAL_PHASES,
    ZONE_CHECKS,
)
from services.zone_automation_controller_exec import (
    append_correlation_id,
    check_phase_transitions,
    emit_controller_circuit_open_signal,
    emit_controller_cooldown_skip_signal,
    is_controller_in_cooldown,
    process_climate_controller,
    process_irrigation_controller,
    process_light_controller,
    process_recirculation_controller,
    publish_controller_action_with_event_integrity,
    record_controller_failure,
    safe_process_controller,
)
from services.zone_automation_corrections import (
    apply_sensor_mode_policy,
    build_correction_gating_state,
    build_correction_skip_signature,
    check_pid_config_updates,
    check_zone_deletion,
    emit_correction_skip_event_throttled,
    normalize_flag_signature_values,
    process_correction_controllers,
    resolve_correction_sensor_nodes,
    resolve_sensor_mode_action,
    set_sensor_mode,
    update_zone_health,
)
from services.zone_automation_recovery import (
    check_required_nodes_online_safe,
    emit_required_nodes_offline_signal,
    emit_required_nodes_recovered_signal,
    evaluate_required_nodes_recovery_gate,
)
from services.zone_automation_runtime import (
    calculate_backoff_seconds,
    deserialize_dt,
    export_runtime_state,
    get_error_streak,
    get_next_allowed_run_at,
    get_or_restore_workflow_phase,
    get_zone_state,
    is_degraded_mode,
    normalize_workflow_phase,
    process_zone,
    record_zone_error,
    reset_zone_error_streak,
    reset_zone_pid_state,
    resolve_allowed_ec_components,
    restore_runtime_state,
    restore_workflow_phase_from_events,
    save_all_pid_states,
    serialize_dt,
    should_process_zone,
    sync_sensor_mode_cache_with_workflow_phase,
    update_workflow_phase,
)
from services.zone_automation_signals import (
    create_zone_event_safe,
    emit_backoff_skip_signal,
    emit_correction_gating_recovered_signal,
    emit_correction_missing_flags_signal,
    emit_correction_stale_flags_signal,
    emit_degraded_mode_signal,
    emit_missing_targets_signal,
    emit_zone_data_unavailable_signal,
    emit_zone_recovered_signal,
)


# Backward-compatible alias with the original typo used in older code.
COOL_DOWN_SKIP_REPORT_THROTTLE_SECONDS = COOLDOWN_SKIP_REPORT_THROTTLE_SECONDS


class ZoneAutomationService:
    """Оркестрация автоматизации зоны."""

    def __init__(
        self,
        zone_repo: ZoneRepository,
        telemetry_repo: TelemetryRepository,
        node_repo: NodeRepository,
        recipe_repo: RecipeRepository,
        grow_cycle_repo: GrowCycleRepository,
        infrastructure_repo: InfrastructureRepository,
        command_bus: CommandBus,
        pid_state_manager: Optional[PidStateManager] = None,
    ):
        self.zone_repo = zone_repo
        self.telemetry_repo = telemetry_repo
        self.node_repo = node_repo
        self.recipe_repo = recipe_repo
        self.grow_cycle_repo = grow_cycle_repo
        self.infrastructure_repo = infrastructure_repo
        self.command_bus = command_bus
        self.pid_state_manager = pid_state_manager or PidStateManager()
        self.actuator_registry = ActuatorRegistry()
        self.command_gateway = CommandGateway(command_bus)

        self.ph_controller = CorrectionController(CorrectionType.PH, self.pid_state_manager)
        self.ec_controller = CorrectionController(CorrectionType.EC, self.pid_state_manager)

        self._controller_failures: Dict[tuple[int, str], datetime] = {}
        self._zone_states: Dict[int, Dict[str, Any]] = {}
        self._controller_cooldown_reported_at: Dict[tuple[int, str], datetime] = {}
        self._controller_circuit_open_reported_at: Dict[tuple[int, str], datetime] = {}
        self._correction_sensor_mode_state: Dict[int, bool] = {}

    save_all_pid_states = save_all_pid_states
    _serialize_dt = staticmethod(serialize_dt)
    _deserialize_dt = staticmethod(deserialize_dt)
    export_runtime_state = export_runtime_state
    restore_runtime_state = restore_runtime_state
    process_zone = process_zone
    _get_zone_state = get_zone_state
    _get_error_streak = get_error_streak
    _get_next_allowed_run_at = get_next_allowed_run_at
    _normalize_workflow_phase = staticmethod(normalize_workflow_phase)
    _restore_workflow_phase_from_events = restore_workflow_phase_from_events
    _get_or_restore_workflow_phase = get_or_restore_workflow_phase
    _reset_zone_pid_state = reset_zone_pid_state
    _sync_sensor_mode_cache_with_workflow_phase = sync_sensor_mode_cache_with_workflow_phase
    update_workflow_phase = update_workflow_phase
    _resolve_allowed_ec_components = staticmethod(resolve_allowed_ec_components)
    _should_process_zone = should_process_zone
    _is_degraded_mode = is_degraded_mode
    _calculate_backoff_seconds = calculate_backoff_seconds
    _record_zone_error = record_zone_error
    _reset_zone_error_streak = reset_zone_error_streak

    _create_zone_event_safe = create_zone_event_safe
    _emit_backoff_skip_signal = emit_backoff_skip_signal
    _emit_missing_targets_signal = emit_missing_targets_signal
    _emit_correction_missing_flags_signal = emit_correction_missing_flags_signal
    _emit_correction_stale_flags_signal = emit_correction_stale_flags_signal
    _emit_correction_gating_recovered_signal = emit_correction_gating_recovered_signal
    _emit_zone_data_unavailable_signal = emit_zone_data_unavailable_signal
    _emit_degraded_mode_signal = emit_degraded_mode_signal
    _emit_zone_recovered_signal = emit_zone_recovered_signal

    _check_required_nodes_online = check_required_nodes_online_safe
    _emit_required_nodes_offline_signal = emit_required_nodes_offline_signal
    _emit_required_nodes_recovered_signal = emit_required_nodes_recovered_signal
    _evaluate_required_nodes_recovery_gate = evaluate_required_nodes_recovery_gate

    _emit_controller_circuit_open_signal = emit_controller_circuit_open_signal
    _is_controller_in_cooldown = is_controller_in_cooldown
    _record_controller_failure = record_controller_failure
    _safe_process_controller = safe_process_controller
    _emit_controller_cooldown_skip_signal = emit_controller_cooldown_skip_signal
    _check_phase_transitions = check_phase_transitions
    _append_correlation_id = staticmethod(append_correlation_id)
    _publish_controller_action_with_event_integrity = publish_controller_action_with_event_integrity
    _process_light_controller = process_light_controller
    _process_climate_controller = process_climate_controller
    _process_irrigation_controller = process_irrigation_controller
    _process_recirculation_controller = process_recirculation_controller

    _emit_correction_skip_event_throttled = emit_correction_skip_event_throttled
    _normalize_flag_signature_values = staticmethod(normalize_flag_signature_values)
    _build_correction_skip_signature = classmethod(build_correction_skip_signature)
    _resolve_sensor_mode_action = staticmethod(resolve_sensor_mode_action)
    _apply_sensor_mode_policy = apply_sensor_mode_policy
    _process_correction_controllers = process_correction_controllers
    _build_correction_gating_state = build_correction_gating_state
    _resolve_correction_sensor_nodes = staticmethod(resolve_correction_sensor_nodes)
    _set_sensor_mode = set_sensor_mode
    _update_zone_health = update_zone_health
    _check_zone_deletion = check_zone_deletion
    _check_pid_config_updates = check_pid_config_updates


__all__ = [
    "ZoneAutomationService",
    "ZONE_CHECKS",
    "CHECK_LAT",
    "CONTROLLER_COOLDOWN_SECONDS",
    "INITIAL_BACKOFF_SECONDS",
    "MAX_BACKOFF_SECONDS",
    "BACKOFF_MULTIPLIER",
    "DEGRADED_MODE_THRESHOLD",
    "SKIP_REPORT_THROTTLE_SECONDS",
    "COOLDOWN_SKIP_REPORT_THROTTLE_SECONDS",
    "CONTROLLER_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS",
    "CORRECTION_FLAGS_MISSING_ALERT_THROTTLE_SECONDS",
    "REQUIRED_NODES_OFFLINE_ALERT_THROTTLE_SECONDS",
    "CORRECTION_FLAGS_MAX_AGE_SECONDS",
    "CORRECTION_FLAGS_STALE_ALERT_THROTTLE_SECONDS",
    "CORRECTION_SKIP_EVENT_THROTTLE_SECONDS",
    "CORRECTION_FLAGS_REQUIRE_TIMESTAMPS",
    "CORRECTION_REQUIRED_FLAG_NAMES",
    "WORKFLOW_PHASE_EVENT_TYPE",
    "WORKFLOW_PHASE_VALUES",
    "WORKFLOW_CORRECTION_OPEN_PHASES",
    "WORKFLOW_SENSOR_MODE_EXTERNAL_PHASES",
    "WORKFLOW_EC_COMPONENTS_BY_PHASE",
    "SENSOR_MODE_POLICY",
]
