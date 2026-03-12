"""
Climate Controller - управление температурой, влажностью и вентиляцией.
Согласно ZONE_CONTROLLER_FULL.md раздел 5
"""
from typing import Optional, Dict, Any, List, Tuple
from common.db import fetch, execute, create_zone_event
from alerts_manager import ensure_alert


# Пороги для алертов
TEMP_HIGH_THRESHOLD = 2.0  # °C выше цели
TEMP_LOW_THRESHOLD = 2.0  # °C ниже цели
HUMIDITY_HIGH_THRESHOLD = 15  # % выше цели
HUMIDITY_LOW_THRESHOLD = 15  # % ниже цели
CO2_LOW_THRESHOLD = 400  # ppm - минимальный порог CO₂

# Гистерезис для предотвращения "дребезга"
TEMP_HYSTERESIS = 0.5  # °C
HUMIDITY_HYSTERESIS = 3  # %


async def get_climate_nodes(zone_id: int) -> Dict[str, Dict[str, Any]]:
    """
    Получить климатические узлы для зоны.
    
    Returns:
        Dict с ключами: 'fan', 'heater', 'climate_sensor'
    """
    rows = await fetch(
        """
        SELECT n.id, n.uid, n.type, nc.channel
        FROM nodes n
        LEFT JOIN node_channels nc ON nc.node_id = n.id
        WHERE n.zone_id = $1 AND n.status = 'online'
          AND (n.type = 'climate' OR nc.channel IN ('fan_A', 'fan_B', 'heater_1', 'temperature', 'humidity'))
        """,
        zone_id,
    )
    
    result: Dict[str, Dict[str, Any]] = {
        'fan': None,
        'heater': None,
        'climate_sensor': None,
    }
    
    for row in rows:
        node_type = row["type"]
        channel = row["channel"] or "default"
        
        # Ищем вентилятор
        if channel in ('fan_A', 'fan_B') or (node_type == 'climate' and 'fan' in channel.lower()):
            if result['fan'] is None:
                result['fan'] = {
                    'node_id': row["id"],
                    'node_uid': row["uid"],
                    'type': node_type,
                    'channel': channel,
                }
        
        # Ищем нагреватель
        if channel == 'heater_1' or (node_type == 'climate' and 'heater' in channel.lower()):
            if result['heater'] is None:
                result['heater'] = {
                    'node_id': row["id"],
                    'node_uid': row["uid"],
                    'type': node_type,
                    'channel': channel,
                }
        
        # Ищем сенсор климата
        if channel in ('temperature', 'humidity') or node_type == 'climate':
            if result['climate_sensor'] is None:
                result['climate_sensor'] = {
                    'node_id': row["id"],
                    'node_uid': row["uid"],
                    'type': node_type,
                }
    
    return result


async def check_and_control_climate(
    zone_id: int,
    targets: Dict[str, Any],
    telemetry: Dict[str, Optional[float]]
) -> List[Dict[str, Any]]:
    """
    Проверка и управление климатом зоны.
    
    Args:
        zone_id: ID зоны
        targets: Целевые значения из рецепта (temp_air, humidity_air)
        telemetry: Текущие значения телеметрии
    
    Returns:
        Список команд для отправки узлам
    """
    commands: List[Dict[str, Any]] = []
    
    # Получаем текущие значения
    temp_air = telemetry.get("TEMP_AIR") or telemetry.get("temp_air")
    humidity = telemetry.get("HUMIDITY") or telemetry.get("humidity")
    co2 = telemetry.get("CO2") or telemetry.get("co2")
    
    # Получаем целевые значения
    target_temp = targets.get("temp_air")
    target_humidity = targets.get("humidity_air")
    
    # Получаем узлы
    nodes = await get_climate_nodes(zone_id)
    
    # Контроль температуры
    if target_temp is not None and temp_air is not None:
        temp_val = float(temp_air)
        target_temp_val = float(target_temp)
        
        # Проверка алертов
        await check_temp_alerts(zone_id, temp_val, target_temp_val)
        
        # Логика управления: if temp_air < target.min → heater, if temp_air > target.max → fans
        # Если target_temp - это одно значение, используем гистерезис
        temp_min = target_temp_val - TEMP_HYSTERESIS
        temp_max = target_temp_val + TEMP_HYSTERESIS
        
        if temp_val < temp_min and nodes['heater']:
            # Включаем нагреватель
            commands.append({
                'node_uid': nodes['heater']['node_uid'],
                'channel': nodes['heater']['channel'],
                'cmd': 'set_relay',
                'params': {'state': True},
                'event_type': 'CLIMATE_HEATING_ON',
                'event_details': {
                    'temp_air': temp_val,
                    'target_temp': target_temp_val,
                    'action': 'heating_on'
                }
            })
        elif temp_val > temp_max and nodes['fan']:
            # Включаем вентилятор (охлаждение)
            commands.append({
                'node_uid': nodes['fan']['node_uid'],
                'channel': nodes['fan']['channel'],
                'cmd': 'set_relay',
                'params': {'state': True},
                'event_type': 'CLIMATE_COOLING_ON',
                'event_details': {
                    'temp_air': temp_val,
                    'target_temp': target_temp_val,
                    'action': 'cooling_on'
                }
            })
        elif temp_min <= temp_val <= temp_max:
            # Выключаем все, если температура в норме
            if nodes['heater']:
                commands.append({
                    'node_uid': nodes['heater']['node_uid'],
                    'channel': nodes['heater']['channel'],
                    'cmd': 'set_relay',
                    'params': {'state': False},
                    'event_type': None,  # Не создаем событие при выключении
                })
            if nodes['fan']:
                commands.append({
                    'node_uid': nodes['fan']['node_uid'],
                    'channel': nodes['fan']['channel'],
                    'cmd': 'set_relay',
                    'params': {'state': False},
                    'event_type': 'FAN_OFF',  # Создаем событие при выключении вентилятора
                })
        
        # Событие при перегреве
        if temp_val > target_temp_val + TEMP_HIGH_THRESHOLD:
            await create_zone_event(
                zone_id,
                'CLIMATE_OVERHEAT',
                {
                    'temp_air': temp_val,
                    'target_temp': target_temp_val,
                    'diff': temp_val - target_temp_val
                }
            )
    
    # Контроль влажности
    if target_humidity is not None and humidity is not None:
        humidity_val = float(humidity)
        target_humidity_val = float(target_humidity)
        
        # Проверка алертов
        await check_humidity_alerts(zone_id, humidity_val, target_humidity_val)
        
        # Логика: if humidity > target.max → increase ventilation
        humidity_max = target_humidity_val + HUMIDITY_HYSTERESIS
        
        if humidity_val > humidity_max and nodes['fan']:
            # Увеличиваем вентиляцию
            commands.append({
                'node_uid': nodes['fan']['node_uid'],
                'channel': nodes['fan']['channel'],
                'cmd': 'set_pwm',
                'params': {'value': 100},  # Максимальная вентиляция
                'event_type': 'FAN_ON',
                'event_details': {
                    'humidity': humidity_val,
                    'target_humidity': target_humidity_val,
                    'action': 'increase_ventilation'
                }
            })
        elif humidity_val <= target_humidity_val and nodes['fan']:
            # Нормальная вентиляция (средняя)
            commands.append({
                'node_uid': nodes['fan']['node_uid'],
                'channel': nodes['fan']['channel'],
                'cmd': 'set_pwm',
                'params': {'value': 50},  # Средняя вентиляция
                'event_type': 'FAN_ON',  # Вентилятор все еще работает
                'event_details': {
                    'humidity': humidity_val,
                    'target_humidity': target_humidity_val,
                    'action': 'normal_ventilation'
                }
            })
    
    # Контроль CO₂ (опционально)
    if co2 is not None:
        co2_val = float(co2)
        if co2_val < CO2_LOW_THRESHOLD:
            # Создаем событие при низком CO₂
            await create_zone_event(
                zone_id,
                'CO2_LOW',
                {
                    'co2': co2_val,
                    'threshold': CO2_LOW_THRESHOLD
                }
            )
    
    return commands


async def check_temp_alerts(zone_id: int, temp_air: float, target_temp: float) -> None:
    """Создание алертов для температуры."""
    # TEMP_HIGH: temp_air > target_temp + 2.0
    if temp_air > target_temp + TEMP_HIGH_THRESHOLD:
        await ensure_alert(zone_id, 'TEMP_HIGH', {
            'temp_air': temp_air,
            'target_temp': target_temp,
            'diff': temp_air - target_temp
        })
    # TEMP_LOW: temp_air < target_temp - 2.0
    elif temp_air < target_temp - TEMP_LOW_THRESHOLD:
        await ensure_alert(zone_id, 'TEMP_LOW', {
            'temp_air': temp_air,
            'target_temp': target_temp,
            'diff': target_temp - temp_air
        })


async def check_humidity_alerts(zone_id: int, humidity: float, target_humidity: float) -> None:
    """Создание алертов для влажности."""
    # HUMIDITY_HIGH: humidity > target_hum + 15
    if humidity > target_humidity + HUMIDITY_HIGH_THRESHOLD:
        await ensure_alert(zone_id, 'HUMIDITY_HIGH', {
            'humidity': humidity,
            'target_humidity': target_humidity,
            'diff': humidity - target_humidity
        })
    # HUMIDITY_LOW: humidity < target_hum - 15
    elif humidity < target_humidity - HUMIDITY_LOW_THRESHOLD:
        await ensure_alert(zone_id, 'HUMIDITY_LOW', {
            'humidity': humidity,
            'target_humidity': target_humidity,
            'diff': target_humidity - humidity
        })

