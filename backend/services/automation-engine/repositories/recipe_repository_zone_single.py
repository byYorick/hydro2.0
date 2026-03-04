"""Single-zone data loader for RecipeRepository."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from common.db import fetch
from repositories.capabilities_profile_fallback import (
    resolve_zone_capabilities_with_profile_fallback,
)
from repositories.zone_repository import ZoneRepository


async def load_zone_data_batch(repo: Any, zone_id: int) -> Dict[str, Any]:
    """
    Получить данные зоны одним запросом (telemetry, nodes, capabilities).
    Targets и recipe_info здесь больше не подгружаются.
    """

    async def _fetch():
        return await fetch(
            """
            WITH zone_info AS (
                SELECT
                    z.id as zone_id,
                    z.capabilities,
                    profile.subsystems as automation_subsystems
                FROM zones z
                LEFT JOIN LATERAL (
                    SELECT subsystems
                    FROM zone_automation_logic_profiles
                    WHERE zone_id = z.id
                      AND is_active = TRUE
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                ) profile ON TRUE
                WHERE z.id = $1
            ),
            telemetry_data AS (
                SELECT DISTINCT ON (s.type)
                    s.type as metric_type,
                    tl.last_value as value,
                    tl.last_ts as updated_at
                FROM telemetry_last tl
                JOIN sensors s ON s.id = tl.sensor_id
                WHERE s.zone_id = $1
                  AND s.is_active = TRUE
                ORDER BY s.type,
                    tl.last_ts DESC NULLS LAST,
                    tl.updated_at DESC NULLS LAST,
                    tl.sensor_id DESC
            ),
            correction_flags AS (
                SELECT
                    (
                        SELECT ts.metadata->'raw'->>'flow_active'
                        FROM telemetry_samples ts
                        JOIN sensors s ON s.id = ts.sensor_id
                        WHERE s.zone_id = $1
                          AND s.is_active = TRUE
                          AND s.type IN ('PH', 'EC')
                          AND ts.metadata->'raw' ? 'flow_active'
                        ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                        LIMIT 1
                    ) as flow_active,
                    (
                        SELECT ts.ts
                        FROM telemetry_samples ts
                        JOIN sensors s ON s.id = ts.sensor_id
                        WHERE s.zone_id = $1
                          AND s.is_active = TRUE
                          AND s.type IN ('PH', 'EC')
                          AND ts.metadata->'raw' ? 'flow_active'
                        ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                        LIMIT 1
                    ) as flow_active_ts,
                    (
                        SELECT ts.metadata->'raw'->>'stable'
                        FROM telemetry_samples ts
                        JOIN sensors s ON s.id = ts.sensor_id
                        WHERE s.zone_id = $1
                          AND s.is_active = TRUE
                          AND s.type IN ('PH', 'EC')
                          AND ts.metadata->'raw' ? 'stable'
                        ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                        LIMIT 1
                    ) as stable,
                    (
                        SELECT ts.ts
                        FROM telemetry_samples ts
                        JOIN sensors s ON s.id = ts.sensor_id
                        WHERE s.zone_id = $1
                          AND s.is_active = TRUE
                          AND s.type IN ('PH', 'EC')
                          AND ts.metadata->'raw' ? 'stable'
                        ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                        LIMIT 1
                    ) as stable_ts,
                    (
                        SELECT ts.metadata->'raw'->>'corrections_allowed'
                        FROM telemetry_samples ts
                        JOIN sensors s ON s.id = ts.sensor_id
                        WHERE s.zone_id = $1
                          AND s.is_active = TRUE
                          AND s.type IN ('PH', 'EC')
                          AND ts.metadata->'raw' ? 'corrections_allowed'
                        ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                        LIMIT 1
                    ) as corrections_allowed,
                    (
                        SELECT ts.ts
                        FROM telemetry_samples ts
                        JOIN sensors s ON s.id = ts.sensor_id
                        WHERE s.zone_id = $1
                          AND s.is_active = TRUE
                          AND s.type IN ('PH', 'EC')
                          AND ts.metadata->'raw' ? 'corrections_allowed'
                        ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                        LIMIT 1
                    ) as corrections_allowed_ts,
                    (
                        SELECT EXISTS(
                            SELECT 1
                            FROM telemetry_samples ts
                            JOIN sensors s ON s.id = ts.sensor_id
                            WHERE s.zone_id = $1
                              AND s.is_active = TRUE
                              AND s.type IN ('PH', 'EC')
                        )
                    ) as samples_present,
                    (
                        SELECT ts.ts
                        FROM telemetry_samples ts
                        JOIN sensors s ON s.id = ts.sensor_id
                        WHERE s.zone_id = $1
                          AND s.is_active = TRUE
                          AND s.type IN ('PH', 'EC')
                        ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                        LIMIT 1
                    ) as latest_sample_ts
            ),
            nodes_data AS (
                SELECT n.id, n.uid, n.type, nc.id as node_channel_id, nc.channel
                FROM nodes n
                LEFT JOIN node_channels nc ON nc.node_id = n.id
                WHERE n.zone_id = $1 AND n.status = 'online'
            )
            SELECT
                (SELECT row_to_json(zone_info) FROM zone_info) as zone_info,
                (SELECT json_object_agg(
                    metric_type,
                    json_build_object('value', value, 'updated_at', updated_at)
                ) FROM telemetry_data) as telemetry,
                (SELECT row_to_json(correction_flags) FROM correction_flags) as correction_flags,
                (SELECT json_agg(row_to_json(nodes_data)) FROM nodes_data) as nodes
            """,
            zone_id,
        )

    if repo.db_circuit_breaker:
        rows = await repo.db_circuit_breaker.call(_fetch)
    else:
        rows = await _fetch()

    if not rows or not rows[0]:
        return {
            "recipe_info": None,
            "telemetry": {},
            "nodes": {},
            "capabilities": {},
        }

    result = rows[0]

    zone_info_raw = result.get("zone_info") or {}
    if isinstance(zone_info_raw, str):
        zone_info_raw = json.loads(zone_info_raw)
    zone_info = zone_info_raw or {}

    telemetry_raw = result.get("telemetry") or {}
    if isinstance(telemetry_raw, str):
        telemetry_raw = json.loads(telemetry_raw)

    correction_flags_raw = result.get("correction_flags") or {}
    if isinstance(correction_flags_raw, str):
        correction_flags_raw = json.loads(correction_flags_raw)

    nodes_list = result.get("nodes") or []
    if isinstance(nodes_list, str):
        nodes_list = json.loads(nodes_list)

    telemetry: Dict[str, Optional[float]] = {}
    telemetry_timestamps: Dict[str, Any] = {}
    for metric_type, metric_data in telemetry_raw.items():
        if isinstance(metric_data, dict):
            telemetry[metric_type] = metric_data.get("value")
            telemetry_timestamps[metric_type] = metric_data.get("updated_at")
        else:
            telemetry[metric_type] = metric_data

    nodes_dict: Dict[str, Dict[str, Any]] = {}
    for node in nodes_list:
        node_type = node.get("type", "")
        channel = node.get("channel") or "default"
        key = f"{node_type}:{channel}"
        if key not in nodes_dict:
            nodes_dict[key] = {
                "node_id": node.get("id"),
                "node_uid": node.get("uid"),
                "type": node_type,
                "node_channel_id": node.get("node_channel_id"),
                "channel": channel,
            }

    capabilities = resolve_zone_capabilities_with_profile_fallback(
        raw_capabilities=zone_info.get("capabilities"),
        profile_subsystems=zone_info.get("automation_subsystems"),
        default_capabilities=ZoneRepository.DEFAULT_CAPABILITIES.copy(),
    )
    await repo._sync_telemetry_samples_health_signal(
        zone_id=zone_id,
        correction_flags_raw=correction_flags_raw,
        capabilities=capabilities,
    )

    return {
        "recipe_info": None,
        "telemetry": telemetry,
        "telemetry_timestamps": telemetry_timestamps,
        "correction_flags": repo._extract_correction_flags(
            correction_flags_raw,
            telemetry,
            telemetry_timestamps,
        ),
        "nodes": nodes_dict,
        "capabilities": capabilities,
    }


__all__ = ["load_zone_data_batch"]
