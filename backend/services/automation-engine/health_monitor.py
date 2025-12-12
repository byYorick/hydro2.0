"""
Zone Health Monitor - анализ состояния зоны и расчет health_score.
Согласно ZONE_CONTROLLER_FULL.md раздел 8
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from common.utils.time import utcnow
from common.db import fetch, execute
from common.water_flow import check_water_level, check_flow


async def calculate_ph_stability(zone_id: int, hours: int = 2) -> float:
    """
    Анализ стабильности pH за последние N часов.
    
    Returns:
        Оценка стабильности 0-100 (100 = идеальная стабильность)
    """
    cutoff_time = utcnow() - timedelta(hours=hours)
    
    rows = await fetch(
        """
        SELECT value, created_at
        FROM telemetry_samples
        WHERE zone_id = $1 
          AND metric_type = 'PH'
          AND created_at >= $2
        ORDER BY created_at ASC
        """,
        zone_id,
        cutoff_time,
    )
    
    if not rows or len(rows) < 2:
        # Недостаточно данных
        return 50.0
    
    values = [float(row["value"]) for row in rows if row["value"] is not None]
    if len(values) < 2:
        return 50.0
    
    # Вычисляем стандартное отклонение
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std_dev = variance ** 0.5
    
    # Оценка: чем меньше отклонение, тем выше оценка
    # pH обычно должен быть в диапазоне 5.5-6.5, отклонение > 0.5 - плохо
    if std_dev < 0.1:
        return 100.0
    elif std_dev < 0.2:
        return 80.0
    elif std_dev < 0.3:
        return 60.0
    elif std_dev < 0.5:
        return 40.0
    else:
        return 20.0


async def calculate_ec_stability(zone_id: int, hours: int = 2) -> float:
    """
    Анализ стабильности EC за последние N часов.
    
    Returns:
        Оценка стабильности 0-100
    """
    cutoff_time = utcnow() - timedelta(hours=hours)
    
    rows = await fetch(
        """
        SELECT value, created_at
        FROM telemetry_samples
        WHERE zone_id = $1 
          AND metric_type = 'EC'
          AND created_at >= $2
        ORDER BY created_at ASC
        """,
        zone_id,
        cutoff_time,
    )
    
    if not rows or len(rows) < 2:
        return 50.0
    
    values = [float(row["value"]) for row in rows if row["value"] is not None]
    if len(values) < 2:
        return 50.0
    
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std_dev = variance ** 0.5
    
    # EC обычно в диапазоне 1.0-2.5, отклонение > 0.2 - плохо
    if std_dev < 0.05:
        return 100.0
    elif std_dev < 0.1:
        return 80.0
    elif std_dev < 0.15:
        return 60.0
    elif std_dev < 0.2:
        return 40.0
    else:
        return 20.0


async def calculate_climate_quality(zone_id: int) -> float:
    """
    Анализ качества климата (температура и влажность).
    
    Returns:
        Оценка качества 0-100
    """
    # Получаем текущие значения и цели из рецепта
    telemetry_rows = await fetch(
        """
        SELECT metric_type, value
        FROM telemetry_last
        WHERE zone_id = $1 AND metric_type IN ('TEMP_AIR', 'HUMIDITY')
        """,
        zone_id,
    )
    
    if not telemetry_rows:
        return 50.0
    
    telemetry = {row["metric_type"]: row["value"] for row in telemetry_rows}
    temp_air = telemetry.get("TEMP_AIR")
    humidity = telemetry.get("HUMIDITY")
    
    # Получаем цели из рецепта
    recipe_rows = await fetch(
        """
        SELECT rp.targets
        FROM zone_recipe_instances zri
        JOIN recipe_phases rp ON rp.recipe_id = zri.recipe_id AND rp.phase_index = zri.current_phase_index
        WHERE zri.zone_id = $1
        """,
        zone_id,
    )
    
    if not recipe_rows or not recipe_rows[0]["targets"]:
        return 50.0
    
    targets = recipe_rows[0]["targets"]
    target_temp = targets.get("temp_air")
    target_humidity = targets.get("humidity_air")
    
    score = 100.0
    
    # Оценка температуры
    if temp_air is not None and target_temp is not None:
        temp_diff = abs(float(temp_air) - float(target_temp))
        if temp_diff > 3.0:
            score -= 30
        elif temp_diff > 2.0:
            score -= 20
        elif temp_diff > 1.0:
            score -= 10
    
    # Оценка влажности
    if humidity is not None and target_humidity is not None:
        hum_diff = abs(float(humidity) - float(target_humidity))
        if hum_diff > 20:
            score -= 30
        elif hum_diff > 15:
            score -= 20
        elif hum_diff > 10:
            score -= 10
    
    return max(0.0, score)


async def count_active_alerts(zone_id: int) -> int:
    """Подсчет активных алертов в зоне."""
    rows = await fetch(
        """
        SELECT COUNT(*) as count
        FROM alerts
        WHERE zone_id = $1 AND status = 'ACTIVE'
        """,
        zone_id,
    )
    
    if rows:
        return int(rows[0]["count"])
    return 0


async def check_node_status(zone_id: int) -> Dict[str, Any]:
    """
    Проверка состояния узлов зоны.
    
    Returns:
        Dict с информацией о узлах (online_count, offline_count, total_count)
    """
    rows = await fetch(
        """
        SELECT status, COUNT(*) as count
        FROM nodes
        WHERE zone_id = $1
        GROUP BY status
        """,
        zone_id,
    )
    
    online_count = 0
    offline_count = 0
    total_count = 0
    
    for row in rows:
        count = int(row["count"])
        total_count += count
        if row["status"] == "online":
            online_count = count
        else:
            offline_count += count
    
    return {
        'online_count': online_count,
        'offline_count': offline_count,
        'total_count': total_count,
    }


async def calculate_zone_health(zone_id: int) -> Dict[str, Any]:
    """
    Расчет общего здоровья зоны.
    
    Returns:
        Dict с health_score (0-100), health_status (ok/warning/alarm) и деталями
    """
    # Анализ стабильности pH
    ph_stability = await calculate_ph_stability(zone_id, hours=2)
    
    # Анализ стабильности EC
    ec_stability = await calculate_ec_stability(zone_id, hours=2)
    
    # Качество климата
    climate_quality = await calculate_climate_quality(zone_id)
    
    # Активные алерты
    active_alerts_count = await count_active_alerts(zone_id)
    alerts_score = max(0, 100 - (active_alerts_count * 15))  # -15 за каждый алерт
    
    # Состояние узлов
    node_status = await check_node_status(zone_id)
    if node_status['total_count'] > 0:
        node_uptime_score = (node_status['online_count'] / node_status['total_count']) * 100
    else:
        node_uptime_score = 50.0
    
    # Уровень воды
    water_level_ok, water_level = await check_water_level(zone_id)
    water_score = 100.0 if water_level_ok else 30.0
    
    # Расход воды (проверяем наличие flow)
    flow_ok, flow_value = await check_flow(zone_id)
    flow_score = 100.0 if flow_ok else 50.0
    
    # Взвешенное среднее для расчета общего health_score
    weights = {
        'ph_stability': 0.20,
        'ec_stability': 0.20,
        'climate_quality': 0.15,
        'alerts_score': 0.20,
        'node_uptime': 0.15,
        'water_score': 0.05,
        'flow_score': 0.05,
    }
    
    health_score = (
        ph_stability * weights['ph_stability'] +
        ec_stability * weights['ec_stability'] +
        climate_quality * weights['climate_quality'] +
        alerts_score * weights['alerts_score'] +
        node_uptime_score * weights['node_uptime'] +
        water_score * weights['water_score'] +
        flow_score * weights['flow_score']
    )
    
    # Определяем статус
    if health_score >= 80:
        health_status = 'ok'
    elif health_score >= 50:
        health_status = 'warning'
    else:
        health_status = 'alarm'
    
    return {
        'health_score': round(health_score, 1),
        'health_status': health_status,
        'details': {
            'ph_stability': round(ph_stability, 1),
            'ec_stability': round(ec_stability, 1),
            'climate_quality': round(climate_quality, 1),
            'active_alerts': active_alerts_count,
            'alerts_score': round(alerts_score, 1),
            'node_uptime_score': round(node_uptime_score, 1),
            'node_status': node_status,
            'water_score': round(water_score, 1),
            'water_level': water_level,
            'flow_score': round(flow_score, 1),
            'flow_value': flow_value,
        }
    }


async def update_zone_health_in_db(zone_id: int, health_data: Dict[str, Any]) -> None:
    """
    Обновление health_score и health_status в таблице zones.
    """
    await execute(
        """
        UPDATE zones
        SET health_score = $1, health_status = $2, updated_at = NOW()
        WHERE id = $3
        """,
        health_data['health_score'],
        health_data['health_status'],
        zone_id,
    )

