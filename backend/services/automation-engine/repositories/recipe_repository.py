"""
Recipe Repository - доступ к рецептам и фазам.
Использует Laravel API для получения effective targets (новая модель GrowCycle).
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from common.db import fetch, create_zone_event
from common.infra_alerts import send_infra_alert, send_infra_resolved_alert
from common.utils.time import utcnow
from infrastructure.circuit_breaker import CircuitBreaker
from repositories.laravel_api_repository import LaravelApiRepository
from common.effective_targets import parse_effective_targets

logger = logging.getLogger(__name__)
MISSING_TELEMETRY_SAMPLES_REPORT_THROTTLE_SECONDS = 300


def _to_optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


class RecipeRepository:
    """Репозиторий для работы с рецептами."""
    
    def __init__(self, db_circuit_breaker: Optional[CircuitBreaker] = None):
        """
        Инициализация репозитория.
        
        Args:
            db_circuit_breaker: Circuit breaker для БД (опционально)
        """
        self.db_circuit_breaker = db_circuit_breaker
        self.laravel_api = LaravelApiRepository()
        self._telemetry_samples_missing_alert_active: Dict[int, bool] = {}
        self._telemetry_samples_missing_last_report_at: Dict[int, datetime] = {}

    @staticmethod
    def _normalize_timestamp(value: Any) -> Optional[str]:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    async def _create_zone_event_safe(
        self,
        *,
        zone_id: int,
        event_type: str,
        details: Dict[str, Any],
    ) -> bool:
        try:
            await create_zone_event(zone_id, event_type, details)
            return True
        except Exception as event_error:
            logger.warning(
                "Zone %s: failed to persist zone event %s: %s",
                zone_id,
                event_type,
                event_error,
                exc_info=True,
            )
            return False

    async def _sync_telemetry_samples_health_signal(
        self,
        *,
        zone_id: int,
        correction_flags_raw: Optional[Dict[str, Any]],
        capabilities: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not isinstance(correction_flags_raw, dict):
            return
        if isinstance(capabilities, dict):
            if not bool(capabilities.get("ph_control") or capabilities.get("ec_control")):
                return

        samples_present_raw = correction_flags_raw.get("samples_present")
        if samples_present_raw is None:
            return

        samples_present = _to_optional_bool(samples_present_raw)
        if samples_present is None:
            return

        latest_sample_ts = self._normalize_timestamp(correction_flags_raw.get("latest_sample_ts"))
        is_active = bool(self._telemetry_samples_missing_alert_active.get(zone_id, False))

        if samples_present:
            if not is_active:
                return
            resolved_sent = await send_infra_resolved_alert(
                code="infra_correction_flags_telemetry_samples_missing",
                alert_type="Correction Flags Telemetry Missing",
                message=f"Zone {zone_id}: telemetry_samples for correction flags restored",
                zone_id=zone_id,
                service="automation-engine",
                component="recipe_repository",
                details={
                    "zone_id": zone_id,
                    "sensor_types": ["PH", "EC"],
                    "latest_sample_ts": latest_sample_ts,
                },
            )
            if resolved_sent:
                await self._create_zone_event_safe(
                    zone_id=zone_id,
                    event_type="CORRECTION_FLAGS_SOURCE_RESTORED",
                    details={
                        "source": "telemetry_samples",
                        "sensor_types": ["PH", "EC"],
                        "latest_sample_ts": latest_sample_ts,
                    },
                )
                self._telemetry_samples_missing_alert_active[zone_id] = False
                self._telemetry_samples_missing_last_report_at.pop(zone_id, None)
            return

        now = utcnow()
        last_reported = self._telemetry_samples_missing_last_report_at.get(zone_id)
        if isinstance(last_reported, datetime) and (
            now - last_reported
        ).total_seconds() < MISSING_TELEMETRY_SAMPLES_REPORT_THROTTLE_SECONDS:
            return

        logger.warning(
            "Zone %s: telemetry_samples missing for PH/EC sensors, correction flags cannot be computed from samples metadata",
            zone_id,
            extra={"zone_id": zone_id, "latest_sample_ts": latest_sample_ts},
        )

        event_created = False
        if not is_active:
            event_created = await self._create_zone_event_safe(
                zone_id=zone_id,
                event_type="CORRECTION_FLAGS_SOURCE_MISSING",
                details={
                    "source": "telemetry_samples",
                    "sensor_types": ["PH", "EC"],
                    "latest_sample_ts": latest_sample_ts,
                    "reason": "samples_absent_for_ph_ec",
                },
            )

        alert_sent = await send_infra_alert(
            code="infra_correction_flags_telemetry_samples_missing",
            alert_type="Correction Flags Telemetry Missing",
            message=f"Zone {zone_id}: telemetry_samples missing for PH/EC, correction flags degraded",
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="recipe_repository",
            error_type="TelemetrySamplesMissing",
            details={
                "zone_id": zone_id,
                "sensor_types": ["PH", "EC"],
                "latest_sample_ts": latest_sample_ts,
                "throttle_seconds": MISSING_TELEMETRY_SAMPLES_REPORT_THROTTLE_SECONDS,
            },
        )
        if alert_sent or event_created:
            self._telemetry_samples_missing_alert_active[zone_id] = True
            self._telemetry_samples_missing_last_report_at[zone_id] = now

    @staticmethod
    def _extract_correction_flags(
        correction_flags_raw: Optional[Dict[str, Any]],
        telemetry: Dict[str, Optional[float]],
        telemetry_timestamps: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_flags = correction_flags_raw if isinstance(correction_flags_raw, dict) else {}
        flow_active = _to_optional_bool(raw_flags.get("flow_active"))
        if flow_active is None:
            flow_active = _to_optional_bool(telemetry.get("FLOW_ACTIVE"))
        stable = _to_optional_bool(raw_flags.get("stable"))
        if stable is None:
            stable = _to_optional_bool(telemetry.get("STABLE"))
        corrections_allowed = _to_optional_bool(raw_flags.get("corrections_allowed"))
        if corrections_allowed is None:
            corrections_allowed = _to_optional_bool(telemetry.get("CORRECTIONS_ALLOWED"))
        return {
            "flow_active": flow_active,
            "stable": stable,
            "corrections_allowed": corrections_allowed,
            "flow_active_ts": raw_flags.get("flow_active_ts", telemetry_timestamps.get("FLOW_ACTIVE")),
            "stable_ts": raw_flags.get("stable_ts", telemetry_timestamps.get("STABLE")),
            "corrections_allowed_ts": raw_flags.get(
                "corrections_allowed_ts",
                telemetry_timestamps.get("CORRECTIONS_ALLOWED"),
            ),
        }
    
    async def get_zone_recipe_and_targets(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить активный рецепт и targets для зоны (новая модель через Laravel API).
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict с zone_id, phase_index, targets, phase_name или None
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        # Используем Laravel API для получения effective targets
        try:
            effective_targets = await self.laravel_api.get_effective_targets(zone_id)
            if not effective_targets:
                return None
            try:
                parsed = parse_effective_targets(effective_targets)
            except Exception as e:
                logger.warning(f'Failed to parse effective targets for zone {zone_id}: {e}')
                return None

            normalized = parsed.model_dump()
            # Преобразуем формат из Laravel API в формат, ожидаемый кодом
            phase = normalized.get('phase', {})
            targets = normalized.get('targets', {})

            return {
                "zone_id": normalized.get('zone_id', zone_id),
                "cycle_id": normalized.get('cycle_id'),
                "phase_index": phase.get('id'),  # Используем ID фазы как индекс
                "targets": targets,
                "phase_name": phase.get('name', phase.get('code', 'UNKNOWN')),
            }
        except Exception as e:
            logger.warning(f'Failed to get effective targets from Laravel API for zone {zone_id}: {e}')
            return None
    
    async def get_zones_recipes_batch(self, zone_ids: List[int]) -> Dict[int, Optional[Dict[str, Any]]]:
        """
        Получить рецепты и targets для нескольких зон одним запросом (новая модель через Laravel API).
        
        Args:
            zone_ids: Список ID зон
        
        Returns:
            Dict[zone_id, recipe_info] или None если рецепта нет
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        if not zone_ids:
            return {}
        
        try:
            effective_targets_batch = await self.laravel_api.get_effective_targets_batch(zone_ids)

            # Преобразуем формат из Laravel API в формат, ожидаемый кодом
            result: Dict[int, Optional[Dict[str, Any]]] = {}
            for zone_id in zone_ids:
                effective_targets = effective_targets_batch.get(zone_id)
                if not effective_targets or 'error' in effective_targets:
                    result[zone_id] = None
                    continue

                try:
                    parsed = parse_effective_targets(effective_targets)
                    normalized = parsed.model_dump()
                except Exception as e:
                    logger.warning(f'Failed to parse effective targets for zone {zone_id}: {e}')
                    result[zone_id] = None
                    continue

                phase = normalized.get('phase', {})
                targets = normalized.get('targets', {})

                result[zone_id] = {
                    "zone_id": normalized.get('zone_id', zone_id),
                    "cycle_id": normalized.get('cycle_id'),
                    "phase_index": phase.get('id'),  # Используем ID фазы как индекс
                    "targets": targets,
                    "phase_name": phase.get('name', phase.get('code', 'UNKNOWN')),
                }

            return result
        except Exception as e:
            logger.warning(f'Failed to get effective targets batch from Laravel API: {e}')
            return {zone_id: None for zone_id in zone_ids}
    
    async def get_zone_data_batch(self, zone_id: int) -> Dict[str, Any]:
        """
        Получить данные зоны одним запросом (telemetry, nodes, capabilities).
        Targets и recipe_info здесь больше не подгружаются.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict с recipe_info (None), telemetry, nodes, capabilities
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        async def _fetch():
            return await fetch(
                """
                WITH zone_info AS (
                    SELECT 
                        z.id as zone_id,
                        z.capabilities
                    FROM zones z
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
        
        if self.db_circuit_breaker:
            rows = await self.db_circuit_breaker.call(_fetch)
        else:
            rows = await _fetch()
        
        if not rows or not rows[0]:
            return {
                "recipe_info": None,
                "telemetry": {},
                "nodes": {},
                "capabilities": {}
            }
        
        result = rows[0]
        
        # asyncpg возвращает json/jsonb поля как строки, поэтому нормализуем
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
        
        # Преобразуем телеметрию: извлекаем value и updated_at из объектов
        # Формат: {"PH": {"value": 6.5, "updated_at": "2024-01-01T12:00:00"}, ...}
        telemetry: Dict[str, Optional[float]] = {}
        telemetry_timestamps: Dict[str, Any] = {}  # Для проверки свежести
        for metric_type, metric_data in telemetry_raw.items():
            if isinstance(metric_data, dict):
                telemetry[metric_type] = metric_data.get("value")
                telemetry_timestamps[metric_type] = metric_data.get("updated_at")
            else:
                # Обратная совместимость: если приходит просто value
                telemetry[metric_type] = metric_data
        
        # Преобразуем список узлов в словарь
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
        
        # Получаем capabilities
        capabilities = zone_info.get("capabilities") or {}
        if not capabilities:
            from .zone_repository import ZoneRepository
            capabilities = ZoneRepository.DEFAULT_CAPABILITIES.copy()
        await self._sync_telemetry_samples_health_signal(
            zone_id=zone_id,
            correction_flags_raw=correction_flags_raw,
            capabilities=capabilities,
        )
        
        return {
            "recipe_info": None,
            "telemetry": telemetry,
            "telemetry_timestamps": telemetry_timestamps,  # Добавляем timestamps для проверки свежести
            "correction_flags": self._extract_correction_flags(
                correction_flags_raw,
                telemetry,
                telemetry_timestamps,
            ),
            "nodes": nodes_dict,
            "capabilities": capabilities
        }

    async def get_zones_data_batch_optimized(self, zone_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        Оптимизированный batch запрос для получения данных нескольких зон одним запросом.
        Targets и recipe_info здесь больше не подгружаются.
        
        Args:
            zone_ids: Список ID зон
        
        Returns:
            Dict[zone_id, zone_data] с полными данными каждой зоны
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        if not zone_ids:
            return {}
        
        async def _fetch():
            return await fetch(
            """
            WITH zone_info AS (
                SELECT 
                    z.id as zone_id,
                    z.capabilities
                FROM zones z
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
                    'capabilities', COALESCE(zi.capabilities, '{}'::jsonb)
                ) as zone_data
            FROM zone_info zi
            """,
            zone_ids,
        )
        
        if self.db_circuit_breaker:
            rows = await self.db_circuit_breaker.call(_fetch)
        else:
            rows = await _fetch()
        
        result: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            zone_id = row['zone_id']
            zone_data = row['zone_data']
            if isinstance(zone_data, str):
                zone_data = json.loads(zone_data)
            
            # Обрабатываем телеметрию
            telemetry_raw = zone_data.get('telemetry', {})
            telemetry: Dict[str, Optional[float]] = {}
            telemetry_timestamps: Dict[str, Any] = {}
            
            for metric_type, metric_data in telemetry_raw.items():
                if isinstance(metric_data, dict):
                    telemetry[metric_type] = metric_data.get("value")
                    telemetry_timestamps[metric_type] = metric_data.get("updated_at")
                else:
                    telemetry[metric_type] = metric_data
            
            # Обновляем zone_data с обработанной телеметрией
            zone_data['telemetry'] = telemetry
            zone_data['telemetry_timestamps'] = telemetry_timestamps or zone_data.get('telemetry_timestamps', {})
            correction_flags_raw = zone_data.get("correction_flags")
            if isinstance(correction_flags_raw, str):
                correction_flags_raw = json.loads(correction_flags_raw)
            await self._sync_telemetry_samples_health_signal(
                zone_id=zone_id,
                correction_flags_raw=correction_flags_raw,
                capabilities=zone_data.get("capabilities"),
            )
            zone_data['correction_flags'] = self._extract_correction_flags(
                correction_flags_raw,
                zone_data['telemetry'],
                zone_data['telemetry_timestamps'],
            )
            
            result[zone_id] = zone_data
        
        # Добавляем пустые данные для зон без результатов
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
                    "capabilities": {}
                }
        
        return result
