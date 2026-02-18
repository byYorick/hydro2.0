from typing import Dict, Any, Optional, List
import logging
from datetime import datetime
from common.utils.time import utcnow
from common.simulation_clock import SimulationClock
from common.simulation_events import record_simulation_event
from common.infra_alerts import (
    send_infra_alert,
    send_infra_exception_alert,
    send_infra_resolved_alert,
)
from common.db import create_zone_event, fetch
from common.water_flow import check_water_level, ensure_water_level_alert
from common.pump_safety import can_run_pump
from light_controller import check_and_control_lighting
from climate_controller import check_and_control_climate
from irrigation_controller import check_and_control_irrigation, check_and_control_recirculation
from health_monitor import calculate_zone_health, update_zone_health_in_db
from correction_controller import CorrectionController, CorrectionType
from config.settings import get_settings
from repositories import (
    ZoneRepository, 
    TelemetryRepository, 
    NodeRepository, 
    RecipeRepository,
    GrowCycleRepository,
    InfrastructureRepository
)
from infrastructure.command_bus import CommandBus
from infrastructure.command_gateway import CommandGateway
from infrastructure.circuit_breaker import CircuitBreakerOpenError
from services.pid_state_manager import PidStateManager
from prometheus_client import Histogram, Counter
from services.pid_config_service import invalidate_cache
from actuator_registry import ActuatorRegistry
from services.zone_correction_gating import (
    build_correction_gating_state as policy_build_correction_gating_state,
)
from services.zone_sensor_mode_orchestrator import (
    apply_sensor_mode_policy as policy_apply_sensor_mode_policy,
    resolve_correction_sensor_nodes as policy_resolve_correction_sensor_nodes,
    resolve_sensor_mode_action as policy_resolve_sensor_mode_action,
    set_sensor_mode as policy_set_sensor_mode,
)
from services.zone_correction_skip_events import (
    build_correction_skip_signature as policy_build_correction_skip_signature,
    emit_correction_skip_event_throttled as policy_emit_correction_skip_event_throttled,
    normalize_flag_signature_values as policy_normalize_flag_signature_values,
)
from services.zone_correction_signals import (
    emit_correction_missing_flags_signal as policy_emit_correction_missing_flags_signal,
    emit_correction_stale_flags_signal as policy_emit_correction_stale_flags_signal,
)
from services.zone_correction_orchestrator import (
    process_correction_controllers as policy_process_correction_controllers,
)
from services.zone_skip_signals import (
    emit_backoff_skip_signal as policy_emit_backoff_skip_signal,
    emit_missing_targets_signal as policy_emit_missing_targets_signal,
)
from services.zone_runtime_signals import (
    emit_degraded_mode_signal as policy_emit_degraded_mode_signal,
    emit_zone_data_unavailable_signal as policy_emit_zone_data_unavailable_signal,
    emit_zone_recovered_signal as policy_emit_zone_recovered_signal,
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
from services.zone_process_cycle import (
    process_zone_cycle as policy_process_zone_cycle,
)
from services.zone_housekeeping import (
    check_pid_config_updates as policy_check_pid_config_updates,
    check_zone_deletion as policy_check_zone_deletion,
    update_zone_health as policy_update_zone_health,
)
from services.zone_runtime_backoff import (
    calculate_backoff_seconds as policy_calculate_backoff_seconds,
    is_degraded_mode as policy_is_degraded_mode,
    record_zone_error as policy_record_zone_error,
    reset_zone_error_streak as policy_reset_zone_error_streak,
    should_process_zone as policy_should_process_zone,
)
from services.zone_controller_guardrails import (
    emit_controller_circuit_open_signal as policy_emit_controller_circuit_open_signal,
    emit_controller_cooldown_skip_signal as policy_emit_controller_cooldown_skip_signal,
    is_controller_in_cooldown as policy_is_controller_in_cooldown,
    record_controller_failure as policy_record_controller_failure,
    safe_process_controller as policy_safe_process_controller,
)
from services.zone_controller_execution import (
    append_correlation_id as policy_append_correlation_id,
    check_phase_transitions as policy_check_phase_transitions,
    publish_controller_action_with_event_integrity as policy_publish_controller_action_with_event_integrity,
)
from services.zone_controller_processors import (
    process_climate_controller as policy_process_climate_controller,
    process_irrigation_controller as policy_process_irrigation_controller,
    process_light_controller as policy_process_light_controller,
    process_recirculation_controller as policy_process_recirculation_controller,
)

logger = logging.getLogger(__name__)


ZONE_CHECKS = Counter("zone_checks_total", "Zone automation checks")
CHECK_LAT = Histogram("zone_check_seconds", "Zone check duration seconds")

CONTROLLER_COOLDOWN_SECONDS = 60

INITIAL_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 600
BACKOFF_MULTIPLIER = 2
DEGRADED_MODE_THRESHOLD = 3
SKIP_REPORT_THROTTLE_SECONDS = 120
COOLDOWN_SKIP_REPORT_THROTTLE_SECONDS = 120
CONTROLLER_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS = 120
CORRECTION_FLAGS_MISSING_ALERT_THROTTLE_SECONDS = 120
_AUTOMATION_SETTINGS = get_settings()
CORRECTION_FLAGS_MAX_AGE_SECONDS = max(
    30,
    int(getattr(_AUTOMATION_SETTINGS, "AE_CORRECTION_FLAGS_MAX_AGE_SEC", 300)),
)
CORRECTION_FLAGS_STALE_ALERT_THROTTLE_SECONDS = max(
    30,
    int(getattr(_AUTOMATION_SETTINGS, "AE_CORRECTION_FLAGS_STALE_ALERT_THROTTLE_SEC", 120)),
)
CORRECTION_SKIP_EVENT_THROTTLE_SECONDS = max(
    5,
    int(getattr(_AUTOMATION_SETTINGS, "AE_CORRECTION_SKIP_EVENT_THROTTLE_SEC", 120)),
)
CORRECTION_FLAGS_REQUIRE_TIMESTAMPS = bool(
    getattr(_AUTOMATION_SETTINGS, "AE_CORRECTION_FLAGS_REQUIRE_TS", True)
)
CORRECTION_REQUIRED_FLAG_NAMES = ("flow_active", "stable", "corrections_allowed")
WORKFLOW_PHASE_EVENT_TYPE = "WORKFLOW_PHASE_UPDATED"
WORKFLOW_PHASE_VALUES = {"idle", "tank_filling", "tank_recirc", "ready", "irrigating", "irrig_recirc"}
WORKFLOW_CORRECTION_OPEN_PHASES = {"tank_filling", "tank_recirc"}
WORKFLOW_SENSOR_MODE_EXTERNAL_PHASES = {"tank_filling", "tank_recirc", "irrig_recirc"}
WORKFLOW_EC_COMPONENTS_BY_PHASE = {
    "tank_filling": ["npk"],
    "tank_recirc": ["npk"],
    "irrigating": ["calcium", "magnesium", "micro"],
    "irrig_recirc": ["calcium", "magnesium", "micro"],
}
SENSOR_MODE_POLICY = {
    "gating_passed": "noop",
    "missing_flags": "noop",
    "flow_inactive": "deactivate",
    "sensor_unstable": "deactivate",
    "corrections_not_allowed": "deactivate",
    "stale_flags": "deactivate",
}


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
        pid_state_manager: Optional[PidStateManager] = None
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
    
    async def save_all_pid_states(self):
        """Сохранить состояние всех PID контроллеров."""
        await self.ph_controller.save_all_states()
        await self.ec_controller.save_all_states()
    
    async def process_zone(self, zone_id: int, sim_clock: Optional[SimulationClock] = None) -> None:
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
    
    def _get_zone_state(self, zone_id: int) -> Dict[str, Any]:
        return policy_get_zone_state(
            zone_id=zone_id,
            zone_states=self._zone_states,
            logger=logger,
        )
    
    def _get_error_streak(self, zone_id: int) -> int:
        return self._get_zone_state(zone_id)['error_streak']
    
    def _get_next_allowed_run_at(self, zone_id: int) -> Optional[datetime]:
        return self._get_zone_state(zone_id)['next_allowed_run_at']

    @staticmethod
    def _normalize_workflow_phase(raw: Any) -> str:
        return policy_normalize_workflow_phase(raw, workflow_phase_values=WORKFLOW_PHASE_VALUES)

    async def _restore_workflow_phase_from_events(self, zone_id: int) -> str:
        return await policy_restore_workflow_phase_from_events(
            zone_id=zone_id,
            fetch_fn=fetch,
            workflow_phase_event_type=WORKFLOW_PHASE_EVENT_TYPE,
            normalize_workflow_phase_fn=self._normalize_workflow_phase,
            logger=logger,
        )

    async def _get_or_restore_workflow_phase(self, zone_id: int) -> str:
        return await policy_get_or_restore_workflow_phase(
            zone_id=zone_id,
            state=self._get_zone_state(zone_id),
            restore_workflow_phase_from_events_fn=self._restore_workflow_phase_from_events,
            normalize_workflow_phase_fn=self._normalize_workflow_phase,
            utcnow_fn=utcnow,
            logger=logger,
        )

    def _reset_zone_pid_state(self, zone_id: int) -> None:
        policy_reset_zone_pid_state(
            zone_id=zone_id,
            ph_controller=self.ph_controller,
            ec_controller=self.ec_controller,
            logger=logger,
        )

    def _sync_sensor_mode_cache_with_workflow_phase(
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

    @staticmethod
    def _resolve_allowed_ec_components(workflow_phase: str) -> Optional[List[str]]:
        return policy_resolve_allowed_ec_components(
            workflow_phase=workflow_phase,
            normalize_workflow_phase_fn=ZoneAutomationService._normalize_workflow_phase,
            workflow_ec_components_by_phase=WORKFLOW_EC_COMPONENTS_BY_PHASE,
        )
    
    def _should_process_zone(self, zone_id: int) -> bool:
        return policy_should_process_zone(
            zone_id=zone_id,
            next_allowed_run_at=self._get_next_allowed_run_at(zone_id),
            utcnow_fn=utcnow,
            logger=logger,
        )
    
    def _is_degraded_mode(self, zone_id: int) -> bool:
        return policy_is_degraded_mode(
            error_streak=self._get_error_streak(zone_id),
            degraded_mode_threshold=DEGRADED_MODE_THRESHOLD,
        )
    
    def _calculate_backoff_seconds(self, error_streak: int) -> int:
        return policy_calculate_backoff_seconds(
            error_streak=error_streak,
            initial_backoff_seconds=INITIAL_BACKOFF_SECONDS,
            backoff_multiplier=BACKOFF_MULTIPLIER,
            max_backoff_seconds=MAX_BACKOFF_SECONDS,
        )
    
    def _record_zone_error(self, zone_id: int) -> None:
        policy_record_zone_error(
            zone_id=zone_id,
            get_zone_state_fn=self._get_zone_state,
            calculate_backoff_seconds_fn=self._calculate_backoff_seconds,
            utcnow_fn=utcnow,
            logger=logger,
        )
    
    def _reset_zone_error_streak(self, zone_id: int) -> int:
        return policy_reset_zone_error_streak(
            zone_id=zone_id,
            get_zone_state_fn=self._get_zone_state,
            logger=logger,
        )

    async def _create_zone_event_safe(
        self,
        zone_id: int,
        event_type: str,
        details: Dict[str, Any],
        signal_name: str,
    ) -> bool:
        try:
            await create_zone_event(zone_id, event_type, details)
            return True
        except Exception as event_error:
            logger.warning(
                "Zone %s: Failed to create %s event: %s",
                zone_id,
                event_type,
                event_error,
                exc_info=True,
            )
            await send_infra_exception_alert(
                error=event_error,
                code="infra_zone_event_write_failed",
                alert_type="Zone Event Write Failed",
                severity="error",
                zone_id=zone_id,
                service="automation-engine",
                component="zone_events",
                details={
                    "event_type": event_type,
                    "signal_name": signal_name,
                },
            )
            return False

    async def _emit_backoff_skip_signal(self, zone_id: int) -> None:
        """Лог/ивент/алерт при пропуске зоны из-за backoff (с защитой от спама)."""
        await policy_emit_backoff_skip_signal(
            zone_id=zone_id,
            zone_state=self._get_zone_state(zone_id),
            utcnow_fn=utcnow,
            get_error_streak_fn=self._get_error_streak,
            create_zone_event_safe_fn=self._create_zone_event_safe,
            send_infra_alert_fn=send_infra_alert,
            skip_report_throttle_seconds=SKIP_REPORT_THROTTLE_SECONDS,
            logger=logger,
        )

    async def _emit_missing_targets_signal(self, zone_id: int, grow_cycle: Optional[Dict[str, Any]]) -> None:
        """Лог/ивент/алерт при отсутствии targets (чтобы не было тихого return)."""
        await policy_emit_missing_targets_signal(
            zone_id=zone_id,
            grow_cycle=grow_cycle,
            zone_state=self._get_zone_state(zone_id),
            utcnow_fn=utcnow,
            create_zone_event_safe_fn=self._create_zone_event_safe,
            send_infra_alert_fn=send_infra_alert,
            skip_report_throttle_seconds=SKIP_REPORT_THROTTLE_SECONDS,
            logger=logger,
        )

    async def _emit_correction_missing_flags_signal(
        self,
        zone_id: int,
        gating_state: Dict[str, Any],
        nodes: Dict[str, Dict[str, Any]],
    ) -> None:
        """Инфра-алерт о пропуске коррекций из-за отсутствия sensor-mode flags."""
        await policy_emit_correction_missing_flags_signal(
            zone_id=zone_id,
            gating_state=gating_state,
            nodes=nodes,
            zone_state=self._get_zone_state(zone_id),
            utcnow_fn=utcnow,
            resolve_correction_sensor_nodes_fn=self._resolve_correction_sensor_nodes,
            send_infra_alert_fn=send_infra_alert,
            correction_flags_missing_alert_throttle_seconds=CORRECTION_FLAGS_MISSING_ALERT_THROTTLE_SECONDS,
            logger=logger,
        )

    async def _emit_correction_stale_flags_signal(
        self,
        zone_id: int,
        gating_state: Dict[str, Any],
        nodes: Dict[str, Dict[str, Any]],
    ) -> None:
        """Инфра-алерт о пропуске коррекций из-за устаревших correction_flags."""
        await policy_emit_correction_stale_flags_signal(
            zone_id=zone_id,
            gating_state=gating_state,
            nodes=nodes,
            zone_state=self._get_zone_state(zone_id),
            utcnow_fn=utcnow,
            resolve_correction_sensor_nodes_fn=self._resolve_correction_sensor_nodes,
            send_infra_alert_fn=send_infra_alert,
            correction_flags_stale_alert_throttle_seconds=CORRECTION_FLAGS_STALE_ALERT_THROTTLE_SECONDS,
            logger=logger,
        )

    async def _emit_zone_data_unavailable_signal(self, zone_id: int) -> None:
        """Лог/ивент/алерт при недоступности данных зоны (DB circuit breaker open)."""
        state = self._get_zone_state(zone_id)
        await policy_emit_zone_data_unavailable_signal(
            zone_id=zone_id,
            error_streak=int(state.get("error_streak", 0)),
            next_allowed_run_at=state.get("next_allowed_run_at"),
            create_zone_event_safe_fn=self._create_zone_event_safe,
            send_infra_alert_fn=send_infra_alert,
            logger=logger,
        )

    async def _emit_degraded_mode_signal(self, zone_id: int) -> None:
        """Лог/ивент/алерт при входе в degraded mode (один раз на инцидент)."""
        await policy_emit_degraded_mode_signal(
            zone_id=zone_id,
            zone_state=self._get_zone_state(zone_id),
            degraded_mode_threshold=DEGRADED_MODE_THRESHOLD,
            create_zone_event_safe_fn=self._create_zone_event_safe,
            send_infra_alert_fn=send_infra_alert,
            logger=logger,
        )

    async def _emit_zone_recovered_signal(self, zone_id: int, previous_error_streak: int) -> None:
        """Явный recovery-сигнал в логи и zone_events после серии ошибок."""
        await policy_emit_zone_recovered_signal(
            zone_id=zone_id,
            previous_error_streak=previous_error_streak,
            create_zone_event_safe_fn=self._create_zone_event_safe,
            send_infra_resolved_alert_fn=send_infra_resolved_alert,
            logger=logger,
        )

    async def _emit_controller_circuit_open_signal(
        self,
        zone_id: int,
        controller_name: str,
        *,
        channel: Optional[str] = None,
        cmd: Optional[str] = None,
    ) -> None:
        """Алерт о пропуске команды из-за открытого API Circuit Breaker (с троттлингом)."""
        await policy_emit_controller_circuit_open_signal(
            zone_id=zone_id,
            controller_name=controller_name,
            controller_circuit_open_reported_at=self._controller_circuit_open_reported_at,
            throttle_seconds=CONTROLLER_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS,
            utcnow_fn=utcnow,
            send_infra_alert_fn=send_infra_alert,
            channel=channel,
            cmd=cmd,
        )
    
    def _is_controller_in_cooldown(self, zone_id: int, controller_name: str) -> bool:
        return policy_is_controller_in_cooldown(
            zone_id=zone_id,
            controller_name=controller_name,
            controller_failures=self._controller_failures,
            cooldown_seconds=CONTROLLER_COOLDOWN_SECONDS,
            utcnow_fn=utcnow,
        )
    
    def _record_controller_failure(self, zone_id: int, controller_name: str) -> None:
        policy_record_controller_failure(
            zone_id=zone_id,
            controller_name=controller_name,
            controller_failures=self._controller_failures,
            controller_cooldown_reported_at=self._controller_cooldown_reported_at,
            utcnow_fn=utcnow,
        )
    
    async def _safe_process_controller(
        self,
        controller_name: str,
        controller_coro,
        zone_id: int
    ) -> None:
        await policy_safe_process_controller(
            zone_id=zone_id,
            controller_name=controller_name,
            controller_coro=controller_coro,
            is_controller_in_cooldown_fn=self._is_controller_in_cooldown,
            emit_controller_cooldown_skip_signal_fn=self._emit_controller_cooldown_skip_signal,
            record_controller_failure_fn=self._record_controller_failure,
            controller_failures=self._controller_failures,
            controller_cooldown_reported_at=self._controller_cooldown_reported_at,
            create_zone_event_fn=create_zone_event,
            send_infra_exception_alert_fn=send_infra_exception_alert,
            controller_cooldown_seconds=CONTROLLER_COOLDOWN_SECONDS,
            logger=logger,
        )

    async def _emit_controller_cooldown_skip_signal(self, zone_id: int, controller_name: str) -> None:
        """Лог/ивент/алерт при skip контроллера в cooldown с троттлингом."""
        await policy_emit_controller_cooldown_skip_signal(
            zone_id=zone_id,
            controller_name=controller_name,
            controller_failures=self._controller_failures,
            controller_cooldown_reported_at=self._controller_cooldown_reported_at,
            cooldown_seconds=CONTROLLER_COOLDOWN_SECONDS,
            cooldown_skip_report_throttle_seconds=COOLDOWN_SKIP_REPORT_THROTTLE_SECONDS,
            utcnow_fn=utcnow,
            create_zone_event_safe_fn=self._create_zone_event_safe,
            send_infra_alert_fn=send_infra_alert,
            logger=logger,
        )
    
    async def _check_phase_transitions(
        self,
        zone_id: int,
        sim_clock: Optional[SimulationClock] = None,
    ) -> None:
        await policy_check_phase_transitions(
            zone_id=zone_id,
            sim_clock=sim_clock,
            grow_cycle_repo=self.grow_cycle_repo,
            record_simulation_event_fn=record_simulation_event,
            emit_controller_circuit_open_signal_fn=self._emit_controller_circuit_open_signal,
            logger=logger,
        )

    @staticmethod
    def _append_correlation_id(details: Dict[str, Any], correlation_id: Optional[str]) -> Dict[str, Any]:
        return policy_append_correlation_id(details, correlation_id)

    async def _publish_controller_action_with_event_integrity(
        self,
        *,
        zone_id: int,
        controller_name: str,
        command: Dict[str, Any],
    ) -> bool:
        return await policy_publish_controller_action_with_event_integrity(
            zone_id=zone_id,
            controller_name=controller_name,
            command=command,
            command_gateway=self.command_gateway,
            create_zone_event_safe_fn=self._create_zone_event_safe,
            emit_controller_circuit_open_signal_fn=self._emit_controller_circuit_open_signal,
            append_correlation_id_fn=self._append_correlation_id,
        )
    
    async def _process_light_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        capabilities: Dict[str, bool],
        bindings: Dict[str, Dict[str, Any]],
        current_time: datetime,
    ) -> None:
        """Обработка контроллера освещения."""
        await policy_process_light_controller(
            zone_id=zone_id,
            targets=targets,
            capabilities=capabilities,
            bindings=bindings,
            current_time=current_time,
            check_and_control_lighting_fn=check_and_control_lighting,
            publish_controller_action_with_event_integrity_fn=self._publish_controller_action_with_event_integrity,
        )
    
    async def _process_climate_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        capabilities: Dict[str, bool],
        bindings: Dict[str, Dict[str, Any]]
    ) -> None:
        """Обработка контроллера климата."""
        await policy_process_climate_controller(
            zone_id=zone_id,
            targets=targets,
            telemetry=telemetry,
            capabilities=capabilities,
            bindings=bindings,
            check_and_control_climate_fn=check_and_control_climate,
            publish_controller_action_with_event_integrity_fn=self._publish_controller_action_with_event_integrity,
        )
    
    async def _process_irrigation_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        capabilities: Dict[str, bool],
        workflow_phase: str,
        water_level_ok: bool,
        bindings: Dict[str, Dict[str, Any]],
        actuators: Dict[str, Dict[str, Any]],
        current_time: datetime,
        time_scale: Optional[float],
        sim_clock: Optional[SimulationClock],
    ) -> None:
        """Обработка контроллера полива."""
        await policy_process_irrigation_controller(
            zone_id=zone_id,
            targets=targets,
            telemetry=telemetry,
            capabilities=capabilities,
            workflow_phase=workflow_phase,
            bindings=bindings,
            actuators=actuators,
            current_time=current_time,
            time_scale=time_scale,
            sim_clock=sim_clock,
            check_and_control_irrigation_fn=check_and_control_irrigation,
            can_run_pump_fn=can_run_pump,
            send_infra_alert_fn=send_infra_alert,
            publish_controller_action_with_event_integrity_fn=self._publish_controller_action_with_event_integrity,
            logger=logger,
        )
    
    async def _process_recirculation_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        capabilities: Dict[str, bool],
        water_level_ok: bool,
        bindings: Dict[str, Dict[str, Any]],
        actuators: Dict[str, Dict[str, Any]],
        current_time: datetime,
        time_scale: Optional[float],
        sim_clock: Optional[SimulationClock],
    ) -> None:
        """Обработка контроллера рециркуляции."""
        await policy_process_recirculation_controller(
            zone_id=zone_id,
            targets=targets,
            telemetry=telemetry,
            capabilities=capabilities,
            bindings=bindings,
            actuators=actuators,
            current_time=current_time,
            time_scale=time_scale,
            sim_clock=sim_clock,
            check_and_control_recirculation_fn=check_and_control_recirculation,
            publish_controller_action_with_event_integrity_fn=self._publish_controller_action_with_event_integrity,
        )
    
    async def _emit_correction_skip_event_throttled(
        self,
        *,
        zone_id: int,
        event_type: str,
        event_payload: Dict[str, Any],
        reason_code: str,
    ) -> None:
        await policy_emit_correction_skip_event_throttled(
            zone_id=zone_id,
            event_type=event_type,
            event_payload=event_payload,
            reason_code=reason_code,
            zone_state=self._get_zone_state(zone_id),
            correction_skip_event_throttle_seconds=CORRECTION_SKIP_EVENT_THROTTLE_SECONDS,
            utcnow_fn=utcnow,
            create_zone_event_fn=create_zone_event,
            logger=logger,
        )

    @staticmethod
    def _normalize_flag_signature_values(raw_values: Any) -> List[str]:
        return policy_normalize_flag_signature_values(raw_values)

    @classmethod
    def _build_correction_skip_signature(
        cls,
        *,
        event_type: str,
        event_payload: Dict[str, Any],
        reason_code: str,
    ) -> str:
        return policy_build_correction_skip_signature(
            event_type=event_type,
            event_payload=event_payload,
            reason_code=reason_code,
        )

    @staticmethod
    def _resolve_sensor_mode_action(reason_code: str, can_run: bool) -> str:
        return policy_resolve_sensor_mode_action(
            reason_code,
            can_run,
            sensor_mode_policy=SENSOR_MODE_POLICY,
        )

    async def _apply_sensor_mode_policy(
        self,
        *,
        zone_id: int,
        nodes: Dict[str, Dict[str, Any]],
        reason_code: str,
        can_run: bool,
    ) -> None:
        await policy_apply_sensor_mode_policy(
            zone_id=zone_id,
            nodes=nodes,
            reason_code=reason_code,
            can_run=can_run,
            resolve_sensor_mode_action_fn=self._resolve_sensor_mode_action,
            set_sensor_mode_fn=self._set_sensor_mode,
            logger=logger,
        )

    async def _process_correction_controllers(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        telemetry_timestamps: Dict[str, Any],
        correction_flags: Dict[str, Any],
        nodes: Dict[str, Dict[str, Any]],
        capabilities: Dict[str, bool],
        workflow_phase: str,
        water_level_ok: bool,
        bindings: Dict[str, Dict[str, Any]],
        actuators: Dict[str, Dict[str, Any]]
    ) -> None:
        """Обработка контроллеров корректировки pH/EC."""
        await policy_process_correction_controllers(
            zone_id=zone_id,
            targets=targets,
            telemetry=telemetry,
            telemetry_timestamps=telemetry_timestamps,
            correction_flags=correction_flags,
            nodes=nodes,
            capabilities=capabilities,
            workflow_phase=workflow_phase,
            water_level_ok=water_level_ok,
            actuators=actuators,
            ph_controller=self.ph_controller,
            ec_controller=self.ec_controller,
            command_gateway=self.command_gateway,
            build_correction_gating_state_fn=self._build_correction_gating_state,
            emit_correction_skip_event_throttled_fn=self._emit_correction_skip_event_throttled,
            emit_correction_missing_flags_signal_fn=self._emit_correction_missing_flags_signal,
            emit_correction_stale_flags_signal_fn=self._emit_correction_stale_flags_signal,
            apply_sensor_mode_policy_fn=self._apply_sensor_mode_policy,
            resolve_allowed_ec_components_fn=self._resolve_allowed_ec_components,
            emit_controller_circuit_open_signal_fn=self._emit_controller_circuit_open_signal,
            logger=logger,
        )

    def _build_correction_gating_state(
        self,
        *,
        telemetry: Dict[str, Optional[float]],
        telemetry_timestamps: Dict[str, Any],
        correction_flags: Dict[str, Any],
        workflow_phase: str = "idle",
    ) -> Dict[str, Any]:
        return policy_build_correction_gating_state(
            telemetry=telemetry,
            telemetry_timestamps=telemetry_timestamps,
            correction_flags=correction_flags,
            workflow_phase=workflow_phase,
            normalize_workflow_phase_fn=self._normalize_workflow_phase,
            utcnow_fn=utcnow,
            correction_open_phases=WORKFLOW_CORRECTION_OPEN_PHASES,
            required_flag_names=CORRECTION_REQUIRED_FLAG_NAMES,
            flags_max_age_seconds=CORRECTION_FLAGS_MAX_AGE_SECONDS,
            flags_require_timestamps=CORRECTION_FLAGS_REQUIRE_TIMESTAMPS,
            logger=logger,
        )

    @staticmethod
    def _resolve_correction_sensor_nodes(nodes: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        return policy_resolve_correction_sensor_nodes(nodes)

    async def _set_sensor_mode(
        self,
        *,
        zone_id: int,
        nodes: Dict[str, Dict[str, Any]],
        activate: bool,
        reason: str,
    ) -> None:
        await policy_set_sensor_mode(
            zone_id=zone_id,
            nodes=nodes,
            activate=activate,
            reason=reason,
            command_gateway=self.command_gateway,
            correction_sensor_mode_state=self._correction_sensor_mode_state,
            emit_controller_circuit_open_signal_fn=self._emit_controller_circuit_open_signal,
            logger=logger,
            resolve_correction_sensor_nodes_fn=self._resolve_correction_sensor_nodes,
        )
    
    async def _update_zone_health(self, zone_id: int) -> None:
        """Обновление health score зоны."""
        await policy_update_zone_health(
            zone_id=zone_id,
            calculate_zone_health_fn=calculate_zone_health,
            update_zone_health_in_db_fn=update_zone_health_in_db,
        )
    
    async def _check_zone_deletion(self, zone_id: int) -> None:
        """Проверить, не была ли зона удалена, и очистить PID инстансы."""
        from common.db import fetch as db_fetch

        await policy_check_zone_deletion(
            zone_id=zone_id,
            fetch_fn=db_fetch,
            invalidate_cache_fn=invalidate_cache,
            ph_controller=self.ph_controller,
            ec_controller=self.ec_controller,
            logger=logger,
            send_infra_exception_alert_fn=send_infra_exception_alert,
        )
    
    async def _check_pid_config_updates(self, zone_id: int) -> None:
        """Проверить обновления PID конфигов и инвалидировать кеш при необходимости."""
        from common.db import fetch as db_fetch

        await policy_check_pid_config_updates(
            zone_id=zone_id,
            fetch_fn=db_fetch,
            invalidate_cache_fn=invalidate_cache,
            ph_controller=self.ph_controller,
            ec_controller=self.ec_controller,
            logger=logger,
            send_infra_exception_alert_fn=send_infra_exception_alert,
        )
