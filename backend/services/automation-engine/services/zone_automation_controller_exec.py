"""Controller execution methods for ZoneAutomationService."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from common.db import create_zone_event
from common.infra_alerts import send_infra_alert, send_infra_exception_alert, send_infra_resolved_alert
from common.simulation_clock import SimulationClock
from common.simulation_events import record_simulation_event
from common.utils.time import utcnow
from common.pump_safety import can_run_pump
from climate_controller import check_and_control_climate
from irrigation_controller import check_and_control_irrigation, check_and_control_recirculation
from light_controller import check_and_control_lighting
from services.zone_controller_execution import (
    append_correlation_id as policy_append_correlation_id,
    check_phase_transitions as policy_check_phase_transitions,
    publish_controller_action_with_event_integrity as policy_publish_controller_action_with_event_integrity,
)
from services.zone_controller_guardrails import (
    emit_controller_circuit_open_signal as policy_emit_controller_circuit_open_signal,
    emit_controller_cooldown_skip_signal as policy_emit_controller_cooldown_skip_signal,
    is_controller_in_cooldown as policy_is_controller_in_cooldown,
    record_controller_failure as policy_record_controller_failure,
    safe_process_controller as policy_safe_process_controller,
)
from services.zone_controller_processors import (
    process_climate_controller as policy_process_climate_controller,
    process_irrigation_controller as policy_process_irrigation_controller,
    process_light_controller as policy_process_light_controller,
    process_recirculation_controller as policy_process_recirculation_controller,
)
from services.zone_automation_constants import (
    CONTROLLER_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS,
    CONTROLLER_COOLDOWN_SECONDS,
    COOLDOWN_SKIP_REPORT_THROTTLE_SECONDS,
)

logger = logging.getLogger(__name__)


async def emit_controller_circuit_open_signal(
    self,
    zone_id: int,
    controller_name: str,
    *,
    channel: Optional[str] = None,
    cmd: Optional[str] = None,
) -> None:
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


def is_controller_in_cooldown(self, zone_id: int, controller_name: str) -> bool:
    return policy_is_controller_in_cooldown(
        zone_id=zone_id,
        controller_name=controller_name,
        controller_failures=self._controller_failures,
        cooldown_seconds=CONTROLLER_COOLDOWN_SECONDS,
        utcnow_fn=utcnow,
    )


def record_controller_failure(self, zone_id: int, controller_name: str) -> None:
    policy_record_controller_failure(
        zone_id=zone_id,
        controller_name=controller_name,
        controller_failures=self._controller_failures,
        controller_cooldown_reported_at=self._controller_cooldown_reported_at,
        utcnow_fn=utcnow,
    )


async def safe_process_controller(
    self,
    controller_name: str,
    controller_coro,
    zone_id: int,
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


async def emit_controller_cooldown_skip_signal(self, zone_id: int, controller_name: str) -> None:
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


async def check_phase_transitions(self, zone_id: int, sim_clock: Optional[SimulationClock] = None) -> None:
    await policy_check_phase_transitions(
        zone_id=zone_id,
        sim_clock=sim_clock,
        grow_cycle_repo=self.grow_cycle_repo,
        record_simulation_event_fn=record_simulation_event,
        emit_controller_circuit_open_signal_fn=self._emit_controller_circuit_open_signal,
        logger=logger,
    )


def append_correlation_id(details: Dict[str, Any], correlation_id: Optional[str]) -> Dict[str, Any]:
    return policy_append_correlation_id(details, correlation_id)


async def publish_controller_action_with_event_integrity(
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


async def process_light_controller(
    self,
    zone_id: int,
    targets: Dict[str, Any],
    capabilities: Dict[str, bool],
    bindings: Dict[str, Dict[str, Any]],
    current_time: datetime,
) -> None:
    await policy_process_light_controller(
        zone_id=zone_id,
        targets=targets,
        capabilities=capabilities,
        bindings=bindings,
        current_time=current_time,
        check_and_control_lighting_fn=check_and_control_lighting,
        publish_controller_action_with_event_integrity_fn=self._publish_controller_action_with_event_integrity,
    )


async def process_climate_controller(
    self,
    zone_id: int,
    targets: Dict[str, Any],
    telemetry: Dict[str, Optional[float]],
    capabilities: Dict[str, bool],
    bindings: Dict[str, Dict[str, Any]],
) -> None:
    await policy_process_climate_controller(
        zone_id=zone_id,
        targets=targets,
        telemetry=telemetry,
        capabilities=capabilities,
        bindings=bindings,
        check_and_control_climate_fn=check_and_control_climate,
        publish_controller_action_with_event_integrity_fn=self._publish_controller_action_with_event_integrity,
    )


async def process_irrigation_controller(
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
    _ = water_level_ok
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
        send_infra_resolved_alert_fn=send_infra_resolved_alert,
        publish_controller_action_with_event_integrity_fn=self._publish_controller_action_with_event_integrity,
        logger=logger,
    )


async def process_recirculation_controller(
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
    _ = water_level_ok
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
