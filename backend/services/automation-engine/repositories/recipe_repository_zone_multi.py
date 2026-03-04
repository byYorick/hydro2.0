"""Multi-zone optimized data loader for RecipeRepository."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from common.db import fetch
from repositories.capabilities_profile_fallback import (
    resolve_zone_capabilities_with_profile_fallback,
)
from repositories.zone_repository import ZoneRepository


async def load_zones_data_batch_optimized(repo: Any, zone_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """
    Оптимизированный batch-запрос данных нескольких зон одним SQL.
    Targets и recipe_info здесь не подгружаются.
    """
    if not zone_ids:
        return {}

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
                WHERE z.id = ANY($1::int[])
            ),
            telemetry_data AS (
                SELECT zone_id, metric_type, value, updated_at
                FROM (
                    SELECT
                        s.zone_id as zone_id,
                        s.type as metric_type,
                        tl.last_value as value,
                        tl.last_ts as updated_at,
                        ROW_NUMBER() OVER (
                            PARTITION BY s.zone_id, s.type
                            ORDER BY tl.last_ts DESC NULLS LAST,
                                tl.updated_at DESC NULLS LAST,
                                tl.sensor_id DESC
                        ) as rn
                    FROM telemetry_last tl
                    JOIN sensors s ON s.id = tl.sensor_id
                    WHERE s.zone_id = ANY($1::int[])
                      AND s.is_active = TRUE
                ) ranked
                WHERE rn = 1
            ),
            nodes_data AS (
                SELECT n.zone_id, n.id, n.uid, n.type, nc.id as node_channel_id, nc.channel
                FROM nodes n
                LEFT JOIN node_channels nc ON nc.node_id = n.id
                WHERE n.zone_id = ANY($1::int[]) AND n.status = 'online'
            )
            SELECT
                zi.zone_id,
                json_build_object(
                    'recipe_info', NULL,
                    'telemetry', (
                        SELECT json_object_agg(
                            td.metric_type,
                            json_build_object('value', td.value, 'updated_at', td.updated_at)
                        )
                        FROM telemetry_data td
                        WHERE td.zone_id = zi.zone_id
                    ),
                    'telemetry_timestamps', (
                        SELECT json_object_agg(td.metric_type, td.updated_at)
                        FROM telemetry_data td
                        WHERE td.zone_id = zi.zone_id
                    ),
                    'correction_flags', json_build_object(
                        'flow_active', (
                            SELECT ts.metadata->'raw'->>'flow_active'
                            FROM telemetry_samples ts
                            JOIN sensors s ON s.id = ts.sensor_id
                            WHERE s.zone_id = zi.zone_id
                              AND s.is_active = TRUE
                              AND s.type IN ('PH', 'EC')
                              AND ts.metadata->'raw' ? 'flow_active'
                            ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                            LIMIT 1
                        ),
                        'flow_active_ts', (
                            SELECT ts.ts
                            FROM telemetry_samples ts
                            JOIN sensors s ON s.id = ts.sensor_id
                            WHERE s.zone_id = zi.zone_id
                              AND s.is_active = TRUE
                              AND s.type IN ('PH', 'EC')
                              AND ts.metadata->'raw' ? 'flow_active'
                            ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                            LIMIT 1
                        ),
                        'stable', (
                            SELECT ts.metadata->'raw'->>'stable'
                            FROM telemetry_samples ts
                            JOIN sensors s ON s.id = ts.sensor_id
                            WHERE s.zone_id = zi.zone_id
                              AND s.is_active = TRUE
                              AND s.type IN ('PH', 'EC')
                              AND ts.metadata->'raw' ? 'stable'
                            ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                            LIMIT 1
                        ),
                        'stable_ts', (
                            SELECT ts.ts
                            FROM telemetry_samples ts
                            JOIN sensors s ON s.id = ts.sensor_id
                            WHERE s.zone_id = zi.zone_id
                              AND s.is_active = TRUE
                              AND s.type IN ('PH', 'EC')
                              AND ts.metadata->'raw' ? 'stable'
                            ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                            LIMIT 1
                        ),
                        'corrections_allowed', (
                            SELECT ts.metadata->'raw'->>'corrections_allowed'
                            FROM telemetry_samples ts
                            JOIN sensors s ON s.id = ts.sensor_id
                            WHERE s.zone_id = zi.zone_id
                              AND s.is_active = TRUE
                              AND s.type IN ('PH', 'EC')
                              AND ts.metadata->'raw' ? 'corrections_allowed'
                            ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                            LIMIT 1
                        ),
                        'corrections_allowed_ts', (
                            SELECT ts.ts
                            FROM telemetry_samples ts
                            JOIN sensors s ON s.id = ts.sensor_id
                            WHERE s.zone_id = zi.zone_id
                              AND s.is_active = TRUE
                              AND s.type IN ('PH', 'EC')
                              AND ts.metadata->'raw' ? 'corrections_allowed'
                            ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                            LIMIT 1
                        ),
                        'samples_present', (
                            SELECT EXISTS(
                                SELECT 1
                                FROM telemetry_samples ts
                                JOIN sensors s ON s.id = ts.sensor_id
                                WHERE s.zone_id = zi.zone_id
                                  AND s.is_active = TRUE
                                  AND s.type IN ('PH', 'EC')
                            )
                        ),
                        'latest_sample_ts', (
                            SELECT ts.ts
                            FROM telemetry_samples ts
                            JOIN sensors s ON s.id = ts.sensor_id
                            WHERE s.zone_id = zi.zone_id
                              AND s.is_active = TRUE
                              AND s.type IN ('PH', 'EC')
                            ORDER BY ts.ts DESC NULLS LAST, ts.id DESC
                            LIMIT 1
                        )
                    ),
                    'nodes', (
                        SELECT json_object_agg(
                            nd.type || ':' || COALESCE(nd.channel, 'default'),
                            json_build_object(
                                'node_id', nd.id,
                                'node_uid', nd.uid,
                                'type', nd.type,
                                'node_channel_id', nd.node_channel_id,
                                'channel', nd.channel
                            )
                        )
                        FROM nodes_data nd
                        WHERE nd.zone_id = zi.zone_id
                    ),
                    'capabilities', COALESCE(zi.capabilities, '{}'::jsonb),
                    'automation_subsystems', COALESCE(zi.automation_subsystems, '{}'::jsonb)
                ) as zone_data
            FROM zone_info zi
            """,
            zone_ids,
        )

    if repo.db_circuit_breaker:
        rows = await repo.db_circuit_breaker.call(_fetch)
    else:
        rows = await _fetch()

    result: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        zone_id = row["zone_id"]
        zone_data = row["zone_data"]
        if isinstance(zone_data, str):
            zone_data = json.loads(zone_data)

        telemetry_raw = zone_data.get("telemetry", {})
        telemetry: Dict[str, Optional[float]] = {}
        telemetry_timestamps: Dict[str, Any] = {}

        for metric_type, metric_data in telemetry_raw.items():
            if isinstance(metric_data, dict):
                telemetry[metric_type] = metric_data.get("value")
                telemetry_timestamps[metric_type] = metric_data.get("updated_at")
            else:
                telemetry[metric_type] = metric_data

        zone_data["telemetry"] = telemetry
        zone_data["telemetry_timestamps"] = telemetry_timestamps or zone_data.get("telemetry_timestamps", {})
        zone_data["capabilities"] = resolve_zone_capabilities_with_profile_fallback(
            raw_capabilities=zone_data.get("capabilities"),
            profile_subsystems=zone_data.get("automation_subsystems"),
            default_capabilities=ZoneRepository.DEFAULT_CAPABILITIES.copy(),
        )
        zone_data.pop("automation_subsystems", None)
        correction_flags_raw = zone_data.get("correction_flags")
        if isinstance(correction_flags_raw, str):
            correction_flags_raw = json.loads(correction_flags_raw)
        await repo._sync_telemetry_samples_health_signal(
            zone_id=zone_id,
            correction_flags_raw=correction_flags_raw,
            capabilities=zone_data.get("capabilities"),
        )
        zone_data["correction_flags"] = repo._extract_correction_flags(
            correction_flags_raw,
            zone_data["telemetry"],
            zone_data["telemetry_timestamps"],
        )
        result[zone_id] = zone_data

    for zone_id in zone_ids:
        if zone_id not in result:
            result[zone_id] = {
                "recipe_info": None,
                "telemetry": {},
                "telemetry_timestamps": {},
                "correction_flags": {
                    "flow_active": None,
                    "stable": None,
                    "corrections_allowed": None,
                    "flow_active_ts": None,
                    "stable_ts": None,
                    "corrections_allowed_ts": None,
                },
                "nodes": {},
                "capabilities": {},
            }

    return result


__all__ = ["load_zones_data_batch_optimized"]
