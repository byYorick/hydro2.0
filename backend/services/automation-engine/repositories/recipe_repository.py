"""
Recipe Repository - доступ к рецептам и фазам.
Использует Laravel API для получения effective targets (новая модель GrowCycle).
"""
import json
import logging
from typing import Dict, Any, Optional, List
from common.db import fetch
from infrastructure.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from repositories.laravel_api_repository import LaravelApiRepository
from common.effective_targets import parse_effective_targets

logger = logging.getLogger(__name__)


class RecipeRepository:
    """Репозиторий для работы с рецептами."""
    
    def __init__(self, db_circuit_breaker: Optional[CircuitBreaker] = None, use_laravel_api: bool = True):
        """
        Инициализация репозитория.
        
        Args:
            db_circuit_breaker: Circuit breaker для БД (опционально)
            use_laravel_api: Использовать Laravel API вместо прямых SQL запросов (по умолчанию True)
        """
        self.db_circuit_breaker = db_circuit_breaker
        self.use_laravel_api = use_laravel_api
        if use_laravel_api:
            self.laravel_api = LaravelApiRepository()
        else:
            self.laravel_api = None
    
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
        if self.use_laravel_api and self.laravel_api:
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

        logger.warning("Laravel API disabled; legacy recipe tables are no longer supported")
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
        
        # Используем Laravel API для batch запроса
        if self.use_laravel_api and self.laravel_api:
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

        logger.warning("Laravel API disabled; legacy recipe tables are no longer supported")
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
                nodes_data AS (
                    SELECT n.id, n.uid, n.type, nc.channel
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
                    "channel": channel,
                }
        
        # Получаем capabilities
        capabilities = zone_info.get("capabilities") or {}
        if not capabilities:
            from .zone_repository import ZoneRepository
            capabilities = ZoneRepository.DEFAULT_CAPABILITIES.copy()
        
        return {
            "recipe_info": None,
            "telemetry": telemetry,
            "telemetry_timestamps": telemetry_timestamps,  # Добавляем timestamps для проверки свежести
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
                SELECT n.zone_id, n.id, n.uid, n.type, nc.channel
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
                    'nodes', (
                        SELECT json_object_agg(
                            nd.type || ':' || COALESCE(nd.channel, 'default'),
                            json_build_object(
                                'node_id', nd.id,
                                'node_uid', nd.uid,
                                'type', nd.type,
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
            
            result[zone_id] = zone_data
        
        # Добавляем пустые данные для зон без результатов
        for zone_id in zone_ids:
            if zone_id not in result:
                result[zone_id] = {
                    "recipe_info": None,
                    "telemetry": {},
                    "telemetry_timestamps": {},
                    "nodes": {},
                    "capabilities": {}
                }
        
        return result
