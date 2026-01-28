"""
Grow Cycle Repository - доступ к циклам выращивания.
Использует LaravelApiRepository для получения effective targets вместо прямых SQL запросов к legacy таблицам.
"""
from typing import Dict, Any, Optional, List
import logging
from infrastructure.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from repositories.laravel_api_repository import LaravelApiRepository
from common.effective_targets import parse_effective_targets
from common.db import fetch

logger = logging.getLogger(__name__)


class GrowCycleRepository:
    """Репозиторий для работы с циклами выращивания."""

    def __init__(self, laravel_api_repo: Optional[LaravelApiRepository] = None, db_circuit_breaker: Optional[CircuitBreaker] = None):
        """
        Инициализация репозитория.

        Args:
            laravel_api_repo: Репозиторий для работы с Laravel API
            db_circuit_breaker: Circuit breaker для БД (опционально, для обратной совместимости)
        """
        self.laravel_api_repo = laravel_api_repo or LaravelApiRepository()
        self.db_circuit_breaker = db_circuit_breaker
    
    async def get_active_grow_cycle(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить активный цикл выращивания для зоны через batch effective-targets API.

        Args:
            zone_id: ID зоны

        Returns:
            Dict с данными цикла или None если нет активного цикла

        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        # Получаем effective targets для зоны через batch API
        batch_result = await self.get_zones_grow_cycles_batch([zone_id])
        cycle_data = batch_result.get(zone_id)

        if not cycle_data:
            return None

        # Преобразуем формат effective-targets в формат, ожидаемый automation-engine
        return {
            "id": cycle_data["cycle_id"],
            "zone_id": zone_id,
            "status": "RUNNING",  # Предполагаем, что если есть effective targets, цикл активен
            "targets": cycle_data["targets"],
            "phase_name": cycle_data["phase"]["name"] if cycle_data.get("phase") else None,
            "current_stage_code": cycle_data["phase"]["code"] if cycle_data.get("phase") else None,
        }
    
    async def get_zones_grow_cycles_batch(self, zone_ids: List[int]) -> Dict[int, Optional[Dict[str, Any]]]:
        """
        Получить effective targets для нескольких зон через LaravelApiRepository.

        Args:
            zone_ids: Список ID зон

        Returns:
            Dict[zone_id, effective_targets_data] или None если нет активного цикла

        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        if not zone_ids:
            return {}

        async def _fetch():
            return await self.laravel_api_repo.get_effective_targets_batch(zone_ids)

        if self.db_circuit_breaker:
            api_result = await self.db_circuit_breaker.call(_fetch)
        else:
            api_result = await _fetch()

        # Преобразуем результат API в ожидаемый формат
        result: Dict[int, Optional[Dict[str, Any]]] = {}

        for zone_id in zone_ids:
            zone_data = api_result.get(zone_id)
            if zone_data and "error" not in zone_data:
                try:
                    parsed = parse_effective_targets(zone_data)
                    result[zone_id] = parsed.model_dump()
                except Exception as exc:
                    logger.warning(
                        "Failed to parse effective targets",
                        extra={"zone_id": zone_id, "error": str(exc)},
                    )
                    result[zone_id] = None
            else:
                result[zone_id] = None

        return result

    async def get_current_phase_timing(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить тайминг текущей фазы цикла выращивания для зоны.

        Возвращает данные, необходимые для фазовых переходов.
        """
        async def _fetch():
            return await fetch(
                """
                SELECT
                    gc.id as grow_cycle_id,
                    gc.status,
                    gc.phase_started_at,
                    gc.recipe_started_at,
                    gcp.id as phase_id,
                    gcp.phase_index,
                    gcp.duration_hours,
                    gcp.duration_days,
                    (
                        SELECT MAX(phase_index)
                        FROM grow_cycle_phases
                        WHERE grow_cycle_id = gc.id
                    ) as max_phase_index
                FROM grow_cycles gc
                JOIN grow_cycle_phases gcp ON gcp.id = gc.current_phase_id
                WHERE gc.zone_id = $1
                  AND gc.status = 'RUNNING'
                ORDER BY gc.id DESC
                LIMIT 1
                """,
                zone_id,
            )

        if self.db_circuit_breaker:
            rows = await self.db_circuit_breaker.call(_fetch)
        else:
            rows = await _fetch()

        if not rows:
            return None

        row = rows[0]
        return {
            "grow_cycle_id": row.get("grow_cycle_id"),
            "status": row.get("status"),
            "phase_started_at": row.get("phase_started_at"),
            "recipe_started_at": row.get("recipe_started_at"),
            "phase_id": row.get("phase_id"),
            "phase_index": row.get("phase_index"),
            "duration_hours": row.get("duration_hours"),
            "duration_days": row.get("duration_days"),
            "max_phase_index": row.get("max_phase_index"),
        }

    async def advance_phase(self, grow_cycle_id: int) -> bool:
        """Продвинуть фазу цикла выращивания через Laravel API (internal)."""
        async def _call():
            return await self.laravel_api_repo.advance_grow_cycle_phase(grow_cycle_id)

        if self.db_circuit_breaker:
            return await self.db_circuit_breaker.call(_call)
        return await _call()

    async def harvest_cycle(self, grow_cycle_id: int) -> bool:
        """Завершить цикл выращивания через Laravel API (internal)."""
        async def _call():
            return await self.laravel_api_repo.harvest_grow_cycle(grow_cycle_id)

        if self.db_circuit_breaker:
            return await self.db_circuit_breaker.call(_call)
        return await _call()
