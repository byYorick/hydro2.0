"""runtime normalization: explicit dependencies and invocation data."""

import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from models import TelemetrySampleModel

from common.redis_queue import QueueEntry


@dataclass(frozen=True)
class RuntimeNormalizationPorts:
    telemetry_dropped: Callable[..., Any]
    emit_telemetry_anomaly_alert: Callable[..., Any]
    is_temp_namespace: Callable[..., Any]
    log_warning_throttled: Callable[..., Any]
    node_cache: Callable[..., Any]
    node_unassigned_last_seen: Callable[..., Any]
    parse_node_info: Callable[..., Any]
    create_zone_event: Callable[..., Any]
    fetch: Callable[..., Any]
    logger: Callable[..., Any]
    timezone: Callable[..., Any]
    utcnow: Callable[..., Any]


class RuntimeNormalization:
    def __init__(self, ports: RuntimeNormalizationPorts) -> None:
        self._ports = ports

    async def normalize_batch_samples(
        self,
        *,
        entries: Optional[List[QueueEntry]],
        max_age_minutes: float,
        max_age_seconds: float,
        node_info_source: Any,
        node_uid_to_info: Any,
        samples: List[TelemetrySampleModel],
        zone_uid_to_id: Any,
    ) -> Any:
        resolved_samples: list[dict] = []
        node_unassigned_recovery_candidates: dict[tuple[int, str], TelemetrySampleModel] = {}
        node_unassigned_detected_in_batch: set[tuple[int, str]] = set()
        node_assignment_refresh_attempted: set[tuple[str, Optional[str]]] = set()
        zone_ids_for_greenhouse: set[int] = set()

        for idx, sample in enumerate(samples):
            entry = entries[idx] if entries is not None else None
            zone_id = sample.zone_id if sample.zone_id is not None else None
            if zone_id is None and sample.zone_uid:
                zone_id = zone_uid_to_id.get((sample.zone_uid, sample.gh_uid))
                if zone_id is None and sample.gh_uid:
                    zone_id = zone_uid_to_id.get((sample.zone_uid, None))

            node_id = None
            node_zone_id = None
            node_pending_zone_id = None
            if sample.node_uid:
                primary_key = (sample.node_uid, sample.gh_uid)
                node_info = node_uid_to_info.get(primary_key)
                if node_info is None and sample.gh_uid:
                    fallback_key = (sample.node_uid, None)
                    node_info = node_uid_to_info.get(fallback_key)

                if node_info:
                    node_id, node_zone_id, node_pending_zone_id = self._ports.parse_node_info(node_info)

            if zone_id is None:
                if not sample.zone_uid:
                    self._ports.logger().warning(
                        "Skipping sample: zone_uid missing",
                        extra={
                            "zone_uid": sample.zone_uid,
                            "node_uid": sample.node_uid,
                            "metric_type": sample.metric_type,
                        },
                    )
                else:
                    extra = {
                        "zone_uid": sample.zone_uid,
                        "node_uid": sample.node_uid,
                        "metric_type": sample.metric_type,
                        "zone_uid_format_valid": sample.zone_uid.startswith("zn-") if sample.zone_uid else False,
                    }
                    if self._ports.is_temp_namespace(sample.gh_uid, sample.zone_uid):
                        self._ports.logger().debug(
                            "Skipping sample: zone_id not found for temp namespace zone_uid",
                            extra=extra,
                        )
                    else:
                        self._ports.log_warning_throttled(
                            key=(
                                "zone_id_not_found",
                                sample.gh_uid or "-",
                                sample.zone_uid or "-",
                                sample.metric_type or "-",
                            ),
                            message="Skipping sample: zone_id not found for zone_uid",
                            extra=extra,
                        )
                self._ports.telemetry_dropped().labels(reason="zone_id_not_found").inc()
                continue

            if node_id is None:
                extra = {
                    "node_uid": sample.node_uid,
                    "zone_uid": sample.zone_uid,
                    "gh_uid": sample.gh_uid,
                    "metric_type": sample.metric_type,
                }
                if self._ports.is_temp_namespace(sample.gh_uid, sample.zone_uid):
                    self._ports.logger().debug(
                        "Skipping sample: node_id not found during temp namespace bootstrap",
                        extra=extra,
                    )
                else:
                    self._ports.log_warning_throttled(
                        key=(
                            "node_id_not_found",
                            sample.gh_uid or "-",
                            sample.node_uid or "-",
                            sample.metric_type or "-",
                        ),
                        message="Skipping sample: node_id not found for node_uid",
                        extra=extra,
                    )
                self._ports.telemetry_dropped().labels(reason="node_id_not_found").inc()
                await self._ports.emit_telemetry_anomaly_alert(
                    code="infra_telemetry_sample_dropped_node_not_found",
                    message="Telemetry sample dropped: node_id not found for node_uid",
                    zone_id=zone_id,
                    gh_uid=sample.gh_uid,
                    zone_uid=sample.zone_uid,
                    node_uid=sample.node_uid,
                    channel=sample.channel,
                    metric_type=sample.metric_type,
                )
                continue

            if sample.node_uid and zone_id is not None and node_zone_id is None and node_pending_zone_id is None:
                refresh_key = (sample.node_uid, sample.gh_uid)
                if refresh_key not in node_assignment_refresh_attempted:
                    node_assignment_refresh_attempted.add(refresh_key)
                    try:
                        refreshed_rows = await self._ports.fetch(
                            """
                            SELECT id, zone_id, pending_zone_id
                            FROM nodes
                            WHERE uid = $1
                            LIMIT 1
                            """,
                            sample.node_uid,
                        )
                    except Exception:
                        refreshed_rows = []
                        self._ports.logger().warning(
                            "Failed to refresh node assignment from DB, using cached node info",
                            extra={
                                "node_uid": sample.node_uid,
                                "gh_uid": sample.gh_uid,
                                "zone_id": zone_id,
                            },
                            exc_info=True,
                        )

                    if refreshed_rows:
                        refreshed_node = refreshed_rows[0]
                        refreshed_info = (
                            refreshed_node.get("id"),
                            refreshed_node.get("zone_id"),
                            refreshed_node.get("pending_zone_id"),
                        )
                        for cache_key in ((sample.node_uid, sample.gh_uid), (sample.node_uid, None)):
                            node_uid_to_info[cache_key] = refreshed_info
                            self._ports.node_cache()[cache_key] = refreshed_info
                            node_info_source[cache_key] = "db_refresh"

                        node_id, node_zone_id, node_pending_zone_id = self._ports.parse_node_info(refreshed_info)

            if node_zone_id is None:
                if node_pending_zone_id is not None and node_pending_zone_id == zone_id:
                    self._ports.logger().info(
                        "Skipping sample: node assignment pending, telemetry ignored until zone binding is confirmed",
                        extra={
                            "node_uid": sample.node_uid,
                            "node_id": node_id,
                            "pending_zone_id": node_pending_zone_id,
                            "requested_zone_id": zone_id,
                            "zone_uid": sample.zone_uid,
                            "gh_uid": sample.gh_uid,
                            "metric_type": sample.metric_type,
                        },
                    )
                    self._ports.telemetry_dropped().labels(reason="node_assignment_pending").inc()
                    continue
                if sample.node_uid:
                    key = (zone_id, sample.node_uid)
                    node_unassigned_detected_in_batch.add(key)
                    self._ports.node_unassigned_last_seen()[key] = time.time()
                self._ports.log_warning_throttled(
                    key=(
                        "node_unassigned",
                        sample.gh_uid or "-",
                        sample.node_uid or "-",
                        str(zone_id),
                    ),
                    message="Skipping sample: node is not assigned to any zone",
                    extra={
                        "node_uid": sample.node_uid,
                        "node_id": node_id,
                        "zone_uid": sample.zone_uid,
                        "gh_uid": sample.gh_uid,
                        "metric_type": sample.metric_type,
                        "pending_zone_id": node_pending_zone_id,
                    },
                )
                self._ports.telemetry_dropped().labels(reason="node_unassigned").inc()
                await self._ports.emit_telemetry_anomaly_alert(
                    code="infra_telemetry_node_unassigned",
                    message="Telemetry sample dropped: node is not assigned to any zone",
                    zone_id=zone_id,
                    gh_uid=sample.gh_uid,
                    zone_uid=sample.zone_uid,
                    node_uid=sample.node_uid,
                    channel=None,
                    metric_type=None,
                    details={
                        "node_id": node_id,
                        "pending_zone_id": node_pending_zone_id,
                        "sample_channel": sample.channel,
                        "sample_metric_type": sample.metric_type,
                    },
                )
                continue

            if (
                node_zone_id is not None
                and node_zone_id != zone_id
                and node_pending_zone_id is not None
                and node_pending_zone_id == zone_id
            ):
                self._ports.logger().info(
                    "Skipping sample: node rebind pending, telemetry ignored until old zone assignment is finalized",
                    extra={
                        "node_uid": sample.node_uid,
                        "node_id": node_id,
                        "node_zone_id": node_zone_id,
                        "pending_zone_id": node_pending_zone_id,
                        "requested_zone_id": zone_id,
                        "zone_uid": sample.zone_uid,
                        "gh_uid": sample.gh_uid,
                        "metric_type": sample.metric_type,
                    },
                )
                self._ports.telemetry_dropped().labels(reason="node_rebind_pending").inc()
                continue

            if node_zone_id != zone_id:
                self._ports.logger().warning(
                    "Security: node_uid does not belong to zone_id, dropping sample",
                    extra={
                        "node_uid": sample.node_uid,
                        "node_id": node_id,
                        "node_zone_id": node_zone_id,
                        "requested_zone_id": zone_id,
                        "zone_uid": sample.zone_uid,
                        "gh_uid": sample.gh_uid,
                        "metric_type": sample.metric_type,
                    },
                )
                self._ports.telemetry_dropped().labels(reason="node_zone_mismatch").inc()
                await self._ports.emit_telemetry_anomaly_alert(
                    code="infra_telemetry_node_zone_mismatch",
                    message="Telemetry sample dropped: node-zone mismatch detected",
                    zone_id=zone_id,
                    gh_uid=sample.gh_uid,
                    zone_uid=sample.zone_uid,
                    node_uid=sample.node_uid,
                    channel=sample.channel,
                    metric_type=sample.metric_type,
                    details={
                        "node_id": node_id,
                        "node_zone_id": node_zone_id,
                        "requested_zone_id": zone_id,
                    },
                )
                continue

            sample_ts = sample.ts
            if sample_ts:
                if getattr(sample_ts, "tzinfo", None):
                    sample_ts = sample_ts.astimezone(self._ports.timezone.utc)
                else:
                    sample_ts = sample_ts.replace(tzinfo=self._ports.timezone.utc)
                age_seconds = (self._ports.utcnow() - sample_ts).total_seconds()
                if age_seconds > max_age_seconds:
                    try:
                        await self._ports.create_zone_event(
                            zone_id,
                            "TELEMETRY_STALE",
                            {
                                "metric_type": sample.metric_type,
                                "age_minutes": age_seconds / 60,
                                "max_age_minutes": max_age_minutes,
                                "node_uid": sample.node_uid,
                                "channel": sample.channel,
                            },
                        )
                    except Exception as e:
                        self._ports.logger().warning(
                            f"Failed to create TELEMETRY_STALE event: {e}",
                            exc_info=True,
                        )

            resolved_samples.append(
                {
                    "sample": sample,
                    "zone_id": zone_id,
                    "node_id": node_id,
                    "entry": entry,
                }
            )
            if sample.node_uid:
                node_unassigned_recovery_candidates[(zone_id, sample.node_uid)] = sample
            zone_ids_for_greenhouse.add(zone_id)
        return (
            resolved_samples,
            node_unassigned_recovery_candidates,
            node_unassigned_detected_in_batch,
            zone_ids_for_greenhouse,
        )
