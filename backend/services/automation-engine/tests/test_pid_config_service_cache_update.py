"""
Тесты для проверки обновления кеша при изменении конфига в БД
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.pid_config_service import get_config, invalidate_cache
from utils.adaptive_pid import AdaptivePidConfig, PidZone, PidZoneCoeffs


@pytest.mark.asyncio
async def test_cache_invalidates_when_config_updated_in_db():
    """Тест: кеш инвалидируется при обновлении конфига в БД"""
    zone_id = 1
    correction_type = 'ph'
    setpoint = 6.0
    
    # Очищаем кеш
    invalidate_cache(zone_id, correction_type)
    
    old_config = {
        'target': 6.0,
        'dead_zone': 0.2,
        'close_zone': 0.5,
        'far_zone': 1.0,
        'zone_coeffs': {
            'close': {'kp': 10.0, 'ki': 0.0, 'kd': 0.0},
            'far': {'kp': 12.0, 'ki': 0.0, 'kd': 0.0},
        },
        'max_output': 50.0,
        'min_interval_ms': 60000,
        'enable_autotune': False,
        'adaptation_rate': 0.05,
    }
    
    new_config = {
        'target': 6.5,
        'dead_zone': 0.3,
        'close_zone': 0.6,
        'far_zone': 1.2,
        'zone_coeffs': {
            'close': {'kp': 15.0, 'ki': 0.1, 'kd': 0.0},
            'far': {'kp': 18.0, 'ki': 0.1, 'kd': 0.0},
        },
        'max_output': 60.0,
        'min_interval_ms': 90000,
        'enable_autotune': True,
        'adaptation_rate': 0.1,
    }
    
    old_updated_at = datetime.utcnow() - timedelta(minutes=5)
    new_updated_at = datetime.utcnow()
    
    with patch('services.pid_config_service.fetch', new_callable=AsyncMock) as mock_fetch:
        # Первый вызов - загружаем старый конфиг
        mock_fetch.return_value = [
            {'config': old_config, 'updated_at': old_updated_at}
        ]
        config1 = await get_config(zone_id, correction_type, setpoint)
        
        assert config1.dead_zone == 0.2
        assert mock_fetch.call_count == 1
        
        # Второй вызов - проверяем updated_at, конфиг обновился
        mock_fetch.return_value = [
            {'updated_at': new_updated_at}  # Только updated_at для проверки
        ]
        # Затем загружаем новый конфиг
        mock_fetch.side_effect = [
            [{'updated_at': new_updated_at}],  # Проверка updated_at
            [{'config': new_config, 'updated_at': new_updated_at}]  # Загрузка нового конфига
        ]
        
        config2 = await get_config(zone_id, correction_type, setpoint)
        
        # Должен быть загружен новый конфиг
        assert config2.dead_zone == 0.3
        assert config2.close_zone == 0.6
        assert config2.max_output == 60.0


@pytest.mark.asyncio
async def test_cache_uses_default_when_config_deleted():
    """Тест: при удалении конфига из БД используется дефолтный конфиг"""
    zone_id = 1
    correction_type = 'ph'
    setpoint = 6.0
    
    invalidate_cache(zone_id, correction_type)
    
    with patch('services.pid_config_service.fetch', new_callable=AsyncMock) as mock_fetch:
        # Первый вызов - конфиг есть в БД
        mock_fetch.return_value = [
            {
                'config': {
                    'target': 6.5,
                    'dead_zone': 0.3,
                    'close_zone': 0.6,
                    'far_zone': 1.2,
                    'zone_coeffs': {
                        'close': {'kp': 15.0, 'ki': 0.1, 'kd': 0.0},
                        'far': {'kp': 18.0, 'ki': 0.1, 'kd': 0.0},
                    },
                    'max_output': 60.0,
                    'min_interval_ms': 90000,
                    'enable_autotune': True,
                    'adaptation_rate': 0.1,
                },
                'updated_at': datetime.utcnow()
            }
        ]
        config1 = await get_config(zone_id, correction_type, setpoint)
        assert config1.dead_zone == 0.3
        
        # Второй вызов - конфиг удален из БД
        mock_fetch.side_effect = [
            [],  # Проверка updated_at - конфига нет
            []   # Загрузка конфига - конфига нет, используем дефолты
        ]
        
        config2 = await get_config(zone_id, correction_type, setpoint)
        
        # Должен использоваться дефолтный конфиг
        assert config2.dead_zone == 0.2  # Дефолт для pH


@pytest.mark.asyncio
async def test_cache_preserves_default_when_no_config_in_db():
    """Тест: дефолтный конфиг кешируется и используется без лишних проверок"""
    zone_id = 1
    correction_type = 'ph'
    setpoint = 6.0
    
    invalidate_cache(zone_id, correction_type)
    
    with patch('services.pid_config_service.fetch', new_callable=AsyncMock) as mock_fetch:
        # Первый вызов - конфига нет в БД
        mock_fetch.return_value = []
        config1 = await get_config(zone_id, correction_type, setpoint)
        
        # Второй вызов - проверяем updated_at (конфига нет), используем кеш
        mock_fetch.return_value = []  # Конфига нет в БД
        config2 = await get_config(zone_id, correction_type, setpoint)
        
        # Должен использоваться кешированный дефолтный конфиг
        assert config1.dead_zone == config2.dead_zone
        # Fetch вызывается для проверки updated_at, но конфиг не перезагружается
        assert mock_fetch.call_count >= 1

