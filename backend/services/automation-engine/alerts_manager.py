"""
Alerts Manager - централизованное управление созданием и обновлением алертов.
Согласно EVENTS_AND_ALERTS_ENGINE.md раздел 5
"""
from typing import Optional, Dict, Any, Tuple
from common.db import fetch, execute, create_zone_event
from common.alerts import create_alert, AlertSource, AlertCode

# Маппинг старых alert_type на новые (source, code)
ALERT_TYPE_MAPPING: Dict[str, Tuple[str, str]] = {
    'PH_HIGH': (AlertSource.BIZ.value, AlertCode.BIZ_HIGH_PH.value),
    'PH_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_LOW_PH.value),
    'EC_HIGH': (AlertSource.BIZ.value, AlertCode.BIZ_HIGH_EC.value),
    'EC_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_LOW_EC.value),
    'TEMP_HIGH': (AlertSource.BIZ.value, AlertCode.BIZ_HIGH_TEMP.value),
    'TEMP_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_LOW_TEMP.value),
    'HUMIDITY_HIGH': (AlertSource.BIZ.value, AlertCode.BIZ_HIGH_HUMIDITY.value),
    'HUMIDITY_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_LOW_HUMIDITY.value),
    'NO_FLOW': (AlertSource.BIZ.value, AlertCode.BIZ_NO_FLOW.value),
    'WATER_LEVEL_LOW': (AlertSource.BIZ.value, AlertCode.BIZ_DRY_RUN.value),
    'LIGHT_FAILURE': (AlertSource.BIZ.value, AlertCode.BIZ_LIGHT_FAILURE.value),
    'MISSING_BINDING': (AlertSource.BIZ.value, AlertCode.BIZ_CONFIG_ERROR.value),
}


def _get_alert_source_and_code(alert_type: str) -> Tuple[str, str]:
    """
    Получить source и code для alert_type.
    Если маппинга нет, использует дефолтные значения.
    """
    if alert_type in ALERT_TYPE_MAPPING:
        return ALERT_TYPE_MAPPING[alert_type]
    # Дефолт для неизвестных типов
    return (AlertSource.BIZ.value, AlertCode.BIZ_CONFIG_ERROR.value)


async def ensure_alert(zone_id: int, alert_type: str, details: Dict[str, Any]) -> None:
    """
    Создание/обновление алерта если его еще нет.
    
    Логика:
    - Если алерт такого типа уже активен - обновляем details
    - Если нет - создаем новый алерт и событие ALERT_CREATED
    
    Args:
        zone_id: ID зоны
        alert_type: Тип алерта (PH_HIGH, TEMP_LOW, и т.д.)
        details: Детали алерта (JSON-совместимый словарь)
    """
    import json
    
    # Проверяем, есть ли уже активный алерт
    rows = await fetch(
        """
        SELECT id, details
        FROM alerts
        WHERE zone_id = $1 AND type = $2 AND status = 'ACTIVE'
        """,
        zone_id,
        alert_type,
    )
    
    if rows:
        # Обновляем существующий алерт
        alert_id = rows[0]["id"]
        details_json = json.dumps(details)
        await execute(
            """
            UPDATE alerts
            SET details = $1
            WHERE id = $2
            """,
            details_json,
            alert_id,
        )
    else:
        # Создаем новый алерт с source и code
        source, code = _get_alert_source_and_code(alert_type)
        await create_alert(
            zone_id=zone_id,
            source=source,
            code=code,
            type=alert_type,  # type остается для обратной совместимости
            details=details
        )
        # Создаем событие ALERT_CREATED
        await create_zone_event(
            zone_id,
            'ALERT_CREATED',
            {
                'alert_type': alert_type,
                'details': details
            }
        )


async def resolve_alert(zone_id: int, alert_type: str) -> bool:
    """
    Закрытие алерта (автоматическое).
    
    Args:
        zone_id: ID зоны
        alert_type: Тип алерта для закрытия
    
    Returns:
        True если алерт был закрыт, False если не найден
    """
    rows = await fetch(
        """
        SELECT id
        FROM alerts
        WHERE zone_id = $1 AND type = $2 AND status = 'ACTIVE'
        """,
        zone_id,
        alert_type,
    )
    
    if not rows:
        return False
    
    alert_id = rows[0]["id"]
    
    # Закрываем алерт
    await execute(
        """
        UPDATE alerts
        SET status = 'RESOLVED', resolved_at = NOW()
        WHERE id = $1
        """,
        alert_id,
    )
    
    # Создаем событие ALERT_RESOLVED
    await create_zone_event(
        zone_id,
        'ALERT_RESOLVED',
        {
            'alert_id': alert_id,
            'alert_type': alert_type
        }
    )
    
    return True


async def find_active_alert(zone_id: int, alert_type: str) -> Optional[Dict[str, Any]]:
    """
    Поиск активного алерта.
    
    Returns:
        Dict с данными алерта или None
    """
    rows = await fetch(
        """
        SELECT id, type, details, status, created_at
        FROM alerts
        WHERE zone_id = $1 AND type = $2 AND status = 'ACTIVE'
        LIMIT 1
        """,
        zone_id,
        alert_type,
    )
    
    if rows:
        return {
            'id': rows[0]["id"],
            'type': rows[0]["type"],
            'details': rows[0]["details"],
            'status': rows[0]["status"],
            'created_at': rows[0]["created_at"],
        }
    return None
