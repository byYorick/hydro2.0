"""
Тесты для проверки очистки PID инстансов при удалении зоны
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.zone_automation_service import ZoneAutomationService
from correction_controller import CorrectionController, CorrectionType
from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository
from infrastructure.command_bus import CommandBus


@pytest.mark.asyncio
async def test_zone_deletion_clears_pid_instances():
    """Тест: при удалении зоны очищаются PID инстансы"""
    zone_id = 1
    
    # Создаем моки репозиториев
    zone_repo = MagicMock(spec=ZoneRepository)
    telemetry_repo = MagicMock(spec=TelemetryRepository)
    node_repo = MagicMock(spec=NodeRepository)
    recipe_repo = MagicMock(spec=RecipeRepository)
    command_bus = MagicMock(spec=CommandBus)
    
    # Создаем сервис
    service = ZoneAutomationService(
        zone_repo, telemetry_repo, node_repo, recipe_repo, command_bus
    )
    
    # Создаем PID инстансы для зоны
    service.ph_controller._pid_by_zone[zone_id] = MagicMock()
    service.ph_controller._last_pid_tick[zone_id] = 123.45
    service.ec_controller._pid_by_zone[zone_id] = MagicMock()
    service.ec_controller._last_pid_tick[zone_id] = 123.45
    
    # Мокаем fetch для проверки существования зоны (зона не найдена)
    with patch('common.db.fetch', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []  # Зона не найдена
        
        # Вызываем проверку удаления зоны
        await service._check_zone_deletion(zone_id)
        
        # Проверяем, что PID инстансы очищены
        assert zone_id not in service.ph_controller._pid_by_zone
        assert zone_id not in service.ph_controller._last_pid_tick
        assert zone_id not in service.ec_controller._pid_by_zone
        assert zone_id not in service.ec_controller._last_pid_tick


@pytest.mark.asyncio
async def test_zone_deletion_does_not_clear_when_zone_exists():
    """Тест: PID инстансы не очищаются, если зона существует"""
    zone_id = 1
    
    # Создаем моки репозиториев
    zone_repo = MagicMock(spec=ZoneRepository)
    telemetry_repo = MagicMock(spec=TelemetryRepository)
    node_repo = MagicMock(spec=NodeRepository)
    recipe_repo = MagicMock(spec=RecipeRepository)
    command_bus = MagicMock(spec=CommandBus)
    
    # Создаем сервис
    service = ZoneAutomationService(
        zone_repo, telemetry_repo, node_repo, recipe_repo, command_bus
    )
    
    # Создаем PID инстансы для зоны
    ph_pid = MagicMock()
    ec_pid = MagicMock()
    service.ph_controller._pid_by_zone[zone_id] = ph_pid
    service.ph_controller._last_pid_tick[zone_id] = 123.45
    service.ec_controller._pid_by_zone[zone_id] = ec_pid
    service.ec_controller._last_pid_tick[zone_id] = 123.45
    
    # Мокаем fetch для проверки существования зоны (зона найдена)
    with patch('common.db.fetch', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{'id': zone_id}]  # Зона найдена
        
        # Вызываем проверку удаления зоны
        await service._check_zone_deletion(zone_id)
        
        # Проверяем, что PID инстансы НЕ очищены
        assert zone_id in service.ph_controller._pid_by_zone
        assert service.ph_controller._pid_by_zone[zone_id] == ph_pid
        assert zone_id in service.ec_controller._pid_by_zone
        assert service.ec_controller._pid_by_zone[zone_id] == ec_pid

