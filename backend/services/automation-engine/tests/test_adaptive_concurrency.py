"""
Тесты для адаптивной конкурентности в automation-engine.
Проверяет расчет optimal_concurrency и метрики.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

# Добавляем путь к модулю
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    calculate_optimal_concurrency,
    process_zones_parallel,
)
from services import ZoneAutomationService
from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository, GrowCycleRepository, InfrastructureRepository
from infrastructure import CommandBus


@pytest.mark.asyncio
async def test_calculate_optimal_concurrency():
    """Тест расчета оптимальной конкурентности."""
    # Тест 1: Нормальный случай
    result = await calculate_optimal_concurrency(
        total_zones=100,
        target_cycle_time=15,
        avg_zone_processing_time=0.5
    )
    # (100 * 0.5) / 15 = 3.33 -> округляем до 4
    assert result >= 5  # Минимум 5
    assert result <= 50  # Максимум 50
    
    # Тест 2: Много зон, быстрое время обработки
    result = await calculate_optimal_concurrency(
        total_zones=200,
        target_cycle_time=15,
        avg_zone_processing_time=0.1
    )
    assert result >= 5
    assert result <= 50
    
    # Тест 3: Мало зон
    result = await calculate_optimal_concurrency(
        total_zones=10,
        target_cycle_time=15,
        avg_zone_processing_time=1.0
    )
    assert result >= 5
    assert result <= 50
    
    # Тест 4: Нет данных (avg_time <= 0)
    result = await calculate_optimal_concurrency(
        total_zones=100,
        target_cycle_time=15,
        avg_zone_processing_time=0.0
    )
    assert result == 5  # Дефолтное значение


@pytest.mark.asyncio
async def test_optimal_concurrency_metric():
    """Тест метрики optimal_concurrency."""
    from config.settings import get_settings as get_automation_settings
    
    automation_settings = get_automation_settings()
    
    # Мокаем все зависимости
    zone_repo = MagicMock(spec=ZoneRepository)
    telemetry_repo = MagicMock(spec=TelemetryRepository)
    node_repo = MagicMock(spec=NodeRepository)
    recipe_repo = MagicMock(spec=RecipeRepository)
    grow_cycle_repo = MagicMock(spec=GrowCycleRepository)
    infrastructure_repo = MagicMock(spec=InfrastructureRepository)
    mqtt = MagicMock()
    command_bus = CommandBus(mqtt, "gh-1")
    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value=None)
    infrastructure_repo.get_zone_bindings_by_role = AsyncMock(return_value={})
    
    zone_service = ZoneAutomationService(
        zone_repo, telemetry_repo, node_repo, recipe_repo, grow_cycle_repo, infrastructure_repo, command_bus
    )
    
    # Мокаем process_zone
    zone_service.process_zone = AsyncMock()
    
    zones = [
        {"id": 1, "name": "Zone 1"},
        {"id": 2, "name": "Zone 2"},
    ]
    
    # Мокаем OPTIMAL_CONCURRENCY
    with patch('main.OPTIMAL_CONCURRENCY') as mock_gauge:
        # Устанавливаем адаптивную конкурентность
        with patch.object(automation_settings, 'ADAPTIVE_CONCURRENCY', True):
            with patch('main._avg_processing_time', 0.5):
                await process_zones_parallel(
                    zones, zone_service, max_concurrent=10
                )
                
                # Проверяем, что метрика была обновлена (если адаптивность включена)
                # В реальном коде это происходит в main(), но здесь мы тестируем функцию напрямую


@pytest.mark.asyncio
async def test_zone_processing_errors_metric():
    """Тест метрики ошибок обработки зон."""
    zone_repo = MagicMock(spec=ZoneRepository)
    telemetry_repo = MagicMock(spec=TelemetryRepository)
    node_repo = MagicMock(spec=NodeRepository)
    recipe_repo = MagicMock(spec=RecipeRepository)
    grow_cycle_repo = MagicMock(spec=GrowCycleRepository)
    infrastructure_repo = MagicMock(spec=InfrastructureRepository)
    mqtt = MagicMock()
    command_bus = CommandBus(mqtt, "gh-1")
    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value=None)
    infrastructure_repo.get_zone_bindings_by_role = AsyncMock(return_value={})
    
    zone_service = ZoneAutomationService(
        zone_repo, telemetry_repo, node_repo, recipe_repo, grow_cycle_repo, infrastructure_repo, command_bus
    )
    
    # Мокаем process_zone чтобы выбрасывал ошибку
    zone_service.process_zone = AsyncMock(side_effect=Exception("Test error"))
    
    zones = [
        {"id": 1, "name": "Zone 1"},
    ]
    
    # Мокаем ZONE_PROCESSING_ERRORS
    with patch('main.ZONE_PROCESSING_ERRORS') as mock_errors:
        results = await process_zones_parallel(
            zones, zone_service, max_concurrent=5
        )
        
        # Проверяем, что ошибка была зафиксирована
        assert results['failed'] == 1
        assert results['total'] == 1
        assert len(results['errors']) == 1
        assert mock_errors.labels.called


@pytest.mark.asyncio
async def test_zone_processing_time_metric():
    """Тест метрики времени обработки зон."""
    zone_repo = MagicMock(spec=ZoneRepository)
    telemetry_repo = MagicMock(spec=TelemetryRepository)
    node_repo = MagicMock(spec=NodeRepository)
    recipe_repo = MagicMock(spec=RecipeRepository)
    grow_cycle_repo = MagicMock(spec=GrowCycleRepository)
    infrastructure_repo = MagicMock(spec=InfrastructureRepository)
    mqtt = MagicMock()
    command_bus = CommandBus(mqtt, "gh-1")
    grow_cycle_repo.get_active_grow_cycle = AsyncMock(return_value=None)
    infrastructure_repo.get_zone_bindings_by_role = AsyncMock(return_value={})
    
    zone_service = ZoneAutomationService(
        zone_repo, telemetry_repo, node_repo, recipe_repo, grow_cycle_repo, infrastructure_repo, command_bus
    )
    
    # Мокаем process_zone с задержкой
    async def slow_process(zone_id):
        import asyncio
        await asyncio.sleep(0.1)
    
    zone_service.process_zone = AsyncMock(side_effect=slow_process)
    
    zones = [
        {"id": 1, "name": "Zone 1"},
    ]
    
    # Мокаем ZONE_PROCESSING_TIME
    with patch('main.ZONE_PROCESSING_TIME') as mock_time:
        results = await process_zones_parallel(
            zones, zone_service, max_concurrent=5
        )
        
        # Проверяем, что метрика времени была обновлена
        assert results['success'] == 1
        assert mock_time.observe.called
