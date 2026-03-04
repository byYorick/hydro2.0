"""Signal/event methods for ZoneAutomationService."""

import logging
from typing import Any, Dict, Optional

from common.db import create_zone_event
from common.infra_alerts import (
    send_infra_alert,
    send_infra_exception_alert,
    send_infra_resolved_alert,
)
from common.utils.time import utcnow
from services.resilience_contract import INFRA_ZONE_EVENT_WRITE_FAILED
from services.zone_correction_signals import (
    emit_correction_missing_flags_signal as policy_emit_correction_missing_flags_signal,
    resolve_correction_gating_signals as policy_resolve_correction_gating_signals,
    emit_correction_stale_flags_signal as policy_emit_correction_stale_flags_signal,
)
from services.zone_runtime_signals import (
    emit_degraded_mode_signal as policy_emit_degraded_mode_signal,
    emit_zone_data_unavailable_signal as policy_emit_zone_data_unavailable_signal,
    emit_zone_recovered_signal as policy_emit_zone_recovered_signal,
)
from services.zone_skip_signals import (
    emit_backoff_skip_signal as policy_emit_backoff_skip_signal,
    emit_missing_targets_signal as policy_emit_missing_targets_signal,
)

from services.zone_automation_constants import (
    CORRECTION_FLAGS_MISSING_ALERT_THROTTLE_SECONDS,
    CORRECTION_FLAGS_STALE_ALERT_THROTTLE_SECONDS,
    DEGRADED_MODE_THRESHOLD,
    SKIP_REPORT_THROTTLE_SECONDS,
)

logger = logging.getLogger(__name__)


async def create_zone_event_safe(
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
            code=INFRA_ZONE_EVENT_WRITE_FAILED,
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


async def emit_backoff_skip_signal(self, zone_id: int) -> None:
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


async def emit_missing_targets_signal(self, zone_id: int, grow_cycle: Optional[Dict[str, Any]]) -> None:
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


async def emit_correction_missing_flags_signal(
    self,
    zone_id: int,
    gating_state: Dict[str, Any],
    nodes: Dict[str, Dict[str, Any]],
) -> None:
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


async def emit_correction_stale_flags_signal(
    self,
    zone_id: int,
    gating_state: Dict[str, Any],
    nodes: Dict[str, Dict[str, Any]],
) -> None:
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


async def emit_correction_gating_recovered_signal(
    self,
    zone_id: int,
    reason_code: str,
) -> None:
    await policy_resolve_correction_gating_signals(
        zone_id=zone_id,
        reason_code=reason_code,
        zone_state=self._get_zone_state(zone_id),
        send_infra_resolved_alert_fn=send_infra_resolved_alert,
        logger=logger,
    )


async def emit_zone_data_unavailable_signal(self, zone_id: int) -> None:
    state = self._get_zone_state(zone_id)
    await policy_emit_zone_data_unavailable_signal(
        zone_id=zone_id,
        error_streak=int(state.get("error_streak", 0)),
        next_allowed_run_at=state.get("next_allowed_run_at"),
        create_zone_event_safe_fn=self._create_zone_event_safe,
        send_infra_alert_fn=send_infra_alert,
        logger=logger,
    )


async def emit_degraded_mode_signal(self, zone_id: int) -> None:
    await policy_emit_degraded_mode_signal(
        zone_id=zone_id,
        zone_state=self._get_zone_state(zone_id),
        degraded_mode_threshold=DEGRADED_MODE_THRESHOLD,
        create_zone_event_safe_fn=self._create_zone_event_safe,
        send_infra_alert_fn=send_infra_alert,
        logger=logger,
    )


async def emit_zone_recovered_signal(self, zone_id: int, previous_error_streak: int) -> None:
    await policy_emit_zone_recovered_signal(
        zone_id=zone_id,
        previous_error_streak=previous_error_streak,
        zone_state=self._get_zone_state(zone_id),
        create_zone_event_safe_fn=self._create_zone_event_safe,
        send_infra_resolved_alert_fn=send_infra_resolved_alert,
        logger=logger,
    )
