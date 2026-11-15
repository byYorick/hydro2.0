"""runtime zone resolution: explicit dependencies and invocation data."""

from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from models import TelemetrySampleModel


@dataclass(frozen=True)
class RuntimeZoneResolutionPorts:
    emit_telemetry_anomaly_alert: Callable[..., Any]
    is_temp_namespace: Callable[..., Any]
    log_warning_throttled: Callable[..., Any]
    zone_cache: Callable[..., Any]
    fetch: Callable[..., Any]
    logger: Callable[..., Any]


class RuntimeZoneResolution:
    def __init__(self, ports: RuntimeZoneResolutionPorts) -> None:
        self._ports = ports

    async def resolve_batch_zones(self, *, samples: List[TelemetrySampleModel]) -> Any:
        zone_uid_to_id: dict[tuple[str, Optional[str]], int] = {}

        zone_gh_pairs = list(set((sample.zone_uid, sample.gh_uid) for sample in samples if sample.zone_uid))

        if zone_gh_pairs:
            missing_zones = []
            for zone_uid, gh_uid in zone_gh_pairs:
                key = (zone_uid, gh_uid)
                if key in self._ports.zone_cache():
                    zone_uid_to_id[key] = self._ports.zone_cache()[key]
                else:
                    fallback_key = (zone_uid, None)
                    if fallback_key in self._ports.zone_cache():
                        zone_uid_to_id[key] = self._ports.zone_cache()[fallback_key]
                    else:
                        missing_zones.append((zone_uid, gh_uid))

            if missing_zones:
                zones_with_gh = [(z, g) for z, g in missing_zones if g]
                zones_without_gh = [(z, g) for z, g in missing_zones if not g]

                if zones_with_gh:
                    zone_uids = [z for z, _ in zones_with_gh]
                    gh_uids = [g for _, g in zones_with_gh]
                    zone_rows = await self._ports.fetch(
                        """
                        SELECT z.id, z.uid, g.uid as gh_uid
                        FROM zones z
                        JOIN greenhouses g ON g.id = z.greenhouse_id
                        WHERE (z.uid, g.uid) IN (SELECT unnest($1::text[]), unnest($2::text[]))
                        """,
                        zone_uids,
                        gh_uids,
                    )

                    for zone in zone_rows:
                        zone_uid = zone.get("uid")
                        zone_id = zone.get("id")
                        if not zone_uid or zone_id is None:
                            continue
                        gh_uid = zone.get("gh_uid")
                        key = (zone_uid, gh_uid)
                        zone_uid_to_id[key] = zone_id
                        self._ports.zone_cache()[key] = zone_id

                if zones_without_gh:
                    zone_uids = [z for z, _ in zones_without_gh]
                    zone_rows = await self._ports.fetch(
                        """
                        SELECT id, uid
                        FROM zones
                        WHERE uid = ANY($1)
                        """,
                        zone_uids,
                    )

                    for zone in zone_rows:
                        zone_uid = zone.get("uid")
                        zone_id = zone.get("id")
                        if not zone_uid or zone_id is None:
                            continue
                        key = (zone_uid, None)
                        zone_uid_to_id[key] = zone_id
                        self._ports.zone_cache()[key] = zone_id

            for zone_uid, gh_uid in zone_gh_pairs:
                if (zone_uid, gh_uid) not in zone_uid_to_id:
                    if (zone_uid, None) not in zone_uid_to_id:
                        extra = {"zone_uid": zone_uid, "gh_uid": gh_uid}
                        if self._ports.is_temp_namespace(gh_uid, zone_uid):
                            self._ports.logger().debug(
                                "Zone not found during temp namespace telemetry bootstrap: zone_uid=%s, gh_uid=%s",
                                zone_uid,
                                gh_uid,
                                extra=extra,
                            )
                            continue
                        self._ports.log_warning_throttled(
                            key=("zone_not_found", gh_uid or "-", zone_uid, "-"),
                            message=f"Zone not found: zone_uid={zone_uid}, gh_uid={gh_uid}",
                            extra=extra,
                        )
                        await self._ports.emit_telemetry_anomaly_alert(
                            code="infra_telemetry_zone_not_found",
                            message="Telemetry received for unknown zone_uid",
                            gh_uid=gh_uid,
                            zone_uid=zone_uid,
                            details={"missing_entity": "zone"},
                        )
        return zone_uid_to_id
