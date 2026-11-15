"""runtime node resolution: explicit dependencies and invocation data."""

import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from models import TelemetrySampleModel


@dataclass(frozen=True)
class RuntimeNodeResolutionPorts:
    emit_telemetry_anomaly_alert: Callable[..., Any]
    emit_telemetry_anomaly_resolved_alert: Callable[..., Any]
    is_temp_namespace: Callable[..., Any]
    log_warning_throttled: Callable[..., Any]
    node_cache: Callable[..., Any]
    node_unassigned_last_seen: Callable[..., Any]
    node_unassigned_recovery_grace_sec: Callable[..., Any]
    prewarm_stale_node_assignments: Callable[..., Any]
    zone_greenhouse_cache: Callable[..., Any]
    fetch: Callable[..., Any]
    logger: Callable[..., Any]


class RuntimeNodeResolution:
    def __init__(self, ports: RuntimeNodeResolutionPorts) -> None:
        self._ports = ports

    async def resolve_batch_nodes(self, *, samples: List[TelemetrySampleModel]) -> Any:
        node_uid_to_info: dict[
            tuple[str, Optional[str]],
            tuple[int, Optional[int], Optional[int]] | tuple[int, Optional[int]],
        ] = {}
        node_info_source: dict[tuple[str, Optional[str]], str] = {}

        node_gh_pairs = list(set((s.node_uid, s.gh_uid) for s in samples if s.node_uid))

        if node_gh_pairs:
            missing_nodes = []
            for node_uid, gh_uid in node_gh_pairs:
                key = (node_uid, gh_uid)
                if key in self._ports.node_cache():
                    node_uid_to_info[key] = self._ports.node_cache()[key]
                    node_info_source[key] = "cache"
                else:
                    fallback_key = (node_uid, None)
                    if fallback_key in self._ports.node_cache():
                        node_uid_to_info[key] = self._ports.node_cache()[fallback_key]
                        node_info_source[key] = "cache"
                    else:
                        missing_nodes.append((node_uid, gh_uid))

            if missing_nodes:
                nodes_with_gh = [(n, g) for n, g in missing_nodes if g]
                nodes_without_gh = [(n, g) for n, g in missing_nodes if not g]

                if nodes_with_gh:
                    node_uids = [n for n, _ in nodes_with_gh]
                    gh_uids = [g for _, g in nodes_with_gh]
                    node_rows = await self._ports.fetch(
                        """
                        SELECT n.id, n.uid, n.zone_id, n.pending_zone_id, g.uid as gh_uid
                        FROM nodes n
                        LEFT JOIN zones z ON z.id = n.zone_id
                        LEFT JOIN greenhouses g ON g.id = z.greenhouse_id
                        WHERE (n.uid, COALESCE(g.uid, '')) IN (
                            SELECT unnest($1::text[]), unnest($2::text[])
                        )
                        """,
                        node_uids,
                        gh_uids,
                    )

                    for node in node_rows:
                        node_uid = node.get("uid")
                        node_id = node.get("id")
                        if not node_uid or node_id is None:
                            continue
                        gh_uid = node.get("gh_uid")
                        zone_id = node.get("zone_id")
                        pending_zone_id = node.get("pending_zone_id")
                        key = (node_uid, gh_uid)
                        node_uid_to_info[key] = (node_id, zone_id, pending_zone_id)
                        self._ports.node_cache()[key] = (node_id, zone_id, pending_zone_id)
                        node_info_source[key] = "db"

                    unresolved_nodes_with_gh = [
                        (node_uid, gh_uid)
                        for node_uid, gh_uid in nodes_with_gh
                        if (node_uid, gh_uid) not in node_uid_to_info
                    ]
                    if unresolved_nodes_with_gh:
                        fallback_node_uids = sorted({node_uid for node_uid, _ in unresolved_nodes_with_gh})
                        fallback_rows = await self._ports.fetch(
                            """
                            SELECT id, uid, zone_id, pending_zone_id
                            FROM nodes
                            WHERE uid = ANY($1)
                            """,
                            fallback_node_uids,
                        )

                        for node in fallback_rows:
                            node_uid = node.get("uid")
                            node_id = node.get("id")
                            if not node_uid or node_id is None:
                                continue
                            zone_id = node.get("zone_id")
                            pending_zone_id = node.get("pending_zone_id")
                            key = (node_uid, None)
                            node_uid_to_info[key] = (node_id, zone_id, pending_zone_id)
                            self._ports.node_cache()[key] = (node_id, zone_id, pending_zone_id)
                            node_info_source[key] = "db"

                        for node_uid, gh_uid in unresolved_nodes_with_gh:
                            fallback_key = (node_uid, None)
                            fallback_info = node_uid_to_info.get(fallback_key)
                            if fallback_info is not None:
                                node_uid_to_info[(node_uid, gh_uid)] = fallback_info
                                self._ports.node_cache()[(node_uid, gh_uid)] = fallback_info
                                node_info_source[(node_uid, gh_uid)] = node_info_source.get(
                                    fallback_key,
                                    "db",
                                )

                if nodes_without_gh:
                    node_uids = [n for n, _ in nodes_without_gh]
                    node_rows = await self._ports.fetch(
                        """
                        SELECT id, uid, zone_id, pending_zone_id
                        FROM nodes
                        WHERE uid = ANY($1)
                        """,
                        node_uids,
                    )

                    for node in node_rows:
                        node_uid = node.get("uid")
                        node_id = node.get("id")
                        if not node_uid or node_id is None:
                            continue
                        zone_id = node.get("zone_id")
                        pending_zone_id = node.get("pending_zone_id")
                        key = (node_uid, None)
                        node_uid_to_info[key] = (node_id, zone_id, pending_zone_id)
                        self._ports.node_cache()[key] = (node_id, zone_id, pending_zone_id)
                        node_info_source[key] = "db"

            for node_uid, gh_uid in node_gh_pairs:
                if (node_uid, gh_uid) not in node_uid_to_info:
                    if (node_uid, None) not in node_uid_to_info:
                        if not gh_uid:
                            self._ports.logger().warning(
                                "gh_uid not provided for node_uid=%s, using simple node_id resolution "
                                "(may cause conflicts in multi-greenhouse setup)",
                                node_uid,
                                extra={"node_uid": node_uid},
                            )
                        extra = {"node_uid": node_uid, "gh_uid": gh_uid}
                        if self._ports.is_temp_namespace(gh_uid, None):
                            self._ports.logger().debug(
                                "Node not found during temp namespace telemetry bootstrap: node_uid=%s, gh_uid=%s",
                                node_uid,
                                gh_uid,
                                extra=extra,
                            )
                            continue
                        self._ports.log_warning_throttled(
                            key=("node_not_found", gh_uid or "-", node_uid, "-"),
                            message=f"Node not found: node_uid={node_uid}, gh_uid={gh_uid}",
                            extra=extra,
                        )
                        await self._ports.emit_telemetry_anomaly_alert(
                            code="infra_telemetry_node_not_found",
                            message="Telemetry received for unknown node_uid",
                            gh_uid=gh_uid,
                            node_uid=node_uid,
                            details={"missing_entity": "node"},
                        )

        await self._ports.prewarm_stale_node_assignments(node_uid_to_info, node_gh_pairs)
        return node_uid_to_info, node_info_source

    async def recover_batch_assignments(
        self,
        *,
        node_unassigned_detected_in_batch: Any,
        node_unassigned_recovery_candidates: Any,
        zone_ids_for_greenhouse: Any,
    ) -> None:
        for (
            zone_id,
            node_uid,
        ), recovery_sample in node_unassigned_recovery_candidates.items():
            recovery_key = (zone_id, node_uid)
            if recovery_key in node_unassigned_detected_in_batch:
                continue

            if self._ports.node_unassigned_recovery_grace_sec() > 0:
                last_unassigned_seen_at = self._ports.node_unassigned_last_seen().get(recovery_key)
                if (
                    last_unassigned_seen_at
                    and (time.time() - last_unassigned_seen_at) < self._ports.node_unassigned_recovery_grace_sec()
                ):
                    continue

            await self._ports.emit_telemetry_anomaly_resolved_alert(
                code="infra_telemetry_node_unassigned",
                message="Telemetry processing recovered: node is assigned to zone",
                zone_id=zone_id,
                gh_uid=recovery_sample.gh_uid,
                zone_uid=recovery_sample.zone_uid,
                node_uid=recovery_sample.node_uid,
                channel=recovery_sample.channel,
                metric_type=recovery_sample.metric_type,
            )
            self._ports.node_unassigned_last_seen().pop(recovery_key, None)

        missing_zone_ids = [
            zone_id for zone_id in zone_ids_for_greenhouse if zone_id not in self._ports.zone_greenhouse_cache()
        ]
        if missing_zone_ids:
            zone_rows = await self._ports.fetch(
                """
                SELECT id, greenhouse_id
                FROM zones
                WHERE id = ANY($1)
                """,
                missing_zone_ids,
            )
            for zone in zone_rows:
                zone_id = zone.get("id")
                greenhouse_id = zone.get("greenhouse_id")
                if zone_id is not None and greenhouse_id is not None:
                    self._ports.zone_greenhouse_cache()[zone_id] = greenhouse_id
