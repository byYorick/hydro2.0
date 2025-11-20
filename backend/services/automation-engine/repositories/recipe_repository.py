"""
Recipe Repository - доступ к рецептам и фазам.
"""
from typing import Dict, Any, Optional, List
from common.db import fetch


class RecipeRepository:
    """Репозиторий для работы с рецептами."""
    
    async def get_zone_recipe_and_targets(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить активный рецепт и targets для зоны.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict с zone_id, phase_index, targets, phase_name или None
        """
        rows = await fetch(
            """
            SELECT zri.zone_id, zri.current_phase_index, rp.targets, rp.name as phase_name
            FROM zone_recipe_instances zri
            JOIN recipe_phases rp ON rp.recipe_id = zri.recipe_id AND rp.phase_index = zri.current_phase_index
            WHERE zri.zone_id = $1
            """,
            zone_id,
        )
        if rows and len(rows) > 0:
            return {
                "zone_id": rows[0]["zone_id"],
                "phase_index": rows[0]["current_phase_index"],
                "targets": rows[0]["targets"],
                "phase_name": rows[0]["phase_name"],
            }
        return None
    
    async def get_zones_recipes_batch(self, zone_ids: List[int]) -> Dict[int, Optional[Dict[str, Any]]]:
        """
        Получить рецепты и targets для нескольких зон одним запросом.
        
        Args:
            zone_ids: Список ID зон
        
        Returns:
            Dict[zone_id, recipe_info] или None если рецепта нет
        """
        if not zone_ids:
            return {}
        
        rows = await fetch(
            """
            SELECT zri.zone_id, zri.current_phase_index, rp.targets, rp.name as phase_name
            FROM zone_recipe_instances zri
            JOIN recipe_phases rp ON rp.recipe_id = zri.recipe_id AND rp.phase_index = zri.current_phase_index
            WHERE zri.zone_id = ANY($1::int[])
            """,
            zone_ids,
        )
        
        result: Dict[int, Optional[Dict[str, Any]]] = {}
        for row in rows:
            zone_id = row["zone_id"]
            result[zone_id] = {
                "zone_id": zone_id,
                "phase_index": row["current_phase_index"],
                "targets": row["targets"],
                "phase_name": row["phase_name"],
            }
        
        # Добавляем None для зон без рецептов
        for zone_id in zone_ids:
            if zone_id not in result:
                result[zone_id] = None
        
        return result
    
    async def get_zone_data_batch(self, zone_id: int) -> Dict[str, Any]:
        """
        Получить все данные зоны одним запросом (recipe, telemetry, nodes, capabilities).
        Оптимизированный метод для получения всех данных одной зоны.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict с recipe_info, telemetry, nodes, capabilities
        """
        rows = await fetch(
            """
            WITH zone_info AS (
                SELECT 
                    z.id as zone_id,
                    z.capabilities,
                    zri.current_phase_index,
                    rp.targets,
                    rp.name as phase_name
                FROM zones z
                LEFT JOIN zone_recipe_instances zri ON zri.zone_id = z.id
                LEFT JOIN recipe_phases rp ON rp.recipe_id = zri.recipe_id 
                    AND rp.phase_index = zri.current_phase_index
                WHERE z.id = $1
            ),
            telemetry_data AS (
                SELECT metric_type, value
                FROM telemetry_last
                WHERE zone_id = $1
            ),
            nodes_data AS (
                SELECT n.id, n.uid, n.type, nc.channel
                FROM nodes n
                LEFT JOIN node_channels nc ON nc.node_id = n.id
                WHERE n.zone_id = $1 AND n.status = 'online'
            )
            SELECT 
                (SELECT row_to_json(zone_info) FROM zone_info) as zone_info,
                (SELECT json_object_agg(metric_type, value) FROM telemetry_data) as telemetry,
                (SELECT json_agg(row_to_json(nodes_data)) FROM nodes_data) as nodes
            """,
            zone_id,
        )
        
        if not rows or not rows[0]:
            return {
                "recipe_info": None,
                "telemetry": {},
                "nodes": {},
                "capabilities": {}
            }
        
        result = rows[0]
        zone_info = result.get("zone_info") or {}
        telemetry = result.get("telemetry") or {}
        nodes_list = result.get("nodes") or []
        
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
        
        # Формируем recipe_info
        recipe_info = None
        if zone_info.get("targets") is not None:
            recipe_info = {
                "zone_id": zone_id,
                "phase_index": zone_info.get("current_phase_index"),
                "targets": zone_info.get("targets"),
                "phase_name": zone_info.get("phase_name"),
            }
        
        return {
            "recipe_info": recipe_info,
            "telemetry": telemetry,
            "nodes": nodes_dict,
            "capabilities": capabilities
        }

