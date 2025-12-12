"""
Grow Cycle Repository - доступ к циклам выращивания.
"""
from typing import Dict, Any, Optional, List
from common.db import fetch
from infrastructure.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError


class GrowCycleRepository:
    """Репозиторий для работы с циклами выращивания."""
    
    def __init__(self, db_circuit_breaker: Optional[CircuitBreaker] = None):
        """
        Инициализация репозитория.
        
        Args:
            db_circuit_breaker: Circuit breaker для БД (опционально)
        """
        self.db_circuit_breaker = db_circuit_breaker
    
    async def get_active_grow_cycle(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить активный цикл выращивания для зоны.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict с данными цикла или None если нет активного цикла
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        async def _fetch():
            return await fetch(
                """
                SELECT 
                    gc.id,
                    gc.greenhouse_id,
                    gc.zone_id,
                    gc.plant_id,
                    gc.recipe_id,
                    gc.zone_recipe_instance_id,
                    gc.status,
                    gc.started_at,
                    gc.recipe_started_at,
                    gc.expected_harvest_at,
                    gc.actual_harvest_at,
                    gc.batch_label,
                    gc.notes,
                    gc.settings,
                    gc.current_stage_code,
                    gc.current_stage_started_at,
                    zri.current_phase_index,
                    rp.targets,
                    rp.name as phase_name
                FROM grow_cycles gc
                LEFT JOIN zone_recipe_instances zri ON zri.id = gc.zone_recipe_instance_id
                LEFT JOIN recipe_phases rp ON rp.recipe_id = zri.recipe_id 
                    AND rp.phase_index = zri.current_phase_index
                WHERE gc.zone_id = $1
                    AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
                ORDER BY gc.started_at DESC
                LIMIT 1
                """,
                zone_id,
            )
        
        if self.db_circuit_breaker:
            rows = await self.db_circuit_breaker.call(_fetch)
        else:
            rows = await _fetch()
        
        if rows and len(rows) > 0:
            row = rows[0]
            return {
                "id": row["id"],
                "greenhouse_id": row["greenhouse_id"],
                "zone_id": row["zone_id"],
                "plant_id": row["plant_id"],
                "recipe_id": row["recipe_id"],
                "zone_recipe_instance_id": row["zone_recipe_instance_id"],
                "status": row["status"],
                "started_at": row["started_at"],
                "recipe_started_at": row["recipe_started_at"],
                "expected_harvest_at": row["expected_harvest_at"],
                "actual_harvest_at": row["actual_harvest_at"],
                "batch_label": row["batch_label"],
                "notes": row["notes"],
                "settings": row["settings"],
                "current_stage_code": row["current_stage_code"],
                "current_stage_started_at": row["current_stage_started_at"],
                "current_phase_index": row["current_phase_index"],
                "targets": row["targets"],  # Fallback targets из фазы (для обратной совместимости)
                "phase_name": row["phase_name"],
            }
        return None
    
    async def get_zones_grow_cycles_batch(self, zone_ids: List[int]) -> Dict[int, Optional[Dict[str, Any]]]:
        """
        Получить активные циклы для нескольких зон одним запросом.
        
        Args:
            zone_ids: Список ID зон
        
        Returns:
            Dict[zone_id, grow_cycle_info] или None если нет активного цикла
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        if not zone_ids:
            return {}
        
        async def _fetch():
            return await fetch(
                """
                SELECT 
                    gc.id,
                    gc.greenhouse_id,
                    gc.zone_id,
                    gc.plant_id,
                    gc.recipe_id,
                    gc.zone_recipe_instance_id,
                    gc.status,
                    gc.started_at,
                    gc.recipe_started_at,
                    gc.expected_harvest_at,
                    gc.actual_harvest_at,
                    gc.batch_label,
                    gc.notes,
                    gc.settings,
                    gc.current_stage_code,
                    gc.current_stage_started_at,
                    zri.current_phase_index,
                    rp.targets,
                    rp.name as phase_name
                FROM grow_cycles gc
                LEFT JOIN zone_recipe_instances zri ON zri.id = gc.zone_recipe_instance_id
                LEFT JOIN recipe_phases rp ON rp.recipe_id = zri.recipe_id 
                    AND rp.phase_index = zri.current_phase_index
                WHERE gc.zone_id = ANY($1::int[])
                    AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
                ORDER BY gc.zone_id, gc.started_at DESC
                """,
                zone_ids,
            )
        
        if self.db_circuit_breaker:
            rows = await self.db_circuit_breaker.call(_fetch)
        else:
            rows = await _fetch()
        
        result: Dict[int, Optional[Dict[str, Any]]] = {}
        # Группируем по zone_id, берём первый (самый свежий) для каждой зоны
        seen_zones = set()
        for row in rows:
            zone_id = row["zone_id"]
            if zone_id in seen_zones:
                continue  # Уже есть активный цикл для этой зоны
            seen_zones.add(zone_id)
            
            result[zone_id] = {
                "id": row["id"],
                "greenhouse_id": row["greenhouse_id"],
                "zone_id": row["zone_id"],
                "plant_id": row["plant_id"],
                "recipe_id": row["recipe_id"],
                "zone_recipe_instance_id": row["zone_recipe_instance_id"],
                "status": row["status"],
                "started_at": row["started_at"],
                "recipe_started_at": row["recipe_started_at"],
                "expected_harvest_at": row["expected_harvest_at"],
                "actual_harvest_at": row["actual_harvest_at"],
                "batch_label": row["batch_label"],
                "notes": row["notes"],
                "settings": row["settings"],
                "current_stage_code": row["current_stage_code"],
                "current_stage_started_at": row["current_stage_started_at"],
                "current_phase_index": row["current_phase_index"],
                "targets": row["targets"],  # Fallback targets из фазы
                "phase_name": row["phase_name"],
            }
        
        # Добавляем None для зон без активных циклов
        for zone_id in zone_ids:
            if zone_id not in result:
                result[zone_id] = None
        
        return result

