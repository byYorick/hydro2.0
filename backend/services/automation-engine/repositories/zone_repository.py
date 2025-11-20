"""
Zone Repository - доступ к данным зон.
"""
from typing import Dict, Any, Optional, List
from common.db import fetch


class ZoneRepository:
    """Репозиторий для работы с зонами."""
    
    DEFAULT_CAPABILITIES = {
        "ph_control": False,
        "ec_control": False,
        "climate_control": False,
        "light_control": False,
        "irrigation_control": False,
        "recirculation": False,
        "flow_sensor": False,
    }
    
    async def get_zone_capabilities(self, zone_id: int) -> Dict[str, bool]:
        """
        Получить capabilities зоны.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict с capabilities или дефолтные значения
        """
        rows = await fetch(
            """
            SELECT capabilities
            FROM zones
            WHERE id = $1
            """,
            zone_id,
        )
        if rows and len(rows) > 0 and rows[0]["capabilities"]:
            return rows[0]["capabilities"]
        return self.DEFAULT_CAPABILITIES.copy()
    
    async def get_zones_capabilities_batch(self, zone_ids: List[int]) -> Dict[int, Dict[str, bool]]:
        """
        Получить capabilities для нескольких зон одним запросом.
        
        Args:
            zone_ids: Список ID зон
        
        Returns:
            Dict[zone_id, capabilities]
        """
        if not zone_ids:
            return {}
        
        rows = await fetch(
            """
            SELECT id, capabilities
            FROM zones
            WHERE id = ANY($1::int[])
            """,
            zone_ids,
        )
        
        result: Dict[int, Dict[str, bool]] = {}
        for row in rows:
            zone_id = row["id"]
            capabilities = row["capabilities"] if row["capabilities"] else self.DEFAULT_CAPABILITIES.copy()
            result[zone_id] = capabilities
        
        # Добавляем дефолтные значения для зон, которых нет в результате
        for zone_id in zone_ids:
            if zone_id not in result:
                result[zone_id] = self.DEFAULT_CAPABILITIES.copy()
        
        return result
    
    async def get_active_zones(self) -> List[Dict[str, Any]]:
        """
        Получить список активных зон с рецептами.
        
        Returns:
            Список зон с id и status
        """
        zones = await fetch(
            """
            SELECT DISTINCT z.id, z.status
            FROM zones z
            JOIN zone_recipe_instances zri ON zri.zone_id = z.id
            WHERE z.status IN ('online', 'warning')
            """
        )
        return zones if zones else []

