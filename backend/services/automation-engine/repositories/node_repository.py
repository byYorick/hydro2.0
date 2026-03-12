"""
Node Repository - доступ к узлам.
"""
from typing import Dict, Any, List
from common.db import fetch


class NodeRepository:
    """Репозиторий для работы с узлами."""
    
    async def get_zone_nodes(self, zone_id: int) -> Dict[str, Dict[str, Any]]:
        """
        Получить узлы зоны, сгруппированные по типу и каналу.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict["type:channel", node_info]
        """
        rows = await fetch(
            """
            SELECT n.id, n.uid, n.type, nc.channel
            FROM nodes n
            LEFT JOIN node_channels nc ON nc.node_id = n.id
            WHERE n.zone_id = $1 AND n.status = 'online'
            """,
            zone_id,
        )
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            node_type = row["type"]
            channel = row["channel"] or "default"
            key = f"{node_type}:{channel}"
            if key not in result:
                result[key] = {
                    "node_id": row["id"],
                    "node_uid": row["uid"],
                    "type": node_type,
                    "channel": channel,
                }
        return result
    
    async def get_zones_nodes_batch(self, zone_ids: List[int]) -> Dict[int, Dict[str, Dict[str, Any]]]:
        """
        Получить узлы для нескольких зон одним запросом.
        
        Args:
            zone_ids: Список ID зон
        
        Returns:
            Dict[zone_id, Dict["type:channel", node_info]]
        """
        if not zone_ids:
            return {}
        
        rows = await fetch(
            """
            SELECT n.zone_id, n.id, n.uid, n.type, nc.channel
            FROM nodes n
            LEFT JOIN node_channels nc ON nc.node_id = n.id
            WHERE n.zone_id = ANY($1::int[]) AND n.status = 'online'
            """,
            zone_ids,
        )
        
        result: Dict[int, Dict[str, Dict[str, Any]]] = {}
        for row in rows:
            zone_id = row["zone_id"]
            if zone_id not in result:
                result[zone_id] = {}
            
            node_type = row["type"]
            channel = row["channel"] or "default"
            key = f"{node_type}:{channel}"
            if key not in result[zone_id]:
                result[zone_id][key] = {
                    "node_id": row["id"],
                    "node_uid": row["uid"],
                    "type": node_type,
                    "channel": channel,
                }
        
        # Добавляем пустые словари для зон без узлов
        for zone_id in zone_ids:
            if zone_id not in result:
                result[zone_id] = {}
        
        return result
    
    async def get_nodes_by_type(self, zone_id: int, node_type: str) -> List[Dict[str, Any]]:
        """
        Получить узлы зоны по типу.
        
        Args:
            zone_id: ID зоны
            node_type: Тип узла (light, climate, irrig, etc.)
        
        Returns:
            Список узлов указанного типа
        """
        rows = await fetch(
            """
            SELECT n.id, n.uid, n.type, nc.channel
            FROM nodes n
            LEFT JOIN node_channels nc ON nc.node_id = n.id
            WHERE n.zone_id = $1 AND n.type = $2 AND n.status = 'online'
            """,
            zone_id,
            node_type,
        )
        result: List[Dict[str, Any]] = []
        for row in rows:
            result.append({
                "node_id": row["id"],
                "node_uid": row["uid"],
                "type": row["type"],
                "channel": row["channel"] or "default",
            })
        return result

