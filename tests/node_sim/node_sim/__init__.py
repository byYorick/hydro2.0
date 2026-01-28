"""
Node Simulator - симулятор нод для системы Hydro.
Совместим с протоколом MQTT системы 2.0.
"""

__version__ = "0.1.0"

# Экспорт функций генерации топиков для удобного импорта
from .topics import (
    telemetry,
    command,
    command_response,
    error,
    status,
    heartbeat,
    config_report,
    temp_command,
    temp_error,
    temp_status,
    temp_config_report,
    temp_telemetry,
    temp_command_response,
    temp_heartbeat,
)

__all__ = [
    "telemetry",
    "command",
    "command_response",
    "error",
    "status",
    "heartbeat",
    "config_report",
    "temp_command",
    "temp_error",
    "temp_status",
    "temp_config_report",
    "temp_telemetry",
    "temp_command_response",
    "temp_heartbeat",
]
