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
        Получить список активных зон с grow cycles.

        Returns:
            Список зон с id и status
        """
        zones = await fetch(
            """
            SELECT DISTINCT z.id, z.status
            FROM zones z
            JOIN grow_cycles gc ON gc.zone_id = z.id
            WHERE z.status IN ('online', 'warning', 'RUNNING', 'PAUSED')
            AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
            """
        )
        return zones if zones else []

    async def get_zone_data_batch(self, zone_id: int) -> Dict[str, Any]:
        """
        Получить данные зоны одним запросом (legacy формат).

        Возвращает recipe_info, telemetry, nodes, capabilities.
        """
        rows = await fetch(
            """
            SELECT
                z.id as zone_id,
                z.capabilities,
                gc.id as recipe_id,
                gcp.index as phase_index,
                gcp.targets,
                gcp.name as phase_name,
                s.type as metric_type,
                tl.last_value as value,
                n.id as node_id,
                n.uid as node_uid,
                n.type as node_type,
                nc.channel,
                nc.id as node_channel_id
            FROM zones z
            LEFT JOIN grow_cycles gc ON gc.zone_id = z.id AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
            LEFT JOIN grow_cycle_phases gcp ON gcp.grow_cycle_id = gc.id AND gcp.status = 'active'
            LEFT JOIN sensors s ON s.zone_id = z.id AND s.is_active = TRUE
            LEFT JOIN telemetry_last tl ON tl.sensor_id = s.id
            LEFT JOIN nodes n ON n.zone_id = z.id AND n.status = 'online'
            LEFT JOIN node_channels nc ON nc.node_id = n.id
            WHERE z.id = $1
            """,
            zone_id,
        )

        if not rows:
            return {
                "recipe_info": None,
                "telemetry": {},
                "nodes": {},
                "capabilities": {},
            }

        recipe_info: Optional[Dict[str, Any]] = None
        telemetry: Dict[str, Optional[float]] = {}
        nodes: Dict[str, Dict[str, Any]] = {}
        capabilities = self.DEFAULT_CAPABILITIES.copy()

        for row in rows:
            if not recipe_info and row.get("recipe_id") is not None:
                recipe_info = {
                    "zone_id": row.get("zone_id", zone_id),
                    "recipe_id": row.get("recipe_id"),
                    "phase_index": row.get("phase_index"),
                    "targets": row.get("targets"),
                    "phase_name": row.get("phase_name"),
                }

            metric_type = row.get("metric_type")
            if metric_type:
                telemetry[metric_type] = row.get("value")

            node_uid = row.get("node_uid")
            node_type = row.get("node_type") or ""
            channel = row.get("channel") or "default"
            if node_uid:
                key = f"{node_type}:{channel}"
                if key not in nodes:
                    nodes[key] = {
                        "node_id": row.get("node_id"),
                        "node_uid": node_uid,
                        "type": node_type,
                        "node_channel_id": row.get("node_channel_id"),
                        "channel": channel,
                    }

            row_capabilities = row.get("capabilities") or {}
            if row_capabilities:
                capabilities = row_capabilities

        return {
            "recipe_info": recipe_info,
            "telemetry": telemetry,
            "nodes": nodes,
            "capabilities": capabilities,
        }
