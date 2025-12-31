"""
Climate Controller - управление температурой, влажностью и вентиляцией.
Согласно ZONE_CONTROLLER_FULL.md раздел 5
"""
from typing import Optional, Dict, Any, List, Tuple
from common.db import fetch, execute, create_zone_event
from alerts_manager import ensure_alert
from services.targets_accessor import get_climate_request


# Пороги для алертов
TEMP_HIGH_THRESHOLD = 2.0  # °C выше цели
TEMP_LOW_THRESHOLD = 2.0  # °C ниже цели
HUMIDITY_HIGH_THRESHOLD = 15  # % выше цели
HUMIDITY_LOW_THRESHOLD = 15  # % ниже цели
CO2_LOW_THRESHOLD = 400  # ppm - минимальный порог CO₂

# Гистерезис для предотвращения "дребезга"
TEMP_HYSTERESIS = 0.5  # °C
HUMIDITY_HYSTERESIS = 3  # %


def get_climate_bindings(zone_id: int, bindings: Dict[str, Dict[str, Any]]) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Получить климатические bindings для зоны по ролям.
    
    Args:
        zone_id: ID зоны
        bindings: Dict[role, binding_info] из InfrastructureRepository
    
    Returns:
        Dict с ключами: 'fan', 'heater', 'climate_sensor'
        Если binding отсутствует, значение будет None
    """
    result: Dict[str, Optional[Dict[str, Any]]] = {
        'fan': None,
        'heater': None,
        'climate_sensor': None,
    }
    
    # Ищем вентилятор по ролям: vent, fan, ventilation
    for role in ['vent', 'fan', 'ventilation']:
        if role in bindings and bindings[role]['direction'] == 'actuator':
            result['fan'] = {
                'node_id': bindings[role]['node_id'],
                'node_uid': bindings[role]['node_uid'],
                'channel': bindings[role]['channel'],
                'asset_type': bindings[role]['asset_type'],
            }
            break
    
    # Ищем нагреватель по ролям: heater, heating
    for role in ['heater', 'heating']:
        if role in bindings and bindings[role]['direction'] == 'actuator':
            result['heater'] = {
                'node_id': bindings[role]['node_id'],
                'node_uid': bindings[role]['node_uid'],
                'channel': bindings[role]['channel'],
                'asset_type': bindings[role]['asset_type'],
            }
            break
    
    # Ищем сенсор климата по ролям: climate_sensor, temperature_sensor, humidity_sensor
    for role in ['climate_sensor', 'temperature_sensor', 'humidity_sensor']:
        if role in bindings and bindings[role]['direction'] == 'sensor':
            result['climate_sensor'] = {
                'node_id': bindings[role]['node_id'],
                'node_uid': bindings[role]['node_uid'],
                'channel': bindings[role]['channel'],
                'asset_type': bindings[role]['asset_type'],
            }
            break
    
    return result


async def check_and_control_climate(
    zone_id: int,
    targets: Dict[str, Any],
    telemetry: Dict[str, Optional[float]],
    bindings: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Проверка и управление климатом зоны.
    
    Args:
        zone_id: ID зоны
        targets: Целевые значения из рецепта (climate_request)
        telemetry: Текущие значения телеметрии
        bindings: Dict[role, binding_info] из InfrastructureRepository
    
    Returns:
        Список команд для отправки узлам
    """
    commands: List[Dict[str, Any]] = []
    
    # Получаем текущие значения
    temp_air = telemetry.get("TEMPERATURE")
    humidity = telemetry.get("HUMIDITY")
    co2 = telemetry.get("CO2")
    
    # Получаем целевые значения
    target_temp, target_humidity, _ = get_climate_request(targets, zone_id=zone_id)
    
    # Получаем bindings по ролям
    nodes = get_climate_bindings(zone_id, bindings)
    
    # Проверяем наличие обязательных bindings и создаём alerts при их отсутствии
    if target_temp is not None:
        # Для управления температурой нужен либо heater, либо fan
        if temp_air is not None:
            temp_val = float(temp_air)
            target_temp_val = float(target_temp)
            
            if temp_val < target_temp_val - TEMP_HYSTERESIS and not nodes['heater']:
                # Нужен нагреватель, но его нет
                await ensure_alert(zone_id, 'MISSING_BINDING', {
                    'binding_role': 'heater',
                    'required_for': 'temperature_control',
                    'current_temp': temp_val,
                    'target_temp': target_temp_val,
                })
            
            if temp_val > target_temp_val + TEMP_HYSTERESIS and not nodes['fan']:
                # Нужен вентилятор, но его нет
                await ensure_alert(zone_id, 'MISSING_BINDING', {
                    'binding_role': 'vent',
                    'required_for': 'temperature_control',
                    'current_temp': temp_val,
                    'target_temp': target_temp_val,
                })
    
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
        elif temp_val > temp_max:
            if nodes['fan']:
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
            else:
                # Нет binding для вентилятора - alert уже создан выше
                pass
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
        
        if humidity_val > humidity_max:
            if nodes['fan']:
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
            else:
                # Нет binding для вентилятора
                await ensure_alert(zone_id, 'MISSING_BINDING', {
                    'binding_role': 'vent',
                    'required_for': 'humidity_control',
                    'current_humidity': humidity_val,
                    'target_humidity': target_humidity_val,
                })
        elif humidity_val <= target_humidity_val:
            if nodes['fan']:
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
