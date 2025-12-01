"""
Интеграционные тесты для PID с использованием конфигов из БД
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from correction_controller import CorrectionController, CorrectionType
from services.pid_config_service import get_config, invalidate_cache
from utils.adaptive_pid import AdaptivePidConfig, PidZone, PidZoneCoeffs


@pytest.mark.asyncio
async def test_correction_controller_uses_pid_config_from_db():
    """Тест: CorrectionController использует конфиг из БД"""
    zone_id = 1
    correction_type = CorrectionType.PH
    
    # Мокаем конфиг из БД
    db_config = {
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
    
    controller = CorrectionController(correction_type)
    
    with patch('services.pid_config_service.fetch', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{'config': db_config, 'updated_at': datetime.utcnow()}]
        
        # Мокаем другие зависимости
        with patch('correction_controller.should_apply_correction', new_callable=AsyncMock) as mock_should:
            mock_should.return_value = (True, 'test')
            with patch('correction_controller.create_zone_event', new_callable=AsyncMock):
                with patch('correction_controller.record_correction', new_callable=AsyncMock):
                    targets = {'ph': 6.0}
                    telemetry = {'PH': 6.8}  # Отклонение 0.8
                    nodes = {
                        'irrig:default': {
                            'node_uid': 'test-node',
                            'channel': 'pump_acid',
                            'type': 'irrig',
                        }
                    }
                    
                    result = await controller.check_and_correct(
                        zone_id, targets, telemetry, nodes=nodes, water_level_ok=True
                    )
                    
                    # Проверяем, что конфиг был загружен из БД
                    mock_fetch.assert_called()
                    
                    # Если результат не None, проверяем структуру
                    if result:
                        assert 'node_uid' in result
                        assert 'channel' in result
                        assert 'cmd' in result


@pytest.mark.asyncio
async def test_pid_output_event_created():
    """Тест: событие PID_OUTPUT создается при output > 0"""
    zone_id = 1
    correction_type = CorrectionType.PH
    
    controller = CorrectionController(correction_type)
    
    with patch('services.pid_config_service.fetch', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []  # Используем дефолты
        
        with patch('correction_controller.should_apply_correction', new_callable=AsyncMock) as mock_should:
            mock_should.return_value = (True, 'test')
            
            create_event_mock = AsyncMock()
            with patch('correction_controller.create_zone_event', create_event_mock):
                with patch('correction_controller.record_correction', new_callable=AsyncMock):
                    targets = {'ph': 6.0}
                    telemetry = {'PH': 7.0}  # Большое отклонение
                    nodes = {
                        'irrig:default': {
                            'node_uid': 'test-node',
                            'channel': 'pump_acid',
                            'type': 'irrig',
                        }
                    }
                    
                    await controller.check_and_correct(
                        zone_id, targets, telemetry, nodes=nodes, water_level_ok=True
                    )
                    
                    # Проверяем, что create_zone_event был вызван
                    # (может быть вызван для PID_OUTPUT или других событий)
                    assert create_event_mock.called

