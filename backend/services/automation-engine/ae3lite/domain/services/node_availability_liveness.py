"""node availability liveness: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ae3lite.domain.errors import ErrorCodes
from ae3lite.domain.services.node_availability_records import OfflineFailure


@dataclass(frozen=True)
class NodeAvailabilityLivenessPorts:
    format_offline_nodes_message: Callable[..., Any]
    liveness_is_unreachable: Callable[..., Any]
    node_persistent_dead_sec: Callable[..., Any]
    offline_failure_from_liveness: Callable[..., Any]


class NodeAvailabilityLiveness:
    def __init__(self, ports: NodeAvailabilityLivenessPorts) -> None:
        self._ports = ports

    def liveness_is_unreachable(self, liveness: Mapping[str, Any] | None, *, heartbeat_age_limit_sec: float) -> bool:
        if not isinstance(liveness, Mapping):
            return False
        if liveness.get("found") is not True:
            return False
        status = str(liveness.get("status") or "").strip().lower()
        if status == "offline":
            return True
        heartbeat_age = liveness.get("heartbeat_age_sec")
        if heartbeat_age is not None and float(heartbeat_age) > float(heartbeat_age_limit_sec):
            return True
        return False

    def offline_failure_for_node_uid(
        self, *, zone_id: int, node_uid: str, diagnostics: Mapping[str, Any]
    ) -> OfflineFailure | None:
        uid = str(node_uid or "").strip()
        if not uid:
            return None
        zone_nodes = diagnostics.get("zone_nodes")
        if not isinstance(zone_nodes, list):
            return None
        for node in zone_nodes:
            if not isinstance(node, Mapping):
                continue
            if str(node.get("uid") or "").strip() != uid:
                continue
            status = str(node.get("status") or "").strip().lower()
            if status == "online":
                return None
            return OfflineFailure(
                code=(
                    ErrorCodes.AE3_SNAPSHOT_REQUIRED_NODE_PERSISTENTLY_OFFLINE
                    if uid in set(diagnostics.get("persistently_offline_uids") or [])
                    else ErrorCodes.AE3_REQUIRED_NODE_OFFLINE
                ),
                message=self._ports.format_offline_nodes_message(offline_nodes=[dict(node)]),
                details={
                    "zone_id": zone_id,
                    "node_uid": uid,
                    "offline_required_nodes": [dict(node)],
                    **dict(diagnostics),
                },
            )
        return None

    async def offline_failure_for_node_liveness(
        self, *, zone_id: int, node_uid: str, runtime_monitor: Any, heartbeat_age_limit_sec: float
    ) -> OfflineFailure | None:
        read_node_liveness = getattr(runtime_monitor, "read_node_liveness", None)
        if not callable(read_node_liveness):
            return None
        uid = str(node_uid or "").strip()
        if not uid:
            return None
        liveness = await read_node_liveness(node_uid=uid)
        if not isinstance(liveness, Mapping) or not self._ports.liveness_is_unreachable(
            liveness,
            heartbeat_age_limit_sec=heartbeat_age_limit_sec,
        ):
            return None
        return self._ports.offline_failure_from_liveness(zone_id=zone_id, node_uid=uid, liveness=liveness)

    def offline_failure_from_liveness(
        self, *, zone_id: int, node_uid: str, liveness: Mapping[str, Any]
    ) -> OfflineFailure:
        status = str(liveness.get("status") or "offline").strip().lower() or "offline"
        heartbeat_age = liveness.get("heartbeat_age_sec")
        last_seen_age = liveness.get("last_seen_age_sec")
        age = last_seen_age if last_seen_age is not None else heartbeat_age
        node = {
            "uid": node_uid,
            "type": str(liveness.get("node_type") or "irrig").strip().lower() or "irrig",
            "status": status,
            "last_seen_age_sec": age,
        }
        persistent_threshold = self._ports.node_persistent_dead_sec()
        code = ErrorCodes.AE3_REQUIRED_NODE_OFFLINE
        if age is not None and int(age) >= persistent_threshold:
            code = ErrorCodes.AE3_SNAPSHOT_REQUIRED_NODE_PERSISTENTLY_OFFLINE
        message = self._ports.format_offline_nodes_message(offline_nodes=[node])
        return OfflineFailure(
            code=code,
            message=message,
            details={
                "zone_id": zone_id,
                "node_uid": node_uid,
                "node_status": status,
                "heartbeat_age_sec": heartbeat_age,
                "last_seen_age_sec": last_seen_age,
                "offline_required_nodes": [node],
            },
        )
