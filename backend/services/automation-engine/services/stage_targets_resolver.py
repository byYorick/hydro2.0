"""
Stage Targets Resolver - агрегация targets из фаз на основе стадий цикла.
"""
from typing import Dict, Any, Optional, List
import logging
from common.db import fetch

logger = logging.getLogger(__name__)


class StageTargetsResolver:
    """Резолвер targets для стадий цикла выращивания."""
    
    async def resolve_stage_targets(
        self,
        zone_id: int,
        grow_cycle: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Получить агрегированные targets для текущей стадии цикла.
        
        Args:
            zone_id: ID зоны
            grow_cycle: Данные активного цикла (опционально, если не передано - загружается)
        
        Returns:
            Dict с агрегированными targets для стадии или None
        """
        # Если цикл не передан, загружаем его
        if not grow_cycle:
            rows = await fetch(
                """
                SELECT 
                    gc.id,
                    gc.recipe_id,
                    gc.current_stage_code,
                    gc.status
                FROM grow_cycles gc
                WHERE gc.zone_id = $1
                    AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
                ORDER BY gc.started_at DESC
                LIMIT 1
                """,
                zone_id,
            )
            if not rows or len(rows) == 0:
                return None
            grow_cycle = rows[0]
        
        # Если нет активного цикла или стадии, возвращаем None
        if not grow_cycle or not grow_cycle.get("current_stage_code"):
            return None
        
        recipe_id = grow_cycle.get("recipe_id")
        current_stage_code = grow_cycle.get("current_stage_code")
        
        if not recipe_id:
            return None
        
        # Получаем phase_indices для текущей стадии из recipe_stage_maps
        stage_map = await self._get_stage_map(recipe_id, current_stage_code)
        if not stage_map:
            logger.warning(
                f"Zone {zone_id}: Stage map not found for stage_code={current_stage_code}, recipe_id={recipe_id}"
            )
            return None
        
        phase_indices = stage_map.get("phase_indices")
        targets_override = stage_map.get("targets_override")
        
        # Если есть override - используем его напрямую
        if targets_override:
            logger.debug(
                f"Zone {zone_id}: Using targets_override for stage {current_stage_code}"
            )
            return targets_override
        
        # Если нет phase_indices - возвращаем None
        if not phase_indices or not isinstance(phase_indices, list):
            logger.warning(
                f"Zone {zone_id}: No phase_indices for stage {current_stage_code}"
            )
            return None
        
        # Получаем targets из всех фаз, указанных в phase_indices
        phase_targets = await self._get_phase_targets(recipe_id, phase_indices)
        if not phase_targets:
            return None
        
        # Агрегируем targets из фаз
        aggregated_targets = self._aggregate_phase_targets(phase_targets)
        
        logger.debug(
            f"Zone {zone_id}: Resolved stage targets for stage {current_stage_code}, "
            f"phases={phase_indices}, aggregated_keys={list(aggregated_targets.keys())}"
        )
        
        return aggregated_targets
    
    async def _get_stage_map(
        self,
        recipe_id: int,
        stage_code: str
    ) -> Optional[Dict[str, Any]]:
        """
        Получить stage map для рецепта и стадии.
        
        Args:
            recipe_id: ID рецепта
            stage_code: Код стадии
        
        Returns:
            Dict с phase_indices и targets_override или None
        """
        rows = await fetch(
            """
            SELECT 
                rsm.phase_indices,
                rsm.targets_override,
                gst.code as stage_code
            FROM recipe_stage_maps rsm
            JOIN grow_stage_templates gst ON gst.id = rsm.stage_template_id
            WHERE rsm.recipe_id = $1
                AND gst.code = $2
            ORDER BY rsm.order_index
            LIMIT 1
            """,
            recipe_id,
            stage_code,
        )
        
        if rows and len(rows) > 0:
            return {
                "phase_indices": rows[0]["phase_indices"],
                "targets_override": rows[0]["targets_override"],
            }
        return None
    
    async def _get_phase_targets(
        self,
        recipe_id: int,
        phase_indices: List[int]
    ) -> List[Dict[str, Any]]:
        """
        Получить targets из указанных фаз рецепта.
        
        Args:
            recipe_id: ID рецепта
            phase_indices: Список индексов фаз
        
        Returns:
            Список dict с targets для каждой фазы
        """
        if not phase_indices:
            return []
        
        rows = await fetch(
            """
            SELECT 
                phase_index,
                targets
            FROM recipe_phases
            WHERE recipe_id = $1
                AND phase_index = ANY($2::int[])
            ORDER BY phase_index
            """,
            recipe_id,
            phase_indices,
        )
        
        result = []
        for row in rows:
            if row.get("targets"):
                result.append({
                    "phase_index": row["phase_index"],
                    "targets": row["targets"],
                })
        
        return result
    
    def _aggregate_phase_targets(
        self,
        phase_targets: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Агрегировать targets из нескольких фаз.
        
        Правила агрегации:
        - Для числовых значений: усреднение (если min/max - усреднение границ)
        - Для строковых значений: последнее значение
        - Для объектов (min/max): усреднение границ
        
        Args:
            phase_targets: Список dict с targets для каждой фазы
        
        Returns:
            Агрегированный dict с targets
        """
        if not phase_targets:
            return {}
        
        # Если только одна фаза - возвращаем её targets
        if len(phase_targets) == 1:
            return phase_targets[0]["targets"].copy() if phase_targets[0]["targets"] else {}
        
        aggregated = {}
        
        # Собираем все ключи из всех фаз
        all_keys = set()
        for phase in phase_targets:
            if phase.get("targets"):
                all_keys.update(phase["targets"].keys())
        
        # Агрегируем каждое поле
        for key in all_keys:
            values = []
            for phase in phase_targets:
                targets = phase.get("targets")
                if not targets:
                    continue
                value = targets.get(key)
                if value is not None:
                    values.append(value)
            
            if not values:
                continue
            
            # Агрегация в зависимости от типа значения
            aggregated[key] = self._aggregate_value(values)
        
        return aggregated
    
    def _aggregate_value(self, values: List[Any]) -> Any:
        """
        Агрегировать список значений.
        
        Args:
            values: Список значений для агрегации
        
        Returns:
            Агрегированное значение
        """
        if not values:
            return None
        
        # Если только одно значение - возвращаем его
        if len(values) == 1:
            return values[0]
        
        # Определяем тип первого значения
        first_value = values[0]
        
        # Если это dict (например, ph: {min: 5.5, max: 6.0})
        if isinstance(first_value, dict):
            # Агрегируем min/max отдельно
            aggregated = {}
            for key in first_value.keys():
                key_values = [
                    v.get(key) for v in values
                    if isinstance(v, dict) and v.get(key) is not None
                ]
                if key_values:
                    aggregated[key] = sum(key_values) / len(key_values)
            return aggregated
        
        # Если это число - усредняем
        if isinstance(first_value, (int, float)):
            return sum(values) / len(values)
        
        # Для строк и других типов - возвращаем последнее значение
        return values[-1]

