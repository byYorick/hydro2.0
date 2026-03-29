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
from .utils.time import utcnow
from .alerts import AlertCode
from .infra_alerts import send_infra_alert, send_infra_resolved_alert

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
    state['last_check'] = utcnow()
    
    if connected:
        state['status'] = 'ok'
        if state['alert_sent']:
            await send_infra_resolved_alert(
                code=AlertCode.INFRA_MQTT_DOWN.value,
                message="MQTT connection restored",
                zone_id=None,
                alert_type="MQTT Down",
                service="mqtt-bridge",
                component="mqtt",
            )
            logger.info("MQTT connection restored")
            state['alert_sent'] = False
    else:
        state['status'] = 'fail'
        if not state['alert_sent']:
            await send_infra_alert(
                code=AlertCode.INFRA_MQTT_DOWN.value,
                message="MQTT connection is down",
                zone_id=None,
                alert_type="MQTT Down",
                service="mqtt-bridge",
                component="mqtt",
                details={
                    "detected_at": utcnow().isoformat(),
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
    state['last_check'] = utcnow()
    
    if connected:
        state['status'] = 'ok'
        if state['alert_sent']:
            await send_infra_resolved_alert(
                code=AlertCode.INFRA_DB_UNREACHABLE.value,
                message="Database connection restored",
                zone_id=None,
                alert_type="Database Unreachable",
                service="history-logger",
                component="database",
            )
            logger.info("Database connection restored")
            state['alert_sent'] = False
    else:
        state['status'] = 'fail'
        if not state['alert_sent']:
            await send_infra_alert(
                code=AlertCode.INFRA_DB_UNREACHABLE.value,
                message="Database is unreachable",
                zone_id=None,
                alert_type="Database Unreachable",
                service="history-logger",
                component="database",
                details={
                    "detected_at": utcnow().isoformat(),
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
    state['last_check'] = utcnow()
    
    if available:
        state['status'] = 'ok'
        if state['alert_sent']:
            await send_infra_resolved_alert(
                code=AlertCode.INFRA_SERVICE_DOWN.value,
                message="Laravel API restored",
                zone_id=None,
                alert_type="Laravel API Down",
                service="laravel_api",
                component="laravel",
            )
            logger.info("Laravel API restored")
            state['alert_sent'] = False
    else:
        state['status'] = 'fail'
        if not state['alert_sent']:
            await send_infra_alert(
                code=AlertCode.INFRA_SERVICE_DOWN.value,
                message="Laravel API is down",
                zone_id=None,
                alert_type="Laravel API Down",
                service="laravel_api",
                component="laravel",
                details={
                    "detected_at": utcnow().isoformat(),
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
    state['last_check'] = utcnow()
    
    if available:
        state['status'] = 'ok'
        if state['alert_sent']:
            await send_infra_resolved_alert(
                code=AlertCode.INFRA_SERVICE_DOWN.value,
                message=f"{service_name} service restored",
                zone_id=None,
                alert_type=f"{service_name} Down",
                service=service_name,
                component=service_name,
            )
            logger.info(f"{service_name} service restored")
            state['alert_sent'] = False
    else:
        state['status'] = 'fail'
        if not state['alert_sent']:
            await send_infra_alert(
                code=AlertCode.INFRA_SERVICE_DOWN.value,
                message=f"{service_name} service is down",
                zone_id=None,
                alert_type=f"{service_name} Down",
                service=service_name,
                component=service_name,
                details={
                    "detected_at": utcnow().isoformat(),
                }
            )
            state['alert_sent'] = True
            logger.warning(f"{service_name} service is down, alert created")


def get_infra_state() -> Dict[str, Dict[str, Any]]:
    """Возвращает текущее состояние инфраструктуры."""
    return _infra_state.copy()
