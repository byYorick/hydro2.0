"""
Irrigation Controller - управление поливом и рециркуляцией.
Согласно ZONE_CONTROLLER_FULL.md раздел 6
"""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from common.utils.time import utcnow
from common.db import fetch, create_zone_event
from common.water_flow import check_water_level
from alerts_manager import ensure_alert
from services.targets_accessor import get_irrigation_params


async def get_last_irrigation_time(zone_id: int) -> Optional[datetime]:
    """
    Получить время последнего полива из событий.
    
    Returns:
        datetime последнего IRRIGATION_STARTED или None
    """
    rows = await fetch(
        """
        SELECT created_at
        FROM zone_events
        WHERE zone_id = $1 AND type = 'IRRIGATION_STARTED'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        zone_id,
    )
    
    if rows and rows[0]["created_at"]:
        return rows[0]["created_at"]
    return None


def get_irrigation_binding(bindings: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Получить binding для полива по ролям.
    
    Args:
        bindings: Dict[role, binding_info] из InfrastructureRepository
    
    Returns:
        binding_info для полива или None
    """
    # Ищем по ролям: main_pump, irrigation_pump, pump
    for role in ['main_pump', 'irrigation_pump', 'pump']:
        if role in bindings and bindings[role]['direction'] == 'actuator':
            return {
                'node_id': bindings[role]['node_id'],
                'node_uid': bindings[role]['node_uid'],
                'channel': bindings[role]['channel'],
                'asset_type': bindings[role]['asset_type'],
            }
    return None


async def check_and_control_irrigation(
    zone_id: int,
    targets: Dict[str, Any],
    telemetry: Dict[str, Optional[float]],
    bindings: Dict[str, Dict[str, Any]],
    actuators: Optional[Dict[str, Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    """
    Проверка и управление поливом зоны.
    
    Логика: if (now - last_irrigation >= interval) AND water_level_ok → start irrigation
    
    Args:
        zone_id: ID зоны
        targets: Целевые значения из рецепта (irrigation_interval_sec, irrigation_duration_sec)
        telemetry: Текущие значения телеметрии (не используется, но для совместимости)
        bindings: Dict[role, binding_info] из InfrastructureRepository
    
    Returns:
        Команда для запуска полива или None
    """
    # Получаем параметры полива из targets
    irrigation_interval_sec, irrigation_duration_sec, _ = get_irrigation_params(
        targets,
        zone_id=zone_id,
    )
    if irrigation_duration_sec is None:
        irrigation_duration_sec = 60

    if irrigation_interval_sec is None:
        # Если интервал не задан, не запускаем автоматический полив
        return None
    
    # Получаем binding для полива (сначала через резолвер ролей, потом fallback)
    pump_binding = None
    if actuators:
        for role in ['irrigation_pump', 'main_pump', 'pump']:
            if role in actuators:
                pump_binding = actuators[role]
                break
    if not pump_binding:
        pump_binding = get_irrigation_binding(bindings)
    if not pump_binding:
        # Нет binding для полива - создаем alert
        await ensure_alert(zone_id, 'MISSING_BINDING', {
            'binding_role': 'main_pump',
            'required_for': 'irrigation_control',
        })
        return None
    
    # Получаем время последнего полива
    last_irrigation_time = await get_last_irrigation_time(zone_id)
    
    if last_irrigation_time is None:
        # Если полива еще не было, можно запустить сразу (или подождать интервал)
        # Для безопасности ждем хотя бы половину интервала
        return None
    
    # Проверяем, прошло ли достаточно времени
    now = utcnow()
    # Приводим last_irrigation_time к aware UTC для корректного сравнения
    if last_irrigation_time.tzinfo is None:
        last_irrigation_time = last_irrigation_time.replace(tzinfo=timezone.utc)
    elif last_irrigation_time.tzinfo != timezone.utc:
        last_irrigation_time = last_irrigation_time.astimezone(timezone.utc)
    
    elapsed_sec = (now - last_irrigation_time).total_seconds()
    
    if elapsed_sec < irrigation_interval_sec:
        # Еще не прошло достаточно времени
        return None
    
    # Проверяем уровень воды
    water_level_ok, water_level = await check_water_level(zone_id)
    if not water_level_ok:
        # Уровень воды низкий - не запускаем полив
        return None
    
    # Возвращаем команду для запуска полива
    return {
        'node_uid': pump_binding['node_uid'],
        'channel': pump_binding['channel'],
        'cmd': 'run_pump',
        'params': {
            'duration_ms': int(irrigation_duration_sec * 1000)
        },
        'event_type': 'IRRIGATION_STARTED',
        'event_details': {
            'interval_sec': irrigation_interval_sec,
            'duration_sec': irrigation_duration_sec,
            'duration_ms': int(irrigation_duration_sec * 1000),
            'last_irrigation_time': last_irrigation_time.isoformat(),
            'elapsed_sec': elapsed_sec
        }
    }


async def get_last_recirculation_time(zone_id: int) -> Optional[datetime]:
    """
    Получить время последней рециркуляции из событий.
    
    Returns:
        datetime последнего RECIRCULATION_CYCLE или None
    """
    rows = await fetch(
        """
        SELECT created_at
        FROM zone_events
        WHERE zone_id = $1 AND type = 'RECIRCULATION_CYCLE'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        zone_id,
    )
    
    if rows and rows[0]["created_at"]:
        return rows[0]["created_at"]
    return None


def get_recirculation_binding(bindings: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Получить binding для рециркуляции по ролям.
    
    Args:
        bindings: Dict[role, binding_info] из InfrastructureRepository
    
    Returns:
        binding_info для рециркуляции или None
    """
    # Ищем по ролям: recirculation_pump, recirculation
    for role in ['recirculation_pump', 'recirculation']:
        if role in bindings and bindings[role]['direction'] == 'actuator':
            return {
                'node_id': bindings[role]['node_id'],
                'node_uid': bindings[role]['node_uid'],
                'channel': bindings[role]['channel'],
                'asset_type': bindings[role]['asset_type'],
            }
    return None


async def check_and_control_recirculation(
    zone_id: int,
    targets: Dict[str, Any],
    telemetry: Dict[str, Optional[float]],
    bindings: Dict[str, Dict[str, Any]],
    actuators: Optional[Dict[str, Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    """
    Проверка и управление рециркуляцией воды.
    
    Логика: if recirculation_enabled AND (now - last_recirculation >= interval) → run recirculation_pump
    
    Args:
        zone_id: ID зоны
        targets: Целевые значения из рецепта (recirculation_enabled, recirculation_interval_min, recirculation_duration_sec)
        telemetry: Текущие значения телеметрии (не используется, но для совместимости с другими контроллерами)
        bindings: Dict[role, binding_info] из InfrastructureRepository
    
    Returns:
        Команда для запуска рециркуляции или None
    """
    # Получаем параметры рециркуляции из targets
    recirculation_enabled = targets.get("recirculation_enabled", False)
    
    if not recirculation_enabled:
        # Рециркуляция отключена
        return None
    
    recirculation_interval_min = targets.get("recirculation_interval_min")
    recirculation_duration_sec = targets.get("recirculation_duration_sec", 300)  # По умолчанию 5 минут
    
    if recirculation_interval_min is None:
        # Интервал не задан
        return None
    
    recirculation_interval_min = int(recirculation_interval_min)
    recirculation_duration_sec = int(recirculation_duration_sec)
    
    # Получаем binding для рециркуляции (role resolver + fallback)
    recirculation_binding = None
    if actuators and 'recirculation_pump' in actuators:
        recirculation_binding = actuators['recirculation_pump']
    if not recirculation_binding:
        recirculation_binding = get_recirculation_binding(bindings)
    if not recirculation_binding:
        # Нет binding для рециркуляции - создаем alert
        await ensure_alert(zone_id, 'MISSING_BINDING', {
            'binding_role': 'recirculation_pump',
            'required_for': 'recirculation_control',
        })
        return None
    
    # Получаем время последней рециркуляции
    last_recirculation_time = await get_last_recirculation_time(zone_id)
    
    now = utcnow()
    
    if last_recirculation_time is not None:
        # Проверяем, прошло ли достаточно времени
        # Приводим last_recirculation_time к aware UTC для корректного сравнения
        if last_recirculation_time.tzinfo is None:
            last_recirculation_time = last_recirculation_time.replace(tzinfo=timezone.utc)
        elif last_recirculation_time.tzinfo != timezone.utc:
            last_recirculation_time = last_recirculation_time.astimezone(timezone.utc)
        
        elapsed_min = (now - last_recirculation_time).total_seconds() / 60.0
        
        if elapsed_min < recirculation_interval_min:
            # Еще не прошло достаточно времени
            return None
    # Если рециркуляции еще не было, можно запустить сразу
    
    # Проверяем уровень воды перед запуском рециркуляции
    water_level_ok, water_level = await check_water_level(zone_id)
    if not water_level_ok:
        # Уровень воды низкий - не запускаем рециркуляцию
        return None
    
    # Возвращаем команду для запуска рециркуляции
    return {
        'node_uid': recirculation_binding['node_uid'],
        'channel': recirculation_binding['channel'],
        'cmd': 'run_pump',
        'params': {
            'duration_ms': int(recirculation_duration_sec * 1000)
        },
        'event_type': 'RECIRCULATION_CYCLE',
        'event_details': {
            'interval_min': recirculation_interval_min,
            'duration_sec': recirculation_duration_sec,
            'duration_ms': int(recirculation_duration_sec * 1000),
            'last_recirculation_time': last_recirculation_time.isoformat() if last_recirculation_time else None,
            'elapsed_min': (now - last_recirculation_time).total_seconds() / 60.0 if last_recirculation_time else None
        }
    }
