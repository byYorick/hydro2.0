"""node availability command transport: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ae3lite.domain.errors import ErrorCodes
from ae3lite.domain.services.node_availability_records import OfflineFailure


@dataclass(frozen=True)
class NodeAvailabilityCommandTransportPorts:
    irr_command_transport_codes: Callable[..., Any]
    node_transport_error_codes: Callable[..., Any]


class NodeAvailabilityCommandTransport:
    def __init__(self, ports: NodeAvailabilityCommandTransportPorts) -> None:
        self._ports = ports

    def should_remap_error_for_node_check(self, error_code: str) -> bool:
        normalized = str(error_code or "").strip().lower()
        if normalized in self._ports.node_transport_error_codes():
            return True
        if normalized.endswith("_unavailable") or normalized.endswith("_stale"):
            return True
        if "probe_exhausted" in normalized or "probe_streak" in normalized:
            return True
        return False

    def extract_irrig_node_uid_from_actuators(self, actuators: Any) -> str | None:
        for actuator in actuators or ():
            node_type = str(getattr(actuator, "node_type", "") or "").strip().lower()
            if node_type != "irrig":
                continue
            uid = str(getattr(actuator, "node_uid", "") or "").strip()
            if uid:
                return uid
        return None

    def offline_failure_for_command_transport(
        self, *, zone_id: int, node_uid: str, error_code: str, diagnostics: Mapping[str, Any]
    ) -> OfflineFailure | None:
        """Fail-closed, когда transport-команда к ноде не проходит (в т.ч. stale-online)."""
        uid = str(node_uid or "").strip()
        if not uid:
            return None
        normalized = str(error_code or "").strip().lower()
        if normalized not in {str(code).strip().lower() for code in self._ports.irr_command_transport_codes()}:
            return None

        node_type = "irrig"
        node_status = "unknown"
        last_seen_age_sec: int | None = None
        zone_nodes = diagnostics.get("zone_nodes")
        if isinstance(zone_nodes, list):
            for node in zone_nodes:
                if not isinstance(node, Mapping):
                    continue
                if str(node.get("uid") or "").strip() != uid:
                    continue
                node_type = str(node.get("type") or node_type).strip().lower() or node_type
                node_status = str(node.get("status") or node_status).strip().lower() or node_status
                try:
                    last_seen_age_sec = (
                        int(node.get("last_seen_age_sec")) if node.get("last_seen_age_sec") is not None else None
                    )
                except (TypeError, ValueError):
                    last_seen_age_sec = None
                break

        # Transport/probe races with a freshly-online node are usually stage timing
        # (short fill timeout, concurrent cleanup, delayed irr snapshot), not true offline.
        # Keep the original error so probe-backoff / stage handlers can retry.
        _fresh_online_skip_codes = frozenset(
            {
                "ae3_command_poll_deadline_exceeded",
                "irr_state_unavailable",
                "irr_state_stale",
            }
        )
        if (
            normalized in _fresh_online_skip_codes
            and node_status == "online"
            and (last_seen_age_sec is None or last_seen_age_sec < 60)
        ):
            return None

        offline_node = {
            "uid": uid,
            "type": node_type,
            "status": node_status,
            "last_seen_age_sec": last_seen_age_sec,
        }
        return OfflineFailure(
            code=ErrorCodes.AE3_REQUIRED_NODE_OFFLINE,
            message=(
                f"Узел {uid} ({node_type}) не отвечает на команды — возможна потеря связи. "
                "Проверьте питание, Wi‑Fi и MQTT."
            ),
            details={
                "zone_id": zone_id,
                "node_uid": uid,
                "node_status": node_status,
                "transport_error_code": normalized,
                "offline_required_nodes": [offline_node],
                **dict(diagnostics),
            },
        )
