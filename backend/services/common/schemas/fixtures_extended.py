"""
Расширенные fixtures для всех типов payload'ов.

Используются в контрактных тестах для проверки совместимости протокола.
"""
import time
from typing import Dict, Any, Optional


def create_telemetry_fixture(
    metric_type: str = "PH",
    value: float = 6.5,
    ts: Optional[int] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Создает fixture телеметрии в формате JSON.
    
    Args:
        metric_type: Тип метрики
        value: Значение метрики
        ts: Timestamp (если None, используется текущее время, секунды)
        **kwargs: Дополнительные поля из MQTT контракта (unit, raw, stub, stable)
    
    Returns:
        Словарь с данными телеметрии
    """
    if ts is None:
        ts = int(time.time())
    
    payload = {
        "metric_type": metric_type,
        "value": value,
        "ts": ts
    }

    payload.update(kwargs)
    return payload


def create_error_fixture(
    level: str = "ERROR",
    component: str = "sensor",
    message: str = "Error occurred",
    error_code: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Создает fixture ошибки в формате JSON.
    
    Args:
        level: Уровень ошибки (ERROR, WARNING, INFO, DEBUG, CRITICAL, FATAL)
        component: Компонент
        message: Сообщение об ошибке
        error_code: Код ошибки
        **kwargs: Дополнительные поля
    
    Returns:
        Словарь с данными ошибки
    """
    payload = {
        "level": level,
        "component": component,
        "message": message
    }
    
    if error_code:
        payload["error_code"] = error_code
    
    if "ts" not in payload:
        payload["ts"] = time.time()
    
    payload.update(kwargs)
    return payload


def create_alert_fixture(
    source: str = "biz",
    code: str = "PH_LOW",
    type: str = "threshold",
    severity: Optional[str] = None,
    zone_id: Optional[int] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Создает fixture алерта в формате JSON.
    
    Args:
        source: Источник алерта (biz, infra)
        code: Код алерта
        type: Тип алерта
        severity: Уровень серьезности
        zone_id: Zone ID
        **kwargs: Дополнительные поля
    
    Returns:
        Словарь с данными алерта
    """
    payload = {
        "level": "WARNING",
        "component": "automation",
        "source": source,
        "code": code,
        "type": type
    }
    
    if severity:
        payload["severity"] = severity
    
    if zone_id:
        payload["zone_id"] = zone_id
    
    if "ts" not in payload:
        payload["ts"] = time.time()
    
    payload.update(kwargs)
    return payload


# Предопределенные fixtures для тестирования

FIXTURE_TELEMETRY_MINIMAL = create_telemetry_fixture()

FIXTURE_TELEMETRY_FULL = create_telemetry_fixture(
    metric_type="PH",
    value=6.5,
    unit="pH",
    raw=1465,
    stub=False,
    stable=True
)

FIXTURE_TELEMETRY_EC = create_telemetry_fixture(
    metric_type="EC",
    value=2.5,
    unit="mS/cm",
    raw=1250
)

FIXTURE_TELEMETRY_TEMP = create_telemetry_fixture(
    metric_type="TEMPERATURE",
    value=22.5,
    unit="C"
)

FIXTURE_ERROR_SENSOR = create_error_fixture(
    level="ERROR",
    component="sensor",
    message="Sensor reading failed",
    error_code="ESP_ERR_NO_MEM",
    error_code_num=101
)

FIXTURE_ERROR_PUMP = create_error_fixture(
    level="CRITICAL",
    component="pump",
    message="Pump motor failure",
    error_code="MOTOR_ERROR",
    hardware_id="AA:BB:CC:DD:EE:FF"
)

FIXTURE_ALERT_PH_LOW = create_alert_fixture(
    source="biz",
    code="PH_LOW",
    type="threshold",
    severity="medium",
    zone_id=1,
    message="pH value below threshold",
    details={"current_value": 5.5, "threshold": 6.0}
)

FIXTURE_ALERT_INFRA = create_alert_fixture(
    source="infra",
    code="NODE_OFFLINE",
    type="connectivity",
    severity="high",
    zone_id=1,
    node_uid="nd-ph-1",
    message="Node has been offline for more than 5 minutes"
)


def get_all_telemetry_fixtures() -> Dict[str, Dict[str, Any]]:
    """Возвращает все fixtures телеметрии."""
    return {
        "minimal": FIXTURE_TELEMETRY_MINIMAL,
        "full": FIXTURE_TELEMETRY_FULL,
        "ec": FIXTURE_TELEMETRY_EC,
        "temp": FIXTURE_TELEMETRY_TEMP,
    }


def get_all_error_fixtures() -> Dict[str, Dict[str, Any]]:
    """Возвращает все fixtures ошибок."""
    return {
        "sensor": FIXTURE_ERROR_SENSOR,
        "pump": FIXTURE_ERROR_PUMP,
    }


def get_all_alert_fixtures() -> Dict[str, Dict[str, Any]]:
    """Возвращает все fixtures алертов."""
    return {
        "ph_low": FIXTURE_ALERT_PH_LOW,
        "infra": FIXTURE_ALERT_INFRA,
    }
