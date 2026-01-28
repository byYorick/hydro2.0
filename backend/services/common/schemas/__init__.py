"""
Единый контракт команд для всех сервисов.

Этот модуль содержит модели и схемы для единого формата команд и ответов.
"""

# Импортируем напрямую из родительского модуля schemas.py
# Используем importlib для прямого импорта из файла, чтобы избежать циклических импортов
import importlib.util
from pathlib import Path

# Получаем путь к файлу schemas.py в родительской директории
parent_dir = Path(__file__).parent.parent
schemas_file = parent_dir / "schemas.py"

# Загружаем модуль напрямую из файла
spec = importlib.util.spec_from_file_location("common_schemas", schemas_file)
schemas_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schemas_module)

# Экспортируем классы
Command = schemas_module.Command
CommandResponse = schemas_module.CommandResponse
CommandRequest = schemas_module.CommandRequest
TelemetryPayload = schemas_module.TelemetryPayload
NodeConfigModel = schemas_module.NodeConfigModel
SimulationScenario = schemas_module.SimulationScenario
SimulationRequest = schemas_module.SimulationRequest

__all__ = [
    'Command',
    'CommandResponse',
    'CommandRequest',
    'TelemetryPayload',
    'NodeConfigModel',
    'SimulationScenario',
    'SimulationRequest',
]
