"""
Telemetry Repository - доступ к телеметрии.
"""
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from common.db import fetch
from infrastructure.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError


class TelemetryRepository:
    """Репозиторий для работы с телеметрией."""
    
    def __init__(self, db_circuit_breaker: Optional[CircuitBreaker] = None):
        """
        Инициализация репозитория.
        
        Args:
            db_circuit_breaker: Circuit breaker для БД (опционально)
        """
        self.db_circuit_breaker = db_circuit_breaker
    
    async def get_last_telemetry(self, zone_id: int) -> Dict[str, Optional[float]]:
        """
        Получить последние значения телеметрии для зоны.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict[metric_type, value]
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        async def _fetch():
            return await fetch(
                """
                SELECT metric_type, value
                FROM telemetry_last
                WHERE zone_id = $1
                """,
                zone_id,
            )
        
        if self.db_circuit_breaker:
            rows = await self.db_circuit_breaker.call(_fetch)
        else:
            rows = await _fetch()
        result: Dict[str, Optional[float]] = {}
        for row in rows:
            result[row["metric_type"]] = row["value"]
        return result
    
    async def get_last_telemetry_with_timestamps(self, zone_id: int) -> Dict[str, Tuple[Optional[float], Optional[datetime]]]:
        """
        Получить последние значения телеметрии для зоны с временными метками.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict[metric_type, (value, updated_at)]
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        async def _fetch():
            return await fetch(
                """
                SELECT metric_type, value, updated_at
                FROM telemetry_last
                WHERE zone_id = $1
                """,
                zone_id,
            )
        
        if self.db_circuit_breaker:
            rows = await self.db_circuit_breaker.call(_fetch)
        else:
            rows = await _fetch()
        result: Dict[str, Tuple[Optional[float], Optional[datetime]]] = {}
        for row in rows:
            result[row["metric_type"]] = (row["value"], row.get("updated_at"))
        return result
    
    async def get_zones_telemetry_batch(self, zone_ids: List[int]) -> Dict[int, Dict[str, Optional[float]]]:
        """
        Получить последние значения телеметрии для нескольких зон одним запросом.
        
        Args:
            zone_ids: Список ID зон
        
        Returns:
            Dict[zone_id, Dict[metric_type, value]]
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        if not zone_ids:
            return {}
        
        async def _fetch():
            return await fetch(
                """
                SELECT zone_id, metric_type, value
                FROM telemetry_last
                WHERE zone_id = ANY($1::int[])
                """,
                zone_ids,
            )
        
        if self.db_circuit_breaker:
            rows = await self.db_circuit_breaker.call(_fetch)
        else:
            rows = await _fetch()
        
        result: Dict[int, Dict[str, Optional[float]]] = {}
        for row in rows:
            zone_id = row["zone_id"]
            if zone_id not in result:
                result[zone_id] = {}
            result[zone_id][row["metric_type"]] = row["value"]
        
        # Добавляем пустые словари для зон без телеметрии
        for zone_id in zone_ids:
            if zone_id not in result:
                result[zone_id] = {}
        
        return result

