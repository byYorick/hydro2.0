"""
Мониторинг инфраструктуры и создание алертов.

Отслеживает состояние компонентов инфраструктуры:
- MQTT
- Database
- Laravel API
- History Logger
- Automation Engine

Создает алерты при обнаружении проблем.
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from .alert_queue import send_alert_to_laravel
from .alerts import AlertCode

logger = logging.getLogger(__name__)

# Глобальное состояние компонентов
_infra_state: Dict[str, Dict[str, Any]] = {
    'mqtt': {'status': 'unknown', 'last_check': None, 'alert_sent': False},
    'db': {'status': 'unknown', 'last_check': None, 'alert_sent': False},
    'laravel': {'status': 'unknown', 'last_check': None, 'alert_sent': False},
    'history_logger': {'status': 'unknown', 'last_check': None, 'alert_sent': False},
}


async def check_mqtt_health(connected: bool) -> None:
    """
    Проверяет состояние MQTT и создает алерт при проблемах.
    
    Args:
        connected: True если MQTT подключен
    """
    state = _infra_state['mqtt']
    state['last_check'] = datetime.utcnow()
    
    if connected:
        state['status'] = 'ok'
        # Если был отправлен алерт о проблеме, можно создать алерт о восстановлении
        if state['alert_sent']:
            logger.info("MQTT connection restored")
            state['alert_sent'] = False
    else:
        state['status'] = 'fail'
        # Создаем алерт только если еще не отправлен
        if not state['alert_sent']:
            await send_alert_to_laravel(
                zone_id=None,
                source="infra",
                code=AlertCode.INFRA_MQTT_DOWN.value,
                type="MQTT Down",
                status="ACTIVE",
                details={
                    "component": "mqtt",
                    "message": "MQTT connection is down",
                    "detected_at": datetime.utcnow().isoformat(),
                }
            )
            state['alert_sent'] = True
            logger.warning("MQTT connection is down, alert created")


async def check_db_health(connected: bool) -> None:
    """
    Проверяет состояние БД и создает алерт при проблемах.
    
    Args:
        connected: True если БД доступна
    """
    state = _infra_state['db']
    state['last_check'] = datetime.utcnow()
    
    if connected:
        state['status'] = 'ok'
        if state['alert_sent']:
            logger.info("Database connection restored")
            state['alert_sent'] = False
    else:
        state['status'] = 'fail'
        if not state['alert_sent']:
            await send_alert_to_laravel(
                zone_id=None,
                source="infra",
                code=AlertCode.INFRA_DB_UNREACHABLE.value,
                type="Database Unreachable",
                status="ACTIVE",
                details={
                    "component": "database",
                    "message": "Database is unreachable",
                    "detected_at": datetime.utcnow().isoformat(),
                }
            )
            state['alert_sent'] = True
            logger.warning("Database is unreachable, alert created")


async def check_laravel_health(available: bool) -> None:
    """
    Проверяет состояние Laravel API и создает алерт при проблемах.
    
    Args:
        available: True если Laravel API доступен
    """
    state = _infra_state['laravel']
    state['last_check'] = datetime.utcnow()
    
    if available:
        state['status'] = 'ok'
        if state['alert_sent']:
            logger.info("Laravel API restored")
            state['alert_sent'] = False
    else:
        state['status'] = 'fail'
        if not state['alert_sent']:
            await send_alert_to_laravel(
                zone_id=None,
                source="infra",
                code=AlertCode.INFRA_SERVICE_DOWN.value,
                type="Laravel API Down",
                status="ACTIVE",
                details={
                    "component": "laravel",
                    "service": "laravel_api",
                    "message": "Laravel API is down",
                    "detected_at": datetime.utcnow().isoformat(),
                }
            )
            state['alert_sent'] = True
            logger.warning("Laravel API is down, alert created")


async def check_service_health(service_name: str, available: bool) -> None:
    """
    Проверяет состояние сервиса и создает алерт при проблемах.
    
    Args:
        service_name: Имя сервиса (history_logger, automation_engine, etc.)
        available: True если сервис доступен
    """
    if service_name not in _infra_state:
        _infra_state[service_name] = {'status': 'unknown', 'last_check': None, 'alert_sent': False}
    
    state = _infra_state[service_name]
    state['last_check'] = datetime.utcnow()
    
    if available:
        state['status'] = 'ok'
        if state['alert_sent']:
            logger.info(f"{service_name} service restored")
            state['alert_sent'] = False
    else:
        state['status'] = 'fail'
        if not state['alert_sent']:
            await send_alert_to_laravel(
                zone_id=None,
                source="infra",
                code=AlertCode.INFRA_SERVICE_DOWN.value,
                type=f"{service_name} Down",
                status="ACTIVE",
                details={
                    "component": service_name,
                    "service": service_name,
                    "message": f"{service_name} service is down",
                    "detected_at": datetime.utcnow().isoformat(),
                }
            )
            state['alert_sent'] = True
            logger.warning(f"{service_name} service is down, alert created")


def get_infra_state() -> Dict[str, Dict[str, Any]]:
    """Возвращает текущее состояние инфраструктуры."""
    return _infra_state.copy()
