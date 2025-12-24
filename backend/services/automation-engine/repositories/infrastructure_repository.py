"""
Infrastructure Repository - доступ к инфраструктуре зон и bindings.
"""
from typing import Dict, Any, Optional, List
from common.db import fetch
from infrastructure.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError


class InfrastructureRepository:
    """Репозиторий для работы с инфраструктурой зон и bindings."""
    
    def __init__(self, db_circuit_breaker: Optional[CircuitBreaker] = None):
        """
        Инициализация репозитория.
        
        Args:
            db_circuit_breaker: Circuit breaker для БД (опционально)
        """
        self.db_circuit_breaker = db_circuit_breaker
    
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
                    zcb.role,
                    zcb.node_id,
                    n.uid as node_uid,
                    zcb.channel,
                    zcb.asset_id,
                    zi.asset_type,
                    zcb.direction
                FROM zone_channel_bindings zcb
                JOIN nodes n ON n.id = zcb.node_id
                JOIN zone_infrastructure zi ON zi.id = zcb.asset_id
                WHERE zcb.zone_id = $1
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
                    "channel": row["channel"],
                    "asset_id": row["asset_id"],
                    "asset_type": row["asset_type"],
                    "direction": row["direction"],
                }
        
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
                    zcb.zone_id,
                    zcb.role,
                    zcb.node_id,
                    n.uid as node_uid,
                    zcb.channel,
                    zcb.asset_id,
                    zi.asset_type,
                    zcb.direction
                FROM zone_channel_bindings zcb
                JOIN nodes n ON n.id = zcb.node_id
                JOIN zone_infrastructure zi ON zi.id = zcb.asset_id
                WHERE zcb.zone_id = ANY($1::int[])
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
                    "channel": row["channel"],
                    "asset_id": row["asset_id"],
                    "asset_type": row["asset_type"],
                    "direction": row["direction"],
                }
        
        # Добавляем пустые словари для зон без bindings
        for zone_id in zone_ids:
            if zone_id not in result:
                result[zone_id] = {}
        
        return result
    
    async def get_zone_infrastructure_assets(self, zone_id: int) -> List[Dict[str, Any]]:
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
                    id,
                    zone_id,
                    asset_type,
                    label,
                    required,
                    capacity_liters,
                    flow_rate,
                    specs
                FROM zone_infrastructure
                WHERE zone_id = $1
                ORDER BY asset_type, label
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
                "zone_id": row["zone_id"],
                "asset_type": row["asset_type"],
                "label": row["label"],
                "required": row["required"],
                "capacity_liters": row["capacity_liters"],
                "flow_rate": row["flow_rate"],
                "specs": row["specs"],
            }
            for row in rows
        ]

