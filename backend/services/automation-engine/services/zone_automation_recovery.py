"""Recovery and required-node gate methods for ZoneAutomationService."""

import logging
from typing import Any, Dict, List

from common.db import fetch
from common.infra_alerts import send_infra_alert, send_infra_resolved_alert
from common.utils.time import utcnow
from infrastructure.node_query_adapter import check_required_nodes_online
from services.resilience_contract import (
    INFRA_ZONE_REQUIRED_NODES_OFFLINE,
    REASON_REQUIRED_NODES_OFFLINE,
    REASON_REQUIRED_NODES_RECOVERED,
)
from services.zone_node_recovery import (
    evaluate_required_nodes_recovery_gate as policy_evaluate_required_nodes_recovery_gate,
)
from services.zone_automation_constants import REQUIRED_NODES_OFFLINE_ALERT_THROTTLE_SECONDS

logger = logging.getLogger(__name__)


async def check_required_nodes_online_safe(
    self,
    zone_id: int,
    required_types: List[str],
) -> Dict[str, Any]:
    try:
        return await check_required_nodes_online(
            fetch_fn=fetch,
            zone_id=zone_id,
            required_types=required_types,
        )
    except Exception:
        logger.warning(
            "Zone %s: required-node online check failed; allowing cycle to continue",
            zone_id,
            exc_info=True,
            extra={"zone_id": zone_id, "required_types": required_types},
        )
        return {
            "required_types": list(required_types or []),
            "online_counts": {},
            "missing_types": [],
        }


async def emit_required_nodes_offline_signal(
    self,
    *,
    zone_id: int,
    required_types: List[str],
    online_counts: Dict[str, Any],
    missing_types: List[str],
    reason_code: str = REASON_REQUIRED_NODES_OFFLINE,
) -> None:
    await self._create_zone_event_safe(
        zone_id=zone_id,
        event_type="ZONE_REQUIRED_NODES_OFFLINE",
        details={
            "required_types": sorted(required_types),
            "online_counts": online_counts,
            "missing_types": sorted(missing_types),
            "reason_code": reason_code,
            "status": "frozen",
        },
        signal_name="zone_required_nodes_offline",
    )
    await send_infra_alert(
        code=INFRA_ZONE_REQUIRED_NODES_OFFLINE,
        alert_type="Required Nodes Offline",
        message=f"Zone {zone_id} required nodes offline: {', '.join(sorted(missing_types))}",
        severity="error",
        zone_id=zone_id,
        service="automation-engine",
        component="zone_node_recovery",
        error_type="RequiredNodesOffline",
        details={
            "required_types": sorted(required_types),
            "online_counts": online_counts,
            "missing_types": sorted(missing_types),
            "reason_code": reason_code,
            "status": "frozen",
        },
    )


async def emit_required_nodes_recovered_signal(
    self,
    *,
    zone_id: int,
    previous_missing_types: List[str],
    required_types: List[str],
    online_counts: Dict[str, Any],
    reason_code: str = REASON_REQUIRED_NODES_RECOVERED,
) -> None:
    normalized_prev_missing = sorted(str(item).strip().lower() for item in previous_missing_types if str(item).strip())
    await self._create_zone_event_safe(
        zone_id=zone_id,
        event_type="ZONE_REQUIRED_NODES_RECOVERED",
        details={
            "previous_missing_types": normalized_prev_missing,
            "required_types": sorted(required_types),
            "online_counts": online_counts,
            "reason_code": reason_code,
            "status": "ready",
        },
        signal_name="zone_required_nodes_recovered",
    )
    await send_infra_resolved_alert(
        code=INFRA_ZONE_REQUIRED_NODES_OFFLINE,
        alert_type="Required Nodes Recovered",
        message=f"Zone {zone_id} required nodes recovered",
        zone_id=zone_id,
        service="automation-engine",
        component="zone_node_recovery",
        details={
            "previous_missing_types": normalized_prev_missing,
            "required_types": sorted(required_types),
            "online_counts": online_counts,
            "reason_code": reason_code,
            "status": "ready",
        },
    )


async def evaluate_required_nodes_recovery_gate(
    self,
    zone_id: int,
    capabilities: Dict[str, Any],
) -> bool:
    return await policy_evaluate_required_nodes_recovery_gate(
        zone_id=zone_id,
        capabilities=capabilities,
        zone_state=self._get_zone_state(zone_id),
        check_required_nodes_online_fn=self._check_required_nodes_online,
        emit_required_nodes_offline_signal_fn=self._emit_required_nodes_offline_signal,
        emit_required_nodes_recovered_signal_fn=self._emit_required_nodes_recovered_signal,
        utcnow_fn=utcnow,
        throttle_seconds=REQUIRED_NODES_OFFLINE_ALERT_THROTTLE_SECONDS,
        logger=logger,
    )

