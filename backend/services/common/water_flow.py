"""
Water Flow Engine - контроль уровня воды, расхода и защита от сухого хода.
Согласно WATER_FLOW_ENGINE.md
"""
import asyncio
import os
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timedelta
from .db import fetch, execute, create_zone_event
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


# Пороги для контроля воды
WATER_LEVEL_LOW_THRESHOLD = 0.2  # 20% - низкий уровень
MIN_FLOW_THRESHOLD = 0.1  # L/min - минимальный поток для обнаружения работы насоса
DRY_RUN_CHECK_DELAY_SEC = 3  # Задержка перед проверкой flow после запуска насоса


async def check_water_level(zone_id: int) -> Tuple[bool, Optional[float]]:
    """
    Проверка уровня воды в зоне.
    
    Returns:
        (is_ok, level_value): True если уровень нормальный (>= 0.2), False если низкий
    """
    rows = await fetch(
        """
        SELECT value
        FROM telemetry_last
        WHERE zone_id = $1 AND metric_type = 'WATER_LEVEL'
        """,
        zone_id,
    )
    
    if not rows or rows[0]["value"] is None:
        # Если нет данных о уровне - считаем что уровень нормальный (не блокируем)
        return True, None
    
    level = float(rows[0]["value"])
    is_ok = level >= WATER_LEVEL_LOW_THRESHOLD
    
    return is_ok, level


async def check_flow(zone_id: int, min_flow: float = MIN_FLOW_THRESHOLD) -> Tuple[bool, Optional[float]]:
    """
    Проверка расхода воды в зоне.
    
    Args:
        zone_id: ID зоны
        min_flow: Минимальный порог расхода (L/min)
    
    Returns:
        (is_ok, flow_value): True если расход >= min_flow, False если меньше
    """
    rows = await fetch(
        """
        SELECT value
        FROM telemetry_last
        WHERE zone_id = $1 AND metric_type = 'FLOW'
        """,
        zone_id,
    )
    
    if not rows or rows[0]["value"] is None:
        # Если нет данных о расходе - считаем что flow отсутствует
        return False, None
    
    flow = float(rows[0]["value"])
    is_ok = flow >= min_flow
    
    return is_ok, flow


async def check_dry_run_protection(
    zone_id: int,
    pump_start_time: datetime,
    min_flow: float = MIN_FLOW_THRESHOLD
) -> Tuple[bool, Optional[str]]:
    """
    Защита от сухого хода насоса.
    
    Алгоритм: pump_run_time > 3 сек AND flow < threshold → NO_FLOW alert → stop pump
    
    Args:
        zone_id: ID зоны
        pump_start_time: Время запуска насоса
        min_flow: Минимальный порог расхода
    
    Returns:
        (is_safe, error_message): True если безопасно, False если обнаружен сухой ход
    """
    now = datetime.utcnow()
    elapsed_sec = (now - pump_start_time).total_seconds()
    
    # Проверяем только если прошло больше 3 секунд
    if elapsed_sec < DRY_RUN_CHECK_DELAY_SEC:
        return True, None
    
    # Проверяем flow
    flow_ok, flow_value = await check_flow(zone_id, min_flow)
    
    if not flow_ok:
        # Создаем событие NO_FLOW
        await create_zone_event(
            zone_id,
            'NO_FLOW',
            {
                'pump_start_time': pump_start_time.isoformat(),
                'elapsed_sec': elapsed_sec,
                'flow_value': flow_value,
                'min_flow_threshold': min_flow
            }
        )
        return False, f"NO_FLOW detected: flow={flow_value} L/min < {min_flow} L/min after {elapsed_sec:.1f}s"
    
    return True, None


async def calculate_irrigation_volume(
    zone_id: int,
    start_time: datetime,
    end_time: datetime
) -> float:
    """
    Расчет объема полива на основе flow за период времени.
    
    Формула: volume_L = sum(flow * dt)
    
    Args:
        zone_id: ID зоны
        start_time: Время начала полива
        end_time: Время окончания полива
    
    Returns:
        Объем в литрах
    """
    # Получаем данные flow за период из telemetry_samples
    rows = await fetch(
        """
        SELECT value, created_at
        FROM telemetry_samples
        WHERE zone_id = $1 
          AND metric_type = 'FLOW'
          AND created_at >= $2
          AND created_at <= $3
        ORDER BY created_at ASC
        """,
        zone_id,
        start_time,
        end_time,
    )
    
    if not rows or len(rows) < 2:
        # Если нет данных - возвращаем 0
        return 0.0
    
    total_volume = 0.0
    
    # Вычисляем объем как интеграл flow по времени
    for i in range(len(rows) - 1):
        flow1 = float(rows[i]["value"]) if rows[i]["value"] is not None else 0.0
        time1 = rows[i]["created_at"]
        flow2 = float(rows[i + 1]["value"]) if rows[i + 1]["value"] is not None else 0.0
        time2 = rows[i + 1]["created_at"]
        
        # Средний flow за интервал
        avg_flow = (flow1 + flow2) / 2.0
        
        # Время в секундах
        dt_sec = (time2 - time1).total_seconds()
        
        # Объем за интервал (flow в L/min, переводим в L/sec)
        volume_segment = avg_flow * (dt_sec / 60.0)
        total_volume += volume_segment
    
    return total_volume


async def ensure_water_level_alert(zone_id: int, level: float) -> None:
    """
    Создание/обновление алерта WATER_LEVEL_LOW если уровень низкий.
    """
    if level < WATER_LEVEL_LOW_THRESHOLD:
        # Проверяем, есть ли уже активный алерт
        rows = await fetch(
            """
            SELECT id
            FROM alerts
            WHERE zone_id = $1 AND type = 'WATER_LEVEL_LOW' AND status = 'ACTIVE'
            """,
            zone_id,
        )
        
        if not rows:
            # Создаем новый алерт
            await execute(
                """
                INSERT INTO alerts (zone_id, type, details, status, created_at)
                VALUES ($1, $2, $3, 'ACTIVE', NOW())
                """,
                zone_id,
                'WATER_LEVEL_LOW',
                f'{{"level": {level}, "threshold": {WATER_LEVEL_LOW_THRESHOLD}}}',
            )
            # Создаем событие
            await create_zone_event(
                zone_id,
                'WATER_LEVEL_LOW',
                {
                    'level': level,
                    'threshold': WATER_LEVEL_LOW_THRESHOLD
                }
            )
            # Создаем событие ALERT_CREATED
            await create_zone_event(
                zone_id,
                'ALERT_CREATED',
                {
                    'alert_type': 'WATER_LEVEL_LOW',
                    'level': level,
                    'threshold': WATER_LEVEL_LOW_THRESHOLD
                }
            )


async def ensure_no_flow_alert(zone_id: int, flow_value: Optional[float], min_flow: float) -> None:
    """
    Создание/обновление алерта NO_FLOW если расход отсутствует.
    """
    if flow_value is None or flow_value < min_flow:
        # Проверяем, есть ли уже активный алерт
        rows = await fetch(
            """
            SELECT id
            FROM alerts
            WHERE zone_id = $1 AND type = 'NO_FLOW' AND status = 'ACTIVE'
            """,
            zone_id,
        )
        
        if not rows:
            # Создаем новый алерт
            await execute(
                """
                INSERT INTO alerts (zone_id, type, details, status, created_at)
                VALUES ($1, $2, $3, 'ACTIVE', NOW())
                """,
                zone_id,
                'NO_FLOW',
                f'{{"flow_value": {flow_value if flow_value is not None else "null"}, "min_flow": {min_flow}}}',
            )
            # Создаем событие ALERT_CREATED
            await create_zone_event(
                zone_id,
                'ALERT_CREATED',
                {
                    'alert_type': 'NO_FLOW',
                    'flow_value': flow_value,
                    'min_flow': min_flow
                }
            )


async def get_irrigation_nodes(zone_id: int) -> List[Dict[str, Any]]:
    """
    Получить узлы для управления водой (irrigation или fill/drain).
    
    Returns:
        Список узлов с информацией о node_uid и channel
    """
    rows = await fetch(
        """
        SELECT n.id, n.uid, n.type, nc.channel
        FROM nodes n
        LEFT JOIN node_channels nc ON nc.node_id = n.id
        WHERE n.zone_id = $1 AND n.status = 'online'
          AND (n.type = 'irrig' OR nc.channel IN ('fill_valve', 'drain_valve', 'water_control'))
        """,
        zone_id,
    )
    
    result = []
    seen_nodes = set()
    
    for row in rows:
        node_uid = row["uid"]
        if node_uid in seen_nodes:
            continue
        seen_nodes.add(node_uid)
        
        result.append({
            'node_id': row["id"],
            'node_uid': node_uid,
            'type': row["type"],
            'channel': row["channel"] or "default",
        })
    
    # Если не нашли специальные узлы, ищем обычные irrigation
    if not result:
        rows = await fetch(
            """
            SELECT n.id, n.uid, n.type, nc.channel
            FROM nodes n
            LEFT JOIN node_channels nc ON nc.node_id = n.id
            WHERE n.zone_id = $1 AND n.type = 'irrig' AND n.status = 'online'
            LIMIT 1
            """,
            zone_id,
        )
        if rows:
            result.append({
                'node_id': rows[0]["id"],
                'node_uid': rows[0]["uid"],
                'type': rows[0]["type"],
                'channel': rows[0]["channel"] or "default",
            })
    
    return result


async def execute_fill_mode(
    zone_id: int,
    target_level: float,
    mqtt_client: Any,  # MqttClient
    gh_uid: str,
    max_duration_sec: int = 300  # Максимальная длительность 5 минут
) -> Dict[str, Any]:
    """
    Режим наполнения (Fill Mode).
    
    Включает клапан подачи и насос, мониторит уровень воды,
    останавливает при достижении target_level.
    
    Args:
        zone_id: ID зоны
        target_level: Целевой уровень воды (0.0-1.0)
        mqtt_client: MQTT клиент для отправки команд
        gh_uid: UID теплицы
        max_duration_sec: Максимальная длительность операции (защита от зависания)
    
    Returns:
        Dict с результатом операции
    """
    fill_start_time = datetime.utcnow()
    
    # Создаем событие FILL_STARTED
    await create_zone_event(
        zone_id,
        'FILL_STARTED',
        {
            'target_level': target_level,
            'start_time': fill_start_time.isoformat()
        }
    )
    
    # Получаем узлы для управления водой
    nodes = await get_irrigation_nodes(zone_id)
    if not nodes:
        await create_zone_event(
            zone_id,
            'FILL_FINISHED',
            {
                'target_level': target_level,
                'status': 'failed',
                'error': 'no_nodes',
                'start_time': fill_start_time.isoformat(),
                'end_time': datetime.utcnow().isoformat()
            }
        )
        return {'success': False, 'error': 'no_nodes'}
    
    node_info = nodes[0]
    
    # Отправляем команду fill
    payload = {"cmd": "fill", "params": {"target_level": target_level}}
    topic = f"hydro/{gh_uid}/zn-{zone_id}/{node_info['node_uid']}/{node_info['channel']}/command"
    mqtt_client.publish_json(topic, payload, qos=1, retain=False)
    
    # Мониторим уровень воды каждые 2 секунды
    check_interval = 2.0
    start_time = datetime.utcnow()
    
    while True:
        await asyncio.sleep(check_interval)
        
        # Проверяем таймаут
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        if elapsed > max_duration_sec:
            # Отправляем команду остановки
            stop_payload = {"cmd": "stop"}
            mqtt_client.publish_json(topic, stop_payload, qos=1, retain=False)
            
            await create_zone_event(
                zone_id,
                'FILL_FINISHED',
                {
                    'target_level': target_level,
                    'status': 'timeout',
                    'elapsed_sec': elapsed,
                    'start_time': fill_start_time.isoformat(),
                    'end_time': datetime.utcnow().isoformat()
                }
            )
            return {'success': False, 'error': 'timeout', 'elapsed_sec': elapsed}
        
        # Проверяем уровень воды
        _, current_level = await check_water_level(zone_id)
        
        if current_level is not None:
            if current_level >= target_level:
                # Достигли целевого уровня - останавливаем
                stop_payload = {"cmd": "stop"}
                mqtt_client.publish_json(topic, stop_payload, qos=1, retain=False)
                
                fill_end_time = datetime.utcnow()
                await create_zone_event(
                    zone_id,
                    'FILL_FINISHED',
                    {
                        'target_level': target_level,
                        'final_level': current_level,
                        'status': 'completed',
                        'elapsed_sec': (fill_end_time - fill_start_time).total_seconds(),
                        'start_time': fill_start_time.isoformat(),
                        'end_time': fill_end_time.isoformat()
                    }
                )
                return {
                    'success': True,
                    'target_level': target_level,
                    'final_level': current_level,
                    'elapsed_sec': (fill_end_time - fill_start_time).total_seconds()
                }


async def execute_drain_mode(
    zone_id: int,
    target_level: float,
    mqtt_client: Any,  # MqttClient
    gh_uid: str,
    max_duration_sec: int = 300  # Максимальная длительность 5 минут
) -> Dict[str, Any]:
    """
    Режим слива (Drain Mode).
    
    Включает сливной насос/клапан, мониторит уровень воды,
    останавливает при достижении target_level.
    
    Args:
        zone_id: ID зоны
        target_level: Целевой уровень воды (0.0-1.0)
        mqtt_client: MQTT клиент для отправки команд
        gh_uid: UID теплицы
        max_duration_sec: Максимальная длительность операции (защита от зависания)
    
    Returns:
        Dict с результатом операции
    """
    drain_start_time = datetime.utcnow()
    
    # Создаем событие DRAIN_STARTED
    await create_zone_event(
        zone_id,
        'DRAIN_STARTED',
        {
            'target_level': target_level,
            'start_time': drain_start_time.isoformat()
        }
    )
    
    # Получаем узлы для управления водой
    nodes = await get_irrigation_nodes(zone_id)
    if not nodes:
        await create_zone_event(
            zone_id,
            'DRAIN_FINISHED',
            {
                'target_level': target_level,
                'status': 'failed',
                'error': 'no_nodes',
                'start_time': drain_start_time.isoformat(),
                'end_time': datetime.utcnow().isoformat()
            }
        )
        return {'success': False, 'error': 'no_nodes'}
    
    node_info = nodes[0]
    
    # Отправляем команду drain
    payload = {"cmd": "drain", "params": {"target_level": target_level}}
    topic = f"hydro/{gh_uid}/zn-{zone_id}/{node_info['node_uid']}/{node_info['channel']}/command"
    mqtt_client.publish_json(topic, payload, qos=1, retain=False)
    
    # Мониторим уровень воды каждые 2 секунды
    check_interval = 2.0
    start_time = datetime.utcnow()
    
    while True:
        await asyncio.sleep(check_interval)
        
        # Проверяем таймаут
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        if elapsed > max_duration_sec:
            # Отправляем команду остановки
            stop_payload = {"cmd": "stop"}
            mqtt_client.publish_json(topic, stop_payload, qos=1, retain=False)
            
            await create_zone_event(
                zone_id,
                'DRAIN_FINISHED',
                {
                    'target_level': target_level,
                    'status': 'timeout',
                    'elapsed_sec': elapsed,
                    'start_time': drain_start_time.isoformat(),
                    'end_time': datetime.utcnow().isoformat()
                }
            )
            return {'success': False, 'error': 'timeout', 'elapsed_sec': elapsed}
        
        # Проверяем уровень воды
        _, current_level = await check_water_level(zone_id)
        
        if current_level is not None:
            if current_level <= target_level:
                # Достигли целевого уровня - останавливаем
                stop_payload = {"cmd": "stop"}
                mqtt_client.publish_json(topic, stop_payload, qos=1, retain=False)
                
                drain_end_time = datetime.utcnow()
                await create_zone_event(
                    zone_id,
                    'DRAIN_FINISHED',
                    {
                        'target_level': target_level,
                        'final_level': current_level,
                        'status': 'completed',
                        'elapsed_sec': (drain_end_time - drain_start_time).total_seconds(),
                        'start_time': drain_start_time.isoformat(),
                        'end_time': drain_end_time.isoformat()
                    }
                )
                return {
                    'success': True,
                    'target_level': target_level,
                    'final_level': current_level,
                    'elapsed_sec': (drain_end_time - drain_start_time).total_seconds()
                }


async def calibrate_flow(
    zone_id: int,
    node_id: int,
    channel: str,
    mqtt_client: Any,  # MqttClient
    gh_uid: str,
    pump_duration_sec: int = 10
) -> Dict[str, Any]:
    """
    Калибровка расхода воды.
    
    Алгоритм:
    1. Запуск насоса на pump_duration_sec секунд
    2. Измерение потока (получение данных из telemetry_samples)
    3. Вычисление постоянной K (пульс → L/min)
    4. Сохранение в node_channel.config через API
    
    Args:
        zone_id: ID зоны
        node_id: ID узла с датчиком расхода
        channel: Канал датчика расхода (например, "flow_sensor")
        mqtt_client: MQTT клиент для отправки команд
        gh_uid: UID теплицы
        pump_duration_sec: Длительность работы насоса для калибровки (по умолчанию 10 сек)
    
    Returns:
        Результат калибровки с вычисленной постоянной K
    """
    if not HTTPX_AVAILABLE:
        raise RuntimeError("httpx is required for flow calibration")
    
    # Получаем информацию об узле и канале
    node_rows = await fetch(
        """
        SELECT n.id, n.uid, n.zone_id, nc.id as channel_id, nc.config
        FROM nodes n
        LEFT JOIN node_channels nc ON nc.node_id = n.id AND nc.channel = $1
        WHERE n.id = $2 AND n.zone_id = $3
        """,
        channel,
        node_id,
        zone_id,
    )
    
    if not node_rows:
        raise ValueError(f"Node {node_id} or channel {channel} not found in zone {zone_id}")
    
    node_info = node_rows[0]
    node_uid = node_info["uid"]
    channel_id = node_info.get("channel_id")
    
    if not channel_id:
        raise ValueError(f"Channel {channel} not found for node {node_id}")
    
    # Получаем насос для запуска
    pump_rows = await fetch(
        """
        SELECT n.id, n.uid, nc.channel
        FROM nodes n
        LEFT JOIN node_channels nc ON nc.node_id = n.id
        WHERE n.zone_id = $1 AND n.type = 'irrig' AND n.status = 'online'
        LIMIT 1
        """,
        zone_id,
    )
    
    if not pump_rows:
        raise ValueError(f"No irrigation pump found in zone {zone_id}")
    
    pump_info = pump_rows[0]
    pump_node_uid = pump_info["uid"]
    pump_channel = pump_info.get("channel") or "pump_irrigation"
    
    # Проверяем уровень воды перед запуском
    water_level_ok, water_level = await check_water_level(zone_id)
    if not water_level_ok:
        raise ValueError(f"Water level too low for calibration: {water_level}")
    
    # Запускаем насос
    calibration_start_time = datetime.utcnow()
    
    # Публикуем команду запуска насоса через MQTT
    payload = {"cmd": "run", "params": {"sec": pump_duration_sec}}
    topic = f"hydro/{gh_uid}/zn-{zone_id}/{pump_node_uid}/{pump_channel}/command"
    mqtt_client.publish_json(topic, payload, qos=1, retain=False)
    
    # Создаем событие начала калибровки
    await create_zone_event(
        zone_id,
        'FLOW_CALIBRATION_STARTED',
        {
            'node_id': node_id,
            'channel': channel,
            'pump_duration_sec': pump_duration_sec,
            'start_time': calibration_start_time.isoformat()
        }
    )
    
    # Ждем завершения работы насоса + небольшая задержка для получения всех данных
    await asyncio.sleep(pump_duration_sec + 2)
    
    calibration_end_time = datetime.utcnow()
    
    # Получаем данные flow за период калибровки
    flow_rows = await fetch(
        """
        SELECT value, created_at, raw
        FROM telemetry_samples
        WHERE zone_id = $1 
          AND node_id = $2
          AND channel = $3
          AND metric_type = 'FLOW'
          AND created_at >= $4
          AND created_at <= $5
        ORDER BY created_at ASC
        """,
        zone_id,
        node_id,
        channel,
        calibration_start_time,
        calibration_end_time,
    )
    
    if not flow_rows or len(flow_rows) < 2:
        raise ValueError(f"Insufficient flow data for calibration: {len(flow_rows) if flow_rows else 0} samples")
    
    # Вычисляем средний flow
    flow_values = [float(row["value"]) for row in flow_rows if row["value"] is not None]
    if not flow_values:
        raise ValueError("No valid flow values found")
    
    avg_flow = sum(flow_values) / len(flow_values)
    
    # Получаем raw данные (пульсы) для вычисления K
    # Предполагаем, что raw содержит поле "pulses" или "count"
    pulse_values = []
    for row in flow_rows:
        raw_data = row.get("raw")
        if raw_data and isinstance(raw_data, dict):
            pulses = raw_data.get("pulses") or raw_data.get("count") or raw_data.get("pulse_count")
            if pulses is not None:
                pulse_values.append(float(pulses))
    
    # Если нет данных о пульсах, используем упрощенный подход
    # K = avg_flow / (pulses_per_minute), но если нет pulses, используем K = 1.0
    if pulse_values:
        total_pulses = sum(pulse_values)
        # Предполагаем, что измерения были за pump_duration_sec секунд
        pulses_per_minute = (total_pulses / pump_duration_sec) * 60.0
        if pulses_per_minute > 0:
            K = avg_flow / pulses_per_minute
        else:
            K = 1.0
    else:
        # Если нет данных о пульсах, устанавливаем K = 1.0 (предполагаем, что flow уже в L/min)
        K = 1.0
    
    # Сохраняем K в node_channel.config через Laravel API
    from .env import get_settings
    settings = get_settings()
    api_url = settings.laravel_api_url
    api_token = settings.laravel_api_token
    
    # Обновляем config канала
    config_update = {
        "flow_calibration": {
            "K": K,
            "calibrated_at": calibration_end_time.isoformat(),
            "avg_flow_l_per_min": avg_flow,
            "pump_duration_sec": pump_duration_sec,
            "samples_count": len(flow_rows)
        }
    }
    
    # Получаем текущий config
    current_config = node_info.get("config") or {}
    if isinstance(current_config, dict):
        current_config.update(config_update)
    else:
        current_config = config_update
    
    # Обновляем через API
    async with httpx.AsyncClient() as client:
        headers = {}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        
        response = await client.patch(
            f"{api_url}/api/node-channels/{channel_id}",
            json={"config": current_config},
            headers=headers,
            timeout=10.0
        )
        
        if response.status_code != 200:
            raise RuntimeError(f"Failed to update node channel config: {response.status_code} {response.text}")
    
    # Создаем событие завершения калибровки
    await create_zone_event(
        zone_id,
        'FLOW_CALIBRATION_FINISHED',
        {
            'node_id': node_id,
            'channel': channel,
            'K': K,
            'avg_flow_l_per_min': avg_flow,
            'samples_count': len(flow_rows),
            'end_time': calibration_end_time.isoformat()
        }
    )
    
    return {
        'success': True,
        'K': K,
        'avg_flow_l_per_min': avg_flow,
        'samples_count': len(flow_rows),
        'pump_duration_sec': pump_duration_sec,
        'calibrated_at': calibration_end_time.isoformat()
    }

