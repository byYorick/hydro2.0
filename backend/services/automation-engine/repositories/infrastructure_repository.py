"""
Infrastructure Repository - доступ к инфраструктуре зон и bindings.
"""
from typing import Dict, Any, Optional, List, Set, Tuple
import logging
from common.db import fetch
from infrastructure.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = logging.getLogger(__name__)


class InfrastructureRepository:
    """Репозиторий для работы с инфраструктурой зон и bindings."""
    
    def __init__(self, db_circuit_breaker: Optional[CircuitBreaker] = None):
        """
        Инициализация репозитория.
        
        Args:
            db_circuit_breaker: Circuit breaker для БД (опционально)
        """
        self.db_circuit_breaker = db_circuit_breaker
        self._multi_role_logged: Set[Tuple[int, str]] = set()
    
    async def get_zone_bindings_by_role(self, zone_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Получить bindings зоны, сгруппированные по роли (role).
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict[role, binding_info] где binding_info содержит:
                - node_id
                - node_uid
                - channel
                - asset_id
                - asset_type
                - direction (actuator|sensor)
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        async def _fetch():
            return await fetch(
                """
                SELECT 
                    cb.role,
                    cb.direction,
                    ii.id as asset_id,
                    ii.asset_type,
                    n.id as node_id,
                    n.uid as node_uid,
                    nc.id as node_channel_id,
                    nc.channel as channel
                FROM infrastructure_instances ii
                JOIN channel_bindings cb ON cb.infrastructure_instance_id = ii.id
                JOIN node_channels nc ON nc.id = cb.node_channel_id
                JOIN nodes n ON n.id = nc.node_id
                WHERE (
                    (ii.owner_type = 'zone' AND ii.owner_id = $1)
                    OR (
                        ii.owner_type = 'greenhouse'
                        AND ii.owner_id = (SELECT greenhouse_id FROM zones WHERE id = $1)
                    )
                )
                AND n.status = 'online'
                """,
                zone_id,
            )
        
        if self.db_circuit_breaker:
            rows = await self.db_circuit_breaker.call(_fetch)
        else:
            rows = await _fetch()
        
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            role = row["role"]
            if role not in result:
                result[role] = {
                    "node_id": row["node_id"],
                    "node_uid": row["node_uid"],
                    "node_channel_id": row["node_channel_id"],
                    "channel": row["channel"],
                    "asset_id": row["asset_id"],
                    "asset_type": row["asset_type"],
                    "direction": row["direction"],
                }
            else:
                key = (zone_id, role)
                if key not in self._multi_role_logged:
                    self._multi_role_logged.add(key)
                    logger.warning(
                        "Multiple bindings found for role; using first binding",
                        extra={"zone_id": zone_id, "role": role},
                    )
        
        return result
    
    async def get_zones_bindings_batch(self, zone_ids: List[int]) -> Dict[int, Dict[str, Dict[str, Any]]]:
        """
        Получить bindings для нескольких зон одним запросом.
        
        Args:
            zone_ids: Список ID зон
        
        Returns:
            Dict[zone_id, Dict[role, binding_info]]
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        if not zone_ids:
            return {}
        
        async def _fetch():
            return await fetch(
                """
                SELECT 
                    z.id as zone_id,
                    cb.role,
                    cb.direction,
                    ii.id as asset_id,
                    ii.asset_type,
                    n.id as node_id,
                    n.uid as node_uid,
                    nc.id as node_channel_id,
                    nc.channel as channel
                FROM infrastructure_instances ii
                JOIN channel_bindings cb ON cb.infrastructure_instance_id = ii.id
                JOIN node_channels nc ON nc.id = cb.node_channel_id
                JOIN nodes n ON n.id = nc.node_id
                JOIN zones z ON (
                    (ii.owner_type = 'zone' AND ii.owner_id = z.id)
                    OR (ii.owner_type = 'greenhouse' AND ii.owner_id = z.greenhouse_id)
                )
                WHERE z.id = ANY($1::int[])
                    AND n.status = 'online'
                """,
                zone_ids,
            )
        
        if self.db_circuit_breaker:
            rows = await self.db_circuit_breaker.call(_fetch)
        else:
            rows = await _fetch()
        
        result: Dict[int, Dict[str, Dict[str, Any]]] = {}
        for row in rows:
            zone_id = row["zone_id"]
            role = row["role"]
            
            if zone_id not in result:
                result[zone_id] = {}
            
            if role not in result[zone_id]:
                result[zone_id][role] = {
                    "node_id": row["node_id"],
                    "node_uid": row["node_uid"],
                    "node_channel_id": row["node_channel_id"],
                    "channel": row["channel"],
                    "asset_id": row["asset_id"],
                    "asset_type": row["asset_type"],
                    "direction": row["direction"],
                }
            else:
                key = (zone_id, role)
                if key not in self._multi_role_logged:
                    self._multi_role_logged.add(key)
                    logger.warning(
                        "Multiple bindings found for role; using first binding",
                        extra={"zone_id": zone_id, "role": role},
                    )
        
        # Добавляем пустые словари для зон без bindings
        for zone_id in zone_ids:
            if zone_id not in result:
                result[zone_id] = {}
        
        return result
    
    async def get_zone_asset_instances(self, zone_id: int) -> List[Dict[str, Any]]:
        """
        Получить список оборудования (assets) зоны.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Список словарей с информацией об оборудовании
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        async def _fetch():
            return await fetch(
                """
                SELECT 
                    ii.id,
                    ii.owner_type,
                    ii.owner_id,
                    ii.asset_type,
                    ii.label,
                    ii.required,
                    ii.capacity_liters,
                    ii.flow_rate,
                    ii.specs
                FROM infrastructure_instances ii
                WHERE (
                    (ii.owner_type = 'zone' AND ii.owner_id = $1)
                    OR (
                        ii.owner_type = 'greenhouse'
                        AND ii.owner_id = (SELECT greenhouse_id FROM zones WHERE id = $1)
                    )
                )
                ORDER BY ii.asset_type, ii.label
                """,
                zone_id,
            )
        
        if self.db_circuit_breaker:
            rows = await self.db_circuit_breaker.call(_fetch)
        else:
            rows = await _fetch()
        
        return [
            {
                "id": row["id"],
                "owner_type": row["owner_type"],
                "owner_id": row["owner_id"],
                "asset_type": row["asset_type"],
                "label": row["label"],
                "required": row["required"],
                "capacity_liters": row["capacity_liters"],
                "flow_rate": row["flow_rate"],
                "specs": row["specs"],
            }
            for row in rows
        ]
