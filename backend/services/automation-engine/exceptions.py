"""
Кастомные исключения для automation engine.
"""
from typing import Optional, Dict, Any


class AutomationError(Exception):
    """Базовое исключение для всех ошибок automation engine."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ZoneNotFoundError(AutomationError):
    """Ошибка: зона не найдена."""
    
    def __init__(self, zone_id: int, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"Zone {zone_id} not found", details)
        self.zone_id = zone_id


class InvalidConfigurationError(AutomationError):
    """Ошибка: невалидная конфигурация."""
    
    def __init__(self, message: str, config: Optional[Dict[str, Any]] = None):
        details = {"config": config} if config else {}
        super().__init__(f"Invalid configuration: {message}", details)
        self.config = config


class InvalidZoneDataError(AutomationError):
    """Ошибка: невалидные данные зоны."""
    
    def __init__(self, zone_id: int, message: str, data: Optional[Dict[str, Any]] = None):
        details = {"zone_id": zone_id, "data": data} if data else {"zone_id": zone_id}
        super().__init__(f"Invalid zone data for zone {zone_id}: {message}", details)
        self.zone_id = zone_id


class NodeNotFoundError(AutomationError):
    """Ошибка: узел не найден."""
    
    def __init__(self, zone_id: int, node_type: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            f"Node of type '{node_type}' not found for zone {zone_id}",
            details
        )
        self.zone_id = zone_id
        self.node_type = node_type


class TelemetryError(AutomationError):
    """Ошибка: проблема с телеметрией."""
    
    def __init__(self, zone_id: int, message: str, metric: Optional[str] = None):
        details = {"zone_id": zone_id}
        if metric:
            details["metric"] = metric
        super().__init__(f"Telemetry error for zone {zone_id}: {message}", details)
        self.zone_id = zone_id
        self.metric = metric


class CommandPublishError(AutomationError):
    """Ошибка: не удалось опубликовать команду."""
    
    def __init__(
        self,
        zone_id: int,
        command: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            f"Failed to publish command '{command}' for zone {zone_id}: {reason}",
            details
        )
        self.zone_id = zone_id
        self.command = command
        self.reason = reason


class DatabaseError(AutomationError):
    """Ошибка: проблема с базой данных."""
    
    def __init__(self, message: str, query: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        if query:
            details = details or {}
            details["query"] = query
        super().__init__(f"Database error: {message}", details)
        self.query = query


class MQTTError(AutomationError):
    """Ошибка: проблема с MQTT."""
    
    def __init__(self, message: str, topic: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        if topic:
            details = details or {}
            details["topic"] = topic
        super().__init__(f"MQTT error: {message}", details)
        self.topic = topic

