"""
Telemetry Repository - доступ к телеметрии.
"""
from typing import Dict, Optional, List
from common.db import fetch


class TelemetryRepository:
    """Репозиторий для работы с телеметрией."""
    
    async def get_last_telemetry(self, zone_id: int) -> Dict[str, Optional[float]]:
        """
        Получить последние значения телеметрии для зоны.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict[metric_type, value]
        """
        rows = await fetch(
            """
            SELECT metric_type, value
            FROM telemetry_last
            WHERE zone_id = $1
            """,
            zone_id,
        )
        result: Dict[str, Optional[float]] = {}
        for row in rows:
            result[row["metric_type"]] = row["value"]
        return result
    
    async def get_zones_telemetry_batch(self, zone_ids: List[int]) -> Dict[int, Dict[str, Optional[float]]]:
        """
        Получить последние значения телеметрии для нескольких зон одним запросом.
        
        Args:
            zone_ids: Список ID зон
        
        Returns:
            Dict[zone_id, Dict[metric_type, value]]
        """
        if not zone_ids:
            return {}
        
        rows = await fetch(
            """
            SELECT zone_id, metric_type, value
            FROM telemetry_last
            WHERE zone_id = ANY($1::int[])
            """,
            zone_ids,
        )
        
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

