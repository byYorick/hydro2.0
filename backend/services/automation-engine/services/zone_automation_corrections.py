"""Correction/sensor-mode methods for ZoneAutomationService."""

import logging
from typing import Any, Dict, List, Optional

from common.db import create_zone_event
from common.infra_alerts import send_infra_alert, send_infra_exception_alert
from common.utils.time import utcnow
from health_monitor import calculate_zone_health, update_zone_health_in_db
from services.pid_config_service import invalidate_cache
from services.zone_correction_gating import (
    build_correction_gating_state as policy_build_correction_gating_state,
)
from services.zone_correction_orchestrator import (
    process_correction_controllers as policy_process_correction_controllers,
)
from services.zone_correction_skip_events import (
    build_correction_skip_signature as policy_build_correction_skip_signature,
    emit_correction_skip_event_throttled as policy_emit_correction_skip_event_throttled,
    normalize_flag_signature_values as policy_normalize_flag_signature_values,
)
from services.zone_sensor_mode_orchestrator import (
    apply_sensor_mode_policy as policy_apply_sensor_mode_policy,
    resolve_correction_sensor_nodes as policy_resolve_correction_sensor_nodes,
    resolve_sensor_mode_action as policy_resolve_sensor_mode_action,
    set_sensor_mode as policy_set_sensor_mode,
)
from services.zone_housekeeping import (
    check_pid_config_updates as policy_check_pid_config_updates,
    check_zone_deletion as policy_check_zone_deletion,
    update_zone_health as policy_update_zone_health,
)

from services.zone_automation_constants import (
    CORRECTION_FLAGS_MAX_AGE_SECONDS,
    CORRECTION_FLAGS_REQUIRE_TIMESTAMPS,
    CORRECTION_REQUIRED_FLAG_NAMES,
    CORRECTION_SKIP_EVENT_THROTTLE_SECONDS,
    SENSOR_MODE_POLICY,
    WORKFLOW_CORRECTION_OPEN_PHASES,
)

logger = logging.getLogger(__name__)


async def emit_correction_skip_event_throttled(
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


def normalize_flag_signature_values(raw_values: Any) -> List[str]:
    return policy_normalize_flag_signature_values(raw_values)


def build_correction_skip_signature(
    cls,
    *,
    event_type: str,
    event_payload: Dict[str, Any],
    reason_code: str,
) -> str:
    _ = cls
    return policy_build_correction_skip_signature(
        event_type=event_type,
        event_payload=event_payload,
        reason_code=reason_code,
    )


def resolve_sensor_mode_action(reason_code: str, can_run: bool) -> str:
    return policy_resolve_sensor_mode_action(
        reason_code,
        can_run,
        sensor_mode_policy=SENSOR_MODE_POLICY,
    )


async def apply_sensor_mode_policy(
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


async def process_correction_controllers(
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
    actuators: Dict[str, Dict[str, Any]],
) -> None:
    _ = bindings
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
        resolve_correction_gating_signals_fn=self._emit_correction_gating_recovered_signal,
        apply_sensor_mode_policy_fn=self._apply_sensor_mode_policy,
        resolve_allowed_ec_components_fn=self._resolve_allowed_ec_components,
        emit_controller_circuit_open_signal_fn=self._emit_controller_circuit_open_signal,
        logger=logger,
    )


def build_correction_gating_state(
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


def resolve_correction_sensor_nodes(nodes: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    return policy_resolve_correction_sensor_nodes(nodes)


async def set_sensor_mode(
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


async def update_zone_health(self, zone_id: int) -> None:
    await policy_update_zone_health(
        zone_id=zone_id,
        calculate_zone_health_fn=calculate_zone_health,
        update_zone_health_in_db_fn=update_zone_health_in_db,
    )


async def check_zone_deletion(self, zone_id: int) -> None:
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


async def check_pid_config_updates(self, zone_id: int) -> None:
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
