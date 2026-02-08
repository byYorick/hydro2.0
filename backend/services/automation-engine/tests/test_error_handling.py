"""
Тесты для обработки ошибок в automation-engine.
Проверяет явный учет ошибок по зонам в gather.
"""
import pytest
from unittest.mock import AsyncMock
from main import process_zones_parallel


@pytest.mark.asyncio
async def test_process_zones_parallel_tracks_errors():
    """Тест отслеживания ошибок при обработке зон."""
    zone_service = AsyncMock()
    
    # Настраиваем: первая зона успешна, вторая падает с ошибкой
    async def process_zone(zone_id, **_kwargs):
        if zone_id == 1:
            return  # Успех
        else:
            raise ValueError(f"Error processing zone {zone_id}")
    
    zone_service.process_zone = process_zone
    
    zones = [
        {'id': 1, 'name': 'Zone 1'},
        {'id': 2, 'name': 'Zone 2'},
    ]
    
    results = await process_zones_parallel(zones, zone_service, max_concurrent=2)
    
    # Проверяем результаты
    assert results['total'] == 2
    assert results['success'] == 1
    assert results['failed'] == 1
    assert len(results['errors']) == 1
    assert results['errors'][0]['zone_id'] == 2


@pytest.mark.asyncio
async def test_process_zones_parallel_all_success():
    """Тест успешной обработки всех зон."""
    zone_service = AsyncMock()
    zone_service.process_zone = AsyncMock(return_value=None)
    
    zones = [
        {'id': 1, 'name': 'Zone 1'},
        {'id': 2, 'name': 'Zone 2'},
    ]
    
    results = await process_zones_parallel(zones, zone_service, max_concurrent=2)
    
    assert results['total'] == 2
    assert results['success'] == 2
    assert results['failed'] == 0
    assert len(results['errors']) == 0
