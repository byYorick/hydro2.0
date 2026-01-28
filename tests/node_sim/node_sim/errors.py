"""
Модуль для генерации и публикации ошибок/алертов в формате системы Hydro.
Публикует error события в формате, который создаёт alerts и/или unassigned.
"""

import json
from dataclasses import dataclass
from typing import Dict, Optional, Any, Callable
from enum import Enum

from .topics import error, temp_error
from .utils_time import current_timestamp_ms


class ErrorSource(str, Enum):
    """Источник ошибки."""
    INFRASTRUCTURE = "infrastructure"
    BUSINESS = "business"


class ErrorSeverity(str, Enum):
    """Серьёзность ошибки."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorPayload:
    """
    Payload для публикации ошибки в MQTT.
    
    Формат соответствует ожиданиям backend/services/history-logger (handle_error):
    - level
    - component
    - error_code
    - message
    - details (optional)
    - ts (optional)
    """
    level: str  # "ERROR" | "WARNING" | "INFO"
    component: str  # e.g. "node-sim"
    error_code: Optional[str]  # e.g. "infra_overcurrent"
    message: str
    details: Optional[Dict[str, Any]] = None
    ts: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь для JSON сериализации."""
        payload: Dict[str, Any] = {
            "level": self.level,
            "component": self.component,
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.details is not None:
            payload["details"] = self.details
        if self.ts is not None:
            payload["ts"] = self.ts
        return payload
    
    def to_json(self) -> str:
        """Преобразовать в JSON строку."""
        return json.dumps(self.to_dict())


class ErrorPublisher:
    """
    Класс для публикации ошибок в MQTT.
    
    Используется для генерации error событий, которые создают alerts и/или unassigned.
    """
    
    def __init__(
        self,
        mqtt_client,  # MqttClient из mqtt_client.py
        gh_uid: str,
        zone_uid: str,
        node_uid: str,
        hardware_id: str,
        mode: str = "configured",  # "preconfig" | "configured"
    ):
        """
        Инициализация публикатора ошибок.
        
        Args:
            mqtt_client: MQTT клиент для публикации
            gh_uid: UID теплицы
            zone_uid: UID зоны
            node_uid: UID узла
            hardware_id: Hardware ID узла
            mode: Режим работы ("preconfig" или "configured")
        """
        self.mqtt_client = mqtt_client
        self.gh_uid = gh_uid
        self.zone_uid = zone_uid
        self.node_uid = node_uid
        self.hardware_id = hardware_id
        self.mode = mode
    
    def publish_error(
        self,
        source: str,
        code: str,
        severity: str,
        details: Dict[str, Any],
        qos: int = 1,
    ) -> bool:
        """
        Опубликовать ошибку в MQTT.
        
        Args:
            source: Источник ошибки ("infrastructure" | "business")
            code: Код ошибки
            severity: Серьёзность ("low" | "medium" | "high" | "critical")
            details: Дополнительные детали
            qos: QoS уровень для публикации (по умолчанию 1)
        
        Returns:
            True если успешно опубликовано, False в противном случае
        """
        # Определяем топик в зависимости от режима
        if self.mode == "preconfig":
            topic = temp_error(self.hardware_id or self.node_uid)
        else:
            topic = error(self.gh_uid, self.zone_uid, self.node_uid)
        
        # Маппинг severity -> level для history-logger
        sev = (severity or "").lower()
        if sev in ("critical", "high"):
            level = "ERROR"
        elif sev in ("medium",):
            level = "WARNING"
        else:
            level = "INFO"

        message = details.get("message") if isinstance(details, dict) else None
        if not message:
            # fallback: код ошибки как сообщение
            message = code

        payload = ErrorPayload(
            level=level,
            component=str(source or "node-sim"),
            error_code=code,
            message=str(message),
            details=details if isinstance(details, dict) else None,
            ts=current_timestamp_ms(),
        )
        
        # Публикуем в MQTT
        try:
            # mqtt_client.publish() ожидает bytes; publish_json() умеет dict
            if hasattr(self.mqtt_client, "publish_json"):
                self.mqtt_client.publish_json(topic, payload.to_dict(), qos=qos)
            else:
                self.mqtt_client.publish(topic, payload.to_json().encode("utf-8"), qos=qos)
            return True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to publish error to {topic}: {e}")
            return False


# Функции-хелперы для генерации конкретных типов ошибок

def create_overcurrent_error(
    publisher: ErrorPublisher,
    current_ma: float,
    threshold_ma: float = 500.0,
    actuator: Optional[str] = None,
) -> bool:
    """
    Создать и опубликовать ошибку перегрузки по току (infra_overcurrent).
    
    Args:
        publisher: Публикатор ошибок
        current_ma: Текущий ток в мА
        threshold_ma: Порог перегрузки в мА
        actuator: Имя актуатора (опционально)
    
    Returns:
        True если успешно опубликовано
    """
    details = {
        "current_ma": current_ma,
        "threshold_ma": threshold_ma,
    }
    if actuator:
        details["actuator"] = actuator
    
    return publisher.publish_error(
        source=ErrorSource.INFRASTRUCTURE.value,
        code="infra_overcurrent",
        severity=ErrorSeverity.HIGH.value,
        details=details,
    )


def create_no_flow_error(
    publisher: ErrorPublisher,
    actuator: str,
    elapsed_seconds: float,
    timeout_seconds: float,
) -> bool:
    """
    Создать и опубликовать ошибку отсутствия потока (biz_no_flow).
    
    Args:
        publisher: Публикатор ошибок
        actuator: Имя актуатора (насоса)
        elapsed_seconds: Время работы насоса без потока
        timeout_seconds: Таймаут для генерации ошибки
    
    Returns:
        True если успешно опубликовано
    """
    return publisher.publish_error(
        source=ErrorSource.BUSINESS.value,
        code="biz_no_flow",
        severity=ErrorSeverity.HIGH.value,
        details={
            "actuator": actuator,
            "elapsed_seconds": elapsed_seconds,
            "timeout_seconds": timeout_seconds,
        },
    )


def create_sensor_stuck_i2c_error(
    publisher: ErrorPublisher,
    sensor: str,
    i2c_address: Optional[int] = None,
    attempts: Optional[int] = None,
) -> bool:
    """
    Создать и опубликовать ошибку застрявшего I2C сенсора (infra_sensor_stuck_i2c).
    
    Args:
        publisher: Публикатор ошибок
        sensor: Имя сенсора
        i2c_address: Адрес I2C (опционально)
        attempts: Количество попыток чтения (опционально)
    
    Returns:
        True если успешно опубликовано
    """
    details = {"sensor": sensor}
    if i2c_address is not None:
        details["i2c_address"] = i2c_address
    if attempts is not None:
        details["attempts"] = attempts
    
    return publisher.publish_error(
        source=ErrorSource.INFRASTRUCTURE.value,
        code="infra_sensor_stuck_i2c",
        severity=ErrorSeverity.MEDIUM.value,
        details=details,
    )


def create_mqtt_reconnect_error(
    publisher: ErrorPublisher,
    reconnect_count: int,
    last_error: Optional[str] = None,
) -> bool:
    """
    Создать и опубликовать ошибку переподключения MQTT (infra_mqtt_reconnect).
    
    Args:
        publisher: Публикатор ошибок
        reconnect_count: Количество переподключений
        last_error: Последняя ошибка (опционально)
    
    Returns:
        True если успешно опубликовано
    """
    details = {"reconnect_count": reconnect_count}
    if last_error:
        details["last_error"] = last_error
    
    return publisher.publish_error(
        source=ErrorSource.INFRASTRUCTURE.value,
        code="infra_mqtt_reconnect",
        severity=ErrorSeverity.MEDIUM.value,
        details=details,
    )


def create_temp_out_of_range_error(
    publisher: ErrorPublisher,
    sensor: str,
    value: float,
    min_value: float,
    max_value: float,
    unit: str = "celsius",
) -> bool:
    """
    Создать и опубликовать ошибку температуры вне диапазона (biz_temp_out_of_range).
    
    Args:
        publisher: Публикатор ошибок
        sensor: Имя сенсора (air_temp_c, solution_temp_c, etc.)
        value: Текущее значение температуры
        min_value: Минимальное допустимое значение
        max_value: Максимальное допустимое значение
        unit: Единица измерения (по умолчанию "celsius")
    
    Returns:
        True если успешно опубликовано
    """
    return publisher.publish_error(
        source=ErrorSource.BUSINESS.value,
        code="biz_temp_out_of_range",
        severity=ErrorSeverity.MEDIUM.value,
        details={
            "sensor": sensor,
            "value": value,
            "min_value": min_value,
            "max_value": max_value,
            "unit": unit,
        },
    )


# Колбэк для интеграции с моделью ноды

def create_error_callback(publisher: ErrorPublisher) -> Callable[[str, Dict], None]:
    """
    Создать колбэк для обработки ошибок из модели ноды.
    
    Этот колбэк можно зарегистрировать в NodeModel через register_error_callback().
    
    Args:
        publisher: Публикатор ошибок
    
    Returns:
        Функция-колбэк для регистрации в модели
    """
    def error_callback(error_code: str, details: Dict[str, Any]) -> None:
        """
        Обработчик ошибок из модели ноды.
        
        Args:
            error_code: Код ошибки (например, "biz_no_flow")
            details: Детали ошибки
        """
        # Определяем source и severity на основе кода ошибки
        if error_code.startswith("infra_"):
            source = ErrorSource.INFRASTRUCTURE.value
            severity = ErrorSeverity.HIGH.value
        elif error_code.startswith("biz_"):
            source = ErrorSource.BUSINESS.value
            severity = ErrorSeverity.MEDIUM.value
        else:
            # Дефолт для неизвестных кодов
            source = ErrorSource.INFRASTRUCTURE.value
            severity = ErrorSeverity.MEDIUM.value
        
        # Публикуем ошибку
        publisher.publish_error(
            source=source,
            code=error_code,
            severity=severity,
            details=details,
        )
    
    return error_callback

