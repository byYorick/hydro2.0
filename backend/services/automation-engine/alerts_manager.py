"""
Alerts Manager - централизованное управление созданием и обновлением алертов.
Согласно EVENTS_AND_ALERTS_ENGINE.md раздел 5
"""
from typing import Optional, Dict, Any
from common.db import fetch, execute, create_zone_event


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
            SET details = $1, updated_at = NOW()
            WHERE id = $2
            """,
            details_json,
            alert_id,
        )
    else:
        # Создаем новый алерт
        details_json = json.dumps(details)
        await execute(
            """
            INSERT INTO alerts (zone_id, type, details, status, created_at)
            VALUES ($1, $2, $3, 'ACTIVE', NOW())
            """,
            zone_id,
            alert_type,
            details_json,
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

