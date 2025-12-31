"""
Light Controller - управление освещением и фотопериодом.
Согласно ZONE_CONTROLLER_FULL.md раздел 7
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, time
from common.utils.time import utcnow
from common.db import fetch, create_zone_event
from common.alerts import create_alert, AlertSource, AlertCode
from alerts_manager import ensure_alert


# Пороги для обнаружения света
LIGHT_SENSOR_NIGHT_LEVEL = 10  # lux - уровень ночного освещения
LIGHT_FAILURE_THRESHOLD = 20  # lux - если свет включен, но показания < этого значения - ошибка


def parse_photoperiod(light_hours: Any) -> Optional[tuple]:
    """
    Парсинг фотопериода из targets.
    
    Поддерживает форматы:
    - "06:00-22:00" (строка)
    - 16 (число часов, начиная с 06:00)
    - {"start": "06:00", "end": "22:00"} (dict)
    
    Returns:
        (start_time, end_time) или None
    """
    if light_hours is None:
        return None
    
    if isinstance(light_hours, (int, float)):
        # Число часов, по умолчанию начинаем с 06:00
        hours = int(light_hours)
        start = time(6, 0)
        end_hour = (6 + hours) % 24
        end = time(end_hour, 0)
        return (start, end)
    
    if isinstance(light_hours, str):
        # Формат "06:00-22:00"
        if "-" in light_hours:
            parts = light_hours.split("-")
            if len(parts) == 2:
                try:
                    start_parts = parts[0].strip().split(":")
                    end_parts = parts[1].strip().split(":")
                    start = time(int(start_parts[0]), int(start_parts[1]) if len(start_parts) > 1 else 0)
                    end = time(int(end_parts[0]), int(end_parts[1]) if len(end_parts) > 1 else 0)
                    return (start, end)
                except (ValueError, IndexError):
                    pass
    
    if isinstance(light_hours, dict):
        # Формат {"start": "06:00", "end": "22:00"}
        start_str = light_hours.get("start")
        end_str = light_hours.get("end")
        if start_str and end_str:
            try:
                start_parts = start_str.split(":")
                end_parts = end_str.split(":")
                start = time(int(start_parts[0]), int(start_parts[1]) if len(start_parts) > 1 else 0)
                end = time(int(end_parts[0]), int(end_parts[1]) if len(end_parts) > 1 else 0)
                return (start, end)
            except (ValueError, IndexError):
                pass
    
    return None


def get_light_bindings(bindings: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Получить bindings для освещения по ролям.
    
    Args:
        bindings: Dict[role, binding_info] из InfrastructureRepository
    
    Returns:
        Список bindings для освещения
    """
    result: List[Dict[str, Any]] = []
    seen_nodes: set = set()
    
    # Ищем по ролям: light, white_light, uv_light, grow_light
    for role in ['light', 'white_light', 'uv_light', 'grow_light']:
        if role in bindings and bindings[role]['direction'] == 'actuator':
            node_uid = bindings[role]['node_uid']
            if node_uid not in seen_nodes:
                seen_nodes.add(node_uid)
                result.append({
                    'node_id': bindings[role]['node_id'],
                    'node_uid': node_uid,
                    'channel': bindings[role]['channel'],
                    'asset_type': bindings[role]['asset_type'],
                })
    
    return result


async def check_light_failure(zone_id: int, should_be_on: bool) -> bool:
    """
    Проверка на отказ освещения.
    
    Если свет должен быть включен, но показания light_sensor не отличаются от ночного уровня.
    
    Returns:
        True если обнаружен отказ, False если все в порядке
    """
    if not should_be_on:
        return False
    
    # Получаем текущее значение light_sensor
    rows = await fetch(
        """
        SELECT tl.last_value as value
        FROM telemetry_last tl
        JOIN sensors s ON s.id = tl.sensor_id
        WHERE s.zone_id = $1
          AND s.type = 'LIGHT_INTENSITY'
          AND s.is_active = TRUE
        ORDER BY tl.last_ts DESC NULLS LAST,
          tl.updated_at DESC NULLS LAST,
          tl.sensor_id DESC
        LIMIT 1
        """,
        zone_id,
    )
    
    if not rows or rows[0]["value"] is None:
        # Нет данных - не можем определить отказ
        return False
    
    light_value = float(rows[0]["value"])
    
    # Если свет должен быть включен, но показания ниже порога - отказ
    if light_value < LIGHT_FAILURE_THRESHOLD:
        return True
    
    return False


async def check_and_control_lighting(
    zone_id: int,
    targets: Dict[str, Any],
    bindings: Dict[str, Dict[str, Any]],
    current_time: Optional[datetime] = None
) -> Optional[Dict[str, Any]]:
    """
    Проверка и управление освещением зоны.
    
    Логика: if hour in active_hours → light_on, else → light_off
    
    Args:
        zone_id: ID зоны
        targets: Целевые значения из рецепта (light_hours, light_intensity)
        bindings: Dict[role, binding_info] из InfrastructureRepository
        current_time: Текущее время (если None, используется datetime.now())
    
    Returns:
        Команда для управления освещением или None
    """
    if current_time is None:
        current_time = utcnow()
    
    current_hour = current_time.hour
    current_minute = current_time.minute
    current_time_obj = time(current_hour, current_minute)
    
    # Получаем фотопериод из targets
    light_hours = targets.get("light_hours") or targets.get("photoperiod")
    photoperiod = parse_photoperiod(light_hours)
    
    if photoperiod is None:
        # Нет настроек фотопериода
        return None
    
    start_time, end_time = photoperiod
    
    # Проверяем, находится ли текущее время в активном периоде
    # Учитываем случай, когда период переходит через полночь (например, 22:00-06:00)
    if start_time <= end_time:
        # Обычный случай: период в пределах одного дня (например, 06:00-22:00)
        should_be_on = start_time <= current_time_obj <= end_time
    else:
        # Период переходит через полночь (например, 22:00-06:00)
        should_be_on = current_time_obj >= start_time or current_time_obj <= end_time
    
    # Получаем bindings для освещения
    light_bindings = get_light_bindings(bindings)
    if not light_bindings:
        # Нет binding для освещения - создаем alert
        await ensure_alert(zone_id, 'MISSING_BINDING', {
            'binding_role': 'light',
            'required_for': 'light_control',
        })
        return None
    
    # Проверяем на отказ освещения
    light_failure = await check_light_failure(zone_id, should_be_on)
    if light_failure:
        # Создаем алерт LIGHT_FAILURE
        await ensure_light_failure_alert(zone_id)
    
    # Получаем интенсивность (если задана)
    light_intensity = targets.get("light_intensity") or targets.get("ppfd")
    intensity_value = None
    if light_intensity is not None:
        try:
            intensity_value = int(light_intensity)
            # Ограничиваем диапазон 0-100
            intensity_value = max(0, min(100, intensity_value))
        except (ValueError, TypeError):
            intensity_value = None
    
    # Формируем команду
    if should_be_on:
        cmd = "set_pwm" if intensity_value is not None else "set_relay"
        params = {"value": intensity_value} if intensity_value is not None else {"state": True}
        event_type = "LIGHT_ON"
    else:
        cmd = "set_relay"
        params = {"state": False}
        event_type = "LIGHT_OFF"
    
    return {
        'node_uid': light_bindings[0]['node_uid'],
        'channel': light_bindings[0]['channel'],
        'cmd': cmd,
        'params': params,
        'event_type': event_type,
        'event_details': {
            'should_be_on': should_be_on,
            'photoperiod': f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}",
            'intensity': intensity_value,
            'light_failure': light_failure,
        }
    }


async def ensure_light_failure_alert(zone_id: int) -> None:
    """
    Создание/обновление алерта LIGHT_FAILURE.
    """
    # Проверяем, есть ли уже активный алерт
    rows = await fetch(
        """
        SELECT id
        FROM alerts
        WHERE zone_id = $1 AND type = 'LIGHT_FAILURE' AND status = 'ACTIVE'
        """,
        zone_id,
    )
    
    if not rows:
        # Создаем новый алерт
        await create_alert(
            zone_id=zone_id,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_LIGHT_FAILURE.value,
            type='LIGHT_FAILURE',
            details={'message': 'Light should be on but sensor readings indicate failure'}
        )
        # Создаем событие
        await create_zone_event(
            zone_id,
            'LIGHT_FAILURE',
            {
                'message': 'Light should be on but sensor readings indicate failure'
            }
        )
        # Создаем событие ALERT_CREATED
        await create_zone_event(
            zone_id,
            'ALERT_CREATED',
            {
                'alert_type': 'LIGHT_FAILURE',
                'message': 'Light should be on but sensor readings indicate failure'
            }
        )
